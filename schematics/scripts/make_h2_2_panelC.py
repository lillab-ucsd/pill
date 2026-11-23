"""
H2.2 schematic, panel C: individual differences in lag slopes.
Cumulative lead across Fam trials = running sum of the pairwise peak offsets from panel B
(2v1, 3v2, 4v3), same sign as panel B: negative = lead. Offsets are whole windows, so values are integers.
Usage: python3 make_h2_2_panelC.py <out.svg>
"""
import sys

OUT = sys.argv[1]

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#ffffff"
F = "font-family='Helvetica, Arial, sans-serif'"

# (label, color, pairwise peak offsets for 2v1, 3v2, 4v3, dash)
profiles = [
    ("Steep, then plateau", "#eb6834", [-2, 0, 0], ""),
    ("Gradual", "#2a78d6", [-1, -1, -1], ""),
    ("No expectation formed", "#1baf7a", [0, 0, 0], "7 5"),
]
def cumulative(offsets):
    out = [0]
    for k in offsets:
        out.append(out[-1] + k)
    return out

W, H = 760, 560
PX0, PX1, PY0, PY1 = 110, 520, 40, 460
YMIN, YMAX = -3.5, .5
X = lambda t: PX0 + (t - 1) / 3 * (PX1 - PX0)
Y = lambda v: PY1 - (v - YMIN) / (YMAX - YMIN) * (PY1 - PY0)

s = []
a = s.append
def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal", extra=""):
    a(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}' {extra}>{t}</text>")

a(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>")
a(f"<rect width='{W}' height='{H}' fill='{SURF}'/>")

for v in range(-3, 1):
    a(f"<line x1='{PX0}' y1='{Y(v):.1f}' x2='{PX1}' y2='{Y(v):.1f}' stroke='{INK2 if v == 0 else GRID}' stroke-width='1'/>")
    text(PX0 - 10, Y(v) + 4, f"{v}".replace("-", "−"), 12, MUTED, "end")
for t in range(1, 5):
    text(X(t), PY1 + 22, f"{t}", 13, MUTED, "middle")
text((PX0 + PX1) / 2, PY1 + 56, "familiarization trial", 18, INK2, "middle")
yc = (PY0 + PY1) / 2
text(PX0 - 10, Y(-3) + 30, "lead ↓", 13, INK2, "end")
text(PX0 - 52, yc, "gaze lead (i.e., windows ahead)", 18, INK2, "middle", extra=f"transform='rotate(-90 {PX0 - 52} {yc})'")

for name, col, offs, dash in profiles:
    vals = cumulative(offs)
    pts = " ".join(f"{X(t + 1):.1f},{Y(v):.1f}" for t, v in enumerate(vals))
    a(f"<polyline points='{pts}' fill='none' stroke='{col}' stroke-width='2.5' stroke-dasharray='{dash}' stroke-linejoin='round'/>")
for name, col, offs, dash in profiles:
    vals = cumulative(offs)
    for t, v in enumerate(vals):
        a(f"<circle cx='{X(t + 1):.1f}' cy='{Y(v):.1f}' r='6' fill='{col}' stroke='{SURF}' stroke-width='2'/>")
    text(PX1 + 16, Y(vals[-1]) + 5, name, 14, INK, weight="bold")

a("</svg>")
open(OUT, "w").write("\n".join(s))
