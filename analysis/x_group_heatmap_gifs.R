## =============================================================================
## Group fixation-density heatmaps by presentation order (1st vs 2nd exposure)
## =============================================================================
##
## WHAT THIS PRODUCES
## For each of the 4 test trial types (expected_duck, surprise_duck,
## expected_shoe, surprise_shoe), this renders one GIF with two stacked
## panels: occurrence 1 (the infant's FIRST time seeing that clip, top panel)
## above occurrence 2 (their SECOND time seeing it, bottom panel). Each
## trial type is shown to a given infant twice (see the timing files -- e.g.
## trials 5/6 and 9/10 are both "expected_duck", trials 7/8 and 11/12 are
## both "surprise_shoe" for a subject who got that object/condition
## assignment). This lets you visually compare whether gaze behavior differs
## between the first and second exposure to the same event.
##
## Each GIF steps through a SLIDING TIME WINDOW (default: 2s wide, sliding by
## 0.5s each step -- e.g. 0-2s, 0.5-2.5s, 1-3s, ...). Every step is a static
## group-level (all subjects pooled) fixation-density heatmap for that
## window, composited over the video frame at the window's midpoint. This is
## NOT a smooth video with a moving heatmap overlaid frame-by-frame -- it's a
## slideshow of overlapping snapshots, each one a "what did the group look at
## during this ~2 second stretch" summary. That's a deliberate choice: with
## infant fixation counts this low, a true per-video-frame (1/30s) heatmap
## would have too few pooled points per frame to mean anything.
##
## The windows run from movie start all the way through the end of the
## STILL (frozen last-frame) period, not just through the movie itself.
## STILL duration is NOT fixed -- it lasts until the infant looks away (or
## caps at 30s by design), so different subjects contribute data for
## different lengths of time. Because of that, every panel is annotated with
## "n = X" (top-right, white text on a dark box) showing how many distinct
## subjects actually have a fixation in THAT SPECIFIC window -- this number
## will shrink over the course of the GIF as infants look away one by one.
## Treat windows with a low n with appropriate skepticism; the heatmap shape
## for e.g. n=2 is not a reliable group estimate.
##
## HOW TO ADAPT THIS FOR OTHER USES
## - Change WINDOW_SEC / STEP_SEC below to make windows wider/narrower or
##   more/less overlapping.
## - Change the `video_map` list to point at different stimulus videos.
## - The whole thing runs off x_label_fixations.py's output, not raw gaze --
##   if you want a raw-gaze version (denser, but no duration-weighting
##   needed since raw samples arrive at a fixed rate), start from
##   voe_heatmap.Rmd's approach instead, which does that already.
##
## WHY FIXATIONS INSTEAD OF RAW GAZE (unlike voe_heatmap.Rmd, which uses raw
## gaze samples): this was a deliberate choice to use the I2MC fixation
## output from x_label_fixations.py rather than raw continuous samples, so
## the heatmap reflects "where the group actually looked" (post-filtering of
## blinks/saccades/data loss) rather than every raw sample including noise.
##
## DURATION WEIGHTING (a fixation that lasted 1000ms should count for more
## than one that lasted 40ms). ggdensity::geom_hdr has NO native `weight`
## aesthetic -- this was confirmed by reading ggdensity's actual source
## (StatHdr$compute_group and get_hdr() both only ever touch data$x/data$y,
## never a weight column). So duration-weighting is faked by REPEATING each
## fixation's (x, y) position once per TICK_MS of overlap between that
## fixation and the current window (clipped to just the overlapping portion
## -- a fixation that's only half inside a window contributes only that
## half's worth of duration, not its full duration). More repeats = more
## influence on the density estimate for that window. See TICK_MS below to
## change the granularity of this.
##
## BOUNDS FILTERING. A fixation's gaze position can legitimately fall
## outside the physical screen (0-1920 x 0-1080 px) -- I2MC doesn't clip to
## the display. Those fixations are dropped BEFORE any windowing or
## plotting happens (see the `filter(x >= 0, x <= SCREEN_WIDTH, ...)` call
## below), so they can never contribute to (or bias) the density estimate,
## not merely be excluded from the visual render. Note this filters to the
## full SCREEN bounds, not the narrower stimulus/AOI bounds (1770x996) --
## an infant can validly look at blank screen space around the toy.
##
## PANEL CLIPPING (a subtler bug worth knowing about if you touch this
## code): ggdensity's KDE grid defaults to the FULL plot scale range unless
## told otherwise via xlim/ylim -- since this plot has two panels stacked
## into one canvas, that means a density contour computed from the TOP
## panel's data could visually bleed across the divider into the BOTTOM
## panel's space (and vice versa), even though the underlying data points
## themselves never cross that line. Confirmed by pixel-scanning the gap
## between panels before/after the fix. Each geom_hdr() call below passes
## explicit xlim/ylim to constrain its density grid to its own panel's
## half of the canvas -- don't remove those or the bleeding comes back.
##
## DATA SOURCE: the labeled fixation files from x_label_fixations.py
## (data/leap_voe_data/fixations/[subject]/[subject]_leap_voe_gaze_fix_labeled.csv),
## filtered to phase %in% c("movie", "still") -- i.e. excludes
## attention-getter and inter-trial-interval fixations.
##
## OUTPUT: data/leap_voe_data/gaze_heatmap_videos/[trial_type]_occurrence_compare.gif
## (and a same-named .mp4, which is the higher-quality byproduct of building
## the gif). This folder is gitignored, same as voe_heatmap.Rmd's output --
## these are meant to be regenerated locally from source data, not committed.
## A full run (all 4 trial types) takes a few minutes.

