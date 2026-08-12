"""
Joins I2MC fixations (data/leap_voe_data/fixations/[subject]/[subject]_leap_voe_gaze_fix.csv)
to what was on screen at that time, using each subject's timing file
(data/leap_voe_data/raw_events/timing/[subject]_leap_voe_timing.csv).

Adds three columns to each fixation:
- trial_num: trial number active at the fixation's midpoint
- phase: 'attn_getter' | 'movie' | 'still' | 'inter_trial'
- trial_type: e.g. "expected_duck", "surprise_shoe", "fam_duck" (blank during inter_trial)

Output: data/leap_voe_data/fixations/[subject]/[subject]_leap_voe_gaze_fix_labeled.csv

Subjects missing a fixation file or a timing file are skipped (printed, not an error).
"""

from pathlib import Path
import pandas as pd


# =============================================================================
# 1. Setup
# =============================================================================

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

fixations_folder = project_root / 'data' / 'leap_voe_data' / 'fixations'
timing_folder = project_root / 'data' / 'leap_voe_data' / 'raw_events' / 'timing'

subject_dirs = sorted(fixations_folder.glob('*_leap_voe_gaze'))
print(f"Found {len(subject_dirs)} subject fixation folders")


# =============================================================================
# 2. Trial-type naming (generalized from 0_convert_tsv.py: works for MOV or STILL)
# =============================================================================

def get_trial_type_short_name(trial_type_str):
    """e.g. "Test.EXP_DUCK.EXP_DUCK_MOV" or "...EXP_DUCK_STILL" -> "expected_duck"."""
    if not isinstance(trial_type_str, str):
        return ""

    if trial_type_str.startswith('Fam.'):
        phase = 'fam'
    elif 'SUR_' in trial_type_str:
        phase = 'surprise'
    elif 'EXP_' in trial_type_str:
        phase = 'expected'
    else:
        return ""

    if 'DUCK' in trial_type_str:
        obj = 'duck'
    elif 'SHOE' in trial_type_str:
        obj = 'shoe'
    else:
        return ""

    return f"{phase}_{obj}"


# =============================================================================
# 3. Build labeled windows for one subject from their timing file
# =============================================================================

def build_trial_windows(timing_df):
    """
    Returns a list of (trial_num, phase, trial_type, t_start, t_end) windows,
    covering attention-getters, movie playback, and still/coding periods, plus
    the gaps between trials as 'inter_trial'. Times in ms, sorted by t_start.

    trial_type is suffixed with a presentation index, e.g. "surprise_shoe_1",
    "surprise_shoe_2", since each expected/surprise clip is shown twice. A
    STILL trial is always the MOV trial immediately before it (trialNum + 1)
    and shares its presentation index.
    """
    trial_groups = sorted(timing_df.groupby('trialNum'), key=lambda x: x[0])

    # First pass: assign a presentation index per trial_type, incrementing on
    # each MOV/Fam trial (the "real" presentation) and having each STILL
    # trial inherit its paired MOV trial's index.
    occurrence_counter = {}
    occurrence_by_trial = {}
    for trial_num, trial_df in trial_groups:
        trial_type_full = trial_df['trialType'].iloc[0]
        trial_type = get_trial_type_short_name(trial_type_full)
        is_still = trial_type_full.endswith('_STILL')

        if is_still:
            occurrence_by_trial[trial_num] = occurrence_by_trial.get(trial_num - 1)
        else:
            occurrence_counter[trial_type] = occurrence_counter.get(trial_type, 0) + 1
            occurrence_by_trial[trial_num] = occurrence_counter[trial_type]

    windows = []

    for trial_num, trial_df in trial_groups:
        events = dict(zip(trial_df['event'], trial_df['time']))
        trial_type_full = trial_df['trialType'].iloc[0]
        trial_type = get_trial_type_short_name(trial_type_full)
        is_still = trial_type_full.endswith('_STILL')

        occurrence = occurrence_by_trial.get(trial_num)
        if trial_type and occurrence is not None:
            trial_type = f"{trial_type}_{occurrence}"

        # Attention-getter (MOV trials only)
        if 'startAttnGetter' in events and 'endAttnGetter' in events:
            windows.append((trial_num, 'attn_getter', trial_type,
                             events['startAttnGetter'] * 1000, events['endAttnGetter'] * 1000))

        if is_still:
            # Still/coding window: whole trial is the freeze period
            if 'startTrial' in events and 'endTrial' in events:
                windows.append((trial_num, 'still', trial_type,
                                 events['startTrial'] * 1000, events['endTrial'] * 1000))
        else:
            # Movie window: prefer actual playback timestamps, fall back to trial bounds
            if 'startMoviePlayback' in events and 'endMoviePlayback' in events:
                windows.append((trial_num, 'movie', trial_type,
                                 events['startMoviePlayback'] * 1000, events['endMoviePlayback'] * 1000))
            elif 'startTrial' in events and 'endTrial' in events:
                windows.append((trial_num, 'movie', trial_type,
                                 events['startTrial'] * 1000, events['endTrial'] * 1000))

    windows.sort(key=lambda w: w[3])

    # Fill gaps between windows (and before the first / after the last) as inter_trial
    filled = []
    prev_end = 0.0
    for w in windows:
        t_start = w[3]
        if t_start > prev_end:
            filled.append((None, 'inter_trial', '', prev_end, t_start))
        filled.append(w)
        prev_end = max(prev_end, w[4])
    filled.append((None, 'inter_trial', '', prev_end, float('inf')))

    return filled


def label_fixation(windows, start_t, end_t):
    """Find the window containing this fixation's midpoint."""
    mid = (start_t + end_t) / 2
    for trial_num, phase, trial_type, t_start, t_end in windows:
        if t_start <= mid <= t_end:
            return trial_num, phase, trial_type
    return None, 'inter_trial', ''


# =============================================================================
# 4. Process all subjects
# =============================================================================

if __name__ == "__main__":
    n_labeled = 0
    n_skipped = 0

    for subj_dir in subject_dirs:
        subject_name = subj_dir.name  # e.g. "138_leap_voe_gaze"
        subject_num = subject_name.replace('_leap_voe_gaze', '')

        fix_path = subj_dir / f"{subject_name}_fix.csv"
        timing_path = timing_folder / f"{subject_num}_leap_voe_timing.csv"

        if not fix_path.exists():
            print(f"  Skipping {subject_num}: no fixation file")
            n_skipped += 1
            continue
        if not timing_path.exists():
            print(f"  Skipping {subject_num}: no timing file")
            n_skipped += 1
            continue

        fix_df = pd.read_csv(fix_path)
        timing_df = pd.read_csv(timing_path)

        windows = build_trial_windows(timing_df)

        labels = fix_df.apply(
            lambda row: label_fixation(windows, row['startT'], row['endT']),
            axis=1, result_type='expand'
        )
        labels.columns = ['trial_num', 'phase', 'trial_type']

        labeled_df = pd.concat([fix_df, labels], axis=1)

        output_path = subj_dir / f"{subject_name}_fix_labeled.csv"
        labeled_df.to_csv(output_path, index=False)

        phase_counts = labeled_df['phase'].value_counts().to_dict()
        print(f"  {subject_num}: {len(labeled_df)} fixations labeled -> {output_path.name}  {phase_counts}")
        n_labeled += 1

    print(f"\n{'='*60}")
    print(f"Labeled {n_labeled} subjects, skipped {n_skipped}")
    print(f"{'='*60}")
