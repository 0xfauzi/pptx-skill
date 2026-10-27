#!/usr/bin/env python3
"""The plugin's listing icon: a slide with a column chart and two text lines, on a square
navy ground. No mark of any firm or product. Writes
plugins/designing-presentations/.claude-plugin/icon.png at 512 x 512 px (the directory
check takes a square PNG of 512 to 2048 px a side, under 2 MB), drawn at four times that
size and reduced, so its edges are smooth.

usage: python3 tools/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIDE = 512
SCALE = 4
NAVY = (31, 58, 96)
PAPER = (255, 255, 255)
SLATE = (150, 163, 180)
ACCENT = (224, 122, 47)


def main() -> None:
    s = SIDE * SCALE
    img = Image.new("RGB", (s, s), NAVY)
    d = ImageDraw.Draw(img)

    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        return round(x0 * s), round(y0 * s), round(x1 * s), round(y1 * s)

    # the slide, 16:9, centred
    d.rounded_rectangle(box(0.12, 0.2375, 0.88, 0.6650), radius=round(0.02 * s), fill=PAPER)
    # a title line and a shorter subtitle line
    d.rectangle(box(0.18, 0.29, 0.62, 0.32), fill=NAVY)
    d.rectangle(box(0.18, 0.345, 0.48, 0.365), fill=SLATE)
    # four columns on a baseline, the last one in the accent
    base = 0.615
    for i, top in enumerate((0.50, 0.465, 0.43, 0.395)):
        x0 = 0.18 + i * 0.13
        d.rectangle(box(x0, top, x0 + 0.09, base), fill=ACCENT if i == 3 else NAVY)
    d.rectangle(box(0.17, base, 0.83, base + 0.006), fill=SLATE)
    out = Path(__file__).resolve().parents[1] / "plugins/designing-presentations/.claude-plugin/icon.png"
    img.resize((SIDE, SIDE), Image.LANCZOS).save(out, optimize=True)
    print(out.name, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
