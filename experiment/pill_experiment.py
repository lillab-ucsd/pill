"""
Author(s): Tori Hennessy
Description: This is the PILL experiment code.
"""

from psychopy import core, gui, logging
import tobii_research as tr
import atexit
import os
import csv
import glob
import math
import sys
import numpy as np
from datetime import datetime


######## Settings ########

# set up paths
STIMULI_DIR = os.path.join(os.path.dirname(__file__), "stimuli", "pill_stimuli")
CONDITIONS_FILE = os.path.join(os.path.dirname(__file__), "pill_conditions.csv")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")  # one subfolder per subject
ATTENTION_GETTERS = [
    os.path.join(STIMULI_DIR, "attention_getters", "crazy_swirl.mp4"),
    os.path.join(STIMULI_DIR, "attention_getters", "crystal_ball.mp4"),
]
BG_COLOR = "#d9ccfd"  # light lavender, start/end screen background
END_SCREEN_SECONDS = 5  # how long "All done!" stays up
KID_FONT = "Georgia"  # start/end screen font, built into mac and windows

# coding window / attention getter timing (seconds)
MAX_CODING_WINDOW = 30
LOOK_AWAY_THRESHOLD = 2
LOOK_KEY = "B"  # coder holds this key while the infant is looking

# trials per task
N_FAM_TRIALS = 4
N_TEST_TRIALS = 4

# display settings
SCREEN_INDEX = 1
SCREEN_SIZE = (1920, 1080)
SCREEN_WIDTH_CM = 52.7  # 23.8" 16:9 EIZO (tobii pro spectrum), from the diagonal
VIEWING_DISTANCE_CM = 62.5  # infant sits ~60-65 cm from the screen

# calibration stimuli and the 5 calibration/validation points (norm units)
CALIB_DIR = os.path.join(os.path.dirname(__file__), "CalibrationStim")
CALIB_POINTS = [(-0.8, 0.8), (-0.8, -0.8), (0.0, 0.0), (0.8, 0.8), (0.8, -0.8)]

# validation check.
# a point is "good" under good_threshold and "bad" over bad_threshold (degrees, mean of both eyes),
# points with no data count as bad. validation passes with >= min_good_points good and <= max_bad_points bad
CALIBRATION_CONFIG = {
    "initial_validation": {
        "max_retries": 2,  # total attempts including the first
        "good_threshold": 100,  # TODO: not yet tuned, revisit once we have real calibration data
        "bad_threshold": 100,  # TODO: not yet tuned, revisit once we have real calibration data
    },
    "general_validation": {
        "min_good_points": 3,  # TODO: not yet tuned, revisit once we have real calibration data
        "max_bad_points": 2,  # TODO: not yet tuned, revisit once we have real calibration data
    },
}

# map trial types to file name suffixes
TYPE_MAP = {"fam": "fam", "expected": "exp", "unexpected": "unexp"}

EVENT_COLS = [
    "sub_id", "condition", "task", "trial_type", "trial_number", "event",
    "coding_window", "ag", "gazeOnOff", "startTime", "endTime", "duration",
]
MISSING_SECONDS = 10  # print warning if no valid gaze for this long

# validation summary: one row per validation point plus a mean row, per attempt
VALIDATION_SUMMARY_COLS = [
    "point", "point_index", "presentation_order", "stimulus_x", "stimulus_y", "validation_step",
    "Mean_accuracy_degrees_left", "Mean_accuracy_degrees_right",
    "Mean_accuracy_pixels_left", "Mean_accuracy_pixels_right", "passed",
]
# validation samples: every gaze sample the accuracy was computed from, for replotting validation gaze.
# positions in pixels (origin bottom-left), study_time in ms since calibration started
VALIDATION_SAMPLE_COLS = [
    "stimulus_x", "stimulus_y", "point_index", "presentation_order", "validation_step",
    "system_time_stamp", "study_time", "left_x", "left_y", "left_valid",
    "right_x", "right_y", "right_valid", "gaze_x", "gaze_y", "psychopy_time",
]

