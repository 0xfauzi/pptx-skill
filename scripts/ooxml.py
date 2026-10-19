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
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lxml import etree

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

DEFAULT_CLR_MAP = {
    "bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2",
    "accent1": "accent1", "accent2": "accent2", "accent3": "accent3",
    "accent4": "accent4", "accent5": "accent5", "accent6": "accent6",
    "hlink": "hlink", "folHlink": "folHlink",
}
TITLE_TYPES = {"title", "ctrTitle"}
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
        self._table_styles: dict[str, etree._Element] | None = None

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
                   sink: list[Run], surface: str, ref: str, own_layer: str, row_class: str | None = None) -> int:
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
            ri = 0
            for r in para:
                if _local(r) not in ("r", "fld"):
                    continue
                t = r.find(_a("t"))
                text = (t.text or "") if t is not None else ""
                if not text.strip():
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
                if color is None:
                    color = self.chain.tx1()
                    color_layer = "theme"
                chars = len(text.strip())
                total_chars += chars
                sink.append(Run(
                    chars=chars, family=face,
                    size_pt=float(size) if isinstance(size, (int, float)) else DEFAULT_SIZE_PT,
                    bold=bool(bold), color=color, align=str(align), ph_class=cls,
                    surface=surface, ref=f"{ref}/p[{pi}]/r[{ri}]", level=level,
                    italic=bool(italic), caps=bool(caps),
                    size_layer=("autofit" if scaled else size_layer), face_layer=face_layer, color_layer=color_layer,
                    line_spacing=lnspc if isinstance(lnspc, float) else None,
                    space_before_pt=float(before), space_after_pt=float(after),
                    bullet=("char" if str(bullet).startswith("char:") else str(bullet)),
                    row_class=row_class, text_sample=text.strip()[:40],
                    words=len(text.split()), bullet_glyph=(str(bullet)[5:] if str(bullet).startswith("char:") else None),
                ))
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
                            if run.size_layer == "default" and run.color_layer == "theme":
                                c = self.chain.first_color(style_text.find(_a("fontRef")) if style_text.find(_a("fontRef")) is not None else None)
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
                rotation=xfrm_rotation(sp), dash=dash, in_group=transform is not None,
            )
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
                run_sink = self.print.runs if with_text else self.print.chrome_runs
                shape.text_chars = self._walk_text(tx, self._level_holders(sp, layer, ph), cls if with_text else "chrome",
                                                   ph[0] if ph else None, run_sink, surface, ref, layer)
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


def fingerprint_pdf(path: str, max_pages: int | None = None) -> list[SlidePrint]:
    import pdfplumber  # optional dependency: only PDF references need it

    name = Path(path).stem
    out: list[SlidePrint] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            if max_pages is not None and i >= max_pages:
                break
            w, h = float(page.width), float(page.height)
            scale = 12700.0  # pt -> EMU so margins and areas share the pptx arithmetic
            sp = SlidePrint(name, i, int(w * scale), int(h * scale), None, source="pdf")
            # runs: consecutive chars sharing font, size and colour on one line
            key = None
            buf = 0
            for ch in page.chars:
                if not str(ch.get("text", "")).strip():
                    continue
                family, bold = _pdf_family(ch.get("fontname"))
                k = (family, bold, round(float(ch.get("size", 0)) * 2) / 2, _pdf_color(ch.get("non_stroking_color")), round(float(ch.get("top", 0))))
                if k != key:
                    if key is not None and buf:
                        sp.runs.append(Run(buf, key[0], key[2], key[1], key[3], "?", "none"))
                    key, buf = k, 0
                buf += 1
            if key is not None and buf:
                sp.runs.append(Run(buf, key[0], key[2], key[1], key[3], "?", "none"))
            page_area = w * h
            for rect in page.rects:
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
                                       None, False, None, "slide"))
            for line in page.lines:
                lw = float(line.get("linewidth") or 1.0)
                color = _pdf_color(line.get("stroking_color"))
                box = (int(float(line["x0"]) * scale), int(float(line["top"]) * scale),
                       int(max(1.0, float(line["x1"]) - float(line["x0"])) * scale), int(max(lw, float(line["bottom"]) - float(line["top"])) * scale))
                sp.shapes.append(Shape("line", box, None, color, int(lw * scale), None, False, None, "slide"))
            if sp.background is None:
                sp.background = "FFFFFF"
            # text extents feed the margins: a PDF has no text boxes, so words stand in for them
            try:
                words = page.extract_words()
            except Exception:  # noqa: BLE001 - a malformed page still has rects
                words = []
            for wd in words:
                box = (int(float(wd["x0"]) * scale), int(float(wd["top"]) * scale),
                       int((float(wd["x1"]) - float(wd["x0"])) * scale), int((float(wd["bottom"]) - float(wd["top"])) * scale))
                sp.shapes.append(Shape("text_box", box, None, None, None, None, False, None, "slide"))
            out.append(sp)
    return out




def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    slides = fingerprint_deck(argv[0])
    print(json.dumps([asdict(s) for s in slides], indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