library(tidyverse)
library(png)
library(ggdensity)
library(here)
library(janitor)

# =============================================================================
# Config
# =============================================================================

FRAME_RATE   <- 30   # source video frame rate. Used for (a) extracting frames from the
                      # stimulus mp4s via ffmpeg, and (b) converting a window's midpoint
                      # time into a specific frame number to use as that window's
                      # background image. Matches the mp4's own encoded frame rate --
                      # changing this without checking the actual video files will
                      # misalign the background frame shown for each window.
MS_PER_FRAME <- 1000 / FRAME_RATE

WINDOW_SEC <- 2     # sliding window length, in seconds. Each GIF "step" pools all
                    # fixation data from this many seconds of the trial.
STEP_SEC   <- 0.5   # how far the window slides forward each step, in seconds. Smaller
                    # than WINDOW_SEC means windows overlap (e.g. 2s window / 0.5s step
                    # means each window shares 1.5s of data with its neighbor) -- more
                    # steps, smoother-feeling animation, but adjacent windows are highly
                    # correlated since they mostly contain the same fixations.
TICK_MS    <- 20    # duration-weighting granularity (see "DURATION WEIGHTING" above):
                    # 1 repeated point gets added to a window's density input per this
                    # many ms of overlap between a fixation and that window. Smaller =
                    # finer-grained weighting but more rows generated (slower); this
                    # value just needs to be small relative to typical fixation
                    # durations (I2MC's minFixDur is 40ms) to weight reasonably.

# Screen/stimulus geometry -- must match how the "with_borders" stimulus videos were
# actually built and how PyHab displayed them (see voe_heatmap.Rmd's own config chunk,
# which uses these exact same numbers). SCREEN_WIDTH/HEIGHT is the full display; the
# stimulus itself is scaled down to STIM_WIDTH x STIM_HEIGHT and centered, leaving a
# border on all sides (X_OFFSET/Y_OFFSET). NOTE: the "with_borders" mp4 files have this
# border baked into the video pixels themselves (confirmed by inspecting a raw extracted
# frame -- the white border extends a little further than just X_OFFSET/Y_OFFSET would
# suggest, and its exact extent varies a bit by scene). Don't assume the area right at
# the edge of the AOI box below is meaningfully dark; it can be white depending on the
# frame's own content. This is why the "n =" subject-count label uses an opaque
# background box rather than relying on bare white text being visible there.
SCREEN_WIDTH  <- 1920
SCREEN_HEIGHT <- 1080
STIM_WIDTH    <- 1770
STIM_HEIGHT   <- 996
X_OFFSET      <- (SCREEN_WIDTH - STIM_WIDTH) / 2
Y_OFFSET      <- (SCREEN_HEIGHT - STIM_HEIGHT) / 2