# hides ffmpeg/swscaler warnings from video playback, keeps decode errors visible
try:
    from ffpyplayer.tools import set_loglevel
    set_loglevel("error")
except ImportError:
    pass


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
    # gui dialog for subject id, eyetracker toggle, and condition (1-16).
    # asks again if the subject already has a data folder, so nothing gets overwritten
    while True:
        info = {"subject_id": "PILL_", "use_eyetracker": True, "condition": list(range(1, 17))}
        dlg = gui.DlgFromDict(info, title="PILL Experiment")
        if not dlg.OK:
            core.quit()
        if not os.path.exists(os.path.join(DATA_DIR, info["subject_id"])):
            return info
        error = gui.Dlg(title="Error")
        error.addText("Subject ID already exists!", color="red")
        error.show()


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
validation_summary_path = validation_samples_path = None


def setup_data_files(subject_id, cond, use_eyetracker):
    # opens the events csv now; the gaze csv opens in start_eyetracker,
    # the validation files in run_calibration_and_validation
    global sub_id, condition, event_file, event_writer, gaze_path, validation_summary_path, validation_samples_path
    sub_id, condition = subject_id, cond
    data_dir = os.path.join(DATA_DIR, sub_id)
    os.makedirs(data_dir)  # get_session_info already checked it doesn't exist
    open_console_log(data_dir)
    event_file = open(os.path.join(data_dir, f"{sub_id}_events.csv"), "w", newline="")
    event_writer = csv.DictWriter(event_file, fieldnames=EVENT_COLS)
    event_writer.writeheader()
    if use_eyetracker:
        gaze_path = os.path.join(data_dir, f"{sub_id}_gaze.csv")
        validation_summary_path = os.path.join(data_dir, f"{sub_id}_validation_summary.csv")
        validation_samples_path = os.path.join(data_dir, f"{sub_id}_validation.csv")


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


# everything printed to the console (including psychopy warnings and crash errors) is copied to
# {sub_id}_session.log as it happens. lines printed before the subject folder exists are held
# in console_text and written when the log opens
console_text = []
console_log = None


class ConsoleCopy:
    # stands in for sys.stdout/sys.stderr: prints as usual and copies to the session log
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        if console_log is None:
            console_text.append(text)
        else:
            console_log.write(text)
            console_log.flush()  # so the log survives the script being killed
        return self.stream.write(text)

    def __getattr__(self, name):
        return getattr(self.stream, name)  # flush, fileno, etc. go to the real console


def start_console_log():
    sys.stdout, sys.stderr = ConsoleCopy(sys.stdout), ConsoleCopy(sys.stderr)
    print(f"[pill] session started {datetime.now():%Y-%m-%d %H:%M:%S}")


def open_console_log(data_dir):
    # called once the subject folder exists, writes everything printed so far
    global console_log
    console_log = open(os.path.join(data_dir, f"{sub_id}_session.log"), "w", encoding="utf-8")
    console_log.write("".join(console_text))
    console_log.flush()
    console_text.clear()


def quit_session(win):
    # closes data files, stops any playing video, shows the end screen, then exits
    close_data_files()
    for movie in movies.values():
        movie.pause()  # so no video audio plays over the end screen
    end_screen(win)
    win.close()
    core.quit()


######## Stimuli ########

_ag_index = 0  # alternates which AG video plays next between trials
movies = {}  # video path -> movie, each opened once in load_movies (same approach as PyHab)


def get_video_path(task, trial_type):
    # trial_type is "fam", "expected", or "unexpected"
    return os.path.join(STIMULI_DIR, task, f"{task}_{TYPE_MAP[trial_type]}.mp4")


def get_next_attention_getter():
    # alternates between the AG videos on each call
    global _ag_index
    video_path = ATTENTION_GETTERS[_ag_index % len(ATTENTION_GETTERS)]
    _ag_index += 1
    return video_path


