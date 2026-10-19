#!/usr/bin/env python3
"""Style fingerprint of a .pptx, and the distance between fingerprints.

The outside judge for style adherence. It reads OOXML directly (zipfile + lxml,
nothing else) and resolves inherited text and shape properties through the
slide -> layout -> master -> theme chain, so a deck that declares Arial 12pt once
on its master and a deck that writes it on every run fingerprint the same.

    fingerprint.py print  deck.pptx                      # per-deck summary
    fingerprint.py compare cand.pptx --reference ref.pptx [--others a.pptx ...]
    fingerprint.py calibrate house1=a.pptx,b.pptx house2=c.pptx ...  [--json out]

`compare` prints every distance component, so a bad component names the defect
(sizes off the reference ladder, a colour outside the palette, margins wrong).
`calibrate` runs leave-one-slide-out and leave-one-deck-out 1-nearest-neighbour
over the houses given and prints accuracy against the binomial chance bound: it
is how the measure itself is checked before it judges anything.

Ported from deckgen's style walker (inheritance order, colour transforms) with
the port audit in ../PORT_AUDIT.md. No value in here is a design standard.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": A, "p": P, "r": R}

REL_LAYOUT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
REL_MASTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
REL_THEME = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"

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
MAX_ZIP_MEMBERS = 5000
MAX_MEMBER_BYTES = 64 * 1024 * 1024


def _a(tag: str) -> str:
    return f"{{{A}}}{tag}"


def _p(tag: str) -> str:
    return f"{{{P}}}{tag}"


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
    ph_class: str  # title | body | chrome | other | none


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


class Chain:
    """slide part -> layout part -> master part -> theme, with the colour map."""

    def __init__(self, pkg: Package, slide_part: str) -> None:
        self.pkg = pkg
        self.slide = slide_part
        self.layout = pkg.rel_target(slide_part, REL_LAYOUT)
        self.master = pkg.rel_target(self.layout, REL_MASTER) if self.layout else None
        theme_part = pkg.rel_target(self.master, REL_THEME) if self.master else None
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


def placeholder_of(sp: etree._Element) -> tuple[str | None, int | None] | None:
    for wrapper in ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr"):
        ph = sp.find(f"{_p(wrapper)}/{_p('nvPr')}/{_p('ph')}")
        if ph is not None:
            idx = ph.get("idx")
            return ph.get("type") or ("body" if idx else None), int(idx) if idx and idx.isdigit() else None
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
    if sp.find(f"{_p('nvSpPr')}/{_p('cNvSpPr')}") is not None and sp.find(f"{_p('nvSpPr')}/{_p('cNvSpPr')}").get("txBox") == "1":
        return "text_box"
    return "text_shape" if has_text else "shape"


class SlideWalker:
    def __init__(self, pkg: Package, slide_part: str, deck: str, index: int) -> None:
        self.pkg = pkg
        self.chain = Chain(pkg, slide_part)
        pres = pkg.root("ppt/presentation.xml")
        size = pres.find(_p("sldSz"))
        self.width = int(size.get("cx", "9144000")) if size is not None else 9144000
        self.height = int(size.get("cy", "6858000")) if size is not None else 6858000
        self.print = SlidePrint(deck, index, self.width, self.height, self._background())

    # text chain ------------------------------------------------------------------
    def _level_holders(self, sp: etree._Element, layer: str, ph: tuple[str | None, int | None] | None) -> list[etree._Element | None]:
        holders: list[etree._Element | None] = []
        tx = sp.find(_p("txBody"))
        holders.append(tx.find(_a("lstStyle")) if tx is not None else None)
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
                    holders.append(ltx.find(_a("lstStyle")) if ltx is not None else None)
            if layer in ("slide", "layout") and self.chain.master:
                msp = find_placeholder(self.pkg.root(self.chain.master), key_type, key_idx, True)
                if msp is not None:
                    mtx = msp.find(_p("txBody"))
                    holders.append(mtx.find(_a("lstStyle")) if mtx is not None else None)
        if self.chain.master and (ph is not None or layer == "master"):
            name = "titleStyle" if ph_type in TITLE_TYPES else "bodyStyle" if ph_type in BODY_TYPES else "otherStyle"
            styles = self.pkg.root(self.chain.master).find(_p("txStyles"))
            holders.append(styles.find(_p(name)) if styles is not None else None)
        holders.append(self.chain.default_text_style)
        return holders

    def _resolve_run(self, rpr: etree._Element | None, def_rpr: etree._Element | None,
                     holders: list[etree._Element | None], level: int, getter) -> object | None:
        for el in (rpr, def_rpr):
            if el is not None:
                v = getter(el)
                if v is not None:
                    return v
        tag = _a(f"lvl{level + 1}pPr")
        for holder in holders:
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
                return v
        return None

    def _resolve_para(self, ppr: etree._Element | None, holders: list[etree._Element | None], level: int, attr: str) -> str | None:
        if ppr is not None and ppr.get(attr):
            return ppr.get(attr)
        tag = _a(f"lvl{level + 1}pPr")
        for holder in holders:
            if holder is None:
                continue
            lvl = holder.find(tag)
            if lvl is not None and lvl.get(attr):
                return lvl.get(attr)
        return None

    def _walk_text(self, tx: etree._Element, holders: list[etree._Element | None], cls: str, ph_type: str | None) -> None:
        theme = self.chain.theme

        def g_size(el: etree._Element) -> float | None:
            sz = el.get("sz")
            try:
                return int(sz) / 100.0 if sz else None
            except ValueError:
                return None

        def g_bold(el: etree._Element) -> bool | None:
            b = el.get("b")
            return None if b is None else b in ("1", "true")

        def g_face(el: etree._Element) -> str | None:
            latin = el.find(_a("latin"))
            return latin.get("typeface") if latin is not None else None

        def g_color(el: etree._Element) -> str | None:
            sf = el.find(_a("solidFill"))
            return self.chain.first_color(sf) if sf is not None else None

        for para in tx.iter(_a("p")):
            ppr = para.find(_a("pPr"))
            level = 0
            if ppr is not None and ppr.get("lvl"):
                try:
                    level = int(ppr.get("lvl") or "0")
                except ValueError:
                    level = 0
            def_rpr = ppr.find(_a("defRPr")) if ppr is not None else None
            align = self._resolve_para(ppr, holders, level, "algn") or "l"
            for r in para:
                if _local(r) not in ("r", "fld"):
                    continue
                t = r.find(_a("t"))
                text = (t.text or "") if t is not None else ""
                if not text.strip():
                    continue
                rpr = r.find(_a("rPr"))
                size = self._resolve_run(rpr, def_rpr, holders, level, g_size)
                bold = self._resolve_run(rpr, def_rpr, holders, level, g_bold)
                face = self._resolve_run(rpr, def_rpr, holders, level, g_face)
                color = self._resolve_run(rpr, def_rpr, holders, level, g_color)
                if face in ("+mj-lt", "+mn-lt", None) and theme:
                    face = theme.major_latin if (face == "+mj-lt" or (face is None and ph_type in TITLE_TYPES)) else theme.minor_latin
                if color is None:
                    color = self.chain.theme.colors.get(self.chain.clr_map.get("tx1", "dk1")) if self.chain.theme else None
                self.print.runs.append(Run(
                    chars=len(text.strip()), family=face,
                    size_pt=float(size) if isinstance(size, (int, float)) else DEFAULT_SIZE_PT,
                    bold=bool(bold), color=color, align=align, ph_class=cls,
                ))

    # shapes ----------------------------------------------------------------------
    def _background(self) -> str | None:
        for part in (self.chain.slide, self.chain.layout, self.chain.master):
            if not part:
                continue
            bg = self.pkg.root(part).find(f"{_p('cSld')}/{_p('bg')}")
            if bg is None:
                continue
            bgpr = bg.find(_p("bgPr"))
            if bgpr is not None:
                sf = bgpr.find(_a("solidFill"))
                if sf is not None:
                    return self.chain.first_color(sf)
                gf = bgpr.find(_a("gradFill"))
                if gf is not None:
                    gs = gf.find(f"{_a('gsLst')}/{_a('gs')}")
                    return self.chain.first_color(gs) if gs is not None else None
                return None
            ref = bg.find(_p("bgRef"))
            if ref is not None:
                return self.chain.first_color(ref)
        if self.chain.theme:
            return self.chain.theme.colors.get(self.chain.clr_map.get("bg1", "lt1"))
        return None

    def _fill(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> str | None:
        sppr = sp.find(_p("spPr"))
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

    def _line(self, sp: etree._Element, ph: tuple[str | None, int | None] | None, layer: str) -> tuple[str | None, int | None]:
        for candidate in self._sppr_chain(sp, ph, layer):
            if candidate is None:
                continue
            ln = candidate.find(_a("ln"))
            if ln is None:
                continue
            w = ln.get("w")
            width = int(w) if w and w.isdigit() else None
            for child in ln:
                if _local(child) == "noFill":
                    return None, None
                if _local(child) == "solidFill":
                    return self.chain.first_color(child), width or 9525
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
                    return None, None
                ph_color = self.chain.first_color(ref)
                if 1 <= idx <= len(self.chain.theme.line_styles):
                    ls = self.chain.theme.line_styles[idx - 1]
                    w = ls.get("w")
                    sf = ls.find(_a("solidFill"))
                    return (self.chain.first_color(sf, ph_color) if sf is not None else ph_color), int(w) if w and w.isdigit() else 9525
                return ph_color, 9525
        return None, None

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

    def walk_tree(self, tree: etree._Element, layer: str, sink: list[Shape], with_text: bool,
                  transform: tuple[float, float, float, float] | None = None) -> None:
        for sp in tree:
            local = _local(sp)
            if local not in ("sp", "pic", "cxnSp", "graphicFrame", "grpSp"):
                continue
            ph = placeholder_of(sp)
            if layer != "slide" and ph is not None and ph_class(ph[0]) in ("title", "body") and local == "sp":
                # A layout/master placeholder prototype is a template, not chrome.
                continue
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
                self.walk_tree(sp, layer, sink, with_text, child_t)
                continue
            box = self._box_of(sp, ph, layer)
            if box is not None:
                box = _apply_transform(box, transform)
            fill = self._fill(sp, ph, layer) if local in ("sp", "cxnSp") else None
            line, line_w = self._line(sp, ph, layer) if local in ("sp", "cxnSp") else (None, None)
            prst_el = sp.find(f"{_p('spPr')}/{_a('prstGeom')}")
            sink.append(Shape(
                kind=_shape_kind(sp), box=box, fill=fill, line=line, line_w_emu=line_w,
                prst=prst_el.get("prst") if prst_el is not None else None,
                is_placeholder=ph is not None, ph_type=ph[0] if ph else None, layer=layer,
            ))
            if with_text:
                cls = ph_class(ph[0]) if ph else "none"
                tx = sp.find(_p("txBody"))
                if tx is not None:
                    self._walk_text(tx, self._level_holders(sp, layer, ph), cls, ph[0] if ph else None)
                if local == "graphicFrame":
                    for tc in sp.iter(_a("tc")):
                        ttx = tc.find(_a("txBody"))
                        if ttx is not None:
                            self._walk_text(ttx, [self.chain.default_text_style], "table", None)

    def run(self) -> SlidePrint:
        root = self.pkg.root(self.chain.slide)
        tree = root.find(f"{_p('cSld')}/{_p('spTree')}")
        if tree is not None:
            self.walk_tree(tree, "slide", self.print.shapes, True)
        for part, layer in ((self.chain.layout, "layout"), (self.chain.master, "master")):
            if not part:
                continue
            tree = self.pkg.root(part).find(f"{_p('cSld')}/{_p('spTree')}")
            if tree is not None:
                self.walk_tree(tree, layer, self.print.chrome, False)
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


# --- features ------------------------------------------------------------------------


@dataclass
class Features:
    """Weighted distributions of one slide or one house. Weights are characters
    (text), area (fills) or count (kinds); every histogram is normalised at use."""

    families: Counter = field(default_factory=Counter)
    sizes: Counter = field(default_factory=Counter)
    title_sizes: Counter = field(default_factory=Counter)
    bold_chars: float = 0.0
    chars: float = 0.0
    text_colors: Counter = field(default_factory=Counter)
    fills: Counter = field(default_factory=Counter)
    lines: Counter = field(default_factory=Counter)  # (color, width_pt_bin)
    aligns: Counter = field(default_factory=Counter)
    kinds: Counter = field(default_factory=Counter)
    prsts: Counter = field(default_factory=Counter)
    backgrounds: Counter = field(default_factory=Counter)
    margins: list[tuple[float, float, float, float]] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    coverage: list[float] = field(default_factory=list)
    chrome_boxes: Counter = field(default_factory=Counter)

    def add(self, other: "Features") -> None:
        for name in ("families", "sizes", "title_sizes", "text_colors", "fills", "lines", "aligns", "kinds", "prsts", "backgrounds", "chrome_boxes"):
            getattr(self, name).update(getattr(other, name))
        self.bold_chars += other.bold_chars
        self.chars += other.chars
        self.margins.extend(other.margins)
        self.counts.extend(other.counts)
        self.coverage.extend(other.coverage)


def slide_features(s: SlidePrint) -> Features:
    f = Features()
    pdf = s.source == "pdf"
    for r in s.runs:
        w = r.chars
        f.families[(r.family or "?").lower()] += w
        f.sizes[round(r.size_pt * 2) / 2] += w
        if r.ph_class == "title":
            f.title_sizes[round(r.size_pt * 2) / 2] += w
        f.chars += w
        if r.bold:
            f.bold_chars += w
        if r.color:
            f.text_colors[r.color] += w
        if not pdf:
            f.aligns[r.align] += w
    xs0, ys0, xs1, ys1 = [], [], [], []
    area_union = 0.0
    chrome_keys = {(c.kind, _quant(c.box, s.width, s.height)) for c in s.chrome if c.box}
    n_shapes = 0
    for sh in s.shapes:
        if not pdf:
            f.kinds[sh.kind] += 1
            n_shapes += 1
        elif sh.kind != "text_box":
            n_shapes += 1
        if sh.prst:
            f.prsts[sh.prst] += 1
        if sh.box:
            x, y, w, h = sh.box
            if w <= 0 or h <= 0:
                continue
            if (sh.kind, _quant(sh.box, s.width, s.height)) in chrome_keys:
                continue  # chrome repeated on the slide layer does not set the content margin
            if sh.fill:
                f.fills[sh.fill] += (w * h) / (s.width * s.height)
            if sh.line and sh.line_w_emu:
                f.lines[(sh.line, round(sh.line_w_emu / 12700 * 4) / 4)] += 1
            xs0.append(x); ys0.append(y); xs1.append(x + w); ys1.append(y + h)
            area_union += w * h
    if xs0:
        f.margins.append((min(xs0) / s.width, 1 - max(xs1) / s.width, min(ys0) / s.height, 1 - max(ys1) / s.height))
        f.coverage.append(min(1.0, area_union / (s.width * s.height)))
    if not pdf:
        f.counts.append(n_shapes)
    if s.background:
        f.backgrounds[s.background] += 1
    for c in s.chrome:
        if c.box:
            f.chrome_boxes[(c.kind, _quant(c.box, s.width, s.height))] += 1
    return f


def _quant(box: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    return (round(box[0] / w * 40), round(box[1] / h * 40), round(box[2] / w * 40), round(box[3] / h * 40))


def house_features(slides: list[SlidePrint]) -> Features:
    f = Features()
    for s in slides:
        f.add(slide_features(s))
    return f


# --- distance -------------------------------------------------------------------------


def _norm(c: Counter) -> dict:
    total = float(sum(c.values()))
    return {k: v / total for k, v in c.items()} if total > 0 else {}


def hist_distance(a: Counter, b: Counter) -> float | None:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return None
    return 1.0 - sum(min(na.get(k, 0.0), nb.get(k, 0.0)) for k in set(na) | set(nb))


def ladder_distance(a: Counter, b: Counter, tol: float = 0.5) -> float | None:
    """Weight of candidate sizes that sit off the house's size ladder."""
    na = _norm(a)
    if not na or not b:
        return None
    ladder = list(b.keys())
    return sum(w for k, w in na.items() if min(abs(k - r) for r in ladder) > tol)


