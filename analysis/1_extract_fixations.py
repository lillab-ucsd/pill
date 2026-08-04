"""
Runs I2MC fixation extraction on PILL VOE gaze CSVs (raw_gaze/csv).
Follows: https://devstart.org/CONTENT/EyeTracking/I2MC_tutorial.html

Output: for each subject, data/leap_voe_data/fixations/[subject]/[subject]_leap_voe_gaze_fix.csv
(plus a fixation plot .png, if do_plot_data is True).
"""

from pathlib import Path
import I2MC
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# =============================================================================
# 1. Setup
# =============================================================================

# Repo root is one level up from this script
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# Gaze CSVs produced by 0_convert_tsv.py
gaze_csv_folder = project_root / 'data' / 'leap_voe_data' / 'raw_gaze' / 'csv'
data_files = sorted(gaze_csv_folder.glob('*_leap_voe_gaze.csv'))

print(f"Found {len(data_files)} VOE gaze files to process")

# Output folder
base_output_folder = project_root / 'data' / 'leap_voe_data' / 'fixations'
base_output_folder.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 2. Functions
# =============================================================================

def parse_gaze_point(gaze_str):
    """Parse gaze point string tuple to floats."""
    if pd.isna(gaze_str) or gaze_str == "(nan, nan)":
        return np.nan, np.nan
    try:
        coords = gaze_str.strip('()').split(',')
        x = float(coords[0].strip())
        y = float(coords[1].strip())
        return x, y
    except:
        return np.nan, np.nan

def tobii_fusion(fname, res=[1920, 1080]):
    # 1. Load the raw data from CSV
    raw_df = pd.read_csv(fname, delimiter=',')

    # 2. Create the output DataFrame expected by I2MC
    df = pd.DataFrame()
    # VOE timestamps are already in ms
    df['time'] = raw_df['device_time_stamp']

    # 3. Parse coordinates (top-left origin, Y increases downward)
    left_gaze = raw_df['left_gaze_point_on_display_area'].apply(parse_gaze_point)
    df['L_X'] = [x[0] * res[0] if not pd.isna(x[0]) else np.nan
                 for x in left_gaze]
    df['L_Y'] = [x[1] * res[1] if not pd.isna(x[1]) else np.nan
                 for x in left_gaze]

    right_gaze = raw_df['right_gaze_point_on_display_area'].apply(parse_gaze_point)
    df['R_X'] = [x[0] * res[0] if not pd.isna(x[0]) else np.nan
                 for x in right_gaze]
    df['R_Y'] = [x[1] * res[1] if not pd.isna(x[1]) else np.nan
                 for x in right_gaze]

    # 4. Clean artifacts (out of bounds / invalid samples)
    # --- Left Eye ---
    lMiss1 = (df['L_X'] < -res[0]) | (df['L_X'] > 2 * res[0])
    lMiss2 = (df['L_Y'] < -res[1]) | (df['L_Y'] > 2 * res[1])
    lMiss = lMiss1 | lMiss2 | (raw_df['left_gaze_point_validity'] == 0)

    df.loc[lMiss, 'L_X'] = np.nan
    df.loc[lMiss, 'L_Y'] = np.nan

    # --- Right Eye ---
    rMiss1 = (df['R_X'] < -res[0]) | (df['R_X'] > 2 * res[0])
    rMiss2 = (df['R_Y'] < -res[1]) | (df['R_Y'] > 2 * res[1])
    rMiss = rMiss1 | rMiss2 | (raw_df['right_gaze_point_validity'] == 0)

    df.loc[rMiss, 'R_X'] = np.nan
    df.loc[rMiss, 'R_Y'] = np.nan

    print(f"  Left eye: {lMiss.sum()}/{len(lMiss)} samples filtered ({100*lMiss.sum()/len(lMiss):.1f}%)")
    print(f"  Right eye: {rMiss.sum()}/{len(rMiss)} samples filtered ({100*rMiss.sum()/len(rMiss):.1f}%)")

    return df

# =============================================================================
# 3. I2MC Settings (NECESSARY VARIABLES)
# =============================================================================

opt = {}
# General variables for eye-tracking data
opt['xres']         = 1920.0                # Max horizontal resolution in pixels
opt['yres']         = 1080.0                # Max vertical resolution in pixels
opt['missingx']     = np.nan                # Missing value code
opt['missingy']     = np.nan                # Missing value code
opt['freq']         = 250.0          # Sampling frequency (Hz) - CHECK YOUR DEVICE!

# Visual Angle Calculation
opt['scrSz']        = [50.9174, 28.6411]    # Screen size in cm, roughly 1920 x 1080 px
opt['disttoscreen'] = 65.0                  # Distance to screen in cm

# Plotting
do_plot_data = True # Save visualization plots?


# =============================================================================
# 4. Optional Variables (Fine-Tuning)
# =============================================================================

# --- Interpolation Settings ---
opt['windowtimeInterp'] = 0.1 # Max duration (s) of missing data to interpolate
opt['edgeSampInterp'] = 2 # Samples required at edges for interpolation
opt['maxdisp'] = opt['xres'] * 0.2 * np.sqrt(2) # Max displacement allowed

# --- K-Means Clustering Settings ---
opt['windowtime'] = 0.2 # Time window (s) for clustering (approx 1 saccade duration)
opt['steptime'] = 0.02 # Window shift (s) per iteration
opt['maxerrors'] = 100 # Max errors allowed before skipping file
opt['downsamples'] = [2, 5, 10]
opt['downsampFilter'] = False # Chebychev filter (False avoids ringing artifacts)

# --- Fixation Determination Settings ---
opt['cutoffstd'] = 2.0 # Std devs above mean weight for fixation cutoff
opt['onoffsetThresh'] = 3.0 # MADs for refining fixation start/end points
opt['maxMergeDist'] = 30.0 # Max pixels between fixations to merge them
opt['maxMergeTime'] = 40.0 # Max ms between fixations to merge them
opt['minFixDur'] = 40.0 # Min duration (ms) for a valid fixation


# =============================================================================
# 5. Run I2MC Loop & Save
# =============================================================================

for file_idx, file in enumerate(data_files):
    print(f'Processing file {file_idx + 1} of {len(data_files)}: {file.name}')

    name = file.stem

    # Create subject folder
    subj_folder = base_output_folder / name
    subj_folder.mkdir(parents=True, exist_ok=True)

    # Check if file already processed (with _fix suffix)
    save_file = subj_folder / f"{name}_fix.csv"
    if save_file.exists():
        print(f'  Output file already exists, skipping...')
        continue

    # Import data using our function
    data = tobii_fusion(file, res=[opt['xres'], opt['yres']])

    # Run I2MC
    fix, _, _ = I2MC.I2MC(data, opt)

    # Save Plot
    if do_plot_data and fix:
        save_plot = subj_folder / f"{name}_fix.png"
        f = I2MC.plot.data_and_fixations(
            data, fix,
            fix_as_line=True,
            res=[opt['xres'], opt['yres']]
        )
        f.savefig(save_plot)
        plt.close(f)

    # Save Data
    fix['participant'] = name # Add participant ID to fixation data
    fix_df = pd.DataFrame(fix)
    fix_df.to_csv(save_file, index=False)
    print(f'  Saved: {save_file.name}')