def load_movies(win, tasks):
    # opens every video for this session once, before the start screen.
    # opening/unloading players mid-session crashed or lagged on windows
    paths = [get_video_path(task, t) for task in tasks for t in TYPE_MAP] + ATTENTION_GETTERS
    for path in paths:
        movies[path] = visual.MovieStim(
            win, path, loop=path in ATTENTION_GETTERS, units="norm", size=(2, 2)  # fills the 16:9 screen
        )
    print(f"[pill] loaded {len(movies)} videos")


def rewind(movie):
    # stops playback (and audio) and goes back to the start for the next play
    movie.pause()
    movie.seek(0.0)


def check_exit_key(win):
    # "x" exits the experiment immediately
    if "x" in event.getKeys(keyList=["x"]):
        quit_session(win)


def play_video(win, video_path):
    # plays video to completion, leaves last frame on screen
    movie = movies[video_path]
    movie.play()
    clock = core.Clock()
    print(f"[pill] playing {os.path.basename(video_path)}")
    while not movie.isFinished:
        check_exit_key(win)
        movie.draw()
        win.flip()
    movie.draw()
    win.flip()
    rewind(movie)  # last frame stays on screen until the next flip
    print(f"[pill] video finished after {clock.getTime():.1f}s")


def attention_getter(win):
    # loops the AG video until space advances to the next trial
    global trigger
    video_path = get_next_attention_getter()
    movie = movies[video_path]
    ag_name = os.path.basename(video_path)
    event.clearEvents(eventType="keyboard")  # drop earlier presses so space must be pressed now
    trigger = "start_ag"
    ag_start = core.getTime()
    movie.play()
    while True:
        keys = event.getKeys(keyList=["x", "space"])  # single call: getKeys clears the whole buffer
        if "x" in keys or "space" in keys:
            write_row(ag_name, ag_start, core.getTime(), ag=1)
            rewind(movie)  # stops AG audio, ready for next time
            if "x" in keys:
                quit_session(win)
            return
        movie.draw()
        win.flip()


def show_message(win, text):
    # lavender background with centered text, used by start_screen and end_screen
    visual.Rect(win, width=2, height=2, units="norm", fillColor=BG_COLOR, lineColor=BG_COLOR).draw()
    visual.TextStim(win, text=text, font=KID_FONT, color="black", height=0.12, units="norm").draw()
    win.flip()


def start_screen(win):
    # "Ready to start!" until space is pressed (x quits)
    show_message(win, "Ready to start!")
    if "x" in event.waitKeys(keyList=["space", "x"]):
        quit_session(win)


def end_screen(win):
    # "All done!" for END_SCREEN_SECONDS, like the visual learning script
    show_message(win, "All done!")
    core.wait(END_SCREEN_SECONDS)


######## Calibration ########

def as_degrees(value):
    # accuracy rounded to 4 places, or None if missing (NaN, or not a number on timed-out points)
    if isinstance(value, float) and not math.isnan(value):
        return round(value, 4)
    return None


def as_pixels(degrees, monitor):
    # degrees -> pixels on this monitor, None stays None
    return None if degrees is None else round(deg2pix(degrees, monitor), 4)


def manual_validation(controller, validation_points, _focus_time=0.5, collect_key="space", exit_key="return"):
    # validation shown the same way as calibration: 1-5 shows that point's picture (with chime),
    # space collects. each point can only be collected once (no redos, pass/fail comes from
    # check_validation). ends after the last point, or early with enter (skipped points count as missing).
    # copied from _update_calibration_infant in psychopy_tobii_infant.
    # collection order is kept in controller.validation_order for the summary file
    controller.validation_order = []
    event.clearEvents()
    point_idx = -1
    clock = core.Clock()
    while len(controller.validation_order) < len(validation_points):
        for key in event.getKeys():
            if key in controller.numkey_dict:
                if controller.numkey_dict[key] in controller.validation_order:
                    continue  # already collected
                point_idx = controller.numkey_dict[key]
                if point_idx >= 0 and controller._audio is not None:
                    controller._audio.play()
            elif key == collect_key and 0 <= point_idx < len(validation_points):
                core.wait(_focus_time, 0.0)  # let the infant focus
                controller._collect_validation_data(validation_points[point_idx])
                controller.validation_order.append(point_idx)
                point_idx = -1
                if controller._audio is not None:
                    controller._audio.pause()
            elif key == exit_key:
                return

        # pulsing picture, same as calibration
        if 0 <= point_idx < len(validation_points):
            target = controller.targets.get_stim(point_idx)
            target.setPos(validation_points[point_idx])
            t = clock.getTime() * controller.shrink_speed
            target.setSize([(np.sin(t) ** 2 + controller.calibration_target_min) * e
                            for e in controller.targets.get_stim_original_size(point_idx)])
            target.draw()
        controller.win.flip()


