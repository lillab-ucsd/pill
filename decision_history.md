# Decision History

Running log of methods and implementation decisions for PILL: parameter choices,
deviations from a spec or reference script, and the reasoning behind them. Covers the
experiment script, stimuli, and analysis. Newest at bottom.

## 2026-10-26: Calibration and validation added to the session flow

- **Decision:** `run_calibration_and_validation()` in `experiment/pill_experiment.py` runs before
  the "Ready to start!" screen whenever the eyetracker is used. Order: positioning screen
  (`show_status`), calibration, validation, pass/fail check.
- **Basis:** structure modeled after `calibration_routine()` in `moviewatching.py`
  (`movie-watching/experiment/moviewatching.py:144-262`), a collaborator's movie-watching
  experiment, adapted to PILL's version of
  `psychopy_tobii_infant`. Reuses the library's `run_calibration()` and `run_validation()`.
- Calibration uses the library's manual flow (1-5 shows a point, space collects, enter ends).
  Points can be redone from the calibration result screen before accepting.
- Validation shows the same pictures, at the same size, with the same pulsing and chime as
  calibration (1-5 shows a point, space collects), but each point can only be collected once
  and validation ends after the 5th point. Calibration is the visual check; validation is
  judged only by the tracker's accuracy numbers. Replaces the library's default fixed 1-5 order.
- **Not used:** the randomized automatic point order in `moviewatching.py`.
- Validation results screen shows first; the pass/fail line prints to the console after
  space is pressed (order copied from `moviewatching.py`).
- Validation runs on the same 5 points as calibration: (±0.8, ±0.8) and (0, 0) in norm units.
- `experiment/calibration.py` (standalone calibration script, never called from the
  experiment) deleted.

## 2026-10-26: tobii_research_addons copied into the repo

- **Decision:** Tobii's original `tobii_research_addons` source (github.com/tobiipro/
  prosdk-addons-python, Apache 2.0, license included) copied into
  `experiment/psychopy_tobii_infant/tobii_research_addons/`.
- **Basis:** `run_validation()` needs it, and it was not installed in the `leapvoe` env. It is
  not on PyPI. Keeping it in the repo means both lab machines get the same version with no
  install step.
- **Not used:** the copy in `movie-watching/experiment/tobii_research_addons/`, which was edited
  to import `mock_tobii_research` and would not import in PILL.
