"""Football field: valuation ranges on one shared axis, as flex weights.

Every bar is a row of weighted children (space before, the range, space after) whose
weights are the data's own numbers, so the bars line up on one axis in any box. Bar
height and gaps are spacing steps read from the guide; type sizes are roles. Two
variants: `wide` (a label column beside the bars, a value column after them) and
`compact` (the value inside the label, above a thinner bar). `data["variant"]` asks for
one; otherwise the variant is chosen by what fits, and the report says which and why.

The marker (the offer, the current price) is the page's claim, so it is drawn: a thin
vertical rule at its value in the label row and inside every bar row, split out of
the bar's own range where it crosses it, so the rules stack into one line down the
field. It takes the first accent that reads on the page ground at 3:1 (component_api
`reading_role`, as kpi_row picks its lead): numbering is the extractor's, by usage, and
keybank's accent1 is a light grey at 1.5:1 on white. The bands take the first other
accent. Figures are written at the data's own precision: a format that would round 12.4
to 12 is refused.

Every role and every constant is open: `data["roles"]` and `data["params"]` (component_api
`choices`); each default left in place, and each role computed, is in the report. The
params are design choices, not measurements: the label column's share of the row, the
lines a wide label may take, the narrowest wide box, the widest value column, the
marker's width.

Text is measured with guide["_api"] (the solver's ruler) and nothing else: expand
refuses to run without it, since an estimate wrapped "$8.2 to $12.4" before the API
existed.
"""

from __future__ import annotations

EMU_PER_PT = 12700
VARIANTS = ("wide", "compact")
#: the roles; None where the default is computed from the guide (reported as computed)
ROLES = {"band": None, "marker": None, "label": "type.body", "caption": None, "marker_label": None, "axis_rule": "color.rule",
         "gap": "space.xs", "bar": "space.sm", "bar_compact": "space.xs"}
#: today's constants (design choices, not measurements)
PARAMS = {"label_share": 0.42, "max_label_lines": 2, "wide_min_width_emu": 3_000_000, "value_share_max": 0.25, "marker_width_pt": 1.5}
ACCENTS = ("color.accent1", "color.accent2", "color.accent3", "color.accent4")


def _first_role(guide: dict, names: tuple[str, ...], what: str) -> str:
    roles = guide.get("typography", {}).get("roles", {})
    found = next((n for n in names if n in roles), None)
    if found is None:
        raise ValueError(f"no {what} role: the guide defines none of {list(names)}; give roles.{what}")
    return found


def _measurer(guide: dict):
    """width(role, text) -> int EMU that holds `text` on one line in `role` at scale 1.00:
    the solver's own measurement plus its fit epsilon (component_api)."""
    api = guide.get("_api")
    if not api:
        raise ValueError("football_field measures its text with guide['_api'] (component_api); build_deck and component.py pass it, "
                         "and nothing estimates a width in its place")
    eps = int(api["fit_epsilon_emu"])
    return lambda role, text: int(api["text_width_emu"](guide, role, text)) + eps


def _wrapped_lines(width, role: str, text: str, budget: int) -> int:
    """Lines `text` takes at `budget` EMU, breaking at spaces, each candidate line
    measured whole (never a sum of word widths: kerning)."""
    lines, line = 1, ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if line and width(role, candidate) > budget:
            lines, line = lines + 1, word
        else:
            line = candidate
    return lines


def _spacer(nid: str, weight: float) -> dict | None:
    return {"type": "element", "id": nid, "kind": "image", "weight": weight, "_spacer": True} if weight > 0 else None


def _decimals(values: list[float]) -> int:
    out = 0
    for v in values:
        text = repr(float(v))
        if "." in text and not text.endswith(".0"):
            out = max(out, len(text.split(".")[1]))
    return min(out, 4)


