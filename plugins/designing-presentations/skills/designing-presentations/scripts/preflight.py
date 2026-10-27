#!/usr/bin/env python3
"""Check this machine before the first command: Python packages, LibreOffice, poppler,
fontconfig, HarfBuzz, and the faces a reference uses.

    preflight.py [--reference REF.pptx|REF.pdf]

Each line is ok, missing (the workflow cannot run; the install command follows),
optional (the workflow runs, and says what it does without it) or, for a face, needs.
With --reference, every face the reference names is looked up with fc-match: a face drawn
by an unrelated substitute, or with no file to measure it, reads needs: the workflow runs,
and the build refuses text set in that face until the user supplies its file (fonts.py
report) or a stand-in is named in the guide. A symbol face (bullet and tick glyphs) is never measured
as text and reads ok. Exit 0 when nothing missing; a needs line does not change the exit.
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
#: the same packages under Homebrew on macOS (each name checked against formulae.brew.sh)
BREW = {"libreoffice-impress": "--cask libreoffice", "poppler-utils": "poppler", "fontconfig": "fontconfig"}


def system_install(apt_names: list[str]) -> str:
    """The command that installs these system packages on this machine: Homebrew on macOS,
    apt-get elsewhere (Debian and Ubuntu names; another distribution has its own)."""
    if sys.platform == "darwin":
        casks = [BREW[n].removeprefix("--cask ") for n in apt_names if BREW[n].startswith("--cask ")]
        formulae = [BREW[n] for n in apt_names if not BREW[n].startswith("--cask ")]
        return " && ".join(([f"brew install {' '.join(formulae)}"] if formulae else []) + ([f"brew install --cask {' '.join(casks)}"] if casks else []))
    return f"sudo apt-get install -y {' '.join(apt_names)}"


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
        import textfit
        from ooxml import SYMBOL_FACES
        index = textfit.default_index()
        for face, e in sorted(report.items()):
            fidelity = str(e.get("fidelity"))
            bad = fidelity == "substituted" and not e.get("bullets_only")
            # the reference's renders and the build's measure are two questions: a PDF draws
            # its embedded copy of a face exactly while this machine has no file to measure
            # it with (bain's Verdana, McKinsey's Georgia: preflight said exact, the solver
            # refused every page)
            try:
                measured = index.resolve(face)
                measures = f"measured with {measured.family} ({measured.provenance})"
            except LookupError:
                measured = None
                measures = (f"NOT measurable here: no file of {face} and no metric-compatible clone; the build refuses text set in it until "
                            f"the user supplies its file in $DECK_FONTS or fc-match's stand-in ({textfit.fc_match(face)[0]}) is named under typography.families.substitutes")
            symbol = face.lower().startswith(SYMBOL_FACES)  # bullet and tick glyphs: drawn, never measured as text
            if measured is None and symbol:
                measures = "a symbol face: its glyphs are bullets and marks, not measured text"
            bad = bad and not symbol
            unmeasured = measured is None and not e.get("bullets_only") and not symbol
            faces_ok = faces_ok and not bad and not unmeasured
            note = ("bullet glyphs only, moves no text" if e.get("bullets_only") else
                    "an unrelated face: do not read text fit off its renders" if bad else fidelity)
            print(f"{'needs' if bad or unmeasured else 'ok':8} face {face}: drawn as {e.get('rendered_with')} ({note}); {measures}")
    if missing_pip or optional_pip or missing_apt:
        print("\nfor the user to run (or to tell you to); never run them yourself: packages are machine-wide (references/intake.md, What you may install)")
    if missing_pip:
        print(f"install: python3 -m pip install {' '.join(missing_pip)}")
    if optional_pip:
        print(f"optional: python3 -m pip install {' '.join(optional_pip)}")
    if missing_apt:
        print(f"install: {system_install(sorted(missing_apt))}")
    if not faces_ok:
        print("faces: never download or install a font. Run python3 scripts/fonts.py report REF -o \"$DECK_WORK/ref/fonts.json\" and show\n"
              "the user its report: the faces missing, the stand-in for each and its measured width, and the folder ($DECK_FONTS)\n"
              "where they can put font files they license (references/fonts.md)")
    return 0 if ok and not missing_pip and not missing_apt else 1


if __name__ == "__main__":
    import cli
    cli.run(main)
