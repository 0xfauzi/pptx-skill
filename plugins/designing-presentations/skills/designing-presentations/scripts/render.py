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

A .pdf is rasterized as it is, and its fonts.json lists the families the file names
(pdffonts): an embedded face is drawn from the file's own glyphs (exact), a face the file
only names is matched through fontconfig as above.

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
from bisect import bisect_right
from pathlib import Path

from lxml import etree

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ooxml  # noqa: E402
from textfit import fc_match, metric_alias  # noqa: E402

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
UNCOVERED_SAMPLE_MAX = 10
# Codepoints that carry no glyph by definition: control, format, unassigned, private use, surrogate,
# separators. PowerPoint keeps Wingdings bullets in the Private Use Area.
NON_DRAWING_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp", "Zs"})


def declared_fonts(pptx: Path) -> set[str]:
    names: set[str] = set()
    # through ooxml.Package, the one reader that holds the zip-bomb and element caps
    pkg = ooxml.Package(str(pptx))
    with pkg.zip:
        for member in sorted(pkg.xml_parts):
            if not member.startswith("ppt/"):
                continue
            try:
                root = pkg.root(member)
            except etree.XMLSyntaxError:
                continue
            for tag in ("latin", "ea", "cs", "buFont"):  # a bullet font is a face too (Wingdings squares)
                for el in root.iter(f"{{{A}}}{tag}"):
                    face = el.get("typeface")
                    if face and not face.startswith("+"):
                        names.add(face)
    return names


