"""
combines raw gaze and labeled i2mc fixations for all leap_voe infants into two files.
output: data/leap_voe_data/combined_data/raw_gaze_combined.csv and fixations_combined.csv.
"""

from pathlib import Path
import numpy as np
import pandas as pd


# =============================================================================
# 1. setup
# =============================================================================

root = Path(__file__).resolve().parent.parent
data_dir = root / 'data' / 'leap_voe_data'
tsv_dir = data_dir / 'raw_gaze' / 'tsv'
timing_dir = data_dir / 'raw_events' / 'timing'
summary_dir = data_dir / 'raw_events' / 'summary'
fix_dir = data_dir / 'fixations'
out_dir = data_dir / 'combined_data'
out_dir.mkdir(parents=True, exist_ok=True)

excluded = {'102', '107_1', '171', '901', '902', '903', '904'}
excluded |= {'104'}  # saw original _Trimmed stimuli

# screen and stimulus rect in top-left px
screen_w, screen_h = 1920, 1080
stim_x0, stim_y0, stim_w, stim_h = 75, 42, 1770, 996

# pyhab still names -> image files (leap_voe voe_experimentSettings.csv)
still_files = {
    'FamDuckFREEZE': 'duck_fam.jpg',
    'FamShoeFREEZE': 'shoe_fam.jpg',
    'ExpDuckFREEZE': 'duck_expected.jpg',
    'TestDuckFREEZE': 'duck_surprise.jpg',
    'ExpShoeFREEZE': 'shoe_expected.jpg',
    'TestShoeFREEZE': 'shoe_surprise.jpg',
    'famDuckFREEZE_bright': 'fam_duck_still_bright.jpg',
    'famShoeFREEZE_bright': 'fam_shoe_still_bright.jpg',
    'expDuckFREEZE_bright': 'duck_expected_still_bright.jpg',
    'surDuckFREEZE_bright': 'duck_unexpected_still_bright.jpg',
    'expShoeFREEZE_bright': 'shoe_expected_still_bright.jpg',
    'surShoeFREEZE_bright': 'shoe_unexpected_still_bright.jpg',
}

label_cols = ['sub_id', 'trial_num', 'phase', 'condition', 'object', 'rep', 'segment', 'stim_file']


# =============================================================================
# 2. trial windows
# =============================================================================

def parse_trial_type(tt):
    # e.g. "Test.SUR_SHOE.SUR_SHOE_STILL"
    phase = 'fam' if tt.startswith('Fam.') else 'test'
    if phase == 'fam':
        condition = 'fam'
    else:
        condition = 'unexpected' if 'SUR_' in tt else 'expected'
    obj = 'duck' if 'DUCK' in tt else 'shoe'
    segment = 'still' if tt.endswith('_STILL') else 'movie'
    return phase, condition, obj, segment


def build_windows(sub):
    """one row per trial: labels plus segment start/end in ms (movie = playback, still = whole trial)."""
    timing = pd.read_csv(timing_dir / f'{sub}_leap_voe_timing.csv')
    summary = pd.read_csv(summary_dir / f'{sub}_leap_voe_summary.csv')
    stim_by_trial = dict(zip(summary['trial'], summary['stimName']))

    rows, rep_count = [], {}
    for trial_num, g in timing.groupby('trialNum'):
        tt = g.loc[g['trialType'].str.contains(r'\.'), 'trialType'].iloc[0]
        phase, condition, obj, segment = parse_trial_type(tt)
        ev = g.groupby('event')['time'].last() * 1000  # last copy, as in 2_label_fixations

        # still inherits the rep of its movie
        if segment == 'movie':
            rep_count[(condition, obj)] = rep_count.get((condition, obj), 0) + 1
        rep = rep_count.get((condition, obj), 1)

        if segment == 'movie' and 'startMoviePlayback' in ev:
            seg_start, seg_end = ev['startMoviePlayback'], ev['endMoviePlayback']
            video_start = seg_start
        else:
            seg_start, seg_end = ev['startTrial'], ev['endTrial']
            video_start = np.nan

        stim = stim_by_trial.get(trial_num, '')
        rows.append(dict(sub_id=sub, trial_num=int(trial_num), phase=phase, condition=condition,
                         object=obj, rep=rep, segment=segment,
                         stim_file=still_files.get(stim, stim),
                         trial_start=ev['startTrial'], seg_start=seg_start, seg_end=seg_end,
                         video_start=video_start))
    return pd.DataFrame(rows)


