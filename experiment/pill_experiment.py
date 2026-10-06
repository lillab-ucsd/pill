"""
Author(s): Tori Hennessy, Madison Wolfe, AJ Haskins
Description: This is the PILL experiment code. 
"""

from psychopy import visual, core, event, gui, logging
import tobii_research as tr
import os
import csv
from datetime import datetime


######## Settings ########

# set up paths
STIMULI_DIR = os.path.join(os.path.dirname(__file__), "stimuli", "pill_stimuli")
CONDITIONS_FILE = os.path.join(os.path.dirname(__file__), "pill_conditions.csv")
ATTENTION_GETTERS = [
    os.path.join(STIMULI_DIR, "attention_getters", "crazy_swirl.mp4"),
    os.path.join(STIMULI_DIR, "attention_getters", "crystal_ball.mp4"),
]

# coding window / attention getter timing (seconds)
MAX_CODING_WINDOW = 30
LOOK_AWAY_THRESHOLD = 2

# trials per task
N_FAM_TRIALS = 4
N_TEST_TRIALS = 4

# display settings
SCREEN_INDEX = 1
SCREEN_SIZE = (1920, 1080)

# map trial types to file name suffixes
TYPE_MAP = {"fam": "fam", "expected": "exp", "unexpected": "unexp"}

EVENT_COLS = [
    "sub_id", "condition", "task", "trial_type", "trial_number", "event",
    "coding_window", "ag", "gazeOnOff", "startTime", "endTime", "duration",
]
MISSING_SECONDS = 10  # print warning if no valid gaze for this long


######## Eye Tracker ########

# eye tracker variables (updated during the session)
trigger = ""  # tags the next gaze sample, e.g. start_video
eyetracker = None
gaze_path = gaze_file = gaze_writer = None
clock_offset = 0.0  # tobii system time (s) -> psychopy time (s)
last_valid_time = 0.0
gaze_warned = False


def setup_eyetracker():
    # finds connected tobii tracker, returns None if not found
    trackers = tr.find_all_eyetrackers()
    if not trackers:
        logging.warning("No eyetracker found!")
        return None
    return trackers[0]


def start_eyetracker(tracker):
    # opens the gaze csv and starts tobii recording
    global eyetracker, gaze_file, clock_offset, last_valid_time
    gaze_file = open(gaze_path, "w", newline="")
    clock_offset = core.getTime() - tr.get_system_time_stamp() / 1e6
    last_valid_time = core.getTime()
    eyetracker = tracker
    tracker.subscribe_to(tr.EYETRACKER_GAZE_DATA, gaze_data_callback, as_dictionary=True)


def gaze_data_callback(gaze_data):
    # writes gaze data to the gaze csv, adds psychopy time and event markers
    # also warns if no valid gaze for MISSING_SECONDS (10) - maybe modify this later
    global trigger, gaze_writer, last_valid_time, gaze_warned
    if gaze_file is None or gaze_file.closed:
        return
    t = gaze_data["system_time_stamp"] / 1e6 + clock_offset  # sample time (psychopy)
    gaze_data["psychopy_time"] = t  # matches event times
    gaze_data["triggers"] = trigger  # event marker, if any
    trigger = ""  # clear after use
    gaze_data["task"] = cur_task  # current task
    gaze_data["trial_type"] = cur_trial_type  # fam, exp, unexp
    gaze_data["trial_number"] = cur_trial_number  # trial 1-8
    if gaze_writer is None:
        gaze_writer = csv.DictWriter(gaze_file, fieldnames=list(gaze_data.keys()))  # first sample only
        gaze_writer.writeheader()
    gaze_writer.writerow(gaze_data)

    # warn once if no valid gaze for MISSING_SECONDS (10)
    if gaze_data["left_gaze_point_validity"] or gaze_data["right_gaze_point_validity"]:
        last_valid_time, gaze_warned = t, False  # reset warning timer
    elif t - last_valid_time > MISSING_SECONDS and not gaze_warned:
        print(f"[pill] WARNING: No gaze data in the last {MISSING_SECONDS} seconds")
        gaze_warned = True  # warn only once