def codepoints_by_face(pptx: Path) -> tuple[dict[str, set[int]], set[str]]:
    """The codepoints each face is asked to draw: every run's text under the face
    ooxml.py resolves for it (run, list styles, layout, master, theme), every bullet
    glyph under its bullet font, and chart text under the chart part's own latin face
    or, when it declares none, the theme's minor face. Second: the faces that set text
    (a run or chart text resolves to them), as opposed to a bullet glyph only."""
    out: dict[str, set[int]] = {}
    text_faces: set[str] = set()
    pkg = ooxml.Package(str(pptx))
    for slide_print in ooxml.fingerprint_deck(str(pptx)):
        for run in (*slide_print.runs, *slide_print.chrome_runs):
            if run.family:
                out.setdefault(run.family, set()).update(map(ord, run.text))
                text_faces.add(run.family)
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
            text_faces.add(face)
            for el in (*root.iter(f"{{{A}}}t"), *root.iter(f"{{{ooxml.C}}}v")):
                out.setdefault(face, set()).update(map(ord, el.text or ""))
    return out, text_faces


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
    deck) the uncovered codepoints of the regular-style file fc-match picks, and
    `bullets_only`: the face draws bullet glyphs and nothing else. A substitute for such
    a face moves no text (the paragraph's marL and indent place the text, not the glyph's
    advance), so it does not decide whether text extents in a render are evidence."""
    used, text_faces = codepoints_by_face(deck) if deck is not None else ({}, set())
    out: dict[str, dict[str, object]] = {}
    for face in sorted(faces | set(used)):
        chosen, file, face_index = fc_match(face)  # the one fc-match reader: the solver measures a stand-in with it too
        same = chosen.lower() == face.lower()
        entry: dict[str, object] = {
            "rendered_with": chosen,
            "file": file or None,
            "fidelity": "exact" if same else "metric_alias" if metric_alias(face, chosen) else "substituted",
        }
        if deck is not None:
            points = used.get(face, set())
            missing = uncovered(points, charset_of(file, face_index) if file else [])
            entry["codepoints_checked"] = len(points)
            entry["uncovered_count"] = len(missing)
            entry["uncovered_sample"] = [f"U+{p:04X}" for p in missing[:UNCOVERED_SAMPLE_MAX]]
            entry["bullets_only"] = bool(points) and face not in text_faces
        out[face] = entry
    return out


_PDFFONTS_ROW = re.compile(r"^(\S+)\s+.*?\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$")


def pdf_font_report(pdf: Path) -> dict[str, dict[str, object]]:
    """Per family a PDF names (pdffonts), what the page renders draw it with. pdftoppm
    draws an embedded font from the file's own glyphs, so the render is exact for it; a
    face the file only names is drawn with what fontconfig picks, and is judged like a
    pptx face (exact, metric_alias or substituted). An embedded subset holds exactly the
    glyphs the file sets, so no codepoint check applies; a named face is not checked
    either (the file's text is not mapped to faces here) and says so."""
    try:
        listing = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        listing = ""
    embedded: dict[str, bool] = {}
    for line in listing.splitlines()[2:]:
        m = _PDFFONTS_ROW.match(line)
        if not m or m.group(1) == "[none]":
            continue
        family, _ = ooxml._pdf_family(m.group(1))
        if family:
            embedded[family] = embedded.get(family, True) and m.group(2) == "yes"
    named = {face for face, emb in embedded.items() if not emb}
    out = font_report(named) if named else {}
    for face in out:
        out[face]["embedded"] = False
        out[face]["codepoints_checked"] = None
    for face, emb in embedded.items():
        if emb:
            out[face] = {"rendered_with": face, "file": None, "fidelity": "exact", "embedded": True, "codepoints_checked": None,
                         "uncovered_count": 0, "uncovered_sample": []}
    return dict(sorted(out.items()))


def uncovered_faces(fonts: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Faces that cannot draw some of the deck's characters."""
    return {face: entry for face, entry in fonts.items() if int(entry.get("uncovered_count") or 0) > 0}


def offline_copy(src: Path, workdir: Path, blocked: list[str] | None = None) -> Path:
    """A copy of the package in which every relationship that does not name a part inside
    it points nowhere. LibreOffice fetches a picture a deck links to on the web when it
    converts the deck (measured: a linked picture drew OPTIONS, HEAD
    and GET requests to a local HTTP server), and a reference deck is untrusted input.
    It reads TargetMode without regard to case and follows a picture's relationship by its
    id whatever its Type (a picture under a hyperlink Type was fetched too), so the rule
    here reads neither: a relationship is kept only when it is Internal and its target,
    compared case-insensitively, is a member of the zip. Every package is copied, whatever
    its extension (.potx and .pptm were fetched from when only .pptx was). Each target left
    out is added to `blocked` ("part: target"); a linked picture draws as an empty frame,
    as it would offline."""
    import zipfile
    from urllib.parse import unquote
    ooxml.Package(str(src)).zip.close()  # the caps, one copy per part name, well-formed relationship parts
    out = workdir / "offline" / src.name
    out.parent.mkdir(parents=True, exist_ok=True)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        members = {info.filename.lower() for info in zin.infolist()}
        for info in zin.infolist():
            data = zin.read(info)
            name = info.filename
            if name.lower().endswith(".rels"):
                low = name.lower()
                folder = low.rpartition("/_rels/")[0] if "/_rels/" in low else ""
                try:
                    root = etree.fromstring(data, parser)
                except etree.XMLSyntaxError:
                    root = etree.Element(f"{{{RELS_NS}}}Relationships")  # nothing in it is followed
                    if blocked is not None:
                        blocked.append(f"{name}: not well-formed, dropped")
                cut = []
                for rel in root.iter():
                    if not isinstance(rel.tag, str) or rel.get("Target") is None:
                        continue
                    target = rel.get("Target") or ""
                    internal = (rel.get("TargetMode") or "Internal").strip().lower() == "internal"
                    if not (internal and ooxml.resolve_target(folder, unquote(target)).lower() in members):
                        cut.append(rel)
                for rel in cut:
                    if blocked is not None:
                        blocked.append(f"{name}: {rel.get('Target')}")
                    rel.set("Target", "")
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(info, data)
    return out


RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def to_pdf(src: Path, workdir: Path, blocked: list[str] | None = None) -> Path:
    """The deck's PDF as LibreOffice draws it, from offline_copy, so nothing the package
    links to outside itself is fetched; `blocked` collects the targets left out."""
    profile = workdir / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("HOME", str(workdir))
    src = offline_copy(src, workdir, blocked)
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
    ap.add_argument("--keep-pdf", default=None, help="also write the PDF LibreOffice made (a pptx source) to this path: the build reads the words it drew")
    args = ap.parse_args(argv)
    src = Path(args.deck).resolve()
    import cli
    cli.guard_args(args, "keep_pdf")
    out = cli.out_path(Path(args.out) if args.out else src.with_name(src.stem + "-renders"), "render folder")
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"source": str(src)}
    with tempfile.TemporaryDirectory(prefix="render-") as tmp:
        work = Path(tmp)
        if src.suffix.lower() == ".pdf":
            pdf = src
            fonts = pdf_font_report(src)
            report["fonts"] = fonts
            (out / "fonts.json").write_text(json.dumps(fonts, indent=1))
        else:
            faces = declared_fonts(src)
            fonts = font_report(faces, src)
            report["fonts"] = fonts
            (out / "fonts.json").write_text(json.dumps(fonts, indent=1))
            blocked: list[str] = []
            pdf = to_pdf(src, work, blocked)
            if blocked:
                report["external_links_not_fetched"] = blocked
            if args.keep_pdf:
                shutil.copyfile(pdf, args.keep_pdf)
        n = page_count(pdf)
        slides = parse_slides(args.slides, n)
        images = rasterize(pdf, out, args.dpi, slides, args.width)
        report["pages"] = n
        report["images"] = [str(p) for p in images]
        if args.grid:
            report["grid"] = str(grid(images, out / "grid.png"))
    print(json.dumps(report, indent=1))
    substituted = [f for f, v in report.get("fonts", {}).items() if v["fidelity"] == "substituted" and not v.get("bullets_only")]  # type: ignore[union-attr]
    if substituted:
        print(f"WARNING: unrelated substitutes for {substituted}: do not read text fit off these renders", file=sys.stderr)
    tofu = uncovered_faces(report.get("fonts", {}))  # type: ignore[arg-type]
    if tofu:
        print(f"WARNING: characters the rendered faces cannot draw: { {f: e['uncovered_sample'] for f, e in tofu.items()} }; those runs render as empty boxes or another face", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
