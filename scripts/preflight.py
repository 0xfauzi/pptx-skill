#!/usr/bin/env python3
"""Check this machine before the first command: Python packages, LibreOffice, poppler,
fontconfig, HarfBuzz, and the faces a reference uses.

    preflight.py [--reference REF.pptx|REF.pdf]

Each line is ok, missing (the workflow cannot run; the install command follows) or
optional (the workflow runs, and says what it does without it). With --reference, every
face the reference names is looked up with fc-match: a face drawn by an unrelated
substitute cannot be measured, and the build refuses text set in it until it is
installed or a metric-compatible stand-in is named in the guide. Exit 0 when nothing
required is missing.
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))

PACKAGES = (  # (import name, pip name, required, what it does)
    ("lxml", "lxml", True, "reads and writes OOXML"),
    ("PIL", "Pillow", True, "images, crops and the fallback text ruler"),
    ("pptx", "python-pptx", True, "writes the deck"),
    ("pdfplumber", "pdfplumber", True, "reads PDF references"),
    ("uharfbuzz", "uharfbuzz", False, "the better text ruler; without it the Pillow ruler measures (the build report names the ruler)"),
)
TOOLS = (  # (binary, apt package, required, what it does)
    ("soffice", "libreoffice-impress", True, "renders .pptx to PDF"),
    ("pdftoppm", "poppler-utils", True, "rasterises PDF pages"),
    ("pdftotext", "poppler-utils", True, "reads the words a render drew (annotation check, leakage on PDFs)"),
    ("pdffonts", "poppler-utils", True, "lists a PDF's fonts"),
    ("fc-match", "fontconfig", True, "finds the installed face for each named face"),
    ("fc-query", "fontconfig", True, "reads a face's character coverage"),
)
METRIC_FONTS = "fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", default=None, help="a reference deck whose faces to look up")
    args = ap.parse_args(argv)
    missing_pip, missing_apt, optional_pip = [], set(), []
    ok = sys.version_info >= (3, 11)
    print(f"{'ok' if ok else 'missing':8} python {sys.version.split()[0]} (3.11 or later)")
    for mod, pip, required, what in PACKAGES:
        try:
            m = importlib.import_module(mod)
            print(f"{'ok':8} {pip} {getattr(m, '__version__', '')}: {what}")
        except ImportError:
            print(f"{'missing' if required else 'optional':8} {pip}: {what}")
            (missing_pip if required else optional_pip).append(pip)
    for binary, apt, required, what in TOOLS:
        path = shutil.which(binary)
        if path:
            version = ""
            if binary == "soffice":
                version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=60).stdout.strip().split("\n")[0]
            print(f"{'ok':8} {binary} {version}: {what}")
        else:
            print(f"{'missing':8} {binary}: {what}")
            missing_apt.add(apt)
    faces_ok = True
    if args.reference and shutil.which("fc-match"):
        # render.py's own font report: the verdicts the renders and the gallery are read with
        import render
        ref = Path(args.reference)
        report = render.pdf_font_report(ref) if ref.suffix.lower() == ".pdf" else render.font_report(render.declared_fonts(ref), ref)
        for face, e in sorted(report.items()):
            fidelity = str(e.get("fidelity"))
            bad = fidelity == "substituted" and not e.get("bullets_only")
            faces_ok = faces_ok and not bad
            note = ("bullet glyphs only, moves no text" if e.get("bullets_only") else
                    "an unrelated face: do not read text fit off its renders, and measuring it needs the face or a named stand-in" if bad else fidelity)
            print(f"{'missing' if bad else 'ok':8} face {face}: drawn as {e.get('rendered_with')} ({note})")
    if missing_pip:
        print(f"\ninstall: python3 -m pip install {' '.join(missing_pip)}")
    if optional_pip:
        print(f"optional: python3 -m pip install {' '.join(optional_pip)}")
    if missing_apt:
        print(f"install: sudo apt-get install -y {' '.join(sorted(missing_apt))}")
    if not faces_ok:
        print(f"faces: install the named faces, or their metric-compatible stand-ins (sudo apt-get install -y {METRIC_FONTS}),\n"
              "then fc-cache -f; a face with no stand-in is named under typography.families.substitutes in the completion")
    return 0 if ok and not missing_pip and not missing_apt else 1


if __name__ == "__main__":
    import cli
    cli.run(main)