def palette_distance(a: Counter, b: Counter, scale: float = 40.0) -> float | None:
    """Weighted mean of each candidate colour's nearest-neighbour CIE76 distance
    to the house palette, capped at `scale` (a visibly different colour)."""
    na = _norm(a)
    if not na or not b:
        return None
    palette = [k if isinstance(k, str) else k[0] for k in b.keys()]
    total = 0.0
    for k, w in na.items():
        hexv = k if isinstance(k, str) else k[0]
        total += w * min(1.0, min(delta_e(hexv, p) for p in palette) / scale)
    return total


def line_distance(a: Counter, b: Counter) -> float | None:
    na = _norm(a)
    if not na or not b:
        return None
    total = 0.0
    for (color, width), w in na.items():
        best = 1.0
        for (hc, hw), _ in b.items():
            d = 0.5 * min(1.0, delta_e(color, hc) / 40.0) + 0.5 * min(1.0, abs(math.log((width + 0.25) / (hw + 0.25))) / math.log(3))
            best = min(best, d)
        total += w * best
    return total


def margin_distance(a: list, b: list) -> float | None:
    if not a or not b:
        return None
    mean_b = [sum(m[i] for m in b) / len(b) for i in range(4)]
    mean_a = [sum(m[i] for m in a) / len(a) for i in range(4)]
    return min(1.0, sum(abs(mean_a[i] - mean_b[i]) for i in range(4)) / 0.2)


