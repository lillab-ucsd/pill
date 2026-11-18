"""
H2.2 schematic, panel B: how one lead value is computed for a trial pair (Fam n vs Fam n-1).
Each window's fixation density map is compared with the previous trial's maps at offset k:
Fam n window w vs Fam n-1 window w - k, Pearson r between maps, averaged over overlapping windows.
The k with the highest mean r is the pair's lead (negative = lead, 0 = none, positive = lag).
Gaze positions match make_h2_2_panelA.py; maps are Gaussians on a grid, so the r values are computed, not drawn.
Usage: python3 make_h2_2_panelB.py <repo root> <out.svg> [expectation|no_expectation]
"""
import base64, math, os, subprocess, sys, tempfile

ROOT, OUT = sys.argv[1], sys.argv[2]
PROFILE = sys.argv[3] if len(sys.argv) > 3 else "expectation"
VIDEO = os.path.join(ROOT, "experiment/stimuli/pill_stimuli/support/support_fam.mp4")

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
HEAT_IN, HEAT_OUT, LINE = "#ffd23f", "#eb6834", "#2a78d6"
F = "font-family='Helvetica, Arial, sans-serif'"

# same windows and gaze as panel A
mids = [1.25, 2.5, 3.75, 5.0]
BALL_Y = .29
fam1 = [.05, .28, .56, .85]
fam2 = [.31, .59, .88, .96] if PROFILE == "expectation" else [.04, .27, .55, .84]
N = len(mids)
OFFSETS = [-2, -1, 0, 1, 2]
SHOWN = [-1, 0, 1]  # offsets illustrated as sliding strips

# ---------- compute map correlations ----------
GW, GH, SIG = 64, 36, .07
def density(gx):
    return [math.exp(-(((i + .5) / GW - gx) ** 2 + (((j + .5) / GH - BALL_Y) * 9 / 16) ** 2) / (2 * SIG ** 2))
            for j in range(GH) for i in range(GW)]
def pearson(u, v):
    mu, mv = sum(u) / len(u), sum(v) / len(v)
    cov = sum((x - mu) * (y - mv) for x, y in zip(u, v))
    return cov / math.sqrt(sum((x - mu) ** 2 for x in u) * sum((y - mv) ** 2 for y in v))
m1, m2 = [density(g) for g in fam1], [density(g) for g in fam2]
def pairs(k):  # (Fam n window, Fam n-1 window) index pairs at offset k
    return [(w, w - k) for w in range(N) if 0 <= w - k < N]
mean_r = {k: sum(pearson(m2[w], m1[v]) for w, v in pairs(k)) / len(pairs(k)) for k in OFFSETS}
PEAK = max(OFFSETS, key=lambda k: mean_r[k])
print({k: round(r, 2) for k, r in mean_r.items()}, "peak", PEAK)

