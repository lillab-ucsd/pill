"""
Data-quality check on the LEAP-VOE eye-tracking data for PILL.

Reports, per trial: how much of the trial the tracker found each eye, how many trials are
mostly lost, and (during the coding window) how much of the online coder's looking the tracker
captured. Prints summary tables, saves a per-trial CSV and three slide-sized figures to
data/leap_voe_data/data_qc/.

A trial is one MOV + the STILL that follows it (trialNum 1+2, 3+4, ... 11+12), so each subject
has 6 trials: Fam 1, Fam 2, Test 1-4. MOV is the video up to its last frame; STILL is that last
frame frozen. STILL only marks when online coding starts, the scene itself doesn't change.

Nothing is excluded here; this only reports, so exclusion decisions can be made downstream.

TODO: add calibration accuracy (validation error in degrees) per subject once PILL sessions
log it ({sub_id}_validation_summary.csv). LEAP-VOE did not record it.
"""

from pathlib import Path
import pandas as pd
import numpy as np

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

raw_dir = project_root / "data" / "leap_voe_data" / "raw_gaze" / "csv"
timing_dir = project_root / "data" / "leap_voe_data" / "raw_events" / "timing"
verbose_dir = project_root / "data" / "leap_voe_data" / "raw_events" / "verbose"
out_dir = project_root / "data" / "leap_voe_data" / "data_qc"

SAMPLE_S = 0.004  # 250 Hz, a sample every 4 ms

# A trial is flagged (not excluded) if both eyes are invalid on more than this share of its samples.
# TODO: placeholder, choose the real threshold
MAX_INVALID_FRAC = 0.8

# Minimum number of test trials that pass MAX_INVALID_FRAC for a subject to count as usable
MIN_TEST_TRIALS = 2

TRIAL_LABELS = {1: "Fam 1", 2: "Fam 2", 3: "Test 1", 4: "Test 2", 5: "Test 3", 6: "Test 4"}

# sort subject IDs
def subkey(s):
    """Sort subject ids 101, 102, ... numerically rather than as strings."""
    return (0, int(s)) if s.isdigit() else (1, 0, s)

# short trial-type name, e.g. "Test.SUR_DUCK.SUR_DUCK_MOV" -> "surprise_duck"
def short_name(trial_type):
    t = str(trial_type)
    phase = "fam" if t.startswith("Fam.") else "surprise" if "SUR_" in t else "expected" if "EXP_" in t else ""
    obj = "duck" if "DUCK" in t else "shoe" if "SHOE" in t else ""
    return f"{phase}_{obj}" if phase and obj else ""

# timing-file trialNum (1-12) -> trial (1-6): MOV 1 and STILL 2 are trial 1, and so on
def pair_of(trial_num):
    return (int(trial_num) + 1) // 2

# now load the raw gaze data
def load_gaze(path):
    """
    Raw samples with per-eye validity and an on-screen flag.

    on-screen uses the off_screen column from 0_convert_tsv.py, i.e. gaze inside the 1770x996
    stimulus area. Invalid samples are already marked off-screen there.
    """
    g = pd.read_csv(path, usecols=["device_time_stamp", "left_gaze_point_validity",
                                   "right_gaze_point_validity", "off_screen"])
    lv = (g["left_gaze_point_validity"] == 1).to_numpy() # lv = left eye valid
    rv = (g["right_gaze_point_validity"] == 1).to_numpy() # rv = right eye valid
    onscreen = (g["off_screen"] == 0).to_numpy()
    return g["device_time_stamp"].to_numpy(), lv, rv, onscreen

