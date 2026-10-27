"""Redraw the Ridgeline wordmark lighter and smaller, at the reference wordmark's scale.
Input: the v1 background (its wordmark area is cleared first)."""
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont


def face(pattern):
    """The font file fontconfig picks for a pattern (Liberation Sans, as installed)."""
    return subprocess.run(["fc-match", "-f", "%{file}", pattern], check=True, capture_output=True, text=True).stdout


src, out, preview = sys.argv[1], sys.argv[2], sys.argv[3]
im = Image.open(src).convert("RGB")
W, H = im.size
px = W / 13.333
I = lambda v: int(round(v * px))
d = ImageDraw.Draw(im)
d.rectangle([I(11.2), I(6.70), W - 1, I(7.44)], fill=(255, 255, 255))
ink, teal = (0x1A, 0x1A, 0x1A), (0x19, 0x68, 0x86)
right = 13.12
bold = ImageFont.truetype(face("Liberation Sans:style=Bold Italic"), I(0.27))
small = ImageFont.truetype(face("Liberation Sans:style=Regular"), I(0.105))
t1, t2 = "RIDGELINE", "State Forestry Program"
w1 = d.textlength(t1, font=bold); w2 = d.textlength(t2, font=small)
x1 = I(right) - w1; y1 = I(6.93)
bb = bold.getbbox(t1)
d.text((x1, y1 - bb[1]), t1, font=bold, fill=ink)
# a thin ridge line over the word: the mark's only drawing
yb = y1 - I(0.05)
xs = [x1 + w1 * f for f in (0.0, 0.18, 0.30, 0.46, 0.60, 0.80, 1.0)]
ys = [yb, yb - I(0.07), yb - I(0.03), yb - I(0.11), yb - I(0.04), yb - I(0.08), yb]
d.line(list(zip(xs, ys)), fill=teal, width=max(2, I(0.018)), joint="curve")
cap = bb[3] - bb[1]
d.text((I(right) - w2, y1 + cap + I(0.045)), t2, font=small, fill=ink)
im.save(out, quality=95)
im.crop((I(10.8), I(6.4), W, H)).save(preview)
print("wordmark width in", round(w1 / px, 2), "subtitle width in", round(w2 / px, 2))