def to_pixels(x, y, size):
    # tobii display coordinates (0-1, origin top-left) -> pixels, origin bottom-left
    return round(x * size[0], 4), round(size[1] - y * size[1], 4)


def validation_points_by_index(controller, result):
    # {point_index (1-5): latest collection at that point}.
    # matched by key: the add-ons mix up the fields of timed-out points (accuracy_left_eye ends up a Point2)
    by_pos = {(round(k.x, 6), round(k.y, 6)): v[-1] for k, v in result.points.items()}
    points = {}
    for i, pos in enumerate(CALIB_POINTS, start=1):
        x, y = controller._get_tobii_pos(pos)
        if (round(x, 6), round(y, 6)) in by_pos:
            points[i] = by_pos[(round(x, 6), round(y, 6))]
    return points


def presentation_order(controller, i):
    # when point i (1-5) was collected, None if skipped
    order = getattr(controller, "validation_order", [])
    return order.index(i - 1) + 1 if i - 1 in order else None


def validation_samples(controller, result, step, t0, offset):
    # one row per gaze sample collected at each validation point.
    # t0 = tobii time (microseconds) when calibration started, offset = tobii seconds -> psychopy seconds
    size = controller.win.size
    rows = []
    for i, point in sorted(validation_points_by_index(controller, result).items(),
                           key=lambda item: presentation_order(controller, item[0]) or 0):
        stim_x, stim_y = to_pixels(*controller._get_tobii_pos(CALIB_POINTS[i - 1]), size)
        for s in point.gaze_data:
            left_x, left_y = to_pixels(*s.left_eye.gaze_point.position_on_display_area, size)
            right_x, right_y = to_pixels(*s.right_eye.gaze_point.position_on_display_area, size)
            rows.append({
                "stimulus_x": stim_x, "stimulus_y": stim_y, "point_index": i,
                "presentation_order": presentation_order(controller, i), "validation_step": step,
                "system_time_stamp": s.system_time_stamp,
                "study_time": round((s.system_time_stamp - t0) / 1000.0, 2),
                "left_x": left_x, "left_y": left_y, "left_valid": bool(s.left_eye.gaze_point.validity),
                "right_x": right_x, "right_y": right_y, "right_valid": bool(s.right_eye.gaze_point.validity),
                "gaze_x": round(np.nanmean([left_x, right_x]), 4), "gaze_y": round(np.nanmean([left_y, right_y]), 4),
                "psychopy_time": s.system_time_stamp / 1e6 + offset,
            })
    return rows


