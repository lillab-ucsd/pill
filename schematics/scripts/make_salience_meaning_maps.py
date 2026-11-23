"""
Schematic: simulated priority maps over the final frame of support_unexp.mp4 (ball floating past the table edge).
1. Visual salience: computed from the frame with a simple low-level model: local luminance-edge density
   (blurred gradient magnitude) plus color center-surround contrast (red/green, blue/yellow), so it lights up
   wherever low-level contrast is high (checkerboard floor, box edges, ball, shadow) regardless of meaning.
2. Semantic meaning: hand-placed (simulated) map weighting the regions that carry the event's meaning:
   the ball, the empty space where support is missing, the table edge it left, the supporting wall/table
   itself (less than the ball), and its shadow.
3. Salience + meaning: equal-weight average of the two normalized maps.
Usage: python3 make_salience_meaning_maps.py <pill_root> <out.svg>
"""
import base64, io, subprocess, sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

ROOT, OUT = sys.argv[1], sys.argv[2]
INK2, SURF = "#52514e", "#ffffff"
F = "font-family='Helvetica, Arial, sans-serif'"
MW, MH = 384, 216  # map resolution

raw = subprocess.run(["ffmpeg", "-v", "quiet", "-sseof", "-0.1", "-i",
                      f"{ROOT}/experiment/stimuli/pill_stimuli/support/support_unexp.mp4",
                      "-frames:v", "1", "-vf", "scale=960:540", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     capture_output=True, check=True).stdout
frame = np.frombuffer(raw, np.uint8).reshape(540, 960, 3)

def norm(m):
    m = m - m.min()
    return m / m.max() if m.max() > 0 else m

# ---------- 1. visual salience (low-level contrast) ----------
small = np.asarray(Image.fromarray(frame).resize((MW, MH), Image.BILINEAR)).astype(float) / 255
r, g, b = small[..., 0], small[..., 1], small[..., 2]
lum = (r + g + b) / 3
gy_, gx_ = np.gradient(gaussian_filter(lum, 1))
edges = norm(gaussian_filter(np.hypot(gx_, gy_), 3))                      # luminance-edge density
color = norm(sum(np.abs(gaussian_filter(f, 2) - gaussian_filter(f, 12)) for f in (r - g, b - (r + g) / 2)))
sal = norm(gaussian_filter(.65 * edges + .35 * color, 3)) ** 1.3

# ---------- 2. semantic meaning (simulated) ----------
gx, gy = np.meshgrid((np.arange(MW) + .5) / MW, (np.arange(MH) + .5) / MH)
def blob(x, y, sd):
    return np.exp(-((gx - x) ** 2 + ((gy - y) * 9 / 16) ** 2) / (2 * sd ** 2))
def region(x0, x1, y0, y1, blur=6):  # soft-edged rectangle (fractions of width/height)
    return gaussian_filter(((gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)).astype(float), blur)
meaning = norm(1.0 * blob(.528, .33, .055)    # the ball
               + .4 * region(0, .43, .40, .77)  # the supporting wall/table, less than the ball
               + .8 * blob(.525, .52, .06)    # empty space under it, where support is missing
               + .55 * blob(.43, .42, .045)   # table edge the ball left
               + .3 * blob(.555, .70, .05))   # its shadow on the floor

# ---------- 3. combined ----------
combined = norm(.5 * sal + .5 * meaning)

def overlay(m):
    lo, hi = np.array([255, 210, 63]), np.array([235, 104, 52])  # #ffd23f -> #eb6834
    alpha = np.clip((m - .12) / .88 * 1.3, 0, .85)  # low priority stays transparent
    rgba = np.dstack([lo + (hi - lo) * m[..., None], alpha * 255]).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

buf = io.BytesIO()
Image.fromarray(frame).save(buf, "JPEG", quality=88)
BG = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

pw, gap, m = 420, 24, 20
ph = pw * 9 / 16
W = 2 * m + 3 * pw + 2 * gap
H = m + ph + 46
s = [f"<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='{W}' height='{H:.0f}' viewBox='0 0 {W} {H:.0f}'>",
     f"<defs><filter id='dim'><feColorMatrix type='saturate' values='0.5'/><feComponentTransfer>"
     f"<feFuncR type='linear' slope='0.7' intercept='0.3'/><feFuncG type='linear' slope='0.7' intercept='0.3'/>"
     f"<feFuncB type='linear' slope='0.7' intercept='0.3'/></feComponentTransfer></filter></defs>",
     f"<rect width='{W}' height='{H:.0f}' fill='{SURF}'/>"]
for i, (name, mp) in enumerate([("Visual salience", sal), ("Semantic meaning", meaning), ("Salience + meaning", combined)]):
    x0 = m + i * (pw + gap)
    ov = overlay(mp)
    s.append(f"<image x='{x0}' y='{m}' width='{pw}' height='{ph:.1f}' href='{BG}' xlink:href='{BG}' filter='url(#dim)'/>")
    s.append(f"<image x='{x0}' y='{m}' width='{pw}' height='{ph:.1f}' href='{ov}' xlink:href='{ov}' preserveAspectRatio='none'/>")
    s.append(f"<rect x='{x0}' y='{m}' width='{pw}' height='{ph:.1f}' fill='none' stroke='{INK2}' stroke-width='1.2'/>")
    s.append(f"<text x='{x0 + pw / 2:.1f}' y='{m + ph + 30:.1f}' {F} font-size='17' fill='{INK2}' text-anchor='middle'>{name}</text>")
s.append("</svg>")
open(OUT, "w").write("\n".join(s))
print(W, round(H))