WINDOW_GIF_FPS <- 1 / STEP_SEC   # output gif playback speed: how many WINDOWS (not video
                       # frames) are shown per second. Set to 1/STEP_SEC so playback
                       # duration matches the real elapsed time of the underlying
                       # movie+still window (each window's screen-time == STEP_SEC,
                       # matching how far it advances the underlying timeline). At the
                       # old fixed value of 1, windows overlap (STEP_SEC < WINDOW_SEC)
                       # but each still got a full real second on screen, so playback ran
                       # ~WINDOW_SEC/STEP_SEC times longer than the real event duration
                       # (2x, at the old 2s/0.5s settings).
GIF_WIDTH      <- 700  # output gif width in px; height scales automatically to preserve
                       # the (two-screens-tall) aspect ratio. Smaller = smaller file size.

# Where things live in the project. `here()` resolves relative to the project root
# (wherever pill.Rproj / the git repo root is), so this works regardless of your
# working directory when you source this script.
stimuli_path   <- here("stimuli", "leap_voe_stimuli", "videos", "with_borders")
fixations_dir  <- here("data", "leap_voe_data", "fixations")
timing_dir     <- here("data", "leap_voe_data", "raw_events", "timing")
output_folder  <- here("data", "leap_voe_data", "gaze_heatmap_videos")
frames_root    <- here("data", "leap_voe_data", "tmp_frames")  # scratch space, deleted per-trial-type as we go

dir.create(output_folder, showWarnings = FALSE, recursive = TRUE)
dir.create(frames_root,   showWarnings = FALSE, recursive = TRUE)

# Maps each base trial type (as produced by x_label_fixations.py's trial_type column,
# minus the _1/_2 occurrence suffix) to the actual stimulus video file to composite the
# heatmap onto. Only the 4 "test" trial types get their own GIF here -- familiarization
# (fam_duck / fam_shoe) trials are present in the fixation data but not rendered,
# since each infant only sees familiarization once (no 1st-vs-2nd comparison to make).
video_map <- c(
  "expected_duck"  = "duck_expected_bright.mp4",
  "surprise_duck"  = "duck_surprise_bright.mp4",
  "expected_shoe"  = "shoe_expected_bright.mp4",
  "surprise_shoe"  = "shoe_surprise_bright.mp4"
)

# =============================================================================
# Build (subject, trial_type, start_rel, end_rel, x, y) from labeled fixations
# start_rel/end_rel are ms relative to that trial's own movie start.
# =============================================================================

fix_files <- list.files(fixations_dir, pattern = "_fix_labeled\\.csv$",
                         recursive = TRUE, full.names = TRUE)
message("Found ", length(fix_files), " labeled fixation files")

# Per-subject: trialNum -> movie start time (ms), read from that subject's own timing
# file (data/leap_voe_data/raw_events/timing/[subject]_leap_voe_timing.csv).
#
# Every MOV trial has its own startMoviePlayback event, which we use as t=0 for that
# presentation. The matching STILL trial (the frozen-last-frame coding window right
# after it) does NOT have its own startMoviePlayback event -- but per the pairing used
# everywhere else in this project (see voe_heatmap.Rmd's build-trial-timing chunk), a
# STILL trial's trialNum is always exactly its paired MOV trial's trialNum + 1. So we
# duplicate each MOV trial's start time under trialNum+1, letting the STILL trial
# inherit its MOV trial's anchor. This means fixation timestamps from BOTH the movie
# and the still period end up on the same t=0-at-movie-start timeline, which is what
# lets us build one continuous set of sliding windows spanning both phases.
#
# Subjects missing a timing file entirely (as of this writing: 101 and 107) are skipped
# here (get_movie_starts returns NULL for them, and the map_dfr below just contributes
# nothing for that subject) -- same skip behavior as x_label_fixations.py.
get_movie_starts <- function(sub_id) {
  timing_path <- file.path(timing_dir, paste0(sub_id, "_leap_voe_timing.csv"))
  if (!file.exists(timing_path)) return(NULL)
  timing_raw <- read_csv(timing_path, show_col_types = FALSE)
  mov_starts <- timing_raw |>
    filter(event == "startMoviePlayback") |>
    select(trialNum, movie_start = time) |>
    mutate(movie_start = movie_start * 1000)  # timing files are in seconds; we work in ms throughout
  still_starts <- mov_starts |> mutate(trialNum = trialNum + 1)
  bind_rows(mov_starts, still_starts)
}

