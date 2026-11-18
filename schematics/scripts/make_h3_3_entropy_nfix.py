"""
H3.3 caveat figure: why fixation entropy is hard to compare across individual infants.
Plug-in entropy (H = -sum p log2 p over a 4x3 grid) depends on the number of fixations:
with n fixations it can never exceed log2(n), and it is biased low until n is large relative to 12 cells.
Top: one "explorer" (looks everywhere equally; true H = 3.58) sampled with 4, 8, 16, 48 fixations
(for each n, the simulated draw closest to the mean H is shown).
Bottom: mean observed H (10th-90th percentile band) by number of fixations for the explorer and a
"focused" looker (60% on one cell; true H = 2.35), from simulation.
Usage: python3 make_h3_3_entropy_nfix.py <out.svg>
"""
import math, random, sys

OUT = sys.argv[1]

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, CELLLINE = "#2a78d6", "#eb6834", "#c9c8c2"
F = "font-family='Helvetica, Arial, sans-serif'"
GX, GY = 4, 3
NC = GX * GY

rng = random.Random(1)
def H(counts):
    n = sum(counts)
    return -sum(k / n * math.log2(k / n) for k in counts if k) + 0.0
P = {"Explorer": [1 / NC] * NC, "Focused": [.6 if i == 6 else .4 / (NC - 1) for i in range(NC)]}
TRUE = {k: H([p * 1e6 for p in v]) for k, v in P.items()}
def draw(probs, n):
    c = [0] * NC
    for i in rng.choices(range(NC), probs, k=n):
        c[i] += 1
    return c

NS = [2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32, 40, 50, 64, 80, 100]
R = 3000
stats = {}
for name, probs in P.items():
    rows = []
    for n in NS:
        hs = sorted(H(draw(probs, n)) for _ in range(R))
        rows.append((n, sum(hs) / R, hs[int(.1 * R)], hs[int(.9 * R) - 1]))
    stats[name] = rows
mean_at = lambda name, n: next(m for k, m, _, _ in stats[name] if k == n)

# example grids: explorer at several n, draw closest to the mean H
EX_N = [4, 8, 16, 48]
examples = []
for n in EX_N:
    target = sum(H(draw(P["Explorer"], n)) for _ in range(R)) / R
    best = min((draw(P["Explorer"], n) for _ in range(400)), key=lambda c: abs(H(c) - target))
    examples.append((n, best))

# ---------- layout ----------
m, gw, gap = 20, 240, 34
gh = gw * 9 / 16
cw, ch = gw / GX, gh / GY
W = 2 * m + len(EX_N) * gw + (len(EX_N) - 1) * gap
PX0, PX1 = 90, W - 220
PY0 = m + gh + 120
PY1 = PY0 + 330
H_ = PY1 + 80

s = []
a = s.append
def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal", extra=""):
    a(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}' {extra}>{t}</text>")

a(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H_:.0f}' viewBox='0 0 {W} {H_:.0f}'>")
a(f"<rect width='{W}' height='{H_:.0f}' fill='{SURF}'/>")

for e, (n, counts) in enumerate(examples):
    x0, y0 = m + e * (gw + gap), m
    a(f"<rect x='{x0}' y='{y0}' width='{gw}' height='{gh:.1f}' fill='#ffffff'/>")
    for i, k in enumerate(counts):
        if k:
            c, r = i % GX, i // GX
            a(f"<rect x='{x0 + c * cw:.1f}' y='{y0 + r * ch:.1f}' width='{cw:.1f}' height='{ch:.1f}' fill='{BLUE}' fill-opacity='{0.08 + 0.72 * k / n:.2f}'/>")
    for i in range(1, GX):
        a(f"<line x1='{x0 + i * cw:.1f}' y1='{y0}' x2='{x0 + i * cw:.1f}' y2='{y0 + gh:.1f}' stroke='{CELLLINE}' stroke-width='1.2'/>")
    for j in range(1, GY):
        a(f"<line x1='{x0}' y1='{y0 + j * ch:.1f}' x2='{x0 + gw}' y2='{y0 + j * ch:.1f}' stroke='{CELLLINE}' stroke-width='1.2'/>")
    a(f"<rect x='{x0}' y='{y0}' width='{gw}' height='{gh:.1f}' fill='none' stroke='{INK2}' stroke-width='1.5'/>")
    for i, k in enumerate(counts):
        c, r = i % GX, i // GX
        for _ in range(k):
            fx, fy = x0 + (c + rng.uniform(.15, .85)) * cw, y0 + (r + rng.uniform(.18, .82)) * ch
            a(f"<circle cx='{fx:.1f}' cy='{fy:.1f}' r='2.8' fill='{INK}' stroke='#ffffff' stroke-width='0.8'/>")
    text(x0 + gw / 2, y0 + gh + 26, f"{n} fixations", 14, INK2, "middle")
    text(x0 + gw / 2, y0 + gh + 50, f"H = {H(counts):.2f} bits", 17, INK, "middle", "bold")

