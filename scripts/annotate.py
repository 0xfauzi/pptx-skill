#!/usr/bin/env python3
"""The annotation layer: shapes placed on an exhibit at positions in its own data.

A slide's `annotations` list is resolved after the page is solved, against the solved
boxes of their hosts. Each annotation becomes ordinary page elements (rect, rule, text)
that the emitter draws, the contrast gate scores and the emitted-fit check re-measures;
nothing here draws, and nothing here decides what to annotate.

    {"id": "subject", "host": "comps", "kind": "outline_box", "anchor": {"row": 3},
     "line_role": "color.accent2", "line_width_pt": 1.5, "pad_role": "space.xs"}

Kinds (each a measured move, TARGET_SPEC Appendix A.6): outline_box, band, reference_line,
arrow, callout, bracket, badge. Anchors on a chart (chart_geometry.py, which needs
plot_area and the axes' min, max and cross_between): point {series, category} or
{series, index} on XY; categories [i, j]; category i (a line at its centre: an event
marker); value v; values [a, b]; region {categories, values} or {x, y}. On a table (the
solver's fitted column widths and row heights): cell [r, c], cells [[r0, c0], [r1, c1]],
row r, rows [r0, r1], column c, columns [c0, c1], header_group {row, columns}; body
rows count from 0 as `rows` lists them, header rows only through header_group.

Placement is computed from the anchor, the kind's closed set of positions and the
spacing roles the spec names. A choice the spec leaves out is written as the neutral
value in DEFAULTS and listed in the report's `defaults_taken`; a choice with no neutral
value (a colour, a stroke width, which side, how far) is required and refused by name.

The collision contract (TARGET_SPEC 15.3): an annotation may overlap only its anchor
(its host). It may not cover another page element, another annotation, the page edge
or a reserved chrome zone (checked here, from the solved boxes), nor the host's own
text: tick labels, data labels, legend (checked after the render, from the words
LibreOffice drew: render_check). A band is ground, drawn under its host, and is not a
cover; the contrast gate scores every label and table row on it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L  # noqa: E402
from chart_geometry import ChartGeometry, GeometryRefused, table_geometry  # noqa: E402
from emit_pptx import DASHES, Guide as EmitGuide  # noqa: E402

EMU_PER_PT = 12_700

KINDS = ("outline_box", "band", "reference_line", "arrow", "callout", "bracket", "badge")
COMMON_KEYS = {"id", "host", "kind", "anchor"}
KIND_KEYS = {
    "outline_box": {"line_role", "line_width_pt", "dash", "pad_role", "shape"},
    "band": {"fill_role", "label", "pad_role"},
    "reference_line": {"line_role", "line_width_pt", "dash", "label", "gap_role"},
    "arrow": {"line_role", "line_width_pt", "dash", "label", "position", "gap_role"},
    "callout": {"line_role", "line_width_pt", "fill_role", "label", "position", "gap_role", "pad_role", "head"},
    "bracket": {"line_role", "line_width_pt", "style", "side", "gap_role", "depth_role", "label"},
    "badge": {"fill_role", "label", "position", "gap_role", "pad_role"},
}
REQUIRED = {
    "outline_box": ("line_role", "line_width_pt"),
    "band": ("fill_role",),
    "reference_line": ("line_role", "line_width_pt"),
    "arrow": ("line_role", "line_width_pt", "label", "position", "gap_role"),
    "callout": ("line_role", "line_width_pt", "fill_role", "label", "position", "gap_role"),
    "bracket": ("line_role", "line_width_pt", "side", "gap_role", "depth_role"),
    "badge": ("fill_role", "label", "position"),
}
LABEL_KEYS = {"text", "role", "ink_role", "position", "max_width_share", "align"}
SHAPES = {"rect": "rect", "ellipse": "ellipse", "rounded": "roundRect"}
AROUND = ("above", "below", "left", "right", "above_left", "above_right", "below_left", "below_right")
LABEL_POSITIONS = {
    "reference_line_h": ("end_outside", "end_above", "end_below", "start_above", "start_below"),
    "reference_line_v": ("end_outside", "end_right", "end_left", "start_right", "start_left"),
    "band": ("inside_top_left", "inside_top_right", "inside_bottom_left", "inside_bottom_right"),
}
DEFAULTS = {
    "pad_role": "0 EMU: drawn on the anchor's own edge",
    "gap_role": "0 EMU: the label touches what it labels",
    "dash": "solid",
    "shape": "rect",
    "style": "square (leftBracket / rightBracket presets)",
    "head": "none: a plain leader",
    "label.align": "left (center on a badge and on a bracket label)",
    "label.max_width_share": "one line, as wide as the text measures",
    "label.position.reference_line": "end_outside: past the plot's far edge, centred on the line",
    "label.position.band": "inside_top_left",
}


class AnnotationRefused(ValueError):
    pass


def _num(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


# --- anchors ---------------------------------------------------------------------------


def _pair(v, where: str, what: str) -> tuple:
    if not isinstance(v, list) or len(v) != 2:
        raise AnnotationRefused(f"{where}: {what} must be a [first, last] pair, got {v!r}")
    return v[0], v[1]


def _union(rects: list[tuple]) -> tuple[float, float, float, float]:
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return x0, y0, x1 - x0, y1 - y0


def chart_anchor(geo: ChartGeometry, anchor: dict, where: str) -> dict:
    """{"rect": (x, y, w, h)} for an area anchor, plus "line": ((x1, y1), (x2, y2)) for a
    value or category line and "marks": the union of the marks the anchor spans."""
    p = geo.plot
    keys = set(anchor)
    if keys == {"point"}:
        pt = anchor["point"]
        if not isinstance(pt, dict) or "series" not in pt or not ({"category"} == set(pt) - {"series"} or {"index"} == set(pt) - {"series"}):
            raise AnnotationRefused(f"{where}: point is {{series, category}} (or {{series, index}} on an XY chart), got {pt!r}")
        idx = pt.get("category", pt.get("index"))
        rect = geo.mark_rect(pt["series"], idx)
        return {"rect": rect, "marks": rect}
    if keys == {"categories"}:
        a, b = _pair(anchor["categories"], where, "categories")
        ax, a0, a1 = geo.category_band(a)
        _, b0, b1 = geo.category_band(b)
        lo, hi = min(a0, b0), max(a1, b1)
        i0, i1 = sorted((geo._category_index(a), geo._category_index(b)))
        marks = _union([geo.mark_rect(j, i) for j in range(len(geo.series)) for i in range(i0, i1 + 1)])
        rect = (lo, p.top, hi - lo, p.height) if ax == "x" else (p.left, lo, p.width, hi - lo)
        return {"rect": rect, "marks": marks}
    if keys == {"category"}:
        ax, c = geo.category_centre(anchor["category"])
        line = ((c, p.top), (c, p.top + p.height)) if ax == "x" else ((p.left, c), (p.left + p.width, c))
        return {"rect": _union([(line[0][0], line[0][1], 0, 0), (line[1][0], line[1][1], 0, 0)]), "line": line}
    if keys <= {"value", "axis"} and "value" in keys:
        ax, c = geo.value_coord(anchor["value"], anchor.get("axis", "value"))
        line = ((p.left, c), (p.left + p.width, c)) if ax == "y" else ((c, p.top), (c, p.top + p.height))
        return {"rect": _union([(line[0][0], line[0][1], 0, 0), (line[1][0], line[1][1], 0, 0)]), "line": line}
    if keys <= {"values", "axis"} and "values" in keys:
        a, b = _pair(anchor["values"], where, "values")
        ax, lo, hi = geo.value_span(a, b, anchor.get("axis", "value"))
        return {"rect": (p.left, lo, p.width, hi - lo) if ax == "y" else (lo, p.top, hi - lo, p.height)}
    if keys == {"region"}:
        reg = anchor["region"]
        if not isinstance(reg, dict):
            raise AnnotationRefused(f"{where}: region is {{categories, values}} or {{x, y}} on an XY chart")
        if geo.family == "xy":
            if set(reg) != {"x", "y"}:
                raise AnnotationRefused(f"{where}: an XY region is {{x: [a, b], y: [c, d]}}")
            _, x0, x1 = geo.value_span(*_pair(reg["x"], where, "x"), axis="category")
            _, y0, y1 = geo.value_span(*_pair(reg["y"], where, "y"))
            return {"rect": (x0, y0, x1 - x0, y1 - y0)}
        if set(reg) != {"categories", "values"}:
            raise AnnotationRefused(f"{where}: a region is {{categories: [i, j], values: [a, b]}}")
        span = chart_anchor(geo, {"categories": reg["categories"]}, where)["rect"]
        vax, v0, v1 = geo.value_span(*_pair(reg["values"], where, "values"))
        if vax == "y":
            return {"rect": (span[0], v0, span[2], v1 - v0)}
        return {"rect": (v0, span[1], v1 - v0, span[3])}
    raise AnnotationRefused(f"{where}: chart anchor {sorted(keys)} is not one of point, categories, category, value, values, region")


def table_anchor(el: dict, anchor: dict, where: str) -> dict:
    xs, ys = table_geometry(el)
    h = int(el.get("header_rows", 1))
    n_body, n_cols = len(el["rows"]), len(el["columns"])

    def body(r) -> int:
        if not isinstance(r, int) or isinstance(r, bool) or not 0 <= r < n_body:
            raise AnnotationRefused(f"{where}: body row {r!r} outside 0..{n_body - 1} (rows count from 0 as the table lists them; header rows through header_group)")
        return h + r

    def col(c) -> int:
        if isinstance(c, str):
            keys = [k["key"] for k in el["columns"]]
            if c in keys:
                return keys.index(c)
        if not isinstance(c, int) or isinstance(c, bool) or not 0 <= c < n_cols:
            raise AnnotationRefused(f"{where}: column {c!r} is not a column index 0..{n_cols - 1} or key")
        return c

    def rect(r0: int, r1: int, c0: int, c1: int) -> dict:
        r0, r1 = sorted((r0, r1))
        c0, c1 = sorted((c0, c1))
        return {"rect": (xs[c0], ys[r0], xs[c1 + 1] - xs[c0], ys[r1 + 1] - ys[r0])}

    keys = set(anchor)
    if keys == {"cell"}:
        r, c = _pair(anchor["cell"], where, "cell")
        return rect(body(r), body(r), col(c), col(c))
    if keys == {"cells"}:
        a, b = _pair(anchor["cells"], where, "cells")
        (r0, c0), (r1, c1) = _pair(a, where, "cells[0]"), _pair(b, where, "cells[1]")
        return rect(body(r0), body(r1), col(c0), col(c1))
    if keys == {"row"}:
        return rect(body(anchor["row"]), body(anchor["row"]), 0, n_cols - 1)
    if keys == {"rows"}:
        a, b = _pair(anchor["rows"], where, "rows")
        return rect(body(a), body(b), 0, n_cols - 1)
    if keys == {"column"}:
        return rect(0, h + n_body - 1, col(anchor["column"]), col(anchor["column"]))
    if keys == {"columns"}:
        a, b = _pair(anchor["columns"], where, "columns")
        return rect(0, h + n_body - 1, col(a), col(b))
    if keys == {"header_group"}:
        g = anchor["header_group"]
        if not isinstance(g, dict) or "columns" not in g or set(g) - {"row", "columns"}:
            raise AnnotationRefused(f"{where}: header_group is {{row (header row, default 0), columns: [c0, c1]}}")
        hr = g.get("row", 0)
        if not isinstance(hr, int) or not 0 <= hr < h:
            raise AnnotationRefused(f"{where}: header row {hr!r} outside 0..{h - 1}")
        a, b = _pair(g["columns"], where, "columns")
        return rect(hr, hr, col(a), col(b))
    raise AnnotationRefused(f"{where}: table anchor {sorted(keys)} is not one of cell, cells, row, rows, column, columns, header_group")


# --- labels ----------------------------------------------------------------------------


class Labeller:
    """Measures a label with the solver's ruler at the page's scale and returns the text
    element the emitter writes (measured lines and the fitted sizes)."""

    def __init__(self, ctx: L.Context, scale: Fraction) -> None:
        self.ctx, self.scale = ctx, scale

    def space(self, role: str | None, where: str) -> int:
        if role is None:
            return 0
        try:
            return L.space_emu(self.ctx.guide, role, self.scale, "x")
        except L.LayoutContractError as error:
            raise AnnotationRefused(f"{where}: {error}") from None

    def measure(self, label: dict, max_width: float | None, where: str) -> tuple[list[str], int, int, dict]:
        text = label["text"]
        el = L.Element(where, "text", None, "scaling", (L.Paragraph(label["role"], text, None),), None, None, None)
        try:
            width = int(max_width) if max_width else self.ctx.spec.page_width * 4
            rows = L.measure_element(self.ctx, el, L.Box(0, 0, width, 1), self.scale)
        except L.LayoutContractError as error:
            raise AnnotationRefused(f"{where}: {error}") from None
        m = rows[0]
        if max_width is None and len(m.lines) > 1:
            raise AnnotationRefused(f"{where}: the label breaks at the page's width; shorten it or set label.max_width_share")
        w = max(line.width_emu for line in m.lines) + 2 * self.ctx.ruler.fit_epsilon_emu
        h = L.element_height_emu(rows)
        hints = L._entry_hints(m.entry)
        return [line.text for line in m.lines], w, h, {k: hints[k] for k in L.FIT_KEYS}

    def text_element(self, eid: str, label: dict, box: tuple, lines: list[str], fit: dict, align: str, anchor: str = "t") -> dict:
        return {"id": eid, "kind": "text", "box": [round(v) for v in box], "anchor": anchor,
                "paragraphs": [{"role": label["role"], "bullet_level": None, "lines": lines, "indent_emu": 0, "fit": fit,
                                "runs": [{"text": label["text"]}], "ink_role": label["ink_role"], "align": align}]}


def _placed(position: str, target: tuple, w: float, h: float, gap: float) -> tuple[float, float, float, float]:
    """A w x h box beside `target` at `gap`, by one of AROUND."""
    x, y, tw, th = target
    cx, cy = x + tw / 2, y + th / 2
    horiz = {"left": x - gap - w, "right": x + tw + gap}
    vert = {"above": y - gap - h, "below": y + th + gap}
    if position == "above":
        return cx - w / 2, vert["above"], w, h
    if position == "below":
        return cx - w / 2, vert["below"], w, h
    if position == "left":
        return horiz["left"], cy - h / 2, w, h
    if position == "right":
        return horiz["right"], cy - h / 2, w, h
    v, hz = position.split("_")
    return horiz[hz], vert[v], w, h


def _toward(position: str, label: tuple, target: tuple) -> tuple[tuple[float, float], tuple[float, float]]:
    """The leader from the label's edge facing the target to the target's facing point."""
    lx, ly, lw, lh = label
    x, y, w, h = target
    if position == "above":
        return (lx + lw / 2, ly + lh), (x + w / 2, y)
    if position == "below":
        return (lx + lw / 2, ly), (x + w / 2, y + h)
    if position == "left":
        return (lx + lw, ly + lh / 2), (x, y + h / 2)
    if position == "right":
        return (lx, ly + lh / 2), (x + w, y + h / 2)
    v, hz = position.split("_")
    start = (lx + lw if hz == "left" else lx, ly + lh if v == "above" else ly)
    end = (x if hz == "left" else x + w, y if v == "above" else y + h)
    return start, end


# --- the resolver ----------------------------------------------------------------------


def _check_keys(ann: dict, where: str) -> str:
    kind = ann.get("kind")
    if kind not in KINDS:
        raise AnnotationRefused(f"{where}: kind {kind!r} not in {list(KINDS)}")
    allowed = COMMON_KEYS | KIND_KEYS[kind]
    extra = sorted(set(ann) - allowed)
    if extra:
        raise AnnotationRefused(f"{where}: unknown keys {extra} for a {kind}; allowed {sorted(allowed)}")
    missing = [k for k in REQUIRED[kind] if k not in ann]
    if missing:
        raise AnnotationRefused(f"{where}: a {kind} needs {missing}: no neutral value exists for them")
    if not isinstance(ann.get("anchor"), dict):
        raise AnnotationRefused(f"{where}: anchor must be an object")
    if "label" in ann:
        lab = ann["label"]
        if not isinstance(lab, dict):
            raise AnnotationRefused(f"{where}: label must be an object")
        extra = sorted(set(lab) - LABEL_KEYS)
        if extra:
            raise AnnotationRefused(f"{where} label: unknown keys {extra}; allowed {sorted(LABEL_KEYS)}")
        missing = [k for k in ("text", "role", "ink_role") if not lab.get(k)]
        if missing:
            raise AnnotationRefused(f"{where} label: needs {missing} (the ink is yours: nothing picks one for a fill)")
    if ann.get("dash") is not None and ann["dash"] not in DASHES:
        raise AnnotationRefused(f"{where}: dash {ann['dash']!r} not in {list(DASHES)}")
    if "line_width_pt" in ann and (not _num(ann["line_width_pt"]) or ann["line_width_pt"] <= 0):
        raise AnnotationRefused(f"{where}: line_width_pt must be a positive number")
    return kind


def resolve(annotations: list, elements: list[dict], ctx: L.Context, scale: Fraction, guide: dict, zones: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """The page's elements with every annotation's elements inserted (a band before its
    host, everything else after the page's own elements, in the spec's order), the
    per-annotation report, and the refusals."""
    eg = EmitGuide(guide)
    by_id = {el["id"]: el for el in elements}
    lab = Labeller(ctx, scale)
    before: dict[str, list[dict]] = {}
    after: list[dict] = []
    report: list[dict] = []
    problems: list[dict] = []
    seen_ids = set(by_id)
    for ai, ann in enumerate(annotations or []):
        where = f"annotation {ann.get('id', ai)!r}" if isinstance(ann, dict) else f"annotation {ai}"
        try:
            if not isinstance(ann, dict):
                raise AnnotationRefused(f"{where}: expected an object")
            kind = _check_keys(ann, where)
            aid = ann.get("id")
            if not isinstance(aid, str) or not aid or aid in seen_ids:
                raise AnnotationRefused(f"{where}: needs an id unique on the page")
            seen_ids.add(aid)
            host = by_id.get(ann.get("host"))
            if host is None or host["kind"] not in ("chart", "table"):
                raise AnnotationRefused(f"{where}: host {ann.get('host')!r} is not a chart or table element on this page")
            for k in ("line_role", "fill_role"):
                if k in ann:
                    eg.hex(ann[k], where=where)
            if "label" in ann:
                eg.hex(ann["label"]["ink_role"], where=f"{where} label")
            drawn, entry = _resolve_one(ann, kind, aid, host, lab, eg, where)
        except (AnnotationRefused, GeometryRefused) as error:
            problems.append({"kind": "annotation refused", "severity": "refusal", "detail": str(error)})
            report.append({"id": ann.get("id") if isinstance(ann, dict) else ai, "status": "refused", "why": str(error)})
            continue
        except SystemExit as error:  # emit_pptx.SpecError: an unknown role
            problems.append({"kind": "annotation refused", "severity": "refusal", "detail": str(error)})
            report.append({"id": ann.get("id"), "status": "refused", "why": str(error)})
            continue
        for d in drawn:
            d["annotation"] = aid
        if kind == "band":
            before.setdefault(host["id"], []).extend(drawn)
        else:
            after.extend(drawn)
        report.append(entry)
    out: list[dict] = []
    for el in elements:
        out.extend(before.get(el["id"], []))
        out.append(el)
    out.extend(after)
    problems.extend(collisions(out, report, ctx.spec.page_width, ctx.spec.page_height, zones))
    return out, report, problems


def _resolve_one(ann: dict, kind: str, aid: str, host: dict, lab: Labeller, eg: EmitGuide, where: str) -> tuple[list[dict], dict]:
    taken: list[str] = []

    def default(key: str, label_key: str | None = None) -> None:
        taken.append(f"{key}: {DEFAULTS[label_key or key]}")

    other_marks: list[tuple[str, tuple]] = []
    if host["kind"] == "chart":
        geo = ChartGeometry(host, host["box"])
        a = chart_anchor(geo, ann["anchor"], where)
        # every drawn mark the anchor does not take in: an annotation may not cover them
        own = a.get("marks", a["rect"]) if "line" not in a else None
        for j, s in enumerate(geo.series):
            if s.get("fill_role") == "none" and geo.family in ("bar", "bar_stacked"):
                continue  # an invisible carrier series (a football field's base) draws nothing
            n = len(s["values"]) if geo.family == "xy" else len(geo.categories)
            for i in range(n):
                m = geo.mark_rect(j, i)
                if m[2] <= 0 or m[3] <= 0:
                    continue
                if own is not None and _intersects(m, own):
                    continue
                other_marks.append((f"mark {s.get('name')!r} {geo.categories[i] if geo.family != 'xy' else i!r}", m))
    else:
        a = table_anchor(host, ann["anchor"], where)
    lw = round(float(ann.get("line_width_pt", 0)) * EMU_PER_PT)
    if "dash" not in ann and kind in ("outline_box", "reference_line", "arrow"):
        default("dash")
    pad = lab.space(ann.get("pad_role"), where)
    if "pad_role" not in ann and kind in ("outline_box", "band", "callout", "badge"):
        default("pad_role")
    gap = lab.space(ann.get("gap_role"), where)
    if "gap_role" not in ann and kind in ("reference_line", "badge") and (kind == "badge" or "label" in ann):
        default("gap_role")
    label = ann.get("label")
    stroke = {"line_role": ann.get("line_role"), "line_width_emu": lw, "dash": ann.get("dash")}
    drawn: list[dict] = []
    footprint: list[dict] = []  # what the annotation covers: [{"rect" | "segment", ...}]
    r = a["rect"]

    def label_box(max_share_of: float | None) -> tuple[list[str], int, int, dict]:
        share = label.get("max_width_share")
        if share is not None and (not _num(share) or not 0 < share <= 1):
            raise AnnotationRefused(f"{where} label: max_width_share is a fraction of the host's width, 0 to 1")
        if share is None:
            default("label.max_width_share")
        return lab.measure(label, share * max_share_of if share else None, f"{where} label")

    def align(default_align: str) -> str:
        if "align" in label:
            if label["align"] not in ("left", "center", "right"):
                raise AnnotationRefused(f"{where} label: align {label['align']!r} not in left, center, right")
            return label["align"]
        default("label.align")
        return default_align

    if kind == "outline_box":
        shape = ann.get("shape", "rect")
        if shape not in SHAPES:
            raise AnnotationRefused(f"{where}: shape {shape!r} not in {list(SHAPES)}")
        if "shape" not in ann:
            default("shape")
        box = (r[0] - pad, r[1] - pad, r[2] + 2 * pad, r[3] + 2 * pad)
        drawn.append({"id": f"{aid}-box", "kind": "rect", "box": [round(v) for v in box], "fill_role": None, "prst": SHAPES[shape], **stroke})
        footprint += [{"outline": box, "width": lw}]
    elif kind == "band":
        box = (r[0] - pad, r[1] - pad, r[2] + 2 * pad, r[3] + 2 * pad)
        if host["kind"] == "table":
            _band_visible_on_table(host, box, eg, where)
        drawn.append({"id": f"{aid}-band", "kind": "rect", "box": [round(v) for v in box], "fill_role": ann["fill_role"], "line_role": None, "prst": "rect"})
        if label:
            pos = label.get("position", "inside_top_left")
            if pos not in LABEL_POSITIONS["band"]:
                raise AnnotationRefused(f"{where} label: position {pos!r} not in {list(LABEL_POSITIONS['band'])}")
            if "position" not in label:
                default("label.position", "label.position.band")
            lines, w, h, fit = label_box(box[2])
            _, v, hz = pos.split("_")
            lx = box[0] + pad if hz == "left" else box[0] + box[2] - pad - w
            ly = box[1] + pad if v == "top" else box[1] + box[3] - pad - h
            drawn.append(lab.text_element(f"{aid}-label", label, (lx, ly, w, h), lines, fit, align("left")))
            footprint.append({"rect": (lx, ly, w, h), "text": True})
    elif kind == "reference_line":
        if "line" not in a:
            raise AnnotationRefused(f"{where}: a reference line anchors to a value or a category, not {sorted(ann['anchor'])}")
        (x1, y1), (x2, y2) = a["line"]
        horizontal = abs(y2 - y1) < 1
        if not horizontal:
            # the line's end is its top
            (x1, y1), (x2, y2) = ((x1, max(y1, y2)), (x2, min(y1, y2)))
        drawn.append({"id": f"{aid}-line", "kind": "rule", "points": [round(x1), round(y1), round(x2), round(y2)],
                      "box": [round(min(x1, x2)), round(min(y1, y2)), round(abs(x2 - x1)), round(abs(y2 - y1))], **stroke})
        footprint.append({"segment": ((x1, y1), (x2, y2)), "width": lw})
        if label:
            options = LABEL_POSITIONS["reference_line_h" if horizontal else "reference_line_v"]
            pos = label.get("position", "end_outside")
            if pos not in options:
                raise AnnotationRefused(f"{where} label: position {pos!r} not in {list(options)} for a {'horizontal' if horizontal else 'vertical'} line")
            if "position" not in label:
                default("label.position", "label.position.reference_line")
            lines, w, h, fit = label_box(host["box"][2])
            end, start = (x2, y2), (x1, y1)
            if horizontal:
                lx = {"end_outside": end[0] + gap, "end_above": end[0] - w, "end_below": end[0] - w, "start_above": start[0], "start_below": start[0]}[pos]
                ly = {"end_outside": end[1] - h / 2, "end_above": end[1] - gap - h, "end_below": end[1] + gap, "start_above": start[1] - gap - h, "start_below": start[1] + gap}[pos]
            else:
                lx = {"end_outside": end[0] - w / 2, "end_right": end[0] + gap, "end_left": end[0] - gap - w, "start_right": start[0] + gap, "start_left": start[0] - gap - w}[pos]
                ly = {"end_outside": end[1] - gap - h, "end_right": end[1], "end_left": end[1], "start_right": start[1] - h, "start_left": start[1] - h}[pos]
            drawn.append(lab.text_element(f"{aid}-label", label, (lx, ly, w, h), lines, fit, align("left")))
            footprint.append({"rect": (lx, ly, w, h), "text": True})
    elif kind in ("arrow", "callout"):
        pos = ann["position"]
        if pos not in AROUND:
            raise AnnotationRefused(f"{where}: position {pos!r} not in {list(AROUND)}")
        if gap <= 0:
            raise AnnotationRefused(f"{where}: gap_role must leave room for the {'arrow' if kind == 'arrow' else 'leader'}")
        target = a.get("marks", r)
        lines, w, h, fit = label_box(host["box"][2])
        inner = (2 * pad) if kind == "callout" else 0
        box = _placed(pos, target, w + inner, h + inner, gap)
        if kind == "callout":
            drawn.append({"id": f"{aid}-box", "kind": "rect", "box": [round(v) for v in box], "fill_role": ann["fill_role"], "prst": "rect", **stroke, "dash": None})
            footprint.append({"rect": box})
        text_box = (box[0] + inner / 2, box[1] + inner / 2, w, h)
        drawn.append(lab.text_element(f"{aid}-label", label, text_box, lines, fit, align("left")))
        footprint.append({"rect": text_box, "text": True})
        (sx, sy), (ex, ey) = _toward(pos, box, target)
        head = "arrow" if kind == "arrow" else ann.get("head", "none")
        if head not in ("none", "arrow"):
            raise AnnotationRefused(f"{where}: head {head!r} not in none, arrow")
        if kind == "callout" and "head" not in ann:
            default("head")
        drawn.append({"id": f"{aid}-leader", "kind": "rule", "points": [round(sx), round(sy), round(ex), round(ey)],
                      "box": [round(min(sx, ex)), round(min(sy, ey)), round(abs(ex - sx)), round(abs(ey - sy))], **stroke,
                      "dash": ann.get("dash") if kind == "arrow" else None, "tail_end": "triangle" if head == "arrow" else None})
        footprint.append({"segment": ((sx, sy), (ex, ey)), "width": lw})
    elif kind == "bracket":
        side = ann["side"]
        if side not in ("above", "below", "left", "right"):
            raise AnnotationRefused(f"{where}: side {side!r} not in above, below, left, right")
        style = ann.get("style", "square")
        if style not in ("square", "brace"):
            raise AnnotationRefused(f"{where}: style {style!r} not in square, brace")
        if "style" not in ann:
            default("style")
        depth = lab.space(ann["depth_role"], where)
        span, extent = r, a.get("marks", r)
        if side in ("above", "below"):
            y = extent[1] - gap - depth if side == "above" else extent[1] + extent[3] + gap
            box = (span[0], y, span[2], depth)
        else:
            x = extent[0] - gap - depth if side == "left" else extent[0] + extent[2] + gap
            box = (x, span[1], depth, span[3])
        word = "Bracket" if style == "square" else "Brace"
        prst, rot = {"above": (f"left{word}", 90), "below": (f"right{word}", 90), "left": (f"left{word}", 0), "right": (f"right{word}", 0)}[side]
        drawn.append({"id": f"{aid}-bracket", "kind": "rect", "box": [round(v) for v in box], "fill_role": None, "prst": prst[0].lower() + prst[1:], "rot": rot, **stroke})
        footprint.append({"rect": box})
        if label:
            lines, w, h, fit = label_box(host["box"][2])
            lb = _placed(side, box, w, h, gap)
            drawn.append(lab.text_element(f"{aid}-label", label, lb, lines, fit, align("center")))
            footprint.append({"rect": lb, "text": True})
    elif kind == "badge":
        pos = ann["position"]
        if pos not in AROUND:
            raise AnnotationRefused(f"{where}: position {pos!r} not in {list(AROUND)}")
        lines, w, h, fit = label_box(None)
        if len(lines) != 1:
            raise AnnotationRefused(f"{where}: a badge holds one line")
        # the circle holds the whole text box (its diagonal), so the label stands on the fill
        # (+4 EMU: both boxes are rounded to whole EMU when written)
        d = (w * w + h * h) ** 0.5 + 2 * pad + 4
        box = _placed(pos, r, d, d, gap)
        drawn.append({"id": f"{aid}-badge", "kind": "rect", "box": [round(v) for v in box], "fill_role": ann["fill_role"], "line_role": None, "prst": "ellipse"})
        tb = (box[0] + (d - w) / 2, box[1] + (d - h) / 2, w, h)
        drawn.append(lab.text_element(f"{aid}-label", label, tb, lines, fit, align("center"), anchor="m"))
        footprint += [{"rect": box}, {"rect": tb, "text": True}]
    entry = {"id": aid, "kind": kind, "host": host["id"], "anchor": ann["anchor"], "status": "placed",
             "anchor_emu": [round(v) for v in r], "drawn": [d["id"] for d in drawn], "defaults_taken": taken,
             "_footprint": footprint, "_host_box": host["box"], "_other_marks": other_marks}
    return drawn, entry


def _band_visible_on_table(host: dict, box: tuple, eg: EmitGuide, where: str) -> None:
    """A band is drawn under the table; a row the table fills itself hides it
    (emit_pptx.table_row_styles, the rows as the emitter writes them)."""
    from emit_pptx import table_row_styles
    _, ys = table_geometry(host)
    for st, top, bottom in zip(table_row_styles(host, eg), ys, ys[1:]):
        if bottom > box[1] and top < box[1] + box[3] and st["fill_hex"]:
            raise AnnotationRefused(f"{where}: table row {st['row']} ({st['class']}) is filled with {st['fill_name']}, which hides a band drawn under it; "
                                    "colour the row through the table (emphasis_rows, banding_role) instead")


# --- the collision contract --------------------------------------------------------------


def _intersects(a: tuple, b: tuple) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _contains(outer, inner) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[0] + outer[2] >= inner[0] + inner[2] and outer[1] + outer[3] >= inner[1] + inner[3]


def _segment_hits(seg: tuple, width: float, rect: tuple) -> bool:
    """A stroked segment against a rectangle: Liang-Barsky clipping of the segment to the
    rectangle grown by half the stroke."""
    (x1, y1), (x2, y2) = seg
    hw = width / 2
    rx0, ry0, rx1, ry1 = rect[0] - hw, rect[1] - hw, rect[0] + rect[2] + hw, rect[1] + rect[3] + hw
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - rx0), (dx, rx1 - x1), (-dy, y1 - ry0), (dy, ry1 - y1)):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _outline_strips(box: tuple, width: float) -> list[tuple]:
    x, y, w, h = box
    hw = width / 2
    return [(x - hw, y - hw, w + width, width), (x - hw, y + h - hw, w + width, width), (x - hw, y - hw, width, h + width), (x + w - hw, y - hw, width, h + width)]


def covers(fp: dict, rect: tuple) -> bool:
    """Whether one footprint part covers `rect`: a stroke where it runs, a filled or text
    box over its whole area. An outline's interior is not a cover."""
    if "segment" in fp:
        return _segment_hits(fp["segment"], fp["width"], rect)
    if "outline" in fp:
        return any(_intersects(s, rect) for s in _outline_strips(fp["outline"], fp["width"]))
    return _intersects(fp["rect"], rect)