# load trial windows from the timing file
def trial_windows(timing_path):
    """
    One window per trial (MOV + its STILL) in ms, plus each timing-file trialNum's startTrial
    (which the verbose file's startTime is relative to).

    A trial runs from the MOV's startMoviePlayback to the paired STILL's endTrial. It starts at
    startMoviePlayback, NOT the MOV's startTrial, because the gap between trial start and
    playback start reaches 15s on some trials. (startTrial is only a fallback for a MOV missing
    its playback event; the MOV's own end is the fallback if its STILL is missing.)

    Note the gaze_event_tag column in the raw file looks like it could define trials, but
    every event in a trial carries the same "trial_N_" prefix (attn-getter, trial start,
    movie playback), so keying on it lumps them together and inflates durations. Instead,
    I'm using the timing file's start/end events.

    Returns a DataFrame with columns trial, label, trial_type, t0, t1, plus a dict mapping
    trialNum -> startTrial.
    """
    t = pd.read_csv(timing_path)
    ev = {tn: dict(zip(g["event"], g["time"])) for tn, g in t.groupby("trialNum")} # trialNum -> {event: time}
    types = t.groupby("trialNum")["trialType"].first()
    starts = {tn: e["startTrial"] for tn, e in ev.items() if "startTrial" in e}
    rows = []
    for tn, trial_type in types.items():
        if str(trial_type).endswith("_STILL"): # STILL rows are picked up through their MOV
            continue
        mov, still = ev[tn], ev.get(tn + 1, {})
        t0 = mov.get("startMoviePlayback", mov.get("startTrial"))
        t1 = still.get("endTrial", mov.get("endMoviePlayback", mov.get("endTrial")))
        if t0 is None or t1 is None:
            continue
        trial = pair_of(tn)
        rows.append((trial, TRIAL_LABELS.get(trial, str(trial)), short_name(trial_type), t0 * 1000, t1 * 1000)) # times in ms
    return pd.DataFrame(rows, columns=["trial", "label", "trial_type", "t0", "t1"]), starts

# per-trial validity, from the samples that fall inside each trial window
def validity_by_trial(ts, lv, rv, win):
    """
    Per window: number of samples, share with the left / right / at least one eye valid,
    share with both eyes invalid, and seconds with at least one eye valid.
    """
    idx = pd.IntervalIndex.from_arrays(win["t0"], win["t1"]) # create an interval index from the trial windows
    loc = idx.get_indexer(ts) # which trial window each timestamp from the raw gaze falls into
    keep = loc >= 0 # drop samples that don't fall into any trial window
    if not keep.any():
        return pd.DataFrame()
    d = pd.DataFrame({"trial": win["trial"].to_numpy()[loc[keep]],
                      "left": lv[keep], "right": rv[keep], "either": lv[keep] | rv[keep]})
    g = d.groupby("trial")
    out = pd.DataFrame({"n_samp": g.size(), "valid_left": g["left"].mean(),
                        "valid_right": g["right"].mean(), "validity": g["either"].mean()})
    out["both_invalid"] = 1 - out["validity"]
    out["valid_s"] = g["either"].sum() * SAMPLE_S
    return out


