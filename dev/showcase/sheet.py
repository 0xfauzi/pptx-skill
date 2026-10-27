"""Lay page renders out as one PNG and shrink it to a 256-colour palette.

usage: python3 dev/showcase/sheet.py OUT.png WIDTH COLUMNS PAGE.png [PAGE.png ...]

Pages are scaled to the column width and placed in reading order on a grey ground, with a
16 px gutter. The palette is chosen by maximum coverage with no dithering: on the five showcase
sheets it kept every pixel within 21 (sum of the three channel differences, out of 765) of
the full-colour sheet, at 22 to 28 percent of the full-colour file's size (measured when the
sheets in docs/showcase/ were made).
"""
import sys

from PIL import Image

GUTTER = 16
GROUND = "#d0d4da"


def main(argv: list[str]) -> None:
    out, width, cols, pages = argv[0], int(argv[1]), int(argv[2]), argv[3:]
    if not pages:
        raise SystemExit("usage: sheet.py OUT.png WIDTH COLUMNS PAGE.png [PAGE.png ...]")
    cell = (width - GUTTER * (cols + 1)) // cols
    ims = []
    for path in pages:
        with Image.open(path) as im:
            im = im.convert("RGB")
            ims.append(im.resize((cell, round(im.height * cell / im.width)), Image.LANCZOS))
    rows = [ims[k:k + cols] for k in range(0, len(ims), cols)]
    height = GUTTER + sum(max(i.height for i in row) + GUTTER for row in rows)
    sheet = Image.new("RGB", (width, height), GROUND)
    y = GUTTER
    for row in rows:
        for k, im in enumerate(row):
            sheet.paste(im, (GUTTER + k * (cell + GUTTER), y))
        y += max(i.height for i in row) + GUTTER
    sheet.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE).save(out, optimize=True)
    print(out, sheet.size)


if __name__ == "__main__":
    main(sys.argv[1:])
