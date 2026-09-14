"""
PILL experiment: PsychoPy script for infant VOE gaze study.
Plays familiarization/expected/unexpected videos per task, records key-press looking time,
and logs Tobii gaze data alongside trial events.
"""

from psychopy import visual, core, event, gui, logging
import tobii_research as tr
import os
import csv
import subprocess
from datetime import datetime

# hides ffmpeg/swscaler warnings from video playback, keeps decode errors visible
try:
    from ffpyplayer.tools import set_loglevel
    set_loglevel("error")
except ImportError:
    pass

# tasks and stimulus folder names (final stimuli set, not yet in stimuli/pill_stimuli)
STIMULI_DIR = os.path.join(os.path.dirname(__file__), "stimuli", "pill_stimuli")
CONDITIONS_FILE = os.path.join(os.path.dirname(__file__), "pill_conditions.csv")
TASKS = ["goal", "efficiency", "support", "permanence"]
ATTENTION_GETTERS = [
    os.path.join(STIMULI_DIR, "attention_getters", "crazy_swirl.mp4"),
    os.path.join(STIMULI_DIR, "attention_getters", "crystal_ball.mp4"),
]
_ag_index = 0  # alternates which AG video plays next

# coding window / attention getter timing (seconds)
MAX_CODING_WINDOW = 30
LOOK_AWAY_THRESHOLD = 2

# trials per task
N_FAM_TRIALS = 4
N_TEST_TRIALS = 4

# display settings
SCREEN_INDEX = 1
SCREEN_SIZE = (1920, 1080)


def get_session_info():
    # gui dialog for subject id, eyetracker toggle, and condition (1-16)
    info = {"subject_id": "PILL_", "use_eyetracker": True, "condition": list(range(1, 17))}
    dlg = gui.DlgFromDict(info, title="PILL Experiment")
    if not dlg.OK:
        core.quit()
    return info


def setup_data_files(subject_id, use_eyetracker):
    # creates event log path, and gaze log path only if using the eyetracker
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    event_path = os.path.join(data_dir, f"{subject_id}_{timestamp}_events.csv")
    gaze_path = os.path.join(data_dir, f"{subject_id}_{timestamp}_gaze.csv") if use_eyetracker else None
    return event_path, gaze_path


def setup_eyetracker():
    # finds connected tobii tracker, returns None if not found
    trackers = tr.find_all_eyetrackers()
    if not trackers:
        logging.warning("No eyetracker found!")
        return None
    return trackers[0]


def gaze_data_callback(gaze_data, gaze_file):
    # todo: write gaze sample to gaze_file with shared clock reference
    pass


def get_trial_order(condition):
    # reads pill_conditions.csv and returns the row matching this condition number
    with open(CONDITIONS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["condition"]) == int(condition):
                return row
    raise ValueError(f"condition {condition} not found in {CONDITIONS_FILE}")


def get_video_path(task, trial_type):
    # trial_type is "fam", "expected", or "unexpected"
    return os.path.join(STIMULI_DIR, task, f"{task}_{trial_type}.mp4")


def check_exit_key(win):
    # "x" exits the experiment immediately
    if "x" in event.getKeys(keyList=["x"]):
        win.close()
        core.quit()


def get_native_video_size(video_path):
    # reads width/height via ffprobe so videos aren't stretched to the screen size
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path],
        capture_output=True, text=True
    )
    width, height = result.stdout.strip().split(",")
    return int(width), int(height)


def fit_size_norm(win, native_w, native_h):
    # size in norm units (window is always 2.0 x 2.0) that fits the video without
    # distortion. uses aspect ratios, so actual resolution and retina scaling don't matter
    win_aspect = win.size[0] / win.size[1]
    video_aspect = native_w / native_h
    if video_aspect > win_aspect:
        return (2.0, 2.0 * win_aspect / video_aspect)  # wider than window: fit to width
    return (2.0 * video_aspect / win_aspect, 2.0)  # taller than window: fit to height


def movie_finished(movie, clock):
    # psychopy versions differ on how movie end is reported, so check all of them
    if getattr(movie, "isFinished", False):
        return True
    if movie.status == visual.FINISHED:
        return True
    duration = getattr(movie, "duration", None)
    return duration is not None and clock.getTime() > duration


