#!/usr/bin/env python3
"""Render a .pptx or .pdf to one PNG per slide with LibreOffice and pdftoppm,
and report which fonts the renderer substituted.

    render.py deck.pptx [--out DIR] [--dpi 110] [--slides 1,3,5-8] [--grid]

Writes DIR/slide-NN.png (NN zero-padded to the slide count) and DIR/fonts.json:
for every font family the deck declares, what fontconfig will draw it with (family
and file) and whether that is a metric-compatible alias (fontconfig's binding="same"
table, textfit.METRIC_ALIAS_CLASSES: same advance widths, so the layout is faithful
even though the letterforms are not) or an unrelated substitute (the render is NOT
evidence about fit). Per face it also counts the codepoints the deck's runs set in
that face which the rendered file's charset (fc-query) does not cover, with up to
10 samples: a nonzero count means that face draws empty boxes or another face's
glyphs. --grid also writes DIR/grid.png, a labelled contact sheet for a first look.

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
import unicodedata
import zipfile
from bisect import bisect_right
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ooxml  # noqa: E402
from textfit import metric_alias  # noqa: E402

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
UNCOVERED_SAMPLE_MAX = 10
# Codepoints that carry no glyph by definition (deckgen render/fonts.py
# uncovered_codepoints): control, format, unassigned, private use, surrogate,
# separators. PowerPoint keeps Wingdings bullets in the Private Use Area.
NON_DRAWING_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp", "Zs"})


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
            for tag in ("latin", "ea", "cs", "buFont"):  # a bullet font is a face too (Wingdings squares)
                for el in root.iter(f"{{{A}}}{tag}"):
                    face = el.get("typeface")
                    if face and not face.startswith("+"):
                        names.add(face)
    return names


def codepoints_by_face(pptx: Path) -> dict[str, set[int]]:
    """The codepoints each face is asked to draw: every run's text under the face
    ooxml.py resolves for it (run, list styles, layout, master, theme), every bullet
    glyph under its bullet font, and chart text under the chart part's own latin face
    or, when it declares none, the theme's minor face."""
    out: dict[str, set[int]] = {}
    pkg = ooxml.Package(str(pptx))
    for slide_print in ooxml.fingerprint_deck(str(pptx)):
        for run in (*slide_print.runs, *slide_print.chrome_runs):
            if run.family:
                out.setdefault(run.family, set()).update(map(ord, run.text))
            if run.bullet_glyph and (run.bullet_font or run.family):
                out.setdefault(run.bullet_font or run.family or "", set()).update(map(ord, run.bullet_glyph))
    for part in pkg.slide_parts():
        chain = ooxml.Chain(pkg, part)
        for kind, target in pkg.rels(part).values():
            if kind != ooxml.REL_CHART or target not in pkg.names:
                continue
            root = pkg.root(target)
            faces = [el.get("typeface") for el in root.iter(f"{{{A}}}latin") if el.get("typeface") and not el.get("typeface", "").startswith("+")]
            face = faces[0] if faces else (chain.theme.minor_latin if chain.theme else None)
            if not face:
                continue
            for el in (*root.iter(f"{{{A}}}t"), *root.iter(f"{{{ooxml.C}}}v")):
                out.setdefault(face, set()).update(map(ord, el.text or ""))
    return out


def charset_of(path: str, index: int = 0) -> list[tuple[int, int]]:
    """The file's coverage from fc-query, as sorted (start, end) ranges. A query that
    fails vouches for nothing: an empty list, which covers no codepoint."""
    try:
        proc = subprocess.run(["fc-query", f"--index={index}", "--format=%{charset}", path], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    spans: list[tuple[int, int]] = []
    for token in proc.stdout.split():
        low, _, high = token.partition("-")
        try:
            start, end = int(low, 16), int(high, 16) if high else int(low, 16)
        except ValueError:
            continue
        if 0 <= start <= end <= 0x10FFFF:
            spans.append((start, end))
    return sorted(spans)


def uncovered(codepoints: set[int], charset: list[tuple[int, int]]) -> list[int]:
    missing: list[int] = []
    for point in sorted(codepoints):
        if 0xFE00 <= point <= 0xFE0F or 0xE0100 <= point <= 0xE01EF:  # variation selectors
            continue
        if unicodedata.category(chr(point)) in NON_DRAWING_CATEGORIES:
            continue
        i = bisect_right(charset, (point, 0x10FFFF)) - 1
        if i < 0 or not charset[i][0] <= point <= charset[i][1]:
            missing.append(point)
    return missing


def font_report(faces: set[str], deck: Path | None = None) -> dict[str, dict[str, object]]:
    """Per face: what fontconfig draws it with, the fidelity verdict, and (given the
    deck) the uncovered codepoints of the regular-style file fc-match picks."""
    used = codepoints_by_face(deck) if deck is not None else {}
    out: dict[str, dict[str, object]] = {}
    for face in sorted(faces | set(used)):
        try:
            match = subprocess.run(["fc-match", "-f", "%{family}\t%{file}\t%{index}", face], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            match = ""
        family, _, rest = match.partition("\t")
        file, _, index = rest.partition("\t")
        chosen = family.split(",")[0].strip()
        same = chosen.lower() == face.lower()
        entry: dict[str, object] = {
            "rendered_with": chosen,
            "file": file or None,
            "fidelity": "exact" if same else "metric_alias" if metric_alias(face, chosen) else "substituted",
        }
        if deck is not None:
            points = used.get(face, set())
            missing = uncovered(points, charset_of(file, int(index) if index.isdigit() else 0) if file else [])
            entry["codepoints_checked"] = len(points)
            entry["uncovered_count"] = len(missing)
            entry["uncovered_sample"] = [f"U+{p:04X}" for p in missing[:UNCOVERED_SAMPLE_MAX]]
        out[face] = entry
    return out


def uncovered_faces(fonts: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Faces that cannot draw some of the deck's characters."""
    return {face: entry for face, entry in fonts.items() if int(entry.get("uncovered_count") or 0) > 0}


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
            fonts = font_report(faces, src)
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
    tofu = uncovered_faces(report.get("fonts", {}))  # type: ignore[arg-type]
    if tofu:
        print(f"WARNING: characters the rendered faces cannot draw: { {f: e['uncovered_sample'] for f, e in tofu.items()} }; those runs render as empty boxes or another face", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