def coded_capture(verbose_path, starts, ts, valid, onscreen):
    """
    How much of the online coder's looking did the eye tracker capture?

    The verbose file logs the coder's key state as on/off bouts (column gazeOnOff), with startTime relative to
    that trialNum's startTrial, so it sits on the same clock as the raw gaze.

    Coding only happens during the STILL part of each trial (the coding window), so only those
    bouts are used. Returns one row per trial (1-6) x looking (1 = coder says looking, 0 = not looking).
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
        out.append(dict(trial=pair_of(tn), looking=int(onoff),
                        coded_s=(t1 - t0).sum() / 1000,
                        valid_s=sum(valid[a:b].sum() for a, b in zip(i0, i1)) * SAMPLE_S,
                        onscr_s=sum(onscreen[a:b].sum() for a, b in zip(i0, i1)) * SAMPLE_S))
    return pd.DataFrame(out)

# set up main function to run the data QC and print results
def main():
    raw_files = {p.stem.replace("_leap_voe_gaze", ""): p for p in raw_dir.glob("*_leap_voe_gaze.csv")}
    tim_files = {p.stem.replace("_leap_voe_timing", ""): p for p in timing_dir.glob("*_leap_voe_timing.csv")}
    vrb_files = {p.stem.replace("_leap_voe_verbose", ""): p for p in verbose_dir.glob("*_leap_voe_verbose.csv")}

    subjects = sorted(set(raw_files) & set(tim_files), key=subkey)
    print(f"raw {len(raw_files)} | timing {len(tim_files)} | verbose {len(vrb_files)} | analysed {len(subjects)}")
    dropped = sorted(set(raw_files) - set(subjects), key=subkey)
    if dropped:
        print(f"excluded (missing timing): {', '.join(dropped)}")

    recs, caps = [], []
    for sub in subjects:
        win, starts = trial_windows(tim_files[sub])
        if win.empty:
            continue
        ts, lv, rv, onscreen = load_gaze(raw_files[sub])
        r = validity_by_trial(ts, lv, rv, win)
        if r.empty:
            continue
        m = win.set_index("trial").join(r)
        m["trial_s"] = (m["t1"] - m["t0"]) / 1000
        m["test"] = m["trial_type"].str.startswith(("expected", "surprise"))
        m["flagged"] = m["both_invalid"] > MAX_INVALID_FRAC
        m["subject"] = sub
        m = m.reset_index()

        if sub in vrb_files:
            c = coded_capture(vrb_files[sub], starts, ts, lv | rv, onscreen)
            if not c.empty:
                c["subject"] = sub
                caps.append(c)
                on = c[c.looking == 1].set_index("trial")
                m = m.join(on[["coded_s", "valid_s"]].rename(columns={"valid_s": "captured_s"}), on="trial")
        recs.append(m)

    df = pd.concat(recs, ignore_index=True)
    df["trial"] = df["trial"].astype(int)
    df["capture"] = df["captured_s"] / df["coded_s"]
    order = sorted(df["subject"].unique(), key=subkey)
    val = df.pivot(index="subject", columns="trial", values="validity").reindex(order)
    fam = [c for c in val.columns if c <= 2]
    test = [c for c in val.columns if c > 2]

    # ---- 1. validity per subject per trial ----
    trials = sorted(val.columns)
    hdr = "  sub  " + "".join(f"{TRIAL_LABELS[t]:>8}" for t in trials) + "   |   FAM   TEST    ALL"
    print("\nVALIDITY per subject (fraction of raw samples with >=1 valid eye)")
    print("  trial = MOV + STILL, movie start to end of coding")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for sub in val.index:
        row = val.loc[sub]
        cells = "".join("       ." if pd.isna(row[t]) else f"{row[t]:>8.2f}" for t in trials)
        print(f"  {sub:<5}{cells}   |{row[fam].mean():>6.2f}{row[test].mean():>7.2f}{row.mean():>7.2f}")

    # ---- 2. group validity ----
    print("\nGROUP VALIDITY (across subject x trial)")
    parts = {"fam": df[~df.test], "test": df[df.test], "overall": df}
    print(pd.DataFrame({
        "left": [p.valid_left.mean() for p in parts.values()],
        "right": [p.valid_right.mean() for p in parts.values()],
        "either": [p.validity.mean() for p in parts.values()],
        "sd": [p.validity.std() for p in parts.values()],
        "min": [p.validity.min() for p in parts.values()],
        "max": [p.validity.max() for p in parts.values()],
        "valid_s": [p.valid_s.mean() for p in parts.values()],
        "trial_s": [p.trial_s.mean() for p in parts.values()],
        "n_trials": [len(p) for p in parts.values()],
    }, index=list(parts)).round(3).to_string())
    print("\n  left / right / either = share of samples where that eye (or at least one eye) was found")
    print("  valid_s = mean seconds per trial with at least one eye found; trial_s = mean trial length")

    # ---- 3. mostly-lost trials ----
    print(f"\nFLAGGED TRIALS (both eyes invalid on > {MAX_INVALID_FRAC:.0%} of samples)")
    print(pd.DataFrame({
        "flagged": [p.flagged.sum() for p in parts.values()],
        "of": [len(p) for p in parts.values()],
        "share": [p.flagged.mean() for p in parts.values()],
    }, index=list(parts)).round(3).to_string())
    test_trials = df[df.test]
    usable = test_trials.groupby("subject")["flagged"].apply(lambda f: (~f).sum()).reindex(order, fill_value=0)
    short = usable[usable < MIN_TEST_TRIALS]
    print(f"\n  subjects with fewer than {MIN_TEST_TRIALS} unflagged test trials: {len(short)}")
    for sub, n in short.items():
        print(f"    {sub}: {n} of {(test_trials.subject == sub).sum()}")

    # ---- 4. capture against the coder, coding window ----
    cap = pd.concat(caps, ignore_index=True) if caps else None
    if cap is not None:
        print("\nCODER-VERIFIED CAPTURE, coding window (STILL part of each trial)")
        g = cap.groupby("looking").agg(coded_s=("coded_s", "sum"), valid_s=("valid_s", "sum"),
                                       onscr_s=("onscr_s", "sum"))
        # ordered least to most restrictive: eye detected -> landed in the stimulus area
        g["validity"] = g.valid_s / g.coded_s
        g["onscreen"] = g.onscr_s / g.coded_s
        g.index = g.index.map({0: "coder: NOT looking", 1: "coder: looking"})
        print(g.round(3).to_string())
        print("\n  onscreen = gaze inside the stimulus area (off_screen == 0 in the raw gaze csv)")

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

    # ---- save per-trial table ----
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["subject", "trial", "label", "trial_type", "test", "trial_s", "n_samp",
            "valid_left", "valid_right", "validity", "both_invalid", "valid_s", "flagged",
            "coded_s", "captured_s", "capture"]
    out_csv = out_dir / "voe_data_qc_trials.csv"
    df[cols].round(4).to_csv(out_csv, index=False)
    print(f"\nsaved per-trial table: {out_csv.relative_to(project_root)}")

    return df, cap


# ---- figures ----
# Each figure is sized for a 16:9 Keynote slide (1920x1080), placed ~1600 px wide under a title
# box with 70pt text. 8 x 3.0 in leaves room for that title and side margins; fonts are set so
# tick labels land at ~20 px and axis labels at ~28 px once placed. No plot titles, the slide
# title does that.
FIG_SIZE = (8, 3.0)
# forest green throughout: ACCENT for bars/lines, PALE for the coder bars, MUTED for axes and
# error bars, GRID for gridlines; all text (labels, ticks, legend) is black
ACCENT, PALE, MUTED, GRID = "#2d6a35", "#d3e6d3", "#5e7363", "#ecf3ec"
TEXT, TEXT_MUTED = "#000000", "#000000"


def setup_plotting():
    """Import matplotlib, set fonts. Font falls back through Avenir -> Helvetica -> DejaVu Sans."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR) # silence findfont warnings for fallback fonts not installed
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": ["Avenir", "Avenir Next", "Helvetica", "Helvetica Neue",
                        "Nimbus Sans", "DejaVu Sans"],
        "font.size": 9, "axes.labelsize": 10, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "legend.fontsize": 8, "axes.edgecolor": MUTED, "axes.labelcolor": TEXT, "text.color": TEXT,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": TEXT_MUTED,
        "ytick.labelcolor": TEXT_MUTED})
    return plt


