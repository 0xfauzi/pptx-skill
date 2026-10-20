"""Bullet stack: a list of co-equal points, in one column or in two.

Ported from deckgen fixtures/components/bullet_stack (seed 2A-3). Two arrangements:
`single_column` reads straight down; `two_column` is a flex ROW of two flex columns of
ceil(n/2) items, filled DOWN the first column and then across, so the order the writer
chose survives the reflow (filling across would reorder the argument).

WHICH RULE PICKS THE VARIANT: deckgen's one selection rule, unchanged,

    parts >= 2 and width // parts >= height      (parts = 2 columns)

so two columns only when each column would be at least as wide as the box is tall. It
compares the box's own two sides and carries no EMU threshold. A list of one item is
always single_column. An explicit `data["variant"]` wins; `two_column` with fewer items
than columns is refused rather than swapped.

Columns of flex, not a grid: grid tracks are uniform (scripts/layout.py), so one long
item would make every row as tall as itself; in a flex column each item costs its own
measured height and nothing else. Items are separate text elements, not one element
of paragraphs, so the two-column split never cuts inside a text body.
"""

from __future__ import annotations

WIDE_COLUMNS = 2
VARIANTS = ("single_column", "two_column")


def _wide_fits(parts: int, box: dict) -> bool:
    if parts < 2:
        return False
    return box["width_emu"] // parts >= box["height_emu"]


def select_variant(items: list[str], data: dict, box: dict) -> str:
    requested = data.get("variant")
    if requested is not None:
        if requested not in VARIANTS:
            raise ValueError(f"unknown bullet_stack variant {requested!r}")
        if requested == "two_column" and len(items) < WIDE_COLUMNS:
            raise ValueError("variant 'two_column' needs at least one item per column")
        return str(requested)
    if len(items) < WIDE_COLUMNS:
        return "single_column"
    return "two_column" if _wide_fits(WIDE_COLUMNS, box) else "single_column"


def _column(nid: str, children: list[dict], weight: float | None = None) -> dict:
    node = {"type": "region", "id": nid,
            "layout": {"kind": "flex", "direction": "column", "gap_role": "space.sm", "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
    if weight is not None:
        node["weight"] = weight
    return node


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "bs")
    items = [str(t) for t in data["items"]]
    if not items:
        raise ValueError("bullet_stack needs at least one item; an empty list draws nothing")
    variant = select_variant(items, data, box)
    elements = [{"type": "element", "id": f"{pid}-item{i}", "kind": "text",
                 "paragraphs": [{"role": "type.body", "text": t, "bullet_level": 0}]} for i, t in enumerate(items)]
    if variant == "single_column":
        return dict(_column(pid, elements))
    rows = (len(elements) + WIDE_COLUMNS - 1) // WIDE_COLUMNS
    columns = [_column(f"{pid}-col{c}", elements[c * rows:(c + 1) * rows], 1.0) for c in range(WIDE_COLUMNS)]
    return {"type": "region", "id": pid,
            "layout": {"kind": "flex", "direction": "row", "gap_role": "space.md", "pad_role": None, "align": "start", "justify": "start"},
            "children": [c for c in columns if c["children"]]}
