"""Bullet stack: a list of co-equal points, in one column or in two.

Two arrangements:
`single_column` reads straight down; `two_column` is a flex ROW of two flex columns of
ceil(n/2) items, filled DOWN the first column and then across, so the order the writer
chose survives the reflow (filling across would reorder the argument).

WHICH RULE PICKS THE VARIANT: one selection rule,

    parts >= 2 and width // parts >= height      (parts = 2 columns)

so two columns only when each column would be at least as wide as the box is tall. It
compares the box's own two sides and carries no EMU threshold. A list of one item is
always single_column. An explicit `data["variant"]` wins; `two_column` with fewer items
than columns is refused rather than swapped.

The item role, the gaps and the bullet are open through `data["roles"]` and
`data["bullet_level"]` (null sets the items without a bullet); each default left in place
is in the component's report, with the variant and why.

Columns of flex, not a grid: grid tracks are uniform (scripts/layout.py), so one long
item would make every row as tall as itself; in a flex column each item costs its own
measured height and nothing else. Items are separate text elements, not one element
of paragraphs, so the two-column split never cuts inside a text body.
"""

from __future__ import annotations

WIDE_COLUMNS = 2
VARIANTS = ("single_column", "two_column")
#: today's constants, each open through data["roles"]
ROLES = {"item": "type.body", "gap": "space.sm", "gutter": "space.md"}
BULLET_LEVEL = 0


def _wide_fits(parts: int, box: dict) -> bool:
    if parts < 2:
        return False
    return box["width_emu"] // parts >= box["height_emu"]


def select_variant(items: list[str], data: dict, box: dict) -> tuple[str, str]:
    requested = data.get("variant")
    if requested is not None:
        if requested not in VARIANTS:
            raise ValueError(f"unknown bullet_stack variant {requested!r}; it draws {list(VARIANTS)}")
        if requested == "two_column" and len(items) < WIDE_COLUMNS:
            raise ValueError("variant 'two_column' needs at least one item per column")
        return str(requested), "asked for by the data"
    if len(items) < WIDE_COLUMNS:
        return "single_column", "one item"
    if _wide_fits(WIDE_COLUMNS, box):
        return "two_column", f"two columns of {box['width_emu'] // WIDE_COLUMNS} EMU are each at least as wide as the box is tall ({box['height_emu']} EMU)"
    return "single_column", f"two columns of {box['width_emu'] // WIDE_COLUMNS} EMU would be narrower than the box is tall ({box['height_emu']} EMU)"


def _column(nid: str, children: list[dict], gap: str, weight: float | None = None) -> dict:
    node = {"type": "region", "id": nid,
            "layout": {"kind": "flex", "direction": "column", "gap_role": gap, "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
    if weight is not None:
        node["weight"] = weight
    return node


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "bs")
    items = [str(t) for t in data["items"]]
    if not items:
        raise ValueError("bullet_stack needs at least one item; an empty list draws nothing")
    roles, report = guide["_api"]["choices"](data, "roles", ROLES, "bullet_stack")
    variant, why = select_variant(items, data, box)
    report.insert(0, f"variant {variant}: {why}")
    level = data.get("bullet_level", BULLET_LEVEL)
    if level is not None and (isinstance(level, bool) or not isinstance(level, int) or level < 0):
        raise ValueError(f"bullet_level is a bullet level (0, 1, ...) or null for none, got {level!r}")
    if "bullet_level" not in data:
        report.append(f"bullet_level: {BULLET_LEVEL} (the default; null sets the items without a bullet)")
    elements = [{"type": "element", "id": f"{pid}-item{i}", "kind": "text",
                 "paragraphs": [{"role": roles["item"], "text": t, "bullet_level": level}]} for i, t in enumerate(items)]
    if variant == "single_column":
        return {**_column(pid, elements, roles["gap"]), "report": report}
    rows = (len(elements) + WIDE_COLUMNS - 1) // WIDE_COLUMNS
    columns = [_column(f"{pid}-col{c}", elements[c * rows:(c + 1) * rows], roles["gap"], 1.0) for c in range(WIDE_COLUMNS)]
    return {"type": "region", "id": pid, "report": report,
            "layout": {"kind": "flex", "direction": "row", "gap_role": roles["gutter"], "pad_role": None, "align": "start", "justify": "start"},
            "children": [c for c in columns if c["children"]]}
