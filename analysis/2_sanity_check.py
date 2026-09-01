"""
Data-quality check on the LEAP-VOE eye-tracking data for PILL.

Reports, per trial: how much valid gaze the tracker recorded, how much of that became
I2MC fixations, and (for STILL trials) how much of online coded looking the eye tracker captured.
"""

from pathlib import Path
import pandas as pd
import numpy as np

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

raw_dir = project_root / "data" / "leap_voe_data" / "raw_gaze" / "csv"
fix_dir = project_root / "data" / "leap_voe_data" / "fixations"
timing_dir = project_root / "data" / "leap_voe_data" / "raw_events" / "timing"
verbose_dir = project_root / "data" / "leap_voe_data" / "raw_events" / "verbose"

SAMPLE_S = 0.004  # 250 Hz, a sample every 4 ms

# sort subject IDs 
def subkey(s):
    """Sort subject ids 101, 102, ... numerically rather than as strings."""
    return (0, int(s)) if s.isdigit() else (1, 0, s)

# turn tobii gaze strings into floats, so (x,y) -> x, y
def parse_xy(series):
    """Tobii writes gaze as the string '(x, y)', normalized to the display, nan if missing."""
    p = series.astype(str).str.strip("()").str.split(",", n=1, expand=True)
    return (pd.to_numeric(p[0], errors="coerce").to_numpy(),
            pd.to_numeric(p[1], errors="coerce").to_numpy())

# now load the raw gaze data and trial windows
def load_gaze(path):
    """Raw samples with per-sample validity and an on-screen flag."""
    g = pd.read_csv(path, usecols=["device_time_stamp", "left_gaze_point_on_display_area", # key gaze columns
                                   "right_gaze_point_on_display_area",
                                   "left_gaze_point_validity", "right_gaze_point_validity"]) 
    lx, ly = parse_xy(g["left_gaze_point_on_display_area"])
    rx, ry = parse_xy(g["right_gaze_point_on_display_area"])
    lv = (g["left_gaze_point_validity"] == 1).to_numpy() # lv = left eye valid
    rv = (g["right_gaze_point_validity"] == 1).to_numpy() # rv = right eye valid
    valid = lv | rv # counts as valid if at least one eye is valid
    gx = np.where(lv, lx, np.where(rv, rx, np.nan)) # if left eye valid, use left; else if right eye valid, use right; else nan
    gy = np.where(lv, ly, np.where(rv, ry, np.nan))
    onscreen = valid & (gx >= 0) & (gx <= 1) & (gy >= 0) & (gy <= 1) # on-screen if valid and gaze within [0,1] normalized display coordinates
    return g["device_time_stamp"].to_numpy(), valid, onscreen

# load trial windows from the timing file
def trial_windows(timing_path):
    """
    MOV and STILL windows in ms, plus each trial's startTrial (which the verbose file's
    startTime is relative to).

    Each trial is either a MOV or a STILL, encoded in the trialType column, which ends in
    "_STILL" for freeze trials. The two phases are bounded by DIFFERENT events:
        STILL = startTrial -> endTrial
        MOV   = startMoviePlayback -> endMoviePlayback, NOT startTrial, because the gap
                between trial start and playback start reaches 15s on some trials
    (startMoviePlayback is present on all 310 MOV trials, so the startTrial fallback below
    never actually fires; it is kept only for parity with the labeller.)

    Note the gaze_event_tag column in the raw file looks like it could define trials, but
    every event in a trial carries the same "trial_N_" prefix (attn-getter, trial start,
    movie playback), so keying on it lumps them together and inflates durations. Instead,
    I'm using the timing file's start/end events.

    Returns a DataFrame with columns trial, phase, t0, t1, plus a dict mapping trial -> startTrial.
    """
    t = pd.read_csv(timing_path)
    rows, starts = [], {}
    for tn, g in t.groupby("trialNum"): # group by trial number
        e = dict(zip(g["event"], g["time"])) # this dict maps event names to their times for this trial, e.g. {"startTrial": 123.456, "endTrial": 234.567, "startMoviePlayback": 130.000, "endMoviePlayback": 220.000}
        if "startTrial" in e:
            starts[tn] = e["startTrial"]
        is_still = str(g["trialType"].iloc[0]).endswith("_STILL") # check if trial is a STILL trial
        if is_still:
            if "startTrial" in e and "endTrial" in e:
                rows.append((tn, "still", e["startTrial"] * 1000, e["endTrial"] * 1000)) # append trial number, phase (e.g. "still"), start time in ms, end time in ms
        elif "startMoviePlayback" in e and "endMoviePlayback" in e: # if it's a MOV trial, use the movie playback start/end times
            rows.append((tn, "movie", e["startMoviePlayback"] * 1000, e["endMoviePlayback"] * 1000))
        elif "startTrial" in e and "endTrial" in e:
            rows.append((tn, "movie", e["startTrial"] * 1000, e["endTrial"] * 1000))
    return pd.DataFrame(rows, columns=["trial", "phase", "t0", "t1"]), starts

