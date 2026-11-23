import math, sys

OUT = sys.argv[1]
W, H = 1280, 790
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, AQUA, HEAT = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
F = "font-family='Helvetica, Arial, sans-serif'"

s = []
a = s.append
a(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>")
a(f"<defs><radialGradient id='heat'><stop offset='0' stop-color='{HEAT}' stop-opacity='0.95'/>"
  f"<stop offset='0.55' stop-color='{HEAT}' stop-opacity='0.45'/><stop offset='1' stop-color='{HEAT}' stop-opacity='0'/></radialGradient>"
  f"<marker id='arr' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
  f"<path d='M0,0 L10,5 L0,10 z' fill='{INK2}'/></marker></defs>")
a(f"<rect width='{W}' height='{H}' fill='{SURF}'/>")

def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal", extra=""):
    a(f"<text x='{x}' y='{y}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}' {extra}>{t}</text>")

# Title
text(40, 44, "H2.2 · Do individual infants form expectations at different rates?", 22, weight="bold")
text(40, 70, "If an infant forms an expectation, gaze on each Fam trial shifts earlier relative to the previous Fam trial; "
     "the rate of that shift differs across infants.", 14, INK2)

# ---------- Panel A: windowed fixation density ----------
text(40, 116, "A", 18, weight="bold")
text(64, 116, "Windowed fixation density maps, consecutive Fam trials (illustrated: Fam 1 vs Fam 2)", 15, weight="bold")
tw, th, gap, x0 = 140, 78, 16, 130
obj = [.15, .35, .55, .80, .80, .80]           # object position per window; event at window 4 (n)
gaze = {"Fam 1": obj, "Fam 2": [.35, .55, .80, .80, .80, .80]}  # Fam 2 arrives one window earlier
rows = {"Fam 1": 150, "Fam 2": 268}
for i in range(6):
    lab = ["n−3", "n−2", "n−1", "n", "n+1", "n+2"][i]
    text(x0 + i * (tw + gap) + tw / 2, 142, f"window {lab}", 12, INK2, "middle")
for row, y in rows.items():
    text(x0 - 14, y + th / 2 + 5, row, 14, anchor="end", weight="bold")
    for i in range(6):
        x = x0 + i * (tw + gap)
        a(f"<rect x='{x}' y='{y}' width='{tw}' height='{th}' rx='4' fill='#ffffff' stroke='{GRID}' stroke-width='1.5'/>")
        gx = x + gaze[row][i] * tw
        a(f"<circle cx='{gx}' cy='{y + th / 2}' r='26' fill='url(#heat)'/>")
        ox = x + obj[i] * tw
        a(f"<rect x='{ox - 7}' y='{y + th / 2 - 7}' width='14' height='14' rx='2' fill='none' stroke='{INK}' stroke-width='2'/>")
        if i == 3:
            a(f"<text x='{ox}' y='{y + 16}' {F} font-size='11' fill='{INK2}' text-anchor='middle'>event</text>")
# highlight matched maps
hx1 = x0 + 3 * (tw + gap); hx2 = x0 + 2 * (tw + gap)
a(f"<rect x='{hx1 - 3}' y='{rows['Fam 1'] - 3}' width='{tw + 6}' height='{th + 6}' rx='6' fill='none' stroke='{INK}' stroke-width='2.5'/>")
a(f"<rect x='{hx2 - 3}' y='{rows['Fam 2'] - 3}' width='{tw + 6}' height='{th + 6}' rx='6' fill='none' stroke='{INK}' stroke-width='2.5'/>")
a(f"<path d='M{hx1 + tw / 2},{rows['Fam 1'] + th + 4} C{hx1 + tw / 2},{rows['Fam 1'] + th + 26} {hx2 + tw / 2},{rows['Fam 2'] - 26} {hx2 + tw / 2},{rows['Fam 2'] - 6}' "
  f"fill='none' stroke='{INK2}' stroke-width='2' marker-end='url(#arr)'/>")
text(hx2 + 16, 244, "Fam 1 window n  ≈  Fam 2 window n−1", 13, anchor="end", weight="bold")
text(hx2 + 16, 260, "Fam 2 is shifted one window earlier", 13, INK2, "end")
# legend for panel A
ly = 372
a(f"<circle cx='{x0 + 8}' cy='{ly - 4}' r='9' fill='url(#heat)'/>")
text(x0 + 24, ly, "fixation density", 12, INK2)
a(f"<rect x='{x0 + 140}' y='{ly - 11}' width='12' height='12' rx='2' fill='none' stroke='{INK}' stroke-width='2'/>")
text(x0 + 160, ly, "object position (same on every Fam trial)", 12, INK2)

a(f"<line x1='40' y1='398' x2='{W - 40}' y2='398' stroke='{GRID}' stroke-width='1'/>")

# ---------- Panel B: cross-correlation ----------
text(40, 432, "B", 18, weight="bold")
text(64, 432, "Time-shifted correlation, Fam n vs Fam n−1", 15, weight="bold")
bx0, bx1, by0, by1 = 110, 540, 470, 690
X = lambda k: bx0 + (k + 3) / 6 * (bx1 - bx0)
Y = lambda r: by1 - r * (by1 - by0)
for r in (0, .25, .5, .75, 1):
    a(f"<line x1='{bx0}' y1='{Y(r)}' x2='{bx1}' y2='{Y(r)}' stroke='{GRID}' stroke-width='1'/>")
    text(bx0 - 8, Y(r) + 4, f"{r:g}", 11, MUTED, "end")
for k in range(-3, 4):
    text(X(k), by1 + 18, f"{k:+d}" if k else "0", 11, MUTED, "middle")
text((bx0 + bx1) / 2, by1 + 40, "offset of Fam n relative to Fam n−1 (windows)", 12, INK2, "middle")
text(bx0 - 40, (by0 + by1) / 2, "correlation of density maps (r)", 12, INK2, "middle",
     extra=f"transform='rotate(-90 {bx0 - 40} {(by0 + by1) / 2})'")
a(f"<line x1='{X(0)}' y1='{by0 - 6}' x2='{X(0)}' y2='{by1}' stroke='{INK2}' stroke-width='1.5' stroke-dasharray='5 4'/>")
text(X(0) + 6, by0 + 4, "0 = no shift", 11, INK2)
pts = [(k / 8, .12 + .72 * math.exp(-((k / 8 + 1) ** 2) / 1.1)) for k in range(-24, 25)]
a(f"<polyline points='{' '.join(f'{X(k):.1f},{Y(r):.1f}' for k, r in pts)}' fill='none' stroke='{BLUE}' stroke-width='2.5' stroke-linejoin='round'/>")
a(f"<line x1='{X(-1)}' y1='{Y(.84)}' x2='{X(-1)}' y2='{by1}' stroke='{BLUE}' stroke-width='1' stroke-dasharray='2 3'/>")
a(f"<circle cx='{X(-1)}' cy='{Y(.84)}' r='6' fill='{BLUE}' stroke='{SURF}' stroke-width='2'/>")
text(X(-1) - 10, Y(.84) - 14, "peak at −1 window", 12, INK, "end", "bold")
text(X(-1) - 10, Y(.84) + 2, "= lead for this trial pair", 12, INK2, "end")
text(bx0, by1 + 66, "Negative peak offset = gaze arrives earlier than on the previous", 12, INK2)
text(bx0, by1 + 82, "trial (anticipation). One lead value per pair: 2v1, 3v2, 4v3.", 12, INK2)

# ---------- Panel C: individual lead trajectories ----------
text(640, 432, "C", 18, weight="bold")
text(664, 432, "Individual differences in rate of expectation formation", 15, weight="bold")
cx0, cx1, cy0, cy1 = 720, 1080, 470, 690
CX = lambda t: cx0 + (t - 1) / 3 * (cx1 - cx0)
CY = lambda v: cy1 - v / 3.5 * (cy1 - cy0)
for v in range(0, 4):
    a(f"<line x1='{cx0}' y1='{CY(v)}' x2='{cx1}' y2='{CY(v)}' stroke='{GRID}' stroke-width='1'/>")
    text(cx0 - 8, CY(v) + 4, f"{v}", 11, MUTED, "end")
for t in range(1, 5):
    text(CX(t), cy1 + 18, f"Fam {t}", 11, MUTED, "middle")
text((cx0 + cx1) / 2, cy1 + 40, "familiarization trial", 12, INK2, "middle")
text(cx0 - 34, (cy0 + cy1) / 2, "cumulative lead (windows)", 12, INK2, "middle",
     extra=f"transform='rotate(-90 {cx0 - 34} {(cy0 + cy1) / 2})'")
series = [
    ("Steep, then plateau", ORANGE, [0, 2.5, 3, 3], "", -6),
    ("Gradual", BLUE, [0, .9, 1.8, 2.7], "", 8),
    ("No expectation formed", AQUA, [0, .2, .1, .2], "6 4", 0),
]
for name, col, vals, dash, dy in series:
    pts = " ".join(f"{CX(t + 1):.1f},{CY(v):.1f}" for t, v in enumerate(vals))
    a(f"<polyline points='{pts}' fill='none' stroke='{col}' stroke-width='2.5' stroke-dasharray='{dash}' stroke-linejoin='round'/>")
    for t, v in enumerate(vals):
        a(f"<circle cx='{CX(t + 1):.1f}' cy='{CY(v):.1f}' r='5' fill='{col}' stroke='{SURF}' stroke-width='2'/>")
    text(cx1 + 12, CY(vals[-1]) + 4 + dy, name, 12, INK, weight="bold")
text(cx0, cy1 + 66, "Cumulative lead = running sum of the pairwise peak offsets in B.", 12, INK2)
text(cx0, cy1 + 82, "Each infant's lag slope = the shape/slope of their trajectory.", 12, INK2)

a("</svg>")
open(OUT, "w").write("\n".join(s))
