"""KPI row: figures with their labels, a lead among them or none.

By default the first metric
leads (its own type role and the first accent that reads on the ground) and the rest are
its comparison; labels are a caption role in a muted ink. `data["lead"]` names another
metric to lead, or null for co-equal figures. Every role, gap and ink is open through
`data["roles"]` (component_api `choices`), each default left in place reported.

Three arrangements: `horizontal` sets the figures side by side on one line with each
label beneath its figure; `stacked` turns the row on its side into label-left,
figure-right lines; `panel` sets each figure and its label in a filled tile. Panels are
reached only by asking for them (`data["variant"]`): big-number or KPI panels are on 8 of
578 coded corpus pages, none of them bank pages (references/composition.md), and a
rater named "icon + number + label tiles" a generated-deck tell; a figure alone in
a tile must carry its base in its label, so the report asks of what, and for whom.

WHICH RULE PICKS THE VARIANT when none is asked: the bullet_stack rule, with parts = the
metric count,

    parts >= 2 and width // parts >= height

AND, added here, every figure must measure onto one line in its horizontal column
(guide["_api"]["text_width_emu"] plus the ruler's fit epsilon, against the column
width after the gutters). A figure is never wrapped: a box that passes the
aspect test but cannot hold the widest figure gets `stacked`. The choice and its reason
are in the report. `horizontal` or `panel` with fewer than two metrics is refused.

All arrangements are flex, not grid: grid tracks are uniform
(scripts/layout.py), so a two-row grid gives the label row the same height as the
figure row whatever either holds, and an n x 2 grid gives the figure column half the
width. Here the stacked figure column is exactly as wide as the widest figure
measures, and the label takes the rest.
"""

from __future__ import annotations

VARIANTS = ("horizontal", "stacked", "panel")
#: today's constants, each open through data["roles"]; lead_ink and panel_fill have none:
#: the lead's ink is computed (the first accent that reads), a panel's fill is asked
ROLES = {"lead": "type.emphasis", "figure": "type.body", "label": "type.caption", "label_ink": "color.ink_muted",
         "lead_ink": None, "gap": "space.xs", "row_gap": "space.sm", "gutter": "space.md", "panel_fill": None, "panel_pad": "space.sm"}
LEAD_DEFAULT = 0
#: the order the lead's ink is looked for in: the accents by the extractor's numbering (by
#: usage, so accent1 on keybank is a light grey panel fill at 1.5:1 on white)
LEAD_CANDIDATES = ("color.accent1", "color.accent2", "color.accent3", "color.accent4")


