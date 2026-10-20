#!/usr/bin/env python3
"""The measurement API a component reads instead of estimating text.

A component (`components/<kind>/expand.py`) receives the guide with `guide["_api"]`
set to this module's two functions, bound to the same ruler, face index and role
resolution the solver measures the page with. A component that writes
`0.6 * em * len(text)` for a figure's width is guessing at a number the solver will
measure a moment later; a component that calls the API gets the solver's own figure,
so a box it sizes to a string holds that string on one line at scale 1.00.

    api = guide["_api"]
    w = api["text_width_emu"](guide, "type.caption", "$12.4 to $13.9")   # int EMU
    p = api["line_pitch_emu"](guide, "type.body")                        # int EMU
    eps = api["fit_epsilon_emu"]                                           # int EMU

text_width_emu(guide, role, text, emphasis=False) -> int
    The width the whole string DRAWS in `role` at scale 1.00: cased by the role's case
    convention, in the face the solver resolves for the role (bold when the role's
    weight is 700, or when `emphasis` is set, since the emitter bolds emphasis runs),
    tracked as OOXML spc tracks it, measured as one run (never a sum of fragments:
    kerning). A text element given `size.width_emu = text_width_emu(...) +
    fit_epsilon_emu` keeps the string on one line, because the solver wraps at the box
    width minus its ruler's fit epsilon. Add the element's own insets or padding, which
    this figure does not include.

line_pitch_emu(guide, role) -> int
    The baseline-to-baseline advance of one line in `role` at scale 1.00: exactly the
    a:spcPts the file writes (line_spacing x size, 1.2 x size when the guide leaves the
    spacing absent). A paragraph of n lines stacks n x pitch plus the role's paragraph
    spacing (`paragraph_spacing_emu`, also exposed), which is what the solver charges
    for the element's height.

Both raise layout.UnknownTokenRoleError for a role the guide does not define, like the
solver would a moment later; a component must not catch it and fall back to a guess.

The functions are bound to the guide at `make_api` time (build_deck builds one API per
build); the `guide` argument they take is the one the component received, so a
component can call them as plain functions without holding anything else.
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L  # noqa: E402

API_KEYS = ("text_width_emu", "line_pitch_emu", "paragraph_spacing_emu", "fit_epsilon_emu")


def make_api(guide_raw: dict, lg: L.Guide | None = None, ruler: L.Ruler | None = None, index: L.FaceIndex | None = None) -> dict[str, Any]:
    """The API dict for `guide["_api"]`, bound to the solver's instruments. The build
    passes its own loaded guide, ruler and index so the component measures with
    exactly what the page is solved with; a standalone caller gets the defaults."""
    lg = lg if lg is not None else L.load_guide(guide_raw)
    ruler = ruler if ruler is not None else L.default_ruler()
    index = index if index is not None else L.default_index()
    ctx = L.Context(lg, ruler, index)  # spec=None: a measuring-only context

    def text_width_emu(guide: dict, role: str, text: str, emphasis: bool = False) -> int:
        entry = L.resolve_type_entry(lg, role, Fraction(1))
        face = ctx.face(entry, bold=entry.bold or bool(emphasis))
        cased = L.apply_case(text, entry.case)
        if not cased.strip(" "):
            return 0
        return L.one_line_width(ctx, cased, L.DrawnRole(entry, face.path))

    def line_pitch_emu(guide: dict, role: str) -> int:
        return L.resolve_type_entry(lg, role, Fraction(1)).pitch_emu

    def paragraph_spacing_emu(guide: dict, role: str) -> int:
        return L.resolve_type_entry(lg, role, Fraction(1)).spacing_emu

    return {"text_width_emu": text_width_emu, "line_pitch_emu": line_pitch_emu,
            "paragraph_spacing_emu": paragraph_spacing_emu, "fit_epsilon_emu": ruler.fit_epsilon_emu}


def with_api(guide_raw: dict, api: dict[str, Any]) -> dict:
    """The guide a component receives: a shallow copy carrying `_api`, so the build's
    own guide dict stays JSON-serialisable."""
    return {**guide_raw, "_api": api}


def main(argv: list[str]) -> int:
    """component_api.py guide.json role text...: print the measured width and pitch,
    so an author can check a figure by hand."""
    import json
    if len(argv) < 3:
        print(__doc__)
        return 2
    guide = json.loads(Path(argv[0]).read_text())
    api = make_api(guide)
    role = argv[1]
    for text in argv[2:]:
        print(json.dumps({"role": role, "text": text, "text_width_emu": api["text_width_emu"](guide, role, text),
                          "line_pitch_emu": api["line_pitch_emu"](guide, role), "fit_epsilon_emu": api["fit_epsilon_emu"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
