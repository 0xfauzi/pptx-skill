#!/usr/bin/env python3
"""The annotation layer: shapes placed on an exhibit at positions in its own data.

A slide's `annotations` list is resolved after the page is solved, against the solved
boxes of their hosts. Each annotation becomes ordinary page elements (rect, rule, text)
that the emitter draws, the contrast gate scores and the emitted-fit check re-measures;
nothing here draws, and nothing here decides what to annotate.

    {"id": "subject", "host": "comps", "kind": "outline_box", "anchor": {"row": 3},
     "line_role": "color.accent2", "line_width_pt": 1.5, "pad_role": "space.xs"}

Kinds (each a move the coded corpus measures): outline_box, band, reference_line,
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

The collision contract: an annotation may overlap only its anchor
(its host). It may not cover another page element, another annotation, the page edge
or a reserved chrome zone (checked here, from the solved boxes), nor the host's own
text: tick labels, data labels, legend (checked after the render, from the words
LibreOffice drew: render_check). A band's fill is ground, drawn under its host, and is
not a cover; the contrast gate scores every label and table row on it. A band's label
is drawn under the host too: it is checked like any label, against every mark of the
host, every other annotation and the host's words, and it must lie inside its band.

A value anchor must be a number inside its axis's min..max, and a label may not break
a word between characters (layout.split_words, the solver's own test).
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L  # noqa: E402
from chart_geometry import ChartGeometry, GeometryRefused, table_geometry  # noqa: E402
from emit_pptx import DASHES, Guide as EmitGuide  # noqa: E402

EMU_PER_PT = 12_700

KINDS = ("outline_box", "band", "reference_line", "arrow", "callout", "bracket", "badge", "category_row")
COMMON_KEYS = {"id", "host", "kind", "anchor"}
KIND_KEYS = {
    "outline_box": {"line_role", "line_width_pt", "dash", "pad_role", "shape", "label", "gap_role", "explained_by"},
    "band": {"fill_role", "label", "pad_role", "explained_by"},
    "reference_line": {"line_role", "line_width_pt", "dash", "label", "gap_role", "explained_by"},
    "arrow": {"line_role", "line_width_pt", "dash", "label", "position", "gap_role"},
    "callout": {"line_role", "line_width_pt", "fill_role", "label", "position", "gap_role", "pad_role", "head"},
    "bracket": {"line_role", "line_width_pt", "style", "side", "gap_role", "depth_role", "label", "explained_by"},
    "badge": {"fill_role", "label", "position", "gap_role", "pad_role"},
    "category_row": {"cells", "role", "ink_role", "position", "gap_role", "gap_lines", "after", "shape", "cell_width", "label"},
}
REQUIRED = {
    "outline_box": ("line_role", "line_width_pt"),
    "band": ("fill_role",),
    "reference_line": ("line_role", "line_width_pt"),
    "arrow": ("line_role", "line_width_pt", "label", "position", "gap_role"),
    "callout": ("line_role", "line_width_pt", "fill_role", "label", "position", "gap_role"),
    "bracket": ("line_role", "line_width_pt", "side", "gap_role", "depth_role"),
    "badge": ("fill_role", "label", "position"),
    "category_row": ("cells", "position", "gap_role"),
}
LABEL_KEYS = {"text", "role", "ink_role", "position", "max_width_share", "align"}
SHAPES = {"rect": "rect", "ellipse": "ellipse", "rounded": "roundRect"}
AROUND = ("above", "below", "left", "right", "above_left", "above_right", "below_left", "below_right")
LABEL_POSITIONS = {
    "reference_line_h": ("end_outside", "end_above", "end_below", "start_above", "start_below", "middle_above", "middle_below"),
    "reference_line_v": ("end_outside", "end_right", "end_left", "start_right", "start_left", "middle_right", "middle_left"),
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
    "cell_width": "uniform: every cell of the row as wide as its widest (one oval or box size along the row)",
    "label.align.category_row": "right on a row (the label ends at the plot's edge), center on a column",
}
ROW_SHAPE_KEYS = {"prst", "line_role", "line_width_pt", "fill_role", "pad_role"}
ROW_CELL_KEYS = {"text", "image"}
#: a cell's text box inside an ellipse: the ellipse through the box's corners, sqrt(2) wider
#: and taller than the box (an ellipse x^2/a^2 + y^2/b^2 = 1 with a = w/sqrt2 holds the corner)
SQRT2 = 2 ** 0.5


#: a spacing key's explicit zero: "pad_role": "none" draws on the anchor's own edge as a
#: choice, so it is not listed under defaults_taken as the key left out is
NO_SPACE = "none"


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


def drawn_marks(geo: ChartGeometry) -> list[tuple[int, int, tuple]]:
    """(series, index, rect) of every mark the chart draws: a bar of a series with no fill
    (a football field's invisible base, a label carrier) and a zero-sized point are not."""
    out = []
    for j, s in enumerate(geo.series):
        if s.get("fill_role") == "none" and geo.series_family(j) in ("bar", "bar_stacked"):
            continue
        n = len(s["values"]) if geo.family == "xy" else len(geo.categories)
        for i in range(n):
            m = geo.mark_rect(j, i)
            if m[2] > 0 and m[3] > 0:
                out.append((j, i, m))
    return out


#: a line series written with no width is drawn at the renderer's default stroke; Office's
#: default line-series width, taken as the stroke a label must clear (not measured on LibreOffice)
DEFAULT_LINE_PT = 2.25


def line_strokes(geo: ChartGeometry) -> list[tuple[str, tuple, float]]:
    """(name, segment, width EMU) of every stroked segment of a line chart's series, between
    consecutive points that both carry a number."""
    if geo.family != "line":
        return []
    out = []
    for j, s in enumerate(geo.series):
        if s.get("line_role") == "none":
            continue
        width = float(s.get("line_width_pt") or DEFAULT_LINE_PT) * EMU_PER_PT
        vals = s.get("values") or []
        pts = [geo.point(j, i) if i < len(vals) and _num(vals[i]) else None for i in range(len(geo.categories))]
        for i in range(len(pts) - 1):
            if pts[i] is not None and pts[i + 1] is not None:
                out.append((f"line {s.get('name')!r} {geo.categories[i]!r}-{geo.categories[i + 1]!r}", (pts[i], pts[i + 1]), width))
    return out


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
        rect = (lo, p.top, hi - lo, p.height) if ax == "x" else (p.left, lo, p.width, hi - lo)
        inside = [m for _, i, m in drawn_marks(geo) if i0 <= i <= i1]
        return {"rect": rect, "marks": _union(inside)} if inside else {"rect": rect}
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
        # cells: the table rows (header rows first) and columns the anchor spans
        return {"rect": (xs[c0], ys[r0], xs[c1 + 1] - xs[c0], ys[r1 + 1] - ys[r0]), "cells": (r0, r1, c0, c1)}

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

    def space(self, role: str | None, where: str, lines: int | None = None) -> int:
        """A spacing role at the page's scale; or, for a type role, `lines` of its line
        pitch (a row that must clear tick labels set in that role on that many lines)."""
        if role is None or role == NO_SPACE:
            return 0
        try:
            if role.startswith("type."):
                if lines is None:
                    raise AnnotationRefused(f"{where}: a type role as a distance counts lines of it: give gap_lines")
                return L.resolve_type_entry(self.ctx.guide, role, self.scale).pitch_emu * lines
            if lines is not None:
                raise AnnotationRefused(f"{where}: gap_lines counts lines of a type role; {role!r} is a spacing role")
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
        cut = L.split_words(m)
        if cut:
            raise AnnotationRefused(f"{where}: {cut[0]!r} at {m.entry.size_pt}pt is wider than the {m.allowance_emu - self.ctx.ruler.fit_epsilon_emu} EMU line, "
                                    "so it breaks between characters; widen label.max_width_share or shorten the label")
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
        if not isinstance(lab["text"], str) or not lab["text"].strip():
            raise AnnotationRefused(f"{where} label: text {lab['text']!r} says nothing; a label is words (leave the label out, and explain the mark another way)")
    if ann.get("dash") is not None and ann["dash"] not in DASHES:
        raise AnnotationRefused(f"{where}: dash {ann['dash']!r} not in {list(DASHES)}")
    if "line_width_pt" in ann and (not _num(ann["line_width_pt"]) or ann["line_width_pt"] <= 0):
        raise AnnotationRefused(f"{where}: line_width_pt must be a positive number")
    return kind


def resolve(annotations: list, elements: list[dict], ctx: L.Context, scale: Fraction, guide: dict, zones: list[dict],
            plan_types: list[str] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """The page's elements with every annotation's elements inserted (a band before its
    host, everything else after the page's own elements, in the spec's order), the
    per-annotation report, and the refusals. An unlabelled mark that names nothing
    explaining it (explanation) is drawn, so the render shows it, and refuses the page
    as `annotation unexplained`; plan_types are the exhibit types the plan lists for the
    page, against which a house precedent's exhibit type is checked."""
    eg = EmitGuide(guide)
    by_id = {el["id"]: el for el in elements}
    lab = Labeller(ctx, scale)
    before: dict[str, list[dict]] = {}
    after: list[dict] = []
    report: list[dict] = []
    problems: list[dict] = []
    seen_ids = set(by_id)
    rows: dict[str, tuple] = {}  # a placed category_row's id -> its row rectangle, for "after"
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
            for k in ("line_role", "fill_role", "ink_role"):
                if k in ann:
                    eg.hex(ann[k], where=where)
            if "label" in ann:
                eg.hex(ann["label"]["ink_role"], where=f"{where} label")
            drawn, entry = _resolve_one(ann, kind, aid, host, lab, eg, where, rows)
            try:
                siblings = {a["id"]: a for a in annotations if isinstance(a, dict) and isinstance(a.get("id"), str)}
                entry["explained_by"] = explanation(ann, kind, host, by_id, guide, plan_types, where, siblings) or "its own label"
            except AnnotationUnexplained as error:
                entry["explained_by"] = f"unexplained: {error}"
                problems.append({"kind": "annotation unexplained", "severity": "refusal", "detail": str(error)})
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


def _resolve_one(ann: dict, kind: str, aid: str, host: dict, lab: Labeller, eg: EmitGuide, where: str, rows: dict | None = None) -> tuple[list[dict], dict]:
    taken: list[str] = []

    def default(key: str, label_key: str | None = None) -> None:
        taken.append(f"{key}: {DEFAULTS[label_key or key]}")

    other_marks: list[tuple[str, tuple]] = []
    strokes: list[tuple[str, tuple, float]] = []
    if host["kind"] == "chart":
        geo = ChartGeometry(host, host["box"])
        strokes = line_strokes(geo)
        a = chart_anchor(geo, ann["anchor"], where)
        # every drawn mark the anchor does not take in: an annotation may not cover them. A
        # band's label lies under its host, so every mark in it hides it: none is its own
        own = a.get("marks", a["rect"]) if "line" not in a and kind not in ("band", "category_row") else None
        for j, i, m in drawn_marks(geo):
            if own is None or not _intersects(m, own):
                name = geo.series[j].get("name")
                # a blank category label (a dense time axis labels every n-th) is named by its index
                label = (geo.categories[i] or f"category #{i}") if geo.family != "xy" else i
                other_marks.append((f"mark {name!r} {label!r}", m))
    else:
        a = table_anchor(host, ann["anchor"], where)
    lw = round(float(ann.get("line_width_pt", 0)) * EMU_PER_PT)
    if "dash" not in ann and kind in ("outline_box", "reference_line", "arrow"):
        default("dash")
    pad = lab.space(ann.get("pad_role"), where)
    if "pad_role" not in ann and kind in ("outline_box", "band", "callout", "badge"):
        default("pad_role")
    if "gap_lines" in ann and (isinstance(ann["gap_lines"], bool) or not isinstance(ann["gap_lines"], int) or ann["gap_lines"] < 1):
        raise AnnotationRefused(f"{where}: gap_lines is a whole number of lines, 1 or more")
    gap = lab.space(ann.get("gap_role"), where, ann.get("gap_lines"))
    if "gap_role" not in ann and kind in ("reference_line", "badge", "outline_box") and (kind == "badge" or "label" in ann):
        default("gap_role")
    label = ann.get("label")
    stroke = {"line_role": ann.get("line_role"), "line_width_emu": lw, "dash": ann.get("dash")}
    drawn: list[dict] = []
    footprint: list[dict] = []  # what the annotation covers: [{"rect" | "segment", ...}]
    r = a["rect"]

    def label_box() -> tuple[list[str], int, int, dict]:
        share = label.get("max_width_share")
        if share is not None and (not _num(share) or not 0 < share <= 1):
            raise AnnotationRefused(f"{where} label: max_width_share is a fraction of the host's width, 0 to 1")
        if share is None:
            default("label.max_width_share")
        return lab.measure(label, share * host["box"][2] if share is not None else None, f"{where} label")

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
        if label:
            # the label says what the box marks, beside it: where is a choice with no neutral value
            pos = label.get("position")
            if pos not in AROUND:
                raise AnnotationRefused(f"{where} label: an outline box's label needs position, one of {list(AROUND)} (beside the box, at gap_role)")
            lines, w, h, fit = label_box()
            hw = lw / 2  # the label stands clear of the stroke, not of the anchor
            lb = _placed(pos, (box[0] - hw, box[1] - hw, box[2] + lw, box[3] + lw), w, h, gap)
            drawn.append(lab.text_element(f"{aid}-label", label, lb, lines, fit, align("left")))
            footprint.append({"rect": lb, "text": True, "tokens": label["text"].split()})
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
            lines, w, h, fit = label_box()
            room_w, room_h = box[2] - 2 * pad, box[3] - 2 * pad
            if w > room_w or h > room_h:
                raise AnnotationRefused(f"{where} label: measures {w} x {h} EMU and the band holds {round(room_w)} x {round(room_h)} EMU inside its pad; "
                                        "a label placed inside a band stays inside it: shorten it or set label.max_width_share")
            _, v, hz = pos.split("_")
            lx = box[0] + pad if hz == "left" else box[0] + box[2] - pad - w
            ly = box[1] + pad if v == "top" else box[1] + box[3] - pad - h
            drawn.append(lab.text_element(f"{aid}-label", label, (lx, ly, w, h), lines, fit, align("left")))
            footprint.append({"rect": (lx, ly, w, h), "text": True, "tokens": label["text"].split()})
    elif kind == "reference_line":
        if "line" not in a:
            raise AnnotationRefused(f"{where}: a reference line anchors to a value or a category, not {sorted(ann['anchor'])}")
        (x1, y1), (x2, y2) = a["line"]
        horizontal = abs(y2 - y1) < 1
        if not horizontal:
            # the line's end is its top
            y1, y2 = max(y1, y2), min(y1, y2)
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
            lines, w, h, fit = label_box()
            end, start = (x2, y2), (x1, y1)
            if horizontal:
                mid = (start[0] + end[0]) / 2 - w / 2
                lx = {"end_outside": end[0] + gap, "end_above": end[0] - w, "end_below": end[0] - w, "start_above": start[0], "start_below": start[0],
                      "middle_above": mid, "middle_below": mid}[pos]
                ly = {"end_outside": end[1] - h / 2, "end_above": end[1] - gap - h, "end_below": end[1] + gap, "start_above": start[1] - gap - h, "start_below": start[1] + gap,
                      "middle_above": end[1] - gap - h, "middle_below": end[1] + gap}[pos]
            else:
                lx = {"end_outside": end[0] - w / 2, "end_right": end[0] + gap, "end_left": end[0] - gap - w, "start_right": start[0] + gap, "start_left": start[0] - gap - w,
                      "middle_right": end[0] + gap, "middle_left": end[0] - gap - w}[pos]
                ly = {"end_outside": end[1] - gap - h, "end_right": end[1], "end_left": end[1], "start_right": start[1] - h, "start_left": start[1] - h,
                      "middle_right": (start[1] + end[1]) / 2 - h / 2, "middle_left": (start[1] + end[1]) / 2 - h / 2}[pos]
            drawn.append(lab.text_element(f"{aid}-label", label, (lx, ly, w, h), lines, fit, align("left")))
            footprint.append({"rect": (lx, ly, w, h), "text": True, "tokens": label["text"].split()})
    elif kind in ("arrow", "callout"):
        pos = ann["position"]
        if pos not in AROUND:
            raise AnnotationRefused(f"{where}: position {pos!r} not in {list(AROUND)}")
        if gap <= 0:
            raise AnnotationRefused(f"{where}: gap_role must leave room for the {'arrow' if kind == 'arrow' else 'leader'}")
        target = a.get("marks", r)
        lines, w, h, fit = label_box()
        inner = (2 * pad) if kind == "callout" else 0
        box = _placed(pos, target, w + inner, h + inner, gap)
        if kind == "callout":
            drawn.append({"id": f"{aid}-box", "kind": "rect", "box": [round(v) for v in box], "fill_role": ann["fill_role"], "prst": "rect", **stroke, "dash": None})
            footprint.append({"rect": box})
        text_box = (box[0] + inner / 2, box[1] + inner / 2, w, h)
        drawn.append(lab.text_element(f"{aid}-label", label, text_box, lines, fit, align("left")))
        footprint.append({"rect": text_box, "text": True, "tokens": label["text"].split()})
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
            lines, w, h, fit = label_box()
            lb = _placed(side, box, w, h, gap)
            drawn.append(lab.text_element(f"{aid}-label", label, lb, lines, fit, align("center")))
            footprint.append({"rect": lb, "text": True, "tokens": label["text"].split()})
    elif kind == "category_row":
        if host["kind"] != "chart":
            raise AnnotationRefused(f"{where}: a category row is aligned to a chart's categories; its host is a {host['kind']}")
        drawn, footprint, row_rect = _category_row(ann, aid, host, geo, lab, eg, where, rows or {}, default, gap)
        (rows if rows is not None else {})[aid] = row_rect
        r = row_rect
    elif kind == "badge":
        pos = ann["position"]
        if pos not in AROUND:
            raise AnnotationRefused(f"{where}: position {pos!r} not in {list(AROUND)}")
        lines, w, h, fit = label_box()
        if len(lines) != 1:
            raise AnnotationRefused(f"{where}: a badge holds one line")
        # the circle holds the whole text box (its diagonal), so the label stands on the fill
        # (+4 EMU: both boxes are rounded to whole EMU when written)
        d = (w * w + h * h) ** 0.5 + 2 * pad + 4
        box = _placed(pos, r, d, d, gap)
        drawn.append({"id": f"{aid}-badge", "kind": "rect", "box": [round(v) for v in box], "fill_role": ann["fill_role"], "line_role": None, "prst": "ellipse"})
        tb = (box[0] + (d - w) / 2, box[1] + (d - h) / 2, w, h)
        drawn.append(lab.text_element(f"{aid}-label", label, tb, lines, fit, align("center"), anchor="m"))
        footprint += [{"rect": box}, {"rect": tb, "text": True, "tokens": label["text"].split()}]
    entry = {"id": aid, "kind": kind, "host": host["id"], "anchor": ann["anchor"], "status": "placed",
             "anchor_emu": [round(v) for v in r], "drawn": [d["id"] for d in drawn], "defaults_taken": taken,
             "_footprint": footprint, "_host_box": host["box"], "_other_marks": other_marks, "_lines": strokes}
    return drawn, entry


def _category_row(ann: dict, aid: str, host: dict, geo: ChartGeometry, lab: Labeller, eg: EmitGuide, where: str, rows: dict, default, gap: float):
    """A row of cells (text, or a picture) centred on the chart's categories, beyond the
    plot on one side, each inside its category's band: data rows under a chart, logos or
    icons as category labels. Positions from chart_geometry, text measured with the
    solver's ruler; a cell wider than its band is refused by name."""
    import images
    p = geo.plot
    a = ann["anchor"]
    if set(a) != {"categories"}:
        raise AnnotationRefused(f"{where}: a category row anchors to {{\"categories\": [first, last]}}, the categories its cells sit under")
    c0, c1 = _pair(a["categories"], where, "categories")
    i0, i1 = geo._category_index(c0), geo._category_index(c1)
    if i1 < i0:
        raise AnnotationRefused(f"{where}: categories run first to last, got {i0}..{i1}")
    cells = ann["cells"]
    if not isinstance(cells, list) or len(cells) != i1 - i0 + 1:
        raise AnnotationRefused(f"{where}: cells must list one entry per category {i0}..{i1} ({i1 - i0 + 1}); "
                                f"got {len(cells) if isinstance(cells, list) else type(cells).__name__} (null leaves a category empty)")
    pos = ann["position"]
    across = not p.horizontal_bars  # categories run across the page: the row lies below or above the plot
    if across and pos not in ("below", "above"):
        raise AnnotationRefused(f"{where}: on a column or line chart a row lies below or above the plot, not {pos!r}")
    if not across and pos not in ("left", "right"):
        raise AnnotationRefused(f"{where}: on a horizontal bar chart a category column lies left or right of the plot, not {pos!r}")
    text_style = {k: ann[k] for k in ("role", "ink_role") if k in ann}
    shape = ann.get("shape")
    if shape is not None:
        if not isinstance(shape, dict) or set(shape) - ROW_SHAPE_KEYS or shape.get("prst") not in SHAPES:
            raise AnnotationRefused(f"{where} shape: {{prst ({list(SHAPES)}), line_role, line_width_pt, fill_role, pad_role}}")
        if not shape.get("line_role") and not shape.get("fill_role"):
            raise AnnotationRefused(f"{where} shape: draws nothing without a line_role or fill_role")
        if shape.get("line_role") and (not _num(shape.get("line_width_pt")) or shape["line_width_pt"] <= 0):
            raise AnnotationRefused(f"{where} shape: a line_role needs a positive line_width_pt (no neutral stroke width exists)")
        for k in ("line_role", "fill_role"):
            if shape.get(k):
                eg.hex(shape[k], where=f"{where} shape")
    width_mode = ann.get("cell_width", "uniform")
    if width_mode not in ("uniform", "own"):
        raise AnnotationRefused(f"{where}: cell_width is \"uniform\" or \"own\"")
    if "cell_width" not in ann:
        default("cell_width")
    pad = lab.space(shape.get("pad_role"), where) if shape else 0
    # measure every cell
    measured = []
    for k, cell in enumerate(cells):
        cw = f"{where} cells[{k}]"
        if cell is None:
            measured.append(None)
            continue
        if isinstance(cell, str):
            cell = {"text": cell}
        if not isinstance(cell, dict) or len(cell) != 1 or not set(cell) <= ROW_CELL_KEYS:
            raise AnnotationRefused(f"{cw}: a cell is a string, {{\"text\": ...}}, {{\"image\": {{\"path\" | \"svg\", \"height_role\" | \"width_role\", ...}}}} or null")
        if "text" in cell:
            if not isinstance(cell["text"], str) or not cell["text"].strip():
                raise AnnotationRefused(f"{cw}: text must be non-blank (null leaves the category empty)")
            missing = [k2 for k2 in ("role", "ink_role") if k2 not in text_style]
            if missing:
                raise AnnotationRefused(f"{where}: a row of text cells needs {missing} (nothing picks a type or an ink for you)")
            lines, w, h, fit = lab.measure({"text": cell["text"], **text_style}, None, cw)
            measured.append(("text", cell["text"], lines, w, h, fit))
        else:
            try:
                pic = images.picture(cell["image"], cw, eg.g)
                size = images.box_size(pic, eg.g)
            except images.ImageRefused as error:
                raise AnnotationRefused(str(error)) from None
            if size is None:
                raise AnnotationRefused(f"{cw}: a picture in a row is sized by its role: give it height_role or width_role")
            measured.append(("image", pic, None, size["width_emu"], size["height_emu"], None))
    present = [m for m in measured if m is not None]
    if not present:
        raise AnnotationRefused(f"{where}: every cell is null")
    k_inflate = SQRT2 if shape and shape["prst"] == "ellipse" else 1.0
    def outer(w: float, h: float, kind: str) -> tuple[float, float]:
        if shape is None or kind == "image":
            return w, h
        return w * k_inflate + 2 * pad, h * k_inflate + 2 * pad
    sizes = [outer(m[3], m[4], m[0]) for m in present]
    uni_w, uni_h = max(s_[0] for s_ in sizes), max(s_[1] for s_ in sizes)
    depth = uni_h if across else uni_w      # extent away from the plot
    # where the row starts: the plot's edge, or the row it follows
    if "after" in ann:
        prev = rows.get(ann["after"])
        if prev is None:
            raise AnnotationRefused(f"{where}: after {ann['after']!r} names no category row placed before this one on the page")
        edge = {"below": prev[1] + prev[3], "above": prev[1], "right": prev[0] + prev[2], "left": prev[0]}[pos]
    else:
        edge = {"below": p.top + p.height, "above": p.top, "right": p.left + p.width, "left": p.left}[pos]
    start = edge + gap if pos in ("below", "right") else edge - gap - depth
    drawn: list[dict] = []
    footprint: list[dict] = []
    for k, m in enumerate(measured):
        if m is None:
            continue
        i = i0 + k
        cname = geo.categories[i] or f"category #{i}"
        _, lo, hi = geo.category_band(i)
        _, c = geo.category_centre(i)
        cw_, ch_ = (uni_w, uni_h) if width_mode == "uniform" else outer(m[3], m[4], m[0])
        a_ext = cw_ if across else ch_
        if a_ext > hi - lo + 1:
            raise AnnotationRefused(f"{where} cells[{k}] ({cname!r}): {round(a_ext)} EMU wide, wider than its category's {round(hi - lo)} EMU band; "
                                    "shorten it, use a smaller role, or give the chart more width")
        if across:
            box = (c - cw_ / 2, start + (depth - ch_) / 2, cw_, ch_)
        else:
            box = (start + (depth - cw_) / 2, c - ch_ / 2, cw_, ch_)
        cid = f"{aid}-{k}"
        if m[0] == "image":
            pic = m[1]
            drawn.append({"id": cid, "kind": "image", "box": [round(v) for v in box], **pic.emit_fields()})
            footprint.append({"rect": box})
            continue
        if shape is not None:
            drawn.append({"id": f"{cid}-shape", "kind": "rect", "box": [round(v) for v in box], "fill_role": shape.get("fill_role"),
                          "line_role": shape.get("line_role"), "line_width_emu": round(float(shape.get("line_width_pt", 0)) * EMU_PER_PT) or None,
                          "prst": SHAPES[shape["prst"]]})
            lw = round(float(shape.get("line_width_pt", 0)) * EMU_PER_PT)
            footprint.append({"rect": box} if shape.get("fill_role") else {"outline": box, "width": lw})
        _, text, lines, w, h, fit = m
        tb = (box[0] + (box[2] - w) / 2, box[1] + (box[3] - h) / 2, w, h)
        drawn.append(lab.text_element(f"{cid}-text", {"text": text, **text_style}, tb, lines, fit, "center", anchor="m"))
        footprint.append({"rect": tb, "text": True, "tokens": text.split()})
    if across:
        row_rect = (p.left, start, p.width, depth)
    else:
        row_rect = (start, p.top, depth, p.height)
    label = ann.get("label")
    if label:
        if across:
            # the row's name before the first category: from the chart frame's edge to the plot's
            room = p.left - host["box"][0]
            if room <= 0:
                raise AnnotationRefused(f"{where} label: the plot leaves no room left of it for the row's name; move plot_area.x right")
            share = label.get("max_width_share")
            limit = min(room, share * host["box"][2]) if share is not None else room
            lines, w, h, fit = lab.measure(label, limit, f"{where} label")
            if "align" not in label:
                default("label.align", "label.align.category_row")
            lb = (p.left - w, start + (depth - h) / 2, w, h)
            al = label.get("align", "right")
        else:
            lines, w, h, fit = lab.measure(label, depth if label.get("max_width_share") is None else label["max_width_share"] * host["box"][2], f"{where} label")
            if "align" not in label:
                default("label.align", "label.align.category_row")
            lb = (start + (depth - w) / 2, p.top - h, w, h)
            al = label.get("align", "center")
        if al not in ("left", "center", "right"):
            raise AnnotationRefused(f"{where} label: align {al!r} not in left, center, right")
        drawn.append(lab.text_element(f"{aid}-label", label, lb, lines, fit, al, anchor="m"))
        footprint.append({"rect": lb, "text": True, "tokens": label["text"].split()})
    return drawn, footprint, row_rect


def _band_visible_on_table(host: dict, box: tuple, eg: EmitGuide, where: str) -> None:
    """A band is drawn under the table; a row the table fills itself hides it
    (emit_pptx.table_row_styles, the rows as the emitter writes them)."""
    from emit_pptx import table_row_styles
    xs, ys = table_geometry(host)
    for st, top, bottom in zip(table_row_styles(host, eg), ys, ys[1:]):
        if not (bottom > box[1] and top < box[1] + box[3]):
            continue
        for cs, left, right in zip(st["cells"], xs, xs[1:]):
            if right > box[0] and left < box[0] + box[2] and cs["fill_hex"]:
                raise AnnotationRefused(f"{where}: {'header row ' + str(st['row']) if st['header'] else 'body row ' + str(st['row'] - int(host.get('header_rows', 1)))} ({cs['class']}) is filled with {cs['fill_name']}, which hides a band drawn under it; "
                                        "colour the cells through the table (emphasis, banding_role) instead")


# --- what a mark means ------------------------------------------------------------------

VOCABULARY = json.loads((Path(__file__).resolve().parent.parent / "references" / "page_craft_vocabulary.json").read_text())
#: the kinds that can be drawn saying nothing (an outline, a fill, a line, a bracket), and
#: the digest's annotation moves each one draws, which a house precedent must show
MARK_MOVES: dict[str, list[str]] = VOCABULARY["annotation_kind_moves"]
EXPLAINED_BY = ("text", "annotation", "legend", "footnote", "house_precedent")
EXPLAINED_EXAMPLE = ('{"text": "<page text element id>", "quote": "<its words naming what the mark encloses>"}, '
                     '{"annotation": "<a labelled annotation on the same host and anchor: a callout or arrow saying what it marks>"}, '
                     '{"legend": "<series name the host chart\'s legend shows in the mark\'s ink>"}, '
                     '{"footnote": {"marker": "*", "note": "<text element id whose paragraph starts with the marker>"}} or '
                     '{"house_precedent": {"slide": N}} (a digest record on reference slide N with the same move drawn unlabelled)')
FOOTNOTE_MARKER = re.compile(r"^(\*{1,3}|†|‡|§|\(\w{1,2}\)|\[\w{1,2}\])$")
#: a word runs on through letters and digits ("CET1" is one word, not "CET" and a "1")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'&]*|\d[\d,]*(?:\.\d+)?")
_STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "its", "per", "than", "into", "over", "all", "but", "not", "has", "have"}


class AnnotationUnexplained(AnnotationRefused):
    """A mark that says nothing about what it marks."""


def _words(text: str) -> tuple[set[str], list[tuple[float, int]]]:
    """The words (three letters or more, lower case, common joiners left out) and the
    numbers (value, decimals as written) of a text."""
    words: set[str] = set()
    numbers: list[tuple[float, int]] = []
    for tok in _TOKEN.findall(text):
        if tok[0].isdigit():
            plain = tok.replace(",", "")
            numbers.append((float(plain), len(plain.split(".")[1]) if "." in plain else 0))
        elif len(tok) >= 3 and tok.lower() not in _STOP:
            words.add(tok.lower())
    return words, numbers


def anchor_content(host: dict, anchor: dict, where: str) -> tuple[list[str], list[float]]:
    """What the mark encloses, as the host draws it: the texts (cell text, row labels and
    column heads of a table anchor; category and series names on a chart) and the numbers
    (the values of the marks spanned, or the value a line or band stands at)."""
    texts: list[str] = []
    numbers: list[float] = []
    if host["kind"] == "table":
        r0, r1, c0, c1 = table_anchor(host, anchor, where)["cells"]
        h = int(host.get("header_rows", 1))
        cols = host["columns"]
        n_body = len(host["rows"])
        # a heading or a row label names what the mark encloses only where it picks the
        # mark out: a column's heading for a mark that encloses the heading or only some
        # of the columns, a row's label for a mark that encloses the label or only some
        # of the rows. A box round one whole row is not named by the heading of every
        # column it crosses ("P / TBV" does not say which company is boxed).
        every_column = c0 <= 1 and c1 == len(cols) - 1
        every_row = r0 <= h and r1 == h + n_body - 1
        if r0 < h or not every_column:
            texts += [str(cols[c].get("label") or "") for c in range(c0, c1 + 1)]
        for r in range(max(r0, h), r1 + 1):
            row = host["rows"][r - h]
            if c0 > 0 and not every_row:
                texts.append(str(row[0]))
            texts += [str(row[c]) for c in range(c0, c1 + 1)]
        return texts, numbers
    geo = ChartGeometry(host, host["box"])
    keys = set(anchor)
    series = list(range(len(geo.series)))
    cats: list[int] = []
    if keys == {"point"}:
        pt = anchor["point"]
        series = [geo._series_index(pt["series"])]
        if geo.family != "xy":
            cats = [geo._category_index(pt.get("category", pt.get("index")))]
        else:
            numbers += [float(v) for v in geo.series[series[0]]["values"][pt["index"]][:2] if _num(v)]
    elif keys == {"categories"} or (keys == {"region"} and geo.family != "xy"):
        span = anchor["categories"] if keys == {"categories"} else anchor["region"]["categories"]
        i0, i1 = sorted(geo._category_index(c) for c in _pair(span, where, "categories"))
        cats = list(range(i0, i1 + 1))
        if keys == {"region"}:
            numbers += [float(v) for v in anchor["region"]["values"] if _num(v)]
    elif keys == {"category"}:
        texts.append(str(geo.categories[geo._category_index(anchor["category"])]))
    elif "value" in keys:
        numbers.append(float(anchor["value"]))
    elif "values" in keys:
        numbers += [float(v) for v in anchor["values"] if _num(v)]
    elif keys == {"region"}:
        numbers += [float(v) for k in ("x", "y") for v in anchor["region"].get(k, []) if _num(v)]
    texts += [str(geo.series[j].get("name") or "") for j in series]
    for i in cats:
        texts.append(str(geo.categories[i]))
        for j in series:
            vals = geo.series[j].get("values") or []
            if i < len(vals) and _num(vals[i]):
                numbers.append(float(vals[i]))
    return texts, numbers


def _significant(v: float, decimals: int) -> int:
    """Significant digits of a figure as written ("1.4" 2, "75" 2, "1" 1, "0.05" 1)."""
    digits = f"{v:.{decimals}f}".replace(".", "").lstrip("0")
    return len(digits)


def _ties(quote: str, texts: list[str], numbers: list[float]) -> list[str]:
    """What the quote shares with the anchor: a word, or a number equal to an anchored
    value at the quote's own rounding (a value of 0.1 also reads as 10%). A figure of
    one significant digit ties only a value it equals exactly: "1" read at its own
    rounding would tie every value from 0.5 to 1.5."""
    q_words, q_numbers = _words(quote)
    a_words: set[str] = set()
    a_numbers = list(numbers)
    for t in texts:
        w, n = _words(t)
        a_words |= w
        a_numbers += [v for v, _ in n]
    shared = sorted(q_words & a_words)
    for v, d in q_numbers:
        tol = 0.5 * 10 ** -d + 1e-9 if _significant(v, d) >= 2 else 1e-9
        if any(abs(abs(a) - v) <= tol or abs(abs(a) * 100 - v) <= tol for a in a_numbers):
            shared.append(f"{v:g}")
    return shared


def _paragraph_texts(el: dict) -> list[str]:
    return ["".join(r.get("text") or "" for r in p.get("runs") or []) for p in el.get("paragraphs") or []]


def _id_of(value, where: str) -> str:
    """An id or name the explanation looks up: one non-empty string, refused otherwise
    (a list names no one element)."""
    if not isinstance(value, str) or not value.strip():
        raise AnnotationRefused(f"{where} is one id, a non-empty string; got {value!r}")
    return value


def explanation(ann: dict, kind: str, host: dict, by_id: dict, guide: dict, plan_types: list[str] | None, where: str,
                siblings: dict | None = None) -> dict | None:
    """How a mark says what it means, proven, or AnnotationUnexplained. A mark that carries
    a label says it itself (None: nothing to prove). Otherwise `explained_by` names one of:
    a text element on the page and the words in it that name what the mark encloses (a
    word or figure of the anchored cells, categories, series or values); another
    annotation of the page (siblings, by id) on the same host and anchor that carries a
    label (a callout or arrow saying what the band or box marks); a legend entry of
    the host chart drawn in the mark's own ink; a footnote marker that ends a text the
    mark encloses and starts a paragraph of the named note; or a page of the house's
    digest where the same move is drawn unlabelled on an exhibit of the host's class (and
    of a type the plan lists for this page, given --plan). The model decides which; this
    only checks that what it names is there."""
    if kind not in MARK_MOVES:
        return None
    if "label" in ann:
        if "explained_by" in ann:
            raise AnnotationRefused(f"{where}: a label says what the mark means; explained_by beside it is a second answer, give one")
        return None
    how = ann.get("explained_by")
    if how is None:
        raise AnnotationUnexplained(f"{where}: an unlabelled {kind} says nothing about what it marks (a reader sees a shape and no reason). "
                                    f"Give it a label, or explained_by: {EXPLAINED_EXAMPLE}")
    shapes = ({"text", "quote"}, {"annotation"}, {"legend"}, {"footnote"}, {"house_precedent"})
    if not isinstance(how, dict) or set(how) not in shapes:
        raise AnnotationRefused(f"{where}: explained_by is one of {EXPLAINED_EXAMPLE}; got {how!r}")
    for key in ("text", "annotation", "legend"):
        if key in how:
            _id_of(how[key], f"{where}: explained_by.{key}")
    if "text" in how:
        el = by_id.get(how["text"])
        if el is None or el.get("kind") != "text":
            raise AnnotationUnexplained(f"{where}: explained_by.text {how['text']!r} is not a text element of this page")
        quote = how["quote"]
        if not isinstance(quote, str) or not quote.strip():
            raise AnnotationRefused(f"{where}: explained_by.quote is the words of {how['text']!r} that say what the mark encloses")
        body = " ".join(" ".join(t.split()) for t in _paragraph_texts(el))
        if " ".join(quote.split()) not in body:
            raise AnnotationUnexplained(f"{where}: the quote {quote!r} is not in {how['text']!r} (it reads {body[:160]!r})")
        texts, numbers = anchor_content(host, ann["anchor"], where)
        shared = _ties(quote, texts, numbers)
        if not shared:
            raise AnnotationUnexplained(f"{where}: the quote {quote!r} names nothing the mark encloses; the anchor holds {[t for t in texts if t][:8]} "
                                        f"and values {[round(v, 4) for v in numbers][:8]}: quote the words that name it")
        return {"by": "text", "element": how["text"], "quote": quote, "shares": shared}
    if "annotation" in how:
        other = (siblings or {}).get(how["annotation"])
        if not isinstance(other, dict) or other is ann:
            raise AnnotationUnexplained(f"{where}: explained_by.annotation {how['annotation']!r} is not another annotation of this page")
        if not isinstance(other.get("label"), dict) or other.get("host") != ann.get("host") or other.get("anchor") != ann.get("anchor"):
            raise AnnotationUnexplained(f"{where}: annotation {how['annotation']!r} explains this mark only with a label, on the same host and the same anchor "
                                        f"(it has {'a' if isinstance(other.get('label'), dict) else 'no'} label, host {other.get('host')!r}, anchor {other.get('anchor')!r})")
        return {"by": "annotation", "annotation": how["annotation"], "says": other["label"].get("text")}
    if "legend" in how:
        from emit_pptx import chart_legend
        name = how["legend"]
        if host["kind"] != "chart":
            raise AnnotationUnexplained(f"{where}: explained_by.legend names a legend entry, and the host {host['id']!r} is a table")
        legend = chart_legend(host)
        if not isinstance(legend, dict):
            raise AnnotationUnexplained(f"{where}: the host chart draws no legend, so no entry explains the mark")
        names = [s.get("name") for s in host.get("series") or []]
        hidden = {int(i) for i in legend.get("hide_entries") or []}
        if names.count(name) != 1 or names.index(name) in hidden:
            raise AnnotationUnexplained(f"{where}: the legend shows no one entry {name!r} (entries {[n for i, n in enumerate(names) if i not in hidden]})")
        s = host["series"][names.index(name)]
        ink = ann.get("line_role") or ann.get("fill_role")
        if ink not in (s.get("fill_role"), s.get("line_role")):
            raise AnnotationUnexplained(f"{where}: legend entry {name!r} is drawn in {s.get('fill_role') or s.get('line_role')!r} and the mark in {ink!r}; "
                                        "a legend explains a mark drawn in its swatch's ink")
        return {"by": "legend", "entry": name}
    if "footnote" in how:
        fn = how["footnote"]
        if not isinstance(fn, dict) or set(fn) != {"marker", "note"}:
            raise AnnotationRefused(f"{where}: explained_by.footnote is {{\"marker\", \"note\"}}")
        _id_of(fn["note"], f"{where}: explained_by.footnote.note")
        mk = fn["marker"]
        if not isinstance(mk, str) or not FOOTNOTE_MARKER.match(mk):
            raise AnnotationRefused(f"{where}: footnote marker {mk!r} is not a marker (*, **, †, ‡, §, (1), [a])")
        note = by_id.get(fn["note"])
        if note is None or note.get("kind") != "text":
            raise AnnotationUnexplained(f"{where}: footnote note {fn['note']!r} is not a text element of this page")
        if not any(t.lstrip().startswith(mk) for t in _paragraph_texts(note)):
            raise AnnotationUnexplained(f"{where}: no paragraph of {fn['note']!r} starts with {mk!r}")
        texts, _ = anchor_content(host, ann["anchor"], where)
        if not any(t.rstrip().endswith(mk) for t in texts):
            raise AnnotationUnexplained(f"{where}: no text the mark encloses ends with {mk!r} (it holds {[t for t in texts if t][:8]}); "
                                        "put the marker on the figure or label it explains")
        return {"by": "footnote", "marker": mk, "note": fn["note"]}
    hp = how["house_precedent"]
    slide = hp.get("slide") if isinstance(hp, dict) and set(hp) == {"slide"} else None
    if not isinstance(slide, int) or isinstance(slide, bool):
        raise AnnotationRefused(f"{where}: explained_by.house_precedent is {{\"slide\": N}}, a reference page of the digest")
    records = (guide.get("exhibit_habits") or {}).get("records")
    if not isinstance(records, list):
        raise AnnotationUnexplained(f"{where}: the guide holds no completed digest (/exhibit_habits), so no house precedent can be read")
    klass = {"table": "table", "chart": "data_chart"}[host["kind"]]
    moves = MARK_MOVES[kind]
    seen: list[str] = []
    for r in records:
        if not isinstance(r, dict) or r.get("slide") != slide:
            continue
        for m in r.get("annotation_moves") or []:
            if not isinstance(m, dict) or m.get("move") not in moves:
                continue
            what = f"slide {slide} {r.get('type')} ({r.get('class')}): {m['move']} on {m.get('anchor')!r}"
            if r.get("class") != klass:
                seen.append(f"{what}: a {r.get('class')}, the host is a {klass}")
            elif "labelled" not in m:
                seen.append(f"{what}: the digest does not say whether it is labelled (answer labelled on the move and re-run --digest)")
            elif m["labelled"] is not False:
                seen.append(f"{what}: labelled there, so it is precedent for a labelled mark only")
            elif plan_types is not None and r.get("type") not in plan_types:
                seen.append(f"{what}: a {r.get('type')}, and the plan lists {plan_types} for this page")
            else:
                return {"by": "house_precedent", "slide": slide, "type": r.get("type"), "move": m["move"], "anchor": m.get("anchor"),
                        "type_checked": plan_types is not None}
    raise AnnotationUnexplained(f"{where}: reference slide {slide} shows no unlabelled {' or '.join(moves)} on a {klass}"
                                + (f" ({'; '.join(seen)})" if seen else " (the digest records no such move there)"))


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


def _covering(e: dict) -> list[dict]:
    """The footprint parts that can collide: all of them, except a band's fill, which is
    ground under its host. A band's label is text like any other."""
    return [fp for fp in e["_footprint"] if e["kind"] != "band" or fp.get("text")]


def collisions(elements: list[dict], report: list[dict], page_w: int, page_h: int, zones: list[dict]) -> list[dict]:
    """Refusals from the solved boxes: an annotation over another page element (a filled
    ground that contains it is no collision), over another annotation (a band is ground),
    past the page edge, or in a reserved chrome zone. The host is the annotation's anchor
    and is never a collision. A band's fill covers nothing; its label is checked against
    the host's marks (all of them: it lies under the host) and every other annotation."""
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
        # a reference line crosses the marks by design; its label may not
        for fp in _covering(e):
            if e["kind"] == "reference_line" and "segment" in fp:
                continue
            hits += [name for name, m in e.get("_other_marks", []) if covers(fp, m)]
            if fp.get("text"):
                # a label lies on the page's ink: a line series stroked through it hides words
                hits += [name for name, seg, width in e.get("_lines", []) if _segment_hits(seg, width, fp["rect"])]
        for other in placed:
            if other is e:
                continue
            if any(covers(fp, _bbox(ofp)) for fp in _covering(e) for ofp in _covering(other)):
                hits.append(f"annotation {other['id']}")
        hits = list(dict.fromkeys(hits))
        e["collisions"] = hits
        if hits:
            out.append({"kind": "annotation collides", "severity": "refusal", "detail": f"annotation {e['id']!r} ({e['kind']}) covers {', '.join(hits)}"})
    return out


# --- after the render: the host's own text ---------------------------------------------------

_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
_PAGE = re.compile(r"<page width=\"([\d.]+)\" height=\"([\d.]+)\">(.*?)</page>", re.DOTALL)


class RenderUnread(RuntimeError):
    """The render's words could not be read, so the host's text is unknown."""


def pdf_words(pdf: str) -> list[list[tuple[tuple[float, float, float, float], str]]]:
    """Every word LibreOffice drew, per page, as an EMU box (pdftotext -bbox)."""
    try:
        done = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RenderUnread(f"pdftotext did not run: {error}") from None
    if done.returncode != 0:
        raise RenderUnread(f"pdftotext exited {done.returncode}: {done.stderr.strip()[-200:]}")
    pages = []
    for m in _PAGE.finditer(done.stdout):
        words = []
        for w in _WORD.finditer(m.group(3)):
            x0, y0, x1, y1 = (float(v) * EMU_PER_PT for v in w.groups()[:4])
            words.append(((x0, y0, x1 - x0, y1 - y0), html.unescape(w.group(5))))
        pages.append(words)
    return pages


def _label_words(placed: list[dict], words: list[tuple]) -> set[int]:
    """Indices of the words that are an annotation label's own: inside the label's box and
    one of its tokens, each token taken once. A word of the host under a label is not."""
    own: set[int] = set()
    for e in placed:
        for fp in e["_footprint"]:
            if not fp.get("text"):
                continue
            tokens = list(fp["tokens"])
            for k, (box, text) in enumerate(words):
                centre = (box[0] + box[2] / 2, box[1] + box[3] / 2, 0, 0)
                if k not in own and text in tokens and _contains(fp["rect"], centre):
                    tokens.remove(text)
                    own.add(k)
    return own


def render_check(entry_annotations: list[dict], elements: list[dict], words: list[tuple]) -> list[dict]:
    """Every word the renderer drew inside an annotation's host (tick labels, data labels,
    legend, cell text), against what each annotation covers: its strokes and boxes, and
    for a band its label only (the fill lies under the host's text by design). A word of
    an annotation's own label, or inside another element's box (checked before the
    emit), is not the host's. Returns the refusals and fills each entry's `render_check`."""
    out: list[dict] = []
    placed = [e for e in entry_annotations if e.get("status") == "placed"]
    own_words = _label_words(placed, words)
    own = {d for e in placed for d in e["drawn"]}
    others = [el for el in elements if el["id"] not in own]
    for e in placed:
        host_box = tuple(e["_host_box"])
        candidates = []
        for k, (box, text) in enumerate(words):
            centre = (box[0] + box[2] / 2, box[1] + box[3] / 2, 0, 0)
            if k in own_words or not _contains(host_box, centre):
                continue
            if any(el["id"] != e["host"] and el["kind"] in ("text", "table", "chart") and _contains(tuple(el["box"]), centre) for el in others):
                continue
            candidates.append((box, text))
        # pdftotext's word box runs from the face's ascent to its descent, taller than the
        # ink: a stroke inside that box but clear of the ink is still counted as a crossing
        crossed = [text for box, text in candidates if any(covers(fp, box) for fp in _covering(e))]
        e["render_check"] = {"host_words": len(candidates), "covered": crossed}
        if crossed:
            out.append({"kind": "annotation covers chart text", "severity": "refusal",
                        "detail": f"annotation {e['id']!r} ({e['kind']}) covers {len(crossed)} word(s) its host drew: {crossed[:6]}"})
    return out
