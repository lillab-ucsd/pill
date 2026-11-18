"""
H2.3 schematic: speed of expectation formation vs strength of the violation-of-expectation effect.
x = early lead: peak offset k for Fam 2 vs Fam 1 (negative = lead; same sign as H2.2 B/C). A linear slope over
Fam 1-4 is not used because it ranks a steep-then-plateau kid below a gradual one.
VOE effect = looking time to unexpected - expected outcome. Prediction: the fastest expectation-formers
(most negative early lead) show the largest VOE effect.
Simulated participants, for illustration only; the three highlighted kids are the panel C profiles.
Usage: python3 make_h2_3_plot.py <out.svg>
"""
import random, sys

OUT = sys.argv[1]

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#ffffff"
OTHER = "#b5b4ae"
F = "font-family='Helvetica, Arial, sans-serif'"

def early_lead(offsets):  # peak offset for the first trial pair (Fam 2 vs Fam 1)
    return offsets[0]

# (label, color, pairwise offsets as in panel C, VOE effect in s)
kids = [
    ("Steep, then plateau", "#eb6834", [-2, 0, 0], 4.3),
    ("Gradual", "#2a78d6", [-1, -1, -1], 2.3),
    ("No expectation formed", "#1baf7a", [0, 0, 0], 0.2),
]
kids = [(n, c, early_lead(o), v) for n, c, o, v in kids]

random.seed(3)
others = []
for _ in range(30):
    x = random.uniform(-2.3, 0.15)  # continuous, e.g. averaged across event types
    others.append((x, 0.3 - 1.9 * x + random.gauss(0, .8)))

pts = others + [(x, v) for _, _, x, v in kids]
mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
b = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
a0 = my - b * mx

W, H = 760, 560
PX0, PX1, PY0, PY1 = 110, 520, 40, 460
XMIN, XMAX, YMIN, YMAX = -2.5, .5, -1.5, 6
X = lambda v: PX0 + (v - XMIN) / (XMAX - XMIN) * (PX1 - PX0)
Y = lambda v: PY1 - (v - YMIN) / (YMAX - YMIN) * (PY1 - PY0)
minus = lambda v: f"{v:g}".replace("-", "−")

s = []
add = s.append
def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal", extra=""):
    add(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}' {extra}>{t}</text>")

add(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>")
add(f"<rect width='{W}' height='{H}' fill='{SURF}'/>")

for v in (-1, 0, 2, 4, 6):
    add(f"<line x1='{PX0}' y1='{Y(v):.1f}' x2='{PX1}' y2='{Y(v):.1f}' stroke='{INK2 if v == 0 else GRID}' stroke-width='1'/>")
    text(PX0 - 10, Y(v) + 4, minus(v), 12, MUTED, "end")
for v in (-2, -1, 0):
    add(f"<line x1='{X(v):.1f}' y1='{PY0}' x2='{X(v):.1f}' y2='{PY1}' stroke='{INK2 if v == 0 else GRID}' stroke-width='1' "
        f"{'stroke-dasharray=\"5 4\"' if v == 0 else ''}/>")
    text(X(v), PY1 + 22, minus(v), 12, MUTED, "middle")
# direction labels at the axis ends (left = more anticipation, since negative offset = lead)
def lines(x, y, rows, anchor):
    add(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='15' fill='{INK2}' text-anchor='{anchor}' font-weight='bold'>"
        + "".join(f"<tspan x='{x:.1f}' dy='{0 if i == 0 else 18}'>{r}</tspan>" for i, r in enumerate(rows)) + "</text>")
lines(PX0, PY1 + 52, ["← MORE FAM TRIAL", "ANTICIPATION"], "start")
lines(PX1, PY1 + 52, ["LESS FAM TRIAL →", "ANTICIPATION"], "end")
YL = PX0 - 40
text(YL, PY0, "MORE VOE →", 15, INK2, "end", "bold", extra=f"transform='rotate(-90 {YL} {PY0})'")
text(YL, PY1, "← LESS VOE", 15, INK2, "start", "bold", extra=f"transform='rotate(-90 {YL} {PY1})'")

# predicted relationship
x1, x2 = -2.4, .3
add(f"<line x1='{X(x1):.1f}' y1='{Y(a0 + b * x1):.1f}' x2='{X(x2):.1f}' y2='{Y(a0 + b * x2):.1f}' "
    f"stroke='{INK2}' stroke-width='2'/>")

for x, y in others:
    add(f"<circle cx='{X(x):.1f}' cy='{Y(y):.1f}' r='6' fill='{OTHER}' stroke='{SURF}' stroke-width='2'/>")
for name, col, x, y in kids:
    add(f"<circle cx='{X(x):.1f}' cy='{Y(y):.1f}' r='9' fill='{col}' stroke='{SURF}' stroke-width='2.5'/>")
for name, col, x, y in kids:  # labels last, with a surface halo so dots and the fit line don't cut through them
    text(X(x) + 14, Y(y) + 5, name, 14, INK, weight="bold",
         extra=f"stroke='{SURF}' stroke-width='5' stroke-linejoin='round' paint-order='stroke'")

add("</svg>")
open(OUT, "w").write("\n".join(s))
print("kid early leads", [(n, round(x, 2)) for n, _, x, _ in kids], "fit slope", round(b, 2))