- **Known bug in the add-ons:** for a point that times out, `compute()` passes its arguments
  in the wrong order (`accuracy_left_eye` ends up holding the point's coordinates). PILL looks
  points up by position and treats any non-number as missing. The copy in
  `movie-watching/experiment/tobii_research_addons/` has the same bug.

## 2026-10-26: Validation pass/fail check, placeholder thresholds

- **Decision:** check copied from `calibration_routine()` in `moviewatching.py`. Each point's
  accuracy is averaged across the two eyes; a point is good if under `good_threshold` and bad
  if over `bad_threshold`. Points with no data count as bad. Passes with at least
  `min_good_points` good and at most `max_bad_points` bad. Settings are in `CALIBRATION_CONFIG`
  at the top of `pill_experiment.py`, layout modeled after `movie-watching/experiment/config.yaml`.
- Values: `good_threshold = 100`, `bad_threshold = 100`, `min_good_points = 3`,
  `max_bad_points = 2`, all marked TODO (not yet tuned). In practice, validation currently
  passes if at least 3 of 5 points give usable data.
- **Basis:** the thresholds are placeholders so the retry logic exists before real values are
  chosen (`config.yaml` uses 1.5 and 4 degrees). 3/2 points copied from the infant settings in
  `config.yaml` (`min_good_points_baby`, `max_bad_points_baby`).
- `max_retries = 2` (total attempts). If both fail, the session continues and a warning prints.
  Stopping the session was not used, to avoid losing infant sessions.
- **Not used:** the single-eye fallback in `moviewatching.py:244-248` (passes if either eye
  alone passes). Marked TODO in the code.
- No `later_validation` block, since PILL has no recalibration partway through the session.
- **TO-DO:** choose real threshold values once there is calibration data from PILL sessions.

## 2026-10-26: Validation data saved in two files (plus the session log)

- **Decision:** each session writes `{sub_id}_validation_summary.csv` (accuracy per point plus
  a mean row, degrees and pixels) and `{sub_id}_validation.csv` (every gaze sample used to
  compute accuracy, for replotting validation gaze). Each attempt is labeled `pre_validation_1`,
  `pre_validation_2`.
- **Basis:** file contents and column names copied from the two validation files written by
  `movie-watching/experiment/psychopy_tobii_infant.py`.
  Added `passed` to the summary and `psychopy_time` to the samples file (same clock as PILL's
  gaze and events files). `study_time` is ms since calibration started.
- **Not used:** `run_validation(save_to_file=True, event=...)` as called in `moviewatching.py`.
  PILL has the original library (v0.8.0), which has no `event=` parameter. Its `save_to_file`
  only writes to the library's own data file, which PILL never opens because PILL records gaze
  itself (`start_eyetracker()`).
- The pass/fail result is also saved in the session log and the `passed` column.
- Samples file only contains samples where both eyes were valid (the add-ons discard the rest).
  Same in `movie-watching/experiment/psychopy_tobii_infant.py`.
- Summary `point` label follows screen position (Point 1 = top left); in
  `movie-watching/experiment/psychopy_tobii_infant.py` it follows presentation order. Both
  files have `point_index` and `presentation_order`.

## 2026-10-26: Screen geometry

- **Assumption:** screen width = 52.7 cm, viewing distance = 62.5 cm, 1920 x 1080 px. Set as a
  PsychoPy monitor on the experiment window.
- **Basis:** 23.8" 16:9 EIZO FlexScan EV2480 (Tobii Pro Spectrum). Width computed from the
  23.8" diagonal assuming a 16:9 panel. Viewing distance is the middle of the expected
  60-65 cm.
- Only used to convert validation accuracy from degrees to pixels. Accuracy in degrees comes
  from Tobii's own screen setup in Eye Tracker Manager.

## 2026-10-26: Per-subject data folders, no overwriting

- **Decision:** all files for a session save to `data/{sub_id}/`. If that folder already exists,
  the start dialog shows "Subject ID already exists!" and opens again.
- **Basis:** previously all files went straight into `data/` and a repeated subject ID silently
  overwrote earlier files. Check modeled on `openOutputFileNew()` in
  `leap_voe/visual_learning/experiment/useful_functions_python3.py` (used by
  `PLAY_STATLEARN_try.py`).
- Subject data folders are not yet in `.gitignore`.

## 2026-10-26: Console output saved as a session log

- **Decision:** everything printed to the console, including PsychoPy warnings and crash
  errors, is written to `data/{sub_id}/{sub_id}_session.log` one line at a time as it happens.
- **Basis:** errors on the lab machine were otherwise lost when the terminal closed. Writing
  each line as it happens is modeled after `movie-watching/experiment/logging_config.py`, so
  the log survives the script being killed. Nothing prints during video drawing, so frame
  timing is not affected. Opted to not set up a separate `logging_config.py` file for now.

## 2026-10-26: First test on the lab setup (Windows machine)

- **TO-DO:** run a full session with the tracker and check:
  1. A new subject ID creates `data/{sub_id}/`; an existing ID shows "Subject ID already
     exists!" and the dialog opens again.
  2. Positioning screen shows both eyes; space continues.
  3. Calibration: 1-5 shows each picture with the chime, space collects, enter shows the
     result plot. Space accepts, or number keys select points to redo.
  4. Validation: 1-5 and space per point, a collected point can't be shown again, and
     validation ends after the 5th point.
  5. Results screen shows, then space prints `pre_validation_1: ... passed=...` to the console.
  6. `{sub_id}_validation_summary.csv` and `{sub_id}_validation.csv` fill in with real values,
     along with the events and gaze files.
