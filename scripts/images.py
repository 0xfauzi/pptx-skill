#!/usr/bin/env python3
"""Pictures on a page: a file the user supplies, a logo taken from the reference, or a
vector icon the model writes as a small SVG. The one definition of an image source.

    images.py list REF.pptx|REF.pdf                       # the reference's pictures, with ids
    images.py extract REF --id ID -o "$DECK_WORK/img/x.png"
    images.py extract REF.pdf --page N --bbox X0,Y0,X1,Y1 -o "$DECK_WORK/img/x.png"   # a vector logo, PDF points
    images.py check ICON.svg [--guide guide.json] [--png preview.png --height-px 256]

A slide names its pictures under `slide.images[<element id>]`, one source each:
  {"path": "/abs/logo.png"}     a PNG, JPEG or GIF file (the user's, or one `extract` wrote)
  {"svg": "/abs/icon.svg"}      an icon the model wrote in the SVG subset below
plus, optionally, how big the box is in the reference's own measures (never in EMU):
  "height_role": "type.body" (the role's line pitch x "lines", default 1) or "space.lg";
  or "width_role": the same roles, for a logo sized by its width; or both, a box of both
  sizes the picture is fitted inside (a column of icons of differing aspect lines up);
and where the picture sits in a box larger than it: "align" (left | center | right),
"valign" (top | middle | bottom). A picture is never stretched: it is drawn at its own
aspect ratio inside its box, and a choice left out is written as the neutral value in
DEFAULTS and listed under the page's `image_defaults_taken`.

THE SVG SUBSET (anything else is refused by name, at the boundary):
  root <svg viewBox="minx miny w h"> with no width, height, style or transform;
  its children only (no <g>): <path d>, <rect x y width height [rx ry]>,
  <circle cx cy r>, <line x1 y1 x2 y2>, <polygon points>;
  paint: fill="color.<role>" | "none" (required on every shape but <line>),
  stroke="color.<role>" | "none" (required), stroke-width (required with a stroke),
  stroke-linecap (butt | round | square), stroke-linejoin (miter | round | bevel),
  fill-rule (nonzero | evenodd). Numbers are plain user units; no units, no percent.
  At most 64 KiB and 400 shapes, UTF-8 only; no DOCTYPE, entity or processing instruction;
  every shape draws (a stroke two distinct points, a fill some area).
Colours are the guide's roles, resolved when the file is written. The emitter writes the
icon natively (an SVG part on an a:blip svgBlip extension, which PowerPoint 2016+ draws)
(its coordinates mapped onto a 1000-unit viewBox, EMIT_UNITS) with a PNG fallback
rasterised here from the same parsed shapes, and the build compares
what the renderer drew in the box with this rasterisation (`render_check`).

Reference files are untrusted: run this command with `python3 -I`; every picture read is
opened with Pillow's own guard against decompression bombs and checked for format and size.
"""

from __future__ import annotations

import argparse
import io
import itertools
import json
import math
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache

from lxml import etree
from PIL import Image

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 64 * 1024
MAX_SHAPES = 400
MAX_PATH_COMMANDS = 20_000
MAX_IMAGE_BYTES = 20 * 1024 * 1024
#: Pillow's own bomb limit is 89.5 MP; a page picture needs far less.
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "GIF": "gif"}
#: the PNG fallback's density: 300 px per inch of the drawn box (print quality); the
#: renderer scales it, so this bounds what a zoomed or printed page shows of the fallback
FALLBACK_PPI = 300
EMU_PER_INCH = 914_400

SHAPES = ("path", "rect", "circle", "line", "polygon")
GEOMETRY = {"path": ("d",), "rect": ("x", "y", "width", "height"), "circle": ("cx", "cy", "r"), "line": ("x1", "y1", "x2", "y2"), "polygon": ("points",)}
OPTIONAL_GEOMETRY = {"rect": ("rx", "ry")}
PAINT = ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "fill-rule")
LINECAPS = ("butt", "round", "square")
LINEJOINS = ("miter", "round", "bevel")
FILL_RULES = ("nonzero", "evenodd")
ENTRY_KEYS = {"path", "svg", "height_role", "width_role", "lines", "align", "valign"}
ALIGNS = ("left", "center", "right")
VALIGNS = ("top", "middle", "bottom")
DEFAULTS = {
    "align": "center: the picture centred across a box wider than it",
    "valign": "middle: the picture centred down a box taller than it",
    "stroke-linecap": "butt (SVG's absence value)",
    "stroke-linejoin": "miter (SVG's absence value)",
    "fill-rule": "nonzero (SVG's absence value)",
}


class ImageRefused(ValueError):
    """A picture or icon the build will not place; the message names what and why."""


# --- the SVG subset ------------------------------------------------------------------------


@dataclass
class Shape:
    tag: str
    geometry: dict          # parsed numbers (path: list of (cmd, args)); polygon: list of points
    fill: str               # a role or "none"
    stroke: str             # a role or "none"
    stroke_width: float
    linecap: str
    linejoin: str
    fill_rule: str


@dataclass
class Icon:
    view_box: tuple[float, float, float, float]
    shapes: list[Shape]
    defaults_taken: list[str] = field(default_factory=list)

    @property
    def aspect(self) -> float:
        return self.view_box[2] / self.view_box[3]

    def roles(self) -> list[str]:
        return sorted({r for s in self.shapes for r in (s.fill, s.stroke) if r != "none"})


_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_PATH_TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)|([\s,]+)|(.)")
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _number(text: str | None, where: str, what: str) -> float:
    if text is None:
        raise ImageRefused(f"{where}: {what} is required (an absent number is not zero)")
    t = text.strip()
    if not _NUMBER.fullmatch(t):
        raise ImageRefused(f"{where}: {what}={text!r} is not a plain number (no units, no percent)")
    v = float(t)
    if not math.isfinite(v):
        raise ImageRefused(f"{where}: {what}={text!r} is not finite")
    return v


def _numbers(text: str, where: str, what: str) -> list[float]:
    parts = [p for p in re.split(r"[\s,]+", text.strip()) if p]
    return [_number(p, where, what) for p in parts]


def _path_commands(d: str, where: str) -> list[tuple[str, list[float]]]:
    """d as (absolute-or-relative command, args) per segment, implicit repeats expanded;
    arc flags may be written without separators, as SVG allows."""
    out: list[tuple[str, list[float]]] = []
    cmd: str | None = None
    pos = 0
    pending: list[str] = []  # raw number tokens for the current command

    def flush() -> None:
        nonlocal pending
        if cmd is None:
            if pending:
                raise ImageRefused(f"{where}: path data starts with numbers, not a command")
            return
        up = cmd.upper()
        n = PATH_ARITY[up]
        if up == "Z":
            if pending:
                raise ImageRefused(f"{where}: numbers after Z")
            out.append((cmd, []))
            return
        if not pending or len(pending) % n:
            raise ImageRefused(f"{where}: command {cmd} takes its numbers in groups of {n}; got {len(pending)}")
        first = True
        for i in range(0, len(pending), n):
            group = [float(v) for v in pending[i:i + n]]
            if up == "A":
                for flag_i in (3, 4):
                    if pending[i + flag_i] not in ("0", "1"):
                        raise ImageRefused(f"{where}: arc flags are 0 or 1, got {pending[i + flag_i]!r}")
                if group[0] < 0 or group[1] < 0:
                    raise ImageRefused(f"{where}: arc radii must not be negative")
            c = cmd if (first or up != "M") else ("l" if cmd == "m" else "L")
            out.append((c, group))
            first = False
        pending = []

    while pos < len(d):
        m = _PATH_TOKEN.match(d, pos)
        if m is None or m.group(4) is not None:
            raise ImageRefused(f"{where}: path data has {d[pos:pos + 12]!r}, which is not a command or a number")
        pos = m.end()
        if m.group(1):
            flush()
            cmd = m.group(1)
        elif m.group(2):
            tok = m.group(2)
            if cmd is not None and cmd.upper() == "A":
                # flags (the 4th and 5th of each 7) are single digits that may run on: "0 01"
                k = len(pending) % 7
                if k in (3, 4) and len(tok) > 1 and tok[0] in "01" and not tok.startswith(("0.", "1.")):
                    pending.append(tok[0])
                    rest = tok[1:]
                    if rest:
                        if len(pending) % 7 == 4 and rest[0] in "01":
                            pending.append(rest[0])
                            rest = rest[1:]
                        if rest:
                            pending.append(rest)
                    continue
            pending.append(tok)
        if len(out) + len(pending) > MAX_PATH_COMMANDS:
            raise ImageRefused(f"{where}: path data past {MAX_PATH_COMMANDS} numbers; simplify the icon")
    flush()
    if not out or out[0][0] not in ("M", "m"):
        raise ImageRefused(f"{where}: path data must start with M")
    return out