def play_video(win, video_path):
    # plays video to completion, leaves last frame on screen
    native_w, native_h = get_native_video_size(video_path)
    display_size = fit_size_norm(win, native_w, native_h)
    movie = visual.MovieStim(win, video_path, loop=False, units="norm", size=display_size)
    movie.play()
    clock = core.Clock()
    print(f"[pill] playing {os.path.basename(video_path)} (duration={getattr(movie, 'duration', None)})")
    while not movie_finished(movie, clock):
        check_exit_key(win)
        movie.draw()
        win.flip()
    movie.draw()
    win.flip()
    print(f"[pill] video finished after {clock.getTime():.1f}s")


def coding_window(win, event_file):
    # space toggles: first press = look away (starts timer), pressing again before
    # LOOK_AWAY_THRESHOLD = look back (cancels it). timer running out triggers the AG.
    # screen just holds the video's last frame, so no redraw/flip needed
    print("[pill] CODING WINDOW STARTS NOW!")
    look_away_time = None
    trial_clock = core.Clock()
    while trial_clock.getTime() < MAX_CODING_WINDOW:
        keys = event.getKeys(keyList=["x", "space"])  # single call: getKeys clears the whole buffer
        if "x" in keys:
            win.close()
            core.quit()
        for _ in range(keys.count("space")):  # count, in case two presses land in one poll
            if look_away_time is None:
                look_away_time = core.getTime()
                print("[pill] look away")
            else:
                look_away_time = None
                print("[pill] infant looked back")
        if look_away_time is not None and core.getTime() - look_away_time >= LOOK_AWAY_THRESHOLD:
            print("[pill] look-away confirmed, starting attention getter")
            return True  # look-away confirmed, needs an attention getter
        core.wait(0.01)  # small idle wait instead of flipping (keeps last frame on screen)
    # todo: log trial timing/outcome to event_file
    return False  # ran the full coding window


def get_next_attention_getter():
    # alternates between the AG videos on each call
    global _ag_index
    video_path = ATTENTION_GETTERS[_ag_index % len(ATTENTION_GETTERS)]
    _ag_index += 1
    return video_path


def attention_getter(win):
    # loops the AG video; space advances to the next trial, r replays it
    video_path = get_next_attention_getter()
    native_w, native_h = get_native_video_size(video_path)
    display_size = fit_size_norm(win, native_w, native_h)
    while True:
        movie = visual.MovieStim(win, video_path, loop=True, units="norm", size=display_size)
        while True:
            keys = event.getKeys(keyList=["x", "space", "r"])  # single call: getKeys clears the whole buffer
            if "x" in keys:
                win.close()
                core.quit()
            if "space" in keys:
                return
            if "r" in keys:
                break  # rebuild the movie and replay from the top
            movie.draw()
            win.flip()


def get_task_trial_sequence(first_test_type):
    # 4 fam trials, then test trials alternating from first_test_type
    other = "unexpected" if first_test_type == "expected" else "expected"
    test_order = [first_test_type, other] * (N_TEST_TRIALS // 2)
    return ["fam"] * N_FAM_TRIALS + test_order


def run_trial(win, task, trial_type, event_file):
    video_path = get_video_path(task, trial_type)
    play_video(win, video_path)
    ended_early = coding_window(win, event_file)
    if ended_early:
        attention_getter(win)
    # todo: log trial events


def main():
    info = get_session_info()
    trial_order = get_trial_order(info["condition"])
    event_path, gaze_path = setup_data_files(info["subject_id"], info["use_eyetracker"])
    eyetracker = setup_eyetracker() if info["use_eyetracker"] else None

    win = visual.Window(size=SCREEN_SIZE, screen=SCREEN_INDEX, fullscr=True, color="black", units="norm")
    print(f"[pill] requested {SCREEN_SIZE}, actual window size {tuple(win.size)}")

    # todo: start tobii gaze recording for whole session
    # each task runs all its trials before the next task starts
    for task in [trial_order["task_1"], trial_order["task_2"]]:
        sequence = get_task_trial_sequence(trial_order["first_test_type"])
        for i, trial_type in enumerate(sequence, start=1):
            print(f"[pill] {task} trial {i}/{len(sequence)}: {trial_type}")
            run_trial(win, task, trial_type, event_path)

    win.close()
    core.quit()


if __name__ == "__main__":
    main()
