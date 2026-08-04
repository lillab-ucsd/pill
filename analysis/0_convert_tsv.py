"""
Converts raw VOE gaze TSVs (raw_gaze/tsv) into CSVs (raw_gaze/csv) for I2MC.

Output columns:
- device_time_stamp: gaze sample timestamp in ms
- left_gaze_point_on_display_area / right_gaze_point_on_display_area: normalized (0-1) gaze coords per eye
- left_gaze_point_validity / right_gaze_point_validity: 1 if that eye's sample is valid, else 0
- off_screen: 1 if gaze falls outside the stimulus area, else 0
- gaze_event_tag: raw trial-event label active at that timestamp
- trial_type: short trial label (e.g. "expected_duck"), set only during STILL trials (coding window)
- event_info: marks "start_event"/"end_event" rows for each STILL trial
"""

from pathlib import Path
import pandas as pd


# =============================================================================
# 1. Setup
# =============================================================================

# Set up paths
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# Input paths
raw_gaze_folder = project_root / 'data' / 'leap_voe_data' / 'raw_gaze'
raw_gaze_tsv_folder = raw_gaze_folder / 'tsv'
timing_folder = project_root / 'data' / 'leap_voe_data' / 'raw_events' / 'timing'

# Output path
output_folder = raw_gaze_folder / 'csv'
output_folder.mkdir(parents=True, exist_ok=True)

# Gaze files: "[subject]_leap_voe_gaze.tsv"
tsv_files = sorted(raw_gaze_tsv_folder.glob('*_leap_voe_gaze.tsv'))

print(f"Found {len(tsv_files)} TSV files to convert")


# =============================================================================
# 2. Conversion Function
# =============================================================================