def _paint(el, where: str, attr: str, required: bool) -> str:
    v = el.get(attr)
    if v is None:
        if required:
            raise ImageRefused(f"{where}: {attr} is required: a role such as \"color.accent1\" or \"none\" (SVG's default is a literal black)")
        return "none"
    v = v.strip()
    if v == "none":
        return v
    # a role name as the guide spells it (color.accent1, or an extra role such as chart_navy);
    # a hex, a function or a keyword the guide does not define is refused here or at the guide
    if re.fullmatch(r"#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", v) or not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)*", v):
        raise ImageRefused(f"{where}: {attr}={v!r}; colours are the guide's roles (\"color.accent1\") or \"none\", never a literal")
    return v


def parse_svg(data: bytes, where: str) -> Icon:
    """The icon as parsed shapes, or ImageRefused naming the first thing outside the subset."""
    if len(data) > MAX_SVG_BYTES:
        raise ImageRefused(f"{where}: {len(data)} bytes; an icon is at most {MAX_SVG_BYTES}")
    # the subset is UTF-8 only: in another encoding (UTF-16, UTF-7) a byte search for a
    # declaration sees nothing, so the encoding is settled before anything is searched
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        raise ImageRefused(f"{where}: a UTF-16 or UTF-32 byte order mark; an icon is UTF-8")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise ImageRefused(f"{where}: not UTF-8; an icon is UTF-8") from None
    if re.search(rb"<!DOCTYPE|<!ENTITY", data, re.IGNORECASE):
        raise ImageRefused(f"{where}: a DOCTYPE or ENTITY declaration; the subset takes neither")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, remove_comments=True, remove_pis=False)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as error:
        raise ImageRefused(f"{where}: not well-formed XML ({error})") from None
    info = root.getroottree().docinfo
    if (info.encoding or "UTF-8").upper().replace("_", "-") not in ("UTF-8", "UTF8"):
        raise ImageRefused(f"{where}: declares encoding {info.encoding!r}; an icon is UTF-8")
    if info.doctype or info.internalDTD is not None or info.externalDTD is not None:
        raise ImageRefused(f"{where}: a DOCTYPE or ENTITY declaration; the subset takes neither")
    taken: list[str] = []
    outside = list(root.itersiblings(preceding=True)) + list(root.itersiblings())
    for node in outside + list(root.iter()):
        if not isinstance(node.tag, str):
            raise ImageRefused(f"{where}: a processing instruction or entity reference; the subset takes neither")

    def local(node) -> tuple[str, str]:
        q = etree.QName(node)
        return q.namespace or "", q.localname

    ns, name = local(root)
    if name != "svg" or ns not in ("", SVG_NS):
        raise ImageRefused(f"{where}: the root is <{name}>, not <svg>")
    extra = sorted(set(root.attrib) - {"viewBox"})
    if extra:
        raise ImageRefused(f"{where}: <svg> takes only viewBox; {extra} {'is' if len(extra) == 1 else 'are'} refused (the box's size is a role on the slide)")
    vb = _numbers(root.get("viewBox") or "", where, "viewBox")
    if len(vb) != 4 or vb[2] <= 0 or vb[3] <= 0:
        raise ImageRefused(f"{where}: viewBox must be four numbers \"minx miny width height\" with a positive width and height")
    if (root.text or "").strip():
        raise ImageRefused(f"{where}: text inside <svg>; the subset draws shapes only")
    shapes: list[Shape] = []
    for i, el in enumerate(root):
        ens, tag = local(el)
        w = f"{where} <{tag}> #{i}"
        if ens not in ("", SVG_NS) or tag not in SHAPES:
            raise ImageRefused(f"{w}: <{tag}> is outside the subset; only {list(SHAPES)} as direct children of <svg> (no <g>, <text>, <use>, <style>, <image>)")
        if len(el) or (el.text or "").strip():
            raise ImageRefused(f"{w}: a shape holds no children or text")
        if (el.tail or "").strip():
            raise ImageRefused(f"{where}: text between shapes")
        allowed = set(GEOMETRY[tag]) | set(OPTIONAL_GEOMETRY.get(tag, ())) | set(PAINT)
        extra = sorted(set(el.attrib) - allowed)
        if extra:
            raise ImageRefused(f"{w}: attributes {extra} are outside the subset; a <{tag}> takes {sorted(allowed)}")
        fill = "none" if tag == "line" else _paint(el, w, "fill", True)
        if tag == "line" and el.get("fill") not in (None, "none"):
            raise ImageRefused(f"{w}: a line has no area to fill")
        stroke = _paint(el, w, "stroke", True)
        if fill == "none" and stroke == "none":
            raise ImageRefused(f"{w}: draws nothing (fill and stroke are both none)")
        sw = 0.0
        if stroke != "none":
            sw = _number(el.get("stroke-width"), w, "stroke-width")
            if sw <= 0:
                raise ImageRefused(f"{w}: stroke-width must be positive")
        elif el.get("stroke-width") is not None:
            raise ImageRefused(f"{w}: stroke-width without a stroke")
        attrs = {}
        for key, choices in (("stroke-linecap", LINECAPS), ("stroke-linejoin", LINEJOINS), ("fill-rule", FILL_RULES)):
            v = el.get(key)
            if v is None:
                attrs[key] = choices[0]
                if (key != "fill-rule" and stroke != "none") or (key == "fill-rule" and fill != "none" and tag in ("path", "polygon")):
                    taken.append(f"{w} {key}: {DEFAULTS[key]}")
            elif v not in choices:
                raise ImageRefused(f"{w}: {key}={v!r} not in {list(choices)}")
            else:
                attrs[key] = v
        geo: dict = {}
        if tag == "path":
            geo["d"] = _path_commands(el.get("d") or "", w)
        elif tag == "polygon":
            pts = _numbers(el.get("points") or "", w, "points")
            if len(pts) < 6 or len(pts) % 2:
                raise ImageRefused(f"{w}: points must be at least three x,y pairs")
            geo["points"] = [(pts[k], pts[k + 1]) for k in range(0, len(pts), 2)]
        else:
            for a in GEOMETRY[tag]:
                geo[a] = _number(el.get(a), w, a)
            for a in OPTIONAL_GEOMETRY.get(tag, ()):
                if el.get(a) is not None:
                    geo[a] = _number(el.get(a), w, a)
            if tag == "rect" and (geo["width"] <= 0 or geo["height"] <= 0):
                raise ImageRefused(f"{w}: width and height must be positive")
            if tag == "circle" and geo["r"] <= 0:
                raise ImageRefused(f"{w}: r must be positive")
        shape = Shape(tag, geo, fill, stroke, sw, attrs["stroke-linecap"], attrs["stroke-linejoin"], attrs["fill-rule"])
        if not _draws(shape):
            raise ImageRefused(f"{w}: draws no geometry (no two distinct points to stroke, no area to fill)")
        shapes.append(shape)
        if len(shapes) > MAX_SHAPES:
            raise ImageRefused(f"{where}: more than {MAX_SHAPES} shapes")
    if not shapes:
        raise ImageRefused(f"{where}: no shapes")
    icon = Icon(tuple(vb), shapes, taken)  # type: ignore[arg-type]
    # geometry off the viewBox is clipped where it is drawn: a sign the coordinates are wrong
    x0, y0, x1, y1 = _extent(icon)
    vx, vy, vw, vh = icon.view_box
    tol = 0.01 * max(vw, vh)
    if x0 < vx - tol or y0 < vy - tol or x1 > vx + vw + tol or y1 > vy + vh + tol:
        raise ImageRefused(f"{where}: the shapes reach {x0:g},{y0:g} to {x1:g},{y1:g}, outside the viewBox {vx:g} {vy:g} {vw:g} {vh:g}; they would be clipped")
    return icon