# ---------- chart ----------
lx = lambda n: math.log(n)
X = lambda n: PX0 + (lx(n) - lx(2)) / (lx(100) - lx(2)) * (PX1 - PX0)
Y = lambda h: PY1 - h / 4 * (PY1 - PY0)
for h in range(0, 5):
    a(f"<line x1='{PX0}' y1='{Y(h):.1f}' x2='{PX1}' y2='{Y(h):.1f}' stroke='{INK2 if h == 0 else GRID}' stroke-width='1'/>")
    text(PX0 - 10, Y(h) + 4, f"{h}", 12, MUTED, "end")
for n in (2, 4, 8, 16, 32, 64, 100):
    text(X(n), PY1 + 22, f"{n}", 12, MUTED, "middle")
text((PX0 + PX1) / 2, PY1 + 50, "number of fixations (log scale)", 14, INK2, "middle")
yc = (PY0 + PY1) / 2
text(PX0 - 46, yc, "observed entropy H (bits)", 14, INK2, "middle", extra=f"transform='rotate(-90 {PX0 - 46} {yc})'")

# ceiling: H can't exceed log2(n)
ceil = [n for n in NS if math.log2(n) <= 4]
a(f"<polyline points='{' '.join(f'{X(n):.1f},{Y(math.log2(n)):.1f}' for n in ceil)}' fill='none' stroke='{MUTED}' stroke-width='1.5' stroke-dasharray='3 4'/>")
text(X(13), Y(math.log2(13)) - 10, "ceiling: log₂(n)", 12, MUTED, "end")

for name, col in (("Explorer", BLUE), ("Focused", ORANGE)):
    rows = stats[name]
    band = [f"{X(n):.1f},{Y(hi):.1f}" for n, _, _, hi in rows] + [f"{X(n):.1f},{Y(lo):.1f}" for n, _, lo, _ in reversed(rows)]
    a(f"<polygon points='{' '.join(band)}' fill='{col}' fill-opacity='0.14'/>")
    a(f"<line x1='{PX0}' y1='{Y(TRUE[name]):.1f}' x2='{PX1}' y2='{Y(TRUE[name]):.1f}' stroke='{col}' stroke-width='1.2' stroke-dasharray='6 4'/>")
    a(f"<polyline points='{' '.join(f'{X(n):.1f},{Y(mu):.1f}' for n, mu, _, _ in rows)}' fill='none' stroke='{col}' stroke-width='2.5' stroke-linejoin='round'/>")
    text(PX1 + 12, Y(TRUE[name]) + 5, f"{name} (true H = {TRUE[name]:.2f})", 14, INK, weight="bold")

# the crossover: a short-looking explorer scores below a long-looking focused infant
for name, n, col, dy in (("Explorer", 4, BLUE, 26), ("Focused", 40, ORANGE, 30)):
    h = mean_at(name, n)
    a(f"<circle cx='{X(n):.1f}' cy='{Y(h):.1f}' r='8' fill='{col}' stroke='{SURF}' stroke-width='2.5'/>")
    text(X(n), Y(h) + dy, f"{name.lower()}, {n} fixations: H ≈ {h:.1f}", 13, INK, "middle", "bold",
         extra=f"stroke='{SURF}' stroke-width='5' stroke-linejoin='round' paint-order='stroke'")

a("</svg>")
open(OUT, "w").write("\n".join(s))
print({k: round(v, 2) for k, v in TRUE.items()}, "explorer@4", round(mean_at("Explorer", 4), 2), "focused@40", round(mean_at("Focused", 40), 2))