def _formatter(fmt: str, values: list[float]):
    """The given format, unless it drops a significant digit of any value; then the
    data's own precision with the same prefix and suffix (a `$` or `x` survives)."""
    def faithful(f: str) -> bool:
        try:
            return all(abs(float(f.format(v).strip("$x% ,").replace(",", "")) - float(v)) < 1e-9 for v in values)
        except (ValueError, KeyError, IndexError):
            return False
    if faithful(fmt):
        return lambda v: fmt.format(v)
    d = _decimals(values)
    prefix = fmt.split("{")[0] if "{" in fmt else ""
    suffix = fmt.split("}")[-1] if "}" in fmt else ""
    return lambda v: f"{prefix}{v:,.{d}f}{suffix}"


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "ff")
    width = _measurer(guide)
    api = guide["_api"]
    roles, report = api["choices"](data, "roles", ROLES, "football_field")
    params, taken = api["choices"](data, "params", PARAMS, "football_field")
    report += taken
    axis = data["axis"]
    lo, hi = float(axis["min"]), float(axis["max"])
    rows = data["rows"]
    values = [float(r["low"]) for r in rows] + [float(r["high"]) for r in rows]
    fmt = _formatter(axis.get("format", "{:,.1f}"), values)
    xs = api["space_emu"](guide, roles["gap"])
    for slot, names in (("caption", ("type.caption", "type.footnote")), ("marker_label", ("type.data_label", "type.emphasis", "type.caption"))):
        if roles[slot] is None:
            roles[slot] = _first_role(guide, names, slot)
            report.append(f"roles.{slot}: {roles[slot]}, the first of {list(names)} the guide defines")
    caption, marker_role = roles["caption"], roles["marker_label"]
    colour_roles = guide.get("color", {}).get("roles", {})
    if roles["marker"] is None:
        found = api["reading_role"](guide, ACCENTS, ["color.surface"])
        roles["marker"] = found[0] if found else "color.ink"
        report.append(f"roles.marker: {roles['marker']}, " + (f"the first accent that reads on color.surface ({found[1]['color.surface']}:1)" if found
                                                               else "since no accent reads on color.surface at 3:1"))
    if roles["band"] is None:
        roles["band"] = next((a for a in ACCENTS if a in colour_roles and a != roles["marker"]), None)
        if roles["band"] is None:
            raise ValueError("no accent but the marker's for the bands; give roles.band")
        report.append(f"roles.band: {roles['band']}, the first other accent; the marker reads {api['contrast'](guide, roles['marker'], roles['band']):.2f}:1 against it")
    band_role, marker_fill = roles["band"], roles["marker"]
    marker_w = round(float(params["marker_width_pt"]) * EMU_PER_PT)
    if marker_w <= 0:
        raise ValueError(f"params.marker_width_pt {params['marker_width_pt']!r} draws nothing")
    share = float(params["label_share"])
    if not 0 < share < 1:
        raise ValueError(f"params.label_share {share!r} is the label column's share of the row, between 0 and 1")
    # the value column is sized to its longest figure as the solver measures it, never a
    # weight share: "$8.2 to $12.4" wrapped to two lines at 18% of a half page
    value_w = max(width(caption, f"{fmt(float(r['low']))} to {fmt(float(r['high']))}") for r in rows)
    # the wide variant's label column, and how many lines each label takes in it (greedy
    # word wrap over whole measured candidate lines). Wide needs every label in at most
    # max_label_lines and the measured rows, marker, axis and ticks inside the box height;
    # a value column over value_share_max of the box, or a box under wide_min_width_emu, is
    # compact too.
    label_col = int(share * (box["width_emu"] - value_w - 2 * xs))
    body_pitch = api["line_pitch_emu"](guide, roles["label"])
    sm = api["space_emu"](guide, roles["bar"])
    label_lines = [_wrapped_lines(width, roles["label"], str(r["label"]), label_col) for r in rows]
    needed = (sum(max(k * body_pitch, sm) + xs for k in label_lines) + api["line_pitch_emu"](guide, marker_role)
              + api["line_pitch_emu"](guide, caption) + 3 * xs)
    reasons = [why for cond, why in (
        (box["height_emu"] < needed, f"the wide rows need {needed} EMU and the box is {box['height_emu']} EMU tall"),
        (box["width_emu"] < params["wide_min_width_emu"], f"the box is {box['width_emu']} EMU wide, under params.wide_min_width_emu {params['wide_min_width_emu']}"),
        (value_w > params["value_share_max"] * box["width_emu"], f"the value column measures {value_w} EMU, over params.value_share_max {params['value_share_max']} of the box"),
        (max(label_lines) > params["max_label_lines"], f"a label takes {max(label_lines)} lines in the label column, over params.max_label_lines {params['max_label_lines']}"),
    ) if cond]
    requested = data.get("variant")
    if requested is not None:
        if requested not in VARIANTS:
            raise ValueError(f"unknown football_field variant {requested!r}; it draws {list(VARIANTS)}")
        compact = requested == "compact"
        report.insert(0, f"variant {requested}: asked for by the data" + (f" (the box would have chosen compact: {'; '.join(reasons)})" if reasons and not compact else ""))
    else:
        compact = bool(reasons)
        report.insert(0, f"variant compact: {'; '.join(reasons)}" if compact else "variant wide: every label, row, marker, axis and tick line fits the box")
    label_role = caption if compact else roles["label"]
    bar_h = api["space_emu"](guide, roles["bar_compact"]) if compact else sm
    m = data.get("marker")
    mv = float(m["value"]) if m else None
    marker_in_axis = mv is not None and lo <= mv <= hi
    # wide rows are label (label_share), track (the rest), value (fixed) with two gaps; the
    # flex row shares what the value and gaps leave by weight
    track_w = box["width_emu"] if compact else int((1 - share) * (box["width_emu"] - value_w - 2 * xs))
    track_w = max(1, track_w)

    def marker(nid: str, height: int | None) -> dict:
        return {"type": "element", "id": nid, "kind": "rect", "fill_role": marker_fill,
                "size": {"width_emu": marker_w, "height_emu": height}}

    def bar(i: int, low: float, high: float) -> dict:
        """[space][range][space] with the marker rule cut in wherever its value falls."""
        parts: list[tuple[str, float, dict | None]] = []  # (what, weight, rect spec)
        if marker_in_axis and mv < low:
            parts += [("sp", mv - lo, None), ("mk", 0, None), ("sp", low - mv, None), ("rng", high - low, None), ("sp", hi - high, None)]
        elif marker_in_axis and low <= mv <= high:
            parts += [("sp", low - lo, None), ("rng", mv - low, None), ("mk", 0, None), ("rng", high - mv, None), ("sp", hi - high, None)]
        elif marker_in_axis:
            parts += [("sp", low - lo, None), ("rng", high - low, None), ("sp", mv - high, None), ("mk", 0, None), ("sp", hi - mv, None)]
        else:
            parts += [("sp", low - lo, None), ("rng", high - low, None), ("sp", hi - high, None)]
        children = []
        k = 0
        for what, weight, _ in parts:
            k += 1
            if what == "sp":
                c = _spacer(f"{pid}-b{i}s{k}", max(0.0, weight))
            elif what == "rng":
                if weight <= 0:
                    continue
                c = {"type": "element", "id": f"{pid}-b{i}r{k}", "kind": "rect", "weight": weight, "fill_role": band_role,
                     "size": {"width_emu": None, "height_emu": bar_h}}
            else:
                c = marker(f"{pid}-b{i}m", None)  # stretched to the row: the rules stack into one line
            if c:
                children.append(c)
        return {"type": "region", "id": f"{pid}-bar{i}", "weight": 1.0,
                "layout": {"kind": "flex", "direction": "row", "gap_role": None, "pad_role": None, "align": "stretch", "justify": "start"},
                "children": children}

    children = []
    if m and marker_in_axis:
        label_h = api["line_pitch_emu"](guide, marker_role)
        # the leading space is the gap between rule and label, so it is measured with it
        mlabel_w = width(marker_role, f" {m['label']}")
        units_per_emu = (hi - lo) / track_w
        need_units = mlabel_w * units_per_emu
        label = {"type": "element", "id": f"{pid}-mlabel", "kind": "text", "size": {"width_emu": mlabel_w, "height_emu": None},
                 "paragraphs": [{"role": marker_role, "text": f" {m['label']}"}]}
        if hi - mv >= need_units:
            # the label reads to the right of the rule
            mchildren = [_spacer(f"{pid}-msp", mv - lo), marker(f"{pid}-mrule", label_h), label, _spacer(f"{pid}-msq", max(0.0, hi - mv - need_units))]
        else:
            # no room on the right: the label sits left of the rule, right-aligned
            label["paragraphs"][0]["text"] = f"{m['label']} "
            label["paragraphs"][0]["align"] = "right"
            mchildren = [_spacer(f"{pid}-msp", max(0.0, mv - lo - need_units)), label, marker(f"{pid}-mrule", label_h), _spacer(f"{pid}-msq", hi - mv)]
        children.append({"type": "region", "id": f"{pid}-marker",
                         "layout": {"kind": "flex", "direction": "row", "gap_role": None, "pad_role": None, "align": "end", "justify": "start"},
                         "children": [c for c in mchildren if c]})
    for i, r in enumerate(rows):
        low, high = float(r["low"]), float(r["high"])
        text = f"{r['label']}: {fmt(low)} to {fmt(high)}" if compact else r["label"]
        label = {"type": "element", "id": f"{pid}-lbl{i}", "kind": "text", "weight": share,
                 "paragraphs": [{"role": label_role, "text": text}]}
        track = bar(i, low, high)
        if compact:
            row = {"type": "region", "id": f"{pid}-row{i}",
                   "layout": {"kind": "flex", "direction": "column", "gap_role": roles["gap"], "pad_role": None, "align": "stretch", "justify": "start"},
                   "children": [label, track]}
        else:
            value = {"type": "element", "id": f"{pid}-val{i}", "kind": "text", "size": {"width_emu": value_w, "height_emu": None},
                     "paragraphs": [{"role": caption, "text": f"{fmt(low)} to {fmt(high)}"}]}
            track["weight"] = 1 - share
            row = {"type": "region", "id": f"{pid}-row{i}",
                   "layout": {"kind": "flex", "direction": "row", "gap_role": roles["gap"], "pad_role": None, "align": "center", "justify": "start"},
                   "children": [label, track, value]}
        children.append(row)
    # the axis and its ticks span exactly the bars' track, so they mirror a row's structure.
    # Tick k labels the start of interval k (left-aligned); the last interval is split in
    # two so the final tick can sit right-aligned at the track's end. A tick label that
    # would not fit its interval on one line is dropped (its spacer keeps the scale).
    ticks = [float(t) for t in (axis.get("ticks") or [lo, hi])]
    units_per_emu = (hi - lo) / track_w
    tick_cells = []
    for k in range(len(ticks) - 1):
        span = max(0.0001, ticks[k + 1] - ticks[k])
        last = k == len(ticks) - 2
        # a tick label needs its measured width plus the gap role, so neighbours never touch
        label_units = (width(caption, fmt(ticks[k])) + xs) * units_per_emu
        if last:
            # the final tick is the axis maximum and always drawn: it takes the units its
            # label needs (right-aligned); the tick before it is kept only if room remains
            end_units = min(span, max(span / 2, (width(caption, fmt(ticks[k + 1])) + xs) * units_per_emu))
            rest = span - end_units
            if rest >= label_units:
                tick_cells.append({"type": "element", "id": f"{pid}-tk{k}", "kind": "text", "weight": rest,
                                   "paragraphs": [{"role": caption, "text": fmt(ticks[k]), "align": "left"}]})
            elif rest > 0:
                tick_cells.append(_spacer(f"{pid}-tk{k}", rest))
            tick_cells.append({"type": "element", "id": f"{pid}-tk{k + 1}", "kind": "text", "weight": end_units,
                               "paragraphs": [{"role": caption, "text": fmt(ticks[k + 1]), "align": "right"}]})
        elif span >= label_units or k == 0:
            tick_cells.append({"type": "element", "id": f"{pid}-tk{k}", "kind": "text", "weight": span,
                               "paragraphs": [{"role": caption, "text": fmt(ticks[k]), "align": "left"}]})
        else:
            tick_cells.append(_spacer(f"{pid}-tk{k}", span))
    tick_track = {"type": "region", "id": f"{pid}-ticktrack", "weight": 1.0,
                  "layout": {"kind": "flex", "direction": "row", "gap_role": None, "pad_role": None, "align": "start", "justify": "start"},
                  "children": [c for c in tick_cells if c]}
    axis_track = {"type": "element", "id": f"{pid}-axis", "kind": "rule", "line_role": roles["axis_rule"], "weight": 1.0, "size": {"width_emu": None, "height_emu": 1}}

    def tracked(track: dict, rid: str) -> dict:
        """The same label / track / value structure as a bar row, so the rule, the ticks and
        the marker sit exactly over the bars' track."""
        if compact:
            return track
        right = {"type": "element", "id": f"{rid}-r", "kind": "image", "_spacer": True, "size": {"width_emu": value_w, "height_emu": 1}}
        return {"type": "region", "id": rid, "layout": {"kind": "flex", "direction": "row", "gap_role": roles["gap"], "pad_role": None, "align": "start", "justify": "start"},
                "children": [c for c in (_spacer(f"{rid}-l", share), dict(track, weight=1 - share), right) if c]}

    if m and marker_in_axis:
        children[0] = tracked(children[0], f"{pid}-markerrow")
    children.append(tracked(axis_track, f"{pid}-axisrow"))
    children.append(tracked(tick_track, f"{pid}-tickrow"))
    return {"type": "region", "id": pid, "report": report,
            "layout": {"kind": "flex", "direction": "column", "gap_role": roles["gap"], "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