# --- geometry: everything flattened to polygons ---------------------------------------------


def _arc_points(x1, y1, rx, ry, phi_deg, fa, fs, x2, y2) -> list[tuple[float, float]]:
    """SVG elliptical arc (endpoint form, SVG 1.1 F.6.5) flattened, excluding the start."""
    if (x1, y1) == (x2, y2):
        return []
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    phi = math.radians(phi_deg % 360)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy) -> float:
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(4, int(abs(dt) / (math.pi / 32)) + 1)
    out = []
    for k in range(1, n + 1):
        t = t1 + dt * k / n
        x = cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp
        y = cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp
        out.append((x, y))
    out[-1] = (x2, y2)
    return out


def _bezier(p0, p1, p2, p3=None, n: int = 24) -> list[tuple[float, float]]:
    out = []
    for k in range(1, n + 1):
        t = k / n
        u = 1 - t
        if p3 is None:
            x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
            y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        else:
            x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
            y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
        out.append((x, y))
    return out


def subpaths(shape: Shape) -> list[tuple[list[tuple[float, float]], bool]]:
    """The shape as flattened subpaths: (points, closed)."""
    g = shape.geometry
    if shape.tag == "rect":
        x, y, w, h = g["x"], g["y"], g["width"], g["height"]
        rx, ry = g.get("rx"), g.get("ry")
        if rx is None and ry is None:
            return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
        rx = ry if rx is None else rx
        ry = rx if ry is None else ry
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        pts: list[tuple[float, float]] = []
        for (cx, cy, a0) in ((x + w - rx, y + ry, -90), (x + w - rx, y + h - ry, 0), (x + rx, y + h - ry, 90), (x + rx, y + ry, 180)):
            for k in range(9):
                t = math.radians(a0 + 90 * k / 8)
                pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
        return [(pts, True)]
    if shape.tag == "circle":
        n = 96
        return [([(g["cx"] + g["r"] * math.cos(2 * math.pi * k / n), g["cy"] + g["r"] * math.sin(2 * math.pi * k / n)) for k in range(n)], True)]
    if shape.tag == "line":
        return [([(g["x1"], g["y1"]), (g["x2"], g["y2"])], False)]
    if shape.tag == "polygon":
        return [(list(g["points"]), True)]
    out: list[tuple[list[tuple[float, float]], bool]] = []
    cur: list[tuple[float, float]] = []
    x = y = sx = sy = 0.0
    last_ctrl: tuple[float, float] | None = None
    last_cmd = ""

    def finish(closed: bool) -> None:
        nonlocal cur
        if len(cur) >= 2:
            out.append((cur, closed))
        cur = []

    for cmd, a in g["d"]:
        up, rel = cmd.upper(), cmd.islower()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == "M":
            finish(False)
            x, y = ox + a[0], oy + a[1]
            sx, sy = x, y
            cur = [(x, y)]
        elif up == "Z":
            if cur:
                finish(True)
            x, y = sx, sy
            cur = [(x, y)]
        elif up in ("L", "H", "V"):
            if up == "L":
                x, y = ox + a[0], oy + a[1]
            elif up == "H":
                x = (x if rel else 0.0) + a[0]
            else:
                y = (y if rel else 0.0) + a[0]
            cur.append((x, y))
        elif up in ("C", "S"):
            if up == "C":
                c1 = (ox + a[0], oy + a[1])
                c2, end = (ox + a[2], oy + a[3]), (ox + a[4], oy + a[5])
            else:
                c1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl and last_cmd in ("C", "S") else (x, y)
                c2, end = (ox + a[0], oy + a[1]), (ox + a[2], oy + a[3])
            cur += _bezier((x, y), c1, c2, end)
            last_ctrl = c2
            x, y = end
        elif up in ("Q", "T"):
            if up == "Q":
                c1, end = (ox + a[0], oy + a[1]), (ox + a[2], oy + a[3])
            else:
                c1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl and last_cmd in ("Q", "T") else (x, y)
                end = (ox + a[0], oy + a[1])
            cur += _bezier((x, y), c1, end)
            last_ctrl = c1
            x, y = end
        elif up == "A":
            end = (ox + a[5], oy + a[6])
            cur += _arc_points(x, y, a[0], a[1], a[2], int(a[3]), int(a[4]), end[0], end[1])
            x, y = end
        if up not in ("C", "S", "Q", "T"):
            last_ctrl = None
        last_cmd = up
    finish(False)
    return out


def _stroke_polygons(points: list[tuple[float, float]], closed: bool, width: float, cap: str, join: str) -> list[list[tuple[float, float]]]:
    """A stroked polyline as polygons whose nonzero union is the stroke: one quad per
    segment, a disc or wedge at each join, caps at open ends."""
    hw = width / 2
    pts = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    if closed and len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    polys: list[list[tuple[float, float]]] = []

    def disc(c) -> list[tuple[float, float]]:
        n = 24
        return [(c[0] + hw * math.cos(2 * math.pi * k / n), c[1] + hw * math.sin(2 * math.pi * k / n)) for k in range(n)]

    if len(pts) == 1:
        return [disc(pts[0])] if cap == "round" else []
    segs = list(zip(pts, pts[1:] + ([pts[0]] if closed else [])))
    normals = []
    for (x1, y1), (x2, y2) in segs:
        L = math.hypot(x2 - x1, y2 - y1)
        nx, ny = -(y2 - y1) / L * hw, (x2 - x1) / L * hw
        normals.append((nx, ny))
        polys.append([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)])
    # joins at interior vertices
    n = len(segs)
    joints = range(n) if closed else range(1, n)
    for k in joints:
        prev = (k - 1) % n
        c = segs[k][0]
        if join == "round":
            polys.append(disc(c))
            continue
        (n1x, n1y), (n2x, n2y) = normals[prev], normals[k]
        cross = n1x * n2y - n1y * n2x
        side = 1 if cross > 0 else -1  # the outer side of the turn
        a = (c[0] - side * n1x, c[1] - side * n1y)
        b = (c[0] - side * n2x, c[1] - side * n2y)
        wedge = [c, a, b]
        if join == "miter":
            # the miter tip, limited at SVG's default stroke-miterlimit 4
            d1 = (segs[prev][1][0] - segs[prev][0][0], segs[prev][1][1] - segs[prev][0][1])
            d2 = (segs[k][1][0] - segs[k][0][0], segs[k][1][1] - segs[k][0][1])
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            cos_t = max(-1.0, min(1.0, (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)))
            theta = math.pi - math.acos(cos_t)  # interior angle between the segments
            if theta > 1e-6 and 1 / math.sin(theta / 2) <= 4:
                mx, my = (a[0] + b[0]) / 2 - c[0], (a[1] + b[1]) / 2 - c[1]
                ml = math.hypot(mx, my)
                if ml > 1e-12:
                    tip_len = hw / math.sin(theta / 2)
                    tip = (c[0] + mx / ml * tip_len, c[1] + my / ml * tip_len)
                    wedge = [c, a, tip, b]
        polys.append(wedge)
    if not closed:
        for end, (seg, toward_out) in ((pts[0], (segs[0], -1)), (pts[-1], (segs[-1], 1))):
            if cap == "round":
                polys.append(disc(end))
            elif cap == "square":
                (x1, y1), (x2, y2) = seg
                L = math.hypot(x2 - x1, y2 - y1)
                ux, uy = (x2 - x1) / L * hw * toward_out, (y2 - y1) / L * hw * toward_out
                nx, ny = -(y2 - y1) / L * hw, (x2 - x1) / L * hw
                polys.append([(end[0] + nx, end[1] + ny), (end[0] + nx + ux, end[1] + ny + uy), (end[0] - nx + ux, end[1] - ny + uy), (end[0] - nx, end[1] - ny)])
    return [_ccw(p) for p in polys]