def scalar_distance(a: list, b: list, span: float) -> float | None:
    if not a or not b:
        return None
    return min(1.0, abs(sum(a) / len(a) - sum(b) / len(b)) / span)


COMPONENTS = (
    "families", "size_hist", "size_ladder", "title_size", "bold_ratio", "text_colors",
    "fills", "lines", "aligns", "kinds", "background", "margins", "coverage", "count",
)


def distance(cand: Features, house: Features) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "families": hist_distance(cand.families, house.families),
        "size_hist": hist_distance(cand.sizes, house.sizes),
        "size_ladder": ladder_distance(cand.sizes, house.sizes),
        "title_size": ladder_distance(cand.title_sizes, house.title_sizes, tol=1.0),
        "bold_ratio": (min(1.0, abs(cand.bold_chars / cand.chars - house.bold_chars / house.chars) / 0.5)
                       if cand.chars and house.chars else None),
        "text_colors": palette_distance(cand.text_colors, house.text_colors),
        "fills": palette_distance(cand.fills, house.fills),
        "lines": line_distance(cand.lines, house.lines),
        "aligns": hist_distance(cand.aligns, house.aligns),
        "kinds": hist_distance(cand.kinds, house.kinds),
        "background": palette_distance(cand.backgrounds, house.backgrounds),
        "margins": margin_distance(cand.margins, house.margins),
        "coverage": scalar_distance(cand.coverage, house.coverage, 0.5),
        "count": (min(1.0, abs(math.log((sum(cand.counts) / len(cand.counts) + 1) / (sum(house.counts) / len(house.counts) + 1))) / math.log(4))
                  if cand.counts and house.counts else None),
    }
    return out