def style_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def mean_ci(values):
    """Mean and 95% CI half-width (t distribution) of a 1-D array, ignoring NaN."""
    from scipy import stats
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) < 2:
        return (v.mean() if len(v) else np.nan), np.nan
    return v.mean(), stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v))


def save(fig, plt, name):
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)
    print(f"saved figure: {out.relative_to(project_root)}")


def plot_by_subject(df, plt, order):
    """One bar per subject: mean % valid across all 12 trials, error bars = SD across trials."""
    s = (df.groupby("subject")["validity"].agg(["mean", "std"]) * 100).reindex(order)
    x = np.arange(len(s))
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.bar(x, s["mean"], width=0.75, color=ACCENT, zorder=2)
    ax.errorbar(x, s["mean"], yerr=s["std"], fmt="none", ecolor=MUTED, elinewidth=0.6, capsize=1.2, zorder=3)
    grand = s["mean"].mean()
    ax.axhline(grand, color="#222222", ls="--", lw=0.8, zorder=4)
    ax.text(len(s), grand, f"mean\n{grand:.0f}%", ha="left", va="center", fontsize=8) # right of the last bar
    ax.set_xticks(x)
    ax.set_xticklabels(s.index, rotation=90, fontsize=5.5)
    ax.set_xlim(-0.8, len(s) - 0.2)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Subject")
    ax.set_ylabel("Mean % valid (≥1 eye)")
    style_axes(ax)
    ax.tick_params(axis="x", length=0)
    save(fig, plt, "voe_data_qc_by_subject.png")


