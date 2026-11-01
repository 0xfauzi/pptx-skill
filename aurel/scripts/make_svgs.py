"""Write the deck's shape visuals as SVG in the skill's subset (rect, circle, line; colour roles only)."""
import math, random, sys
out = sys.argv[1]
rnd = random.Random(7)  # fixed seed: the same waveform every build

def bars(n, w, h, height_fn, gap=0.42):
    pitch = w / n
    bw = pitch * (1 - gap)
    parts = []
    for i in range(n):
        bh = max(2.0, height_fn(i, n) * h)
        x = i * pitch + (pitch - bw) / 2
        y = (h - bh) / 2
        parts.append((x, y, bw, bh))
    return parts

def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">\n' + "\n".join(body) + "\n</svg>\n"

# 1. noise: 72 uneven bars across the page
W, H = 1200, 360
amps = [0.25 + 0.75 * abs(math.sin(i * 0.37) * rnd.random()) ** 0.7 for i in range(72)]
body = [f'  <rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" height="{bh:.2f}" fill="color.ink_muted" stroke="none"/>'
        for x, y, bw, bh in bars(72, W, H, lambda i, n: amps[i])]
open(f"{out}/noise.svg", "w").write(svg(W, H, body))

# 2. noise to silence: the same bars decaying to nothing over the right half, then a gold line
def decay(i, n):
    t = i / (n - 1)
    k = 1.0 if t < 0.35 else max(0.0, 1 - (t - 0.35) / 0.4) ** 2
    return amps[i] * k
parts = bars(72, W, H, decay)
body = []
for (x, y, bw, bh), i in zip(parts, range(72)):
    if decay(i, 72) * H > 2.5:
        body.append(f'  <rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" height="{bh:.2f}" fill="color.ink_muted" stroke="none"/>')
first_flat = next(i for i in range(72) if decay(i, 72) * H <= 2.5)
x0 = parts[first_flat][0]
body.append(f'  <rect x="{x0:.2f}" y="{H/2-2:.2f}" width="{W-x0:.2f}" height="4" fill="color.accent1" stroke="none"/>')
open(f"{out}/quiet.svg", "w").write(svg(W, H, body))

# 3. driver rings: concentric rings, the core in gold
S = 600
body = []
for r in (290, 240, 190, 140):
    body.append(f'  <circle cx="300" cy="300" r="{r}" fill="none" stroke="color.rule" stroke-width="3" stroke-linecap="butt" stroke-linejoin="miter"/>')
body.append('  <circle cx="300" cy="300" r="90" fill="none" stroke="color.accent1" stroke-width="6" stroke-linecap="butt" stroke-linejoin="miter"/>')
body.append('  <circle cx="300" cy="300" r="34" fill="color.accent1" stroke="none"/>')
open(f"{out}/rings.svg", "w").write(svg(S, S, body))
print("wrote noise.svg quiet.svg rings.svg; first flat bar", first_flat)