def _ccw(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
    a = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))
    return poly if a >= 0 else poly[::-1]


def _draws(shape: Shape) -> bool:
    """Whether the shape marks the page: a stroke needs two distinct points, a fill a
    subpath with extent in both directions."""
    for pts, _ in subpaths(shape):
        distinct = set(pts)
        if shape.stroke != "none" and len(distinct) >= 2:
            return True
        if shape.fill != "none" and len(distinct) >= 3:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            if max(xs) > min(xs) and max(ys) > min(ys):
                return True
    return False


def _extent(icon: Icon) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for s in icon.shapes:
        hw = s.stroke_width / 2 if s.stroke != "none" else 0
        for pts, _ in subpaths(s):
            xs += [p[0] - hw for p in pts] + [p[0] + hw for p in pts]
            ys += [p[1] - hw for p in pts] + [p[1] + hw for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# --- rasterising: a scanline filler, nonzero and evenodd ----------------------------------


def _coverage(polys: list[list[tuple[float, float]]], rule: str, w: int, h: int) -> bytearray:
    """One byte per pixel (0 or 255) at sample centres, for polygons in pixel space."""
    edges = []
    for poly in polys:
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            if y1 == y2:
                continue
            d = 1 if y2 > y1 else -1
            if y1 > y2:
                x1, y1, x2, y2 = x2, y2, x1, y1
            edges.append((y1, y2, x1, (x2 - x1) / (y2 - y1), d))
    buf = bytearray(w * h)
    if not edges:
        return buf
    edges.sort()
    ymin = max(0, math.floor(edges[0][0]))
    ymax = min(h, math.ceil(max(e[1] for e in edges)) + 1)
    for row in range(ymin, ymax):
        yc = row + 0.5
        xs = [(x0 + (yc - y0) * slope, d) for (y0, y1, x0, slope, d) in edges if y0 <= yc < y1]
        if not xs:
            continue
        xs.sort()
        wind = 0
        base = row * w
        for (xa, da), (xb, _) in itertools.pairwise(xs):
            wind += da
            inside = (wind != 0) if rule == "nonzero" else (wind % 2 != 0)
            if not inside:
                continue
            a = max(0, math.ceil(xa - 0.5))
            b = min(w, math.ceil(xb - 0.5))
            if b > a:
                buf[base + a:base + b] = b"\xff" * (b - a)
    return buf


SUPERSAMPLE = 4


def rasterise(icon: Icon, hexes: dict[str, str], width_px: int, height_px: int) -> Image.Image:
    """The icon as an RGBA image of width_px x height_px, its viewBox fitted to the image
    (the caller keeps the aspect), every role resolved through `hexes`."""
    ss = SUPERSAMPLE
    W, H = width_px * ss, height_px * ss
    vx, vy, vw, vh = icon.view_box
    sx, sy = W / vw, H / vh

    def tx(pts):
        return [((p[0] - vx) * sx, (p[1] - vy) * sy) for p in pts]

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for s in icon.shapes:
        parts = subpaths(s)
        if s.fill != "none":
            polys = [tx(p) for p, _ in parts if len(p) >= 3]
            mask = Image.frombytes("L", (W, H), bytes(_coverage(polys, s.fill_rule, W, H)))
            canvas.paste(Image.new("RGBA", (W, H), "#" + hexes[s.fill]), (0, 0), mask)
        if s.stroke != "none":
            polys = []
            for p, closed in parts:
                polys += _stroke_polygons(tx(p), closed, s.stroke_width * sx, s.linecap, s.linejoin)
            mask = Image.frombytes("L", (W, H), bytes(_coverage(polys, "nonzero", W, H)))
            canvas.paste(Image.new("RGBA", (W, H), "#" + hexes[s.stroke]), (0, 0), mask)
    return canvas.resize((width_px, height_px), Image.Resampling.BOX)


def _fmt(v: float) -> str:
    return repr(round(v, 4)).rstrip("0").rstrip(".") if "." in repr(round(v, 4)) else repr(round(v, 4))


#: the emitted drawing's longer side, in user units. LibreOffice 24.2 draws an SVG part
#: whose width and height are a few units (viewBox "0 0 10 10") inset by about 3 px in a
#: 69 px box, so a correct icon read as 6.5% differing; the same shapes at 100 units drew
#: with 0.0% (PORT_AUDIT.md, exhibit fidelity round 5). Every icon is therefore written at
#: this size, whatever viewBox the model chose.
EMIT_UNITS = 1000.0


def _normalised(icon: Icon) -> tuple[float, float, float]:
    """(scale, width, height) mapping the viewBox onto 0 0 width height, longer side EMIT_UNITS."""
    vw, vh = icon.view_box[2], icon.view_box[3]
    k = EMIT_UNITS / max(vw, vh)
    return k, vw * k, vh * k


def svg_bytes(icon: Icon, hexes: dict[str, str]) -> bytes:
    """The file's SVG, re-written from the parsed shapes (never the model's text): roles
    resolved to the guide's colours, every coordinate mapped onto a viewBox of
    0 0 width height whose longer side is EMIT_UNITS, that size as the drawing's size."""
    vx, vy = icon.view_box[0], icon.view_box[1]
    k, ow, oh = _normalised(icon)

    def ax(v: float) -> float:
        return (v - vx) * k

    def ay(v: float) -> float:
        return (v - vy) * k

    def seg(cmd: str, a: list[float]) -> list[float]:
        up, rel = cmd.upper(), cmd.islower()
        if up == "Z":
            return []
        if up == "A":
            x, y = (a[5] * k, a[6] * k) if rel else (ax(a[5]), ay(a[6]))
            return [a[0] * k, a[1] * k, a[2], a[3], a[4], x, y]
        if up == "H":
            return [a[0] * k if rel else ax(a[0])]
        if up == "V":
            return [a[0] * k if rel else ay(a[0])]
        out = []
        for i in range(0, len(a), 2):
            out += [a[i] * k, a[i + 1] * k] if rel else [ax(a[i]), ay(a[i + 1])]
        return out

    root = etree.Element(f"{{{SVG_NS}}}svg", nsmap={None: SVG_NS})
    root.set("viewBox", f"0 0 {_fmt(ow)} {_fmt(oh)}")
    root.set("width", _fmt(ow))
    root.set("height", _fmt(oh))
    for s in icon.shapes:
        el = etree.SubElement(root, f"{{{SVG_NS}}}{s.tag}")
        g = s.geometry
        if s.tag == "path":
            el.set("d", " ".join(c + (" " + " ".join(_fmt(v) for v in seg(c, a)) if a else "") for c, a in g["d"]))
        elif s.tag == "polygon":
            el.set("points", " ".join(f"{_fmt(ax(x))},{_fmt(ay(y))}" for x, y in g["points"]))
        else:
            for key, v in g.items():
                el.set(key, _fmt(ax(v) if key in ("x", "cx", "x1", "x2") else ay(v) if key in ("y", "cy", "y1", "y2") else v * k))
        el.set("fill", "none" if s.fill == "none" else "#" + hexes[s.fill])
        if s.tag in ("path", "polygon") and s.fill != "none":
            el.set("fill-rule", s.fill_rule)
        el.set("stroke", "none" if s.stroke == "none" else "#" + hexes[s.stroke])
        if s.stroke != "none":
            el.set("stroke-width", _fmt(s.stroke_width * k))
            el.set("stroke-linecap", s.linecap)
            el.set("stroke-linejoin", s.linejoin)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


# --- picture files ----------------------------------------------------------------------------


def read_picture(path: str, where: str) -> tuple[str, int, int]:
    """(format extension, width px, height px) of a picture file, or ImageRefused."""
    p = Path(path)
    if not p.is_file():
        raise ImageRefused(f"{where}: {path} is not a file")
    size = p.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ImageRefused(f"{where}: {path} is {size} bytes; a page picture is at most {MAX_IMAGE_BYTES}")
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(p) as im:
            fmt = im.format
            w, h = im.size
            im.verify()
        with Image.open(p) as im:
            im.load()
    except Image.DecompressionBombError:
        raise ImageRefused(f"{where}: {path} declares more than {MAX_IMAGE_PIXELS} pixels") from None
    except Exception as error:  # noqa: BLE001  # Pillow raises many types for a damaged file; each is a refusal
        raise ImageRefused(f"{where}: {path} is not a readable picture ({type(error).__name__}: {error})") from None
    if fmt not in IMAGE_FORMATS:
        raise ImageRefused(f"{where}: {path} is {fmt}; a page picture is PNG, JPEG or GIF (an icon is an SVG under \"svg\")")
    if w < 1 or h < 1:
        raise ImageRefused(f"{where}: {path} has no pixels")
    return IMAGE_FORMATS[fmt], w, h


# --- a slide's picture entry ------------------------------------------------------------------


def role_extent_emu(guide: dict, role: str, lines: int, where: str) -> int:
    """A box dimension from the guide: a spacing role's size, or a type role's line pitch
    times `lines`, at full scale (the solver's own resolution)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fractions import Fraction

    import layout as L
    try:
        if role.startswith("space."):
            if lines != 1:
                raise ImageRefused(f"{where}: lines multiplies a type role's line pitch; a spacing role is one size")
            return L.space_emu(L.load_guide(guide), role, Fraction(1), "x")
        if role.startswith("type."):
            return int(L.resolve_type_entry(L.load_guide(guide), role, Fraction(1)).pitch_emu) * lines
    except L.LayoutContractError as error:
        raise ImageRefused(f"{where}: {error}") from None
    raise ImageRefused(f"{where}: {role!r} is neither a spacing role (space.*) nor a type role (type.*)")


@dataclass
class Picture:
    """A validated picture entry: what the emitter writes and how big it is."""
    where: str
    kind: str                     # "file" | "svg"
    path: str | None
    icon: Icon | None
    aspect: float                 # width / height
    entry: dict
    defaults_taken: list[str]

    def emit_fields(self) -> dict:
        out = {"aspect": self.aspect, "align": self.entry.get("align", "center"), "valign": self.entry.get("valign", "middle")}
        if self.kind == "file":
            out["path"] = self.path
        else:
            out["svg_source"] = self.entry["svg"]
        return out


def picture(entry, where: str, guide: dict | None = None) -> Picture:
    """One `slide.images` entry (or an annotation cell's image) validated at the boundary."""
    if not isinstance(entry, dict):
        raise ImageRefused(f"{where}: expected an object with \"path\" or \"svg\"")
    extra = sorted(set(entry) - ENTRY_KEYS)
    if extra:
        raise ImageRefused(f"{where}: unknown keys {extra}; a picture takes {sorted(ENTRY_KEYS)}")
    sources = [k for k in ("path", "svg") if k in entry]
    if len(sources) != 1:
        raise ImageRefused(f"{where}: exactly one source, \"path\" (a PNG, JPEG or GIF file) or \"svg\" (an icon in the SVG subset); got {sources or 'none'}")
    taken: list[str] = []
    for k, choices in (("align", ALIGNS), ("valign", VALIGNS)):
        if k in entry and entry[k] not in choices:
            raise ImageRefused(f"{where}: {k} {entry[k]!r} not in {list(choices)}")
        if k not in entry:
            taken.append(f"{k}: {DEFAULTS[k]}")
    if "lines" in entry:
        if type(entry["lines"]) is not int or entry["lines"] < 1:
            raise ImageRefused(f"{where}: lines is a whole number of lines, at least 1")
        if not str(entry.get("height_role", entry.get("width_role", ""))).startswith("type."):
            raise ImageRefused(f"{where}: lines multiplies a type role's line pitch; give height_role or width_role a type role")
    if "path" in entry:
        if not isinstance(entry["path"], str) or not entry["path"]:
            raise ImageRefused(f"{where}: path must be a file path")
        _, w, h = read_picture(entry["path"], where)
        return Picture(where, "file", entry["path"], None, w / h, entry, taken)
    src = entry["svg"]
    if not isinstance(src, str) or not src:
        raise ImageRefused(f"{where}: svg must be the path of an .svg file")
    p = Path(src)
    if not p.is_file():
        raise ImageRefused(f"{where}: {src} is not a file")
    if p.stat().st_size > MAX_SVG_BYTES:
        raise ImageRefused(f"{where}: {src} is {p.stat().st_size} bytes; an icon is at most {MAX_SVG_BYTES}")
    icon = parse_svg(p.read_bytes(), f"{where} ({src})")
    if guide is not None:
        hexes(icon, guide, where)
    return Picture(where, "svg", None, icon, icon.aspect, entry, taken + icon.defaults_taken)


def hexes(icon: Icon, guide: dict, where: str) -> dict[str, str]:
    """Every role the icon paints with, as the guide's hex; an unknown role is refused."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from emit_pptx import Guide as EmitGuide
    eg = guide if isinstance(guide, EmitGuide) else EmitGuide(guide)
    out = {}
    for r in icon.roles():
        try:
            out[r] = eg.hex(r, where=f"{where} icon").upper()
        except SystemExit as error:  # emit_pptx.SpecError: the guide's own refusal, by name
            raise ImageRefused(str(error)) from None
    return out


def box_size(pic: Picture, guide: dict) -> dict | None:
    """The element's size in EMU from its role (scale class fixed), or None when the box
    is left to the solver (the picture is then fitted inside it at its own aspect)."""
    e = pic.entry
    lines = int(e.get("lines", 1))
    if "height_role" in e and "width_role" in e:
        # a box of both sizes (a column of icons of differing aspect lines up): the picture
        # is fitted inside it at its own aspect, placed by align and valign
        return {"width_emu": role_extent_emu(guide, e["width_role"], lines if str(e["width_role"]).startswith("type.") else 1, pic.where),
                "height_emu": role_extent_emu(guide, e["height_role"], lines if str(e["height_role"]).startswith("type.") else 1, pic.where)}
    if "height_role" in e:
        h = role_extent_emu(guide, e["height_role"], lines, pic.where)
        return {"width_emu": max(1, round(h * pic.aspect)), "height_emu": h}
    if "width_role" in e:
        w = role_extent_emu(guide, e["width_role"], lines, pic.where)
        return {"width_emu": w, "height_emu": max(1, round(w / pic.aspect))}
    return None


def placed_box(box: tuple[int, int, int, int] | list[int], aspect: float, align: str, valign: str) -> tuple[int, int, int, int]:
    """The picture's own rectangle inside its box: as large as fits at its aspect."""
    x, y, w, h = (int(v) for v in box)
    if w <= 0 or h <= 0:
        return x, y, 0, 0
    if w / h > aspect:
        pw, ph = round(h * aspect), h
    else:
        pw, ph = w, round(w / aspect)
    px = {"left": x, "center": x + (w - pw) // 2, "right": x + w - pw}[align]
    py = {"top": y, "middle": y + (h - ph) // 2, "bottom": y + h - ph}[valign]
    return px, py, pw, ph


def fallback_png(icon: Icon, hx: dict[str, str], w_emu: int, h_emu: int) -> bytes:
    wpx = max(8, round(w_emu / EMU_PER_INCH * FALLBACK_PPI))
    hpx = max(8, round(h_emu / EMU_PER_INCH * FALLBACK_PPI))
    buf = io.BytesIO()
    rasterise(icon, hx, wpx, hpx).save(buf, "PNG")
    return buf.getvalue()


# --- after the render: did the renderer draw it? ------------------------------------------


#: a pixel counts as differing when no pixel of the picture as written within one pixel
#: of it is within this of it on every channel (of 255); the share of differing pixels a
#: picture may show is RENDER_TOLERANCE. Measured (PORT_AUDIT.md, exhibit fidelity) on
#: LibreOffice 24.2 at 1600 px: 14 pictures drawn as written (an SVG icon, two PDF crops,
#: eleven pptx logos down to 0.25 in tall) differ by 0 to 1.46%; an icon whose SVG part
#: draws nothing differs by 31.9%. 5% sits between; unmeasured in PowerPoint.
CHANNEL_TOLERANCE = 64
RENDER_TOLERANCE = 0.05
#: a crop is compared at most this many pixels on its longer side (both images scaled
#: alike): the check reads whether the picture is there, not its finest detail
CHECK_MAX_PX = 240
#: the fewest render pixels a picture may be drawn across on either side; below this the
#: render cannot show whether it is there (a 20000 x 1 logo drawn 69 x 0 px)
MIN_CHECK_PX = 4


def render_check(elements: list[dict], png: str, page_w_emu: int, guide: dict) -> list[dict]:
    """For every picture on the page: the share of its box's pixels the render drew
    differently from the picture as written (an SVG icon rasterised here at the render's
    size, a file scaled to it), over the render's own background where the picture is
    transparent. Returns one record per picture: {"id", "differ_share", "status"}."""
    out = []
    with Image.open(png) as im:
        page = im.convert("RGB")
    k = page.width / page_w_emu
    for el in elements:
        if el.get("kind") != "image" or not (el.get("path") or el.get("svg_source")):
            continue
        x, y, w, h = placed_box(el["box"], el["aspect"], el.get("align", "center"), el.get("valign", "middle"))
        x0, y0 = round(x * k), round(y * k)
        x1, y1 = round((x + w) * k), round((y + h) * k)
        if x1 - x0 < MIN_CHECK_PX or y1 - y0 < MIN_CHECK_PX:
            # a picture this small is not seen on the page either: refused, never passed
            out.append({"id": el["id"], "status": "too small to check", "box_px": [x0, y0, x1 - x0, y1 - y0]})
            continue
        crop = page.crop((x0, y0, x1, y1))
        if el.get("svg_source"):
            icon = parse_svg(Path(el["svg_source"]).read_bytes(), el["id"])
            want = rasterise(icon, hexes(icon, guide, el["id"]), x1 - x0, y1 - y0)
        else:
            with Image.open(el["path"]) as src:
                want = src.convert("RGBA").resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
        # the background: the render's most common colour where the picture is clear
        alpha = want.getchannel("A")
        clear = [p for p, a in zip(crop.getdata(), alpha.getdata()) if a == 0]
        bg = max(set(clear), key=clear.count) if clear else (255, 255, 255)
        flat = Image.new("RGB", want.size, bg)
        flat.paste(want, (0, 0), want)
        if max(flat.size) > CHECK_MAX_PX:
            k2 = CHECK_MAX_PX / max(flat.size)
            size = (max(1, round(flat.width * k2)), max(1, round(flat.height * k2)))
            flat, crop = flat.resize(size, Image.Resampling.BOX), crop.resize(size, Image.Resampling.BOX)
        # a drawn pixel matches when the picture as written has a pixel within one pixel of
        # it within the channel tolerance: a renderer's resampling may shift a logo's fine
        # detail by a pixel, which is drawing it as written; a missing picture is not
        got, want_px = crop.load(), flat.load()
        cw, ch = crop.size
        diff = 0
        for yy in range(ch):
            for xx in range(cw):
                r1, g1, b1 = got[xx, yy]
                ok = False
                for dy in (0, -1, 1):
                    for dx in (0, -1, 1):
                        u, v = xx + dx, yy + dy
                        if 0 <= u < cw and 0 <= v < ch:
                            r2, g2, b2 = want_px[u, v]
                            if max(abs(r1 - r2), abs(g1 - g2), abs(b1 - b2)) <= CHANNEL_TOLERANCE:
                                ok = True
                                break
                    if ok:
                        break
                diff += not ok
        share = diff / (cw * ch)
        out.append({"id": el["id"], "box_px": [x0, y0, x1 - x0, y1 - y0], "differ_share": round(share, 4),
                    "status": "drawn as written" if share <= RENDER_TOLERANCE else "not drawn as written"})
    return out


# --- the reference's pictures ------------------------------------------------------------------


#: a PDF region is rendered between these densities: below 72 a logo is coarser than the
#: page itself; 1200 is past any print use, and the region's pixels are capped as well
DPI_RANGE = (72, 1200)
#: characters a PDF box must hold for its text layer to state the size: fewer is a label,
#: not a table (asserted; a 3 x 3 grid of two-digit figures already holds 18)
TEXT_LAYER_MIN_CHARS = 20
PDFTOPPM_TIMEOUT_S = 120


def _package(ref: str):
    """The reference as an ooxml.Package (member counts and sizes capped, entities not
    resolved), or ImageRefused naming why it cannot be read."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ooxml
    try:
        return ooxml.Package(ref)
    except (zipfile.BadZipFile, ValueError, OSError) as error:
        raise ImageRefused(f"{ref}: not a readable .pptx package ({type(error).__name__}: {error})") from None


def _pdf(ref: str):
    import pdfplumber
    try:
        return pdfplumber.open(ref)
    except Exception as error:  # noqa: BLE001  # pdfminer raises many types for a damaged file; each is a refusal
        raise ImageRefused(f"{ref}: not a readable PDF ({type(error).__name__}: {error})") from None


def list_pictures(ref: str) -> list[dict]:
    """Every picture the reference holds, with an id `extract` takes."""
    out = []
    if ref.lower().endswith(".pptx"):
        pkg = _package(ref)
        with pkg.zip:
            uses: dict[str, list[int]] = {}
            for n in sorted(pkg.names):
                m = re.fullmatch(r"ppt/slides/_rels/slide(\d+)\.xml\.rels", n)
                if not m:
                    continue
                slide = f"ppt/slides/slide{m.group(1)}.xml"
                try:
                    info = pkg.root(n).getroottree().docinfo
                    rels = pkg.rels(slide)
                except etree.XMLSyntaxError as error:
                    raise ImageRefused(f"{ref}: {n} is not well-formed XML ({error}); which pictures the slide uses cannot be told") from None
                if info.doctype or info.internalDTD is not None:
                    raise ImageRefused(f"{ref}: {n} declares a DOCTYPE; a package part takes none (OPC), and its entities are not read")
                for _, target in rels.values():
                    if target.startswith("ppt/media/"):
                        uses.setdefault(target, []).append(int(m.group(1)))
            for n in sorted(pkg.names):
                if not n.startswith("ppt/media/"):
                    continue
                info = pkg.zip.getinfo(n)
                entry = {"id": n.split("/")[-1], "bytes": info.file_size, "slides": sorted(set(uses.get(n, [])))}
                if info.file_size <= MAX_IMAGE_BYTES:
                    try:
                        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
                        with Image.open(io.BytesIO(pkg.zip.read(n))) as im:
                            entry.update({"format": im.format, "px": list(im.size)})
                    except Exception as error:  # noqa: BLE001  # an unreadable member is listed as such, by name
                        entry["format"] = f"unreadable ({type(error).__name__})"
                else:
                    entry["format"] = f"not read: larger than {MAX_IMAGE_BYTES} bytes"
                out.append(entry)
        return out
    with _pdf(ref) as pdf:
        for pn, page in enumerate(pdf.pages, 1):
            for k, im in enumerate(page.images):
                out.append({"id": f"p{pn}-{im.get('name') or k}", "page": pn,
                            "bbox_pt": [round(im["x0"], 2), round(im["top"], 2), round(im["x1"], 2), round(im["bottom"], 2)],
                            "px": list(im.get("srcsize") or [])})
    return out


def extract(ref: str, out: str, pic_id: str | None, page: int | None, bbox: list[float] | None, dpi: int = 600) -> dict:
    """Write one picture of the reference to `out` as PNG (a PDF region rendered at `dpi`)."""
    dest = Path(out)
    if ref.lower().endswith(".pptx"):
        if not pic_id or page is not None:
            raise ImageRefused("a .pptx picture is named by its --id from `images.py list`")
        name = "ppt/media/" + pic_id
        pkg = _package(ref)
        with pkg.zip as z:
            if name not in pkg.names:
                raise ImageRefused(f"{pic_id}: no such picture; `images.py list` names them")
            if z.getinfo(name).file_size > MAX_IMAGE_BYTES:
                raise ImageRefused(f"{pic_id}: larger than {MAX_IMAGE_BYTES} bytes")
            data = z.read(name)
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                if im.format not in IMAGE_FORMATS:
                    raise ImageRefused(f"{pic_id}: {im.format}; only PNG, JPEG and GIF pictures are placed (a vector logo: crop it from a PDF render)")
                im.convert("RGBA").save(dest, "PNG")
        except ImageRefused:
            raise
        except Exception as error:  # noqa: BLE001  # Pillow raises many types for a damaged picture; each is a refusal
            raise ImageRefused(f"{pic_id}: unreadable picture ({type(error).__name__}: {error})") from None
        read_picture(str(dest), pic_id)
        return {"out": str(dest), "source": f"{ref}#{name}"}
    # PDF: the region rendered by poppler, so a vector logo and a masked picture both come out
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not DPI_RANGE[0] <= dpi <= DPI_RANGE[1]:
        raise ImageRefused(f"--dpi {dpi!r}: a region is rendered at {DPI_RANGE[0]} to {DPI_RANGE[1]} dpi")
    with _pdf(ref) as pdf:
        n_pages = len(pdf.pages)
        if pic_id:
            pics = {p["id"]: p for p in list_pictures(ref)}
            if pic_id not in pics:
                raise ImageRefused(f"{pic_id}: no such picture; `images.py list` names them")
            page, bbox = pics[pic_id]["page"], pics[pic_id]["bbox_pt"]
        if page is None or not bbox or len(bbox) != 4 or not all(math.isfinite(v) for v in bbox) or not (bbox[2] > bbox[0] and bbox[3] > bbox[1]):
            raise ImageRefused("a PDF region is --page N and --bbox X0,Y0,X1,Y1 in PDF points from the top-left, X1 > X0 and Y1 > Y0")
        if not 1 <= page <= n_pages:
            raise ImageRefused(f"--page {page}: the PDF has pages 1 to {n_pages}")
        pw, ph = float(pdf.pages[page - 1].width), float(pdf.pages[page - 1].height)
    if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > pw + 0.5 or bbox[3] > ph + 0.5:
        raise ImageRefused(f"--bbox {bbox}: outside page {page}, which is 0,0 to {pw:g},{ph:g} points")
    k = dpi / 72
    wpx, hpx = max(1, int((bbox[2] - bbox[0]) * k)), max(1, int((bbox[3] - bbox[1]) * k))
    if wpx * hpx > MAX_IMAGE_PIXELS:
        raise ImageRefused(f"the region at {dpi} dpi is {wpx} x {hpx} px, over {MAX_IMAGE_PIXELS} pixels; lower --dpi")
    with tempfile.TemporaryDirectory(prefix="images-") as tmp:
        stem = Path(tmp) / "crop"
        cmd = ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), "-singlefile",
               "-x", str(int(bbox[0] * k)), "-y", str(int(bbox[1] * k)), "-W", str(wpx), "-H", str(hpx),
               ref, str(stem)]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=PDFTOPPM_TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            raise ImageRefused(f"pdftoppm did not render page {page} within {PDFTOPPM_TIMEOUT_S} s") from None
        png = stem.with_suffix(".png")
        if done.returncode or not png.exists():
            raise ImageRefused(f"pdftoppm could not render page {page}: {done.stderr.strip()[-300:]}")
        dest.write_bytes(png.read_bytes())
    read_picture(str(dest), "extract")
    return {"out": str(dest), "source": f"{ref}#page={page}&bbox={','.join(str(v) for v in bbox)}", "dpi": dpi,
            "note": "rendered with the page's own background: a logo on a coloured panel keeps that colour"}


#: what a glyph is when the type size of a pasted picture is read off its pixels: a
#: connected run of ink at least this many pixels tall (a smaller one is a comma, a dot or
#: noise), no wider than GLYPH_MAX_ASPECT times its height (a rule or a bar is wider) and
#: no narrower than GLYPH_MIN_ASPECT (a cell's vertical rule; Arial's l is 0.13 of its height)
GLYPH_MIN_PX = 4
GLYPH_MAX_ASPECT = 1.5
GLYPH_MIN_ASPECT = 0.1
#: a pixel is ink when its luma differs from its row's commonest luma by this much (0-255):
#: dark text on a light row and light text on a filled header row alike
INK_CONTRAST = 96
TALL_GLYPHS = "0123456789ABDEFHKLNTbdhklt"


def _picture_box(ref: str, pic_id: str, slide: int) -> tuple[int, int, tuple[float, float, float, float]]:
    """(width EMU, height EMU, srcRect l, t, r, b as fractions) of picture `pic_id` drawn on
    `slide` of a .pptx: the box the reference displays it in, so its pixels map to points."""
    pkg = _package(ref)
    part = f"ppt/slides/slide{slide}.xml"
    if part not in pkg.names:
        raise ImageRefused(f"--slide {slide}: the deck has no {part}")
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
          "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with pkg.zip:
        rels = pkg.rels(part)
        root = pkg.root(part)
    boxes = []
    for pic in root.iter(f"{{{ns['p']}}}pic"):
        blip = pic.find(".//a:blip", ns)
        rid = None if blip is None else blip.get(f"{{{ns['r']}}}embed")
        if rid is None or rid not in rels or rels[rid][1] != "ppt/media/" + pic_id:
            continue
        ext = pic.find("p:spPr/a:xfrm/a:ext", ns)
        if ext is None:
            continue
        src = pic.find(".//a:srcRect", ns)
        crop = tuple(int((src.get(k) if src is not None else None) or 0) / 100_000 for k in ("l", "t", "r", "b"))
        boxes.append((int(ext.get("cx")), int(ext.get("cy")), crop))
    if len(boxes) != 1:
        raise ImageRefused(f"{pic_id}: drawn {len(boxes)} times on slide {slide}; name a slide that draws it once")
    return boxes[0]


def face_file(face: str) -> str:
    """The installed file the text ruler measures `face` with (the face itself or its
    metric-compatible clone), or a refusal naming the face."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import textfit
    try:
        return textfit.default_index().resolve(face).path
    except LookupError as error:
        raise ImageRefused(f"--face {face!r}: {error}") from None


def _tall_height_em(face_path: str) -> float:
    """The median ink height of the glyphs that stand on the baseline and reach the cap or
    ascender line (digits, capitals, ascender letters), as a share of the face's size, read
    from the font file itself."""
    from PIL import ImageFont
    font = ImageFont.truetype(face_path, 1000)
    heights = sorted(font.getbbox(d)[3] - font.getbbox(d)[1] for d in TALL_GLYPHS)
    return heights[len(heights) // 2] / 1000


def _line_tall_heights(glyphs: list[tuple[int, int]]) -> list[int]:
    """Per text line, the height of its tall glyphs: glyphs are (bottom, height); a line is
    the glyphs standing on one baseline (bottoms within a pixel of its commonest bottom),
    and its tall height the 80th percentile of their heights, so a line of digits reads its
    digits and a line of words its capitals and ascenders, not its x-height."""
    bottoms: dict[int, int] = {}
    for b, _ in glyphs:
        bottoms[b] = bottoms.get(b, 0) + 1
    out = []
    taken: set[int] = set()
    for b in sorted(bottoms, key=lambda k: -bottoms[k]):
        if b in taken or bottoms[b] < 3:
            continue
        taken.update((b - 1, b, b + 1))
        heights = sorted(gh for gb, gh in glyphs if abs(gb - b) <= 1)
        if len(heights) >= 3:
            out.append(heights[min(len(heights) - 1, int(0.8 * len(heights)))])
    return out


def _glyphs(im: Image.Image) -> list[tuple[int, int]]:
    """(bottom row, height) in pixels of every glyph-like connected run of ink (4-connected)."""
    gray = im.convert("L")
    w, h = gray.size
    px = gray.load()
    ink = bytearray(w * h)
    for y in range(h):
        row = [px[x, y] for x in range(w)]
        common = max(set(row), key=row.count)
        for x, v in enumerate(row):
            if abs(v - common) >= INK_CONTRAST:
                ink[y * w + x] = 1
    seen = bytearray(w * h)
    out = []
    for start in range(w * h):
        if not ink[start] or seen[start]:
            continue
        stack, seen[start] = [start], 1
        y0 = y1 = start // w
        x0 = x1 = start % w
        while stack:
            k = stack.pop()
            y, x = divmod(k, w)
            y0, y1, x0, x1 = min(y0, y), max(y1, y), min(x0, x), max(x1, x)
            for n in ((k - 1) if x else -1, (k + 1) if x < w - 1 else -1, k - w, k + w):
                if 0 <= n < w * h and ink[n] and not seen[n]:
                    seen[n] = 1
                    stack.append(n)
        gh, gw = y1 - y0 + 1, x1 - x0 + 1
        if GLYPH_MIN_PX <= gh <= 0.25 * h and GLYPH_MIN_ASPECT * gh <= gw <= GLYPH_MAX_ASPECT * gh:
            out.append((y1, gh))
    return out


def text_size(ref: str, face_path: str, face: str, pic_id: str | None = None, slide: int | None = None,
              page: int | None = None, bbox: list[float] | None = None) -> dict:
    """The type size a pasted picture sets its text at, read off its pixels: the commonest
    glyph height (a table's digits) over the face's own digit height, at the scale the reference
    displays the picture. A .pptx picture is read from its own bytes in the box the slide
    draws it in; a PDF region is rendered at 600 dpi. The face is the model's reading of the
    picture; the measurement is this function's. Calibrated on native Arial tables of known
    size rendered by LibreOffice and read back at 100 to 600 dpi (2026-10-26): 10pt read
    10.2 to 10.5, 12pt read 11.5 to 12.6."""
    if ref.lower().endswith(".pptx"):
        if not pic_id or slide is None:
            raise ImageRefused("a .pptx picture is named by --id (from `images.py list`) and the --slide that draws it")
        cx, cy, (cl, ct, cr, cb) = _picture_box(ref, pic_id, slide)
        with tempfile.TemporaryDirectory(prefix="images-") as tmp:
            png = Path(tmp) / "pic.png"
            extract(ref, str(png), pic_id, None, None)
            with Image.open(png) as im:
                im.load()
                full_w, full_h = im.size
                box = (round(cl * full_w), round(ct * full_h), round(full_w * (1 - cr)), round(full_h * (1 - cb)))
                shown = im.convert("RGB").crop(box)
        pt_per_px = cy / 12_700 / max(1, shown.height)
        source = f"{ref}#ppt/media/{pic_id} on slide {slide}, drawn {cx / EMU_PER_INCH:.2f} x {cy / EMU_PER_INCH:.2f} in"
    else:
        if page is not None and bbox and len(bbox) == 4 and not pic_id:
            # a table the PDF draws as text (bain's vector tables) carries its sizes: they
            # are read off the text layer, exactly, and the pixels are read only without it
            with _pdf(ref) as pdf:
                if 1 <= page <= len(pdf.pages):
                    x0, y0, x1, y1 = bbox
                    sizes = [round(float(c["size"]), 1) for c in pdf.pages[page - 1].chars
                             if c.get("text", "").strip() and x0 <= float(c["x0"]) and float(c["x1"]) <= x1 and y0 <= float(c["top"]) and float(c["bottom"]) <= y1]
                    if len(sizes) >= TEXT_LAYER_MIN_CHARS:
                        counts = {s: sizes.count(s) for s in set(sizes)}
                        return {"source": f"{ref} page {page} bbox {bbox}: the PDF's text layer", "face": face, "chars": len(sizes),
                                "sizes_pt": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:5]), "size_pt": min(counts, key=lambda s: (-counts[s], s)),
                                "band_pt": [min(sizes), max(sizes)],
                                "basis": "the commonest size of the characters the PDF's text layer sets inside the box (exact: the file states it)"}
        dpi = 600
        with tempfile.TemporaryDirectory(prefix="images-") as tmp:
            png = Path(tmp) / "region.png"
            done = extract(ref, str(png), pic_id, page, bbox, dpi)
            with Image.open(png) as im:
                shown = im.convert("RGB")
        pt_per_px = 72 / dpi
        source = done["source"]
    glyphs = _glyphs(shown)
    lines = _line_tall_heights(glyphs)
    if len(lines) < 3:
        raise ImageRefused(f"{len(lines)} text lines found in the picture ({len(glyphs)} glyphs): too few to read a type size from")
    counts: dict[int, int] = {}
    for gh in lines:
        counts[gh] = counts.get(gh, 0) + 1
    median = sorted(lines)[len(lines) // 2]
    tall_em = _tall_height_em(face_path)
    size = median * pt_per_px / tall_em
    return {"source": source, "face": face, "glyphs": len(glyphs), "lines": len(lines), "median_line_tall_px": median,
            "commonest_line_heights_px": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:5]),
            "pt_per_px": round(pt_per_px, 4), "tall_height_em": round(tall_em, 4),
            "size_pt": round(size, 1), "band_pt": [round((median - 1) * pt_per_px / tall_em, 1), round((median + 1) * pt_per_px / tall_em, 1)],
            "basis": "per text line, the height of its tall glyphs (digits, capitals, ascenders: the 80th percentile of the glyphs on "
                     "its baseline); the median line over the face's own median tall-glyph height, at the drawn scale; one pixel either way is the band"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("ref")
    b = sub.add_parser("extract")
    b.add_argument("ref")
    b.add_argument("--id", default=None)
    b.add_argument("--page", type=int, default=None)
    b.add_argument("--bbox", default=None)
    b.add_argument("--dpi", type=int, default=600)
    b.add_argument("-o", "--out", required=True)
    t = sub.add_parser("textsize")
    t.add_argument("ref")
    t.add_argument("--face", required=True, help="the face the picture's text is set in, as you read it (e.g. Calibri)")
    t.add_argument("--id", default=None)
    t.add_argument("--slide", type=int, default=None, help=".pptx: the slide that draws the picture")
    t.add_argument("--page", type=int, default=None)
    t.add_argument("--bbox", default=None)
    c = sub.add_parser("check")
    c.add_argument("svg")
    c.add_argument("--guide", default=None)
    c.add_argument("--png", default=None)
    c.add_argument("--height-px", type=int, default=256)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    try:
        if args.cmd == "list":
            cli.in_path(args.ref, "the reference")
            print(json.dumps(list_pictures(args.ref), indent=1))
        elif args.cmd == "extract":
            cli.in_path(args.ref, "the reference")
            cli.guard_args(args, "out")
            cli.out_path(Path(args.out), "picture")
            try:
                bbox = [float(v) for v in args.bbox.split(",")] if args.bbox else None
            except ValueError:
                raise ImageRefused(f"--bbox {args.bbox!r}: four numbers X0,Y0,X1,Y1") from None
            print(json.dumps(extract(args.ref, args.out, args.id, args.page, bbox, args.dpi), indent=1))
        elif args.cmd == "textsize":
            cli.in_path(args.ref, "the reference")
            try:
                bbox = [float(v) for v in args.bbox.split(",")] if args.bbox else None
            except ValueError:
                raise ImageRefused(f"--bbox {args.bbox!r}: four numbers X0,Y0,X1,Y1") from None
            print(json.dumps(text_size(args.ref, face_file(args.face), args.face, args.id, args.slide, args.page, bbox), indent=1))
        else:
            guide = json.loads(Path(args.guide).read_text()) if args.guide else None
            pic = picture({"svg": args.svg}, "check", guide)
            report = {"svg": args.svg, "view_box": list(pic.icon.view_box), "shapes": len(pic.icon.shapes), "roles": pic.icon.roles(),
                      "defaults_taken": pic.icon.defaults_taken}
            if args.png:
                if guide is None:
                    raise ImageRefused("--png needs --guide: the roles are drawn in the guide's colours")
                cli.guard_args(args, "png")
                h = args.height_px
                rasterise(pic.icon, hexes(pic.icon, guide, args.svg), max(1, round(h * pic.aspect)), h).save(args.png)
                report["png"] = args.png
            print(json.dumps(report, indent=1))
    except ImageRefused as error:
        raise SystemExit(f"refused: {error}") from None
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