# Loop over every subject's labeled fixation CSV and build one big long-format table of
# individual fixations, each with a start/end time relative to ITS OWN trial's movie
# start (so occurrence 1 and occurrence 2 of the same trial_type are each on their own
# 0-based timeline, directly comparable window-by-window).
all_fixations <- map_dfr(fix_files, function(f) {
  sub_id <- str_remove(basename(f), "_leap_voe_gaze_fix_labeled\\.csv$")

  movie_starts <- get_movie_starts(sub_id)
  if (is.null(movie_starts)) return(tibble())  # no timing file for this subject -- skip entirely

  fix_df <- read_csv(f, show_col_types = FALSE) |> clean_names()  # clean_names: startT -> start_t, etc.

  # Keep only fixations that happened during the movie or the still/freeze period
  # (drops attention-getter and inter-trial-interval fixations, and any row where
  # x_label_fixations.py couldn't determine a trial_type at all).
  movie_fix <- fix_df |>
    filter(phase %in% c("movie", "still"), !is.na(trial_num), trial_type != "") |>
    inner_join(movie_starts, by = c("trial_num" = "trialNum"))

  if (nrow(movie_fix) == 0) return(tibble())

  movie_fix |>
    transmute(
      sub_id = sub_id,
      trial_type = trial_type,          # e.g. "expected_duck_1", "surprise_shoe_2" (includes occurrence suffix)
      start_rel = start_t - movie_start, # ms since this trial's own movie start
      end_rel   = end_t - movie_start,
      x = xpos,   # I2MC fixation x position, screen pixel space (top-left origin, NOT normalized 0-1)
      y = ypos    # same, y-down (increases downward, like image coordinates)
    ) |>
    # Drop fixations whose gaze position falls outside the actual screen (0-1920,
    # 0-1080). This happens because I2MC doesn't clip fixation positions to the
    # display -- a fixation's median position can legitimately land off-screen if
    # the infant's gaze drifted there. Filtering HERE (before any windowing/
    # plotting) means these points are excluded from the density estimate itself,
    # not just hidden from the final image -- they never get a chance to skew the
    # heatmap. See the "BOUNDS FILTERING" note at the top of this file.
    filter(x >= 0, x <= SCREEN_WIDTH, y >= 0, y <= SCREEN_HEIGHT)
})

message("Total movie+still fixations (in-bounds): ", nrow(all_fixations))
message("Trial types present: ", paste(sort(unique(all_fixations$trial_type)), collapse = ", "))

# =============================================================================
# Sliding windows + duration-weighted expansion
# =============================================================================

# Builds the sequence of sliding windows covering [0, total_ms], each WINDOW_SEC wide,
# starting every STEP_SEC. The very last window is truncated to end exactly at
# total_ms (via pmin) rather than running past the end of the data.
#
# mid_frame: which video frame number (1-indexed, matching the ffmpeg-extracted
# frame_%04d.png files) should be shown as this window's background image -- the frame
# at the window's temporal midpoint. If that midpoint falls after the movie itself has
# ended (i.e. during the STILL/frozen period), this will compute a frame number beyond
# how many frames actually got extracted; render_occurrence_comparison() clamps it back
# down to the last real frame (min(w$mid_frame, n_frames)) later, which has the effect
# of freezing on the movie's final frame for the whole STILL period -- matching what the
# infant actually saw (the display genuinely freezes on that frame during STILL).
build_windows <- function(total_ms) {
  window_ms <- WINDOW_SEC * 1000
  step_ms   <- STEP_SEC * 1000
  w_start <- seq(0, total_ms - window_ms, by = step_ms)
  if (length(w_start) == 0) w_start <- 0  # clip is shorter than one window -- just use one window covering all of it
  tibble(
    window_idx = seq_along(w_start),
    w_start = w_start,
    w_end   = pmin(w_start + window_ms, total_ms),
    mid_frame = pmax(1, floor(((w_start + pmin(w_start + window_ms, total_ms)) / 2) / MS_PER_FRAME) + 1)
  )
}