# =============================================================================
# 3. raw gaze
# =============================================================================

def read_gaze(sub):
    df = pd.read_csv(tsv_dir / f'{sub}_leap_voe_gaze.tsv', sep='\t', skiprows=5, low_memory=False)
    df = df[df['ValidityLeft'].notna()].copy()  # drops event and session lines
    df['TimeStamp'] = df['TimeStamp'].astype(float)

    out = pd.DataFrame({'t_session_ms': df['TimeStamp'].values})
    for eye, tag in [('left', 'Left'), ('right', 'Right')]:
        valid = df[f'Validity{tag}'].values.astype(int)
        # psychopy centered px (y up) -> top-left px (y down)
        x = df[f'GazePointX{tag}'].astype(float).values + screen_w / 2
        y = -df[f'GazePointY{tag}'].astype(float).values + screen_h / 2
        x[valid == 0] = np.nan
        y[valid == 0] = np.nan
        out[f'x_{eye}'], out[f'y_{eye}'], out[f'valid_{eye}'] = x, y, valid

    # mean of valid eyes
    out['x'] = out[['x_left', 'x_right']].mean(axis=1)
    out['y'] = out[['y_left', 'y_right']].mean(axis=1)

    # same rule as 0_convert_tsv: no valid eye or outside stimulus rect
    inside = (out['x'].between(stim_x0, stim_x0 + stim_w) &
              out['y'].between(stim_y0, stim_y0 + stim_h))
    out['off_screen'] = (~inside).astype(int)
    return out


def label_gaze(gaze, win):
    """keep samples inside movie or still segments and attach trial labels."""
    parts = []
    for w in win.itertuples():
        m = (gaze['t_session_ms'] >= w.seg_start) & (gaze['t_session_ms'] <= w.seg_end)
        seg = gaze[m].copy()
        for c in label_cols:
            seg[c] = getattr(w, c)
        seg['t_trial_ms'] = seg['t_session_ms'] - w.trial_start
        seg['t_video_ms'] = seg['t_session_ms'] - w.video_start
        seg['in_coding_window'] = int(w.segment == 'still')
        parts.append(seg)
    order = label_cols + ['t_session_ms', 't_trial_ms', 't_video_ms',
                          'x_left', 'y_left', 'valid_left', 'x_right', 'y_right', 'valid_right',
                          'x', 'y', 'off_screen', 'in_coding_window']
    return pd.concat(parts)[order]


# =============================================================================
# 4. fixations
# =============================================================================