# now we can compute the fraction of raw samples that were valid, per trial
def raw_by_trial(ts, valid, win):
    """Per window: fraction of raw samples with at least one valid eye."""
    idx = pd.IntervalIndex.from_arrays(win["t0"], win["t1"]) # create an interval index from the trial windows
    loc = idx.get_indexer(ts) # which trial window each timestamp from the raw gaze falls into
    keep = loc >= 0 # drop samples that don't fall into any trial window
    if not keep.any():
        return pd.DataFrame()
    d = pd.DataFrame({"trial": win["trial"].to_numpy()[loc[keep]], "valid": valid[keep]}) # create a df with trial numbers and validity for the samples that fall into trial windows
    g = d.groupby("trial") # group by trial number
    return pd.DataFrame({"n_samp": g.size(), "validity": g["valid"].mean()}) # returns a df with trial number, number of samples, and fraction of valid samples

def fix_by_trial(path):
    """Per trial: fixation count, total fixation time, mean interpolated fraction."""
    d = pd.read_csv(path, usecols=["dur", "fracinterped", "trial_num", "phase"])
    d = d[d["phase"].isin(["movie", "still"])].dropna(subset=["trial_num"])
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("trial_num")
    return pd.DataFrame({"n_fix": g.size(), "fix_s": g["dur"].sum() / 1000,
                         "interp": g["fracinterped"].mean()})


def fix_intervals(path):
    """Fixation start/end times in ms, on the same clock as the raw gaze."""
    d = pd.read_csv(path, usecols=["startT", "endT"]).dropna()
    return d["startT"].to_numpy(), d["endT"].to_numpy()


def overlap_s(w0, w1, f0, f1):
    """Total seconds of overlap between a set of windows and a set of fixations."""
    if len(f0) == 0 or len(w0) == 0:
        return 0.0
    lo = np.maximum(w0[:, None], f0[None, :])
    hi = np.minimum(w1[:, None], f1[None, :])
    return np.clip(hi - lo, 0, None).sum() / 1000


def coded_capture(verbose_path, starts, ts, valid, onscreen, fix0, fix1):
    """
    How much did the online-coding looking did the eye tracker capture?

    The verbose file logs the coder's key state as on/off bouts (column gazeOnOff), with startTime relative to
    that trial's startTrial, so it sits on the same clock as the raw gaze.

    Reported for STILL trials only, since that's when coding window starts. 
    """
    v = pd.read_csv(verbose_path, usecols=["gazeOnOff", "trial", "trialType", "startTime", "endTime"])
    v = v[v["trialType"].astype(str).str.endswith("_STILL")]
    out = []
    for (tn, onoff), g in v.groupby(["trial", "gazeOnOff"]):
        if tn not in starts:
            continue
        t0 = (starts[tn] + g["startTime"].to_numpy()) * 1000
        t1 = (starts[tn] + g["endTime"].to_numpy()) * 1000
        i0 = np.searchsorted(ts, t0, "left")
        i1 = np.searchsorted(ts, t1, "left")
        out.append(dict(trial=tn, looking=int(onoff),
                        coded_s=(t1 - t0).sum() / 1000,
                        valid_s=sum(valid[a:b].sum() for a, b in zip(i0, i1)) * SAMPLE_S,
                        onscr_s=sum(onscreen[a:b].sum() for a, b in zip(i0, i1)) * SAMPLE_S,
                        fix_s=overlap_s(t0, t1, fix0, fix1)))
    return pd.DataFrame(out)

