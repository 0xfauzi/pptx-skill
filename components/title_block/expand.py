"""Title block: an optional kicker, one dominant claim, and a hairline closing the band.

Ported from deckgen fixtures/components/title_block (seed 2A-3). Two arrangements:
`with_kicker` stacks the kicker over the title in a flex column and closes it with a
hairline; `no_kicker` is the same column without the kicker.

WHICH RULE PICKS THE VARIANT: the data, never the box. A kicker in the data gives
`with_kicker`, none gives `no_kicker`. Dropping a kicker the writer gave to make a
shallow band fit would be silent content loss, and a component has no channel to tell
the writer it did that; if the band is too shallow the solver descends the scale or
refuses, which the build reports. An explicit `data["variant"]` wins, and asking for
`with_kicker` with no kicker is refused rather than swapped.

Kicker over title, not beside it: setting one text beside another needs a flex weight
for kicker against title, and deckgen found no source for that ratio (its 2x2 grid
attempt gave the hairline half the band's height).

The column gap is space.xs, not deckgen's space.sm: on keybank (title 24pt, two lines in
the 8,229,600 x 1,143,000 band) the two space.sm gaps left the block 102,473 EMU over
the band, and the kicker reads as the title's label only when it sits tight to it.
"""

from __future__ import annotations

VARIANTS = ("with_kicker", "no_kicker")


def select_variant(data: dict) -> str:
    kicker = str(data.get("kicker") or "")
    requested = data.get("variant")
    if requested is not None:
        if requested not in VARIANTS:
            raise ValueError(f"unknown title_block variant {requested!r}")
        if requested == "with_kicker" and not kicker:
            raise ValueError("variant 'with_kicker' needs a kicker, and this data carries none")
        return str(requested)
    return "with_kicker" if kicker else "no_kicker"


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "tb")
    variant = select_variant(data)
    children = []
    if variant == "with_kicker":
        children.append({"type": "element", "id": f"{pid}-kicker", "kind": "text",
                         "paragraphs": [{"role": "type.kicker", "text": str(data["kicker"]), "ink_role": "color.ink_muted"}]})
    children.append({"type": "element", "id": f"{pid}-title", "kind": "text",
                     "paragraphs": [{"role": "type.title", "text": str(data["title"])}]})
    # the hairline is a measured extent of one EMU in the column: a rule has a width,
    # never a share of the band
    children.append({"type": "element", "id": f"{pid}-rule", "kind": "rule", "line_role": "color.rule",
                     "size": {"width_emu": None, "height_emu": 1}})
    return {"type": "region", "id": pid,
            "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