# For one occurrence's (subject, trial_type, start_rel, end_rel, x, y) fixations, expand
# against a set of windows into a long-format (sub_id, window_idx, x, y) table, with each
# fixation appearing once PER TICK_MS of its overlap with a given window.
#
# Example: a fixation spanning 1800-2600ms, against windows [0,2000] and [1000,3000]:
#   - overlaps [0,2000] by 200ms (1800 to 2000)   -> ~10 repeated rows (200/TICK_MS)
#   - overlaps [1000,3000] by 800ms (1800 to 2600) -> ~40 repeated rows (800/TICK_MS)
# So this single fixation contributes far more "weight" (more repeated identical
# points feeding the KDE) to the window it mostly overlaps than to one it barely
# touches -- that's the duration-weighting mechanism described at the top of this file.
# A fixation with zero overlap with a given window contributes nothing to it.
expand_to_windows <- function(fixations_df, windows) {
  if (nrow(fixations_df) == 0) return(tibble())

  map_dfr(seq_len(nrow(windows)), function(i) {
    w_start <- windows$w_start[i]
    w_end   <- windows$w_end[i]

    # Clip each fixation's span to this window's span; overlap_ms <= 0 means no overlap.
    overlap_start <- pmax(fixations_df$start_rel, w_start)
    overlap_end   <- pmin(fixations_df$end_rel, w_end)
    overlap_ms    <- overlap_end - overlap_start

    keep <- overlap_ms > 0
    if (!any(keep)) return(tibble())

    n_reps <- pmax(1, round(overlap_ms[keep] / TICK_MS))  # at least 1 rep even for a very brief overlap

    tibble(
      sub_id = fixations_df$sub_id[keep],
      window_idx = windows$window_idx[i],
      x = fixations_df$x[keep],
      y = fixations_df$y[keep]
    ) |>
      uncount(n_reps)  # tidyr::uncount -- repeats each row n_reps times
  })
}

# =============================================================================
# Render one stacked (occurrence 1 / occurrence 2) GIF for one base trial type
# =============================================================================