def _bbox(fp: dict) -> tuple:
    if "segment" in fp:
        (x1, y1), (x2, y2) = fp["segment"]
        hw = fp["width"] / 2
        return min(x1, x2) - hw, min(y1, y2) - hw, abs(x2 - x1) + fp["width"], abs(y2 - y1) + fp["width"]
    if "outline" in fp:
        return _union(_outline_strips(fp["outline"], fp["width"]))
    return fp["rect"]


def collisions(elements: list[dict], report: list[dict], page_w: int, page_h: int, zones: list[dict]) -> list[dict]:
    """Refusals from the solved boxes: an annotation over another page element (a filled
    ground that contains it is no collision), over another annotation (a band is ground),
    past the page edge, or in a reserved chrome zone. The host is the annotation's anchor
    and is never a collision."""
    out: list[dict] = []
    placed = [e for e in report if e.get("status") == "placed"]
    own = {d for e in placed for d in e["drawn"]}
    page_els = [el for el in elements if el["id"] not in own]
    for e in placed:
        fps = e["_footprint"]
        hits: list[str] = []
        for fp in fps:
            bb = _bbox(fp)
            if bb[0] < 0 or bb[1] < 0 or bb[0] + bb[2] > page_w or bb[1] + bb[3] > page_h:
                hits.append("the page edge")
            for z in zones:
                zr = (z["left"], z["top"], z["width"], z["height"])
                if covers(fp, zr):
                    hits.append(f"reserved zone {z.get('source', '?')}")
            for el in page_els:
                if el["id"] == e["host"] or el["id"] == e["host"] + "-fill":
                    continue
                if el["kind"] in ("rect",) and el.get("fill_role") and _contains(el["box"], bb):
                    continue  # the ground the exhibit stands on (a filled panel)
                if covers(fp, tuple(el["box"])):
                    hits.append(f"element {el['id']}")
        if e["kind"] != "band":
            # a reference line crosses the marks by design; its label may not
            for fp in fps:
                if e["kind"] == "reference_line" and "segment" in fp:
                    continue
                hits += [name for name, m in e.get("_other_marks", []) if covers(fp, m)]
        for other in placed:
            if other is e or other["kind"] == "band" or e["kind"] == "band":
                continue
            if any(covers(fp, _bbox(ofp)) for fp in fps for ofp in other["_footprint"]):
                hits.append(f"annotation {other['id']}")
        hits = list(dict.fromkeys(hits))
        e["collisions"] = hits
        if hits:
            out.append({"kind": "annotation collides", "severity": "refusal", "detail": f"annotation {e['id']!r} ({e['kind']}) covers {', '.join(hits)}"})
    return out


