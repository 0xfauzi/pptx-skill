#!/usr/bin/env python3
"""Read a .pptx the way PowerPoint resolves it: slide -> layout -> master -> theme.

The one OOXML reader behind the skill's scripts (fingerprint, extract_style,
gallery). zipfile + lxml only; entities are never resolved; member counts and
sizes are capped. Inheritance order and colour arithmetic follow deckgen's
style/inheritance.py and style/drawml.py (see PORT_AUDIT.md); the reader is
validated against deckgen's walker on the corpus decks, not against itself.

    ooxml.py deck.pptx            # JSON dump of every slide's resolved runs and shapes
"""

from __future__ import annotations

import colorsys
import math
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emit_pptx import ORIGIN_TAG_NAME, ORIGIN_TAG_VALUE  # noqa: E402  the producer of the tag this reader reads

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
NS = {"a": A, "p": P, "r": R, "c": C}

REL_LAYOUT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
REL_MASTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
REL_THEME = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
REL_CHART = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart"
REL_TAGS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/tags"
# roundRect's own guide value when the shape declares no adj (ECMA-376 presetShapeDefinitions;
# deckgen style/tokens.py DEFAULT_ROUND_RECT_ADJ): the radius it draws is a format fact.
DEFAULT_ROUND_RECT_ADJ = 16_667

DEFAULT_CLR_MAP = {
    "bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2",
    "accent1": "accent1", "accent2": "accent2", "accent3": "accent3",
    "accent4": "accent4", "accent5": "accent5", "accent6": "accent6",
    "hlink": "hlink", "folHlink": "folHlink",
}
TITLE_TYPES = {"title", "ctrTitle"}


def paragraphs_words(paragraphs: list[dict]) -> str:
    """The words a text frame reads as: each paragraph's runs joined as written (a break or
    a space is in the run text; a run boundary is not a space, "Revenue gr" + "owth" is one
    word), paragraphs joined by a space, whitespace collapsed. The title text the
    extractor records and the title text the build reports are this one reading."""
    return " ".join("".join(r.get("text") or "" for p in paragraphs for r in [*(p.get("runs") or []), {"text": " "}]).split())
BODY_TYPES = {"body", "subTitle"}
CHROME_TYPES = {"dt", "ftr", "sldNum"}
DEFAULT_SIZE_PT = 18.0  # ECMA-376 default when no level declares sz
DEFAULT_LINE_WIDTH_EMU = 9525  # 0.75pt, ECMA-376 default for a:ln without w
MAX_ZIP_MEMBERS = 5000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
EMU_PER_PT = 12700


def _a(tag: str) -> str:
    return f"{{{A}}}{tag}"


def _p(tag: str) -> str:
    return f"{{{P}}}{tag}"


def _c(tag: str) -> str:
    return f"{{{C}}}{tag}"


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname


# --- package ----------------------------------------------------------------------


class Package:
    """The zip, parsed on demand, with relationship lookups. Untrusted input:
    entities are not resolved and member counts and sizes are capped."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.zip = zipfile.ZipFile(path)
        infos = self.zip.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ValueError(f"{path}: {len(infos)} members exceeds {MAX_ZIP_MEMBERS}")
        for info in infos:
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"{path}: {info.filename} exceeds {MAX_MEMBER_BYTES} bytes")
        self.names = set(self.zip.namelist())
        self._roots: dict[str, etree._Element] = {}
        self._rels: dict[str, dict[str, tuple[str, str]]] = {}
        self._parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)

    def root(self, part: str) -> etree._Element:
        if part not in self._roots:
            self._roots[part] = etree.fromstring(self.zip.read(part), self._parser)
        return self._roots[part]

    def rels(self, part: str) -> dict[str, tuple[str, str]]:
        if part in self._rels:
            return self._rels[part]
        folder, _, name = part.rpartition("/")
        rels_part = f"{folder}/_rels/{name}.rels" if folder else f"_rels/{name}.rels"
        out: dict[str, tuple[str, str]] = {}
        if rels_part in self.names:
            for rel in self.root(rels_part):
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target") or ""
                if not target.startswith("/"):
                    target = _resolve_relative(folder, target)
                else:
                    target = target[1:]
                out[rel.get("Id") or ""] = (rel.get("Type") or "", target)
        self._rels[part] = out
        return out

    def rel_target(self, part: str, rel_type: str) -> str | None:
        for _, (kind, target) in self.rels(part).items():
            if kind == rel_type:
                return target
        return None

    def slide_parts(self) -> list[str]:
        pres = self.root("ppt/presentation.xml")
        rels = self.rels("ppt/presentation.xml")
        out = []
        for sld in pres.iter(_p("sldId")):
            rid = sld.get(f"{{{R}}}id")
            if rid in rels:
                out.append(rels[rid][1])
        return out


def _resolve_relative(folder: str, target: str) -> str:
    parts = folder.split("/") if folder else []
    for piece in target.split("/"):
        if piece == "..":
            if parts:
                parts.pop()
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


# --- theme and colour -----------------------------------------------------------------


@dataclass
class Theme:
    colors: dict[str, str]
    major_latin: str | None
    minor_latin: str | None
    fill_styles: list[etree._Element]
    line_styles: list[etree._Element]


def load_theme(pkg: Package, part: str) -> Theme:
    root = pkg.root(part)
    colors: dict[str, str] = {}
    scheme = root.find(f".//{_a('clrScheme')}")
    if scheme is not None:
        for slot in scheme:
            if len(slot) == 0:
                continue
            child = slot[0]
            kind = _local(child)
            value = child.get("val") if kind == "srgbClr" else child.get("lastClr")
            if value and re.fullmatch(r"[0-9A-Fa-f]{6}", value):
                colors[_local(slot)] = value.upper()
    major = root.find(f".//{_a('majorFont')}/{_a('latin')}")
    minor = root.find(f".//{_a('minorFont')}/{_a('latin')}")
    fills = root.find(f".//{_a('fmtScheme')}/{_a('fillStyleLst')}")
    lines = root.find(f".//{_a('fmtScheme')}/{_a('lnStyleLst')}")
    return Theme(
        colors=colors,
        major_latin=major.get("typeface") if major is not None else None,
        minor_latin=minor.get("typeface") if minor is not None else None,
        fill_styles=list(fills) if fills is not None else [],
        line_styles=list(lines) if lines is not None else [],
    )


def clr_map_of(el: etree._Element | None, tag: str) -> dict[str, str] | None:
    if el is None:
        return None
    mapping = dict(DEFAULT_CLR_MAP)
    for key in mapping:
        value = el.get(key)
        if value:
            mapping[key] = value
    return mapping


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def apply_transforms(rgb: tuple[int, int, int], color_el: etree._Element) -> tuple[tuple[int, int, int], float]:
    """PowerPoint's colour transforms in declaration order. Same arithmetic as
    deckgen style/drawml.py _apply_transforms: tint/shade in RGB, lum/sat/hue in HLS."""
    r, g, b = (c / 255.0 for c in rgb)
    alpha = 1.0
    for child in color_el:
        name = _local(child)
        raw = child.get("val")
        if raw is None:
            continue
        try:
            amount = float(raw) / 100000.0
        except ValueError:
            continue
        if name == "tint":
            r, g, b = r * amount + (1 - amount), g * amount + (1 - amount), b * amount + (1 - amount)
        elif name == "shade":
            r, g, b = r * amount, g * amount, b * amount
        elif name in ("lumMod", "lumOff", "satMod", "hueMod"):
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            if name == "lumMod":
                l = _clamp(l * amount)
            elif name == "lumOff":
                l = _clamp(l + amount)
            elif name == "satMod":
                s = _clamp(s * amount)
            else:
                h = (h * amount) % 1.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
        elif name == "alpha":
            alpha = _clamp(amount)
    return (round(_clamp(r) * 255), round(_clamp(g) * 255), round(_clamp(b) * 255)), alpha


PRESET_COLORS = {"black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000",
                 "blue": "0000FF", "yellow": "FFFF00", "gray": "808080", "grey": "808080",
                 "darkGray": "A9A9A9", "lightGray": "D3D3D3", "navy": "000080", "orange": "FFA500"}


def resolve_color(color_el: etree._Element, theme: Theme | None, clr_map: dict[str, str],
                  ph_color: str | None = None) -> tuple[str, float] | None:
    kind = _local(color_el)
    base: tuple[int, int, int] | None = None
    if kind == "srgbClr":
        v = color_el.get("val") or ""
        if re.fullmatch(r"[0-9A-Fa-f]{6}", v):
            base = _hex_rgb(v)
    elif kind == "sysClr":
        v = color_el.get("lastClr") or ""
        if re.fullmatch(r"[0-9A-Fa-f]{6}", v):
            base = _hex_rgb(v)
    elif kind == "scrgbClr":
        try:
            base = tuple(round(255 * float(color_el.get(k, "0")) / 100000.0) for k in ("r", "g", "b"))  # type: ignore[assignment]
        except ValueError:
            base = None
    elif kind == "hslClr":
        try:
            h = float(color_el.get("hue", "0")) / 60000.0 / 360.0
            s = float(color_el.get("sat", "0")) / 100000.0
            l = float(color_el.get("lum", "0")) / 100000.0
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            base = (round(r * 255), round(g * 255), round(b * 255))
        except ValueError:
            base = None
    elif kind == "prstClr":
        v = PRESET_COLORS.get(color_el.get("val") or "")
        base = _hex_rgb(v) if v else None
    elif kind == "schemeClr":
        scheme = color_el.get("val") or ""
        if scheme == "phClr":
            base = _hex_rgb(ph_color) if ph_color else None
        else:
            slot = clr_map.get(scheme, scheme)
            v = theme.colors.get(slot) if theme else None
            base = _hex_rgb(v) if v else None
    if base is None:
        return None
    rgb, alpha = apply_transforms(base, color_el)
    return "%02X%02X%02X" % rgb, alpha


def _hex_rgb(v: str) -> tuple[int, int, int]:
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def srgb_to_lab(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (c / 255.0 for c in _hex_rgb(hex_color))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.0
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(h1: str, h2: str) -> float:
    l1, a1, b1 = srgb_to_lab(h1)
    l2, a2, b2 = srgb_to_lab(h2)
    return math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)


# --- shape walking ------------------------------------------------------------------


@dataclass
class Run:
    chars: int
    family: str | None
    size_pt: float
    bold: bool
    color: str | None
    align: str
    ph_class: str  # title | body | chrome | table | other | none
    surface: str = ""  # the slide part this run is drawn on
    ref: str = ""  # shape id + paragraph + run, the vote's identity
    level: int = 0
    italic: bool = False
    caps: bool = False
    size_layer: str = "default"  # slide | layout | master | presentation | default
    face_layer: str = "default"
    color_layer: str = "default"
    line_spacing: float | None = None  # multiple of the size, None = single
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    bullet: str = "inherit"  # none | char | auto | inherit
    row_class: str | None = None  # header | data | totals for table runs
    text_sample: str = ""  # first characters, case evidence only
    words: int = 0
    bullet_glyph: str | None = None
    bullet_font: str | None = None
    mar_l_emu: int | None = None  # paragraph left margin as resolved, bullets hang inside it
    indent_emu: int | None = None
    text: str = ""  # the whole run, for the renderer's glyph-coverage check only
    box: tuple[int, int, int, int] | None = None  # PDF runs only: the glyphs' extent in EMU (a pptx run sits in its shape's box)


@dataclass
class Shape:
    kind: str
    box: tuple[int, int, int, int] | None  # x, y, w, h EMU
    fill: str | None
    line: str | None
    line_w_emu: int | None
    prst: str | None
    is_placeholder: bool
    ph_type: str | None
    layer: str  # slide | layout | master
    ref: str = ""
    has_effects: bool = False
    rotation: int = 0  # 60000ths of a degree, bounds are pre-rotation
    text_chars: int = 0
    dash: str | None = None
    in_group: bool = False
    text_inset_emu: tuple[int, int, int, int] | None = None  # lIns, tIns, rIns, bIns as declared, else None
    text: str | None = None  # PDF text blocks only: the first 80 characters, for chrome and title detection
    paragraphs: list | None = None  # slide-layer text shapes: [{level, bullet, align, mar_l_emu, line_spacing, space_before, space_after, runs: [{text, size_pt, bold, italic, color, family}]}]
    name: str | None = None  # p:cNvPr/@name: the emitter writes the element id there, so a finding can name it
    text_anchor: str | None = None  # bodyPr anchor (t | ctr | b) as declared on the shape
    corner_radius_emu: int | None = None  # roundRect only: adj / 100000 x min(w, h) of the drawn box
    paint_order: int = 0  # position in the page's painting sequence: a higher one paints over a lower one
    line_style: dict | None = None  # PDF text blocks only: modal family, size_pt, ink_hex and bold of the block's glyphs
    drawn_lines: int | None = None  # PDF text blocks only: the glyph lines the page draws (a pptx box's lines are measured, not read)


@dataclass
class TableObs:
    ref: str
    rows: int
    cols: int
    first_row: bool
    band_row: bool
    last_row: bool
    col_widths_emu: list[int]
    row_heights_emu: list[int]
    header_fills: list[str | None] = field(default_factory=list)
    data_fills: list[str | None] = field(default_factory=list)
    band_fills: list[str | None] = field(default_factory=list)
    edges: dict[str, list[tuple[str | None, int]]] = field(default_factory=dict)  # class -> [(color, width_emu) | None-colour means no line]
    cell_margins_emu: list[tuple[int, int, int, int]] = field(default_factory=list)
    col_aligns: list[str] = field(default_factory=list)
    col_numeric: list[float] = field(default_factory=list)  # share of data cells that parse as a figure


@dataclass
class ChartObs:
    ref: str
    kinds: list[str]
    series_fills: list[str | None]
    series_fill_layers: list[str]
    gridlines_major: bool
    gridlines_minor: bool
    gridline_color: str | None
    gridline_w_emu: int | None
    data_labels: bool
    legend_pos: str | None
    has_title: bool
    text_size_pt: float | None
    text_color: str | None
    axis_line_color: str | None


@dataclass
class SlidePrint:
    deck: str
    index: int
    width: int
    height: int
    background: str | None
    runs: list[Run] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    chrome: list[Shape] = field(default_factory=list)
    source: str = "pptx"  # pptx | pdf: a PDF carries no shape kinds or alignment
    part: str = ""
    layout_part: str = ""
    master_part: str = ""
    layout_name: str = ""
    background_layer: str = "default"
    chrome_runs: list[Run] = field(default_factory=list)
    tables: list[TableObs] = field(default_factory=list)
    charts: list[ChartObs] = field(default_factory=list)
    hidden: bool = False  # p:sld show="0"; walked as evidence (deckgen rule), flagged so the agent can exclude it
    page_class: str = "vector"  # pdf triage: vector | vector_with_image | raster_only | raster_ocr | raster_wrapper | other_size | blank
    image_cover: float = 0.0  # pdf: union area of page images over page area
    pdf_fills: list[tuple[tuple[int, int, int, int], str | None]] = field(default_factory=list)  # pdf: every filled area (rects, filled paths, images) as (box EMU, hex); None = colour unreadable (image, pattern, shading)
    generated: bool = False  # carries emit_pptx's origin tag: this skill made it, so it is not reference evidence
    unread_glyphs: int = 0  # pdf: glyphs set at an angle no type size can be read along, left out of the runs


TYPE_EVIDENCE_CLASSES = ("vector", "vector_with_image")
"""PDF page classes whose text layer is type evidence. A raster page's text layer is a
browser wrapper or an OCR layer (Times at 1pt in a grey no one drew): nothing read from
it describes the house."""


def is_type_evidence(s: SlidePrint) -> bool:
    return s.source != "pdf" or s.page_class in TYPE_EVIDENCE_CLASSES


class Chain:
    """slide part -> layout part -> master part -> theme, with the colour map."""

    def __init__(self, pkg: Package, slide_part: str) -> None:
        self.pkg = pkg
        self.slide = slide_part
        self.layout = pkg.rel_target(slide_part, REL_LAYOUT)
        self.master = pkg.rel_target(self.layout, REL_MASTER) if self.layout else None
        theme_part = pkg.rel_target(self.master, REL_THEME) if self.master else None
        self.theme_part = theme_part
        self.theme = load_theme(pkg, theme_part) if theme_part else None
        self.clr_map = dict(DEFAULT_CLR_MAP)
        if self.master:
            m = clr_map_of(pkg.root(self.master).find(_p("clrMap")), "clrMap")
            if m:
                self.clr_map = m
        for part in (self.layout, self.slide):
            if not part:
                continue
            ovr = pkg.root(part).find(f"{_p('clrMapOvr')}/{_a('overrideClrMapping')}")
            m = clr_map_of(ovr, "overrideClrMapping")
            if m:
                self.clr_map = m
        pres = pkg.root("ppt/presentation.xml")
        self.default_text_style = pres.find(_p("defaultTextStyle"))

    def color(self, color_el: etree._Element | None, ph_color: str | None = None) -> str | None:
        if color_el is None:
            return None
        out = resolve_color(color_el, self.theme, self.clr_map, ph_color)
        return out[0] if out else None

    def first_color(self, parent: etree._Element | None, ph_color: str | None = None) -> str | None:
        if parent is None:
            return None
        for child in parent:
            if _local(child) in ("srgbClr", "schemeClr", "sysClr", "scrgbClr", "hslClr", "prstClr"):
                return self.color(child, ph_color)
        return None

    def tx1(self) -> str | None:
        return self.theme.colors.get(self.clr_map.get("tx1", "dk1")) if self.theme else None


def placeholder_of(sp: etree._Element) -> tuple[str | None, int | None] | None:
    for wrapper in ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr"):
        ph = sp.find(f"{_p(wrapper)}/{_p('nvPr')}/{_p('ph')}")
        if ph is not None:
            idx = ph.get("idx")
            return ph.get("type") or ("body" if idx else None), int(idx) if idx and idx.isdigit() else None
    return None


def shape_ref(sp: etree._Element) -> str:
    for wrapper in ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr", "nvCxnSpPr"):
        cnv = sp.find(f"{_p(wrapper)}/{_p('cNvPr')}")
        if cnv is not None:
            return f"{_local(sp)}[id={cnv.get('id', '?')}]"
    return f"{_local(sp)}[?]"


def shape_name(sp: etree._Element) -> str | None:
    for wrapper in ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr", "nvCxnSpPr"):
        cnv = sp.find(f"{_p(wrapper)}/{_p('cNvPr')}")
        if cnv is not None:
            return cnv.get("name")
    return None


def ph_class(ph_type: str | None) -> str:
    if ph_type in TITLE_TYPES:
        return "title"
    if ph_type in CHROME_TYPES:
        return "chrome"
    if ph_type is None:
        return "none"
    return "body"


def find_placeholder(root: etree._Element, ph_type: str | None, idx: int | None, by_class: bool) -> etree._Element | None:
    by_idx = by_type = by_title = None
    for sp in root.iter(_p("sp")):
        key = placeholder_of(sp)
        if key is None:
            continue
        sp_type, sp_idx = key
        if by_class:
            if ph_class(sp_type) == ph_class(ph_type) and (ph_class(ph_type) != "chrome" or sp_type == ph_type):
                return sp
            continue
        if idx is not None and sp_idx == idx and by_idx is None:
            by_idx = sp
        if sp_type == ph_type and by_type is None:
            by_type = sp
        if ph_type in TITLE_TYPES and sp_type in TITLE_TYPES and by_title is None:
            by_title = sp
    return by_idx if by_idx is not None else by_type if by_type is not None else by_title


def xfrm_box(sp: etree._Element) -> tuple[int, int, int, int] | None:
    xfrm = None
    for path in (f"{_p('spPr')}/{_a('xfrm')}", f"{_p('grpSpPr')}/{_a('xfrm')}", f"{_p('xfrm')}"):
        xfrm = sp.find(path)
        if xfrm is not None:
            break
    if xfrm is None:
        return None
    off = xfrm.find(_a("off"))
    ext = xfrm.find(_a("ext"))
    if off is None or ext is None:
        return None
    try:
        return int(off.get("x", "0")), int(off.get("y", "0")), int(ext.get("cx", "0")), int(ext.get("cy", "0"))
    except ValueError:
        return None


def xfrm_rotation(sp: etree._Element) -> int:
    for path in (f"{_p('spPr')}/{_a('xfrm')}", f"{_p('grpSpPr')}/{_a('xfrm')}", f"{_p('xfrm')}"):
        xfrm = sp.find(path)
        if xfrm is not None:
            rot = xfrm.get("rot")
            try:
                return int(rot) if rot else 0
            except ValueError:
                return 0
    return 0


def visual_extent(bounds: tuple[int, int, int, int], rotation: int) -> tuple[int, int, int, int]:
    """The axis-aligned box a rotated shape occupies: OOXML rotates about the
    centre, so w' = |w cos| + |h sin|. Exact for any angle."""
    if not rotation:
        return bounds
    x, y, w, h = bounds
    radians = math.radians(rotation / 60_000)
    cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
    tw, th = round(w * cos + h * sin), round(w * sin + h * cos)
    return x + (w - tw) // 2, y + (h - th) // 2, tw, th