def plot_over_trials(df, plt):
    """% valid by trial (Fam 1 - Test 4). Faint line per subject, black group mean with 95% CI ribbon."""
    p = df.pivot(index="subject", columns="trial", values="validity") * 100
    trials = np.array(sorted(p.columns))
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    for _, row in p.iterrows():
        seen = row.notna().to_numpy()
        ax.plot(trials[seen], row.to_numpy()[seen], color=ACCENT, alpha=0.3, lw=0.7, zorder=1)
    stats = [mean_ci(p[t]) for t in trials]
    m = np.array([s[0] for s in stats]); ci = np.array([s[1] for s in stats])
    ax.fill_between(trials, m - ci, m + ci, color="#222222", alpha=0.15, lw=0, zorder=2)
    ax.plot(trials, m, color="#222222", lw=1.6, marker="o", ms=3.5, zorder=3)
    ax.axvline(2.5, color=MUTED, lw=0.8, ls=":", zorder=1)
    ax.set_xticks(trials)
    ax.set_xticklabels([TRIAL_LABELS[t] for t in trials])
    ax.set_xlim(0.7, trials.max() + 0.3)
    ax.set_ylim(0, 102)
    ax.set_xlabel("Trial  (lines = subjects; black = group mean ± 95% CI)")
    ax.set_ylabel("% valid (≥1 eye)")
    style_axes(ax)
    ax.tick_params(axis="x", length=0)
    save(fig, plt, "voe_data_qc_over_trials.png")


def plot_coder_vs_tracker(cap, plt):
    """
    Per subject, coding windows of all trials summed: seconds the coder marked as looking (pale), and of that,
    seconds the tracker had at least one valid eye (teal). Sorted by capture, highest first.
    """
    on = cap[cap.looking == 1].groupby("subject").agg(coded_s=("coded_s", "sum"), valid_s=("valid_s", "sum"))
    on["capture"] = on.valid_s / on.coded_s
    on = on.sort_values("capture", ascending=False)
    x = np.arange(len(on))
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    # Pale bar is the coder's looking total; teal is the subset the tracker actually recorded,
    # so the visible gap is what was missed rather than two independent quantities.
    ax.bar(x, on.coded_s, width=0.75, color=PALE, zorder=1, label="Coder: total looking (s)")
    ax.bar(x, on.valid_s, width=0.75, color=ACCENT, zorder=2, label="Eye tracker: of that, ≥1 valid eye (s)")
    ax.set_xticks(x)
    ax.set_xticklabels(on.index, rotation=90, fontsize=5.5)
    ax.set_xlim(-0.8, len(on) - 0.2)
    ax.set_xlabel("Subject  (sorted by capture)")
    ax.set_ylabel("Seconds coded as looking")
    # legend and mean sit above the axes so they never cover the bars
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, borderaxespad=0.2)
    ax.text(1.0, 1.0, f"mean capture = {on.capture.mean():.0%}", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9, color=TEXT, fontweight="bold")
    style_axes(ax)
    ax.tick_params(axis="x", length=0)
    save(fig, plt, "voe_data_qc_coder_vs_tracker.png")


def make_figures(df, cap):
    plt = setup_plotting()
    order = sorted(df["subject"].unique(), key=subkey)
    plot_by_subject(df, plt, order)
    plot_over_trials(df, plt)
    if cap is not None:
        plot_coder_vs_tracker(cap, plt)


if __name__ == "__main__":
    df, cap = main()
    make_figures(df, cap)