# --- after the render: the host's own text ---------------------------------------------------

_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
_PAGE = re.compile(r"<page width=\"([\d.]+)\" height=\"([\d.]+)\">(.*?)</page>", re.S)


def pdf_words(pdf: str) -> list[list[tuple[tuple[float, float, float, float], str]]]:
    """Every word LibreOffice drew, per page, as an EMU box (pdftotext -bbox)."""
    done = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True, timeout=300)
    pages = []
    for m in _PAGE.finditer(done.stdout):
        words = []
        for w in _WORD.finditer(m.group(3)):
            x0, y0, x1, y1 = (float(v) * EMU_PER_PT for v in w.groups()[:4])
            words.append(((x0, y0, x1 - x0, y1 - y0), w.group(5)))
        pages.append(words)
    return pages


def render_check(entry_annotations: list[dict], elements: list[dict], words: list[tuple]) -> list[dict]:
    """Every word the renderer drew inside an annotation's host (tick labels, data labels,
    legend, cell text), against what each annotation covers. A word inside an annotation's
    own label, or inside another element's box (checked before the emit), is not the
    host's. Returns the refusals and fills each entry's `render_check`."""
    out: list[dict] = []
    placed = [e for e in entry_annotations if e.get("status") == "placed"]
    label_boxes = [fp["rect"] for e in placed for fp in e["_footprint"] if fp.get("text")]
    own = {d for e in placed for d in e["drawn"]}
    others = [el for el in elements if el["id"] not in own]
    for e in placed:
        host_box = tuple(e["_host_box"])
        candidates = []
        for box, text in words:
            centre = (box[0] + box[2] / 2, box[1] + box[3] / 2, 0, 0)
            if any(_contains(lb, centre) for lb in label_boxes):
                continue
            if not _contains(host_box, centre):
                continue
            if any(el["id"] != e["host"] and el["kind"] in ("text", "table", "chart") and _contains(tuple(el["box"]), centre) for el in others):
                continue
            candidates.append((box, text))
        crossed = []
        if e["kind"] != "band":
            for box, text in candidates:
                # half a point of the glyph box's slack: pdftotext's boxes are the font's
                # ascent to descent, wider than the ink
                if any(covers(fp, box) for fp in e["_footprint"]):
                    crossed.append(text)
        e["render_check"] = {"host_words": len(candidates), "covered": crossed}
        if crossed:
            out.append({"kind": "annotation covers chart text", "severity": "refusal",
                        "detail": f"annotation {e['id']!r} ({e['kind']}) covers {len(crossed)} word(s) its host drew: {crossed[:6]}"})
    return out




