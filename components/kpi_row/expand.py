"""KPI row: figures with their labels, ranked, never tiled.

Ported from deckgen fixtures/components/kpi_row (seed 2A-3). The first metric leads
(type.emphasis, color.accent1); the rest are its comparison (type.body, base ink);
labels are type.caption in color.ink_muted. No panels, no fills, no equal-weight tiles:
"icon + number + label KPI tiles" is a named generated-deck tell
(references/design/deliberate_composition.md), and both arrangements here are its
counter-example, the figures read as a table with one dominant.

Two arrangements: `horizontal` sets the figures side by side on one line with each
label beneath its figure; `stacked` turns the row on its side into label-left,
figure-right lines.

WHICH RULE PICKS THE VARIANT: deckgen's rule, with parts = the metric count,

    parts >= 2 and width // parts >= height

AND, added here, every figure must measure onto one line in its horizontal column
(guide["_api"]["text_width_emu"] plus the ruler's fit epsilon, against the column
width after the gutters). A figure is never wrapped: a box that passes deckgen's
aspect test but cannot hold the widest figure gets `stacked`. An explicit
`data["variant"]` wins; `horizontal` with fewer than two metrics is refused.

Both arrangements are flex, not deckgen's grid: grid tracks are uniform
(scripts/layout.py), so a two-row grid gives the label row the same height as the
figure row whatever either holds, and an n x 2 grid gives the figure column half the
width. Here the stacked figure column is exactly as wide as the widest figure
measures, and the label takes the rest.
"""

from __future__ import annotations

VARIANTS = ("horizontal", "stacked")
LEAD_INDEX = 0


def _wide_fits(parts: int, box: dict) -> bool:
    if parts < 2:
        return False
    return box["width_emu"] // parts >= box["height_emu"]


def _step(guide: dict, role: str) -> int:
    # the three spellings layout.py's guide reader accepts: {"emu"}, {"value"}, a bare int
    entry = guide["spacing"]["steps"][role]
    if isinstance(entry, dict):
        return int(entry["emu"] if "emu" in entry else entry["value"])
    return int(entry)


def _figure_role(i: int) -> str:
    return "type.emphasis" if i == LEAD_INDEX else "type.body"


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "kpi")
    metrics = [(str(m["label"]), str(m["value"])) for m in data["metrics"]]
    if not metrics:
        raise ValueError("kpi_row needs at least one metric")
    api = guide["_api"]
    eps = int(api["fit_epsilon_emu"])
    widths = [api["text_width_emu"](guide, _figure_role(i), v) + eps for i, (_, v) in enumerate(metrics)]
    n = len(metrics)
    gutter = _step(guide, "space.md")
    column_w = (box["width_emu"] - (n - 1) * gutter) // n
    requested = data.get("variant")
    if requested is not None:
        if requested not in VARIANTS:
            raise ValueError(f"unknown kpi_row variant {requested!r}")
        if requested == "horizontal" and n < 2:
            raise ValueError("variant 'horizontal' needs at least two metrics")
        variant = str(requested)
    else:
        variant = "horizontal" if _wide_fits(n, box) and max(widths) <= column_w else "stacked"

    def figure(i: int, value: str, width: int | None) -> dict:
        para = {"role": _figure_role(i), "text": value}
        if i == LEAD_INDEX:
            para["ink_role"] = "color.accent1"
        node = {"type": "element", "id": f"{pid}-figure{i}", "kind": "text", "paragraphs": [para]}
        if width is not None:
            node["size"] = {"width_emu": width, "height_emu": None}
        return node

    def label(i: int, text: str, weight: float | None) -> dict:
        node = {"type": "element", "id": f"{pid}-label{i}", "kind": "text",
                "paragraphs": [{"role": "type.caption", "text": text, "ink_role": "color.ink_muted"}]}
        if weight is not None:
            node["weight"] = weight
        return node

    if variant == "horizontal":
        columns = [{"type": "region", "id": f"{pid}-col{i}", "weight": 1.0,
                    "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": None, "align": "stretch", "justify": "start"},
                    "children": [figure(i, v, None), label(i, lab, None)]} for i, (lab, v) in enumerate(metrics)]
        return {"type": "region", "id": pid,
                "layout": {"kind": "flex", "direction": "row", "gap_role": "space.md", "pad_role": None, "align": "start", "justify": "start"},
                "children": columns}
    figure_w = max(widths)
    rows = [{"type": "region", "id": f"{pid}-row{i}",
             "layout": {"kind": "flex", "direction": "row", "gap_role": "space.md", "pad_role": None, "align": "start", "justify": "start"},
             "children": [label(i, lab, 1.0), figure(i, v, figure_w)]} for i, (lab, v) in enumerate(metrics)]
    return {"type": "region", "id": pid,
            "layout": {"kind": "flex", "direction": "column", "gap_role": "space.sm", "pad_role": None, "align": "stretch", "justify": "start"},
            "children": rows}