def label_fixations(sub, win):
    fix = pd.read_csv(fix_dir / f'{sub}_leap_voe_gaze' / f'{sub}_leap_voe_gaze_fix_labeled.csv')
    still = win[win['segment'] == 'still']
    edges = np.concatenate([win['seg_start'].values, win['seg_end'].values])

    s, e = fix['startT'].values, fix['endT'].values
    # overlap with each still, in ms
    ov = np.clip(np.minimum(e[:, None], still['seg_end'].values) -
                 np.maximum(s[:, None], still['seg_start'].values), 0, None)
    fix['ms_in_still'] = ov.sum(axis=1)
    fix['crosses_boundary'] = ((edges > s[:, None]) & (edges < e[:, None])).any(axis=1).astype(int)

    # keep movie/still fixations plus any that overlap a still
    keep = fix['phase'].isin(['movie', 'still']) | (fix['ms_in_still'] > 0)
    fix = fix[keep].copy()

    # trial labels from 2_label_fixations; unlabeled ones take the still they overlap
    ov = ov[keep.values]
    tn = pd.to_numeric(fix['trial_num'], errors='coerce').values.astype(float)
    no_trial = np.isnan(tn)
    tn[no_trial] = still['trial_num'].values[ov[no_trial].argmax(axis=1)]
    fix['trial_num'] = tn.astype(int)

    lab = win.set_index('trial_num')
    fix = fix.join(lab[['phase', 'condition', 'object', 'rep', 'stim_file', 'trial_start', 'video_start']],
                   on='trial_num', rsuffix='_w')
    fix = fix.rename(columns={'phase': 'segment', 'phase_w': 'phase'})
    fix['sub_id'] = sub

    out = pd.DataFrame({
        **{c: fix[c] for c in label_cols},
        'start_ms': fix['startT'], 'end_ms': fix['endT'], 'dur_ms': fix['dur'],
        'start_trial_ms': fix['startT'] - fix['trial_start'],
        'start_video_ms': np.where(fix['segment'] == 'movie', fix['startT'] - fix['video_start'], np.nan),
        'x': fix['xpos'], 'y': fix['ypos'],
        'crosses_boundary': fix['crosses_boundary'], 'ms_in_still': fix['ms_in_still'],
        'flankdataloss': fix['flankdataloss'], 'fracinterped': fix['fracinterped'],
        'RMSxy': fix['RMSxy'], 'BCEA': fix['BCEA'],
        'fixRangeX': fix['fixRangeX'], 'fixRangeY': fix['fixRangeY'],
    })
    return out


# =============================================================================
# 5. run
# =============================================================================

if __name__ == '__main__':
    subs = sorted(p.name.replace('_leap_voe_gaze.tsv', '') for p in tsv_dir.glob('*_leap_voe_gaze.tsv'))
    subs = [s for s in subs if s not in excluded]
    print(f'{len(subs)} infants')

    gaze_all, fix_all, checks = [], [], []
    for sub in subs:
        win = build_windows(sub)
        g = label_gaze(read_gaze(sub), win)
        f = label_fixations(sub, win)
        gaze_all.append(g)
        fix_all.append(f)
        checks.append(dict(sub_id=sub, n_trials=len(win),
                           n_test_still=int(((win['phase'] == 'test') & (win['segment'] == 'still')).sum()),
                           n_samples=len(g), pct_valid=round(100 * g['x'].notna().mean(), 1),
                           n_fix=len(f)))

    gaze_all = pd.concat(gaze_all, ignore_index=True)
    fix_all = pd.concat(fix_all, ignore_index=True)

    # keep infants with fixations in >=2 test stills, incl. >=1 expected and >=1 unexpected
    ts = fix_all[(fix_all['phase'] == 'test') & (fix_all['segment'] == 'still')]
    n_trials = ts[['sub_id', 'condition', 'rep']].drop_duplicates().groupby('sub_id').size()
    n_cond = ts.groupby('sub_id')['condition'].nunique()
    keep_subs = set(n_trials[(n_trials >= 2) & (n_cond == 2)].index)
    dropped = sorted(set(subs) - keep_subs)
    print(f'excluded for too few test-still fixations ({len(dropped)}): {dropped}')
    gaze_all = gaze_all[gaze_all['sub_id'].isin(keep_subs)]
    fix_all = fix_all[fix_all['sub_id'].isin(keep_subs)]
    gaze_all.to_csv(out_dir / 'raw_gaze_combined.csv', index=False, float_format='%.1f')
    fix_all.to_csv(out_dir / 'fixations_combined.csv', index=False)

    checks = pd.DataFrame(checks)
    print(checks.to_string(index=False))
    print(f'\nkept {len(keep_subs)} infants, raw gaze rows: {len(gaze_all)}, fixations: {len(fix_all)}')
    odd = checks[(checks['n_trials'] != 12) | (checks['n_fix'] == 0)]
    if len(odd):
        print('check these infants:\n' + odd.to_string(index=False))
