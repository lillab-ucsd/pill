"""
H3.3 concept figure: what fixation entropy measures, on an empty 4x3 grid.
The same 24 fixations are spread over more and more cells; cell shading = proportion of fixations,
H = -sum(p * log2 p) over cells. Max for 12 cells = log2(12) = 3.58 bits.
Usage: python3 make_h3_3_entropy_concept.py <out.svg>
"""
import math, random, sys

OUT = sys.argv[1]

INK, INK2, GRID, SURF, FILL = "#0b0b0b", "#52514e", "#c9c8c2", "#fcfcfb", "#2a78d6"
F = "font-family='Helvetica, Arial, sans-serif'"
GX, GY = 4, 3

# fixation counts per (col, row) cell; 24 fixations each
examples = [
    {(2, 1): 24},
    {(2, 1): 18, (3, 1): 3, (2, 2): 3},
    {(2, 1): 8, (1, 1): 6, (2, 2): 4, (3, 0): 3, (0, 2): 2, (1, 0): 1},
    {(c, r): 2 for c in range(GX) for r in range(GY)},
]
def entropy(counts):
    n = sum(counts.values())
    return -sum(k / n * math.log2(k / n) for k in counts.values()) + 0.0

gw, gh, gap, m, top = 280, 157.5, 34, 20, 20
cw, ch = gw / GX, gh / GY
W = 2 * m + len(examples) * gw + (len(examples) - 1) * gap
H = top + gh + 110

s = []
a = s.append
def text(x, y, t, size=13, fill=INK, anchor="start", weight="normal"):
    a(f"<text x='{x:.1f}' y='{y:.1f}' {F} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'>{t}</text>")

a(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H:.0f}' viewBox='0 0 {W} {H:.0f}'>")
a(f"<defs><marker id='arr' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
  f"<path d='M0,0 L10,5 L0,10 z' fill='{INK2}'/></marker></defs>")
a(f"<rect width='{W}' height='{H:.0f}' fill='{SURF}'/>")

rng = random.Random(4)
for e, counts in enumerate(examples):
    x0, y0 = m + e * (gw + gap), top
    n = sum(counts.values())
    a(f"<rect x='{x0}' y='{y0}' width='{gw}' height='{gh}' fill='#ffffff'/>")
    for (c, r), k in counts.items():  # shade by proportion of fixations
        a(f"<rect x='{x0 + c * cw:.1f}' y='{y0 + r * ch:.1f}' width='{cw:.1f}' height='{ch:.1f}' fill='{FILL}' fill-opacity='{0.08 + 0.72 * k / n:.2f}'/>")
    for i in range(1, GX):
        a(f"<line x1='{x0 + i * cw:.1f}' y1='{y0}' x2='{x0 + i * cw:.1f}' y2='{y0 + gh}' stroke='{GRID}' stroke-width='1.2'/>")
    for j in range(1, GY):
        a(f"<line x1='{x0}' y1='{y0 + j * ch:.1f}' x2='{x0 + gw}' y2='{y0 + j * ch:.1f}' stroke='{GRID}' stroke-width='1.2'/>")
    a(f"<rect x='{x0}' y='{y0}' width='{gw}' height='{gh}' fill='none' stroke='{INK2}' stroke-width='1.5'/>")
    for (c, r), k in counts.items():  # one dot per fixation, jittered inside its cell
        for _ in range(k):
            fx = x0 + (c + rng.uniform(.15, .85)) * cw
            fy = y0 + (r + rng.uniform(.18, .82)) * ch
            a(f"<circle cx='{fx:.1f}' cy='{fy:.1f}' r='3.2' fill='{INK}' stroke='#ffffff' stroke-width='1'/>")
    text(x0 + gw / 2, y0 + gh + 34, f"H = {entropy(counts):.2f} bits", 18, INK, "middle", "bold")

ay = top + gh + 80
a(f"<line x1='{m}' y1='{ay}' x2='{W - m}' y2='{ay}' stroke='{INK2}' stroke-width='1.8' marker-start='url(#arr)' marker-end='url(#arr)'/>")
text(m + 14, ay - 9, "concentrated: low entropy", 14, INK2)
text(W - m - 14, ay - 9, "spread out: high entropy", 14, INK2, "end")

a("</svg>")
open(OUT, "w").write("\n".join(s))