frames = []
with tempfile.TemporaryDirectory() as td:
    for t in mids:
        p = os.path.join(td, f"{t}.jpg")
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-ss", str(t), "-i", VIDEO, "-frames:v", "1",
                        "-vf", "scale=320:180", "-q:v", "4", p], check=True)
        frames.append("data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode())

# ---------- layout ----------
tw, th, gap = 112, 63, 8
step = tw + gap
L0 = 110                      # left edge of the strip area
S1 = L0 + step                # Fam 1 strip start (room for a one-window left shift)
RTXT = L0 + (N + 2) * step + 6
BLK_H, BLK_GAP, TOP = 2 * th + 12, 52, 40
PX0, PX1 = RTXT + 250, RTXT + 570
W = PX1 + 40
H = TOP + len(SHOWN) * BLK_H + (len(SHOWN) - 1) * BLK_GAP + 40

s = []
a = s.append
def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal"):
    a(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'>{t}</text>")
def sign(k):
    return f"{k:+d}".replace("-", "−") if k else "0"

a(f"<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>")
a(f"<defs><radialGradient id='heat'><stop offset='0' stop-color='{HEAT_IN}' stop-opacity='0.85'/>"
  f"<stop offset='0.45' stop-color='{HEAT_OUT}' stop-opacity='0.6'/><stop offset='1' stop-color='{HEAT_OUT}' stop-opacity='0'/></radialGradient></defs>")
a(f"<rect width='{W}' height='{H}' fill='{SURF}'/>")

cid = 0
def tile(x, y, w, gaze, dim):
    global cid
    cid += 1
    op = .35 if dim else 1
    href = frames[w]
    a(f"<g opacity='{op}'><clipPath id='t{cid}'><rect x='{x}' y='{y}' width='{tw}' height='{th}' rx='3'/></clipPath>")
    a(f"<g clip-path='url(#t{cid})'><image x='{x}' y='{y}' width='{tw}' height='{th}' href='{href}' xlink:href='{href}' opacity='0.45'/>")
    a(f"<ellipse cx='{x + gaze * tw:.1f}' cy='{y + BALL_Y * th:.1f}' rx='{tw * .16:.1f}' ry='{tw * .14:.1f}' fill='url(#heat)'/></g>")
    a(f"<rect x='{x}' y='{y}' width='{tw}' height='{th}' rx='3' fill='none' stroke='{GRID}' stroke-width='1.2'/></g>")

for b, k in enumerate(SHOWN):
    y0 = TOP + b * (BLK_H + BLK_GAP)
    y2 = y0 + th + 12
    paired1 = {v for _, v in pairs(k)}
    paired2 = {w for w, _ in pairs(k)}
    text(20, y0 + BLK_H / 2 + 6, f"k = {sign(k)}", 16, weight="bold")
    text(L0 - 8, y0 + th / 2 + 4, "Fam 1", 12, INK2, "end")
    text(L0 - 8, y2 + th / 2 + 4, "Fam 2", 12, INK2, "end")
    for w in range(N):
        tile(S1 + w * step, y0, w, fam1[w], w not in paired1)
        tile(S1 + (w - k) * step, y2, w, fam2[w], w not in paired2)
    for w, v in pairs(k):  # link compared maps
        x = S1 + v * step + tw / 2
        a(f"<line x1='{x}' y1='{y0 + th + 1}' x2='{x}' y2='{y2 - 1}' stroke='{INK}' stroke-width='2'/>")
    text(RTXT, y0 + BLK_H / 2 + 6, f"mean r = {mean_r[k]:.2f}".replace("-", "−"), 15, INK, weight="bold" if k == PEAK else "normal")
    if k == PEAK:
        a(f"<rect x='10' y='{y0 - 10}' width='{RTXT + 160}' height='{BLK_H + 20}' rx='8' "
          f"fill='none' stroke='{INK}' stroke-width='2.5'/>")

# ---------- offset curve ----------
PY0, PY1 = TOP + 10, H - 110
X = lambda k: PX0 + (k - OFFSETS[0]) / (OFFSETS[-1] - OFFSETS[0]) * (PX1 - PX0)
RMIN = -.25
Y = lambda r: PY1 - (r - RMIN) / (1 - RMIN) * (PY1 - PY0)
for r in (RMIN, 0, .25, .5, .75, 1):
    a(f"<line x1='{PX0}' y1='{Y(r):.1f}' x2='{PX1}' y2='{Y(r):.1f}' stroke='{INK2 if r == 0 else GRID}' stroke-width='1'/>")
    text(PX0 - 8, Y(r) + 4, f"{r:g}".replace("-", "−"), 11, MUTED, "end")
for k in OFFSETS:
    text(X(k), PY1 + 20, sign(k), 12, MUTED, "middle")
a(f"<line x1='{X(0)}' y1='{PY0 - 6}' x2='{X(0)}' y2='{PY1}' stroke='{INK2}' stroke-width='1.2' stroke-dasharray='5 4'/>")
text((PX0 + PX1) / 2, PY1 + 44, "offset k (windows)", 13, INK2, "middle")
text(X(-1.5), PY1 + 66, "← lead", 13, INK2, "middle")
text(X(1.5), PY1 + 66, "lag →", 13, INK2, "middle")
text(PX0 - 36, (PY0 + PY1) / 2, "mean map r", 13, INK2, "middle")
s[-1] = s[-1].replace("<text ", f"<text transform='rotate(-90 {PX0 - 36} {(PY0 + PY1) / 2})' ", 1)
pts = " ".join(f"{X(k):.1f},{Y(mean_r[k]):.1f}" for k in OFFSETS)
a(f"<polyline points='{pts}' fill='none' stroke='{LINE}' stroke-width='2' stroke-linejoin='round'/>")
for k in OFFSETS:
    pk = k == PEAK
    a(f"<circle cx='{X(k):.1f}' cy='{Y(mean_r[k]):.1f}' r='{8 if pk else 5}' fill='{LINE if pk or k in SHOWN else SURF}' "
      f"stroke='{LINE if not pk else SURF}' stroke-width='2'/>")
text(X(PEAK), Y(mean_r[PEAK]) - 16, f"lead = {sign(PEAK)}" if PEAK < 0 else ("no lead (0)" if PEAK == 0 else f"lag = {sign(PEAK)}"),
     14, INK, "middle", "bold")

a("</svg>")
open(OUT, "w").write("\n".join(s))
