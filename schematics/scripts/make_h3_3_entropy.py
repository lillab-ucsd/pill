"""
H3.3 schematic: group-level fixation entropy on expected vs unexpected support test trials.
Background = final frame of support_exp.mp4 (ball rests at the table edge) and support_unexp.mp4
(ball floats past the edge). Fixations are simulated; entropy (bits) is computed over the drawn grid.
Row 1: unexpected = high entropy (looking around), expected = low.
Row 2: flipped. Unexpected = low entropy (infants freeze on the ball), expected = high (bored, looking around).
Usage: python3 make_h3_3_entropy.py <repo root> <out.svg>
"""
import base64, math, os, random, subprocess, sys, tempfile

ROOT, OUT = sys.argv[1], sys.argv[2]
STIM = os.path.join(ROOT, "experiment/stimuli/pill_stimuli/support")

INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"
HEAT_IN, HEAT_OUT = "#ffd23f", "#eb6834"
F = "font-family='Helvetica, Arial, sans-serif'"

BALL = (.528, .33)   # ball centre in the final frame of both videos (fraction of width/height)
BALL_R = .056        # ball radius, fraction of width
GX, GY = 4, 3        # entropy grid
N_FIX = 160          # pooled fixations across infants

frames = {}
with tempfile.TemporaryDirectory() as td:
    for cond in ("exp", "unexp"):
        p = os.path.join(td, f"{cond}.jpg")
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-sseof", "-0.1", "-i", os.path.join(STIM, f"support_{cond}.mp4"),
                        "-frames:v", "1", "-vf", "scale=1120:630", "-q:v", "3", p], check=True)
        frames[cond] = "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()

# ---------- simulated fixations ----------
rng = random.Random(7)
def around(cx, cy, sx, sy, n):
    return [(rng.gauss(cx, sx), rng.gauss(cy, sy)) for _ in range(n)]
def uniform(n):
    return [(rng.uniform(.03, .97), rng.uniform(.04, .96)) for _ in range(n)]
def clip(pts):
    return [(min(max(x, .01), .99), min(max(y, .01), .99)) for x, y in pts]

def focused():  # nearly all fixations on the ball
    return clip(around(*BALL, .035, .05, N_FIX - 10) + uniform(10))
def scattered(cond):  # spread over ball, table, floor and empty wall
    edge = (.59, .42) if cond == "exp" else (.43, .42)  # table's right edge
    extra = around(.55, .70, .06, .04, 20) if cond == "unexp" else around(.25, .55, .12, .08, 20)  # shadow / table front
    return clip(around(*BALL, .04, .05, 35) + around(*edge, .04, .04, 25) + extra + uniform(N_FIX - 80))

def entropy(pts):
    counts = {}
    for x, y in pts:
        c = (min(int(x * GX), GX - 1), min(int(y * GY), GY - 1))
        counts[c] = counts.get(c, 0) + 1
    n = len(pts)
    return -sum(k / n * math.log2(k / n) for k in counts.values())

panels = [  # (row, col, condition, fixations)
    (0, 0, "exp", focused()), (0, 1, "unexp", scattered("unexp")),
    (1, 0, "exp", scattered("exp")), (1, 1, "unexp", focused()),
]

# ---------- layout ----------
tw, th, gap, m, top = 560, 315, 24, 20, 40
W, H = 2 * m + 2 * tw + gap, top + 2 * th + gap + m
s = []
a = s.append
def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal", extra=""):
    a(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}' {extra}>{t}</text>")

a(f"<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>")
a(f"<defs><radialGradient id='heat'><stop offset='0' stop-color='{HEAT_IN}' stop-opacity='0.35'/>"
  f"<stop offset='0.5' stop-color='{HEAT_OUT}' stop-opacity='0.18'/><stop offset='1' stop-color='{HEAT_OUT}' stop-opacity='0'/></radialGradient></defs>")
a(f"<rect width='{W}' height='{H}' fill='{SURF}'/>")
for c, name in enumerate(("Expected", "Unexpected")):
    text(m + c * (tw + gap) + tw / 2, top - 14, name, 18, anchor="middle", weight="bold")

for r, c, cond, pts in panels:
    x0, y0 = m + c * (tw + gap), top + r * (th + gap)
    href = frames[cond]
    img = f"x='{x0}' y='{y0}' width='{tw}' height='{th}' href='{href}' xlink:href='{href}'"
    a(f"<clipPath id='p{r}{c}'><rect x='{x0}' y='{y0}' width='{tw}' height='{th}' rx='5'/></clipPath>")
    a(f"<g clip-path='url(#p{r}{c})'><image {img}/>")
    for x, y in pts:  # density: overlapping translucent blobs
        a(f"<circle cx='{x0 + x * tw:.1f}' cy='{y0 + y * th:.1f}' r='30' fill='url(#heat)'/>")
    # ball redrawn on top so it stays visible under dense looking
    bx, by, br = x0 + BALL[0] * tw, y0 + BALL[1] * th, BALL_R * tw
    a(f"<clipPath id='b{r}{c}'><circle cx='{bx:.1f}' cy='{by:.1f}' r='{br:.1f}'/></clipPath>")
    a(f"<image {img} clip-path='url(#b{r}{c})'/>")
    a(f"<circle cx='{bx:.1f}' cy='{by:.1f}' r='{br:.1f}' fill='none' stroke='#ffffff' stroke-width='1.5'/>")
    for x, y in pts:  # individual fixations
        a(f"<circle cx='{x0 + x * tw:.1f}' cy='{y0 + y * th:.1f}' r='2.6' fill='{INK}' fill-opacity='0.75' stroke='#ffffff' stroke-width='0.8'/>")
    for i in range(1, GX):  # entropy grid
        a(f"<line x1='{x0 + i * tw / GX:.1f}' y1='{y0}' x2='{x0 + i * tw / GX:.1f}' y2='{y0 + th}' stroke='#ffffff' stroke-opacity='0.45' stroke-width='1'/>")
    for j in range(1, GY):
        a(f"<line x1='{x0}' y1='{y0 + j * th / GY:.1f}' x2='{x0 + tw}' y2='{y0 + j * th / GY:.1f}' stroke='#ffffff' stroke-opacity='0.45' stroke-width='1'/>")
    a("</g>")
    a(f"<rect x='{x0}' y='{y0}' width='{tw}' height='{th}' rx='5' fill='none' stroke='#e4e3df' stroke-width='1.5'/>")
    a(f"<rect x='{x0 + tw - 148}' y='{y0 + 12}' width='136' height='32' rx='6' fill='{SURF}' fill-opacity='0.92'/>")
    text(x0 + tw - 80, y0 + 34, f"H = {entropy(pts):.1f} bits", 17, INK, "middle", "bold")
    print(r, c, cond, round(entropy(pts), 2))

a("</svg>")
open(OUT, "w").write("\n".join(s))
