"""Make the three kinds of README image from page renders: the range mosaic, the reference
pairs and the close-up crops.

usage: python3 showcase/readme_images.py RENDERS OUT_DIR

RENDERS holds one folder per deck, named as below, each with the slide-NN.png files that
scripts/render.py writes at --width 2400. OUT_DIR receives range.png, reference-eia.png,
reference-samhsa.png and the three closeup-*.png files. showcase/README.md gives the
render commands.

Each image is 1760 px wide or less: two device pixels for each of the 880 CSS pixels of a
GitHub README column. The palette step is the one of sheet.py.
"""
import os
import sys

from PIL import Image
from sheet import GROUND, GUTTER

WIDTH = 1760

# The mosaic, in reading order, two pages to a row: (deck folder, page).
RANGE = [
    ("s1-ipo-pitch-book", 1), ("lbo-committee-book", 4),
    ("board-transformation", 1), ("grocery-strategy", 4),
    ("s1-initiation-report", 5), ("board-transformation", 3),
    ("software-earnings", 1), ("s1-committee-pre-read", 4),
    ("transit-outlook", 2), ("wildfire-plan", 2),
    ("board-transformation", 6), ("parks-annual-report", 2),
]

# Each pair: (output name, reference folder, reference page, generated folder, generated page).
PAIRS = [
    ("reference-eia", "eia", 13, "transit-outlook", 2),
    ("reference-samhsa", "samhsa", 10, "wildfire-plan", 1),
]

# Each crop: (output name, deck folder, page, (left, top, right, bottom) as fractions of the page).
CLOSEUPS = [
    ("closeup-risk", "board-transformation", 8, (0.02, 0.10, 0.98, 0.905)),
    ("closeup-returns", "lbo-committee-book", 4, (0.0, 0.025, 0.69, 0.61)),
    ("closeup-commitments", "s1-initiation-report", 4, (0.0, 0.14, 0.452, 0.95)),
]


def page(renders: str, deck: str, n: int) -> Image.Image:
    folder = os.path.join(renders, deck)
    names = sorted(f for f in os.listdir(folder) if f.startswith("slide-") and f.endswith(".png"))
    hits = [f for f in names if int(f[6:-4]) == n]
    if len(hits) != 1:
        raise SystemExit(f"{folder}: no single render of page {n}")
    with Image.open(os.path.join(folder, hits[0])) as im:
        return im.convert("RGB")


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """The page scaled to fit a w x h cell, centred on the ground."""
    k = min(w / im.width, h / im.height)
    small = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    cell = Image.new("RGB", (w, h), GROUND)
    cell.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
    return cell


def grid(cells: list[Image.Image], cols: int) -> Image.Image:
    w, h = cells[0].size
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (GUTTER + cols * (w + GUTTER), GUTTER + rows * (h + GUTTER)), GROUND)
    for k, cell in enumerate(cells):
        sheet.paste(cell, (GUTTER + (k % cols) * (w + GUTTER), GUTTER + (k // cols) * (h + GUTTER)))
    return sheet


def save(im: Image.Image, path: str) -> None:
    im.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE).save(path, optimize=True)
    print(path, im.size, os.path.getsize(path))


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: readme_images.py RENDERS OUT_DIR")
    renders, out = argv
    os.makedirs(out, exist_ok=True)
    cw = (WIDTH - 3 * GUTTER) // 2
    ch = round(cw * 9 / 16)
    save(grid([fit(page(renders, d, n), cw, ch) for d, n in RANGE], 2), os.path.join(out, "range.png"))
    for name, rd, rn, gd, gn in PAIRS:
        save(grid([fit(page(renders, rd, rn), cw, ch), fit(page(renders, gd, gn), cw, ch)], 2), os.path.join(out, name + ".png"))
    for name, d, n, (x0, y0, x1, y1) in CLOSEUPS:
        im = page(renders, d, n)
        c = im.crop((round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height)))
        if c.width > WIDTH:
            c = c.resize((WIDTH, round(c.height * WIDTH / c.width)), Image.LANCZOS)
        save(c, os.path.join(out, name + ".png"))


if __name__ == "__main__":
    main(sys.argv[1:])
