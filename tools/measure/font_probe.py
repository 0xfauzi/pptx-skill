#!/usr/bin/env python3
"""Measure what the font design rests on. Downloads nothing and installs nothing.

    python3 -I tools/measure/font_probe.py OUT_DIR

It uses the test fonts of tools/evals/fonts/make_fixtures.py (an installed font copied
under the new family name Evalprobe Serif) and prints five measurements:

1. fontconfig: what fc-match answers for the test face, with and without a configuration
   file of one process (FONTCONFIG_FILE) that adds a folder with the test font.
2. LibreOffice: which face a deck set in the test face is drawn in (pdffonts on the PDF):
   with no change, with FONTCONFIG_FILE, with SAL_FONTPATH, and with the font in the
   profile's user/fonts folder.
3. Embedded fonts: whether LibreOffice draws a deck in the font that the deck embeds
   (ECMA-376 p:embeddedFontLst), for three payloads: the font file, EOT, EOT with XOR.
4. fsType: the embedding permission of every installed font file (scripts/fontfiles.py).
5. The width instrument: the test face read back from a PDF that LibreOffice drew in it,
   measured with the base font and with the default sans (scripts/fonts.py).
6. Subsets: how many installed faces map all 95 printable ASCII characters, the faces
   that do not, and the count for the subset fixture (fontfiles.PRINTABLE_ASCII).
For each LibreOffice run it counts the files added to fontconfig's own cache folders
(and removes them), and at the end it checks that those folders are as they were.
"""
from __future__ import annotations

import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "plugins" / "designing-presentations" / "skills" / "designing-presentations"
sys.path.insert(0, str(REPO / "tools" / "evals" / "fonts"))
sys.path.insert(0, str(SKILL / "scripts"))
import fontfiles  # noqa: E402
import make_fixtures  # noqa: E402

CACHE_DIRS = (Path("/var/cache/fontconfig"), Path.home() / ".cache" / "fontconfig")


def caches() -> dict[str, int]:
    return {str(f): f.stat().st_mtime_ns for d in CACHE_DIRS if d.is_dir() for f in d.iterdir()}


def conf(folder: Path, fonts: Path) -> Path:
    path = folder / "fonts.conf"
    path.write_text(f'<?xml version="1.0"?><fontconfig><cachedir>{escape(str(folder / "cache"))}</cachedir>'
                    f'<include ignore_missing="yes">/etc/fonts/fonts.conf</include><dir>{escape(str(fonts))}</dir></fontconfig>')
    return path


def drawn(deck: Path, work: Path, env: dict[str, str], profile_fonts: Path | None = None) -> list[str]:
    profile = work / "profile"
    if profile_fonts is not None:
        (profile / "user" / "fonts").mkdir(parents=True)
        for f in profile_fonts.iterdir():
            shutil.copy(f, profile / "user" / "fonts" / f.name)
    subprocess.run(["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--norestore", "--nolockcheck", "--convert-to", "pdf",
                    "--outdir", str(work), str(deck)], env={**os.environ, "HOME": str(work), **env}, capture_output=True, timeout=600, check=True)
    listing = subprocess.run(["pdffonts", str(work / (deck.stem + ".pdf"))], capture_output=True, text=True, timeout=60, check=True).stdout
    return [line.split()[0] for line in listing.splitlines()[2:] if line.strip()]


def main(out_dir: str) -> int:
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    before = caches()
    fix = out / "fixtures"
    make_fixtures.main(str(fix))
    fonts = fix / "fontsrc"
    only = out / "probe-fonts"
    only.mkdir(exist_ok=True)
    shutil.copy(fonts / "EvalprobeSerif-Regular.ttf", only / "EvalprobeSerif-Regular.ttf")
    face = make_fixtures.PROBE
    result: dict = {}
    with tempfile.TemporaryDirectory(prefix="probe-") as tmp:
        t = Path(tmp)
        cfg = conf(t, only)
        fc = lambda env: subprocess.run(["fc-match", "-f", "%{family}", face], capture_output=True, text=True, env={**os.environ, **env}, timeout=30, check=False).stdout
        result["1 fc-match"] = {"system": fc({}), "FONTCONFIG_FILE of one process": fc({"FONTCONFIG_FILE": str(cfg)}), "system again": fc({})}
        runs = {"no change": ({}, None), "FONTCONFIG_FILE": ({"FONTCONFIG_FILE": str(cfg)}, None),
                "SAL_FONTPATH": ({"SAL_FONTPATH": str(only)}, None), "profile user/fonts": ({}, only)}
        result["2 LibreOffice draws"] = {}
        result["2 cache files written outside the run's folder"] = {}
        for name, (env, pf) in runs.items():
            w = t / name.replace(" ", "-").replace("/", "-")
            w.mkdir()
            ahead = caches()
            result["2 LibreOffice draws"][name] = drawn(fix / "deck-named.pptx", w, env, pf)
            written = sorted(set(caches()) - set(ahead))
            result["2 cache files written outside the run's folder"][name] = len(written)
            for f in written:
                os.remove(f)  # this probe's own cache entry for a temporary folder: removed, so the probe leaves nothing behind
        probe = (fonts / "EvalprobeSerif-Regular.ttf").read_bytes()
        result["3 embedded font drawn by LibreOffice"] = {}
        for name, blob in (("font file", probe), ("EOT", make_fixtures.eot(probe, face)), ("EOT with XOR", make_fixtures.eot(probe, face, xor=True))):
            deck = t / f"embedded-{len(result['3 embedded font drawn by LibreOffice'])}.pptx"
            make_fixtures.embed(fix / "deck-named.pptx", deck, face, blob)
            w = t / deck.stem
            w.mkdir()
            result["3 embedded font drawn by LibreOffice"][name] = drawn(deck, w, {})
    counts: collections.Counter = collections.Counter()
    files = [p for r in ("/usr/share/fonts", "/usr/local/share/fonts") for p in Path(r).rglob("*")
             if p.suffix.lower() in fontfiles.FONT_SUFFIXES and not p.is_symlink()]
    faces_read, short = 0, []
    for p in files:
        try:
            for f in fontfiles.read_faces(p):
                counts[f"{f.embedding} (fsType {f.fs_type})"] += 1
                faces_read += 1
                if f.ascii_unmapped:
                    short.append(f"{f.family}: {f.ascii_unmapped} unmapped")
        except fontfiles.FontFileError as error:
            counts[f"unreadable: {error}"] += 1
    result["4 fsType of installed faces"] = {"files": len(files), **dict(sorted(counts.items()))}
    import zipfile
    subset = zipfile.ZipFile(fix / "deck-embedded-raw-subset.pptx").read("ppt/fonts/font1.fntdata")
    result["6 printable ASCII mapped"] = {"faces": faces_read, "map all 95": faces_read - len(short), "do not": sorted(short),
                                         "subset fixture": [f.ascii_unmapped for f in fontfiles.faces_in_bytes(subset, "subset")]}
    import fonts as report
    import textfit
    ruler = textfit.default_ruler()
    sans = subprocess.run(["fc-match", "-f", "%{family}\t%{file}", "sans-serif"], capture_output=True, text=True, timeout=30, check=False).stdout.split("\t")
    result["5 width instrument (subset.pdf)"] = {
        "ruler": ruler.name,
        "base font (same glyphs)": report.pdf_width_difference(fix / "subset.pdf", face, str(make_fixtures.base_font()), ruler, None),
        f"default sans ({sans[0]})": report.pdf_width_difference(fix / "subset.pdf", face, sans[1], ruler, None),
    }
    result["fontconfig caches unchanged"] = caches() == before
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
