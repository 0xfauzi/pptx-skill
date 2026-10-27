"""Replace the reference agency's wordmark in the master background with the fictional
Ridgeline State Forestry Program wordmark. Input: the template's background JPEG."""
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont


def face(pattern):
    """The font file fontconfig picks for a pattern (Liberation Sans, as installed)."""
    return subprocess.run(["fc-match", "-f", "%{file}", pattern], check=True, capture_output=True, text=True).stdout


src, out, preview = sys.argv[1], sys.argv[2], sys.argv[3]
im = Image.open(src).convert("RGB")
W, H = im.size  # 2928 x 1650 for 13.333 x 7.5 in
px = W / 13.333
I = lambda v: int(round(v * px))
d = ImageDraw.Draw(im)
d.rectangle([I(11.2), I(6.70), W - 1, I(7.44)], fill=(255, 255, 255))
navy, teal, ink = (0x1F, 0x3A, 0x4D), (0x19, 0x68, 0x86), (0, 0, 0)
x0, yb = 11.32, 7.36
d.polygon([(I(x0), I(yb)), (I(x0 + 0.22), I(yb - 0.46)), (I(x0 + 0.44), I(yb))], fill=navy)
d.polygon([(I(x0 + 0.17), I(yb)), (I(x0 + 0.37), I(yb - 0.32)), (I(x0 + 0.57), I(yb))], fill=teal)
d.line([(I(x0 + 0.09), I(yb - 0.17)), (I(x0 + 0.22), I(yb - 0.07)), (I(x0 + 0.37), I(yb - 0.19)), (I(x0 + 0.50), I(yb - 0.08))], fill=(255, 255, 255), width=max(2, I(0.022)))
tx, right = x0 + 0.64, 13.18
avail = I(right - tx)
def fit(path, text, size):
    while True:
        f = ImageFont.truetype(path, size)
        if d.textlength(text, font=f) <= avail:
            return f, size
        size -= 1
bold, bs = fit(face("Liberation Sans:style=Bold Italic"), "RIDGELINE", I(0.40))
small, ss = fit(face("Liberation Sans:style=Regular"), "State Forestry Program", I(0.16))
top = bold.getbbox("RIDGELINE")
d.text((I(tx), I(6.84) - top[1]), "RIDGELINE", font=bold, fill=ink)
d.text((I(tx) + 2, I(6.84) + (top[3] - top[1]) + I(0.05)), "State Forestry Program", font=small, fill=ink)
im.save(out, quality=95)
im.crop((I(10.8), I(6.4), W, H)).save(preview)
print("sizes px", bs, ss, out)