def total(d: dict[str, float | None], weights: dict[str, float] | None = None) -> float:
    weights = weights or {}
    num = den = 0.0
    for k, v in d.items():
        if v is None:
            continue
        w = weights.get(k, 1.0)
        num += w * v
        den += w
    return num / den if den else 1.0


# --- calibration ------------------------------------------------------------------------


def binomial_bound(n: int, k_classes: int, alpha: float = 0.05) -> int:
    """Smallest k with P(Binomial(n, 1/k_classes) >= k) <= alpha."""
    p = 1.0 / k_classes
    for k in range(n + 1):
        tail = sum(math.comb(n, j) * p**j * (1 - p) ** (n - j) for j in range(k, n + 1))
        if tail <= alpha:
            return k
    return n + 1


def calibrate(houses: dict[str, list[str]], weights: dict[str, float] | None = None, max_pages: int | None = None) -> dict:
    prints: dict[str, dict[str, list[SlidePrint]]] = {}
    for house, decks in houses.items():
        prints[house] = {deck: fingerprint_deck(deck, max_pages) for deck in decks}
    house_feats = {h: house_features([s for d in decks.values() for s in d]) for h, decks in prints.items()}
    n_classes = len(houses)

    def predict(cand: Features, exclude_house: str, exclude: Features) -> tuple[str, dict[str, float]]:
        scores = {}
        for h, hf in house_feats.items():
            target = hf
            if h == exclude_house:
                target = Features()
                target.add(hf)
                _subtract(target, exclude)
            scores[h] = total(distance(cand, target), weights)
        return min(scores, key=scores.get), scores

    per_slide = []
    per_component_correct: Counter = Counter()
    per_component_n: Counter = Counter()
    confusion: Counter = Counter()
    for house, decks in prints.items():
        for deck, slides in decks.items():
            for s in slides:
                cf = slide_features(s)
                pred, scores = predict(cf, house, cf)
                confusion[(house, pred)] += 1
                per_slide.append({"house": house, "deck": deck, "slide": s.index + 1, "pred": pred, "scores": scores})
                # per-component 1-NN, to see which dimensions carry signal
                for comp in COMPONENTS:
                    best = None
                    for h, hf in house_feats.items():
                        target = hf
                        if h == house:
                            target = Features(); target.add(hf); _subtract(target, cf)
                        v = distance(cf, target)[comp]
                        if v is None:
                            continue
                        if best is None or v < best[0]:
                            best = (v, h)
                    if best is not None:
                        per_component_n[comp] += 1
                        if best[1] == house:
                            per_component_correct[comp] += 1
    n = len(per_slide)
    correct = sum(1 for r in per_slide if r["pred"] == r["house"])
    # leave-one-deck-out, for houses with several decks
    lodo = []
    for house, decks in prints.items():
        if len(decks) < 2:
            continue
        for deck, slides in decks.items():
            df = house_features(slides)
            pred, scores = predict(df, house, df)
            lodo.append({"house": house, "deck": deck, "pred": pred, "scores": scores})
    return {
        "n_slides": n,
        "n_houses": n_classes,
        "slide_loo_correct": correct,
        "slide_loo_accuracy": correct / n if n else None,
        "chance_bound_k": binomial_bound(n, n_classes),
        "per_component_accuracy": {c: (per_component_correct[c] / per_component_n[c] if per_component_n[c] else None) for c in COMPONENTS},
        "confusion": {f"{a}->{b}": v for (a, b), v in sorted(confusion.items())},
        "leave_one_deck_out": lodo,
        "per_slide": per_slide,
    }


