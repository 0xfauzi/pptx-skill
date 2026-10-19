"""Football field: valuation ranges on one shared axis, as flex weights.

Every bar is a row of weighted children (space before, the range, space after) whose
weights are the data's own numbers, so the bars line up on one axis in any box. Bar
height and gaps are spacing steps read from the guide; type sizes are roles. The
variant is chosen by what fits: a roomy box gets a label column beside the bars, a
tight one puts the value inside the label and the thinnest bar the guide allows."""

from __future__ import annotations

EMU_PER_PT = 12700


def _step(guide: dict, role: str, fallback_role: str) -> int:
    steps = guide.get("spacing", {}).get("steps", {})
    entry = steps.get(role) or steps.get(fallback_role) or {}
    return int(entry.get("emu", 0)) or 91440


def _pitch(guide: dict, role: str) -> int:
    spec = guide.get("typography", {}).get("roles", {}).get(role) or guide["typography"]["roles"]["type.body"]
    return int(round((spec.get("line_spacing") or 1.2) * float(spec["size_pt"]) * EMU_PER_PT))


def _spacer(nid: str, weight: float) -> dict | None:
    return {"type": "element", "id": nid, "kind": "image", "weight": weight, "_spacer": True} if weight > 0 else None


def expand(data: dict, box: dict, guide: dict) -> dict:
    pid = data.get("_id", "ff")
    axis = data["axis"]
    lo, hi = float(axis["min"]), float(axis["max"])
    fmt = axis.get("format", "{:,.1f}")
    rows = data["rows"]
    xs, sm = _step(guide, "space.xs", "space.sm"), _step(guide, "space.sm", "space.xs")
    n = len(rows)
    # what the roomy variant needs: one body line per row plus a bar of space.sm, gaps of xs,
    # a marker line and the tick row; if the box is shorter than that, go compact
    roomy_row = max(_pitch(guide, "type.body"), sm) + xs
    needed = roomy_row * n + _pitch(guide, "type.kicker") + _pitch(guide, "type.caption") + 3 * xs
    compact = box["height_emu"] < needed or box["width_emu"] < 3_000_000
    label_role = "type.caption" if compact else "type.body"
    bar_h = xs if compact else sm

    def bar(i: int, low: float, high: float, fill_role: str) -> dict:
        before, length, after = max(0.0, low - lo), max(0.0001, high - low), max(0.0, hi - high)
        children = [_spacer(f"{pid}-sp{i}a", before),
                    {"type": "element", "id": f"{pid}-rng{i}", "kind": "rect", "weight": length, "fill_role": fill_role,
                     "size": {"width_emu": None, "height_emu": bar_h}},
                    _spacer(f"{pid}-sp{i}b", after)]
        return {"type": "region", "id": f"{pid}-bar{i}", "weight": 1.0,
                "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "center", "justify": "start"},
                "children": [c for c in children if c]}

    children = []
    m = data.get("marker")
    if m:
        mv = float(m["value"])
        mchildren = [_spacer(f"{pid}-msp", max(0.0, mv - lo)),
                     {"type": "element", "id": f"{pid}-mlabel", "kind": "text", "weight": max(0.0001, hi - mv),
                      "paragraphs": [{"role": "type.kicker", "text": m["label"]}]}]
        children.append({"type": "region", "id": f"{pid}-marker",
                         "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "end", "justify": "start"},
                         "children": [c for c in mchildren if c]})
    for i, r in enumerate(rows):
        low, high = float(r["low"]), float(r["high"])
        text = f"{r['label']}: {fmt.format(low)} to {fmt.format(high)}" if compact else r["label"]
        label = {"type": "element", "id": f"{pid}-lbl{i}", "kind": "text", "weight": 0.42,
                 "paragraphs": [{"role": label_role, "text": text}]}
        track = bar(i, low, high, "color.accent1" if i % 2 == 0 else "color.accent2")
        if compact:
            row = {"type": "region", "id": f"{pid}-row{i}",
                   "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": None, "align": "stretch", "justify": "start"},
                   "children": [label, track]}
        else:
            value = {"type": "element", "id": f"{pid}-val{i}", "kind": "text", "weight": 0.18,
                     "paragraphs": [{"role": "type.caption", "text": f"{fmt.format(low)} to {fmt.format(high)}"}]}
            track["weight"] = 0.58
            row = {"type": "region", "id": f"{pid}-row{i}",
                   "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "center", "justify": "start"},
                   "children": [label, track, value]}
        children.append(row)
    # the axis and its ticks span exactly the bars' track, so they mirror a row's structure.
    # Tick k labels the start of interval k (left-aligned); the last interval is split in
    # two so the final tick can sit right-aligned at the track's end.
    ticks = [float(t) for t in (axis.get("ticks") or [lo, hi])]
    tick_cells = []
    for k in range(len(ticks) - 1):
        span = max(0.0001, ticks[k + 1] - ticks[k])
        last = k == len(ticks) - 2
        tick_cells.append({"type": "element", "id": f"{pid}-tk{k}", "kind": "text", "weight": span / 2 if last else span,
                           "paragraphs": [{"role": "type.caption", "text": fmt.format(ticks[k]), "align": "left"}]})
        if last:
            tick_cells.append({"type": "element", "id": f"{pid}-tk{k + 1}", "kind": "text", "weight": span / 2,
                               "paragraphs": [{"role": "type.caption", "text": fmt.format(ticks[k + 1]), "align": "right"}]})
    tick_track = {"type": "region", "id": f"{pid}-ticktrack", "weight": 1.0,
                  "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "start", "justify": "start"},
                  "children": tick_cells}
    axis_track = {"type": "element", "id": f"{pid}-axis", "kind": "rule", "line_role": "color.rule", "weight": 1.0, "size": {"width_emu": None, "height_emu": 1}}

    def tracked(track: dict, rid: str) -> dict:
        if compact:
            return track
        return {"type": "region", "id": rid, "layout": {"kind": "flex", "direction": "row", "gap_role": "space.xs", "pad_role": None, "align": "start", "justify": "start"},
                "children": [c for c in (_spacer(f"{rid}-l", 0.42), dict(track, weight=0.58), _spacer(f"{rid}-r", 0.18)) if c]}

    children.append(tracked(axis_track, f"{pid}-axisrow"))
    children.append(tracked(tick_track, f"{pid}-tickrow"))
    return {"type": "region", "id": pid, "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": None, "align": "stretch", "justify": "start"},
            "children": children}