def _wide_fits(parts: int, box: dict) -> bool:
    if parts < 2:
        return False
    return box["width_emu"] // parts >= box["height_emu"]


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "kpi")
    metrics = [(str(m["label"]), str(m["value"])) for m in data["metrics"]]
    if not metrics:
        raise ValueError("kpi_row needs at least one metric")
    api = guide["_api"]
    roles, report = api["choices"](data, "roles", ROLES, "kpi_row")
    n = len(metrics)
    lead = data.get("lead", LEAD_DEFAULT)
    if "lead" not in data:
        report.append(f"lead: metric {LEAD_DEFAULT} (the default; null sets the figures co-equal)")
    if lead is not None and (isinstance(lead, bool) or not isinstance(lead, int) or not 0 <= lead < n):
        raise ValueError(f"lead {lead!r} is not a metric index 0..{n - 1} or null")
    requested = data.get("variant")
    if requested is not None and requested not in VARIANTS:
        raise ValueError(f"unknown kpi_row variant {requested!r}; it draws {list(VARIANTS)}")
    if requested == "panel" and not roles["panel_fill"]:
        raise ValueError("variant 'panel' needs roles.panel_fill: a tile's fill has no neutral value")
    ground = roles["panel_fill"] if requested == "panel" else "color.surface"
    if lead is not None and roles["lead_ink"] is None:
        found = api["reading_role"](guide, LEAD_CANDIDATES, [ground])
        if found:
            roles["lead_ink"] = found[0]
            report.append(f"roles.lead_ink: {found[0]}, the first accent that reads on {ground} ({found[1][ground]}:1)")
        else:
            roles["lead_ink"] = "color.ink"
            report.append(f"roles.lead_ink: color.ink: no accent reads on {ground} at 3:1, so the lead's weight alone leads")

    def figure_role(i: int) -> str:
        return roles["lead"] if i == lead else roles["figure"]

    eps = int(api["fit_epsilon_emu"])
    widths = [api["text_width_emu"](guide, figure_role(i), v) + eps for i, (_, v) in enumerate(metrics)]
    gutter = api["space_emu"](guide, roles["gutter"])
    column_w = (box["width_emu"] - (n - 1) * gutter) // n
    if requested is not None:
        if requested in ("horizontal", "panel") and n < 2:
            raise ValueError(f"variant {requested!r} needs at least two metrics")
        variant = str(requested)
        report.append(f"variant {variant}: asked for by the data")
    elif _wide_fits(n, box) and max(widths) <= column_w:
        variant = "horizontal"
        report.append(f"variant horizontal: {n} columns of {column_w} EMU are each at least as wide as the box is tall, and the widest figure measures {max(widths)} EMU")
    else:
        variant = "stacked"
        why = (f"the widest figure measures {max(widths)} EMU against a {column_w} EMU column" if _wide_fits(n, box)
               else f"{n} column(s) of {column_w} EMU would be narrower than the box is tall ({box['height_emu']} EMU)")
        report.append(f"variant stacked: {why}")
    if variant == "panel":
        report.append("panel: each figure stands alone in its tile, so its label carries its base and population: of what, and for whom?")

    def figure(i: int, value: str, width: int | None) -> dict:
        para = {"role": figure_role(i), "text": value}
        if i == lead:
            para["ink_role"] = roles["lead_ink"]
        node = {"type": "element", "id": f"{pid}-figure{i}", "kind": "text", "paragraphs": [para]}
        if width is not None:
            node["size"] = {"width_emu": width, "height_emu": None}
        return node

    def label(i: int, text: str, weight: float | None) -> dict:
        node = {"type": "element", "id": f"{pid}-label{i}", "kind": "text",
                "paragraphs": [{"role": roles["label"], "text": text, "ink_role": roles["label_ink"]}]}
        if weight is not None:
            node["weight"] = weight
        return node

    if variant in ("horizontal", "panel"):
        tile = variant == "panel"
        columns = [{"type": "region", "id": f"{pid}-col{i}", "weight": 1.0, **({"fill_role": roles["panel_fill"]} if tile else {}),
                    "layout": {"kind": "flex", "direction": "column", "gap_role": roles["gap"], "pad_role": roles["panel_pad"] if tile else None,
                               "align": "stretch", "justify": "start"},
                    "children": [figure(i, v, None), label(i, lab, None)]} for i, (lab, v) in enumerate(metrics)]
        return {"type": "region", "id": pid, "report": report,
                "layout": {"kind": "flex", "direction": "row", "gap_role": roles["gutter"], "pad_role": None, "align": "stretch" if tile else "start", "justify": "start"},
                "children": columns}
    figure_w = max(widths)
    rows = [{"type": "region", "id": f"{pid}-row{i}",
             "layout": {"kind": "flex", "direction": "row", "gap_role": roles["gutter"], "pad_role": None, "align": "start", "justify": "start"},
             "children": [label(i, lab, 1.0), figure(i, v, figure_w)]} for i, (lab, v) in enumerate(metrics)]
    return {"type": "region", "id": pid, "report": report,
            "layout": {"kind": "flex", "direction": "column", "gap_role": roles["row_gap"], "pad_role": None, "align": "stretch", "justify": "start"},
            "children": rows}