def check_validation(controller, result, step):
    # sorts each point as good/bad by its two-eye mean accuracy.
    # returns the validation summary rows and whether the check passed
    cfg = {**CALIBRATION_CONFIG["initial_validation"], **CALIBRATION_CONFIG["general_validation"]}
    mon = controller.win.monitor
    missing = cfg["bad_threshold"] + 0.01  # points with no data count as just over bad_threshold
    points = validation_points_by_index(controller, result)
    rows, means = [], []
    for i, pos in enumerate(CALIB_POINTS, start=1):
        point = points.get(i)
        left = as_degrees(point.accuracy_left_eye) if point else None
        right = as_degrees(point.accuracy_right_eye) if point else None
        means.append(((missing if left is None else left) + (missing if right is None else right)) / 2)
        stim_x, stim_y = to_pixels(*controller._get_tobii_pos(pos), controller.win.size)
        rows.append({
            "point": f"Point {i}", "point_index": i, "presentation_order": presentation_order(controller, i),
            "stimulus_x": stim_x, "stimulus_y": stim_y, "validation_step": step, "Mean_accuracy_degrees_left": left, "Mean_accuracy_degrees_right": right,
            "Mean_accuracy_pixels_left": as_pixels(left, mon), "Mean_accuracy_pixels_right": as_pixels(right, mon),
        })

    good = sum(m < cfg["good_threshold"] for m in means)
    bad = sum(m > cfg["bad_threshold"] for m in means)
    passed = good >= cfg["min_good_points"] and bad <= cfg["max_bad_points"]
    # TODO: consider also passing if either eye alone passes

    left_mean = as_degrees(result.average_accuracy_left)
    right_mean = as_degrees(result.average_accuracy_right)
    rows.append({
        "point": "mean", "validation_step": step,
        "Mean_accuracy_degrees_left": left_mean, "Mean_accuracy_degrees_right": right_mean,
        "Mean_accuracy_pixels_left": as_pixels(left_mean, mon), "Mean_accuracy_pixels_right": as_pixels(right_mean, mon),
    })
    for row in rows:
        row["passed"] = passed
    print(f"[pill] {step}: left={left_mean} right={right_mean} degrees, "
          f"good points={good}/{len(CALIB_POINTS)}, bad points={bad}/{len(CALIB_POINTS)}, passed={passed}")
    return rows, passed


def run_calibration_and_validation(win, label="pre_validation"):
    # positioning screen, then calibrate + validate until the check passes or max_retries runs out.
    # the experiment continues either way, a failed check is only printed and saved
    from psychopy import sound
    import psychopy_tobii_infant as pti  # slow, only loaded when the eyetracker is used

    controller = pti.TobiiInfantController(win)
    atexit.unregister(controller.close)  # controller has no data file of its own, close() would error at exit
    controller.update_validation = lambda **kw: manual_validation(controller, **kw)  # library default is fixed order
    stims = sorted(glob.glob(os.path.join(CALIB_DIR, "*.png")))
    audio = sound.Sound(os.path.join(CALIB_DIR, "upchime1.wav"))
    max_retries = CALIBRATION_CONFIG["initial_validation"]["max_retries"]

    controller.show_status()  # experimenter checks the infant's position, space to continue
    if not pti._has_addons:
        print("[pill] WARNING: tobii_research_addons not found, calibrating without validation")
        controller.run_calibration(CALIB_POINTS, stims, audio=audio)
        return

    t0 = tr.get_system_time_stamp()  # study_time zero in the validation samples file
    offset = core.getTime() - t0 / 1e6  # tobii seconds -> psychopy seconds, same as the gaze file
    with open(validation_summary_path, "w", newline="") as summary_file, \
            open(validation_samples_path, "w", newline="") as samples_file:
        summary_writer = csv.DictWriter(summary_file, fieldnames=VALIDATION_SUMMARY_COLS)
        samples_writer = csv.DictWriter(samples_file, fieldnames=VALIDATION_SAMPLE_COLS)
        summary_writer.writeheader()
        samples_writer.writeheader()
        for attempt in range(1, max_retries + 1):
            step = f"{label}_{attempt}"
            print(f"[pill] calibration attempt {attempt}/{max_retries}")
            if not controller.run_calibration(CALIB_POINTS, stims, audio=audio):
                print("[pill] WARNING: calibration aborted (esc), counting as a failed attempt")
            else:
                result = controller.run_validation(validation_points=CALIB_POINTS, show_results=True, save_to_file=False)
                samples_writer.writerows(validation_samples(controller, result, step, t0, offset))
                rows, passed = check_validation(controller, result, step)
                summary_writer.writerows(rows)
                summary_file.flush()
                samples_file.flush()
                if passed:
                    return
            if attempt < max_retries:
                show_message(win, "Recalibrating...")
                core.wait(2)
    print(f"[pill] WARNING: validation did not pass after {max_retries} attempts, continuing anyway")


######## Trial Flow ########

# held-key tracking (set up in main once the window exists)
pyglet_key = None
key_state = None


