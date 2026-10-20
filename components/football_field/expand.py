"""Football field: valuation ranges on one shared axis, as flex weights.

Every bar is a row of weighted children (space before, the range, space after) whose
weights are the data's own numbers, so the bars line up on one axis in any box. Bar
height and gaps are spacing steps read from the guide; type sizes are roles. The
variant is chosen by what fits: a roomy box gets a label column beside the bars, a
tight one puts the value inside the label and the thinnest bar the guide allows.

The marker (the offer, the current price) is the page's claim, so it is drawn: a thin
vertical rule at its value in the label row and inside every bar row, split out of
the bar's own range where it crosses it, so the rules stack into one line down the
field. Bands take one muted role; the accent is spent on the marker. Figures are
written at the data's own precision: a format that would round 12.4 to 12 is refused.
"""

from __future__ import annotations

EMU_PER_PT = 12700
MARKER_W_EMU = 19050  # 1.5pt


def _step(guide: dict, role: str, fallback_role: str) -> int:
    steps = guide.get("spacing", {}).get("steps", {})
    entry = steps.get(role) or steps.get(fallback_role) or {}
    return int(entry.get("emu", 0)) or 91440


def _role(guide: dict, *names: str) -> str:
    roles = guide.get("typography", {}).get("roles", {})
    return next((n for n in names if n in roles), "type.body")


def _pitch(guide: dict, role: str) -> int:
    spec = guide.get("typography", {}).get("roles", {}).get(role) or guide["typography"]["roles"]["type.body"]
    return int(round((spec.get("line_spacing") or 1.2) * float(spec["size_pt"]) * EMU_PER_PT))


def _size_pt(guide: dict, role: str) -> float:
    spec = guide.get("typography", {}).get("roles", {}).get(role) or guide["typography"]["roles"]["type.body"]
    return float(spec["size_pt"])


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
    axis = data["axis"]
    lo, hi = float(axis["min"]), float(axis["max"])
    rows = data["rows"]
    values = [float(r["low"]) for r in rows] + [float(r["high"]) for r in rows]
    fmt = _formatter(axis.get("format", "{:,.1f}"), values)
    xs, sm = _step(guide, "space.xs", "space.sm"), _step(guide, "space.sm", "space.xs")
    n = len(rows)
    caption = _role(guide, "type.caption", "type.footnote")
    marker_role = _role(guide, "type.data_label", "type.emphasis", "type.caption")
    band_role = "color.accent2" if "color.accent2" in guide.get("color", {}).get("roles", {}) else "color.accent1"
    marker_fill = "color.accent1"
    roomy_row = max(_pitch(guide, "type.body"), sm) + xs
    needed = roomy_row * n + _pitch(guide, marker_role) + _pitch(guide, caption) + 3 * xs
    em = _size_pt(guide, caption) * EMU_PER_PT
    # the value column is sized to its longest figure (0.6 em per character plus one),
    # never a weight share: "$8.2 to $12.4" wrapped to two lines at 18% of a half page
    value_w = int((max(len(f"{fmt(float(r['low']))} to {fmt(float(r['high']))}") for r in rows) + 1) * 0.6 * em)
    compact = box["height_emu"] < needed or box["width_emu"] < 3_000_000 or value_w > 0.25 * box["width_emu"]
    label_role = caption if compact else "type.body"
    bar_h = xs if compact else sm
    m = data.get("marker")
    mv = float(m["value"]) if m else None
    marker_in_axis = mv is not None and lo <= mv <= hi
    track_w = box["width_emu"] if compact else box["width_emu"] - value_w - int(0.42 / 1.0 * box["width_emu"]) - 2 * xs
    track_w = max(1, track_w)

    def marker(nid: str, height: int | None) -> dict:
        return {"type": "element", "id": nid, "kind": "rect", "fill_role": marker_fill,
                "size": {"width_emu": MARKER_W_EMU, "height_emu": height}}

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
        label_h = _pitch(guide, marker_role)
        mlabel_w = (len(m["label"]) + 2) * 0.6 * _size_pt(guide, marker_role) * EMU_PER_PT
        units_per_emu = (hi - lo) / track_w
        need_units = mlabel_w * units_per_emu
        label = {"type": "element", "id": f"{pid}-mlabel", "kind": "text", "size": {"width_emu": int(mlabel_w), "height_emu": None},
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
        label = {"type": "element", "id": f"{pid}-lbl{i}", "kind": "text", "weight": 0.42,
                 "paragraphs": [{"role": label_role, "text": text}]}
        track = bar(i, low, high)
        if compact:
            row = {"type": "region", "id": f"{pid}-row{i}",
                   "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": None, "align": "stretch", "justify": "start"},
                   "children": [label, track]}
        else:
            value = {"type": "element", "id": f"{pid}-val{i}", "kind": "text", "size": {"width_emu": value_w, "height_emu": None},
                     "paragraphs": [{"role": caption, "text": f"{fmt(low)} to {fmt(high)}"}]}
            track["weight"] = 0.58
            row = {"type": "region", "id": f"{pid}-row{i}",
                   "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "center", "justify": "start"},
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
        label_units = (len(fmt(ticks[k])) + 1) * 0.6 * em * units_per_emu
        if last:
            # the final tick is the axis maximum and always drawn: it takes the units its
            # label needs (right-aligned); the tick before it is kept only if room remains
            end_units = min(span, max(span / 2, (len(fmt(ticks[k + 1])) + 1) * 0.6 * em * units_per_emu))
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
    axis_track = {"type": "element", "id": f"{pid}-axis", "kind": "rule", "line_role": "color.rule", "weight": 1.0, "size": {"width_emu": None, "height_emu": 1}}

    def tracked(track: dict, rid: str) -> dict:
        """The same label / track / value structure as a bar row, so the rule, the ticks and
        the marker sit exactly over the bars' track."""
        if compact:
            return track
        right = {"type": "element", "id": f"{rid}-r", "kind": "image", "_spacer": True, "size": {"width_emu": value_w, "height_emu": 1}}
        return {"type": "region", "id": rid, "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "start", "justify": "start"},
                "children": [c for c in (_spacer(f"{rid}-l", 0.42), dict(track, weight=0.58), right) if c]}

    if m and marker_in_axis:
        children[0] = tracked(children[0], f"{pid}-markerrow")
    children.append(tracked(axis_track, f"{pid}-axisrow"))
    children.append(tracked(tick_track, f"{pid}-tickrow"))
    return {"type": "region", "id": pid, "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