render_occurrence_comparison <- function(base_trial_type) {
  message("\n=== ", base_trial_type, " ===")

  video_file <- file.path(stimuli_path, video_map[[base_trial_type]])
  # Per-trial-type scratch folders for extracted/composited frames -- deleted at the
  # end of this function, so nothing here persists between runs.
  frame_split_path <- file.path(frames_root, paste0("split_", base_trial_type))
  frame_merge_path <- file.path(frames_root, paste0("merge_", base_trial_type))
  dir.create(frame_split_path, showWarnings = FALSE)
  dir.create(frame_merge_path, showWarnings = FALSE)

  # Extract every frame of the stimulus video as a PNG (frame_0001.png, frame_0002.png,
  # ...), so we can later pick out just the ones we need as window backgrounds and draw
  # on top of them with ggplot. This is the ACTUAL "with_borders" video that was shown
  # to infants (not the "full_frame" unbordered source cut) -- see the Config section's
  # note on stimulus geometry for why that distinction matters.
  message("Extracting frames from: ", basename(video_file))
  system(paste0(
    'ffmpeg -y -i "', video_file, '" -vf "fps=', FRAME_RATE, '" "',
    frame_split_path, '/frame_%04d.png"'
  ))
  n_frames <- length(list.files(frame_split_path, pattern = "^frame_[0-9]{4}\\.png$"))
  movie_ms <- n_frames * MS_PER_FRAME
  message("Extracted ", n_frames, " frames (", round(movie_ms/1000, 1), "s movie)")

  # occ1_fix / occ2_fix: this trial type's fixations, split by which presentation
  # (1st or 2nd time this infant saw this specific clip) they belong to. Note the
  # subject sets for occurrence 1 and 2 aren't guaranteed identical -- a subject can
  # have usable fixation data for one presentation but not the other (missing/excluded
  # data, etc.) -- the "Occurrence 1: N subjects" / "Occurrence 2: N subjects" messages
  # below will often differ slightly.
  occ1_fix <- all_fixations |> filter(trial_type == paste0(base_trial_type, "_1"))
  occ2_fix <- all_fixations |> filter(trial_type == paste0(base_trial_type, "_2"))
  message("Occurrence 1: ", n_distinct(occ1_fix$sub_id), " subjects, ", nrow(occ1_fix), " fixations")
  message("Occurrence 2: ", n_distinct(occ2_fix$sub_id), " subjects, ", nrow(occ2_fix), " fixations")

  # How far do the sliding windows need to extend? At minimum, the movie's own length
  # (movie_ms). But STILL period fixations can extend well past that -- STILL runs
  # until the infant looks away, capped at 30s by design -- and different subjects will
  # have different STILL lengths. So we take whichever is longer: the movie itself, or
  # the single latest fixation end-time across BOTH occurrences (so both panels' window
  # sequences line up 1:1, sharing the same window_idx meaning "the same relative time
  # since movie start" in both panels).
  max_fix_ms <- suppressWarnings(max(c(occ1_fix$end_rel, occ2_fix$end_rel), na.rm = TRUE))
  total_ms <- max(movie_ms, max_fix_ms, na.rm = TRUE)
  if (!is.finite(total_ms)) total_ms <- movie_ms  # guards against a trial type with zero fixations at all

  windows <- build_windows(total_ms)
  message("Built ", nrow(windows), " sliding windows (", WINDOW_SEC, "s window, ", STEP_SEC, "s step, ",
          round(total_ms/1000, 1), "s total incl. STILL)")

  # Expand each occurrence's fixations into the duration-weighted (sub_id, window_idx,
  # x, y) long format described above expand_to_windows(). occ1/occ2 here are much
  # bigger tables than occ1_fix/occ2_fix (many repeated rows per fixation).
  occ1 <- expand_to_windows(occ1_fix, windows)
  occ2 <- expand_to_windows(occ2_fix, windows)

  # The rendered canvas is one screen wide and TWO screens tall -- occurrence 1's panel
  # occupies the top half, occurrence 2's the bottom half, with a thin divider line
  # drawn at SCREEN_HEIGHT (see geom_hline below).
  canvas_w <- SCREEN_WIDTH
  canvas_h <- SCREEN_HEIGHT * 2

  # ---- one iteration of this loop = one window = one frame of the output GIF ----
  walk(seq_len(nrow(windows)), function(i) {
    w <- windows[i, ]
    message("  window ", i, " of ", nrow(windows), ": ",
            round(w$w_start/1000, 1), "-", round(w$w_end/1000, 1), "s (frame ", w$mid_frame, ")")

    # Background image for this window: the video frame at its midpoint, clamped to
    # the last real extracted frame if the midpoint falls in the STILL period (past
    # the movie's own length) -- this is what makes the display correctly "freeze" on
    # the final frame for every STILL-period window, same as what the infant saw.
    img_path <- file.path(frame_split_path, sprintf("frame_%04d.png", min(w$mid_frame, n_frames)))
    out_path <- file.path(frame_merge_path, sprintf("window_%04d.png", i))
    frame_img <- as.raster(readPNG(img_path))

    # x/y from I2MC fixations are already in pixel space (top-left origin, y-down) --
    # UNLIKE voe_heatmap.Rmd's gaze_x/gaze_y, which are normalized 0-1 and need
    # multiplying by screen dimensions AND flipping via (1 - gaze_y). Ours are already
    # scaled to pixels, so we only need the flip (not a rescale) to go from "y-down,
    # origin top-left" (how the data is stored) to "y-up" (how ggplot's coordinate
    # system works) -- get this wrong and every point silently lands off-canvas
    # instead of erroring, so double check against a known feature (e.g. the toy's own
    # position in a frame) if you change this.
    #
    # occurrence 1's points get shifted up by one SCREEN_HEIGHT so they land in the
    # canvas's top half; occurrence 2's points are used as-is (bottom half, [0, SCREEN_HEIGHT]).
    g1 <- occ1 |> filter(window_idx == w$window_idx) |>
      mutate(px = x, py = (SCREEN_HEIGHT - y) + SCREEN_HEIGHT)
    g2 <- occ2 |> filter(window_idx == w$window_idx) |>
      mutate(px = x, py = SCREEN_HEIGHT - y)

    # How many distinct subjects actually have a fixation landing in THIS window (not
    # the total pool size for the whole trial type -- this is per-window, and will
    # shrink over the course of STILL as infants look away). Displayed via the "n ="
    # annotation added near the end of this block.
    n_sub1 <- n_distinct(g1$sub_id)
    n_sub2 <- n_distinct(g2$sub_id)

    # ---- build the plot, layer by layer ----
    p <- ggplot() +
      theme_void() +
      theme(legend.position = "none",
            panel.background = element_rect(fill = "white", color = NA),
            plot.margin = margin(0, 0, 0, 0)) +
      # the SAME video frame is drawn twice, once into each panel's AOI box
      annotation_raster(frame_img, xmin = X_OFFSET, xmax = X_OFFSET + STIM_WIDTH,
                         ymin = Y_OFFSET + SCREEN_HEIGHT, ymax = Y_OFFSET + STIM_HEIGHT + SCREEN_HEIGHT) +
      annotation_raster(frame_img, xmin = X_OFFSET, xmax = X_OFFSET + STIM_WIDTH,
                         ymin = Y_OFFSET, ymax = Y_OFFSET + STIM_HEIGHT) +
      geom_hline(yintercept = SCREEN_HEIGHT, color = "grey40", linewidth = 0.5) +  # divider between panels
      annotate("text", x = 20, y = canvas_h - 20,
               label = paste0("1st exposure  |  ", round(w$w_start/1000, 1), "-", round(w$w_end/1000, 1), "s"),
               hjust = 0, vjust = 1, size = 5, color = "black") +
      annotate("text", x = 20, y = SCREEN_HEIGHT - 20,
               label = paste0("2nd exposure  |  ", round(w$w_start/1000, 1), "-", round(w$w_end/1000, 1), "s"),
               hjust = 0, vjust = 1, size = 5, color = "black")
    # ^ these two black labels sit at x=20, which is inside the white canvas margin
    # (the video AOI doesn't start until x=X_OFFSET=75), so black-on-white is reliably
    # legible there. That's NOT true for the "n =" labels below (video content can
    # reach into that corner) -- see their own comment for why they're handled
    # differently (opaque box) rather than just copying this pattern.

    # kde2d (the density estimator underlying geom_hdr) needs actual spread in BOTH
    # x and y to compute a bandwidth. A thin window can have nrow(g) >= 3 yet still be,
    # say, one single subject's one single fixation repeated many times for duration
    # weighting -- every repeated point identical, zero variance, and kde2d errors with
    # "bandwidths must be strictly positive". has_spread() catches the common case
    # before even trying; the tryCatch below is a second safety net for edge cases
    # where variance is nonzero but still too small for kde2d's actual bandwidth
    # estimator (this does still happen occasionally -- as of this writing, about 3
    # times across a full 4-trial-type run, always in very-low-n late-STILL windows).
    # Either way, the window just renders without a heatmap layer for that occurrence
    # rather than crashing the whole run.
    has_spread <- function(df) nrow(df) >= 3 && sd(df$px) > 0 && sd(df$py) > 0

    # IMPORTANT: xlim/ylim here are not just cosmetic bounds -- without them,
    # ggdensity's stat_hdr() computes its KDE grid over the FULL plot scale (both
    # panels combined) by default, and a contour computed from top-panel data can
    # visually bleed across the divider into the bottom panel's space (confirmed by
    # pixel-scanning the gap between panels with/without this). Passing xlim/ylim
    # constrains each panel's density grid to just its own half of the canvas, so a
    # contour can never render outside the panel its data actually belongs to. If you
    # ever see a heatmap blob that looks like it's floating in the wrong panel or past
    # the screen edge, check this first.
    if (has_spread(g1)) {
      p <- tryCatch(
        p + geom_hdr(data = g1, aes(px, py, fill = after_stat(probs)), alpha = 0.5,
                      xlim = c(0, SCREEN_WIDTH), ylim = c(SCREEN_HEIGHT, canvas_h)),
        error = function(e) { message("  window ", i, " occ1 density failed: ", e$message); p }
      )
    }
    if (has_spread(g2)) {
      p <- tryCatch(
        p + geom_hdr(data = g2, aes(px, py, fill = after_stat(probs)), alpha = 0.5,
                      xlim = c(0, SCREEN_WIDTH), ylim = c(0, SCREEN_HEIGHT)),
        error = function(e) { message("  window ", i, " occ2 density failed: ", e$message); p }
      )
    }

    # Subject-count ("n = X") annotations are added LAST, after the density layers,
    # specifically so they always draw ON TOP of the heatmap rather than being
    # obscured underneath it (ggplot draws layers in the order they're added to the
    # plot object -- adding these earlier in the chain, before the geom_hdr() calls
    # above, was an actual bug caught during development: the heatmap would render
    # over the count label whenever a density contour happened to reach that corner).
    #
    # White text alone is not reliably legible here regardless of draw order: the
    # "with_borders" video files have their own baked-in white letterboxing that
    # extends a bit past X_OFFSET/Y_OFFSET, and general scene brightness varies frame
    # to frame -- so you can't assume this corner is a dark part of the video. The
    # semi-opaque dark box behind the text guarantees contrast against anything
    # underneath it (video content OR heatmap color).
    p <- p +
      annotate("rect", xmin = canvas_w - 170, xmax = canvas_w - 10,
               ymin = canvas_h - 55, ymax = canvas_h - 10,
               fill = "black", alpha = 0.55) +
      annotate("text", x = canvas_w - 20, y = canvas_h - 20,
               label = paste0("n = ", n_sub1),
               hjust = 1, vjust = 1, size = 5, color = "white") +
      annotate("rect", xmin = canvas_w - 170, xmax = canvas_w - 10,
               ymin = SCREEN_HEIGHT - 55, ymax = SCREEN_HEIGHT - 10,
               fill = "black", alpha = 0.55) +
      annotate("text", x = canvas_w - 20, y = SCREEN_HEIGHT - 20,
               label = paste0("n = ", n_sub2),
               hjust = 1, vjust = 1, size = 5, color = "white")

    p <- p +
      scale_x_continuous(limits = c(0, canvas_w), expand = c(0, 0)) +
      scale_y_continuous(limits = c(0, canvas_h), expand = c(0, 0)) +
      coord_fixed()  # 1 data unit in x == 1 data unit in y, so the composited video isn't stretched

    tryCatch(
      ggsave(out_path, plot = p, width = canvas_w / 100, height = canvas_h / 100,
             units = "in", dpi = 100),
      error = function(e) message("  window ", i, " failed: ", e$message)
    )
  })

  # ---- compile all the per-window PNGs into an mp4, then convert that to a GIF ----
  # mp4 first, then gif from the mp4 (rather than PNGs -> gif directly), because
  # ffmpeg's two-pass palette generation (palettegen + paletteuse below) gives much
  # better GIF color quality than a naive single-pass conversion, and it's easiest to
  # do that starting from a compressed video rather than a raw image sequence.
  message("Compiling windows -> mp4 -> gif")
  mp4_path <- file.path(output_folder, paste0(base_trial_type, "_occurrence_compare.mp4"))
  gif_path <- file.path(output_folder, paste0(base_trial_type, "_occurrence_compare.gif"))
  palette_path <- file.path(tempdir(), paste0(base_trial_type, "_palette.png"))

  # windows -> mp4, at WINDOW_GIF_FPS (i.e. one video frame per window, played back at
  # the "slideshow" pace set in Config)
  system(paste0(
    'ffmpeg -y -framerate ', WINDOW_GIF_FPS, ' -i "', frame_merge_path, '/window_%04d.png" ',
    '-c:v libx264 -vf format=yuv420p "', mp4_path, '"'
  ))
  # generate an optimized 256-color palette for this specific video (better quality
  # than ffmpeg's default gif encoder palette)
  system(paste0(
    'ffmpeg -y -i "', mp4_path, '" -vf "fps=', WINDOW_GIF_FPS, ',scale=', GIF_WIDTH, ':-1:flags=lanczos,palettegen" "',
    palette_path, '"'
  ))
  # apply that palette while encoding the final gif
  system(paste0(
    'ffmpeg -y -i "', mp4_path, '" -i "', palette_path, '" ',
    '-filter_complex "fps=', WINDOW_GIF_FPS, ',scale=', GIF_WIDTH, ':-1:flags=lanczos[x];[x][1:v]paletteuse" "',
    gif_path, '"'
  ))

  # clean up this trial type's scratch frames (extracted + composited) -- nothing left
  # behind except the final mp4/gif in output_folder
  unlink(frame_split_path, recursive = TRUE)
  unlink(frame_merge_path, recursive = TRUE)
  message("Saved: ", gif_path)
}

# =============================================================================
# Run all 4
# =============================================================================

for (tt in names(video_map)) {
  render_occurrence_comparison(tt)
}

message("\nAll done. GIFs in: ", output_folder)