def convert_tsv_to_csv(tsv_file, output_folder, timing_folder, screen_res=(1920, 1080)):
    """
    Convert one gaze TSV to CSV, adding event/trial-type info from the timing file.

    tsv_file: input TSV ("[subject]_leap_voe_gaze.tsv")
    output_folder: where the output CSV is saved
    timing_folder: folder with "[subject]_leap_voe_timing.csv"
    screen_res: (width, height) for normalizing coordinates
    """
    print(f"\nProcessing: {tsv_file.name}")

    # Subject number = filename minus "_leap_voe_gaze"
    subject_num = tsv_file.stem.replace('_leap_voe_gaze', '')

    timing_path = timing_folder / f"{subject_num}_leap_voe_timing.csv"

    if not timing_path.exists():
        print(f"  Warning: Timing file not found for subject {subject_num}: {timing_path.name}")
        timing_df = None
    else:
        timing_df = pd.read_csv(timing_path)
        print(f"  Loaded timing data: {len(timing_df)} events")

    def get_trial_type_short_name(trial_type_str):
        """Short trial-type name, only for '_STILL' trials, e.g. "Test.EXP_DUCK.EXP_DUCK_STILL" -> "expected_duck"."""
        if not isinstance(trial_type_str, str) or not trial_type_str.endswith('_STILL'):
            return ""

        # Phase
        if trial_type_str.startswith('Fam.'):
            phase = 'fam'
        elif 'SUR_' in trial_type_str:
            phase = 'surprise'
        elif 'EXP_' in trial_type_str:
            phase = 'expected'
        else:
            return ""

        # Object
        if 'DUCK' in trial_type_str:
            obj = 'duck'
        elif 'SHOE' in trial_type_str:
            obj = 'shoe'
        else:
            return ""

        return f"{phase}_{obj}"

    with open(tsv_file, 'r') as f:
        lines = f.readlines()

    # Events are 2-column lines; find where gaze data ends and events start
    gaze_end_idx = None
    for i in range(6, len(lines)):  # after header
        parts = lines[i].strip().split('\t')
        if len(parts) == 2 and not parts[1].startswith('nan'):
            gaze_end_idx = i
            break

    # Gaze rows only (skip 5 metadata lines, stop at events)
    if gaze_end_idx:
        df = pd.read_csv(tsv_file, sep='\t', skiprows=5, nrows=gaze_end_idx - 6)
    else:
        df = pd.read_csv(tsv_file, sep='\t', skiprows=5)

    output_df = pd.DataFrame()

    # Already in ms
    output_df['device_time_stamp'] = df['TimeStamp']

    def normalize_coords(x_pix, y_pix, res_x, res_y):
        """PsychoPy centered pixels -> normalized (0-1), top-left origin."""
        try:
            x_pix = float(x_pix)
            y_pix = float(y_pix)
            x_norm = (x_pix + res_x / 2) / res_x
            y_norm = (-y_pix + res_y / 2) / res_y
            return f"({x_norm}, {y_norm})"
        except (ValueError, TypeError):
            return f"(nan, nan)"

    # Normalized gaze coords per eye, as string tuples
    output_df['left_gaze_point_on_display_area'] = df.apply(
        lambda row: normalize_coords(row['GazePointXLeft'], row['GazePointYLeft'],
                                      screen_res[0], screen_res[1]),
        axis=1
    )
    output_df['right_gaze_point_on_display_area'] = df.apply(
        lambda row: normalize_coords(row['GazePointXRight'], row['GazePointYRight'],
                                      screen_res[0], screen_res[1]),
        axis=1
    )

    output_df['left_gaze_point_validity'] = df['ValidityLeft']
    output_df['right_gaze_point_validity'] = df['ValidityRight']

    # Stimulus bounds: 1770x996 centered on 1920x1080 screen
    STIM_WIDTH = 1770
    STIM_HEIGHT = 996
    X_MIN = (screen_res[0] - STIM_WIDTH) / 2  # 75
    X_MAX = X_MIN + STIM_WIDTH  # 1845
    Y_MIN = (screen_res[1] - STIM_HEIGHT) / 2  # 42
    Y_MAX = Y_MIN + STIM_HEIGHT  # 1038

    def check_off_screen(left_gaze_x, left_gaze_y, right_gaze_x, right_gaze_y,
                          left_valid, right_valid):
        """1 if off-screen, 0 if on-screen. Uses avg of valid eye(s)."""
        valid_x = []
        valid_y = []

        if left_valid == 1:
            try:
                valid_x.append(float(left_gaze_x))
                valid_y.append(float(left_gaze_y))
            except (ValueError, TypeError):
                pass

        if right_valid == 1:
            try:
                valid_x.append(float(right_gaze_x))
                valid_y.append(float(right_gaze_y))
            except (ValueError, TypeError):
                pass

        # No valid points -> treat as off-screen
        if len(valid_x) == 0:
            return 1

        avg_x = sum(valid_x) / len(valid_x)
        avg_y = sum(valid_y) / len(valid_y)

        if avg_x < X_MIN or avg_x > X_MAX or avg_y < Y_MIN or avg_y > Y_MAX:
            return 1
        else:
            return 0

    # 1=off-screen, 0=on-screen
    output_df['off_screen'] = df.apply(
        lambda row: check_off_screen(
            row['GazePointXLeft'], row['GazePointYLeft'],
            row['GazePointXRight'], row['GazePointYRight'],
            row['ValidityLeft'], row['ValidityRight']
        ),
        axis=1
    )

    # Parse trial events, if present
    events = []
    if gaze_end_idx:
        for i in range(gaze_end_idx, len(lines)):
            line = lines[i].strip()
            if line and line != 'Session End':
                parts = line.split('\t')
                if len(parts) == 2:
                    try:
                        timestamp = float(parts[0])
                        event_label = parts[1]
                        events.append({'timestamp': timestamp, 'event': event_label})
                    except ValueError:
                        continue

    if events:
        # gaze_event_tag: most recent event at or before each timestamp
        output_df['gaze_event_tag'] = ''
        current_event = ''

        for idx, row in output_df.iterrows():
            timestamp = row['device_time_stamp']

            for event in events:
                if event['timestamp'] <= timestamp:
                    current_event = event['event']
                else:
                    break

            output_df.at[idx, 'gaze_event_tag'] = current_event

        # trial_type: from timing_df, matched via trial number in the event tag
        output_df['trial_type'] = ''

        if timing_df is not None:
            # tags look like "trial_2_Fam.FAM_SHOE.SHOE_FAM_STILL_startTrial"
            for idx, row in output_df.iterrows():
                event_tag = row['gaze_event_tag']

                if event_tag and event_tag.startswith('trial_'):
                    parts = event_tag.split('_')
                    try:
                        trial_num = int(parts[1])
                        trial_rows = timing_df[timing_df['trialNum'] == trial_num]

                        if not trial_rows.empty:
                            trial_type_full = trial_rows.iloc[0]['trialType']
                            short_name = get_trial_type_short_name(trial_type_full)
                            output_df.at[idx, 'trial_type'] = short_name
                    except (ValueError, IndexError):
                        pass

        # event_info: mark first/last row of each STILL trial
        output_df['event_info'] = ''
        marked_starts = set()
        marked_ends = set()

        for idx, row in output_df.iterrows():
            event_tag = row['gaze_event_tag']
            trial_type = row['trial_type']

            if trial_type and event_tag and event_tag.startswith('trial_'):
                parts = event_tag.split('_')
                try:
                    trial_num = int(parts[1])

                    if 'startTrial' in event_tag and trial_num not in marked_starts:
                        output_df.at[idx, 'event_info'] = 'start_event'
                        marked_starts.add(trial_num)
                    elif 'endTrial' in event_tag and trial_num not in marked_ends:
                        output_df.at[idx, 'event_info'] = 'end_event'
                        marked_ends.add(trial_num)

                except (ValueError, IndexError):
                    pass
    else:
        output_df['gaze_event_tag'] = ''
        output_df['trial_type'] = ''
        output_df['event_info'] = ''

    output_filename = f"{subject_num}_leap_voe_gaze.csv"
    output_path = output_folder / output_filename
    output_df.to_csv(output_path, index=False)

    print(f"  Saved gaze data to: {output_filename}")
    print(f"  Gaze rows: {len(output_df)}")

    if 'trial_type' in output_df.columns:
        trial_types = output_df[output_df['trial_type'] != '']['trial_type'].unique()
        if len(trial_types) > 0:
            print(f"  Trial types found: {', '.join(sorted(trial_types))}")

    return output_path


# =============================================================================
# 3. Process All Files
# =============================================================================

if __name__ == "__main__":
    converted_files = []

    for tsv_file in tsv_files:
        try:
            output_path = convert_tsv_to_csv(tsv_file, output_folder, timing_folder)
            converted_files.append(output_path)
        except Exception as e:
            print(f"  Error processing {tsv_file.name}: {e}")

    print(f"\n{'='*60}")
    print(f"Converted {len(converted_files)} / {len(tsv_files)} files")
    print(f"{'='*60}")