def round_rect_radius(prst_geom: etree._Element, box: tuple[int, int, int, int]) -> int | None:
    """The corner radius a roundRect draws: adj / 100000 x min(w, h), adj pinned to
    [0, 50000] as the preset definition pins it (deckgen style/tokens.py:5575-5600). An
    absent adj draws the default; an adj that is not "val N" is unreadable, so None."""
    adj = DEFAULT_ROUND_RECT_ADJ
    for gd in prst_geom.iterfind(f"{_a('avLst')}/{_a('gd')}"):
        if gd.get("name") != "adj":
            continue
        m = re.fullmatch(r"\s*val\s+(-?\d+)\s*", gd.get("fmla") or "")
        if m is None:
            return None
        adj = min(50_000, max(0, int(m.group(1))))
    return round(adj / 100_000 * min(box[2], box[3]))


def slide_generated(pkg: Package, slide_part: str) -> bool:
    """The slide carries emit_pptx's origin tag (write_origin_tag) in one of its tags parts."""
    for kind, target in pkg.rels(slide_part).values():
        if kind != REL_TAGS or target not in pkg.names:
            continue
        try:
            root = pkg.root(target)
        except etree.XMLSyntaxError:
            continue
        if any(t.get("name") == ORIGIN_TAG_NAME and t.get("val") == ORIGIN_TAG_VALUE for t in root.iter(_p("tag"))):
            return True
    return False


def _shape_kind(sp: etree._Element) -> str:
    local = _local(sp)
    if local == "pic":
        return "picture"
    if local == "cxnSp":
        return "line"
    if local == "graphicFrame":
        g = sp.find(f"{_a('graphic')}/{_a('graphicData')}")
        uri = g.get("uri") if g is not None else ""
        if uri and uri.endswith("/table"):
            return "table"
        if uri and uri.endswith("/chart"):
            return "chart"
        return "object"
    if local == "grpSp":
        return "group"
    prst = sp.find(f"{_p('spPr')}/{_a('prstGeom')}")
    if prst is not None and prst.get("prst") in ("line", "straightConnector1", "bentConnector3"):
        return "line"
    has_text = sp.find(f"{_p('txBody')}") is not None and bool("".join(sp.itertext()).strip())
    cnv = sp.find(f"{_p('nvSpPr')}/{_p('cNvSpPr')}")
    if cnv is not None and cnv.get("txBox") == "1":
        return "text_box"
    return "text_shape" if has_text else "shape"


_LAYER_OF_HOLDER = ("shape", "layout", "master", "master", "presentation")


LAYER_PAINT_BASE = {"master": 0, "layout": 1_000_000, "slide": 2_000_000}


