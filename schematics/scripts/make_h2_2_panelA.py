"""
H2.2 schematic, panel A only: windowed fixation density on consecutive Fam trials,
drawn over real frames from the support familiarization video (ball rolls along table).
Only the windows are labeled; titles and other labels are added separately.
Gaze blobs are illustrative; ball x positions were tracked from support_fam.mp4.
Usage: python3 make_h2_2_panelA.py <repo root> <out.svg> [expectation|no_expectation]
"""
import base64, os, subprocess, sys, tempfile

ROOT, OUT = sys.argv[1], sys.argv[2]
PROFILE = sys.argv[3] if len(sys.argv) > 3 else "expectation"
VIDEO = os.path.join(ROOT, "experiment/stimuli/pill_stimuli/support/support_fam.mp4")

INK, GRID, SURF = "#0b0b0b", "#e4e3df", "#fcfcfb"
HEAT_IN, HEAT_OUT = "#ffd23f", "#eb6834"

# 4 windows of 1.25 s; frame shown is the window midpoint
mids = [1.25, 2.5, 3.75, 5.0]
ball_x = [.07, .31, .59, .88]   # tracked ball x (fraction of width) at each midpoint
BALL_Y = .29
# Fam 1: gaze trails the ball (reactive)
fam1 = [.05, .28, .56, .85]
if PROFILE == "expectation":
    # Fam 2: gaze is where the ball will be one window later (anticipatory); last window = exit point
    fam2 = [.31, .59, .88, .96]
    HL, SHIFT = 3, 1  # highlighted Fam 1 window index; its Fam 2 match is HL - SHIFT
else:
    # Fam 2: still trails the ball, no anticipation, so the best match is the same window
    fam2 = [.04, .27, .55, .84]
    HL, SHIFT = 2, 0
N = len(mids)

frames = []
with tempfile.TemporaryDirectory() as td:
    for t in mids:
        p = os.path.join(td, f"{t}.jpg")
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-ss", str(t), "-i", VIDEO, "-frames:v", "1",
                        "-vf", "scale=640:360", "-q:v", "4", p], check=True)
        frames.append("data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode())

tw, th, gap, x0 = 300, 169, 16, 20
k = tw / 224  # scale for blob/ball sizes
BALL_R = 15 * k
LBL = 34  # space above the top row for window labels
W, H = 2 * x0 + N * tw + (N - 1) * gap, 2 * x0 + LBL + 2 * th + 64
rows = {"Fam 1": x0 + LBL, "Fam 2": x0 + LBL + th + 64}

s = []
a = s.append

a(f"<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>")
a(f"<defs><radialGradient id='heat'><stop offset='0' stop-color='{HEAT_IN}' stop-opacity='0.75'/>"
  f"<stop offset='0.45' stop-color='{HEAT_OUT}' stop-opacity='0.5'/><stop offset='1' stop-color='{HEAT_OUT}' stop-opacity='0'/></radialGradient>"
  f"<marker id='arr' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
  f"<path d='M0,0 L10,5 L0,10 z' fill='{INK}'/></marker>"
  + "".join(f"<clipPath id='c{r}{i}'><rect x='{x0 + i * (tw + gap)}' y='{y}' width='{tw}' height='{th}' rx='4'/></clipPath>"
            for r, y in enumerate(rows.values()) for i in range(N))
  + "</defs>")
a(f"<rect width='{W}' height='{H}' fill='{SURF}'/>")

for i in range(N):
    a(f"<text x='{x0 + i * (tw + gap) + tw / 2}' y='{x0 + 18}' font-family='Helvetica, Arial, sans-serif' "
      f"font-size='18' fill='{INK}' text-anchor='middle'>Window {i + 1}</text>")

for r, (row, y) in enumerate(rows.items()):
    gaze = fam1 if row == "Fam 1" else fam2
    for i in range(N):
        x = x0 + i * (tw + gap)
        img = f"x='{x}' y='{y}' width='{tw}' height='{th}' href='{frames[i]}' xlink:href='{frames[i]}'"
        a(f"<g clip-path='url(#c{r}{i})'>")
        a(f"<image {img}/>")
        a(f"<ellipse cx='{x + gaze[i] * tw:.1f}' cy='{y + BALL_Y * th:.1f}' rx='{34 * k:.1f}' ry='{30 * k:.1f}' fill='url(#heat)'/>")
        a("</g>")
        if ball_x[i] is not None:
            # redraw the ball on top of the density blob so it stays visible
            bx, by = x + ball_x[i] * tw, y + BALL_Y * th + 2 * k
            a(f"<clipPath id='b{r}{i}'><circle cx='{bx:.1f}' cy='{by:.1f}' r='{BALL_R}'/></clipPath>")
            a(f"<image {img} clip-path='url(#b{r}{i})'/>")
            a(f"<circle cx='{bx:.1f}' cy='{by:.1f}' r='{BALL_R}' fill='none' stroke='#ffffff' stroke-width='1.5'/>")
        a(f"<rect x='{x}' y='{y}' width='{tw}' height='{th}' rx='4' fill='none' stroke='{GRID}' stroke-width='1.5'/>")

# highlight the matched pair
hx1 = x0 + HL * (tw + gap); hx2 = x0 + (HL - SHIFT) * (tw + gap)
y1, y2 = rows["Fam 1"], rows["Fam 2"]
a(f"<rect x='{hx1 - 4}' y='{y1 - 4}' width='{tw + 8}' height='{th + 8}' rx='7' fill='none' stroke='{INK}' stroke-width='3'/>")
a(f"<rect x='{hx2 - 4}' y='{y2 - 4}' width='{tw + 8}' height='{th + 8}' rx='7' fill='none' stroke='{INK}' stroke-width='3'/>")
a(f"<path d='M{hx1 + tw / 2},{y1 + th + 6} C{hx1 + tw / 2},{y1 + th + 34} {hx2 + tw / 2},{y2 - 34} {hx2 + tw / 2},{y2 - 8}' "
  f"fill='none' stroke='{INK}' stroke-width='2' marker-end='url(#arr)'/>")

a("</svg>")
open(OUT, "w").write("\n".join(s))
