#!/usr/bin/env python3
"""Render a .pptx or .pdf to one PNG per slide with LibreOffice and pdftoppm,
and report which fonts the renderer substituted.

    render.py deck.pptx [--out DIR] [--dpi 110] [--slides 1,3,5-8] [--grid]

Writes DIR/slide-NN.png (NN zero-padded to the slide count) and DIR/fonts.json:
for every font family the deck declares, what fontconfig will draw it with and
whether that is a metric-compatible alias (same advance widths, so the layout is
faithful even though the letterforms are not) or an unrelated substitute (the
render is NOT evidence about fit). --grid also writes DIR/grid.png, a labelled
contact sheet for a first look.

The renderer runs one conversion at a time in a fresh profile directory, because
a shared LibreOffice profile hangs on the second call in sandboxes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

A = "http://schemas.openxmlformats.org/drawingml/2006/main"

# Metric-compatible aliases fontconfig ships (Liberation, Carlito, Caladea
# families): same advance widths as the Microsoft faces, so wrap and fit agree.
# Anything else fontconfig picks is an unrelated substitute.
METRIC_ALIASES = {
    "arial": {"liberation sans", "arimo"},
    "helvetica": {"liberation sans", "arimo"},
    "times new roman": {"liberation serif", "tinos"},
    "courier new": {"liberation mono", "cousine"},
    "calibri": {"carlito"},
    "cambria": {"caladea"},
    "georgia": {"gelasio"},
    "symbol": {"standard symbols ps"},
}


def declared_fonts(pptx: Path) -> set[str]:
    names: set[str] = set()
    with zipfile.ZipFile(pptx) as z:
        for member in z.namelist():
            if not member.endswith(".xml") or not member.startswith("ppt/"):
                continue
            try:
                root = etree.fromstring(z.read(member), etree.XMLParser(resolve_entities=False, no_network=True))
            except etree.XMLSyntaxError:
                continue
            for tag in ("latin", "ea", "cs"):
                for el in root.iter(f"{{{A}}}{tag}"):
                    face = el.get("typeface")
                    if face and not face.startswith("+"):
                        names.add(face)
    return names


def font_report(faces: set[str]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for face in sorted(faces):
        try:
            match = subprocess.run(["fc-match", "-f", "%{family}", face], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            match = ""
        chosen = match.split(",")[0].strip()
        same = chosen.lower() == face.lower()
        metric = chosen.lower() in METRIC_ALIASES.get(face.lower(), set())
        out[face] = {
            "rendered_with": chosen,
            "fidelity": "exact" if same else "metric_alias" if metric else "substituted",
        }
    return out


def to_pdf(src: Path, workdir: Path) -> Path:
    profile = workdir / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("HOME", str(workdir))
    cmd = [
        "soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--norestore",
        "--nolockcheck", "--convert-to", "pdf", "--outdir", str(workdir), str(src),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    pdf = workdir / (src.stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError(f"LibreOffice produced no PDF\nstdout: {completed.stdout}\nstderr: {completed.stderr}")
    return pdf


def parse_slides(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(1, n + 1))
    wanted: set[int] = set()
    for piece in spec.split(","):
        piece = piece.strip()
        if "-" in piece:
            lo, hi = piece.split("-", 1)
            wanted.update(range(int(lo), int(hi) + 1))
        elif piece:
            wanted.add(int(piece))
    return sorted(i for i in wanted if 1 <= i <= n)


def page_count(pdf: Path) -> int:
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    return int(m.group(1)) if m else 0


def rasterize(pdf: Path, out: Path, dpi: int, slides: list[int], width_px: int | None = None) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    n = page_count(pdf)
    pad = max(2, len(str(n)))
    written: list[Path] = []
    for i in slides:
        target = out / f"slide-{i:0{pad}d}"
        cmd = ["pdftoppm", "-png", "-f", str(i), "-l", str(i), "-singlefile"]
        cmd += ["-scale-to-x", str(width_px), "-scale-to-y", "-1"] if width_px else ["-r", str(dpi)]
        subprocess.run(cmd + [str(pdf), str(target)], check=True, timeout=300)
        written.append(target.with_suffix(".png"))
    return written


def grid(images: list[Path], out: Path, cols: int = 4, cell_w: int = 480) -> Path:
    from PIL import Image, ImageDraw

    if not images:
        raise ValueError("no images to grid")
    thumbs = []
    for img_path in images:
        im = Image.open(img_path).convert("RGB")
        ratio = cell_w / im.width
        thumbs.append(im.resize((cell_w, max(1, int(im.height * ratio)))))
    cell_h = max(t.height for t in thumbs) + 24
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell_w + 12) + 12, rows * (cell_h + 12) + 12), "#DDDDDD")
    draw = ImageDraw.Draw(sheet)
    for k, (t, src) in enumerate(zip(thumbs, images)):
        x = 12 + (k % cols) * (cell_w + 12)
        y = 12 + (k // cols) * (cell_h + 12)
        sheet.paste(t, (x, y + 24))
        draw.text((x, y + 4), src.stem, fill="#000000")
    sheet.save(out)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck")
    ap.add_argument("--out", default=None, help="default: <deck stem>-renders next to the deck")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--width", type=int, default=None, help="pixel width per slide instead of dpi")
    ap.add_argument("--slides", default=None, help="e.g. 1,3,5-8")
    ap.add_argument("--grid", action="store_true")
    args = ap.parse_args(argv)
    src = Path(args.deck).resolve()
    out = Path(args.out) if args.out else src.with_name(src.stem + "-renders")
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"source": str(src)}
    with tempfile.TemporaryDirectory(prefix="render-") as tmp:
        work = Path(tmp)
        if src.suffix.lower() == ".pdf":
            pdf = src
        else:
            faces = declared_fonts(src)
            fonts = font_report(faces)
            report["fonts"] = fonts
            (out / "fonts.json").write_text(json.dumps(fonts, indent=1))
            pdf = to_pdf(src, work)
        n = page_count(pdf)
        slides = parse_slides(args.slides, n)
        images = rasterize(pdf, out, args.dpi, slides, args.width)
        report["pages"] = n
        report["images"] = [str(p) for p in images]
        if args.grid:
            report["grid"] = str(grid(images, out / "grid.png"))
    print(json.dumps(report, indent=1))
    substituted = [f for f, v in report.get("fonts", {}).items() if v["fidelity"] == "substituted"]  # type: ignore[union-attr]
    if substituted:
        print(f"WARNING: unrelated substitutes for {substituted}: do not read text fit off these renders", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
