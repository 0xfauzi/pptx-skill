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
    {"id": "chart", "kind": "chart", "box": [...], "type": "COLUMN_STACKED", "categories": ["2023", "2024"],
     "series": [{"name": "Revenue", "values": [1.0, 2.0], "fill_role": "color.accent2", "line_role": "none",
                 "labels": {"show": true, "position": "center", "number_format": "0.0", "role": "type.data_label", "ink_role": "color.ink_inverse"},
                 "points": [{"index": 1, "fill_role": "color.accent1", "label": {"ink_role": "color.ink"}}]}],
     "axes": {"category": {"visible": true, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": false,
                           "gridlines": "none", "labels": {"show": true, "role": "type.axis_label", "ink_role": "color.ink_muted"}},
              "value": {"visible": false}},
     "gap_width": 50, "overlap": 100, "legend": "none", "text": {...}, "plot_fill_role": "none", "title": "none"},
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

A chart is the spec the model wrote: `type` is any XL_CHART_TYPE member python-pptx
writes, every colour a role or "none", every label, axis, legend and spacing choice
explicit. A choice the spec omits is written as the neutral value in CHART_DEFAULTS and
named in the slide note's `defaults_taken`. Waterfalls, football fields and mekkos are
recipes over this spec (references/design/chart_recipes.md), not code paths. No ink is
chosen here for any fill: tables and charts write the ink the spec or guide names, and
the build's contrast gate refuses a pair below 3:1.

What the file carries so that PowerPoint and LibreOffice draw the same page (deckgen
E38): both cells of every shared table edge declare the edge identically, every chart
plot group writes c:varyColors val=0 (the one chart value written unasked), no rule
is written below 0.5pt unless the guide's own rule width says so. Every generated slide carries a tags part (p:custDataLst/p:tags,
one p:tag name="pptx-skill" val="generated"), which deckgen 2E-1 measured surviving a
PowerPoint save: `pptx_tools.py text` reads it back as the slide's origin.
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
from pptx.chart.data import BubbleChartData, CategoryChartData, XyChartData
from pptx.chart.datalabel import DataLabels
from pptx.dml.color import RGBColor
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
    XL_TICK_LABEL_POSITION,
    XL_TICK_MARK,
)
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import CONTENT_TYPE as CT
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

EMU_PER_PT = 12700
HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
# The origin tag every generated slide carries (one p:tag in its own tags part). deckgen
# 2E-1 measured the part coming back out of a PowerPoint save with the p:tag intact.
ORIGIN_TAG_NAME = "pptx-skill"
ORIGIN_TAG_VALUE = "generated"
# The thinnest stroke PowerPoint still inks: at 0.25pt it lays 0.48px where LibreOffice
# lays 1.27px (deckgen E38 class 5); at 0.5pt both are above one pixel.
RULE_WEIGHT_FLOOR_EMU = 6350
# Chart plot groups whose schema carries c:varyColors (ECMA-376 21.2.2). The element
# defaults to TRUE and the two renderers read the default oppositely (E38 class 10).
VARY_COLORS_GROUPS = {"barChart", "bar3DChart", "lineChart", "line3DChart", "pieChart", "pie3DChart", "ofPieChart", "doughnutChart",
                      "areaChart", "area3DChart", "scatterChart", "radarChart", "bubbleChart"}
# Children that precede c:varyColors in those groups' sequences.
_VARY_COLORS_PREDECESSORS = {"barDir", "grouping", "scatterStyle", "radarStyle", "ofPieType"}


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
        self.text_container = (data.get("register_stats") or {}).get("text_container", "text_shape")

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


def _without_theme_style(shape):
    """python-pptx gives a new autoshape or connector a p:style whose lnRef and fillRef
    paint accent1 and whose effectRef paints a theme effect style (the blank template's
    is a drop shadow, which LibreOffice renders under every rule). The emitter writes
    each fill and line itself, so no theme reference stays on the shape."""
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)
    return shape


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
    # the schema minimum is 0: a negative value blanks the paragraph in LibreOffice
    etree.SubElement(bef, qn("a:spcPts")).set("val", str(max(0, int(round((para.get("space_before_pt", spec.get("space_before_pt")) or 0.0) * 100)))))
    aft = etree.SubElement(p_pr, qn("a:spcAft"))
    etree.SubElement(aft, qn("a:spcPts")).set("val", str(max(0, int(round((para.get("space_after_pt", spec.get("space_after_pt")) or 0.0) * 100)))))
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
        # the solver measured every line at width - indent_emu (the reference's own marL for
        # the level); the file carries that marL, so the literal breaks were computed for the
        # column that is written. The hanging indent is the level's own step from the guide.
        indent = para.get("indent_emu") or guide.space(para.get("indent_role") or ("space.sm" if "space.sm" in guide.spacing else None), 228600)
        hanging_role = entry.get("hanging_indent_role") or entry.get("indent_role")
        hanging = guide.space(hanging_role, indent) if hanging_role else indent
        # the glyph needs its own width plus a word space: a 5pt step on a 12pt body would
        # leave 0.8pt between the square and the text (reviewed on a dark PDF reference)
        hanging = max(hanging, int(float(spec["size_pt"]) * 12700 * 0.9))
        p_pr.set("lvl", str(int(level)))
        p_pr.set("marL", str(int(indent)))
        p_pr.set("indent", str(-int(min(indent, hanging))))
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