class SlideWalker:
    def __init__(self, pkg: Package, slide_part: str, deck: str, index: int) -> None:
        self.pkg = pkg
        self.chain = Chain(pkg, slide_part)
        pres = pkg.root("ppt/presentation.xml")
        size = pres.find(_p("sldSz"))
        self.width = int(size.get("cx", "9144000")) if size is not None else 9144000
        self.height = int(size.get("cy", "6858000")) if size is not None else 6858000
        bg, bg_layer = self._background()
        self.print = SlidePrint(deck, index, self.width, self.height, bg, part=slide_part,
                                layout_part=self.chain.layout or "", master_part=self.chain.master or "",
                                background_layer=bg_layer)
        if self.chain.layout:
            csld = pkg.root(self.chain.layout).find(_p("cSld"))
            self.print.layout_name = csld.get("name", "") if csld is not None else ""
        self.print.hidden = pkg.root(slide_part).get("show") == "0"
        self.print.generated = slide_generated(pkg, slide_part)
        self._table_styles: dict[str, etree._Element] | None = None
        self._para_capture: list | None = None
        self._painted = 0

    # text chain ------------------------------------------------------------------
    def _level_holders(self, sp: etree._Element, layer: str, ph: tuple[str | None, int | None] | None) -> list[tuple[etree._Element | None, str]]:
        """(lstStyle-like holder, declaring layer) in precedence order."""
        holders: list[tuple[etree._Element | None, str]] = []
        tx = sp.find(_p("txBody"))
        holders.append((tx.find(_a("lstStyle")) if tx is not None else None, layer))
        ph_type = ph[0] if ph else None
        if ph is not None:
            key_type, key_idx = ph
            if layer == "slide" and self.chain.layout:
                lsp = find_placeholder(self.pkg.root(self.chain.layout), key_type, key_idx, False)
                if lsp is not None:
                    lkey = placeholder_of(lsp)
                    if lkey:
                        key_type = lkey[0] or key_type
                        key_idx = lkey[1]
                    ltx = lsp.find(_p("txBody"))
                    holders.append((ltx.find(_a("lstStyle")) if ltx is not None else None, "layout"))
            if layer in ("slide", "layout") and self.chain.master:
                msp = find_placeholder(self.pkg.root(self.chain.master), key_type, key_idx, True)
                if msp is not None:
                    mtx = msp.find(_p("txBody"))
                    holders.append((mtx.find(_a("lstStyle")) if mtx is not None else None, "master"))
        if self.chain.master and (ph is not None or layer == "master"):
            name = "titleStyle" if ph_type in TITLE_TYPES else "bodyStyle" if ph_type in BODY_TYPES else "otherStyle"
            styles = self.pkg.root(self.chain.master).find(_p("txStyles"))
            holders.append((styles.find(_p(name)) if styles is not None else None, "master"))
        holders.append((self.chain.default_text_style, "presentation"))
        return holders

    def _resolve_run(self, rpr: etree._Element | None, def_rpr: etree._Element | None,
                     holders: list[tuple[etree._Element | None, str]], level: int, getter, own_layer: str) -> tuple[object | None, str]:
        for el in (rpr, def_rpr):
            if el is not None:
                v = getter(el)
                if v is not None:
                    return v, own_layer
        tag = _a(f"lvl{level + 1}pPr")
        for holder, hl in holders:
            if holder is None:
                continue
            lvl = holder.find(tag)
            if lvl is None:
                continue
            d = lvl.find(_a("defRPr"))
            if d is None:
                continue
            v = getter(d)
            if v is not None:
                return v, hl
        return None, "default"

    def _resolve_para(self, ppr: etree._Element | None, holders: list[tuple[etree._Element | None, str]], level: int, getter) -> object | None:
        if ppr is not None:
            v = getter(ppr)
            if v is not None:
                return v
        tag = _a(f"lvl{level + 1}pPr")
        for holder, _ in holders:
            if holder is None:
                continue
            lvl = holder.find(tag)
            if lvl is not None:
                v = getter(lvl)
                if v is not None:
                    return v
        return None

    def _walk_text(self, tx: etree._Element, holders: list[tuple[etree._Element | None, str]], cls: str, ph_type: str | None,
                   sink: list[Run], surface: str, ref: str, own_layer: str, row_class: str | None = None,
                   style_color: str | None = None) -> int:
        theme = self.chain.theme
        total_chars = 0

        def g_size(el: etree._Element) -> float | None:
            sz = el.get("sz")
            try:
                return int(sz) / 100.0 if sz else None
            except ValueError:
                return None

        def g_flag(attr: str):
            def g(el: etree._Element) -> bool | None:
                v = el.get(attr)
                return None if v is None else v in ("1", "true")
            return g

        def g_caps(el: etree._Element) -> bool | None:
            v = el.get("cap")
            return None if v is None else v == "all"

        def g_face(el: etree._Element) -> str | None:
            latin = el.find(_a("latin"))
            return latin.get("typeface") if latin is not None else None

        def g_color(el: etree._Element) -> str | None:
            sf = el.find(_a("solidFill"))
            return self.chain.first_color(sf) if sf is not None else None

        def g_align(el: etree._Element) -> str | None:
            return el.get("algn")

        def g_lnspc(el: etree._Element) -> float | None:
            ln = el.find(_a("lnSpc"))
            if ln is None:
                return None
            pct = ln.find(_a("spcPct"))
            if pct is not None:
                try:
                    return int(pct.get("val", "100000")) / 100000.0
                except ValueError:
                    return None
            pts = ln.find(_a("spcPts"))
            if pts is not None:
                try:
                    return -int(pts.get("val", "0")) / 100.0  # negative = absolute points
                except ValueError:
                    return None
            return None

        def g_spc(tag: str):
            def g(el: etree._Element) -> float | None:
                sp_el = el.find(_a(tag))
                if sp_el is None:
                    return None
                pts = sp_el.find(_a("spcPts"))
                if pts is not None:
                    try:
                        return int(pts.get("val", "0")) / 100.0
                    except ValueError:
                        return None
                pct = sp_el.find(_a("spcPct"))
                if pct is not None:
                    try:
                        return -int(pct.get("val", "0")) / 100000.0  # negative = multiple of size
                    except ValueError:
                        return None
                return None
            return g

        def g_attr_int(attr: str):
            def g(el: etree._Element) -> int | None:
                v = el.get(attr)
                try:
                    return int(v) if v is not None else None
                except ValueError:
                    return None
            return g

        def g_bufont(el: etree._Element) -> str | None:
            bf = el.find(_a("buFont"))
            return bf.get("typeface") if bf is not None else None

        def g_bullet(el: etree._Element) -> str | None:
            for child in el:
                name = _local(child)
                if name == "buNone":
                    return "none"
                if name == "buChar":
                    return "char:" + (child.get("char") or "")
                if name == "buAutoNum":
                    return "auto"
                if name == "buBlip":
                    return "image"
            return None

        # autofit with fontScale < 1 makes every declared size in this body unreliable
        body_pr = tx.find(_a("bodyPr"))
        scaled = False
        if body_pr is not None:
            na = body_pr.find(_a("normAutofit"))
            if na is not None and na.get("fontScale") not in (None, "100000"):
                scaled = True
        for pi, para in enumerate(tx.iter(_a("p"))):
            ppr = para.find(_a("pPr"))
            level = 0
            if ppr is not None and ppr.get("lvl"):
                try:
                    level = int(ppr.get("lvl") or "0")
                except ValueError:
                    level = 0
            def_rpr = ppr.find(_a("defRPr")) if ppr is not None else None
            align = self._resolve_para(ppr, holders, level, g_align) or "l"
            lnspc = self._resolve_para(ppr, holders, level, g_lnspc)
            before = self._resolve_para(ppr, holders, level, g_spc("spcBef")) or 0.0
            after = self._resolve_para(ppr, holders, level, g_spc("spcAft")) or 0.0
            bullet = self._resolve_para(ppr, holders, level, g_bullet) or "inherit"
            bufont = self._resolve_para(ppr, holders, level, g_bufont)
            mar_l = self._resolve_para(ppr, holders, level, g_attr_int("marL"))
            indent = self._resolve_para(ppr, holders, level, g_attr_int("indent"))
            captured: dict | None = None
            if self._para_capture is not None:
                # line_spacing and the spacings as _resolve_para returns them (negative: points
                # for lnSpc, a multiple of the size for spcBef/spcAft), so a reader can charge
                # the pitch and the spacing the file draws
                captured = {"level": level, "bullet": str(bullet), "align": str(align), "mar_l_emu": mar_l if isinstance(mar_l, int) else 0,
                            "line_spacing": lnspc if isinstance(lnspc, float) else None, "space_before": float(before), "space_after": float(after), "runs": []}
                self._para_capture.append(captured)
            ri = 0
            gap = ""  # a whitespace-only run before the paragraph's first glyph run
            for r in para:
                if _local(r) == "br" and captured is not None:
                    # an explicit break: the emitter writes the measured lines this way, and a
                    # reader joining the runs without it would glue two words into one
                    captured["runs"].append({"text": "\n", "size_pt": DEFAULT_SIZE_PT, "bold": False, "italic": False, "color": None, "caps": False, "br": True})
                    continue
                if _local(r) not in ("r", "fld"):
                    continue
                t = r.find(_a("t"))
                text = (t.text or "") if t is not None else ""
                if not text.strip():
                    # no glyphs, so no run, but the space is drawn: it stays in the paragraph's
                    # text (joined to the run before it, or the next one), or a reader joining
                    # the runs glues "the" and "presentation" into one word (45541 slide 2)
                    if captured is not None and text:
                        if captured["runs"] and not captured["runs"][-1].get("br"):
                            captured["runs"][-1]["text"] += text
                        else:
                            gap += text
                    continue
                rpr = r.find(_a("rPr"))
                size, size_layer = self._resolve_run(rpr, def_rpr, holders, level, g_size, own_layer)
                bold, _ = self._resolve_run(rpr, def_rpr, holders, level, g_flag("b"), own_layer)
                italic, _ = self._resolve_run(rpr, def_rpr, holders, level, g_flag("i"), own_layer)
                caps, _ = self._resolve_run(rpr, def_rpr, holders, level, g_caps, own_layer)
                face, face_layer = self._resolve_run(rpr, def_rpr, holders, level, g_face, own_layer)
                color, color_layer = self._resolve_run(rpr, def_rpr, holders, level, g_color, own_layer)
                if face in ("+mj-lt", "+mn-lt", None) and theme:
                    face = theme.major_latin if (face == "+mj-lt" or (face is None and ph_type in TITLE_TYPES)) else theme.minor_latin
                    face_layer = "theme" if face_layer == "default" else face_layer
                if style_color is not None and (color is None or color_layer in ("master", "presentation")):
                    # p:style/a:fontRef is the shape's own default text colour: it sits above the
                    # master's otherStyle and the presentation default, below the run and the
                    # shape's lstStyle (white labels on a filled rectangle read as black without it)
                    color, color_layer = style_color, "shape_style"
                if color is None:
                    color = self.chain.tx1()
                    color_layer = "theme"
                chars = len(text.strip())
                total_chars += chars
                size_pt = float(size) if isinstance(size, (int, float)) else DEFAULT_SIZE_PT
                # spcPct is a share of a line (1.2 x size): decoded here so no negative value
                # leaves the reader (the stock master's 20% once reached the emitter as -20pt
                # and LibreOffice dropped every paragraph carrying it)
                before_pt = float(before) if before >= 0 else -float(before) * 1.2 * size_pt
                after_pt = float(after) if after >= 0 else -float(after) * 1.2 * size_pt
                if captured is not None:
                    captured["runs"].append({"text": gap + text, "size_pt": float(size) if isinstance(size, (int, float)) else DEFAULT_SIZE_PT,
                                             "bold": bool(bold), "italic": bool(italic), "color": color, "caps": bool(caps), "family": face})
                sink.append(Run(
                    chars=chars, family=face,
                    size_pt=size_pt,
                    bold=bool(bold), color=color, align=str(align), ph_class=cls,
                    surface=surface, ref=f"{ref}/p[{pi}]/r[{ri}]", level=level,
                    italic=bool(italic), caps=bool(caps),
                    size_layer=("autofit" if scaled else size_layer), face_layer=face_layer, color_layer=color_layer,
                    line_spacing=lnspc if isinstance(lnspc, float) else None,
                    space_before_pt=round(before_pt, 2), space_after_pt=round(after_pt, 2),
                    bullet=("char" if str(bullet).startswith("char:") else str(bullet)),
                    row_class=row_class, text_sample=text.strip()[:40],
                    words=len(text.split()), bullet_glyph=(str(bullet)[5:] if str(bullet).startswith("char:") else None),
                    bullet_font=(str(bufont) if bufont else None),
                    mar_l_emu=mar_l if isinstance(mar_l, int) else None, indent_emu=indent if isinstance(indent, int) else None,
                    text=text,
                ))
                gap = ""
                ri += 1
        return total_chars

    # shapes ----------------------------------------------------------------------
    def _background(self) -> tuple[str | None, str]:
        for part, layer in ((self.chain.slide, "slide"), (self.chain.layout, "layout"), (self.chain.master, "master")):
            if not part:
                continue
            bg = self.pkg.root(part).find(f"{_p('cSld')}/{_p('bg')}")
            if bg is None:
                continue
            bgpr = bg.find(_p("bgPr"))
            if bgpr is not None:
                sf = bgpr.find(_a("solidFill"))
                if sf is not None:
                    return self.chain.first_color(sf), layer
                gf = bgpr.find(_a("gradFill"))
                if gf is not None:
                    gs = gf.find(f"{_a('gsLst')}/{_a('gs')}")
                    return (self.chain.first_color(gs) if gs is not None else None), layer
                return None, layer
            ref = bg.find(_p("bgRef"))
            if ref is not None:
                return self.chain.first_color(ref), layer
        if self.chain.theme:
            return self.chain.theme.colors.get(self.chain.clr_map.get("bg1", "lt1")), "theme"
        return None, "default"

    def _fill(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> str | None:
        for candidate in self._sppr_chain(sp, ph, layer):
            if candidate is None:
                continue
            for child in candidate:
                name = _local(child)
                if name == "noFill":
                    return None
                if name == "solidFill":
                    return self.chain.first_color(child)
                if name == "gradFill":
                    gs = child.find(f"{_a('gsLst')}/{_a('gs')}")
                    return self.chain.first_color(gs) if gs is not None else None
                if name in ("blipFill", "pattFill"):
                    return None
        style = sp.find(_p("style"))
        if style is not None and self.chain.theme:
            ref = style.find(_a("fillRef"))
            if ref is not None:
                try:
                    idx = int(ref.get("idx", "0"))
                except ValueError:
                    idx = 0
                if idx == 0:
                    return None
                ph_color = self.chain.first_color(ref)
                if 1 <= idx <= len(self.chain.theme.fill_styles):
                    fs = self.chain.theme.fill_styles[idx - 1]
                    if _local(fs) == "solidFill":
                        return self.chain.first_color(fs, ph_color)
                    if _local(fs) == "gradFill":
                        gs = fs.find(f"{_a('gsLst')}/{_a('gs')}")
                        return self.chain.first_color(gs, ph_color) if gs is not None else ph_color
                return ph_color
        return None

    def _sppr_chain(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> list[etree._Element | None]:
        out = [sp.find(_p("spPr"))]
        if ph is not None:
            key_type, key_idx = ph
            if layer == "slide" and self.chain.layout:
                lsp = find_placeholder(self.pkg.root(self.chain.layout), key_type, key_idx, False)
                if lsp is not None:
                    out.append(lsp.find(_p("spPr")))
                    lkey = placeholder_of(lsp)
                    if lkey:
                        key_type, key_idx = lkey[0] or key_type, lkey[1]
            if layer in ("slide", "layout") and self.chain.master:
                msp = find_placeholder(self.pkg.root(self.chain.master), key_type, key_idx, True)
                if msp is not None:
                    out.append(msp.find(_p("spPr")))
        return out

    def _line(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> tuple[str | None, int | None, str | None]:
        for candidate in self._sppr_chain(sp, ph, layer):
            if candidate is None:
                continue
            ln = candidate.find(_a("ln"))
            if ln is None:
                continue
            w = ln.get("w")
            width = int(w) if w and w.isdigit() else None
            dash_el = ln.find(_a("prstDash"))
            dash = dash_el.get("val") if dash_el is not None else None
            for child in ln:
                if _local(child) == "noFill":
                    return None, None, None
                if _local(child) == "solidFill":
                    return self.chain.first_color(child), width or DEFAULT_LINE_WIDTH_EMU, dash or "solid"
            if width is not None:
                break
        style = sp.find(_p("style"))
        if style is not None and self.chain.theme:
            ref = style.find(_a("lnRef"))
            if ref is not None:
                try:
                    idx = int(ref.get("idx", "0"))
                except ValueError:
                    idx = 0
                if idx == 0:
                    return None, None, None
                ph_color = self.chain.first_color(ref)
                if 1 <= idx <= len(self.chain.theme.line_styles):
                    ls = self.chain.theme.line_styles[idx - 1]
                    w = ls.get("w")
                    sf = ls.find(_a("solidFill"))
                    dash_el = ls.find(_a("prstDash"))
                    return ((self.chain.first_color(sf, ph_color) if sf is not None else ph_color),
                            int(w) if w and w.isdigit() else DEFAULT_LINE_WIDTH_EMU,
                            dash_el.get("val") if dash_el is not None else "solid")
                return ph_color, DEFAULT_LINE_WIDTH_EMU, "solid"
        return None, None, None

    def _has_effects(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> bool:
        for candidate in self._sppr_chain(sp, ph, layer):
            if candidate is None:
                continue
            eff = candidate.find(_a("effectLst"))
            if eff is not None:
                return len(eff) > 0
        style = sp.find(_p("style"))
        if style is not None:
            ref = style.find(_a("effectRef"))
            if ref is not None:
                try:
                    return int(ref.get("idx", "0")) > 0
                except ValueError:
                    return False
        return False

    def _box_of(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> tuple[int, int, int, int] | None:
        box = xfrm_box(sp)
        if box is not None or ph is None:
            return box
        key_type, key_idx = ph
        if layer == "slide" and self.chain.layout:
            lsp = find_placeholder(self.pkg.root(self.chain.layout), key_type, key_idx, False)
            if lsp is not None:
                box = xfrm_box(lsp)
                if box is not None:
                    return box
                lkey = placeholder_of(lsp)
                if lkey:
                    key_type, key_idx = lkey[0] or key_type, lkey[1]
        if self.chain.master:
            msp = find_placeholder(self.pkg.root(self.chain.master), key_type, key_idx, True)
            if msp is not None:
                return xfrm_box(msp)
        return None

    # tables ------------------------------------------------------------------------
    def _table_style(self, style_id: str | None) -> etree._Element | None:
        if not style_id or "ppt/tableStyles.xml" not in self.pkg.names:
            return None
        if self._table_styles is None:
            self._table_styles = {}
            for st in self.pkg.root("ppt/tableStyles.xml").iter(_a("tblStyle")):
                self._table_styles[st.get("styleId", "")] = st
        return self._table_styles.get(style_id)

    def _style_part_fill(self, style: etree._Element | None, part: str) -> str | None:
        if style is None:
            return None
        el = style.find(f"{_a(part)}/{_a('tcStyle')}/{_a('fill')}")
        if el is None:
            return None
        sf = el.find(_a("solidFill"))
        return self.chain.first_color(sf) if sf is not None else None

    def _style_part_border(self, style: etree._Element | None, part: str, side: str) -> tuple[str | None, int] | None:
        if style is None:
            return None
        ln = style.find(f"{_a(part)}/{_a('tcStyle')}/{_a('tcBdr')}/{_a(side)}/{_a('ln')}")
        if ln is None:
            return None
        return self._ln_rule(ln)

    def _ln_rule(self, ln: etree._Element) -> tuple[str | None, int] | None:
        w = ln.get("w")
        width = int(w) if w and w.isdigit() else DEFAULT_LINE_WIDTH_EMU
        for child in ln:
            if _local(child) == "noFill":
                return (None, 0)
            if _local(child) == "solidFill":
                return (self.chain.first_color(child), width)
        return None

    def _walk_table(self, frame: etree._Element, ref: str, surface: str, box: tuple[int, int, int, int] | None) -> None:
        tbl = frame.find(f".//{_a('tbl')}")
        if tbl is None:
            return
        tblpr = tbl.find(_a("tblPr"))
        flags = {k: (tblpr.get(k) in ("1", "true")) if tblpr is not None else False for k in ("firstRow", "bandRow", "lastRow", "firstCol")}
        style_id_el = tblpr.find(_a("tableStyleId")) if tblpr is not None else None
        style = self._table_style(style_id_el.text.strip() if style_id_el is not None and style_id_el.text else None)
        cols = [int(g.get("w", "0")) for g in tbl.findall(f"{_a('tblGrid')}/{_a('gridCol')}") if (g.get("w") or "0").isdigit()]
        rows = tbl.findall(_a("tr"))
        if not rows or not cols or len(rows) * len(cols) > 50000:
            return
        obs = TableObs(ref, len(rows), len(cols), flags["firstRow"], flags["bandRow"], flags["lastRow"],
                       cols, [int(r.get("h", "0")) if (r.get("h") or "0").isdigit() else 0 for r in rows])
        n = len(rows)
        edges: dict[str, list] = {k: [] for k in ("table_top", "header_bottom", "row_interior", "table_bottom", "table_left", "column_interior", "table_right")}
        col_align: list[Counter] = [Counter() for _ in cols]
        col_num: list[list[bool]] = [[] for _ in cols]
        grid: list[list[etree._Element | None]] = []
        for ri, tr in enumerate(rows):
            tcs = [tc for tc in tr if _local(tc) == "tc"]
            grid.append(tcs + [None] * (len(cols) - len(tcs)))
            row_class = "header" if flags["firstRow"] and ri == 0 else "totals" if flags["lastRow"] and ri == n - 1 else "data"
            data_index = ri - (1 if flags["firstRow"] else 0)
            for ci, tc in enumerate(tcs[: len(cols)]):
                if tc.get("hMerge") in ("1", "true") or tc.get("vMerge") in ("1", "true"):
                    continue
                tcpr = tc.find(_a("tcPr"))
                fill: str | None = None
                explicit = False
                if tcpr is not None:
                    for child in tcpr:
                        if _local(child) == "solidFill":
                            fill, explicit = self.chain.first_color(child), True
                        elif _local(child) == "noFill":
                            fill, explicit = None, True
                if not explicit:
                    if row_class == "header":
                        fill = self._style_part_fill(style, "firstRow")
                    if fill is None and row_class == "data" and flags["bandRow"] and data_index % 2 == 0:
                        fill = self._style_part_fill(style, "band1H")
                    if fill is None:
                        fill = self._style_part_fill(style, "wholeTbl")
                if row_class == "header":
                    obs.header_fills.append(fill)
                elif row_class == "data":
                    (obs.band_fills if (flags["bandRow"] and data_index % 2 == 0) else obs.data_fills).append(fill)
                if tcpr is not None and all(tcpr.get(m) for m in ("marL", "marR", "marT", "marB")):
                    try:
                        obs.cell_margins_emu.append(tuple(int(tcpr.get(m)) for m in ("marL", "marR", "marT", "marB")))  # type: ignore[arg-type]
                    except ValueError:
                        pass
                txb = tc.find(_a("txBody"))
                if txb is not None:
                    runs_before = len(self.print.runs)
                    self._walk_text(txb, [(self.chain.default_text_style, "presentation")], "table", None, self.print.runs,
                                    surface, f"{ref}/tr[{ri}]/tc[{ci}]", "slide", row_class)
                    style_text = style.find(f"{_a('firstRow' if row_class == 'header' else 'wholeTbl')}/{_a('tcTxStyle')}") if style is not None else None
                    cell_text = "".join(r.text_sample for r in self.print.runs[runs_before:]).strip()
                    if row_class == "data" and cell_text:
                        col_num[ci].append(bool(re.fullmatch(r"[\(\-\$\u20ac\u00a3]?\s*[\d,\.]+\s*[%x\)]?[A-Za-z]{0,2}", cell_text)))
                    for run in self.print.runs[runs_before:]:
                        col_align[ci][run.align] += run.chars
                        if style_text is not None:
                            if run.color_layer in ("theme", "presentation", "default", "master"):
                                # a run with no colour of its own takes the table style's: tcTxStyle's
                                # own colour child (schemeClr lt1 on the stock header row) outranks
                                # the fontRef's prstClr black beside it, and both outrank the
                                # presentation default the run otherwise falls to
                                font_ref_el = style_text.find(_a("fontRef"))
                                c = self.chain.first_color(style_text) or (self.chain.first_color(font_ref_el) if font_ref_el is not None else None)
                                if c:
                                    run.color, run.color_layer = c, "table_style"
                            if style_text.get("b") == "on" and not run.bold:
                                run.bold = True
        # edges: upper cell's lnB wins over lower cell's lnT (measured in deckgen on PowerPoint re-saves); left lnR over right lnL
        def cell_border(tc: etree._Element | None, side: str) -> tuple[str | None, int] | None:
            if tc is None:
                return None
            tcpr = tc.find(_a("tcPr"))
            if tcpr is None:
                return None
            ln = tcpr.find(_a(side))
            return self._ln_rule(ln) if ln is not None else None

        for ri in range(n + 1):
            klass = "table_top" if ri == 0 else "table_bottom" if ri == n else "header_bottom" if (flags["firstRow"] and ri == 1) else "row_interior"
            for ci in range(len(cols)):
                upper = grid[ri - 1][ci] if ri > 0 and ci < len(grid[ri - 1]) else None
                lower = grid[ri][ci] if ri < n and ci < len(grid[ri]) else None
                rule = cell_border(upper, "lnB") or cell_border(lower, "lnT")
                if rule is None:
                    side = "top" if ri == 0 else "bottom" if ri == n else "insideH"
                    rule = self._style_part_border(style, "wholeTbl", side)
                    if rule is None and klass == "header_bottom":
                        rule = self._style_part_border(style, "firstRow", "bottom")
                edges[klass].append(rule if rule is not None else (None, 0))
        for ci in range(len(cols) + 1):
            klass = "table_left" if ci == 0 else "table_right" if ci == len(cols) else "column_interior"
            for ri in range(n):
                left = grid[ri][ci - 1] if ci > 0 and ci - 1 < len(grid[ri]) else None
                right = grid[ri][ci] if ci < len(cols) and ci < len(grid[ri]) else None
                rule = cell_border(left, "lnR") or cell_border(right, "lnL")
                if rule is None:
                    side = "left" if ci == 0 else "right" if ci == len(cols) else "insideV"
                    rule = self._style_part_border(style, "wholeTbl", side)
                edges[klass].append(rule if rule is not None else (None, 0))
        obs.edges = edges
        obs.col_aligns = [c.most_common(1)[0][0] if c else "l" for c in col_align]
        obs.col_numeric = [(sum(v) / len(v)) if v else 0.0 for v in col_num]
        self.print.tables.append(obs)

    # charts ----------------------------------------------------------------------------
    def _walk_chart(self, frame: etree._Element, ref: str) -> None:
        gd = frame.find(f"{_a('graphic')}/{_a('graphicData')}")
        if gd is None:
            return
        chart_el = gd.find(_c("chart"))
        if chart_el is None:
            return
        rid = chart_el.get(f"{{{R}}}id")
        rels = self.pkg.rels(self.chain.slide)
        if rid not in rels or rels[rid][1] not in self.pkg.names:
            return
        root = self.pkg.root(rels[rid][1])
        plot = root.find(f".//{_c('plotArea')}")
        if plot is None:
            return
        kinds = [_local(ch)[:-5] for ch in plot if _local(ch).endswith("Chart")]
        fills: list[str | None] = []
        layers: list[str] = []
        accents = ["accent1", "accent2", "accent3", "accent4", "accent5", "accent6"]
        for si, ser in enumerate(plot.iter(_c("ser"))):
            sppr = ser.find(_c("spPr"))
            color = None
            if sppr is not None:
                sf = sppr.find(_a("solidFill"))
                if sf is not None:
                    color = self.chain.first_color(sf)
                else:
                    ln = sppr.find(_a("ln"))
                    if ln is not None:
                        sfl = ln.find(_a("solidFill"))
                        if sfl is not None:
                            color = self.chain.first_color(sfl)
            if color is not None:
                fills.append(color)
                layers.append("explicit")
            else:
                slot = self.chain.clr_map.get(accents[si % 6], accents[si % 6])
                fills.append(self.chain.theme.colors.get(slot) if self.chain.theme else None)
                layers.append("theme_accent_cycle")
        grid_major = grid_minor = False
        grid_color: str | None = None
        grid_w: int | None = None
        axis_line: str | None = None
        for ax in list(plot.iter(_c("valAx"))) + list(plot.iter(_c("catAx"))):
            mg = ax.find(_c("majorGridlines"))
            if mg is not None and _local(ax) == "valAx":
                grid_major = True
                sppr = mg.find(_c("spPr"))
                if sppr is not None:
                    ln = sppr.find(_a("ln"))
                    if ln is not None:
                        r = self._ln_rule(ln)
                        if r:
                            grid_color, grid_w = r
            if ax.find(_c("minorGridlines")) is not None:
                grid_minor = True
            sppr = ax.find(_c("spPr"))
            if sppr is not None and axis_line is None:
                ln = sppr.find(_a("ln"))
                if ln is not None:
                    r = self._ln_rule(ln)
                    if r and r[0]:
                        axis_line = r[0]
        dl = root.find(f".//{_c('dLbls')}/{_c('showVal')}")
        data_labels = dl is not None and dl.get("val") in ("1", "true")
        legend = root.find(f".//{_c('legend')}/{_c('legendPos')}")
        legend_pos = legend.get("val") if legend is not None else None
        has_title = root.find(f".//{_c('title')}") is not None
        tsize: float | None = None
        tcolor: str | None = None
        for defrpr in root.iter(_a("defRPr")):
            if tsize is None and defrpr.get("sz"):
                try:
                    tsize = int(defrpr.get("sz")) / 100.0
                except ValueError:
                    pass
            if tcolor is None:
                sf = defrpr.find(_a("solidFill"))
                if sf is not None:
                    tcolor = self.chain.first_color(sf)
            if tsize is not None and tcolor is not None:
                break
        self.print.charts.append(ChartObs(ref, kinds, fills, layers, grid_major, grid_minor, grid_color, grid_w,
                                          data_labels, legend_pos, has_title, tsize, tcolor, axis_line))

    # tree -----------------------------------------------------------------------------
    def walk_tree(self, tree: etree._Element, layer: str, sink: list[Shape], with_text: bool, surface: str,
                  transform: tuple[float, float, float, float] | None = None) -> None:
        for sp in tree:
            local = _local(sp)
            if local not in ("sp", "pic", "cxnSp", "graphicFrame", "grpSp"):
                continue
            ph = placeholder_of(sp)
            if layer != "slide" and ph is not None and ph_class(ph[0]) in ("title", "body") and local == "sp":
                # A layout/master placeholder prototype is a template, not chrome.
                continue
            ref = shape_ref(sp)
            if local == "grpSp":
                box = xfrm_box(sp)
                xfrm = sp.find(f"{_p('grpSpPr')}/{_a('xfrm')}")
                child_t = transform
                if box and xfrm is not None:
                    choff = xfrm.find(_a("chOff"))
                    chext = xfrm.find(_a("chExt"))
                    if choff is not None and chext is not None:
                        try:
                            cx, cy = int(chext.get("cx", "0")), int(chext.get("cy", "0"))
                            ox, oy = int(choff.get("x", "0")), int(choff.get("y", "0"))
                            sx = box[2] / cx if cx else 1.0
                            sy = box[3] / cy if cy else 1.0
                            abs_box = _apply_transform(box, transform)
                            child_t = (abs_box[0] - ox * sx, abs_box[1] - oy * sy, sx, sy)
                        except ValueError:
                            child_t = transform
                self.walk_tree(sp, layer, sink, with_text, surface, child_t)
                continue
            box = self._box_of(sp, ph, layer)
            if box is not None:
                box = _apply_transform(box, transform)
            fill = self._fill(sp, ph, layer) if local in ("sp", "cxnSp") else None
            line, line_w, dash = self._line(sp, ph, layer) if local in ("sp", "cxnSp") else (None, None, None)
            prst_el = sp.find(f"{_p('spPr')}/{_a('prstGeom')}")
            shape = Shape(
                kind=_shape_kind(sp), box=box, fill=fill, line=line, line_w_emu=line_w,
                prst=prst_el.get("prst") if prst_el is not None else None,
                is_placeholder=ph is not None, ph_type=ph[0] if ph else None, layer=layer, ref=ref,
                has_effects=self._has_effects(sp, ph, layer) if local in ("sp", "pic", "cxnSp") else False,
                rotation=xfrm_rotation(sp), dash=dash, in_group=transform is not None, name=shape_name(sp),
            )
            if shape.prst == "roundRect" and box is not None:
                shape.corner_radius_emu = round_rect_radius(prst_el, box)
            # the master paints first, then the layout, then the slide, each in spTree order
            shape.paint_order = LAYER_PAINT_BASE[layer] + self._painted
            self._painted += 1
            sink.append(shape)
            cls = ph_class(ph[0]) if ph else "none"
            tx = sp.find(_p("txBody"))
            if tx is not None:
                bpr = tx.find(_a("bodyPr"))
                if bpr is not None and any(bpr.get(k) for k in ("lIns", "tIns", "rIns", "bIns")):
                    try:
                        shape.text_inset_emu = tuple(int(bpr.get(k, d)) for k, d in (("lIns", "91440"), ("tIns", "45720"), ("rIns", "91440"), ("bIns", "45720")))  # type: ignore[assignment]
                    except ValueError:
                        shape.text_inset_emu = None
                # a date, footer or slide-number placeholder is furniture even on the slide
                # layer: its runs never vote for a text role (a right-aligned page number once
                # decided the alignment of every caption in a deck)
                is_content = with_text and not (ph is not None and ph[0] in CHROME_TYPES)
                run_sink = self.print.runs if is_content else self.print.chrome_runs
                self._para_capture = [] if with_text else None
                if bpr is not None and bpr.get("anchor"):
                    shape.text_anchor = bpr.get("anchor")
                style_el = sp.find(_p("style"))
                font_ref = style_el.find(_a("fontRef")) if style_el is not None else None
                style_color = self.chain.first_color(font_ref) if font_ref is not None else None
                shape.text_chars = self._walk_text(tx, self._level_holders(sp, layer, ph), cls if with_text else "chrome",
                                                   ph[0] if ph else None, run_sink, surface, ref, layer, style_color=style_color)
                shape.paragraphs = self._para_capture
                self._para_capture = None
            if local == "graphicFrame" and with_text:
                kind = shape.kind
                if kind == "table":
                    self._walk_table(sp, ref, surface, box)
                elif kind == "chart":
                    self._walk_chart(sp, ref)

    def run(self) -> SlidePrint:
        root = self.pkg.root(self.chain.slide)
        tree = root.find(f"{_p('cSld')}/{_p('spTree')}")
        if tree is not None:
            self.walk_tree(tree, "slide", self.print.shapes, True, self.chain.slide)
        for part, layer in ((self.chain.layout, "layout"), (self.chain.master, "master")):
            if not part:
                continue
            tree = self.pkg.root(part).find(f"{_p('cSld')}/{_p('spTree')}")
            if tree is not None:
                self.walk_tree(tree, layer, self.print.chrome, False, part)
        return self.print


def _apply_transform(box: tuple[int, int, int, int], t: tuple[float, float, float, float] | None) -> tuple[int, int, int, int]:
    if t is None:
        return box
    ox, oy, sx, sy = t
    return int(ox + box[0] * sx), int(oy + box[1] * sy), int(box[2] * sx), int(box[3] * sy)


def fingerprint_deck(path: str, max_pages: int | None = None) -> list[SlidePrint]:
    if path.lower().endswith(".pdf"):
        return fingerprint_pdf(path, max_pages)
    pkg = Package(path)
    name = Path(path).stem
    out = []
    for i, part in enumerate(pkg.slide_parts()):
        if max_pages is not None and i >= max_pages:
            break
        out.append(SlideWalker(pkg, part, name, i).run())
    return out


# --- ink over backing, as the reference draws it -------------------------------------


def _covers(outer: tuple[int, int, int, int], x: float, y: float) -> bool:
    return outer[0] <= x <= outer[0] + outer[2] and outer[1] <= y <= outer[1] + outer[3]


def ink_backings(slides: list[SlidePrint]) -> dict[tuple[str, str], dict]:
    """Every (text ink, backing fill) pair the reference draws, with the smallest size it
    sets that pair at, the characters and the pages. In a pptx the backing of a run is its
    own shape's fill, else the topmost filled shape drawn before it whose box holds the
    shape's centre (master, then layout, then slide layer, in file order), else the page
    ground; in a PDF, the smallest filled area holding the run's centre. A run over a
    picture, a pattern or a shading has no known backing and is left out, as are table
    runs (cell fills are per cell) and chrome runs (their shape ids repeat across layers).
    Raster pages and generated slides are not evidence."""
    out: dict[tuple[str, str], dict] = {}
    for s in slides:
        if not is_type_evidence(s) or s.generated:
            continue
        under = [sh for layer in ("master", "layout") for sh in s.chrome if sh.layer == layer] + list(s.shapes)
        for r in s.runs:
            if not r.color or r.ph_class == "table" or not r.chars:
                continue
            if s.source == "pdf":
                if r.box is None:
                    continue
                cx, cy = r.box[0] + r.box[2] / 2, r.box[1] + r.box[3] / 2
                # a PDF keeps no draw order across rects, paths and images: the smallest filled
                # area holding the run's centre is taken as the one drawn under it
                holding = [(b[2] * b[3], hexv) for b, hexv in s.pdf_fills if _covers(b, cx, cy)]
                backing = min(holding, key=lambda t: t[0])[1] if holding else (s.background or None)
                if backing is None:
                    continue
            else:
                own_idx = next((i for i, sh in enumerate(under) if sh.layer == "slide" and r.ref.startswith(sh.ref + "/")), None)
                if own_idx is None or under[own_idx].box is None:
                    continue
                own = under[own_idx]
                b = own.box
                cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
                backing = own.fill or None
                if backing is None:
                    for sh in reversed(under[:own_idx]):
                        if sh.box is None or not _covers(sh.box, cx, cy):
                            continue
                        if sh.kind == "picture":
                            backing = "picture"
                            break
                        if sh.fill and sh.kind != "line":
                            backing = sh.fill
                            break
                    else:
                        backing = s.background
            if not backing or backing == "picture":
                continue
            entry = out.setdefault((r.color, backing), {"min_size_pt": r.size_pt, "chars": 0, "pages": set()})
            entry["min_size_pt"] = min(entry["min_size_pt"], r.size_pt)
            entry["chars"] += r.chars
            entry["pages"].add(s.index + 1)
    return out


# --- pdf references ------------------------------------------------------------------


def _pdf_color(value: object) -> str | None:
    """pdfplumber colour tuples: gray (1), RGB (3) or CMYK (4) floats in 0..1."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = (value,)
    if isinstance(value, str):
        return None
    try:
        comps = [float(v) for v in value]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    if len(comps) == 1:
        g = comps[0]
        rgb = (g, g, g)
    elif len(comps) == 3:
        rgb = (comps[0], comps[1], comps[2])
    elif len(comps) == 4:
        c, m, y, k = comps
        rgb = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    else:
        return None
    return "%02X%02X%02X" % tuple(round(_clamp(v) * 255) for v in rgb)


def _pdf_family(fontname: str | None) -> tuple[str | None, bool]:
    if not fontname:
        return None, False
    name = fontname.split("+", 1)[1] if "+" in fontname[:8] else fontname
    bold = "bold" in name.lower() or "black" in name.lower() or "heavy" in name.lower()
    base = re.split(r"[-,]", name, maxsplit=1)[0]
    base = re.sub(r"(MT|PS|PSMT|Std|Pro)$", "", base)
    base = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base)  # ArialNarrow -> Arial Narrow
    return base.strip() or None, bold


PDF_TRIAGE_IMAGE_COVER = 0.4
"""A page whose images cover at least this share is a candidate scan. Measured on the 8
public reference PDFs (scratchpad/probe_pdf/triage.json, 2026-10-20): EDGAR browser prints
embed the slide as one image at 0.47 to 0.69 of a letter page; Citi and the UF McKinsey
scans sit at 1.0; vector decks with a photo or chart image reach 0.61 to 0.66 on single
pages (jazz p5, p6) and the calstrs deck paints full-bleed background images under vector
text (cover 1.0 to 2.5 before the union), which is why coverage alone decides nothing and
the text placement rule below is needed."""
PDF_TRIAGE_MIN_TEXT_PT = 4.0
"""Characters below this size are not type a reader sees: the EDGAR prints carry an OCR
layer at 0 to 1pt (Goldman p3: 4273 of 4414 chars at 1pt) and Tesseract layers come as
GlyphLessFont at box-derived sizes."""


def _pdf_key(obj: dict) -> tuple:
    return (obj.get("object_type"), round(float(obj.get("x0", 0)), 2), round(float(obj.get("top", 0)), 2),
            round(float(obj.get("x1", 0)), 2), round(float(obj.get("bottom", 0)), 2))


def _slide_shaped(w: float, h: float, tolerance: float = 0.015) -> bool:
    """4:3, 16:9 or 16:10 within 1.5%: letter landscape is 1.294 and A4 landscape 1.414, both outside."""
    if w <= 0 or h <= 0:
        return False
    ratio = w / h
    return any(abs(ratio - r) / r <= tolerance for r in (4 / 3, 16 / 9, 16 / 10))


def _union_cover(boxes: list[tuple[float, float, float, float]], w: float, h: float) -> float:
    """Union area of clipped boxes over the page, on a 200x200 grid (exact enough for a share)."""
    if not boxes or w <= 0 or h <= 0:
        return 0.0
    n = 200
    grid = bytearray(n * n)
    for x0, t, x1, b in boxes:
        c0, c1 = max(0, int(x0 / w * n)), min(n, int(x1 / w * n) + 1)
        r0, r1 = max(0, int(t / h * n)), min(n, int(b / h * n) + 1)
        for r in range(r0, r1):
            base = r * n
            for c in range(c0, c1):
                grid[base + c] = 1
    return sum(grid) / (n * n)


def _image_regions(boxes: list[tuple[float, float, float, float]], w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Touching images as one picture each: a producer that tiles one picture into strips
    (bain p52 draws 15,554 image objects) paints one element, not thousands. Tiles join
    when they mark adjacent cells of the 200 x 200 page grid _union_cover uses."""
    if len(boxes) <= 1:
        return list(boxes)
    n = 200
    label = [-1] * (n * n)
    cells_of: list[list[int]] = []
    for x0, t, x1, b in boxes:
        c0, c1 = max(0, int(x0 / w * n)), min(n, int(x1 / w * n) + 1)
        r0, r1 = max(0, int(t / h * n)), min(n, int(b / h * n) + 1)
        cells_of.append([r * n + c for r in range(r0, r1) for c in range(c0, c1)])
    occupied = {cell for cells in cells_of for cell in cells}
    region = 0
    for start in sorted(occupied):
        if label[start] >= 0:
            continue
        stack = [start]
        label[start] = region
        while stack:
            cell = stack.pop()
            r, c = divmod(cell, n)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                k = nr * n + nc
                if 0 <= nr < n and 0 <= nc < n and k in occupied and label[k] < 0:
                    label[k] = region
                    stack.append(k)
        region += 1
    merged: dict[int, list[float]] = {}
    for (x0, t, x1, b), cells in zip(boxes, cells_of):
        if not cells:
            continue
        m = merged.setdefault(label[cells[0]], [x0, t, x1, b])
        m[0], m[1], m[2], m[3] = min(m[0], x0), min(m[1], t), max(m[2], x1), max(m[3], b)
    return [tuple(v) for _, v in sorted(merged.items())]  # type: ignore[misc]


_TRIAGE_CACHE: dict[tuple[str, int | None], dict] = {}


def pdf_triage(path: str, max_pages: int | None = None, pdf=None) -> dict:
    """Per-page evidence class for a PDF reference, before anything is mined from it.

    vector: real type (>= 4pt, a real font) that is not merely a frame around an image.
    vector_with_image: a vector page in a vector deck whose body is an image (a chart
      pasted as a picture): its text is evidence.
    raster_wrapper: an image is the page and the only real text lies outside it (browser
      chrome, a source stamp): nothing on the page is typography evidence.
    raster_ocr: the text layer is an OCR layer (GlyphLessFont or sub-2pt glyphs) over an
      image: words are content evidence, never sizes, faces or inks.
    raster_only: an image and no text at all.
    other_size: a page whose size differs from the deck's modal size (a filing cover, a
      memo bound in front of the deck): excluded.
    blank: no text and no image.
    """
    import pdfplumber  # optional dependency: only PDF references need it

    cache_key = (str(Path(path).resolve()), max_pages)
    if cache_key in _TRIAGE_CACHE:
        return _TRIAGE_CACHE[cache_key]
    if pdf is None:
        with pdfplumber.open(path) as handle:
            return pdf_triage(path, max_pages, handle)
    # an open handle is passed by fingerprint_pdf: pdfplumber caches each page's parsed
    # objects on it, so the triage and the reader parse every page once, not twice
    pages: list[dict] = []
    total = len(pdf.pages)
    for i, page in enumerate(pdf.pages):
        if max_pages is not None and i >= max_pages:
            break
        w, h = float(page.width), float(page.height)
        imgs = []
        src_px: dict[tuple[float, float, float, float], tuple[int, int]] = {}
        for im in page.images:
            x0, x1 = max(0.0, float(im["x0"])), min(w, float(im["x1"]))
            t, b = max(0.0, float(im["top"])), min(h, float(im["bottom"]))
            if x1 > x0 and b > t:
                imgs.append((x0, t, x1, b))
                size = im.get("srcsize")
                if size and len(size) == 2:
                    src_px[(x0, t, x1, b)] = (int(size[0]), int(size[1]))
        cover = _union_cover(imgs, w, h)
        chars = page.chars
        real = 0
        ocr = 0
        inside = 0
        for ch in chars:
            if not str(ch.get("text", "")).strip():
                continue
            size = float(ch.get("size", 0) or 0)
            font = str(ch.get("fontname", "") or "")
            if "GlyphLessFont" in font or size < 2.0:
                ocr += 1
                continue
            if size < PDF_TRIAGE_MIN_TEXT_PT:
                continue
            real += 1
            cx, cy = float(ch.get("x0", 0)), float(ch.get("top", 0))
            if any(x0 <= cx <= x1 and t <= cy <= b for x0, t, x1, b in imgs):
                inside += 1
        seen = real + ocr
        # the largest image is the slide when the page is a wrapper around one
        big = max(imgs, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if imgs else None
        if big is not None and (big[2] - big[0]) * (big[3] - big[1]) < 0.35 * w * h:
            # a scan tiled into strips (the UF McKinsey pages carry 8 images): the page is the slide
            big = (0.0, 0.0, w, h) if cover >= 0.9 else None
        text_digest = hashlib.sha256("".join(str(ch.get("text", "")) for ch in chars if str(ch.get("text", "")).strip()).encode()).hexdigest()[:16]
        if seen == 0:
            cls = "raster_only" if cover >= PDF_TRIAGE_IMAGE_COVER else "blank"
        elif ocr / seen >= 0.5 and cover >= PDF_TRIAGE_IMAGE_COVER:
            cls = "raster_ocr"
        elif cover >= PDF_TRIAGE_IMAGE_COVER and real and inside / real < 0.2:
            # a slide-shaped page with a pasted chart image is a slide; a letter or A4 page
            # around an image is a print of a slide (every EDGAR wrapper in the corpus is
            # 612x792 or 792x612, every pasted-image slide page is 4:3 or 16:9)
            cls = "vector_with_image" if _slide_shaped(w, h) else "raster_wrapper"
        else:
            cls = "vector"
        px = src_px.get(big) if big else None
        eff_dpi = round(px[0] / ((big[2] - big[0]) / 72.0)) if (px and big and big[2] > big[0]) else None
        pages.append({"page": i + 1, "width_pt": round(w, 1), "height_pt": round(h, 1), "chars_real": real, "chars_ocr": ocr,
                      "in_image_share": round(inside / real, 3) if real else None, "image_cover": round(cover, 3), "class": cls,
                      "slide_box_pt": [round(v, 1) for v in big] if big else None, "image_px": list(px) if px else None,
                      "effective_dpi": eff_dpi, "text_digest": text_digest})
    # deck-level rules, in order: modal page size; a stamp repeated on image pages; wrapper vs pasted image
    sizes = Counter((p["width_pt"], p["height_pt"]) for p in pages)
    modal = sizes.most_common(1)[0][0] if sizes else None
    for p in pages:
        if modal and (p["width_pt"], p["height_pt"]) != modal and p["class"] in ("vector", "blank", "raster_wrapper"):
            p["class"] = "other_size"
    digests = Counter(p["text_digest"] for p in pages if p["class"] == "vector" and p["image_cover"] >= 0.9)
    for p in pages:  # the same text on half the image pages is a stamp (a source line), not a slide
        if p["class"] == "vector" and p["image_cover"] >= 0.9 and digests[p["text_digest"]] >= max(2, 0.5 * len(pages)):
            p["class"] = "raster_wrapper"
    # a filing with the deck bound in: the slide images are landscape, the running text
    # around them is portrait (BMO: 139 letter-portrait pages of filing prose beside 104
    # landscape slide images). A vector page whose orientation differs from the slide box
    # the wrappers carry is filing text, not deck evidence, and it does not vote below.
    wrapper_boxes = [p["slide_box_pt"] for p in pages if p["class"] == "raster_wrapper" and p.get("slide_box_pt")]
    if wrapper_boxes:
        bw = Counter((b[2] - b[0]) >= (b[3] - b[1]) for b in wrapper_boxes).most_common(1)[0][0]
        for p in pages:
            if p["class"] == "vector" and ((p["width_pt"] >= p["height_pt"]) != bw):
                p["class"] = "filing_text"
    vector = sum(1 for p in pages if p["class"] == "vector")
    wrappers = [p for p in pages if p["class"] == "raster_wrapper"]
    if vector > len(wrappers):
        for p in wrappers:  # a letter-size vector deck with one pasted image page: still the house
            p["class"] = "vector_with_image"
    counts = Counter(p["class"] for p in pages)
    evidence = [p["page"] for p in pages if p["class"] in ("vector", "vector_with_image")]
    raster_pages = [p for p in pages if p["class"] in ("raster_only", "raster_ocr", "raster_wrapper")]
    # vector pages above a small count are mined whatever the raster share: the UF McKinsey
    # set carries 237 vector slides behind 283 scanned ones
    if not pages:
        deck_class = "empty"
    elif len(evidence) >= max(3, 0.1 * len(pages)) and not raster_pages:
        deck_class = "vector"
    elif len(evidence) >= max(3, 0.1 * len(pages)):
        deck_class = "mixed"
    elif raster_pages:
        deck_class = "raster"
    elif evidence:
        deck_class = "vector"
    else:
        deck_class = "empty"
    # the slide box of a raster deck: the modal largest-image box (wrapper) or the page (raster_only)
    slide_box = None
    if raster_pages:
        boxes = Counter(tuple(p["slide_box_pt"]) for p in raster_pages if p["slide_box_pt"])
        slide_box = list(boxes.most_common(1)[0][0]) if boxes else None
    # a print scales the slide: a 4:3 box is read as a 10 x 7.5 in slide, 16:9 as 13.333 x 7.5,
    # 16:10 as 10 x 6.25, and the scale is reported so sizes read off the pixels can be undone
    slide_size_in = None
    print_scale = None
    size_basis = None
    if slide_box:
        bw, bh = (slide_box[2] - slide_box[0]) / 72.0, (slide_box[3] - slide_box[1]) / 72.0
        # a letter- or A4-ratio box is a deck printed to paper before it was scanned: the
        # paper size is the only size the pixels can vouch for
        for ratio, size, basis in ((4 / 3, (10.0, 7.5), "4:3 slide"), (16 / 9, (13.333, 7.5), "16:9 slide"), (16 / 10, (10.0, 6.25), "16:10 slide"),
                                   (11 / 8.5, (11.0, 8.5), "letter print"), (297 / 210, (11.693, 8.268), "A4 print")):
            if bh > 0 and abs(bw / bh - ratio) / ratio <= 0.015:
                slide_size_in = list(size)
                print_scale = round(bw / size[0], 3)
                size_basis = basis
                break
        if slide_size_in is None:
            slide_size_in = [round(bw, 3), round(bh, 3)]
            print_scale = 1.0
            size_basis = "image box as printed"
    dpis = [p["effective_dpi"] for p in raster_pages if p.get("effective_dpi")]
    result = {"file": path, "pages_total": total, "pages_triaged": len(pages), "modal_page_pt": list(modal) if modal else None,
              "counts": dict(counts), "deck_class": deck_class, "evidence_pages": evidence,
              "raster_pages": [p["page"] for p in raster_pages], "slide_box_pt": slide_box, "slide_size_in": slide_size_in,
              "size_basis": size_basis, "print_scale": print_scale, "effective_dpi": (sorted(dpis)[len(dpis) // 2] if dpis else None), "pages": pages}
    _TRIAGE_CACHE[cache_key] = result
    return result


# --- pdf text: glyphs -> line segments -> blocks of paragraphs -------------------------

PDF_COLUMN_GAP_ADVANCES = 3.0
"""A gap wider than three average character advances on one baseline is a column break: a
source line and a footer on one baseline are two lines, not one."""
PDF_WORD_GAP_EM = 0.2
PDF_BLOCK_GAP_EM = 1.0
PDF_PARAGRAPH_GAP_EM = 0.5
PDF_BLOCK_SIZE_RATIO = 1.25
PDF_INDENT_EM = 4.0
"""The five grouping thresholds above are ASSERTED (a word space, a blank line, half a
line of paragraph spacing, a size step past the 1.10 level ratio, a four-em hanging
indent), then checked on the one reference this repo holds as both pptx and PDF (jazz,
20 slides, 2026-10-20): 192 blocks against the pptx's 149 text shapes (median 1.29 per
slide: the house name the pptx keeps on its layout is one more block on every PDF page,
and a table's cells are blocks, slide 19 reads 17 against 3), 1,326 words against 1,263
(pdfplumber's own word split reads 1,369), 191 paragraphs against 198. Not tuned to that
deck."""
QUARTER_TURN_TOLERANCE = 0.02
"""A glyph matrix whose off-axis terms are under 2% of its scale is upright or a quarter
turn; anything else (skewed, arbitrary angle) has no axis to read a size along."""
BULLET_GLYPHS = frozenset("\u2022\u25e6\u25aa\u25ab\u25a0\u25a1\u25cf\u25cb\u2023\u2043\u2013\u2014\u00bb\u203a\u27a2\u27a4\u2713\u2714\u00b7-*>")
MID_LINE_PUNCTUATION = frozenset("-*>\u2013\u2014\u00b7\u00bb\u203a")
"""Bullet glyphs that also sit inside sentences ("3/16 - 4/19"): they open an item only at
the start of a line."""
SYMBOL_FACES = ("wingdings", "symbol", "zapf", "webdings", "dingbats")


@dataclass
class _Glyph:
    text: str
    family: str | None
    bold: bool
    italic: bool
    color: str | None
    em: float  # the type size: the glyph's extent across its own baseline
    u0: float  # along the line, in reading order
    u1: float
    v0: float  # across the line, increasing from one line to the next
    v1: float
    paint: int = 0  # the glyph's place in the page's content stream

    @property
    def space(self) -> bool:
        return not self.text.strip()


@dataclass
class _Segment:
    direction: str
    glyphs: list[_Glyph]
    bullet: _Glyph | None = None
    ground: int = -1  # the smallest filled rectangle under the line (-1: the page itself)

    @property
    def ink(self) -> list[_Glyph]:
        return [g for g in self.glyphs if not g.space]

    @property
    def u0(self) -> float:
        return min(g.u0 for g in self.ink)

    @property
    def u1(self) -> float:
        return max(g.u1 for g in self.ink)

    @property
    def v0(self) -> float:
        return min(g.v0 for g in self.ink)

    @property
    def v1(self) -> float:
        return max(g.v1 for g in self.ink)

    @property
    def em(self) -> float:
        sizes = Counter(round(g.em * 2) / 2 for g in self.ink)
        return sizes.most_common(1)[0][0]

    @property
    def lead_u0(self) -> float:
        return self.bullet.u0 if self.bullet is not None else self.u0

    def style(self) -> tuple[float, bool]:
        ink = self.ink
        return self.em, all(g.bold for g in ink)


def _pdf_glyph(ch: dict, w: float, h: float, painted: dict[tuple, int] | None = None) -> tuple[str, _Glyph] | None:
    """(direction, glyph), or None for a glyph set at an angle no type size can be read
    along. pdfplumber's `size` is the glyph box's height on the page, which is the type
    size only for upright text: a quarter-turned glyph's height is its advance (bcg's
    rotated copyright line read as 2 to 4pt one glyph at a time), and its size is the box
    width."""
    matrix = ch.get("matrix") or (1, 0, 0, 1, 0, 0)
    a, b, c, d = (float(v) for v in matrix[:4])
    scale = max(math.hypot(a, b), math.hypot(c, d))
    if scale <= 0:
        return None
    tol = QUARTER_TURN_TOLERANCE * scale
    x0, x1, top, bottom = float(ch["x0"]), float(ch["x1"]), float(ch["top"]), float(ch["bottom"])
    family, bold = _pdf_family(ch.get("fontname"))
    name = str(ch.get("fontname") or "").lower()
    italic = "italic" in name or "oblique" in name
    color = _pdf_color(ch.get("non_stroking_color"))
    text = str(ch.get("text", ""))
    paint = (painted or {}).get(_pdf_key(ch), 0)
    if abs(b) <= tol and abs(c) <= tol and a > 0 and d > 0:
        return "ltr", _Glyph(text, family, bold, italic, color, float(ch.get("size", bottom - top)), x0, x1, top, bottom, paint)
    if abs(a) <= tol and abs(d) <= tol:
        if b > 0:  # the baseline runs up the page: lines follow one another to the right
            return "btt", _Glyph(text, family, bold, italic, color, x1 - x0, h - bottom, h - top, x0, x1, paint)
        return "ttb", _Glyph(text, family, bold, italic, color, x1 - x0, top, bottom, w - x1, w - x0, paint)
    return None


def _pdf_segments(direction: str, glyphs: list[_Glyph]) -> list[_Segment]:
    """Glyphs sharing a baseline band, in reading order, cut at column gaps. A glyph joins
    the line whose tallest glyph's band holds its centre, so a superscript or a larger
    first word stays on its line."""
    lines: list[list[_Glyph]] = []
    band: tuple[float, float, float] | None = None  # v0, v1, em of the line's tallest glyph
    for g in sorted((g for g in glyphs if not g.space), key=lambda g: ((g.v0 + g.v1) / 2, g.u0)):
        mid = (g.v0 + g.v1) / 2
        if band is not None and band[0] <= mid <= band[1]:
            lines[-1].append(g)
            if g.em > band[2]:
                band = (g.v0, g.v1, g.em)
        else:
            lines.append([g])
            band = (g.v0, g.v1, g.em)
    spaces = sorted((g for g in glyphs if g.space), key=lambda g: g.u0)
    out: list[_Segment] = []
    for line in lines:
        line.sort(key=lambda g: g.u0)
        lv0, lv1 = min(g.v0 for g in line), max(g.v1 for g in line)
        segs: list[list[_Glyph]] = [[line[0]]]
        for k, (prev, g) in enumerate(zip(line, line[1:]), 1):
            seg = segs[-1]
            adv = (seg[-1].u1 - seg[0].u0) / len(seg)
            gap = g.u0 - prev.u1
            # a bullet after a word space opens the next column's item ("Disciplined process
            # . For each initiative" on bain p135 is a row label beside a bullet list)
            nxt = line[k + 1] if k + 1 < len(line) else None
            bullet_mid = (g.text in BULLET_GLYPHS and nxt is not None and gap > PDF_WORD_GAP_EM * min(g.em, prev.em)
                          and nxt.u0 - g.u1 > PDF_WORD_GAP_EM * min(g.em, nxt.em) and g.text not in MID_LINE_PUNCTUATION)
            if gap > PDF_COLUMN_GAP_ADVANCES * max(adv, 2.0) or bullet_mid:
                segs.append([g])
            else:
                seg.append(g)
        for seg in segs:
            s0, s1 = seg[0].u0, seg[-1].u1
            # the file's own space glyphs inside the segment mark word breaks too
            inner = [sp for sp in spaces if s0 < (sp.u0 + sp.u1) / 2 < s1 and lv0 <= (sp.v0 + sp.v1) / 2 <= lv1]
            glyphs_in = sorted(seg + inner, key=lambda g: g.u0)
            segment = _Segment(direction, glyphs_in)
            first = segment.ink[0]
            rest = segment.ink[1:]
            symbol = (first.family or "").lower().startswith(SYMBOL_FACES)
            if rest and (first.text in BULLET_GLYPHS or symbol) and len(first.text) == 1:
                follows_gap = rest[0].u0 - first.u1 > PDF_WORD_GAP_EM * min(first.em, rest[0].em)
                if follows_gap or symbol:
                    segment.bullet = first
                    segment.glyphs = [x for x in glyphs_in if x is not first]
                    while segment.glyphs and segment.glyphs[0].space:
                        segment.glyphs.pop(0)
            out.append(segment)
    return out


def _segment_runs(seg: _Segment) -> list[dict]:
    """Consecutive glyphs of one face, weight, slant, size and ink, with word spaces put
    back where the file has a space glyph or a gap wider than PDF_WORD_GAP_EM."""
    runs: list[dict] = []
    prev: _Glyph | None = None
    pending = False
    for g in seg.glyphs:
        if g.space:
            pending = prev is not None
            continue
        gap = prev is not None and g.u0 - prev.u1 > PDF_WORD_GAP_EM * min(g.em, prev.em)
        key = (g.family, g.bold, g.italic, round(g.em * 2) / 2, g.color)
        sep = " " if (pending or gap) else ""
        if runs and runs[-1]["key"] == key:
            runs[-1]["text"] += sep + g.text
            runs[-1]["ext"] = _union_ext(runs[-1]["ext"], (g.u0, g.v0, g.u1, g.v1))
        else:
            if runs and sep:
                runs[-1]["text"] += sep
            runs.append({"key": key, "text": g.text, "ext": (g.u0, g.v0, g.u1, g.v1)})
        prev, pending = g, False
    return runs


def _union_ext(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Two (u0, v0, u1, v1) extents in a line's own frame, as one."""
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _page_box(direction: str, ext: tuple[float, float, float, float], w: float, h: float) -> tuple[float, float, float, float]:
    """A (u0, v0, u1, v1) extent in a line's own frame as the (x, y, width, height) it covers
    on the page, in points: _pdf_glyph's frames turned back."""
    u0, v0, u1, v1 = ext
    if direction == "ltr":
        return u0, v0, u1 - u0, v1 - v0
    if direction == "btt":
        return v0, h - u1, v1 - v0, u1 - u0
    return w - v1, u0, v1 - v0, u1 - u0


def _pdf_blocks(segments: list[_Segment]) -> list[list[_Segment]]:
    """Line segments stacked into text blocks, the PDF's stand-in for a text box: the next
    line of a block lies within PDF_BLOCK_GAP_EM of the line above, overlaps it across the
    page, shares its left edge (or its centre, or its right edge), and is set at a size
    within PDF_BLOCK_SIZE_RATIO."""
    blocks: list[list[_Segment]] = []
    for s in sorted(segments, key=lambda s: (s.direction, s.v0, s.lead_u0)):
        best: tuple[float, list[_Segment]] | None = None
        for blk in blocks:
            last = blk[-1]
            if last.direction != s.direction or last.ground != s.ground:  # a fill edge between two lines parts two boxes
                continue
            em = min(last.em, s.em)
            gap = s.v0 - last.v1
            if gap < -0.5 * em or gap > PDF_BLOCK_GAP_EM * em:
                continue
            if max(last.em, s.em) > PDF_BLOCK_SIZE_RATIO * em:
                continue
            if min(last.u1, s.u1) <= max(last.lead_u0, s.lead_u0):
                continue
            left = min(x.lead_u0 for x in blk)
            aligned = (left - em <= s.lead_u0 <= left + PDF_INDENT_EM * em
                       or abs((s.u0 + s.u1) / 2 - (last.u0 + last.u1) / 2) <= em or abs(s.u1 - last.u1) <= em)
            if aligned and (best is None or gap < best[0]):
                best = (gap, blk)
        if best is None:
            blocks.append([s])
        else:
            best[1].append(s)
    return blocks


def _block_paragraphs(blk: list[_Segment]) -> list[dict]:
    """A block's lines joined into paragraphs: a bullet, a change of size or of whole-line
    weight, or a gap wider than PDF_PARAGRAPH_GAP_EM starts a new one; a wrapped line does
    not. Alignment is read off the lines' edges, and is unknown ("?") for a one-line block."""
    groups: list[list[_Segment]] = []
    for k, s in enumerate(blk):
        if k == 0:
            groups.append([s])
            continue
        prev = blk[k - 1]
        gap = s.v0 - prev.v1
        head = groups[-1][0]
        # a line hanging under a bullet's text continues that item whatever its weight
        # ("Senior-level leadership ... are / critical for driving action", bain p135)
        hanging = head.bullet is not None and abs(s.u0 - head.u0) <= 0.5 * s.em and s.em == prev.em
        restyled = s.style() != prev.style() and not hanging
        if s.bullet is not None or restyled or gap > PDF_PARAGRAPH_GAP_EM * min(s.em, prev.em):
            groups.append([s])
        else:
            groups[-1].append(s)
    left, right = min(s.u0 for s in blk), max(s.u1 for s in blk)
    bullet_lefts: list[float] = []
    for s in blk:
        if s.bullet is not None and not any(abs(s.bullet.u0 - b) <= 0.5 * s.em for b in bullet_lefts):
            bullet_lefts.append(s.bullet.u0)
    bullet_lefts.sort()
    paras = []
    for group in groups:
        em = group[0].em
        tol = 0.5 * em
        if len(blk) == 1:
            align = "?"
        elif group[0].bullet is not None and len(group) == 1:
            align = "l"  # a bullet hangs from the left edge whatever its line's length
        elif len(group) == 1:
            s = group[0]
            align = ("l" if abs(s.u0 - left) <= tol else "r" if abs(s.u1 - right) <= tol
                     else "ctr" if abs((s.u0 + s.u1) / 2 - (left + right) / 2) <= tol else "l")
        else:
            g0 = group[0]
            same_left = all(abs(s.u0 - g0.u0) <= tol for s in group[1:])
            full_right = all(abs(s.u1 - g0.u1) <= tol for s in group[1:-1]) and len(group) > 2
            same_right = all(abs(s.u1 - g0.u1) <= tol for s in group[1:])
            same_mid = all(abs((s.u0 + s.u1) / 2 - (g0.u0 + g0.u1) / 2) <= tol for s in group[1:])
            align = ("just" if same_left and full_right and not same_right else "l" if same_left else "r" if same_right
                     else "ctr" if same_mid else "l")
        runs: list[dict] = []
        for li, s in enumerate(group):
            for ri, r in enumerate(_segment_runs(s)):
                if li and not ri and runs and not runs[-1]["text"].endswith(" "):
                    runs[-1]["text"] += " "  # a wrapped line ends a word
                if runs and runs[-1]["key"] == r["key"]:
                    runs[-1]["text"] += r["text"]
                    runs[-1]["ext"] = _union_ext(runs[-1]["ext"], r["ext"])
                else:
                    runs.append(r)
        bullet = group[0].bullet
        level = next((i for i, b in enumerate(bullet_lefts) if abs(bullet.u0 - b) <= 0.5 * em), 0) if bullet is not None else 0
        # the indents a pptx declares, measured: marL is the text's distance from the block's
        # left edge, and the (negative) indent puts the bullet back where it was drawn
        block_left = min(s.lead_u0 for s in blk)
        mar_l = round((group[0].u0 - block_left) * EMU_PER_PT) if bullet is not None else 0
        indent = round((bullet.u0 - group[0].u0) * EMU_PER_PT) if bullet is not None else None
        paras.append({"level": level, "bullet": f"char:{bullet.text}" if bullet is not None else "none", "align": align, "mar_l_emu": mar_l,
                      "indent_emu": indent,
                      # a symbol face whose glyph the file maps to a Unicode bullet: the Unicode
                      # is the meaning, and Wingdings has no glyph at U+2022 to draw it with
                      "bullet_font": (None if bullet is None or ((bullet.family or "").lower().startswith(SYMBOL_FACES) and ord(bullet.text) < 0xE000)
                                      else bullet.family),
                      "runs": [{"text": r["text"].rstrip() if i == len(runs) - 1 else r["text"], "size_pt": r["key"][3], "bold": r["key"][1],
                                "italic": r["key"][2], "color": r["key"][4], "caps": False, "family": r["key"][0], "ext": r["ext"]}
                               for i, r in enumerate(runs)]})
    return paras


def _block_box(blk: list[_Segment], w: float, h: float) -> tuple[tuple[float, float, float, float], int]:
    """(x, y, width, height) in points before rotation, and the OOXML rotation in 60000ths."""
    u0, u1 = min(s.u0 if s.bullet is None else s.bullet.u0 for s in blk), max(s.u1 for s in blk)
    v0, v1 = min(s.v0 for s in blk), max(s.v1 for s in blk)
    direction = blk[0].direction
    if direction == "ltr":
        return (u0, v0, u1 - u0, v1 - v0), 0
    # visual box on the page, then the unrotated box about the same centre
    if direction == "btt":
        vx0, vx1, vy0, vy1 = v0, v1, h - u1, h - u0
        rotation = 16_200_000
    else:
        vx0, vx1, vy0, vy1 = w - v1, w - v0, u0, u1
        rotation = 5_400_000
    cx, cy = (vx0 + vx1) / 2, (vy0 + vy1) / 2
    bw, bh = u1 - u0, v1 - v0
    return (cx - bw / 2, cy - bh / 2, bw, bh), rotation


def _block_style(blk: list[_Segment]) -> dict:
    """Modal family, size, ink and weight of a block's glyphs: the style a chrome entry
    draws its text in."""
    ink = [g for s in blk for g in s.ink]

    def modal(values: list) -> object:
        return Counter(values).most_common(1)[0][0]

    return {"family": modal([g.family for g in ink]), "size_pt": modal([round(g.em * 2) / 2 for g in ink]),
            "ink_hex": modal([g.color for g in ink]), "bold": modal([g.bold for g in ink])}


def _pdf_text(page, sp: SlidePrint, scale: float, painted: dict[tuple, int] | None = None) -> None:
    """Runs and text blocks of one page: the PDF's runs carry their words and text, and
    one block is one element, as one text box is in a pptx. `painted` maps a glyph to its
    place in the content stream, so a block paints when its first glyph does."""
    w, h = float(page.width), float(page.height)
    by_dir: dict[str, list[_Glyph]] = {}
    unread = 0
    for ch in page.chars:
        got = _pdf_glyph(ch, w, h, painted)
        if got is None:
            unread += 1 if str(ch.get("text", "")).strip() else 0
            continue
        by_dir.setdefault(got[0], []).append(got[1])
    sp.unread_glyphs = unread
    segments = [s for direction, glyphs in sorted(by_dir.items()) for s in _pdf_segments(direction, glyphs) if s.ink]
    grounds = sorted(((float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"])) for r in page.rects
                      if r.get("fill") and float(r.get("width", 0)) > 2.0 and float(r.get("height", 0)) > 2.0
                      and float(r.get("width", 0)) * float(r.get("height", 0)) < 0.98 * w * h),
                     key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    for s in segments:
        mu, mv = (s.u0 + s.u1) / 2, (s.v0 + s.v1) / 2
        cx, cy = {"ltr": (mu, mv), "btt": (mv, h - mu), "ttb": (w - mv, mu)}[s.direction]
        s.ground = next((k for k, (x0, t, x1, b) in enumerate(grounds) if x0 <= cx <= x1 and t <= cy <= b), -1)
    surface = f"page{sp.index + 1}"
    for bi, blk in enumerate(_pdf_blocks(segments)):
        ref = f"t{bi}"
        paras = _block_paragraphs(blk)
        (x, y, bw, bh), rotation = _block_box(blk, w, h)
        chars = 0
        for pi, para in enumerate(paras):
            bullet = para["bullet"]
            for ri, r in enumerate(para["runs"]):
                n = sum(1 for c in r["text"] if not c.isspace())
                chars += n
                sp.runs.append(Run(n, r["family"], r["size_pt"], r["bold"], r["color"], para["align"], "none", surface=surface,
                                   ref=f"{ref}/p[{pi}]/r[{ri}]", level=para["level"], italic=r["italic"],
                                   bullet="char" if bullet.startswith("char:") else "none", text_sample=r["text"].strip()[:40],
                                   words=len(r["text"].split()), bullet_glyph=bullet[5:] if bullet.startswith("char:") else None,
                                   bullet_font=para["bullet_font"], text=r["text"],
                                   mar_l_emu=para["mar_l_emu"] if bullet.startswith("char:") else None, indent_emu=para["indent_emu"],
                                   box=tuple(int(v * scale) for v in _page_box(blk[0].direction, r["ext"], w, h))))  # type: ignore[arg-type]
        text = " ".join("".join(r["text"] for r in p["runs"]) for p in paras)
        sp.shapes.append(Shape("text_box", (int(x * scale), int(y * scale), int(bw * scale), int(bh * scale)), None, None, None, None, False,
                               None, "slide", ref=ref, rotation=rotation, text_chars=chars, text=text[:80], paragraphs=paras,
                               paint_order=min(g.paint for s in blk for g in s.ink), line_style=_block_style(blk), drawn_lines=len(blk)))


RECURRENCE_FLOOR = 0.5
"""A position or a text is the deck's own when it recurs on at least half its pages
(deckgen tokens.py:5754, MOTIF_RECURRENCE_FLOOR there; extract_style.py reads it from here)."""
TITLE_SLOT_DEPTH = 3
"""How many of a page's topmost text blocks may be its title: a disclaimer line or a
section tag above the title (bcg pages 20 and 30) pushes it to second place."""


def _pdf_title_slot(prints: list[SlidePrint]) -> dict:
    """Mark the title of each page from position evidence, the only evidence a PDF has
    for it. The TITLE_SLOT_DEPTH topmost text blocks of a page are candidates (text
    repeated on half the pages is chrome and a bare number is a page number: neither is
    one). Candidates share a slot when their left edges, and their top or bottom edges,
    lie within the smaller of their type sizes of each other; a slot holding a candidate on at
    least RECURRENCE_FLOOR of the pages recurs, and the topmost recurring slot holds the
    titles. Size plays no part, so a large numeral never outvotes the page titles. With no
    recurring slot nothing is marked, and type.title stays open for completion."""
    pages = [sp for sp in prints if sp.page_class in ("vector", "vector_with_image")]
    repeated = Counter(t for sp in pages for t in {sh.text for sh in sp.shapes if sh.kind == "text_box" and sh.text})
    chrome_text = {t for t, n in repeated.items() if n >= max(2, RECURRENCE_FLOOR * len(pages))}
    candidates: list[tuple[SlidePrint, Shape, float]] = []
    for sp in pages:
        blocks = [sh for sh in sp.shapes if sh.kind == "text_box" and not sh.rotation and sh.box and sh.paragraphs
                  and sh.text not in chrome_text and not re.fullmatch(r"\d+", (sh.text or "").strip())]
        for sh in sorted(blocks, key=lambda sh: (sh.box[1], sh.box[0]))[:TITLE_SLOT_DEPTH]:  # type: ignore[index]
            candidates.append((sp, sh, float(sh.paragraphs[0]["runs"][0]["size_pt"]) * EMU_PER_PT))  # type: ignore[index]

    def same_slot(a: Shape, b: Shape, em: float) -> bool:
        ax, ay, _, ah = a.box  # type: ignore[misc]
        bx, by, _, bh = b.box  # type: ignore[misc]
        return abs(ax - bx) <= em and (abs(ay - by) <= em or abs((ay + ah) - (by + bh)) <= em)

    need = max(2, RECURRENCE_FLOOR * len(pages))
    best: list[tuple[SlidePrint, Shape]] = []
    best_top = math.inf
    for _, shape, em in candidates:
        members: dict[int, tuple[SlidePrint, Shape]] = {}
        for sp, sh, em2 in candidates:
            if same_slot(shape, sh, min(em, em2)) and (sp.index not in members or sh.box[1] < members[sp.index][1].box[1]):  # type: ignore[index]
                members[sp.index] = (sp, sh)  # one title per page: the slot's topmost block on it
        if len(members) < need:
            continue
        tops = sorted(sh.box[1] for _, sh in members.values())  # type: ignore[index]
        median_top = tops[len(tops) // 2]
        if median_top < best_top or (median_top == best_top and len(members) > len(best)):
            best, best_top = list(members.values()), median_top
    if not best:
        return {"pages": len(pages), "candidates": len(candidates), "needed": need, "marked": 0}
    for sp, sh in best:
        sh.ph_type = "title"
        for r in sp.runs:
            if r.ref.startswith(sh.ref + "/"):
                r.ph_class = "title"
    return {"pages": len(pages), "candidates": len(candidates), "needed": need, "marked": len(best)}


PDF_PROGRESS_EVERY = 50  # pages between progress lines on stderr; a 205-page reference reads for about half a minute


def _pdf_box(o: dict, scale: float) -> tuple[int, int, int, int]:
    return (int(float(o["x0"]) * scale), int(float(o["top"]) * scale),
            int((float(o["x1"]) - float(o["x0"])) * scale), int((float(o["bottom"]) - float(o["top"])) * scale))


def fingerprint_pdf(path: str, max_pages: int | None = None) -> list[SlidePrint]:
    import pdfplumber  # optional dependency: only PDF references need it

    name = Path(path).stem
    out: list[SlidePrint] = []
    with pdfplumber.open(path) as pdf:
        triage = pdf_triage(path, max_pages, pdf)
        total = triage["pages_triaged"]
        for i, page in enumerate(pdf.pages):
            if max_pages is not None and i >= max_pages:
                break
            if total > PDF_PROGRESS_EVERY and i % PDF_PROGRESS_EVERY == 0:
                print(f"ooxml: reading page {i + 1} of {total}", file=sys.stderr, flush=True)
            w, h = float(page.width), float(page.height)
            scale = 12700.0  # pt -> EMU so margins and areas share the pptx arithmetic
            # content-stream order is paint order: a later object paints over an earlier one
            painted: dict[tuple, int] = {}
            for order, obj in enumerate(page.iter_layout_objects(page.layout._objs)):
                painted.setdefault(_pdf_key(obj), order)
            try:
                page = page.dedupe_chars(tolerance=1)  # overprinted glyphs (fake bold) otherwise read twice
            except Exception:  # noqa: BLE001 - older pdfplumber
                pass
            sp = SlidePrint(name, i, int(w * scale), int(h * scale), None, source="pdf")
            if i < len(triage["pages"]):
                sp.page_class = triage["pages"][i]["class"]
                sp.image_cover = triage["pages"][i]["image_cover"]
            _pdf_text(page, sp, scale, painted)
            page_area = w * h

            for im in page.images:
                try:
                    sp.pdf_fills.append((_pdf_box(im, scale), None))
                except (KeyError, TypeError, ValueError):
                    sp.pdf_fills.append(((0, 0, int(w * scale), int(h * scale)), None))  # an image with no extent may lie anywhere
            for obj in list(page.rects) + list(page.curves):
                if obj.get("fill"):
                    try:
                        sp.pdf_fills.append((_pdf_box(obj, scale), _pdf_color(obj.get("non_stroking_color"))))
                    except (KeyError, TypeError, ValueError):
                        continue
            for k, rect in enumerate(page.rects):
                rw, rh = float(rect.get("width", 0)), float(rect.get("height", 0))
                if rw <= 0 or rh <= 0:
                    continue
                fill = _pdf_color(rect.get("non_stroking_color")) if rect.get("fill") else None
                stroke = _pdf_color(rect.get("stroking_color")) if rect.get("stroke") else None
                box = (int(float(rect["x0"]) * scale), int(float(rect["top"]) * scale), int(rw * scale), int(rh * scale))
                if fill and rw * rh >= 0.98 * page_area:
                    sp.background = fill
                    continue
                thin = min(rw, rh) <= 2.0
                lw = float(rect.get("linewidth") or 0) if stroke else None
                sp.shapes.append(Shape("line" if thin else "shape", box, None if thin else fill,
                                       (fill if thin and fill else stroke), int((lw if lw else min(rw, rh)) * scale) if (thin or stroke) else None,
                                       None, False, None, "slide", ref=f"r{k}", paint_order=painted.get(_pdf_key(rect), 0)))
            for k, line in enumerate(page.lines):
                lw = float(line.get("linewidth") or 1.0)
                color = _pdf_color(line.get("stroking_color"))
                box = (int(float(line["x0"]) * scale), int(float(line["top"]) * scale),
                       int(max(1.0, float(line["x1"]) - float(line["x0"])) * scale), int(max(lw, float(line["bottom"]) - float(line["top"])) * scale))
                sp.shapes.append(Shape("line", box, None, color, int(lw * scale), None, False, None, "slide", ref=f"l{k}",
                                       paint_order=painted.get(_pdf_key(line), 0)))
            boxes = []
            orders = []
            for im in page.images:
                x0, x1 = max(0.0, float(im["x0"])), min(w, float(im["x1"]))
                t, b = max(0.0, float(im["top"])), min(h, float(im["bottom"]))
                # an image under the whole page is its ground, as a page-sized rect is
                if x1 > x0 and b > t and (x1 - x0) * (b - t) < 0.98 * page_area:
                    boxes.append((x0, t, x1, b))
                    orders.append(painted.get(_pdf_key(im), 0))
            for k, (x0, t, x1, b) in enumerate(_image_regions(boxes, w, h)):
                # a region paints when its first member does
                first = min((o for (bx0, bt, bx1, bb), o in zip(boxes, orders) if x0 <= (bx0 + bx1) / 2 <= x1 and t <= (bt + bb) / 2 <= b), default=0)
                sp.shapes.append(Shape("picture", (int(x0 * scale), int(t * scale), int((x1 - x0) * scale), int((b - t) * scale)),
                                       None, None, None, None, False, None, "slide", ref=f"img{k}", paint_order=first))
            if sp.background is None:
                sp.background = "FFFFFF"
            out.append(sp)
    triage["title_slot"] = _pdf_title_slot(out)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "triage":
        with open(argv[1], "rb") as fh:
            if fh.read(5) != b"%PDF-":
                print(f"triage: {argv[1]} is not a PDF (no %PDF- header); a .pptx needs no triage: run extract_style.py on it", file=sys.stderr)
                return 2
        max_pages = int(argv[2]) if len(argv) > 2 else None
        print(json.dumps(pdf_triage(argv[1], max_pages), indent=1))
        return 0
    slides = fingerprint_deck(argv[0])
    print(json.dumps([asdict(s) for s in slides], indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