# set up main function to run the sanity check and print results
def main():
    raw_files = {p.stem.replace("_leap_voe_gaze", ""): p for p in raw_dir.glob("*_leap_voe_gaze.csv")}
    lab_files = {p.stem.replace("_leap_voe_gaze_fix_labeled", ""): p for p in fix_dir.glob("*/*_fix_labeled.csv")}
    tim_files = {p.stem.replace("_leap_voe_timing", ""): p for p in timing_dir.glob("*_leap_voe_timing.csv")}
    vrb_files = {p.stem.replace("_leap_voe_verbose", ""): p for p in verbose_dir.glob("*_leap_voe_verbose.csv")}

    subjects = sorted(set(raw_files) & set(lab_files) & set(tim_files), key=subkey)
    print(f"raw {len(raw_files)} | fixations {len(lab_files)} | timing {len(tim_files)} | "
          f"verbose {len(vrb_files)} | analysed {len(subjects)}")
    dropped = sorted(set(raw_files) - set(subjects), key=subkey)
    if dropped:
        print(f"excluded (missing fixations and/or timing): {', '.join(dropped)}")

    recs, caps = [], []
    for sub in subjects:
        win, starts = trial_windows(tim_files[sub])
        if win.empty:
            continue
        ts, valid, onscreen = load_gaze(raw_files[sub])
        r = raw_by_trial(ts, valid, win)
        if r.empty:
            continue
        m = win.set_index("trial").join(r).join(fix_by_trial(lab_files[sub]))
        for c in ("n_fix", "fix_s", "interp"):
            if c not in m.columns:
                m[c] = np.nan
        m["n_fix"] = m["n_fix"].fillna(0)
        m["fix_s"] = m["fix_s"].fillna(0)
        m["trial_s"] = (m["t1"] - m["t0"]) / 1000
        m["coverage"] = (m["fix_s"] / m["trial_s"]).clip(upper=1)
        m["retained"] = (m["coverage"] / m["validity"]).replace([np.inf, -np.inf], np.nan).clip(upper=1)
        m["subject"] = sub
        recs.append(m.reset_index())

        if sub in vrb_files:
            f0, f1 = fix_intervals(lab_files[sub])
            c = coded_capture(vrb_files[sub], starts, ts, valid, onscreen, f0, f1)
            if not c.empty:
                c["subject"] = sub
                caps.append(c)

    df = pd.concat(recs, ignore_index=True)
    df["trial"] = df["trial"].astype(int)
    order = sorted(df["subject"].unique(), key=subkey)
    val = df.pivot(index="subject", columns="trial", values="validity").reindex(order)
    cov = df.pivot(index="subject", columns="trial", values="coverage").reindex(order)
    ret = df.pivot(index="subject", columns="trial", values="retained").reindex(order)
    mov = [c for c in val.columns if c % 2 == 1]
    still = [c for c in val.columns if c % 2 == 0]

    # ---- 1. validity per subject per trial ----
    trials = sorted(val.columns)
    hdr = "  sub  " + "".join(f"{t:>6}" for t in trials) + "   |   MOV  STILL    ALL"
    print("\nVALIDITY per subject (fraction of raw samples with >=1 valid eye)")
    print("  odd trials = MOV, even = STILL")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for sub in val.index:
        row = val.loc[sub]
        cells = "".join("     ." if pd.isna(row[t]) else f"{row[t]:>6.2f}" for t in trials)
        print(f"  {sub:<5}{cells}   |{row[mov].mean():>6.2f}{row[still].mean():>7.2f}{row.mean():>7.2f}")

    # ---- 2. group validity ----
    print("\nGROUP VALIDITY (across subjects)")
    grp = pd.DataFrame({
        "mean": [val[mov].stack().mean(), val[still].stack().mean(), val.stack().mean()],
        "sd": [val[mov].stack().std(), val[still].stack().std(), val.stack().std()],
        "min": [val[mov].stack().min(), val[still].stack().min(), val.stack().min()],
        "max": [val[mov].stack().max(), val[still].stack().max(), val.stack().max()],
        "n_trials": [val[mov].notna().sum().sum(), val[still].notna().sum().sum(), val.notna().sum().sum()],
    }, index=["MOV", "STILL", "overall"])
    print(grp.round(3).to_string())

    # ---- 3. group fixation data ----
    print("\nGROUP FIXATION DATA (across subjects)")
    mv, st = df[df.trial % 2 == 1], df[df.trial % 2 == 0]
    print(pd.DataFrame({
        "coverage": [cov[mov].stack().mean(), cov[still].stack().mean(), cov.stack().mean()],
        "retained": [ret[mov].stack().mean(), ret[still].stack().mean(), ret.stack().mean()],
        "n_fix": [mv.n_fix.mean(), st.n_fix.mean(), df.n_fix.mean()],
        "fix_s": [mv.fix_s.mean(), st.fix_s.mean(), df.fix_s.mean()],
        "interp": [mv.interp.mean(), st.interp.mean(), df.interp.mean()],
    }, index=["MOV", "STILL", "overall"]).round(3).to_string())
    print("\n  coverage = share of trial time inside a fixation")
    print("  retained = coverage / validity, i.e. share of available signal that became fixations")
    print("  interp   = mean fraction of each fixation that I2MC filled in")

    # ---- 4. capture against the coder, STILL trials ----
    if caps:
        cap = pd.concat(caps, ignore_index=True)
        print("\nCODER-VERIFIED CAPTURE, STILL trials only")
        g = cap.groupby("looking").agg(coded_s=("coded_s", "sum"), valid_s=("valid_s", "sum"),
                                       onscr_s=("onscr_s", "sum"), fix_s=("fix_s", "sum"))
        # ordered least to most restrictive: eye detected -> became a fixation -> landed on screen
        g["validity"] = g.valid_s / g.coded_s
        g["fix_frac"] = g.fix_s / g.coded_s
        g["onscreen"] = g.onscr_s / g.coded_s
        g.index = ["coder: NOT looking", "coder: looking"]
        print(g.round(3).to_string())

        # Same ratio as the "validity" column above (valid_s / coded_s), but computed within each
        # subject instead of pooled across all of them. The pooled figure is weighted by how much
        # looking each subject contributed, so it will not equal the mean or median of these.
        on = cap[cap.looking == 1]
        per = on.groupby("subject").apply(
            lambda x: pd.Series({"coded_s": x.coded_s.sum(),
                                 "capture": x.valid_s.sum() / x.coded_s.sum() if x.coded_s.sum() else np.nan,
                                 "cap_onscreen": x.onscr_s.sum() / x.coded_s.sum() if x.coded_s.sum() else np.nan}),
            include_groups=False).sort_values("capture")
        pooled = g.loc["coder: looking", "validity"]
        print(f"\n  per-subject capture during coder-confirmed looking (n={len(per)}):")
        print(f"    capture = valid_s / coded_s within each subject, i.e. the 'validity' column")
        print(f"    above ({pooled:.3f}) recomputed per subject rather than pooled across all.")
        bins = [(0.00, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.01)]
        for lo, hi in bins:
            # top bin is closed so a subject at exactly 1.00 is not dropped
            sel = per[(per.capture >= lo) & (per.capture < hi)]
            label = f"{lo:.0%}-{min(hi, 1.0):.0%}"
            subs = ", ".join(sel.index) if len(sel) else "-"
            print(f"    {label:>8}  {len(sel):>2} subj ({len(sel)/len(per):>5.1%})  {subs}")


if __name__ == "__main__":
    main()