def _subtract(target: Features, part: Features) -> None:
    for name in ("families", "sizes", "title_sizes", "text_colors", "fills", "lines", "aligns", "kinds", "prsts", "backgrounds", "chrome_boxes"):
        c = getattr(target, name)
        c.subtract(getattr(part, name))
        for k in [k for k, v in c.items() if v <= 1e-9]:
            del c[k]
    target.bold_chars -= part.bold_chars
    target.chars -= part.chars
    for m in part.margins:
        if m in target.margins:
            target.margins.remove(m)
    for c in part.counts:
        if c in target.counts:
            target.counts.remove(c)
    for c in part.coverage:
        if c in target.coverage:
            target.coverage.remove(c)


# --- cli -----------------------------------------------------------------------------------


def summarise(feats: Features) -> dict:
    return {
        "families": dict(Counter(_norm(feats.families)).most_common(5)),
        "sizes_pt": {str(k): round(v, 3) for k, v in sorted(_norm(feats.sizes).items())},
        "title_sizes_pt": sorted(feats.title_sizes.keys()),
        "bold_ratio": round(feats.bold_chars / feats.chars, 3) if feats.chars else None,
        "text_colors": dict(Counter(_norm(feats.text_colors)).most_common(8)),
        "fills": {k: round(v, 4) for k, v in Counter(feats.fills).most_common(8)},
        "lines": {f"{c}@{w}pt": n for (c, w), n in feats.lines.most_common(6)},
        "aligns": dict(_norm(feats.aligns)),
        "kinds": dict(feats.kinds),
        "backgrounds": dict(feats.backgrounds),
        "margins_mean": [round(sum(m[i] for m in feats.margins) / len(feats.margins), 3) for i in range(4)] if feats.margins else None,
        "coverage_mean": round(sum(feats.coverage) / len(feats.coverage), 3) if feats.coverage else None,
        "shapes_per_slide": round(sum(feats.counts) / len(feats.counts), 1) if feats.counts else None,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s_print = sub.add_parser("print")
    s_print.add_argument("deck")
    s_print.add_argument("--per-slide", action="store_true")
    s_print.add_argument("--max-pages", type=int, default=None)
    s_cmp = sub.add_parser("compare")
    s_cmp.add_argument("candidate")
    s_cmp.add_argument("--reference", required=True)
    s_cmp.add_argument("--others", nargs="*", default=[])
    s_cmp.add_argument("--json")
    s_cmp.add_argument("--max-pages", type=int, default=None)
    s_cal = sub.add_parser("calibrate")
    s_cal.add_argument("houses", nargs="+", help="name=deck1.pptx,deck2.pdf,...")
    s_cal.add_argument("--json")
    s_cal.add_argument("--max-pages", type=int, default=None, help="cap pages read per file (PDF references can run to hundreds)")
    args = ap.parse_args(argv)

    if args.cmd == "print":
        slides = fingerprint_deck(args.deck, args.max_pages)
        print(json.dumps({"deck": args.deck, "slides": len(slides), "house": summarise(house_features(slides))}, indent=1))
        if args.per_slide:
            for s in slides:
                print(json.dumps({"slide": s.index + 1, **summarise(slide_features(s))}))
        return 0
    if args.cmd == "compare":
        cand = fingerprint_deck(args.candidate, args.max_pages)
        ref = house_features(fingerprint_deck(args.reference, args.max_pages))
        cf = house_features(cand)
        d = distance(cf, ref)
        report = {"candidate": args.candidate, "reference": args.reference, "components": d, "total": total(d)}
        others = {}
        for o in args.others:
            od = distance(cf, house_features(fingerprint_deck(o, args.max_pages)))
            others[o] = total(od)
        report["others"] = others
        report["nearest_is_reference"] = all(report["total"] < v for v in others.values()) if others else None
        per_slide = []
        for s in cand:
            sd = distance(slide_features(s), ref)
            worst = sorted(((v, k) for k, v in sd.items() if v is not None), reverse=True)[:3]
            per_slide.append({"slide": s.index + 1, "total": round(total(sd), 3), "worst": [(k, round(v, 3)) for v, k in worst]})
        report["per_slide"] = per_slide
        text = json.dumps(report, indent=1, default=str)
        print(text)
        if args.json:
            Path(args.json).write_text(text)
        return 0
    if args.cmd == "calibrate":
        houses = {}
        for spec in args.houses:
            name, _, decks = spec.partition("=")
            houses[name] = decks.split(",")
        result = calibrate(houses, max_pages=args.max_pages)
        brief = {k: v for k, v in result.items() if k != "per_slide"}
        print(json.dumps(brief, indent=1, default=str))
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=1, default=str))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
