# For each participant, plots test-trial fixations over time: 2 panels
# (expected top, surprise bottom), occurrence 1 above occurrence 2 in each.
# Segment length = duration (not also mapped to y). Color = occurrence,
# alpha = gaze eccentricity (darker = closer to screen center). Bottom
# "Duration scale" panel shows this participant's min/mean/max fixation
# duration, to scale, for reference.
#
# Output: data/leap_voe_data/fixation_timelines/[participant]_fixation_timeline.png

library(tidyverse)
library(here)

# =============================================================================
# 1. Setup
# =============================================================================

# Screen used for stimulus presentation (matches x_group_heatmap_gifs.Rmd) --
# used to compute gaze eccentricity from screen center.
SCREEN_WIDTH  <- 1920
SCREEN_HEIGHT <- 1080

fixations_dir <- here("data", "leap_voe_data", "fixations")
timing_dir    <- here("data", "leap_voe_data", "raw_events", "timing")
out_dir       <- here("data", "leap_voe_data", "fixation_timelines")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

fix_path     <- function(pid) here(fixations_dir, paste0(pid, "_leap_voe_gaze"), paste0(pid, "_leap_voe_gaze_fix_labeled.csv"))
timing_path  <- function(pid) here(timing_dir, paste0(pid, "_leap_voe_timing.csv"))
verbose_path <- function(pid) here("data", "leap_voe_data", "raw_events", "verbose", paste0(pid, "_leap_voe_verbose.csv"))

# STILL trials are child-controlled: PyHab ends one after this many
# continuous seconds looking away, or at a 30s cap, whichever comes first.
LOOKAWAY_CRITERION_S <- 2

all_participant_ids <- function() {
  dirs <- list.dirs(fixations_dir, full.names = FALSE, recursive = FALSE)
  str_extract(dirs, "^[0-9]+")
}

participant_ids <- all_participant_ids()

row_levels <- c("Occurrence 2", "Occurrence 1", "Duration scale")

# =============================================================================
# 2. Build one participant's trial timeline
# =============================================================================

# Test-trial fixations (movie + still phases), aligned to each trial's
# still-phase onset (t = 0) using the timing file's startTrial event.
# Joined by trial_num, not trialType string -- occurrence 1 vs 2 share the
# same object-name string and are only disambiguated by trial_num.
load_participant_trial_timeline <- function(pid) {
  if (!file.exists(fix_path(pid)) || !file.exists(timing_path(pid))) return(NULL)

  fix <- read_csv(fix_path(pid), show_col_types = FALSE) |>
    filter(phase %in% c("movie", "still"), str_detect(trial_type, "^(expected|surprise)_"))

  if (nrow(fix) == 0) return(NULL)

  timing <- read_csv(timing_path(pid), show_col_types = FALSE) |>
    filter(event == "startTrial") |>
    transmute(trial_num = trialNum, onset_ms = time * 1000)  # timing file is in seconds

  still_trials <- fix |>
    filter(phase == "still") |>
    distinct(trial_type, trial_num)

  anchors <- still_trials |>
    left_join(timing, by = "trial_num") |>
    select(trial_type, onset_ms)

  timeline <- fix |>
    left_join(anchors, by = "trial_type") |>
    filter(!is.na(onset_ms)) |>
    mutate(
      participant  = pid,
      condition    = ifelse(str_detect(trial_type, "^expected_"), "Expected", "Surprise"),
      occurrence   = str_extract(trial_type, "[0-9]+$"),
      rel_start    = (startT - onset_ms) / 1000,
      rel_end      = (endT - onset_ms) / 1000,
      dur_s        = dur / 1000,
      eccentricity = sqrt((xpos - SCREEN_WIDTH / 2)^2 + (ypos - SCREEN_HEIGHT / 2)^2)
    ) |>
    select(participant, condition, occurrence, trial_type, rel_start, rel_end, dur_s, eccentricity)

  list(timeline = timeline, lookaway = load_lookaway_markers(pid, still_trials))
}

# For each STILL trial, the verbose file logs every on/off-look segment
# (gazeOnOff, startTime/endTime relative to that trial's own start -- same
# t = 0 as the timing file's startTrial event above). If the trial's last
# segment is an off-look of >= LOOKAWAY_CRITERION_S, that's what ended the
# trial (as opposed to hitting the 30s cap while still on-look).
load_lookaway_markers <- function(pid, still_trials) {
  empty <- tibble(condition = character(), occurrence = character(), rel_start = double(), rel_end = double())
  if (!file.exists(verbose_path(pid)) || nrow(still_trials) == 0) return(empty)

  verbose <- read_csv(verbose_path(pid), show_col_types = FALSE)

  map_dfr(seq_len(nrow(still_trials)), function(i) {
    trial_type <- still_trials$trial_type[i]
    last_look <- verbose |> filter(trial == still_trials$trial_num[i]) |> slice_tail(n = 1)

    if (nrow(last_look) == 0 || last_look$gazeOnOff != 0 || last_look$duration < LOOKAWAY_CRITERION_S - 0.1) {
      return(empty)
    }

    tibble(
      condition  = ifelse(str_detect(trial_type, "^expected_"), "Expected", "Surprise"),
      occurrence = str_extract(trial_type, "[0-9]+$"),
      rel_start  = last_look$startTime,
      rel_end    = last_look$endTime
    )
  })
}

# =============================================================================
# 3. Plot one participant
# =============================================================================

