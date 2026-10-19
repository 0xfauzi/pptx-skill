#!/usr/bin/env python3
"""Write slides onto the reference's own package from a resolved slide spec and a style guide.

    emit_pptx.py resolved.json --template tpl.pptx --guide guide.json -o out.pptx [--chrome auto|none]

`tpl.pptx` is the reference with its slides removed (pptx_tools.py template): masters,
layouts, theme and chrome stay, so every inherited value is the reference's (deckgen E18:
master reuse). The spec carries TOKEN ROLES and content only. A colour is a role name in
the guide (`color.ink`, `color.accent2`, `color.extra_3`), a text style is a type role
(`type.body`); a literal hex or point size in the spec is refused unless the element is
marked `"foreign": true`. Boxes are integer EMU from the layout solver.

Spec shape (one slide shown):
{
 "slides": [
  {"layout": "Title and Content",
   "title": {"text": "Action title", "role": "type.title"},
   "elements": [
    {"id": "body", "kind": "text", "box": [x, y, w, h],
     "paragraphs": [{"role": "type.body", "bullet_level": 0,
                     "runs": [{"text": "Plain "}, {"text": "bold", "emphasis": true}],
                     "lines": ["Plain bold"]}],
     "fill_role": null, "line_role": null, "anchor": "t"},
    {"id": "comps", "kind": "table", "box": [...], "header_rows": 1,
     "columns": [{"key": "name", "label": "Company", "value_kind": "label"}, {"key": "ev", "label": "EV ($m)", "value_kind": "number"}],
     "rows": [["Acme", "1,234"]], "column_widths_emu": [...], "row_heights_emu": [...], "totals_last_row": false},
    {"id": "chart", "kind": "chart", "box": [...], "chart_kind": "column", "categories": ["2023", "2024"],
     "series": [{"name": "Revenue", "values": [1.0, 2.0]}], "number_format": "0.0", "data_labels": true, "legend": null},
    {"id": "rule", "kind": "rule", "box": [...], "line_role": "color.rule"},
    {"id": "band", "kind": "rect", "box": [...], "fill_role": "color.accent1", "prst": "rect"},
    {"id": "logo", "kind": "image", "box": [...], "path": "logo.png"}
   ],
   "notes": "speaker notes"}
 ]
}
Text bodies are written with zero insets, square wrap and explicit noAutofit, paragraph
spacing and line pitch as absolute points, and, when the solver measured the wrap, the
measured lines as literal breaks: the file carries the wrap the fit decision was made on.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

EMU_PER_PT = 12700
HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


class SpecError(SystemExit):
    pass


# --- guide access -------------------------------------------------------------------------------


class Guide:
    def __init__(self, data: dict) -> None:
        self.g = data
        self.roles = data.get("typography", {}).get("roles", {})
        self.families = data.get("typography", {}).get("families", {})
        colors = dict(data.get("color", {}).get("roles", {}))
        colors.update(data.get("extra_roles", {}))
        self.colors = colors
        self.spacing = data.get("spacing", {}).get("steps", {})
        self.tables = data.get("tables") or {}
        self.charts = data.get("charts") or {}

    def hex(self, role: str | None, *, where: str) -> str | None:
        if role is None:
            return None
        if HEX_RE.match(role):
            raise SpecError(f"{where}: literal colour {role!r}; use a colour role from the guide")
        entry = self.colors.get(role)
        if entry is None:
            raise SpecError(f"{where}: unknown colour role {role!r}; guide roles: {sorted(self.colors)}")
        return entry["hex"]

    def type_spec(self, role: str, *, where: str) -> dict:
        spec = self.roles.get(role)
        if spec is None:
            raise SpecError(f"{where}: unknown type role {role!r}; guide roles: {sorted(self.roles)}")
        if spec.get("partial"):
            # a ladder-derived role has a size only: the other members ride on the body role
            base = dict(self.roles.get("type.body", {}))
            base.update({k: v for k, v in spec.items() if v is not None})
            spec = base
        return spec

    def face(self, spec: dict) -> str:
        fam = spec.get("family")
        if fam in ("major", "minor"):
            return self.families.get(fam) or self.families.get("minor") or "Arial"
        return fam or self.families.get("minor") or "Arial"

    def space(self, role: str | None, default: int = 0) -> int:
        if role is None:
            return default
        entry = self.spacing.get(role)
        if entry is None:
            raise SpecError(f"unknown spacing role {role!r}; guide steps: {sorted(self.spacing)}")
        return int(entry["emu"])


# --- xml helpers ----------------------------------------------------------------------------------


def _solid_fill(parent: etree._Element, hex_color: str) -> None:
    for child in list(parent):
        if child.tag in (qn("a:noFill"), qn("a:solidFill"), qn("a:gradFill"), qn("a:blipFill"), qn("a:pattFill")):
            parent.remove(child)
    sf = etree.SubElement(parent, qn("a:solidFill"))
    etree.SubElement(sf, qn("a:srgbClr")).set("val", hex_color.upper())


def _insert_fill_first(parent: etree._Element, fill: etree._Element) -> None:
    """DrawingML orders fill before ln/effects: put a fill right after xfrm/prstGeom."""
    anchor = 0
    for i, child in enumerate(parent):
        if child.tag in (qn("a:xfrm"), qn("a:prstGeom"), qn("a:custGeom")):
            anchor = i + 1
    parent.insert(anchor, fill)


def _set_line(sp_pr: etree._Element, hex_color: str | None, width_emu: int | None, dash: str | None = None) -> None:
    ln = sp_pr.find(qn("a:ln"))
    if ln is None:
        ln = etree.SubElement(sp_pr, qn("a:ln"))
    for child in list(ln):
        ln.remove(child)
    if hex_color is None:
        etree.SubElement(ln, qn("a:noFill"))
        return
    if width_emu:
        ln.set("w", str(int(width_emu)))
    sf = etree.SubElement(ln, qn("a:solidFill"))
    etree.SubElement(sf, qn("a:srgbClr")).set("val", hex_color.upper())
    if dash and dash != "solid":
        etree.SubElement(ln, qn("a:prstDash")).set("val", dash)


ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY}


def _style_run(run, spec: dict, guide: Guide, *, emphasis: bool, ink_hex: str | None) -> None:
    font = run.font
    font.name = guide.face(spec)
    font.size = Pt(float(spec["size_pt"]))
    font.bold = bool(spec.get("weight", 400) >= 700 or emphasis)
    font.italic = bool(spec.get("italic", False))
    if ink_hex:
        font.color.rgb = RGBColor.from_string(ink_hex.upper())
    if spec.get("case") == "upper":
        run.text = run.text.upper()
    rpr = run._r.get_or_add_rPr()
    tracking = spec.get("tracking_pt") or 0.0
    if tracking:
        rpr.set("spc", str(int(round(tracking * 100))))


def _paragraph_props(p, spec: dict, guide: Guide, para: dict) -> None:
    p_pr = p._p.get_or_add_pPr()
    for tag in ("a:lnSpc", "a:spcBef", "a:spcAft", "a:buNone", "a:buChar", "a:buAutoNum", "a:buFont"):
        for el in p_pr.findall(qn(tag)):
            p_pr.remove(el)
    size = float(spec["size_pt"])
    ls = spec.get("line_spacing") or 1.2  # measured default pitch (deckgen E16: 1.2002 x size, font independent)
    ln = etree.SubElement(p_pr, qn("a:lnSpc"))
    etree.SubElement(ln, qn("a:spcPts")).set("val", str(int(round(ls * size * 100))))
    bef = etree.SubElement(p_pr, qn("a:spcBef"))
    etree.SubElement(bef, qn("a:spcPts")).set("val", str(int(round((para.get("space_before_pt", spec.get("space_before_pt")) or 0.0) * 100))))
    aft = etree.SubElement(p_pr, qn("a:spcAft"))
    etree.SubElement(aft, qn("a:spcPts")).set("val", str(int(round((para.get("space_after_pt", spec.get("space_after_pt")) or 0.0) * 100))))
    level = para.get("bullet_level")
    align = para.get("align") or spec.get("alignment") or "left"
    p.alignment = ALIGN.get(align, PP_ALIGN.LEFT)
    if level is None:
        etree.SubElement(p_pr, qn("a:buNone"))
        p_pr.set("marL", "0")
        p_pr.set("indent", "0")
    else:
        bullets = guide.g.get("typography", {}).get("bullets", {})
        entry = bullets.get(str(level)) or bullets.get(level) or bullets.get("0") or {}
        glyph = entry.get("glyph") or "\u2022"
        bufont = entry.get("font")
        indent = guide.space(para.get("indent_role") or ("space.sm" if "space.sm" in guide.spacing else None), 228600)
        p_pr.set("lvl", str(int(level)))
        p_pr.set("marL", str(indent * (int(level) + 1)))
        p_pr.set("indent", str(-indent))
        if bufont:
            etree.SubElement(p_pr, qn("a:buFont")).set("typeface", bufont)
        bu = etree.SubElement(p_pr, qn("a:buChar"))
        bu.set("char", glyph)


def _body_props(txBody: etree._Element, anchor: str) -> None:
    body_pr = txBody.find(qn("a:bodyPr"))
    if body_pr is None:
        body_pr = etree.SubElement(txBody, qn("a:bodyPr"))
        txBody.insert(0, body_pr)
    for k in ("lIns", "tIns", "rIns", "bIns"):
        body_pr.set(k, "0")
    body_pr.set("wrap", "square")
    body_pr.set("anchor", {"t": "t", "m": "ctr", "b": "b"}.get(anchor, "t"))
    for tag in ("a:normAutofit", "a:spAutoFit", "a:noAutofit"):
        for el in body_pr.findall(qn(tag)):
            body_pr.remove(el)
    etree.SubElement(body_pr, qn("a:noAutofit"))


# --- element writers ---------------------------------------------------------------------------------


def write_text(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    shape = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    shape.name = el.get("id", "text")
    sp_pr = shape._element.spPr
    fill_hex = guide.hex(el.get("fill_role"), where=el.get("id", "text"))
    if fill_hex:
        _solid_fill(sp_pr, fill_hex)
    line_hex = guide.hex(el.get("line_role"), where=el.get("id", "text"))
    if el.get("line_role"):
        _set_line(sp_pr, line_hex, el.get("line_width_emu") or 9525)
    tf = shape.text_frame
    tf.word_wrap = True
    _body_props(tf._txBody, el.get("anchor", "t"))
    first = True
    for para in el.get("paragraphs", []):
        spec = guide.type_spec(para["role"], where=el.get("id", "text"))
        ink_hex = guide.hex(para.get("ink_role") or spec.get("ink_role"), where=para["role"]) if (para.get("ink_role") or spec.get("ink_role")) else (spec.get("ink") if HEX_RE.match(spec.get("ink") or "") else None)
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        _paragraph_props(p, spec, guide, para)
        runs = para.get("runs") or [{"text": para.get("text", "")}]
        lines = para.get("lines")
        if lines:
            # measured wrap: literal breaks between lines, runs split at line boundaries
            full = "".join(r["text"] for r in runs)
            if "".join(lines).replace(" ", "") != full.replace(" ", ""):
                raise SpecError(f"{el.get('id')}: measured lines do not reconstruct the paragraph text")
            cursor = 0
            run_spans = []
            for r in runs:
                run_spans.append((cursor, cursor + len(r["text"]), r))
                cursor += len(r["text"])
            pos = 0
            for li, line in enumerate(lines):
                start = full.find(line, pos)
                if start < 0:
                    start = pos
                end = start + len(line)
                for s0, s1, r in run_spans:
                    a, b = max(s0, start), min(s1, end)
                    if a < b:
                        pr = p.add_run()
                        pr.text = full[a:b]
                        _style_run(pr, spec, guide, emphasis=bool(r.get("emphasis")), ink_hex=ink_hex)
                if li < len(lines) - 1:
                    p._p.append(etree.Element(qn("a:br")))
                pos = end
        else:
            for r in runs:
                pr = p.add_run()
                pr.text = r["text"]
                _style_run(pr, spec, guide, emphasis=bool(r.get("emphasis")), ink_hex=ink_hex)


def write_rule(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    horizontal = w >= h
    line = slide.shapes.add_connector(1, Emu(x), Emu(y + (h // 2 if horizontal else 0)), Emu(x + w if horizontal else x), Emu(y + (h // 2) if horizontal else y + h))
    line.name = el.get("id", "rule")
    hex_color = guide.hex(el.get("line_role") or "color.rule", where=el.get("id", "rule"))
    width = el.get("line_width_emu") or (guide.g.get("motifs") or [{}])[0].get("line_width_pt")
    width_emu = int(round(float(width) * EMU_PER_PT)) if isinstance(width, (int, float)) and width and not el.get("line_width_emu") else (el.get("line_width_emu") or 9525)
    _set_line(line._element.spPr, hex_color, width_emu, el.get("dash"))


def write_rect(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    prst = {"rect": MSO_SHAPE.RECTANGLE, "roundRect": MSO_SHAPE.ROUNDED_RECTANGLE, "ellipse": MSO_SHAPE.OVAL, "chevron": MSO_SHAPE.CHEVRON,
            "rightArrow": MSO_SHAPE.RIGHT_ARROW, "diamond": MSO_SHAPE.DIAMOND, "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE}.get(el.get("prst", "rect"), MSO_SHAPE.RECTANGLE)
    shape = slide.shapes.add_shape(prst, Emu(x), Emu(y), Emu(w), Emu(h))
    shape.name = el.get("id", "rect")
    sp_pr = shape._element.spPr
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)  # theme style refs would paint accent1 and a line the guide never chose
    fill_hex = guide.hex(el.get("fill_role"), where=el.get("id", "rect"))
    if fill_hex:
        _solid_fill(sp_pr, fill_hex)
    else:
        for child in list(sp_pr):
            if child.tag == qn("a:solidFill"):
                sp_pr.remove(child)
        _insert_fill_first(sp_pr, etree.Element(qn("a:noFill")))
    line_hex = guide.hex(el.get("line_role"), where=el.get("id", "rect"))
    _set_line(sp_pr, line_hex, el.get("line_width_emu") or 9525, el.get("dash"))
    if el.get("paragraphs"):
        tf = shape.text_frame
        tf.word_wrap = True
        _body_props(tf._txBody, el.get("anchor", "m"))
        first = True
        for para in el["paragraphs"]:
            spec = guide.type_spec(para["role"], where=el.get("id", "rect"))
            ink_hex = guide.hex(para.get("ink_role"), where=el.get("id", "rect")) if para.get("ink_role") else None
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            _paragraph_props(p, spec, guide, para)
            for r in para.get("runs") or [{"text": para.get("text", "")}]:
                pr = p.add_run()
                pr.text = r["text"]
                _style_run(pr, spec, guide, emphasis=bool(r.get("emphasis")), ink_hex=ink_hex)
        tf.margin_left = tf.margin_right = Emu(guide.space(el.get("pad_role"), 0))
        tf.margin_top = tf.margin_bottom = Emu(guide.space(el.get("pad_role"), 0))


def write_image(slide, el: dict, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    pic = slide.shapes.add_picture(el["path"], Emu(x), Emu(y), Emu(w), Emu(h))
    pic.name = el.get("id", "image")


def _table_edge(guide: Guide, klass: str) -> tuple[str | None, int]:
    rule = (guide.tables.get("edge_rules") or {}).get(klass)
    if not rule or rule.get("none"):
        return None, 0
    return rule.get("color_hex"), int(rule.get("width_emu") or 12700)


def _cell_border(tc_pr: etree._Element, side: str, hex_color: str | None, width_emu: int) -> None:
    for el in tc_pr.findall(qn(side)):
        tc_pr.remove(el)
    ln = etree.Element(qn(side))
    if hex_color is None or width_emu <= 0:
        ln.set("w", "0")
        etree.SubElement(ln, qn("a:noFill"))
    else:
        ln.set("w", str(width_emu))
        sf = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(sf, qn("a:srgbClr")).set("val", hex_color.upper())
    # tcPr children order: lnL, lnR, lnT, lnB, ... then fill
    order = ["a:lnL", "a:lnR", "a:lnT", "a:lnB", "a:lnTlToBr", "a:lnBlToTr"]
    idx = order.index(side)
    insert_at = 0
    for i, child in enumerate(tc_pr):
        tag = etree.QName(child).localname
        if f"a:{tag}" in order and order.index(f"a:{tag}") < idx:
            insert_at = i + 1
    tc_pr.insert(insert_at, ln)


def write_table(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    cols = el["columns"]
    rows = el["rows"]
    header_rows = int(el.get("header_rows", 1))
    n_rows = header_rows + len(rows)
    shape = slide.shapes.add_table(n_rows, len(cols), Emu(x), Emu(y), Emu(w), Emu(h))
    shape.name = el.get("id", "table")
    table = shape.table
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    for attr in ("firstRow", "bandRow", "lastRow", "firstCol", "lastCol", "bandCol"):
        tbl_pr.set(attr, "0")
    style_id = tbl_pr.find(qn("a:tableStyleId"))
    if style_id is not None:
        tbl_pr.remove(style_id)  # the guide decides every fill and rule; a built-in style would paint over them
    widths = el.get("column_widths_emu") or [w // len(cols)] * len(cols)
    for i, col in enumerate(table.columns):
        col.width = Emu(int(widths[i]))
    heights = el.get("row_heights_emu")
    pad = int(guide.tables.get("cell_padding_emu") or guide.space(guide.tables.get("cell_padding_role"), 45720))
    header_fill = guide.tables.get("header_fill_hex")
    header_ink_role = guide.tables.get("header_ink_role")
    header_ink = guide.hex(header_ink_role, where="table header") if header_ink_role else None
    band_hex = guide.tables.get("banding_hex")
    data_hex = guide.tables.get("data_fill_hex")
    header_spec = guide.type_spec("type.table_header" if "type.table_header" in guide.roles else "type.body", where="table")
    cell_spec = guide.type_spec("type.table_cell" if "type.table_cell" in guide.roles else "type.body", where="table")
    align_by_kind = guide.tables.get("alignment_by_column_type") or {}
    totals = bool(el.get("totals_last_row"))
    for ri in range(n_rows):
        row = table.rows[ri]
        if heights and ri < len(heights):
            row.height = Emu(int(heights[ri]))
        is_header = ri < header_rows
        is_totals = totals and ri == n_rows - 1
        data_index = ri - header_rows
        for ci, col in enumerate(cols):
            cell = table.cell(ri, ci)
            text = col["label"] if is_header else str(rows[data_index][ci])
            cell.margin_left = cell.margin_right = cell.margin_top = cell.margin_bottom = Emu(pad)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            run = p.add_run()
            run.text = text
            spec = header_spec if is_header else cell_spec
            kind = col.get("value_kind", "label")
            align = (align_by_kind.get("numeric") if kind in ("number", "percent", "currency") else align_by_kind.get("text")) or ("right" if kind in ("number", "percent", "currency") else "left")
            if is_header and el.get("header_align"):
                align = el["header_align"]
            p.alignment = ALIGN.get(align, PP_ALIGN.LEFT)
            _style_run(run, spec, guide, emphasis=bool(guide.tables.get("header_bold")) if is_header else is_totals,
                       ink_hex=(header_ink if is_header else (spec.get("ink") if HEX_RE.match(spec.get("ink") or "") else None)))
            ln = p._p.get_or_add_pPr()
            for tag in ("a:lnSpc", "a:spcBef", "a:spcAft"):
                for old in ln.findall(qn(tag)):
                    ln.remove(old)
            tc_pr = cell._tc.get_or_add_tcPr()
            fill_hex = header_fill if is_header else (band_hex if (band_hex and data_index % 2 == 0) else data_hex)
            for child in list(tc_pr):
                if child.tag in (qn("a:solidFill"), qn("a:noFill")):
                    tc_pr.remove(child)
            if fill_hex:
                sf = etree.SubElement(tc_pr, qn("a:solidFill"))
                etree.SubElement(sf, qn("a:srgbClr")).set("val", fill_hex.upper())
            else:
                etree.SubElement(tc_pr, qn("a:noFill"))
            top_class = "table_top" if ri == 0 else ("header_bottom" if ri == header_rows else "row_interior")
            bottom_class = "table_bottom" if ri == n_rows - 1 else ("header_bottom" if ri == header_rows - 1 else "row_interior")
            left_class = "table_left" if ci == 0 else "column_interior"
            right_class = "table_right" if ci == len(cols) - 1 else "column_interior"
            for side, klass in (("a:lnL", left_class), ("a:lnR", right_class), ("a:lnT", top_class), ("a:lnB", bottom_class)):
                hex_color, width = _table_edge(guide, klass)
                _cell_border(tc_pr, side, hex_color, width)
            if is_totals and guide.tables.get("totals_rule"):
                hex_color, width = _table_edge(guide, "header_bottom")
                _cell_border(tc_pr, "a:lnT", hex_color, width)


CHART_TYPES = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED, "stacked_column": XL_CHART_TYPE.COLUMN_STACKED, "stacked_column_100": XL_CHART_TYPE.COLUMN_STACKED_100,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED, "stacked_bar": XL_CHART_TYPE.BAR_STACKED, "line": XL_CHART_TYPE.LINE, "line_markers": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE, "doughnut": XL_CHART_TYPE.DOUGHNUT, "area": XL_CHART_TYPE.AREA, "stacked_area": XL_CHART_TYPE.AREA_STACKED,
    "scatter": XL_CHART_TYPE.XY_SCATTER,
}


def write_chart(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    kind = el.get("chart_kind", "column")
    if kind not in CHART_TYPES:
        raise SpecError(f"{el.get('id')}: chart kind {kind!r} not in {sorted(CHART_TYPES)}; build other families from rects and rules")
    data = CategoryChartData()
    data.categories = el["categories"]
    for s in el["series"]:
        data.add_series(s["name"], s["values"], number_format=el.get("number_format"))
    gf = slide.shapes.add_chart(CHART_TYPES[kind], Emu(x), Emu(y), Emu(w), Emu(h), data)
    gf.name = el.get("id", "chart")
    chart = gf.chart
    palette = list(guide.charts.get("series_color_hex") or []) or [guide.colors[r]["hex"] for r in ("color.accent1", "color.accent2", "color.accent3") if r in guide.colors]
    if not palette:
        raise SpecError("the guide has no series colours and no accents; complete color.accent1 first")
    chart.has_title = bool(el.get("title"))
    if el.get("title"):
        chart.chart_title.text_frame.text = el["title"]
    per_kind = (guide.charts.get("per_kind") or {}).get(kind.split("_")[-1]) or (guide.charts.get("per_kind") or {}).get(kind) or {}
    legend = el.get("legend")
    if legend is None:
        legend = per_kind.get("legend_position") if len(el["series"]) > 1 else None
    axis_spec = guide.roles.get("type.axis_label") or guide.roles.get("type.caption") or guide.roles.get("type.body")
    axis_ink = (axis_spec or {}).get("ink") or guide.colors.get("color.ink_muted", guide.colors.get("color.ink", {})).get("hex")
    axis_size = Pt(float((axis_spec or {"size_pt": 10})["size_pt"]))
    face = guide.face(axis_spec or {})
    chart.has_legend = bool(legend)
    if legend:
        chart.legend.position = {"b": XL_LEGEND_POSITION.BOTTOM, "t": XL_LEGEND_POSITION.TOP, "r": XL_LEGEND_POSITION.RIGHT, "l": XL_LEGEND_POSITION.LEFT}.get(legend, XL_LEGEND_POSITION.BOTTOM)
        chart.legend.include_in_layout = False
        chart.legend.font.size = axis_size
        chart.legend.font.name = face
        if axis_ink:
            chart.legend.font.color.rgb = RGBColor.from_string(axis_ink.upper())
    for plot in chart.plots:
        for si, series in enumerate(plot.series):
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor.from_string(palette[si % len(palette)].upper())
            if kind.startswith("line"):
                series.format.line.color.rgb = RGBColor.from_string(palette[si % len(palette)].upper())
                series.format.line.width = Pt(1.75)
                series.smooth = False
        plot.has_data_labels = bool(el.get("data_labels", per_kind.get("data_labels", 0) >= 0.5))
        if plot.has_data_labels:
            dl = plot.data_labels
            dl.font.size = axis_size
            dl.font.name = face
            if axis_ink:
                dl.font.color.rgb = RGBColor.from_string(axis_ink.upper())
            if el.get("number_format"):
                dl.number_format = el["number_format"]
                dl.number_format_is_linked = False
        if kind in ("column", "bar", "stacked_column", "stacked_bar"):
            plot.gap_width = int(el.get("gap_width", 60))
            if kind.startswith("stacked"):
                plot.overlap = 100
    if kind not in ("pie", "doughnut"):
        for axis in (chart.category_axis, chart.value_axis):
            axis.tick_labels.font.size = axis_size
            axis.tick_labels.font.name = face
            if axis_ink:
                axis.tick_labels.font.color.rgb = RGBColor.from_string(axis_ink.upper())
            axis.format.line.color.rgb = RGBColor.from_string((per_kind.get("axis_line_hex") or guide.colors.get("color.rule", guide.colors.get("color.ink_muted", {"hex": "808080"}))["hex"]).upper())
        grid = per_kind.get("gridlines_major")
        chart.value_axis.has_major_gridlines = bool(el.get("gridlines", (grid or 0) >= 0.5))
        if chart.value_axis.has_major_gridlines:
            gl = chart.value_axis.major_gridlines.format.line
            gl.color.rgb = RGBColor.from_string((per_kind.get("gridline_color_hex") or guide.colors.get("color.rule", {"hex": "BFBFBF"})["hex"]).upper())
            gl.width = Pt(per_kind.get("gridline_width_pt") or 0.75)
        chart.value_axis.has_minor_gridlines = False
        if el.get("hide_value_axis"):
            chart.value_axis.visible = False
        if el.get("number_format"):
            chart.value_axis.tick_labels.number_format = el["number_format"]
            chart.value_axis.tick_labels.number_format_is_linked = False
    # chart text inherits the theme's Calibri unless every text part names the face
    tx_pr = chart._chartSpace.find(qn("c:txPr"))
    if tx_pr is None:
        tx_pr = etree.SubElement(chart._chartSpace, qn("c:txPr"))
        etree.SubElement(tx_pr, qn("a:bodyPr"))
        lst = etree.SubElement(tx_pr, qn("a:lstStyle"))
        p = etree.SubElement(tx_pr, qn("a:p"))
        ppr = etree.SubElement(p, qn("a:pPr"))
        d = etree.SubElement(ppr, qn("a:defRPr"))
        etree.SubElement(d, qn("a:latin")).set("typeface", face)
        etree.SubElement(p, qn("a:endParaRPr"))


# --- slides ------------------------------------------------------------------------------------------


def _layout_named(prs, name: str | None):
    layouts = [lay for m in prs.slide_masters for lay in m.slide_layouts]
    if name:
        for lay in layouts:
            if lay.name.casefold() == name.casefold():
                return lay
        raise SpecError(f"layout {name!r} not in template; available: {[lay.name for lay in layouts]}")
    for preferred in ("Title and Content", "Title Only", "Blank"):
        for lay in layouts:
            if lay.name.casefold() == preferred.casefold():
                return lay
    return min(layouts, key=lambda lay: len(lay.placeholders))


def _copy_chrome_placeholders(slide, layout, wanted: set[str]) -> None:
    """python-pptx clones only title/body placeholders; date, footer and slide-number
    placeholders must be copied by hand or the page shows no number."""
    for sp in layout.placeholders:
        kind = str(sp.placeholder_format.type).split(".")[-1].split(" ")[0]
        if kind in wanted:
            el = copy.deepcopy(sp._element)
            slide.shapes._spTree.append(el)
            # keep the field text but re-id the shape
            cnv = el.find(".//" + qn("p:cNvPr"))
            if cnv is not None:
                cnv.set("id", str(max(int(c.get("id", "0")) for c in slide.shapes._spTree.iter(qn("p:cNvPr"))) + 1))


def emit(spec: dict, template: str, guide_data: dict, out: str, chrome: str) -> dict:
    guide = Guide(guide_data)
    prs = Presentation(template)
    if len(prs.slides):
        raise SpecError("template still has slides; make it with pptx_tools.py template")
    wanted_chrome: set[str] = set()
    if chrome == "auto":
        n = max(1, guide_data.get("reference", {}).get("slides", 1))
        for ch in guide_data.get("chrome", []):
            on_slides = "slide" in (ch.get("layers") or [ch.get("source_layer")])
            if on_slides and ch["kind"] in ("page_number", "footer", "date") and ch.get("slides_present", 0) >= 0.5 * n:
                wanted_chrome.add({"page_number": "SLIDE_NUMBER", "footer": "FOOTER", "date": "DATE"}[ch["kind"]])
    report = {"out": out, "slides": []}
    for si, sd in enumerate(spec["slides"], 1):
        layout = _layout_named(prs, sd.get("layout"))
        slide = prs.slides.add_slide(layout)
        filled: set[int] = set()
        title = sd.get("title")
        if title:
            title_ph = next((ph for ph in slide.placeholders if "TITLE" in str(ph.placeholder_format.type)), None)
            if title_ph is not None and not title.get("box"):
                spec_t = guide.type_spec(title.get("role", "type.title"), where="title")
                title_ph.text_frame.text = ""
                p = title_ph.text_frame.paragraphs[0]
                run = p.add_run()
                run.text = title["text"]
                ink = guide.hex(title.get("ink_role"), where="title") if title.get("ink_role") else (spec_t.get("ink") if HEX_RE.match(spec_t.get("ink") or "") else None)
                _style_run(run, spec_t, guide, emphasis=False, ink_hex=ink)
                if title.get("align"):
                    p.alignment = ALIGN.get(title["align"], PP_ALIGN.LEFT)
                filled.add(title_ph.placeholder_format.idx)
            else:
                box = tuple(int(v) for v in title["box"])
                write_text(slide, {"id": "title", "kind": "text", "paragraphs": [{"role": title.get("role", "type.title"), "runs": [{"text": title["text"]}], "lines": title.get("lines")}]}, guide, box)
        for ph in list(slide.placeholders):
            if ph.placeholder_format.idx not in filled:
                ph._element.getparent().remove(ph._element)  # an unfilled prompt is not content
        for el in sd.get("elements", []):
            box = tuple(int(v) for v in el["box"])
            if any(v < 0 for v in box[2:]):
                raise SpecError(f"{el.get('id')}: negative extent")
            if el.get("foreign"):
                pass
            kind = el["kind"]
            if kind == "text":
                write_text(slide, el, guide, box)
            elif kind == "rule":
                write_rule(slide, el, guide, box)
            elif kind == "rect":
                write_rect(slide, el, guide, box)
            elif kind == "image":
                write_image(slide, el, box)
            elif kind == "table":
                write_table(slide, el, guide, box)
            elif kind == "chart":
                write_chart(slide, el, guide, box)
            else:
                raise SpecError(f"{el.get('id')}: unknown element kind {kind!r}")
        if wanted_chrome:
            _copy_chrome_placeholders(slide, layout, wanted_chrome)
        if sd.get("notes"):
            slide.notes_slide.notes_text_frame.text = sd["notes"]
        report["slides"].append({"slide": si, "layout": layout.name, "elements": len(sd.get("elements", []))})
    prs.save(out)
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--template", required=True)
    ap.add_argument("--guide", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--chrome", default="auto", choices=["auto", "none"])
    args = ap.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text())
    guide = json.loads(Path(args.guide).read_text())
    print(json.dumps(emit(spec, args.template, guide, args.out, args.chrome), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