def coding_window(win, video_name):
    # LOOK_KEY held = looking, released = look away. one events row per gaze on/off episode.
    # returns True if a look-away lasted LOOK_AWAY_THRESHOLD (AG needed).
    global trigger
    print("[pill] CODING WINDOW STARTS NOW!")
    trigger = "start_coding"
    event.clearEvents(eventType="keyboard")  # ignore presses made before the window
    look_key = getattr(pyglet_key, LOOK_KEY)
    window_start = core.getTime()
    seg_start = window_start
    looking = int(key_state[look_key])  # starts as whatever the key is doing now
    has_looked = looking == 1  # no auto-advance until B has been held at least once

    def close_segment(end):
        write_row(video_name, seg_start, end, coding_window=1, gaze_on_off=looking)

    while core.getTime() - window_start < MAX_CODING_WINDOW:
        win.winHandle.dispatch_events()  # updates key_state without a flip
        now = core.getTime()
        if "x" in event.getKeys(keyList=["x"]):
            close_segment(now)
            quit_session(win)
        held = int(key_state[look_key])
        if held != looking:
            close_segment(now)
            seg_start, looking = now, held
            has_looked = has_looked or held == 1
            print("[pill] infant is looking" if looking else "[pill] look away!")
        if has_looked and looking == 0 and now - seg_start >= LOOK_AWAY_THRESHOLD:
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


def guard_mac_events(win):
    # mac only: pyglet sometimes gets a bad event while keys are pressed and crashes
    # this is annoying af if you are trying to test on a mac, so this handles it
    # wraps the window's event pump so that event is skipped instead
    original = win.winHandle.dispatch_events

    def safe_dispatch():
        try:
            original()
        except AttributeError:
            pass  # skip the bad event

    win.winHandle.dispatch_events = safe_dispatch


def main():
    start_console_log()
    info = get_session_info()
    global visual, event, monitors, deg2pix
    from psychopy import visual, event, monitors  # ~17 s on the mac, so loaded after the dialog
    from psychopy.tools.monitorunittools import deg2pix
    trial_order = get_trial_order(info["condition"])
    setup_data_files(info["subject_id"], info["condition"], info["use_eyetracker"])
    tracker = setup_eyetracker() if info["use_eyetracker"] else None
    if info["use_eyetracker"] and tracker is None:
        print("[pill] WARNING: eyetracker box checked but none found, no gaze file will be saved")

    # physical screen size + distance, used to convert validation accuracy from degrees to pixels
    mon = monitors.Monitor("pill", width=SCREEN_WIDTH_CM, distance=VIEWING_DISTANCE_CM)
    mon.setSizePix(SCREEN_SIZE)
    win = visual.Window(size=SCREEN_SIZE, screen=SCREEN_INDEX, fullscr=True, color="black", units="norm", monitor=mon)
    print(f"[pill] requested {SCREEN_SIZE}, actual window size {tuple(win.size)}")

    # track held keys directly through pyglet (psychopy's event module only sees key presses)
    global pyglet_key, key_state
    from pyglet.window import key as pyglet_key
    key_state = pyglet_key.KeyStateHandler()
    win.winHandle.push_handlers(key_state)
    if sys.platform == "darwin":
        guard_mac_events(win)

    tasks = [trial_order["task_1"], trial_order["task_2"]]
    load_movies(win, tasks)  # all videos open once, before the start screen
    if tracker is not None:
        run_calibration_and_validation(win)
    start_screen(win)

    if tracker is not None:
        start_eyetracker(tracker)  # records through the whole session
    try:
        # each task runs all its trials before the next task starts
        for task in tasks:
            sequence = get_task_trial_sequence(trial_order["first_test_type"])
            for i, trial_type in enumerate(sequence, start=1):
                print(f"[pill] {task} trial {i}/{len(sequence)}: {trial_type}")
                run_trial(win, task, trial_type, i)
    finally:
        close_data_files()

    end_screen(win)
    win.close()
    core.quit()


if __name__ == "__main__":
    main()