######## Session Setup ########

def get_session_info():
    # gui dialog for subject id, eyetracker toggle, and condition (1-16)
    info = {"subject_id": "PILL_", "use_eyetracker": True, "condition": list(range(1, 17))}
    dlg = gui.DlgFromDict(info, title="PILL Experiment")
    if not dlg.OK:
        core.quit()
    return info


def get_trial_order(condition):
    # reads pill_conditions.csv and returns the row matching this condition number
    with open(CONDITIONS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["condition"]) == int(condition):
                return row
    raise ValueError(f"condition {condition} not found in {CONDITIONS_FILE}")


def get_task_trial_sequence(first_test_type):
    # 4 fam trials, then test trials alternating from first_test_type
    other = "unexpected" if first_test_type == "expected" else "expected"
    test_order = [first_test_type, other] * (N_TEST_TRIALS // 2)
    return ["fam"] * N_FAM_TRIALS + test_order


######## Data Files ########

# data file variables (continuously updated during the recording)
sub_id = condition = ""
cur_task = cur_trial_type = cur_trial_number = ""
event_file = event_writer = None


def setup_data_files(subject_id, cond, use_eyetracker):
    # opens the events csv now; the gaze csv opens in start_eyetracker
    global sub_id, condition, event_file, event_writer, gaze_path
    sub_id, condition = subject_id, cond
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    event_file = open(os.path.join(data_dir, f"{sub_id}_{stamp}_events.csv"), "w", newline="")
    event_writer = csv.DictWriter(event_file, fieldnames=EVENT_COLS)
    event_writer.writeheader()
    if use_eyetracker:
        gaze_path = os.path.join(data_dir, f"{sub_id}_{stamp}_gaze.csv")


def write_row(event_name, start, end, coding_window=0, ag=0, gaze_on_off=None):
    # one events row per stretch with a constant state
    event_writer.writerow({
        "sub_id": sub_id, "condition": condition, "task": cur_task,
        "trial_type": cur_trial_type, "trial_number": cur_trial_number,
        "event": event_name, "coding_window": coding_window, "ag": ag,
        "gazeOnOff": "" if gaze_on_off is None else gaze_on_off,
        "startTime": start, "endTime": end, "duration": end - start,
    })
    event_file.flush() # flush to disk in case of crash


def close_data_files():
    # stops tobii before closing the gaze file. safe to call twice
    global eyetracker
    if eyetracker is not None:
        eyetracker.unsubscribe_from(tr.EYETRACKER_GAZE_DATA, gaze_data_callback)
        eyetracker = None
    for f in (gaze_file, event_file):
        if f is not None and not f.closed:
            f.close()


def quit_session(win):
    # closes data files and the window, then exits
    close_data_files()
    win.close()
    core.quit()


######## Stimuli ########

_ag_index = 0  # alternates which AG video plays next between trials


def get_video_path(task, trial_type):
    # trial_type is "fam", "expected", or "unexpected"
    return os.path.join(STIMULI_DIR, task, f"{task}_{TYPE_MAP[trial_type]}.mp4")


def get_next_attention_getter():
    # alternates between the AG videos on each call
    global _ag_index
    video_path = ATTENTION_GETTERS[_ag_index % len(ATTENTION_GETTERS)]
    _ag_index += 1
    return video_path


def check_exit_key(win):
    # "x" exits the experiment immediately
    if "x" in event.getKeys(keyList=["x"]):
        quit_session(win)


def play_video(win, video_path):
    # plays video to completion, leaves last frame on screen
    movie = visual.MovieStim(win, video_path, loop=False, units="norm", size=(2, 2))  # fills the 16:9 screen
    movie.play()
    clock = core.Clock()
    print(f"[pill] playing {os.path.basename(video_path)}")
    while not movie.isFinished:
        check_exit_key(win)
        movie.draw()
        win.flip()
    movie.draw()
    win.flip()
    print(f"[pill] video finished after {clock.getTime():.1f}s")


def attention_getter(win):
    # loops the AG video; space advances to the next trial, r replays it
    global trigger
    video_path = get_next_attention_getter()
    ag_name = os.path.basename(video_path)
    trigger = "start_ag"
    ag_start = core.getTime()
    while True:
        movie = visual.MovieStim(win, video_path, loop=True, units="norm", size=(2, 2))
        while True:
            keys = event.getKeys(keyList=["x", "space", "r"])  # single call: getKeys clears the whole buffer
            if "x" in keys or "space" in keys:
                write_row(ag_name, ag_start, core.getTime(), ag=1)
                if "x" in keys:
                    quit_session(win)
                return
            if "r" in keys:
                break  # rebuild the movie and replay from the top
            movie.draw()
            win.flip()


######## Trial Flow ########

def coding_window(win, video_name):
    # space toggles look away/back, one events row per gaze on/off episode.
    # returns True if a look-away lasted LOOK_AWAY_THRESHOLD (AG needed).
    global trigger
    print("[pill] CODING WINDOW STARTS NOW!")
    trigger = "start_coding"
    window_start = core.getTime()
    seg_start = window_start
    looking = 1  # infant counts as looking until the first space press

    def close_segment(end):
        write_row(video_name, seg_start, end, coding_window=1, gaze_on_off=looking)

    while core.getTime() - window_start < MAX_CODING_WINDOW:
        keys = event.getKeys(keyList=["x", "space"])  # single call: getKeys clears the whole buffer
        now = core.getTime()
        if "x" in keys:
            close_segment(now)
            quit_session(win)
        for _ in range(keys.count("space")):  # count, in case two presses land in one poll
            close_segment(now)
            seg_start, looking = now, 1 - looking
            print("[pill] infant looked back" if looking else "[pill] look away")
        if looking == 0 and now - seg_start >= LOOK_AWAY_THRESHOLD:
            print("[pill] look-away confirmed, starting attention getter")
            close_segment(now)
            return True
        core.wait(0.01)  # small idle wait instead of flipping (keeps last frame on screen)
    close_segment(core.getTime())
    return False  # ran the full coding window


def run_trial(win, task, trial_type, trial_number):
    global cur_task, cur_trial_type, cur_trial_number, trigger
    cur_task, cur_trial_type, cur_trial_number = task, TYPE_MAP[trial_type], trial_number
    video_path = get_video_path(task, trial_type)
    trigger = "start_video"
    play_video(win, video_path)
    ended_early = coding_window(win, os.path.basename(video_path))
    if ended_early:
        attention_getter(win)


def main():
    info = get_session_info()
    trial_order = get_trial_order(info["condition"])
    setup_data_files(info["subject_id"], info["condition"], info["use_eyetracker"])
    tracker = setup_eyetracker() if info["use_eyetracker"] else None
    if info["use_eyetracker"] and tracker is None:
        print("[pill] WARNING: eyetracker box checked but none found, no gaze file will be saved")

    win = visual.Window(size=SCREEN_SIZE, screen=SCREEN_INDEX, fullscr=True, color="black", units="norm")
    print(f"[pill] requested {SCREEN_SIZE}, actual window size {tuple(win.size)}")

    if tracker is not None:
        start_eyetracker(tracker)  # records through the whole session
    try:
        # each task runs all its trials before the next task starts
        for task in [trial_order["task_1"], trial_order["task_2"]]:
            sequence = get_task_trial_sequence(trial_order["first_test_type"])
            for i, trial_type in enumerate(sequence, start=1):
                print(f"[pill] {task} trial {i}/{len(sequence)}: {trial_type}")
                run_trial(win, task, trial_type, i)
    finally:
        close_data_files()

    win.close()
    core.quit()


if __name__ == "__main__":
    main()