plot_participant_timeline <- function(pid) {
  loaded <- load_participant_trial_timeline(pid)
  timeline <- loaded$timeline
  if (is.null(timeline) || nrow(timeline) == 0) {
    message("Skipping ", pid, ": no usable test-trial fixations.")
    return(invisible(NULL))
  }

  min_dur_s  <- min(timeline$dur_s)
  mean_dur_s <- mean(timeline$dur_s)
  max_dur_s  <- max(timeline$dur_s)

  condition_levels <- c("Expected", "Surprise", "Duration scale")

  set.seed(as.integer(pid))  # reproducible jitter
  timeline <- timeline |>
    mutate(
      condition = factor(condition, levels = condition_levels),
      row_label = factor(paste("Occurrence", occurrence), levels = row_levels),
      y_num     = as.numeric(row_label) + runif(n(), -0.2, 0.2)  # jitter so packed fixations don't blur together
    )

  # Where a STILL trial ended by the infant looking away (not the 30s cap):
  # a vertical bar at the moment the trial ended, spanning that row's height
  # so it lines up with the occurrence label on the y-axis.
  lookaway_df <- loaded$lookaway |>
    mutate(
      condition = factor(condition, levels = condition_levels),
      row_label = factor(paste("Occurrence", occurrence), levels = row_levels),
      y_num     = as.numeric(row_label)
    )

  # Min/mean/max laid left-to-right (not stacked) on the same x-axis as the
  # data, so their length is directly comparable. Gaps are just for
  # legibility, not meaningful time.
  pad <- diff(range(c(timeline$rel_start, timeline$rel_end))) * 0.09
  starts <- cumsum(c(0, c(min_dur_s, mean_dur_s) + pad))
  scale_ref <- tibble(
    condition = factor("Duration scale", levels = condition_levels),
    stat      = c("Min", "Mean", "Max"),
    rel_start = starts,
    dur_s     = c(min_dur_s, mean_dur_s, max_dur_s)
  ) |>
    mutate(rel_end = rel_start + dur_s, y_num = as.numeric(factor("Duration scale", levels = row_levels)))

  vline_df    <- data.frame(condition = factor(c("Expected", "Surprise"), levels = condition_levels))
  scale_bg_df <- data.frame(condition = factor("Duration scale", levels = condition_levels))

  # Duration scale facet holds a single y value, which leaves free_y almost
  # no range to size the panel by -- pad it so the panel and its rotated
  # strip label don't get squished to nothing.
  scale_y <- as.numeric(factor("Duration scale", levels = row_levels))
  scale_pad_df <- data.frame(
    condition = factor("Duration scale", levels = condition_levels),
    y_num = c(scale_y - 0.5, scale_y + 0.5)
  )

  p <- ggplot(timeline, aes(x = rel_start, xend = rel_end, y = y_num, yend = y_num,
                            color = occurrence, alpha = eccentricity)) +
    geom_rect(data = scale_bg_df, aes(xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf),
              fill = "grey88", inherit.aes = FALSE) +
    geom_blank(data = scale_pad_df, aes(y = y_num), inherit.aes = FALSE) +
    geom_vline(data = vline_df, aes(xintercept = 0), linetype = "dashed", color = "grey50", inherit.aes = FALSE) +
    geom_segment(linewidth = 0.9, lineend = "butt") +
    geom_segment(data = lookaway_df, linewidth = 2.2, lineend = "butt", color = "black", inherit.aes = FALSE,
                 mapping = aes(x = rel_end, xend = rel_end, y = y_num - 0.4, yend = y_num + 0.4)) +
    geom_segment(data = scale_ref, linewidth = 1.3, lineend = "butt", color = "#2c3e50", inherit.aes = FALSE,
                 mapping = aes(x = rel_start, xend = rel_end, y = y_num, yend = y_num)) +
    geom_text(data = scale_ref, aes(x = (rel_start + rel_end) / 2, y = y_num,
                                     label = paste0(stat, "\n", round(dur_s * 1000), " ms")),
              vjust = -0.4, size = 3.1, inherit.aes = FALSE, lineheight = 0.9) +
    scale_y_continuous(breaks = seq_along(row_levels), labels = row_levels) +
    scale_color_manual(values = c("1" = "#2166ac", "2" = "#b2182b"), name = "Occurrence") +
    scale_alpha_continuous(range = c(1, 0.15), name = "Eccentricity (px)\n(darker = closer to center)") +
    facet_grid(rows = vars(condition), scales = "free_y", space = "free_y") +
    labs(title = paste("Fixation timeline -- participant", pid),
         x = "Time relative to still onset (s)", y = NULL) +
    theme_minimal(base_size = 12) +
    theme(strip.text = element_text(face = "bold"), legend.position = "none")

  out_path <- file.path(out_dir, paste0(pid, "_fixation_timeline.png"))
  ggsave(out_path, p, width = 11, height = 6, dpi = 150)
  invisible(out_path)
}

# =============================================================================
# 4. Run
# =============================================================================

n_written <- 0
n_skipped <- 0

for (pid in participant_ids) {
  out_path <- tryCatch(plot_participant_timeline(pid), error = function(e) {
    message("Skipping ", pid, ": ", conditionMessage(e))
    NULL
  })
  if (is.null(out_path)) {
    n_skipped <- n_skipped + 1
  } else {
    message("Wrote ", out_path)
    n_written <- n_written + 1
  }
}

message("\n", strrep("=", 60))
message("Wrote ", n_written, " plots, skipped ", n_skipped, " -> ", out_dir)
message(strrep("=", 60))