def write_text(slide, el: dict, guide: Guide, box: tuple[int, int, int, int], shape=None) -> None:
    x, y, w, h = box
    if shape is None:
        shape = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    else:
        # the layout's own title placeholder, moved to the solved box: the file keeps the
        # placeholder semantics (outline view, the judge's title size) and the house's type
        shape.left, shape.top, shape.width, shape.height = Emu(x), Emu(y), Emu(w), Emu(h)
        shape.text_frame.text = ""
    shape.name = el.get("id", "text")
    if guide.text_container != "text_box" and shape.is_placeholder is False:
        # the house draws text in plain shapes (keybank: 16 of 16 on its label page); a text box
        # is what python-pptx writes by default and what the judge counts as a different kind
        cnv = shape._element.find(f"{qn('p:nvSpPr')}/{qn('p:cNvSpPr')}")
        if cnv is not None and cnv.get("txBox") is not None:
            del cnv.attrib["txBox"]
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
        if spec.get("case") == "upper":
            runs = [{**r, "text": r["text"].upper()} for r in runs]  # the solver measured the cased text
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
    line = _without_theme_style(slide.shapes.add_connector(1, Emu(x), Emu(y + (h // 2 if horizontal else 0)), Emu(x + w if horizontal else x), Emu(y + (h // 2) if horizontal else y + h)))
    line.name = el.get("id", "rule")
    hex_color = guide.hex(el.get("line_role") or "color.rule", where=el.get("id", "rule"))
    width = el.get("line_width_emu") or (guide.g.get("motifs") or [{}])[0].get("line_width_pt")
    width_emu = int(round(float(width) * EMU_PER_PT)) if isinstance(width, (int, float)) and width and not el.get("line_width_emu") else (el.get("line_width_emu") or 9525)
    _set_line(line._element.spPr, hex_color, width_emu, el.get("dash"))


def write_rect(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    prst = {"rect": MSO_SHAPE.RECTANGLE, "roundRect": MSO_SHAPE.ROUNDED_RECTANGLE, "ellipse": MSO_SHAPE.OVAL, "chevron": MSO_SHAPE.CHEVRON,
            "rightArrow": MSO_SHAPE.RIGHT_ARROW, "diamond": MSO_SHAPE.DIAMOND, "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE}.get(el.get("prst", "rect"), MSO_SHAPE.RECTANGLE)
    shape = _without_theme_style(slide.shapes.add_shape(prst, Emu(x), Emu(y), Emu(w), Emu(h)))
    shape.name = el.get("id", "rect")
    sp_pr = shape._element.spPr
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
    rules = guide.tables.get("edge_rules") or {}
    rule = rules.get(klass)
    if rule is None and klass == "totals_top":
        # a guide without its own totals class: the totals rule is the header rule when the
        # guide asks for one (tables.totals_rule), else the row interior like any other edge
        rule = rules.get("header_bottom") if guide.tables.get("totals_rule") else rules.get("row_interior")
    if not rule or rule.get("none"):
        return None, 0
    hex_color = rule.get("color_hex") or (guide.hex(rule.get("color_role"), where=f"table edge {klass}") if rule.get("color_role") else None)
    width = rule.get("width_emu") or (int(round(float(rule["width_pt"]) * EMU_PER_PT)) if rule.get("width_pt") else 12700)
    return hex_color, int(width)


def _horizontal_edge_class(index: int, header_rows: int, n_rows: int, totals_index: int | None) -> str:
    if index == 0:
        return "table_top"
    if index == n_rows:
        return "table_bottom"
    if header_rows and index == header_rows:
        return "header_bottom"
    if totals_index is not None and index == totals_index:
        return "totals_top"
    return "row_interior"


def _write_table_edges(table, guide: Guide, n_rows: int, n_cols: int, header_rows: int, totals_index: int | None) -> None:
    """Every shared edge written to BOTH of its declaring cells from one rule, so the two
    sides agree byte for byte (upper lnB == lower lnT, left lnR == right lnL). Measured
    (deckgen E38 class 4, 8 of 8 cases in both axes): where the sides differ, PowerPoint
    draws the first-declared side and writes it back on save while LibreOffice draws the
    heavier one, so a totals rule declared on the totals row's lnT alone shows in the
    render and vanishes in PowerPoint. Identical sides leave no conflict to resolve."""
    def tc_pr(ri: int, ci: int) -> etree._Element:
        return table.cell(ri, ci)._tc.get_or_add_tcPr()

    for index in range(n_rows + 1):
        hex_color, width = _table_edge(guide, _horizontal_edge_class(index, header_rows, n_rows, totals_index))
        for ci in range(n_cols):
            if index > 0:
                _cell_border(tc_pr(index - 1, ci), "a:lnB", hex_color, width)
            if index < n_rows:
                _cell_border(tc_pr(index, ci), "a:lnT", hex_color, width)
    for index in range(n_cols + 1):
        klass = "table_left" if index == 0 else ("table_right" if index == n_cols else "column_interior")
        hex_color, width = _table_edge(guide, klass)
        for ri in range(n_rows):
            if index > 0:
                _cell_border(tc_pr(ri, index - 1), "a:lnR", hex_color, width)
            if index < n_cols:
                _cell_border(tc_pr(ri, index), "a:lnL", hex_color, width)


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


def table_row_styles(el: dict, guide: Guide) -> list[dict]:
    """The fill, ink and weight of every row of a table, from the guide's table section
    and the spec: the header fill and ink, banding parity, the guide's data fill, and the
    emphasis rows' fill and ink, which the spec names (`emphasis_fill_role`, a colour role
    or "none"; `emphasis_ink_role`, else the cell ink). Nothing here picks an ink for a
    fill: a pair that reads below 3:1 is the build's contrast gate's to refuse. The
    emitter and that gate both read rows through this one function."""
    where = el.get("id", "table")
    t = guide.tables
    header_rows = int(el.get("header_rows", 1))
    n_rows = header_rows + len(el["rows"])
    emphasis_rows = {int(i) for i in (el.get("emphasis_rows") or [])}
    if emphasis_rows and "emphasis_fill_role" not in el:
        raise SpecError(f"{where}: emphasis_rows {sorted(emphasis_rows)} need emphasis_fill_role, a colour role from the guide or \"none\" (bold on the row's own ground)")

    def role_hex(role: str | None, literal: str | None, label: str) -> tuple[str | None, str | None]:
        if literal:
            return literal, label
        if role and role != "none":
            return guide.hex(role, where=f"{where} {label}"), role
        return None, None

    header_fill = role_hex(t.get("header_fill_role"), t.get("header_fill_hex"), "header fill")
    header_ink = role_hex(t.get("header_ink_role"), None, "header ink")
    band = role_hex(t.get("banding_role"), t.get("banding_hex"), "banding")
    data = role_hex(None, t.get("data_fill_hex"), "data fill")
    emphasis_fill = role_hex(el.get("emphasis_fill_role"), None, "emphasis fill")
    cell_spec = guide.type_spec("type.table_cell" if "type.table_cell" in guide.roles else "type.body", where=where)
    cell_ink_role = cell_spec.get("ink_role")
    cell_ink = (guide.hex(cell_ink_role, where=f"{where} cell ink"), cell_ink_role) if cell_ink_role else \
        ((cell_spec["ink"], "type.table_cell observed ink") if HEX_RE.match(cell_spec.get("ink") or "") else (None, None))
    emphasis_ink = role_hex(el.get("emphasis_ink_role"), None, "emphasis ink") if el.get("emphasis_ink_role") else cell_ink
    totals = bool(el.get("totals_last_row"))
    rows = []
    for ri in range(n_rows):
        is_header = ri < header_rows
        data_index = ri - header_rows
        is_totals = totals and ri == n_rows - 1
        is_emphasis = not is_header and data_index in emphasis_rows
        if is_header:
            fill, ink, klass, bold = header_fill, header_ink, "header", bool(t.get("header_bold"))
        elif is_emphasis:
            fill, ink, klass, bold = emphasis_fill, emphasis_ink, "emphasis", True
        else:
            fill = band if (band[0] and data_index % 2 == 0) else data
            ink, bold = cell_ink, is_totals or cell_spec.get("weight", 400) >= 700
            klass = "totals" if is_totals else ("body even" if data_index % 2 == 0 else "body odd")
        rows.append({"row": ri, "class": klass, "header": is_header, "fill_hex": fill[0], "fill_name": fill[1], "ink_hex": ink[0], "ink_name": ink[1], "bold": bold})
    return rows


def write_table(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    cols = el["columns"]
    rows = el["rows"]
    header_rows = int(el.get("header_rows", 1))
    n_rows = header_rows + len(rows)
    styles = table_row_styles(el, guide)
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
    header_spec = guide.type_spec("type.table_header" if "type.table_header" in guide.roles else "type.body", where="table")
    cell_spec = guide.type_spec("type.table_cell" if "type.table_cell" in guide.roles else "type.body", where="table")
    align_by_kind = guide.tables.get("alignment_by_column_type") or {}
    totals = bool(el.get("totals_last_row"))
    for ri in range(n_rows):
        row = table.rows[ri]
        if heights and ri < len(heights):
            row.height = Emu(int(heights[ri]))
        st = styles[ri]
        is_header = st["header"]
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
            fill_hex = st["fill_hex"]
            # the ink is declared on the run so a dark reference does not inherit black
            _style_run(run, spec, guide, emphasis=st["bold"], ink_hex=st["ink_hex"])
            ln = p._p.get_or_add_pPr()
            for tag in ("a:lnSpc", "a:spcBef", "a:spcAft"):
                for old in ln.findall(qn(tag)):
                    ln.remove(old)
            tc_pr = cell._tc.get_or_add_tcPr()
            for child in list(tc_pr):
                if child.tag in (qn("a:solidFill"), qn("a:noFill")):
                    tc_pr.remove(child)
            if fill_hex:
                sf = etree.SubElement(tc_pr, qn("a:solidFill"))
                etree.SubElement(sf, qn("a:srgbClr")).set("val", fill_hex.upper())
            else:
                etree.SubElement(tc_pr, qn("a:noFill"))
    _write_table_edges(table, guide, n_rows, len(cols), header_rows, n_rows - 1 if totals else None)


# --- charts: the spec the model writes, written as given -------------------------------------------
#
# Every design choice in a chart (type, fills, strokes, labels, axes, legend, gap and
# overlap) comes from the spec. A choice the spec leaves out is written as the neutral
# value named in CHART_DEFAULTS and listed in the note's `defaults_taken`, so the model
# reads back what it did not decide. c:varyColors val=0 is the one value written without
# being asked for: it is file safety, not design (E38 class 10, below).

CHART_KEYS = {"id", "kind", "box", "type", "categories", "series", "number_format", "text", "axes", "gap_width", "overlap", "legend", "plot_fill_role", "title", "foreign",
              "bridge"}  # bridge: a declaration the build's tie-out reads; nothing here draws from it
SERIES_KEYS = {"name", "values", "number_format", "fill_role", "line_role", "line_width_pt", "labels", "points", "marker", "smooth"}
LABEL_KEYS = {"show", "position", "number_format", "role", "ink_role"}
POINT_KEYS = {"index", "fill_role", "line_role", "label"}
POINT_LABEL_KEYS = LABEL_KEYS | {"text"}
AXIS_KEYS = {"visible", "line_role", "line_width_pt", "gridlines", "number_format", "reverse", "min", "max", "major_unit", "tick_marks", "labels"}
AXIS_LABEL_KEYS = {"show", "position", "role", "ink_role"}
TICK_LABEL_POSITIONS = {"next_to": XL_TICK_LABEL_POSITION.NEXT_TO_AXIS, "low": XL_TICK_LABEL_POSITION.LOW, "high": XL_TICK_LABEL_POSITION.HIGH}
GRIDLINE_KEYS = {"line_role", "line_width_pt"}
LEGEND_KEYS = {"position", "hide_entries", "role", "ink_role"}
TEXT_KEYS = {"role", "ink_role"}
MARKER_KEYS = {"style", "size", "fill_role", "line_role"}
TITLE_KEYS = {"text", "role", "ink_role"}
NONE = "none"
LABEL_POSITIONS = {"center": XL_LABEL_POSITION.CENTER, "inside_end": XL_LABEL_POSITION.INSIDE_END, "inside_base": XL_LABEL_POSITION.INSIDE_BASE,
                   "outside_end": XL_LABEL_POSITION.OUTSIDE_END, "above": XL_LABEL_POSITION.ABOVE, "below": XL_LABEL_POSITION.BELOW,
                   "left": XL_LABEL_POSITION.LEFT, "right": XL_LABEL_POSITION.RIGHT, "best_fit": XL_LABEL_POSITION.BEST_FIT}
LEGEND_POSITIONS = {"b": XL_LEGEND_POSITION.BOTTOM, "t": XL_LEGEND_POSITION.TOP, "r": XL_LEGEND_POSITION.RIGHT, "l": XL_LEGEND_POSITION.LEFT, "tr": XL_LEGEND_POSITION.CORNER}
TICK_MARKS = {"none": XL_TICK_MARK.NONE, "out": XL_TICK_MARK.OUTSIDE, "in": XL_TICK_MARK.INSIDE, "cross": XL_TICK_MARK.CROSS}
MARKER_STYLES = {m.name.lower(): m for m in XL_MARKER_STYLE if m.name not in ("PICTURE", "AUTOMATIC")}
# Label positions PowerPoint's label menu offers per family. A dLblPos outside the menu
# is a schema-valid file PowerPoint does not draw as written, so it is refused here
# rather than emitted; area, doughnut and radar labels take no position at all.
FAMILY_POSITIONS = {
    "bar": ("center", "inside_end", "inside_base", "outside_end"),
    "bar_stacked": ("center", "inside_end", "inside_base"),
    "line": ("center", "left", "right", "above", "below"),
    "xy": ("center", "left", "right", "above", "below"),
    "bubble": ("center", "left", "right", "above", "below"),
    "pie": ("center", "inside_end", "outside_end", "best_fit"),
    "doughnut": (), "area": (), "radar": (),
}
# Where a label at each position sits: on the mark's own fill, or on the plot behind it.
ON_FILL = {"bar": {"center", "inside_end", "inside_base"}, "bar_stacked": {"center", "inside_end", "inside_base"},
           "pie": {"center", "inside_end"}, "bubble": {"center"}, "area": set(), "doughnut": set()}
# The value each omitted choice is written as. "python-pptx" entries are read back from
# the chart part after it is written and reported with the value found.
CHART_DEFAULTS = {
    "series.fill_role": "no fill written: the renderer's automatic colour by series index",
    "series.line_role": "no stroke written: the renderer's automatic stroke",
    "series.line_width_pt": "no width written: the renderer's default stroke width",
    "series.labels": "no data labels",
    "labels.position": "no dLblPos: each renderer's own default position for the type",
    "labels.number_format": "linked to the source data",
    "labels.role": "the chart text (text.role, else the theme)",
    "labels.ink_role": "the chart text ink (text.ink_role, else the theme)",
    "series.marker": "the renderer's automatic marker",
    "series.smooth": "python-pptx's chart part",
    "axis.visible": "shown",
    "axis.line_role": "no stroke written: each renderer reads the theme's line style, and they differ (E38 class 5)",
    "axis.gridlines": "none (OOXML absence)",
    "axis.number_format": "linked to the source data",
    "axis.reverse": "minMax: from the origin outward (a horizontal bar lists its categories bottom-up)",
    "axis.scale": "automatic minimum, maximum and major unit",
    "axis.tick_marks": "python-pptx's chart part",
    "axis.labels": "tick labels next to the axis in the chart text",
    "gap_width": "python-pptx's chart part",
    "overlap": "python-pptx's chart part",
    "legend": "none (OOXML absence)",
    "text": "chart text inherits the theme's face, size and colour",
    "plot_fill_role": "no plot fill: the slide shows through",
    "title": "none",
}


def chart_family(type_name: str) -> str:
    n = type_name
    if n.startswith(("COLUMN_", "BAR_")) and n != "BAR_OF_PIE":
        return "bar_stacked" if "STACKED" in n else "bar"
    if n.startswith("PIE"):
        return "pie"
    if n.startswith("DOUGHNUT"):
        return "doughnut"
    if n.startswith("LINE"):
        return "line"
    if n.startswith("AREA"):
        return "area"
    if n.startswith("XY_SCATTER"):
        return "xy"
    if n.startswith("BUBBLE"):
        return "bubble"
    if n.startswith("RADAR"):
        return "radar"
    return "other"


def _keys(where: str, obj, allowed: set[str]) -> dict:
    if not isinstance(obj, dict):
        raise SpecError(f"{where}: expected an object, got {obj!r}")
    extra = sorted(set(obj) - allowed)
    if extra:
        hint = " (the chart spec changed: see references/design/chart_recipes.md)" if {"chart_kind", "deltas", "totals", "data_labels", "hide_value_axis"} & set(extra) else ""
        raise SpecError(f"{where}: unknown keys {extra}; allowed {sorted(allowed)}{hint}")
    return obj


def _colour(guide: Guide, role, where: str):
    """A colour role, or NONE for an explicit no-fill / no-stroke. A literal is refused."""
    if role == NONE:
        return NONE
    if not isinstance(role, str):
        raise SpecError(f"{where}: colour must be a role name or \"none\", got {role!r}")
    if HEX_RE.match(role.lstrip("#")):
        raise SpecError(f"{where}: literal colour {role!r}; a chart takes colour roles from the guide only")
    return guide.hex(role, where=where)


def _text_style(guide: Guide, style: dict | None, where: str) -> tuple[dict | None, str | None]:
    """A text part's (type spec, ink hex) from its role and ink_role; None where omitted."""
    style = style or {}
    spec = guide.type_spec(style["role"], where=where) if style.get("role") else None
    ink = _colour(guide, style["ink_role"], where) if style.get("ink_role") else None
    if ink == NONE:
        raise SpecError(f"{where}: ink_role cannot be \"none\"")
    return spec, ink


def _font(font, guide: Guide, spec: dict | None, ink: str | None) -> None:
    if spec is not None:
        font.name = guide.face(spec)
        font.size = Pt(float(spec["size_pt"]))
        font.bold = bool(spec.get("weight", 400) >= 700)
        font.italic = bool(spec.get("italic", False))
    if ink:
        font.color.rgb = RGBColor.from_string(ink.upper())


def _fill(fmt, hex_or_none) -> None:
    if hex_or_none == NONE:
        fmt.fill.background()
    else:
        fmt.fill.solid()
        fmt.fill.fore_color.rgb = RGBColor.from_string(hex_or_none.upper())


def _stroke(fmt, hex_or_none, width_pt) -> None:
    if hex_or_none == NONE:
        fmt.line.fill.background()
        return
    fmt.line.color.rgb = RGBColor.from_string(hex_or_none.upper())
    if width_pt is not None:
        fmt.line.width = Pt(float(width_pt))


def _check_position(family: str, position, where: str) -> None:
    if position is None:
        return
    allowed = FAMILY_POSITIONS.get(family, ())
    if position not in LABEL_POSITIONS or position not in allowed:
        raise SpecError(f"{where}: label position {position!r} is not offered for this chart type; offered: {list(allowed) or 'none (omit position)'}")


def chart_parse(el: dict, guide: Guide) -> dict:
    """Validate a chart spec against the guide and list every omitted choice. Returns
    {"type": XL_CHART_TYPE member, "family", "defaults": [(path, written)]}. Both the
    emitter and the build's contrast gate read the spec through this one parse."""
    where = el.get("id", "chart")
    _keys(where, el, CHART_KEYS)
    type_name = el.get("type")
    if not isinstance(type_name, str) or type_name not in XL_CHART_TYPE.__members__:
        raise SpecError(f"{where}: type {type_name!r} is not an XL_CHART_TYPE member name (e.g. COLUMN_CLUSTERED, BAR_STACKED, LINE_MARKERS, PIE, XY_SCATTER)")
    family = chart_family(type_name)
    defaults: list[tuple[str, str]] = []

    def took(path: str, key: str) -> None:
        defaults.append((path, CHART_DEFAULTS[key]))

    series = el.get("series")
    if not isinstance(series, list) or not series:
        raise SpecError(f"{where}: series must be a non-empty list")
    cats = el.get("categories")
    if family in ("xy", "bubble"):
        if cats is not None:
            raise SpecError(f"{where}: {type_name} plots [x, y{', size' if family == 'bubble' else ''}] values; categories do not apply")
    elif not isinstance(cats, list) or not cats:
        raise SpecError(f"{where}: categories must be a non-empty list")
    width = 3 if family == "bubble" else 2
    stroked = family in ("line", "xy", "radar")
    for si, s in enumerate(series):
        sw = f"{where} series[{si}]"
        _keys(sw, s, SERIES_KEYS)
        values = s.get("values")
        if family in ("xy", "bubble"):
            if not isinstance(values, list) or any(not isinstance(v, list) or len(v) != width for v in values):
                raise SpecError(f"{sw}: values must be [[x, y{', size' if width == 3 else ''}], ...]")
        elif not isinstance(values, list) or len(values) != len(cats):
            raise SpecError(f"{sw}: {len(values) if isinstance(values, list) else 'no'} values for {len(cats)} categories")
        if "fill_role" in s:
            if stroked:
                raise SpecError(f"{sw}: a {type_name} series draws its line_role; fill_role does not apply (marker.fill_role colours markers)")
            _colour(guide, s["fill_role"], sw)
        elif not stroked and not (family in ("pie", "doughnut") and len(s.get("points") or []) == len(values) and all("fill_role" in p for p in s.get("points") or [])):
            took(f"series[{si}].fill_role", "series.fill_role")
        if "line_role" in s:
            if _colour(guide, s["line_role"], sw) != NONE and "line_width_pt" not in s:
                took(f"series[{si}].line_width_pt", "series.line_width_pt")
        else:
            took(f"series[{si}].line_role", "series.line_role")
        if stroked and "smooth" not in s and family != "radar":
            took(f"series[{si}].smooth", "series.smooth")
        if "marker" in s:
            m = _keys(f"{sw} marker", s["marker"], MARKER_KEYS)
            if m.get("style") is not None and m["style"] not in MARKER_STYLES:
                raise SpecError(f"{sw}: marker style {m['style']!r} not in {sorted(MARKER_STYLES)}")
            for k in ("fill_role", "line_role"):
                if k in m:
                    _colour(guide, m[k], f"{sw} marker")
        elif stroked and ("MARKERS" in type_name or type_name in ("XY_SCATTER", "XY_SCATTER_LINES", "XY_SCATTER_SMOOTH")):
            took(f"series[{si}].marker", "series.marker")
        labels = s.get("labels")
        if labels is None:
            took(f"series[{si}].labels", "series.labels")
        else:
            _keys(f"{sw} labels", labels, LABEL_KEYS)
            _text_style(guide, labels, f"{sw} labels")
            if labels.get("show", True):
                _check_position(family, labels.get("position"), f"{sw} labels")
                for k, d in (("position", "labels.position"), ("number_format", "labels.number_format"), ("role", "labels.role"), ("ink_role", "labels.ink_role")):
                    if k not in labels and not (k == "position" and not FAMILY_POSITIONS.get(family)):
                        took(f"series[{si}].labels.{k}", d)
        for pi, p in enumerate(s.get("points") or []):
            pw = f"{sw} points[{pi}]"
            _keys(pw, p, POINT_KEYS)
            idx = p.get("index")
            if not isinstance(idx, int) or not 0 <= idx < len(values):
                raise SpecError(f"{pw}: index {idx!r} outside 0..{len(values) - 1}")
            for k in ("fill_role", "line_role"):
                if k in p:
                    _colour(guide, p[k], pw)
            if "label" in p:
                _keys(f"{pw} label", p["label"], POINT_LABEL_KEYS)
                _text_style(guide, p["label"], f"{pw} label")
                _check_position(family, p["label"].get("position"), f"{pw} label")
    if family not in ("pie", "doughnut"):
        axes = _keys(f"{where} axes", el.get("axes") or {}, {"category", "value"})
        for name in ("category", "value"):
            ax = axes.get(name)
            aw = f"{where} axes.{name}"
            if ax is None:
                took(f"axes.{name}", "axis.visible")
                ax = {}
            _keys(aw, ax, AXIS_KEYS)
            if ax.get("visible") is False:
                continue
            if "visible" not in ax and name in axes:
                took(f"axes.{name}.visible", "axis.visible")
            if "line_role" in ax:
                _colour(guide, ax["line_role"], aw)
            else:
                took(f"axes.{name}.line_role", "axis.line_role")
            if "gridlines" in ax:
                if ax["gridlines"] != NONE:
                    g = _keys(f"{aw} gridlines", ax["gridlines"], GRIDLINE_KEYS)
                    _colour(guide, g.get("line_role"), f"{aw} gridlines")
            else:
                took(f"axes.{name}.gridlines", "axis.gridlines")
            if "labels" in ax:
                _keys(f"{aw} labels", ax["labels"], AXIS_LABEL_KEYS)
                _text_style(guide, ax["labels"], f"{aw} labels")
                if ax["labels"].get("position") is not None and ax["labels"]["position"] not in TICK_LABEL_POSITIONS:
                    raise SpecError(f"{aw} labels: position {ax['labels']['position']!r} not in {sorted(TICK_LABEL_POSITIONS)}")
            else:
                took(f"axes.{name}.labels", "axis.labels")
            if ax.get("tick_marks") is not None and ax["tick_marks"] not in TICK_MARKS:
                raise SpecError(f"{aw}: tick_marks {ax['tick_marks']!r} not in {sorted(TICK_MARKS)}")
            for k, d in (("tick_marks", "axis.tick_marks"), ("reverse", "axis.reverse")):
                if k not in ax:
                    took(f"axes.{name}.{k}", d)
            numeric = name == "value" or family in ("xy", "bubble")
            if numeric:
                if "number_format" not in ax:
                    took(f"axes.{name}.number_format", "axis.number_format")
                if not {"min", "max"} & set(ax):
                    took(f"axes.{name}.min/max", "axis.scale")
            elif {"min", "max", "major_unit", "number_format"} & set(ax):
                raise SpecError(f"{aw}: a category axis has no scale or number format")
    elif el.get("axes"):
        raise SpecError(f"{where}: a {type_name} has no axes")
    if family in ("bar", "bar_stacked"):
        for k in ("gap_width", "overlap"):
            if k not in el:
                took(k, k)
    elif "gap_width" in el or "overlap" in el:
        raise SpecError(f"{where}: gap_width and overlap apply to bar and column types only")
    legend = el.get("legend")
    if legend is None:
        took("legend", "legend")
    elif legend != NONE:
        _keys(f"{where} legend", legend, LEGEND_KEYS)
        if legend.get("position") not in LEGEND_POSITIONS:
            raise SpecError(f"{where} legend: position {legend.get('position')!r} not in {sorted(LEGEND_POSITIONS)}")
        _text_style(guide, legend, f"{where} legend")
    if "text" in el:
        _keys(f"{where} text", el["text"], TEXT_KEYS)
        _text_style(guide, el["text"], f"{where} text")
    else:
        took("text", "text")
    if "plot_fill_role" in el:
        _colour(guide, el["plot_fill_role"], f"{where} plot_fill_role")
    else:
        took("plot_fill_role", "plot_fill_role")
    title = el.get("title")
    if title is None:
        took("title", "title")
    elif title != NONE:
        _keys(f"{where} title", title, TITLE_KEYS)
        _text_style(guide, title, f"{where} title")
    return {"type": XL_CHART_TYPE[type_name], "type_name": type_name, "family": family, "defaults": defaults}


def _write_vary_colors(chart_space: etree._Element) -> None:
    """c:varyColors val=0 on every plot group that can carry it. python-pptx 1.0.2 writes
    none for a bar chart; absent, PowerPoint paints one series in five theme colours and
    LibreOffice in one (E38 class 10). With 0 both renderers draw the fills the spec
    wrote: a pie whose slices should differ names a fill per point."""
    area = chart_space.find(".//" + qn("c:plotArea"))
    if area is None:
        return
    for group in area:
        if etree.QName(group).localname not in VARY_COLORS_GROUPS:
            continue
        vc = group.find(qn("c:varyColors"))
        if vc is None:
            vc = etree.Element(qn("c:varyColors"))
            at = 0
            for i, child in enumerate(group):
                if etree.QName(child).localname in _VARY_COLORS_PREDECESSORS:
                    at = i + 1
            group.insert(at, vc)
        vc.set("val", "0")


def _write_labels(dl, guide: Guide, spec: dict, family: str, where: str) -> None:
    """One series' dLbls (python-pptx DataLabels) from a labels spec."""
    tspec, ink = _text_style(guide, spec, where)
    _font(dl.font, guide, tspec, ink)
    dl.show_value = True
    if spec.get("position") is not None:
        dl.position = LABEL_POSITIONS[spec["position"]]
    if spec.get("number_format"):
        dl.number_format = spec["number_format"]
        dl.number_format_is_linked = False


def _write_point_label(series, idx: int, guide: Guide, merged: dict, where: str) -> None:
    """A c:dLbl replaces the series' dLbls for its point, so it carries the merged
    series and point label spec in full: format, position, font, ink, text."""
    if merged.get("show") is False:
        dlbls = series._element.get_or_add_dLbls()
        d_lbl = etree.Element(qn("c:dLbl"))
        etree.SubElement(d_lbl, qn("c:idx")).set("val", str(idx))
        etree.SubElement(d_lbl, qn("c:delete")).set("val", "1")
        dlbls.insert(0, d_lbl)
        return
    dl = series.points[idx].data_label
    tspec, ink = _text_style(guide, merged, where)
    if merged.get("text") is not None:
        dl.text_frame.text = str(merged["text"])
        for run in dl.text_frame.paragraphs[0].runs:
            _font(run.font, guide, tspec, ink)
    _font(dl.font, guide, tspec, ink)
    if merged.get("position") is not None:
        dl.position = LABEL_POSITIONS[merged["position"]]
    d_lbl = dl._dLbl
    if merged.get("number_format") and d_lbl is not None and merged.get("text") is None:
        fmt = etree.Element(qn("c:numFmt"))
        fmt.set("formatCode", merged["number_format"])
        fmt.set("sourceLinked", "0")
        d_lbl.find(qn("c:idx")).addnext(fmt)


def write_chart(slide, el: dict, guide: Guide, box: tuple[int, int, int, int]) -> dict:
    x, y, w, h = box
    parsed = chart_parse(el, guide)
    family = parsed["family"]
    where = el.get("id", "chart")
    if family in ("xy", "bubble"):
        data = XyChartData(number_format=el.get("number_format")) if family == "xy" else BubbleChartData(number_format=el.get("number_format"))
        for s in el["series"]:
            ser = data.add_series(s["name"], number_format=s.get("number_format"))
            for v in s["values"]:
                ser.add_data_point(*v)
    else:
        data = CategoryChartData(number_format=el.get("number_format") or "General")
        data.categories = el["categories"]
        for s in el["series"]:
            data.add_series(s["name"], s["values"], number_format=s.get("number_format"))
    try:
        gf = slide.shapes.add_chart(parsed["type"], Emu(x), Emu(y), Emu(w), Emu(h), data)
    except NotImplementedError as error:
        raise SpecError(f"{where}: python-pptx cannot write {parsed['type_name']} ({error}); choose a type it writes") from None
    gf.name = where
    chart = gf.chart
    if el.get("text"):
        tspec, ink = _text_style(guide, el["text"], f"{where} text")
        _font(chart.font, guide, tspec, ink)
    title = el.get("title")
    chart.has_title = bool(title and title != NONE)
    if chart.has_title:
        chart.chart_title.text_frame.text = title.get("text", "")
        tspec, ink = _text_style(guide, title, f"{where} title")
        for run in chart.chart_title.text_frame.paragraphs[0].runs:
            _font(run.font, guide, tspec, ink)
    legend = el.get("legend")
    chart.has_legend = bool(legend and legend != NONE)
    if chart.has_legend:
        chart.legend.position = LEGEND_POSITIONS[legend["position"]]
        chart.legend.include_in_layout = False
        tspec, ink = _text_style(guide, legend, f"{where} legend")
        _font(chart.legend.font, guide, tspec, ink)
        legend_el = chart._chartSpace.find(".//" + qn("c:legend"))
        pos = legend_el.find(qn("c:legendPos"))
        for idx in sorted((int(i) for i in legend.get("hide_entries") or []), reverse=True):
            entry = etree.Element(qn("c:legendEntry"))
            etree.SubElement(entry, qn("c:idx")).set("val", str(idx))
            etree.SubElement(entry, qn("c:delete")).set("val", "1")
            pos.addnext(entry)
    if el.get("plot_fill_role") is not None:
        plot_fmt = chart.plots[0]._element.getparent()  # c:plotArea
        sp_pr = plot_fmt.find(qn("c:spPr"))
        if sp_pr is None:
            sp_pr = etree.SubElement(plot_fmt, qn("c:spPr"))
        fill = _colour(guide, el["plot_fill_role"], f"{where} plot_fill_role")
        if fill == NONE:
            etree.SubElement(sp_pr, qn("a:noFill"))
        else:
            _solid_fill(sp_pr, fill)
    plot = chart.plots[0]
    for si, (series, s) in enumerate(zip(plot.series, el["series"])):
        sw = f"{where} series[{si}]"
        if "fill_role" in s:
            _fill(series.format, _colour(guide, s["fill_role"], sw))
        if "line_role" in s:
            _stroke(series.format, _colour(guide, s["line_role"], sw), s.get("line_width_pt"))
        if "smooth" in s:
            series.smooth = bool(s["smooth"])
        if "marker" in s:
            m = s["marker"]
            if m.get("style") is not None:
                series.marker.style = MARKER_STYLES[m["style"]]
            if m.get("size") is not None:
                series.marker.size = int(m["size"])
            if "fill_role" in m:
                _fill(series.marker.format, _colour(guide, m["fill_role"], f"{sw} marker"))
            if "line_role" in m:
                _stroke(series.marker.format, _colour(guide, m["line_role"], f"{sw} marker"), None)
        labels = s.get("labels")
        if labels and labels.get("show", True):
            _write_labels(DataLabels(series._element.get_or_add_dLbls()), guide, labels, family, f"{sw} labels")
        for p in s.get("points") or []:
            pw = f"{sw} point {p['index']}"
            if "fill_role" in p:
                _fill(series.points[p["index"]].format, _colour(guide, p["fill_role"], pw))
            if "line_role" in p:
                _stroke(series.points[p["index"]].format, _colour(guide, p["line_role"], pw), s.get("line_width_pt"))
            if "label" in p:
                merged = {**(labels or {}), **p["label"]}
                if not (labels and labels.get("show", True)) and "show" not in p["label"]:
                    merged["show"] = True
                _write_point_label(series, p["index"], guide, merged, f"{pw} label")
    taken = dict(parsed["defaults"])
    for si, (series, s) in enumerate(zip(plot.series, el["series"])):
        if f"series[{si}].smooth" in taken:
            taken[f"series[{si}].smooth"] = f"{bool(series.smooth)} ({CHART_DEFAULTS['series.smooth']})"
    if family in ("bar", "bar_stacked"):
        if "gap_width" in el:
            plot.gap_width = int(el["gap_width"])
        else:
            taken["gap_width"] = f"{plot.gap_width} ({CHART_DEFAULTS['gap_width']})"
        if "overlap" in el:
            plot.overlap = int(el["overlap"])
        else:
            taken["overlap"] = f"{plot.overlap} ({CHART_DEFAULTS['overlap']})"
    if family not in ("pie", "doughnut"):
        axes = el.get("axes") or {}
        for name, axis in (("category", chart.category_axis), ("value", chart.value_axis)):
            ax = axes.get(name) or {}
            aw = f"{where} axes.{name}"
            if ax.get("visible") is False:
                axis.visible = False
                axis.has_major_gridlines = False
                continue
            # python-pptx's chart part writes value-axis gridlines; an omitted choice is none
            axis.has_major_gridlines = False
            axis.has_minor_gridlines = False
            if "line_role" in ax:
                _stroke(axis.format, _colour(guide, ax["line_role"], aw), ax.get("line_width_pt"))
            g = ax.get("gridlines")
            if g and g != NONE:
                axis.has_major_gridlines = True
                _stroke(axis.major_gridlines.format, _colour(guide, g["line_role"], f"{aw} gridlines"), g.get("line_width_pt"))
            lab = ax.get("labels")
            if lab is not None:
                if lab.get("show", True) is False:
                    axis.tick_label_position = XL_TICK_LABEL_POSITION.NONE
                else:
                    tspec, ink = _text_style(guide, lab, f"{aw} labels")
                    _font(axis.tick_labels.font, guide, tspec, ink)
                    if lab.get("position") is not None:
                        axis.tick_label_position = TICK_LABEL_POSITIONS[lab["position"]]
            if "tick_marks" in ax:
                axis.major_tick_mark = TICK_MARKS[ax["tick_marks"]]
            else:
                taken[f"axes.{name}.tick_marks"] = f"{axis.major_tick_mark.name.lower()} ({CHART_DEFAULTS['axis.tick_marks']})"
            if "reverse" in ax:
                axis.reverse_order = bool(ax["reverse"])
            if ax.get("number_format"):
                axis.tick_labels.number_format = ax["number_format"]
                axis.tick_labels.number_format_is_linked = False
            if ax.get("min") is not None:
                axis.minimum_scale = float(ax["min"])
            if ax.get("max") is not None:
                axis.maximum_scale = float(ax["max"])
            if ax.get("major_unit") is not None:
                axis.major_unit = float(ax["major_unit"])
    _write_vary_colors(chart._chartSpace)
    return {"id": where, "type": parsed["type_name"], "defaults_taken": [f"{k}: {v}" for k, v in taken.items()]}


def chart_label_inks(el: dict, guide: Guide) -> list[dict]:
    """Every chart text the spec inks, with what it sits on, for the build's contrast
    gate: data labels per series and per overriding point, axis tick labels, legend.
    `on` is a list of ("fill", hex, name) and ("plot",); "plot" is the plot fill when
    the spec names one, else whatever the page draws under the chart. A label whose
    fill the spec left to the renderer is ("unknown", why). A position the spec left
    open is scored against every backing the label can land on."""
    parsed = chart_parse(el, guide)
    family = parsed["family"]
    where = el.get("id", "chart")
    text_spec, text_ink = _text_style(guide, el.get("text"), f"{where} text")
    on_fill = ON_FILL.get(family, set())
    out: list[dict] = []

    def ink_of(spec: dict) -> tuple[str | None, str | None, dict | None]:
        tspec, ink = _text_style(guide, spec, where)
        name = spec.get("ink_role") or ((el.get("text") or {}).get("ink_role"))
        return ink or text_ink, name, tspec or text_spec

    def backing(fill_role, position) -> list[tuple]:
        if family in ("line", "xy", "radar"):
            return [("plot",)]
        if fill_role is None:
            fill = ("unknown", "the series fill is left to the renderer; name a fill_role to score it")
        elif fill_role == NONE:
            fill = ("plot",)
        else:
            fill = ("fill", guide.hex(fill_role, where=where), fill_role)
        if family in ("area", "doughnut"):
            return [fill]
        if position is None:
            return [fill, ("plot",)]  # the renderer picks the position
        return [fill] if position in on_fill else [("plot",)]

    for si, s in enumerate(el["series"]):
        labels = s.get("labels")
        series_on = labels is not None and labels.get("show", True)
        overridden = {}
        for p in s.get("points") or []:
            if "label" in p or "fill_role" in p:
                overridden[p["index"]] = p
        n = len(s["values"])
        plain = [i for i in range(n) if i not in overridden]
        if series_on and plain:
            ink, name, tspec = ink_of(labels)
            out.append({"element": where, "part": f"series[{si}] {s['name']!r} labels", "points": plain, "ink": ink, "ink_name": name,
                        "spec": tspec, "on": backing(s.get("fill_role"), labels.get("position"))})
        for idx, p in sorted(overridden.items()):
            merged = {**(labels or {}), **p.get("label", {})}
            shown = merged.get("show", True) if ("label" in p or series_on) else False
            if not shown:
                continue
            ink, name, tspec = ink_of(merged)
            out.append({"element": where, "part": f"series[{si}] {s['name']!r} point {idx} label", "points": [idx], "ink": ink, "ink_name": name,
                        "spec": tspec, "on": backing(p.get("fill_role", s.get("fill_role")), merged.get("position"))})
    if family not in ("pie", "doughnut"):
        for name in ("category", "value"):
            ax = (el.get("axes") or {}).get(name) or {}
            if ax.get("visible") is False or (ax.get("labels") or {}).get("show") is False:
                continue
            ink, ink_name, tspec = ink_of(ax.get("labels") or {})
            out.append({"element": where, "part": f"{name} axis labels", "points": [], "ink": ink, "ink_name": ink_name, "spec": tspec, "on": [("plot",)]})
    legend = el.get("legend")
    if legend and legend != NONE:
        ink, ink_name, tspec = ink_of(legend)
        out.append({"element": where, "part": "legend", "points": [], "ink": ink, "ink_name": ink_name, "spec": tspec, "on": [("plot",)]})
    return out


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


def chrome_hex(ch: dict, guide: Guide, part: str) -> str | None:
    """An entry's observed `<part>_hex`, else the hex of its `<part>_role` (part: fill or
    line). None when the entry names neither: nothing is chosen for it."""
    if ch.get(f"{part}_hex"):
        return ch[f"{part}_hex"]
    role = ch.get(f"{part}_role")
    return guide.colors[role]["hex"] if role in guide.colors else None


CHROME_TEXT_KINDS = ("label", "page_number", "footer", "date")


def chrome_text(ch: dict) -> str | None:
    """The words a text entry draws, without its page-number marker; None for an entry
    that draws no text."""
    if ch["kind"] not in CHROME_TEXT_KINDS or not (ch.get("text") or ch["kind"] == "page_number"):
        return None
    return (ch.get("text") or "").replace("<page number>", "").strip()


def chrome_on_page(guide_data: dict, mode: str) -> list[dict]:
    """The guide's chrome a generated page carries, in the reference's paint order: every
    entry on at least half the reference's slides, and under --chrome none only what the
    template inherits (an entry on a layout or master). The emitter draws from this list
    and build_deck reserves zones and scores contrast from it, so what is checked is what
    is drawn. An entry without `paint_order` (a hand-written guide) keeps its list place."""
    n = max(1, guide_data.get("reference", {}).get("slides", 1))
    entries = [ch for ch in guide_data.get("chrome", []) if ch.get("slides_present", 0) >= 0.5 * n]
    if mode == "none":
        entries = [ch for ch in entries if _layers(ch) != ["slide"]]
    return [ch for _, ch in sorted(enumerate(entries), key=lambda ie: (ie[1].get("paint_order", ie[0]), ie[0]))]


def draw_chrome(slide, guide: Guide, guide_data: dict, page_w: int, page_h: int, entries: list[dict] | None = None, notes: list[dict] | None = None) -> list[str]:
    """The guide's own chrome, drawn from the observed hexes and positions. These are
    observed values of the reference, which is why literal hexes are allowed here and
    nowhere else. `entries` is the list to draw, in paint order; by default
    chrome_on_page(guide_data, "draw") (the PDF and blank-template path, --chrome draw).
    An entry is drawn at most once per slide and named by its chrome_id. A text entry is
    one line at its observed face, size and ink, turned by its rotation_deg. A picture
    entry (kind logo) becomes a picture when the entry carries `image_path`, else a rect
    placeholder in the entry's own fill or line, and `notes` names it; an entry with
    neither is not drawn, and `notes` says so. Returns the chrome_ids drawn."""
    if entries is None:
        entries = chrome_on_page(guide_data, "draw")
    present = {sp.name for sp in slide.shapes}
    drawn: list[str] = []
    for ch in entries:
        if ch["chrome_id"] in present:
            continue
        x, y, w, h = (int(v * 914400) for v in ch["box_in"])
        kind = ch["kind"]
        text = chrome_text(ch)
        if kind == "rule":
            width_emu = int(round((ch.get("line_width_pt") or 0.75) * EMU_PER_PT))
            line = _without_theme_style(slide.shapes.add_connector(1, Emu(x), Emu(y + h // 2), Emu(x + w), Emu(y + h // 2)))
            line.name = ch["chrome_id"]
            _set_line(line._element.spPr, chrome_hex(ch, guide, "line") or chrome_hex(ch, guide, "fill") or guide.colors.get("color.rule", {}).get("hex", "000000"), width_emu)
        elif kind == "band" and chrome_hex(ch, guide, "fill"):
            shape = _without_theme_style(slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h)))
            shape.name = ch["chrome_id"]
            _solid_fill(shape._element.spPr, chrome_hex(ch, guide, "fill"))  # type: ignore[arg-type]
            _set_line(shape._element.spPr, None, None)
        elif kind == "logo":
            if ch.get("image_path"):
                pic = slide.shapes.add_picture(ch["image_path"], Emu(x), Emu(y), Emu(w), Emu(h))
                pic.name = ch["chrome_id"]
            else:
                # no image bytes travel with a guide entry: a placeholder the agent can see
                # and replace, painted only in what the entry itself names
                fill_hex, line_hex = chrome_hex(ch, guide, "fill"), chrome_hex(ch, guide, "line")
                noted = notes is not None and any(n["chrome_id"] == ch["chrome_id"] for n in notes)  # once per deck, not per page
                if not fill_hex and not line_hex:
                    if notes is not None and not noted:
                        notes.append({"chrome_id": ch["chrome_id"], "kind": "logo", "drawn_as": None,
                                      "reason": "the entry carries no image_path, fill or line; add image_path, or a fill_hex/fill_role or line_hex/line_role (with line_width_pt) for a placeholder"})
                    continue
                shape = _without_theme_style(slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h)))
                shape.name = ch["chrome_id"]
                if fill_hex:
                    _solid_fill(shape._element.spPr, fill_hex)
                else:
                    _insert_fill_first(shape._element.spPr, etree.Element(qn("a:noFill")))
                _set_line(shape._element.spPr, line_hex, round(float(ch.get("line_width_pt") or 0.75) * EMU_PER_PT) if line_hex else None)
                if notes is not None and not noted:
                    notes.append({"chrome_id": ch["chrome_id"], "kind": "logo", "drawn_as": "rect placeholder", "fill_hex": fill_hex, "line_hex": line_hex,
                                  "reason": "the guide entry carries no image bytes; add image_path to the entry or place the picture by hand"})
        elif text is not None:
            rotation = float(ch.get("rotation_deg") or 0)
            box_w = max(w, 457200) if not rotation else w
            if not rotation and (ch.get("anchor") == "slide_right" or x + w > 0.8 * page_w):
                x = x + w - box_w  # keep the observed right edge: a wider box grows leftwards
            tb = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(box_w), Emu(max(h, 152400) if not rotation else h))
            tb.name = ch["chrome_id"]
            tf = tb.text_frame
            _body_props(tf._txBody, "t")
            tf._txBody.find(qn("a:bodyPr")).set("wrap", "none")  # the entry is one line of the reference: it never wraps
            p = tf.paragraphs[0]
            style = ch.get("text_style") or {}
            if text:
                run = p.add_run()
                run.text = text
                run.font.name = style.get("family") or guide.families.get("minor") or "Arial"
                run.font.size = Pt(float(style.get("size_pt") or guide.roles.get("type.caption", {}).get("size_pt") or 9))
                run.font.bold = bool(style.get("bold"))
                if style.get("ink_hex"):
                    run.font.color.rgb = RGBColor.from_string(style["ink_hex"].upper())
            if kind == "page_number" or "<page number>" in (ch.get("text") or ""):
                fld = etree.SubElement(p._p, qn("a:fld"))
                fld.set("id", "{B6F15528-21DE-4FAA-801E-634DDDAF5B2F}")
                fld.set("type", "slidenum")
                rpr = etree.SubElement(fld, qn("a:rPr"))
                rpr.set("sz", str(int(float(style.get("size_pt") or 9) * 100)))
                if style.get("ink_hex"):
                    sf = etree.SubElement(rpr, qn("a:solidFill"))
                    etree.SubElement(sf, qn("a:srgbClr")).set("val", style["ink_hex"].upper())
                etree.SubElement(rpr, qn("a:latin")).set("typeface", style.get("family") or guide.families.get("minor") or "Arial")
                etree.SubElement(fld, qn("a:t")).text = "1"
            if not rotation and (ch.get("anchor") == "slide_right" or x + box_w > 0.8 * page_w):
                p.alignment = PP_ALIGN.RIGHT
        else:
            continue
        if ch.get("rotation_deg"):
            # box_in is the pre-rotation box: turned about its centre, the shape covers what the reference's does
            # python-pptx appends each new shape to the spTree: the last child is the one just drawn
            slide.shapes._spTree[-1].find(".//" + qn("a:xfrm")).set("rot", str(round(float(ch["rotation_deg"]) * 60000)))
        drawn.append(ch["chrome_id"])
        present.add(ch["chrome_id"])
    return drawn


def _send_to_back(slide, names: list[str]) -> None:
    """Drawn chrome goes behind the content and keeps its own order among itself (`names`
    is paint order): the spTree's first two children are its properties, so the first
    name lands at index 2, the next at 3."""
    tree = slide.shapes._spTree
    by_name: dict[str, etree._Element] = {}
    for el in list(tree):
        cnv = el.find(".//" + qn("p:cNvPr"))
        if cnv is not None and cnv.get("name") in names:
            by_name.setdefault(cnv.get("name"), el)
    for i, name in enumerate(n for n in names if n in by_name):
        tree.remove(by_name[name])
        tree.insert(2 + i, by_name[name])


def _origin_tag_xml() -> bytes:
    root = etree.Element(qn("p:tagLst"), nsmap={"p": P_NS})
    tag = etree.SubElement(root, qn("p:tag"))
    tag.set("name", ORIGIN_TAG_NAME)
    tag.set("val", ORIGIN_TAG_VALUE)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def write_origin_tag(slide) -> str:
    """One User Defined Tags part per generated slide, referenced from p:cSld/p:custDataLst
    (deckgen render/emit/chrome.py add_tag_part and attach_tag_reference; 2E-1 measured
    the part surviving a PowerPoint save with its p:tag intact). python-pptx writes the
    part's content type into [Content_Types].xml and the relationship into the slide's
    rels on save. p:custDataLst follows p:spTree in CT_CommonSlideData's sequence."""
    package = slide.part.package
    partname = package.next_partname("/ppt/tags/tag%d.xml")
    part = Part(partname, CT.PML_TAGS, package, _origin_tag_xml())
    rid = slide.part.relate_to(part, RT.TAGS)
    common = slide._element.find(qn("p:cSld"))
    if common is None:
        raise SpecError("the new slide has no p:cSld to carry its origin tag")
    custom = common.find(qn("p:custDataLst"))
    if custom is None:
        custom = etree.Element(qn("p:custDataLst"))
        common.find(qn("p:spTree")).addnext(custom)
    tags = etree.SubElement(custom, qn("p:tags"))
    tags.set(qn("r:id"), rid)
    return str(partname)


PLACEHOLDER_KIND = {"page_number": "SLIDE_NUMBER", "footer": "FOOTER", "date": "DATE"}


def _layers(ch: dict) -> list[str]:
    return sorted(set(ch.get("layers") or [ch.get("source_layer") or "slide"]))


def emit(spec: dict, template: str, guide_data: dict, out: str, chrome: str) -> dict:
    guide = Guide(guide_data)
    prs = Presentation(template)
    kept = len(prs.slides)  # a template made with --keep carries pages the new ones follow
    surface = guide.colors.get("color.surface", {}).get("hex")
    wanted_chrome: set[str] = set()
    slide_only: list[dict] = []
    if chrome == "auto":
        for ch in chrome_on_page(guide_data, chrome):
            layers = _layers(ch)
            if "slide" in layers and ch["kind"] in PLACEHOLDER_KIND:
                wanted_chrome.add(PLACEHOLDER_KIND[ch["kind"]])
            if layers == ["slide"]:
                # furniture the reference pastes on every slide (a logo, a rule, a label):
                # nothing inherits it from the layout, so it is drawn on every generated
                # slide; an entry with a layout or master layer is inherited and never redrawn
                slide_only.append(ch)
    chrome_report: dict = {"mode": chrome, "placeholders_copied": sorted(wanted_chrome), "slide_layer_entries": [ch["chrome_id"] for ch in slide_only], "notes": []}
    report = {"out": out, "slides": [], "chrome": chrome_report}
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
        # a text element whose first paragraph is the title takes the layout's title
        # placeholder when the layout has one
        title_el = next((el for el in sd.get("elements", []) if el.get("kind") == "text" and el.get("paragraphs") and el["paragraphs"][0].get("role") == "type.title"), None)
        title_ph = None
        if title_el is not None and not title:
            title_ph = next((ph for ph in slide.placeholders if "TITLE" in str(ph.placeholder_format.type)), None)
            if title_ph is not None:
                filled.add(title_ph.placeholder_format.idx)
        for ph in list(slide.placeholders):
            if ph.placeholder_format.idx not in filled:
                ph._element.getparent().remove(ph._element)  # an unfilled prompt is not content
        charts: list[dict] = []
        for el in sd.get("elements", []):
            box = tuple(int(v) for v in el["box"])
            if any(v < 0 for v in box[2:]):
                raise SpecError(f"{el.get('id')}: negative extent")
            if el.get("foreign"):
                pass
            kind = el["kind"]
            if kind == "text":
                write_text(slide, el, guide, box, shape=title_ph if el is title_el else None)
            elif kind == "rule":
                write_rule(slide, el, guide, box)
            elif kind == "rect":
                write_rect(slide, el, guide, box)
            elif kind == "image":
                write_image(slide, el, box)
            elif kind == "table":
                write_table(slide, el, guide, box)
            elif kind == "chart":
                charts.append(write_chart(slide, el, guide, box))
            else:
                raise SpecError(f"{el.get('id')}: unknown element kind {kind!r}")
        if wanted_chrome:
            _copy_chrome_placeholders(slide, layout, wanted_chrome)
        drawn: list[str] = []
        page_w, page_h = int(prs.slide_width), int(prs.slide_height)
        if chrome == "draw":
            if surface and surface.upper() != "FFFFFF":
                slide.background.fill.solid()
                slide.background.fill.fore_color.rgb = RGBColor.from_string(surface.upper())
            drawn = draw_chrome(slide, guide, guide_data, page_w, page_h, notes=chrome_report["notes"])
        elif chrome == "auto" and slide_only:
            # a slide-layer page number, footer or date whose placeholder the layout carries
            # was copied above; the rest is drawn, each entry once, named by its chrome_id
            layout_kinds = {str(sp.placeholder_format.type).split(".")[-1].split(" ")[0] for sp in layout.placeholders}
            entries = [ch for ch in slide_only if PLACEHOLDER_KIND.get(ch["kind"]) not in layout_kinds]
            drawn = draw_chrome(slide, guide, guide_data, page_w, page_h, entries=entries, notes=chrome_report["notes"])
        if drawn:
            _send_to_back(slide, drawn)
        tag_part = write_origin_tag(slide)
        if sd.get("notes"):
            slide.notes_slide.notes_text_frame.text = sd["notes"]
        entry = {"slide": si, "layout": layout.name, "elements": len(sd.get("elements", [])), "chrome_drawn": drawn, "origin_tag": tag_part}
        if charts:
            entry["charts"] = charts
        report["slides"].append(entry)
    prs.save(out)
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--template", required=True)
    ap.add_argument("--guide", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--chrome", default="auto", choices=["auto", "none", "draw"], help="draw: paint the guide's chrome and surface on every slide (PDF references, blank templates)")
    args = ap.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text())
    guide = json.loads(Path(args.guide).read_text())
    print(json.dumps(emit(spec, args.template, guide, args.out, args.chrome), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
