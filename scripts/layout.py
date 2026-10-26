#!/usr/bin/env python3
"""Solve a slide spec to exact EMU boxes with MEASURED text fit.

    layout.py solve spec.json --guide guide.json [--scale 1.0] [-o resolved.json]
    layout.py capacity deck.json --slide ID --guide guide.json [--chrome draw] [-o capacity.json]

A ported layout solver (spacing, solver, type styles, validation, table fitter and the
scale descent; PORT_AUDIT.md) in one standalone script; the ruler is textfit.py beside
it. Stdlib + Pillow, uharfbuzz when importable.

THE LOOP at one scale s: resolve every in-use type role (size snapped to the 0.5 pt
grid, spacing and tracking to hundredth-points); probe solve for widths; measure
every paragraph at width - indent - FIT_EPSILON as whole strings; fit every table;
region heights bottom-up (column = sum + gaps + 2 pad, row = max + 2 pad; flexible:
the root, a grid, an ancestor of a flexible child, a region with a weight inside a
column, each floored at its content height; a row's align never makes it flexible);
final solve with the measured intrinsics; re-measure and REFUSE the candidate if any
line text moved; validate (containment, overlap, exceeds_page, overcommit,
zero_dimension, reserved_zone, and per measured element against its own box:
overflow and word_split, each with scale_fixable). THE DESCENT: 1.00, then the 0.01 ladder with scales where
two adjacent hierarchy sizes snap together excluded, truncated at the legibility
floor, searched by bisection (fit is monotone in s: 2,982 measurements, 0
inversions); else Unfittable with the
splittable groups and each table's fitting row prefix. THE SOLVER NEVER CLAMPS: an
oversize measured child overflows and validation refuses. Content is never dropped.

SLIDE SPEC JSON, one full example:
{"page": {"width_emu": 12192000, "height_emu": 6858000,
          "reserved_zones": [{"left": 11049000, "top": 6324600, "width": 762000, "height": 219456, "source": "page-number"}]},
 "bullet_indent_roles": {"0": "space.md", "1": "space.lg"},
 "root": {"type": "region", "id": "root",
   "layout": {"kind": "flex", "direction": "column", "gap_role": "space.md", "pad_role": "space.margin", "align": "stretch", "justify": "start"},
   "children": [
     {"type": "element", "id": "title", "kind": "text", "paragraphs": [{"role": "type.title", "text": "Margins expand on mix"}]},
     {"type": "region", "id": "body", "weight": 4.0,
      "layout": {"kind": "flex", "direction": "row", "gap_role": "space.gutter", "pad_role": null, "align": "start", "justify": "start"},
      "children": [
        {"type": "element", "id": "left", "kind": "text", "weight": 1.0,
         "paragraphs": [{"role": "type.body", "text": "Aftermarket mix rose", "bullet_level": 0}]},
        {"type": "region", "id": "right", "weight": 1.0,
         "layout": {"kind": "grid", "rows": 2, "cols": 1, "gutter_role": "space.sm", "pad_role": null,
                    "areas": [{"child_id": "comps", "row": 0, "col": 0, "row_span": 1, "col_span": 1},
                              {"child_id": "chart", "row": 1, "col": 0, "row_span": 1, "col_span": 1}]},
         "children": [
           {"type": "element", "id": "comps", "kind": "table",
            "table": {"columns": [{"key": "co", "label": "Company", "value_kind": "text"}, {"key": "ev", "label": "EV ($m)", "value_kind": "number"}],
                      "rows": [["Alpha plc", "1,234"], ["Beta Inc", "987"]], "header_rows": 1,
                      "header_role": "type.table_header", "cell_role": "type.table_cell"}},
           {"type": "element", "id": "chart", "kind": "chart"}]}]},
     {"type": "element", "id": "logo", "kind": "image", "scale_class": "fixed", "size": {"width_emu": 914400, "height_emu": 457200}},
     {"type": "element", "id": "foot", "kind": "text", "paragraphs": [{"role": "type.footnote", "text": "Source: company filings"}]}]},
 "splittable_groups": [{"group_id": "comps-rows", "kind": "table_row_range", "node_ids": ["comps"], "row_range": {"start": 0, "end": 2}}]}
Element kinds: text (paragraphs: role, text, bullet_level|null); table (columns
[{key, label, value_kind, width_share?, min_width_role?}], rows, header_rows,
header_role, cell_role, cell_padding_role|null; a width_share is the column's exact
share of the table width, a min_width_role a spacing role it never narrows below, and
the fitter still measures every cell against both and reports any deficit); image | chart | rule (optional size {width_emu|null,
height_emu|null}: a measured extent, null = flexible). Text takes no height; a width on text
is a no-wrap label's measured extent (a component's marker label), and every paragraph must
set on one line in it (sized_text_refusal, violation sized_text_wraps). Every element may carry
weight (flex share, default equal) and scale_class ("scaling" | "fixed": type
resolves at s = 1). Grid tracks are uniform. Node ids are unique and carry no '#'.

GUIDE JSON SUBSET read (extract_style.py's shape; {"value", "provenance"} wrappers
also accepted): typography.families {major, minor, weight_faces?};
typography.roles[role] {size_pt, line_spacing|null, space_before_pt,
space_after_pt, tracking_pt, family ("major" | "minor" | face name), weight,
italic, case}, where a null field takes OOXML's absence value (b/i off, spacing 0,
tracking 0, as_typed, single spacing = 1.2 x size); typography.bullets (level ->
indent_role when present); spacing.steps[role] {"emu": int} | {"value": int} |
int; spacing.baseline_emu|null; floors[family] {floor_pt|null, absolute_floor_pt,
roles} (or a list of those); tables.cell_padding_role | tables.cell_padding_emu
(else OOXML's 45720 EMU default inset).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
from textfit import (  # noqa: E402
    Face,
    FaceIndex,
    MeasuredLine,
    Ruler,
    SubstituteMismatchError,
    UnknownFamilyError,
    UnknownStyleError,
    UnmeasurableTextError,
    advance_emu,
    break_opportunities,
    default_index,
    measure_runs,
    measure_text,
    resolve_measured,
    ruler_for,
)

EMU_PER_POINT = 12_700
EMU_PER_HUNDREDTH_POINT = 127
#: deckgen config/provisional.py:35 - the one font grid; 0.5 pt lands on sz.
FONT_QUANTUM_PT = Fraction(1, 2)
#: Runaway bounds, never design limits. MAX_NODES and MAX_GRID_TRACKS are deckgen's
#: (contracts limits.py). Its MAX_TREE_DEPTH of 5 measured shape containment (depth 3 on
#: three reference decks plus 2 of headroom, docs/measurements/E10-decision.md), not this
#: tree's layout regions, and refused a component placed three regions down (root > body
#: > col > component > its rows); the depth bound here is a finite guard against a
#: runaway tree, and the build reports each page's deepest chain (Spec.deepest).
MAX_TREE_DEPTH, MAX_NODES, MAX_GRID_TRACKS = 12, 400, 64
#: deckgen measure/tolerance.py:157 - what the emit gate forgives between two
#: measurements of the same text; the table fitter's height budget slack.
EMIT_SLACK_EMU = 13
#: OOXML's default a:tcPr marT/marB, 0.05 in (deckgen table_fitter.py:144).
DEFAULT_CELL_INSET_EMU = 45_720
#: PowerPoint's natural line box in a table cell: 1.2 x size, exact to the EMU
#: on 5 sizes x 4 families (deckgen table_fitter.py:100, docs/measurements/
#: E38-decision.md); +254 EMU is the widest family offset above an explicit
#: a:spcPts on that sweep (table_fitter.py:121).
POWERPOINT_LINE_HEIGHT_RATIO = 1.2
REQUESTED_SPACING_SLACK_EMU = 254
NUMERIC_VALUE_KINDS = frozenset({"number", "percent", "currency", "date"})
#: deckgen content/design_scale.py:41 - 0.01 steps from 0.99 down to 0.10, the
#: single step E21-decision.md recommends; the floor stops the descent first.
SCALE_LADDER = tuple(Fraction(n, 100) for n in range(99, 9, -1))
MARGIN_ROLE = "space.margin"
#: Whole-string mean advance for capacity, labelled in the output as such.
REFERENCE_ALPHABET = "the quick brown fox jumps over the lazy dog 0123456789 ($%,.)"
#: What PowerPoint draws when the attribute is absent: b/i off, spcBef/spcAft/spc
#: zero, and single spacing = 1.2 x size (docs/measurements/E16-decision.md 1.2002 em
#: on 7 families, E38-decision.md 1.2000 exact in cells; deckgen decided.py:91).
_ABSENT_TYPE_VALUES = {
    "line_spacing": 1.2, "weight": 400, "italic": False, "space_before_pt": 0.0,
    "space_after_pt": 0.0, "tracking_pt": 0.0, "case": "as_typed",
}

class LayoutContractError(ValueError):
    """The spec or guide contradicts itself; a typed refusal, never geometry."""

class UnknownTokenRoleError(LayoutContractError):
    """A role the guide does not define. Never a default value."""

class FaceRefused(LayoutContractError):
    """No face measures a role as the renderer draws it: the family is missing with no
    stand-in named, or the guide's stand-in is not fc-match's answer. A property of the
    guide, so every page that sets the family is refused, never measured in another face."""

class CandidateRefused(ValueError):
    """One scale candidate cannot be honestly measured (tracked overrun, lines
    that moved under the final solve, a table width that moved)."""

# --- spacing: every token-times-s snap, in one place (deckgen spacing.py) ----------

def decimal_fraction(value: float | int) -> Fraction:
    """The one float door: recover the DECIMAL the JSON carried."""
    return Fraction(str(value))

def quantize_emu(value: Fraction | int) -> int:
    return round(value)  # round-half-even, unbiased (port audit rows C1-C2)

def hundredths(points: float) -> int:
    return round(points * 100)

def paragraph_spacing_emu(space_before_pt: float, space_after_pt: float) -> int:
    """Written a:spcBef + a:spcAft, in the emitter's units (hundredths x 127)."""
    return (hundredths(space_before_pt) + hundredths(space_after_pt)) * EMU_PER_HUNDREDTH_POINT

def checked_scale(scale: float | Fraction) -> Fraction:
    exact = scale if isinstance(scale, Fraction) else decimal_fraction(scale)
    if not 0 < exact <= 10:
        raise LayoutContractError(f"scale {scale} is outside (0, 10]")
    return exact

def snap_pt(value_pt: float | Fraction, scale: float | Fraction) -> Fraction:
    """value x s onto the 0.5 pt grid, half-even, floored at one quantum."""
    value = value_pt if isinstance(value_pt, Fraction) else decimal_fraction(value_pt)
    multiple = round(value * checked_scale(scale) / FONT_QUANTUM_PT)
    if value > 0:
        multiple = max(1, multiple)
    return multiple * FONT_QUANTUM_PT

def snap_sz(value_pt: float | Fraction, scale: float | Fraction) -> int:
    return int(snap_pt(value_pt, scale) * 100)

def snap_hundredths(value_pt: float | Fraction, scale: float | Fraction) -> int:
    value = value_pt if isinstance(value_pt, Fraction) else decimal_fraction(value_pt)
    return round(value * checked_scale(scale) * 100)

def snap_baseline(scaled_emu: Fraction, baseline_emu: int) -> int:
    if scaled_emu <= 0:
        raise ValueError("snap_baseline requires a positive value")
    return max(1, round(scaled_emu / baseline_emu)) * baseline_emu

def gap_emu(guide: "Guide", role: str | None, scale: Fraction, axis: str) -> int:
    """A flex gap; `None` is zero, for rows whose weighted parts share one scale (a
    component's bar split around a marker rule must not open a gap at the cut)."""
    return space_emu(guide, role, scale, axis) if role else 0


def space_emu(guide: Guide, role: str, scale: float | Fraction, axis: str) -> int:
    """One spacing role at `scale`: vertical values snap to the (unscaled)
    baseline grid when the guide has one, horizontal values quantize once."""
    step = guide.steps.get(role)
    if step is None:
        raise UnknownTokenRoleError(f"spacing role {role!r} is not in the guide's steps")
    scaled = step * checked_scale(scale)
    if axis == "y" and guide.baseline_emu and step > 0:
        return snap_baseline(scaled, guide.baseline_emu)
    return quantize_emu(scaled)

# --- the guide subset ----------------------------------------------------------------

@dataclass(frozen=True)
class TypeRole:
    size_pt: float
    line_spacing: float
    space_before_pt: float
    space_after_pt: float
    tracking_pt: float
    family_token: str | None
    family: str
    weight: int
    italic: bool
    case: str

@dataclass(frozen=True)
class Guide:
    major: str
    minor: str
    weight_faces: dict[str, str]
    steps: dict[str, int]
    baseline_emu: int | None
    roles: dict[str, TypeRole]
    floor_by_role: dict[str, float]
    cell_padding_role: str | None
    cell_padding_emu: int | None
    bullet_indent_roles: dict[int, str]
    substitutes: dict[str, str] = field(default_factory=dict)
    absent_roles: dict[str, str] = field(default_factory=dict)
    table_floor_pt: float | None = None

def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value and "provenance" in value:
        return value["value"]
    return value

def _step_emu(value: Any) -> int | None:
    value = _unwrap(value)
    if isinstance(value, dict):
        value = value.get("emu", value.get("value"))
    return None if value is None else int(value)

TABLE_ROLES = ("type.table_cell", "type.table_header")


#: The product safety floor: the smallest size the specimen stays legible at on both render
#: media, measured in deckgen docs/measurements/E45-decision.md (7.0pt for display, body,
#: annotation and chart, Calibri 700 the binding face). No floor, a guide's or a table's,
#: is ever below it; extract_style writes it as every family's absolute_floor_pt and
#: pptx_tools validate --emit reads it with no guide. The one definition.
PRODUCT_SAFETY_FLOOR_PT = 7.0


def table_floor_pt(raw: Mapping[str, Any]) -> float:
    """The one floor every run in a table clears, whatever role it is set in: a written
    table run carries no role, so `pptx_tools validate --emit` can only read where it sits,
    and the build applies the same rule. It is the lowest floor of the table roles'
    families (each max(floor_pt, absolute_floor_pt)), or with no table role the lowest
    family floor; lowered to the house's own table text where its tables are pasted
    pictures and the guide holds that size as measured (tables.picture_text, read off the
    pictures by images.py textsize at completion), never below the absolute floor: the
    largest absolute_floor_pt the guide names, and never below PRODUCT_SAFETY_FLOOR_PT
    whatever the guide says (a guide with no floors, or a picture_text under 7pt)."""
    floors = _unwrap(raw.get("floors")) or {}
    entries = floors.values() if isinstance(floors, dict) else floors
    by_role: dict[str, float] = {}
    lowest: list[float] = []
    absolute = PRODUCT_SAFETY_FLOOR_PT
    for entry in entries:
        entry = _unwrap(entry) or {}
        if not isinstance(entry, dict):
            continue
        absolute = max(absolute, float(entry.get("absolute_floor_pt") or 0.0))
        floor = max(float(entry.get("floor_pt") or 0.0), float(entry.get("absolute_floor_pt") or 0.0))
        if floor <= 0:
            continue
        lowest.append(floor)
        for role in entry.get("roles") or []:
            by_role[role] = floor
    table = min([by_role[r] for r in TABLE_ROLES if r in by_role] or lowest or [0.0])
    pictures = ((_unwrap(raw.get("tables")) or {}).get("picture_text") or {}).get("floor_pt")
    if pictures is not None:
        measured = max(float(pictures), absolute)
        table = min(table, measured) if table else measured
    return max(table, absolute)


def load_guide(raw: Mapping[str, Any]) -> Guide:
    typography = raw.get("typography") or {}
    families = _unwrap(typography.get("families")) or {}
    major, minor = families.get("major"), families.get("minor")
    if not major or not minor:
        raise LayoutContractError("guide names no typography.families.major/minor")
    roles: dict[str, TypeRole] = {}
    for role, entry in (typography.get("roles") or {}).items():
        entry = _unwrap(entry) or {}
        size = entry.get("size_pt")
        if size is None:
            continue  # a role without a size is unusable; a spec naming it is refused
        values = {k: (entry.get(k) if entry.get(k) is not None else v) for k, v in _ABSENT_TYPE_VALUES.items()}
        token = entry.get("family")
        family = {"major": major, "minor": minor, None: major}.get(token, token)
        roles[role] = TypeRole(
            size_pt=float(size), line_spacing=float(values["line_spacing"]),
            space_before_pt=float(values["space_before_pt"]),
            space_after_pt=float(values["space_after_pt"]),
            tracking_pt=float(values["tracking_pt"]),
            family_token=token if token in ("major", "minor") else None,
            family=str(family), weight=int(values["weight"]), italic=bool(values["italic"]),
            case=str(values["case"]),
        )
    spacing = raw.get("spacing") or {}
    steps = {k: v for k, v in ((k, _step_emu(v)) for k, v in (spacing.get("steps") or {}).items()) if v is not None}
    baseline = _step_emu(spacing.get("baseline_emu"))
    floors_raw = raw.get("floors") or {}
    floor_entries = floors_raw.values() if isinstance(floors_raw, dict) else floors_raw
    floor_by_role: dict[str, float] = {}
    for entry in floor_entries:
        entry = _unwrap(entry) or {}
        candidates = [entry.get("floor_pt"), entry.get("absolute_floor_pt")]
        known = [float(c) for c in candidates if c is not None]
        if not known:
            continue
        for role in entry.get("roles") or []:
            floor_by_role[role] = max(known)
    tables = _unwrap(raw.get("tables")) or {}
    bullets_raw = _unwrap(typography.get("bullets")) or {}
    bullet_roles: dict[int, str] = {}
    items = bullets_raw.items() if isinstance(bullets_raw, dict) else ((None, b) for b in bullets_raw)
    for level, spec in items:
        spec = _unwrap(spec) or {}
        if spec.get("indent_role"):
            bullet_roles[int(spec["level"] if level is None else level)] = spec["indent_role"]
    return Guide(
        major=str(major), minor=str(minor), weight_faces=dict(families.get("weight_faces") or {}),
        substitutes=dict(families.get("substitutes") or {}),
        steps=steps, baseline_emu=baseline, roles=roles, floor_by_role=floor_by_role,
        cell_padding_role=tables.get("cell_padding_role"),
        cell_padding_emu=None if tables.get("cell_padding_emu") is None else int(tables["cell_padding_emu"]),
        bullet_indent_roles=bullet_roles,
        absent_roles={k: str((v or {}).get("why", "")) for k, v in (raw.get("absent_roles") or {}).items()},
        table_floor_pt=table_floor_pt(raw),
    )

# --- the slide spec --------------------------------------------------------------

@dataclass(frozen=True)
class Box:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

@dataclass(frozen=True)
class Flex:
    direction: str
    gap_role: str | None  # None: no gap (a component's bar whose parts must touch)
    pad_role: str | None
    align: str
    justify: str
    pads: tuple = (None, None, None, None)  # left, top, right, bottom roles: pad_role on every side, or pad_roles

@dataclass(frozen=True)
class GridArea:
    child_id: str
    row: int
    col: int
    row_span: int
    col_span: int

@dataclass(frozen=True)
class Grid:
    rows: int
    cols: int
    areas: tuple[GridArea, ...]
    gutter_role: str
    pad_role: str | None
    pads: tuple = (None, None, None, None)

@dataclass(frozen=True)
class Paragraph:
    role: str
    text: str
    bullet_level: int | None
    emphasis: bool = False  # the whole paragraph set bold: one run, bold (run_faces)
    # the runs as the emitter writes them: (text, bold, italic), None taking the role's own;
    # each is measured whole in its own face (textfit.measure_runs)
    runs: tuple[tuple[str, bool | None, bool | None], ...] = ()


def run_faces(paragraph: Paragraph) -> tuple[tuple[str, bool | None, bool | None], ...]:
    """The paragraph's runs, the one reading of how its words are set: its own runs, else
    one run of the whole text, bold when the paragraph is emphasis."""
    return paragraph.runs or ((paragraph.text, True if paragraph.emphasis else None, None),)

@dataclass(frozen=True)
class Column:
    key: str
    label: str
    value_kind: str
    width_share: Fraction | None = None  # the spec's share of the table width, taken exactly
    min_width_role: str | None = None  # a spacing role the column never narrows below
    labels: tuple[str, ...] = ()  # one per header row, top row first (header_labels)


def header_labels(column: Mapping[str, Any], header_rows: int, where: str) -> tuple[str, ...]:
    """A column's text in each header row, top row first. One header row takes `label` as
    a string; header_rows N > 1 takes a list of N strings, so a grouped header (an
    "Operating metrics" spanner over two columns) is written, never left blank or repeated."""
    label = column.get("label", column.get("key"))
    if isinstance(label, list):
        if len(label) != max(header_rows, 1) or not all(isinstance(x, str) for x in label):
            raise LayoutContractError(f"{where}: column {column.get('key')!r}: label {label!r} must be {max(header_rows, 1)} string(s), one per header row, top row first")
        return tuple(label)
    if header_rows > 1:
        raise LayoutContractError(f"{where}: column {column.get('key')!r}: header_rows {header_rows} takes each column's label as a list of {header_rows} "
                                  f"strings, top row first (\"label\": [\"Operating metrics\", \"Revenue growth\"]); the same text in adjacent columns "
                                  f"of an upper row is one cell spanning them, and \"\" leaves a cell empty")
    return (str(label),)


def header_texts(columns: Sequence[Mapping[str, Any]], header_rows: int) -> list[str]:
    """The text of every header cell as drawn, a spanner once: what the page says above
    its data (counted as words, read for leakage and for what a mark encloses)."""
    labels = [header_labels(c, header_rows, "table") for c in columns]
    return [labels[c0][r] for r, row in enumerate(header_spans(labels, header_rows)) for c0, _ in row if labels[c0][r]]


def header_spans(labels: Sequence[Sequence[str]], header_rows: int) -> list[list[tuple[int, int]]]:
    """Per header row, its cells as (first, last) column: in every row above the last,
    adjacent columns with the same non-empty text are one cell spanning them (a spanner);
    the last header row, next to the data, keeps one cell per column."""
    out = []
    for r in range(header_rows):
        spans: list[tuple[int, int]] = []
        for c in range(len(labels)):
            text = labels[c][r]
            if r < header_rows - 1 and spans and text and labels[spans[-1][0]][r] == text and spans[-1][1] == c - 1:
                spans[-1] = (spans[-1][0], c)
            else:
                spans.append((c, c))
        out.append(spans)
    return out

@dataclass(frozen=True)
class Table:
    columns: tuple[Column, ...]
    rows: tuple[tuple[str, ...], ...]
    header_rows: int
    header_role: str
    cell_role: str
    cell_padding_role: str | None
    totals_last_row: bool = False  # the emitter bolds it, so the fitter measures it bold
    # every cell in the setting the emitter writes it in, (grid row, column, bold, italic,
    # indent role), header rows first (emit_pptx.table_row_styles, the one reader); a table
    # parsed without them (a component's probe) is measured by header_bold and totals_last_row
    cell_styles: tuple[tuple[int, int, bool, bool, str | None], ...] = ()
    header_bold: bool = False  # the emitter bolds the header row (the guide's or the table's header_bold), so it is measured bold

@dataclass(frozen=True)
class Element:
    id: str
    kind: str
    weight: float | None
    scale_class: str
    paragraphs: tuple[Paragraph, ...]
    table: Table | None
    width_emu: int | None
    height_emu: int | None

@dataclass(frozen=True)
class Region:
    id: str
    layout: Flex | Grid
    children: tuple[Region | Element, ...]
    weight: float | None

@dataclass(frozen=True)
class SplittableGroup:
    group_id: str
    kind: str
    node_ids: tuple[str, ...]
    row_range: dict[str, int] | None

@dataclass(frozen=True)
class Spec:
    page_width: int
    page_height: int
    root: Region
    groups: tuple[SplittableGroup, ...]
    zones: tuple[tuple[Box, str], ...]
    bullet_indent_roles: dict[int, str]
    deepest: tuple[str, ...] = ()  # the longest root-to-node chain of ids, reported by the build

def walk(node: Region | Element, depth: int = 0) -> Iterator[tuple[Region | Element, int]]:
    yield node, depth
    if isinstance(node, Region):
        for child in node.children:
            yield from walk(child, depth + 1)

def _weight(raw: Mapping[str, Any]) -> float | None:
    weight = raw.get("weight")
    if weight is None:
        return None
    if not isinstance(weight, int | float) or isinstance(weight, bool) or weight <= 0:
        raise LayoutContractError(f"node {raw.get('id')!r}: weight must be a positive number")
    return float(weight)

PAD_SIDES = ("left", "top", "right", "bottom")


def _pads(raw: Mapping[str, Any], region_id: str) -> tuple:
    """The region's padding role per side (left, top, right, bottom): `pad_role` on every
    side, or `pad_roles` naming each of the four sides (a role, or null for none). Both at
    once, or a side left out, is refused: a side not named is not zero."""
    per = raw.get("pad_roles")
    if per is None:
        return (raw.get("pad_role"),) * 4
    if raw.get("pad_role") is not None:
        raise LayoutContractError(f"region {region_id!r}: pad_role and pad_roles both given; write one")
    if not isinstance(per, Mapping) or set(per) != set(PAD_SIDES):
        raise LayoutContractError(f"region {region_id!r}: pad_roles names each of {list(PAD_SIDES)} (a spacing role, or null for none), got {per!r}")
    return tuple(per[side] for side in PAD_SIDES)


def _parse_layout(raw: Mapping[str, Any], region_id: str) -> Flex | Grid:
    kind = raw.get("kind", raw.get("layout_type"))
    if kind == "flex":
        flex = Flex(raw["direction"], raw["gap_role"], raw.get("pad_role"), raw.get("align", "stretch"), raw.get("justify", "start"), _pads(raw, region_id))
        if flex.direction not in ("row", "column") or flex.align not in ("start", "center", "end", "stretch") or flex.justify not in ("start", "center", "end", "space_between", "space_around"):
            raise LayoutContractError(f"region {region_id!r}: unsupported flex direction/align/justify (baseline and cross-axis space_between are refused)")
        return flex
    if kind == "grid":
        rows, cols = int(raw["rows"]), int(raw["cols"])
        if not (1 <= rows <= MAX_GRID_TRACKS and 1 <= cols <= MAX_GRID_TRACKS):
            raise LayoutContractError(f"region {region_id!r}: grid tracks outside 1..{MAX_GRID_TRACKS}")
        areas = tuple(GridArea(a["child_id"], int(a["row"]), int(a["col"]), int(a.get("row_span", 1)), int(a.get("col_span", 1))) for a in raw["areas"])
        for a in areas:
            if a.row < 0 or a.col < 0 or a.row_span < 1 or a.col_span < 1 or a.row + a.row_span > rows or a.col + a.col_span > cols:
                raise LayoutContractError(f"region {region_id!r}: area for {a.child_id!r} spans past the grid")
        return Grid(rows, cols, areas, raw["gutter_role"], raw.get("pad_role"), _pads(raw, region_id))
    raise LayoutContractError(f"region {region_id!r}: layout kind must be flex or grid")

def sized_text_refusal(node_id: Any, size: Mapping[str, Any]) -> str | None:
    """The one rule for a size on text that a page spec or a component writes (the build's
    own title band, build_deck.prepare_page, is the build's, not the spec's). A height would
    be a coordinate: a text box is as tall as its measured lines. A width is a no-wrap
    label's measured extent: the solver holds every paragraph to one line in it
    (measured_violations), so a width that is a guess and not a measurement is refused
    there, by measurement."""
    if size.get("height_emu") is None:
        return None
    return (f"text {node_id!r}: size.height_emu is not read on text; a text box is as tall as its measured lines, or takes a "
            "share of a column by weight (inside a region with a weight). Space above or below it is a gap_role or "
            "a region's pad_roles; the title's height above a top rule is the build's own band. A width alone is a "
            "no-wrap label's measured extent and must hold each paragraph on one line")

def _parse_node(raw: Mapping[str, Any]) -> Region | Element:
    node_id = raw.get("id")
    if not isinstance(node_id, str) or not node_id or "#" in node_id:
        raise LayoutContractError(f"node id {node_id!r} must be a non-empty string without '#'")
    if raw.get("type", raw.get("node_type")) == "region":
        region = Region(node_id, _parse_layout(raw["layout"], node_id), tuple(_parse_node(c) for c in raw.get("children", [])), _weight(raw))
        if isinstance(region.layout, Grid):
            placed = {a.child_id for a in region.layout.areas}
            missing = [c.id for c in region.children if c.id not in placed]
            if missing or len(placed) != len(region.layout.areas) or placed - {c.id for c in region.children}:
                raise LayoutContractError(f"region {node_id!r}: exactly one grid area per child (missing {missing})")
        return region
    kind = raw.get("kind")
    paragraphs: tuple[Paragraph, ...] = ()
    table: Table | None = None
    if kind == "text":
        paragraphs = tuple(Paragraph(p["role"], p["text"], p.get("bullet_level"), bool(p.get("emphasis")),
                                     tuple((str(r[0]), r[1], r[2]) for r in p.get("runs") or ())) for p in raw.get("paragraphs", []))
        if not paragraphs or any(not p.text.strip(" ") for p in paragraphs):
            raise LayoutContractError(f"text element {node_id!r} needs non-blank paragraphs; an empty cell that keeps a row or grid in step is a region with no children "
                                      "(in a row or column a weight gives it its share), not blank text")
    elif kind == "table":
        t = raw.get("table") or {}
        n_header = int(t.get("header_rows", 1))
        columns = tuple(Column(c["key"], (labels := header_labels(c, n_header, f"table {node_id!r}"))[-1], str(c.get("value_kind", "text")),
                               None if c.get("width_share") is None else decimal_fraction(c["width_share"]), c.get("min_width_role"), labels)
                        for c in t.get("columns", []))
        shares = [c.width_share for c in columns if c.width_share is not None]
        if any(not 0 < share <= 1 for share in shares) or sum(shares, Fraction(0)) > 1 or (len(shares) == len(columns) and sum(shares, Fraction(0)) != 1):
            total = sum(shares, Fraction(0))
            raise LayoutContractError(f"table {node_id!r}: width_share must lie in (0, 1], sum to at most 1, and to exactly 1 when every column has one; "
                                      f"these sum to {float(total):.6g} over {len(shares)} of {len(columns)} columns. Rounded shares rarely sum to 1: "
                                      "leave one column's width_share out and it takes the rest")
        rows = tuple(tuple(str(cell) for cell in row) for row in t.get("rows", []))
        if not columns or any(len(row) != len(columns) for row in rows):
            raise LayoutContractError(f"table {node_id!r}: every row needs one cell per column")
        if len({c.key for c in columns}) != len(columns):
            raise LayoutContractError(f"table {node_id!r}: duplicate column keys")
        header_rows = int(t.get("header_rows", 1))
        if not 0 <= header_rows <= 4 or (not rows and not header_rows):
            raise LayoutContractError(f"table {node_id!r}: header_rows outside 0..4 or no rows at all")
        table = Table(columns, rows, header_rows, t.get("header_role", "type.table_header"), t.get("cell_role", "type.table_cell"), t.get("cell_padding_role"),
                      bool(t.get("totals_last_row")), tuple((int(r), int(c), bool(b), bool(i), ind) for r, c, b, i, ind in (t.get("cell_styles") or [])),
                      header_bold=bool(t.get("header_bold")))
    elif kind not in ("image", "chart", "rule"):
        raise LayoutContractError(f"element {node_id!r}: kind must be text, table, image, chart or rule")
    size = raw.get("size") or {}
    for axis in ("width_emu", "height_emu"):
        if size.get(axis) is not None and (type(size[axis]) is not int or size[axis] < 0):
            raise LayoutContractError(f"element {node_id!r}: size.{axis} must be a non-negative integer EMU")
    scale_class = raw.get("scale_class", "scaling")
    if scale_class not in ("scaling", "fixed"):
        raise LayoutContractError(f"element {node_id!r}: scale_class must be scaling or fixed")
    return Element(node_id, kind, _weight(raw), scale_class, paragraphs, table, size.get("width_emu"), size.get("height_emu"))

def parse_spec(raw: Mapping[str, Any]) -> Spec:
    page = raw["page"]
    root = _parse_node(raw["root"])
    if not isinstance(root, Region):
        raise LayoutContractError("root must be a region")
    seen: set[str] = set()
    count = 0
    chain: list[str] = []
    deepest: list[str] = []
    for node, depth in walk(root):
        count += 1
        del chain[depth:]
        chain.append(node.id)
        if len(chain) > len(deepest):
            deepest = list(chain)
        if node.id in seen:
            raise LayoutContractError(f"duplicate node id {node.id!r}: every region and element id must be unique on the page")
        if depth > MAX_TREE_DEPTH:
            raise LayoutContractError(f"tree too deep: {' > '.join(chain)} puts {node.id!r} at depth {depth}, past the runaway bound of {MAX_TREE_DEPTH} "
                                      "levels below the root (root = 0); a tree this deep is a generator looping, not a layout")
        if count > MAX_NODES:
            raise LayoutContractError(f"tree past {MAX_NODES} nodes (reached at {node.id!r}); split the page")
        seen.add(node.id)
    groups = tuple(SplittableGroup(g["group_id"], g["kind"], tuple(g["node_ids"]), g.get("row_range")) for g in raw.get("splittable_groups", []))
    for g in groups:
        if g.kind not in ("node_range", "table_row_range") or any(n not in seen for n in g.node_ids) or (g.kind == "table_row_range") != (g.row_range is not None):
            raise LayoutContractError(f"splittable group {g.group_id!r} is malformed")
    zones = tuple((Box(int(z["left"]), int(z["top"]), int(z["width"]), int(z["height"])), str(z.get("source", "zone"))) for z in page.get("reserved_zones", []))
    return Spec(int(page["width_emu"]), int(page["height_emu"]), root, groups, zones, {int(k): v for k, v in (raw.get("bullet_indent_roles") or {}).items()},
                tuple(deepest))


def defaults_taken(raw_root: Mapping[str, Any]) -> list[str]:
    """Every layout choice a region left out, with the value the solver takes for it
    (_parse_layout, _weighted_sizes): a flex region's align (stretch) and justify (start),
    a region's padding (none), and children with no weight (each flexible one an equal
    share, weight 1). The build lists them per page as `layout_defaults_taken`, as a
    chart's are listed, so a value nobody chose is read back."""
    out: list[str] = []

    def visit(node: Mapping[str, Any]) -> None:
        if node.get("type", node.get("node_type")) != "region":
            return
        nid, lay = node.get("id"), node.get("layout") or {}
        kind = lay.get("kind", lay.get("layout_type"))
        if kind == "flex":
            for key, value in (("align", "stretch"), ("justify", "start")):
                if key not in lay:
                    out.append(f"{nid}: {key} {value} (left out)")
        if lay.get("pad_role") is None and lay.get("pad_roles") is None:
            out.append(f"{nid}: no padding (pad_role left out)")
        children = node.get("children") or []
        unweighted = [c.get("id") for c in children if c.get("weight") is None]
        if kind == "flex" and len(children) > 1 and unweighted:
            share = "an equal share" if len(unweighted) == len(children) else "weight 1 against its siblings' weights"
            out.append(f"{nid}: {unweighted} carry no weight: each that is flexible (not sized by its own content) takes {share} "
                       f"in the split of the free {lay.get('direction', '')} space")
        for c in children:
            visit(c)

    visit(raw_root)
    return out

# --- type resolution and scale admission (deckgen typestyles.py, design_scale.py) ---

@dataclass(frozen=True)
class TypeEntry:
    role: str
    size_pt: float
    space_before_pt: float
    space_after_pt: float
    tracking_pt: float
    line_spacing: float
    family: str
    bold: bool
    italic: bool
    case: str
    weight: int

    @property
    def pitch_emu(self) -> int:
        """Baseline-to-baseline advance: exactly the a:spcPts the file writes,
        measured font-independent (deckgen measure_bridge.py:492)."""
        return round(self.line_spacing * self.size_pt * EMU_PER_POINT)

    @property
    def spacing_emu(self) -> int:
        return paragraph_spacing_emu(self.space_before_pt, self.space_after_pt)

def type_role(guide: Guide, role: str) -> TypeRole:
    spec = guide.roles.get(role)
    if spec is None:
        if role in guide.absent_roles:
            raise UnknownTokenRoleError(f"type role {role!r}: the completed guide records that the house has none ({guide.absent_roles[role]}); "
                                        "use a role the house sets")
        raise UnknownTokenRoleError(f"type role {role!r} is not in the guide's typography roles")
    return spec

def face_for_weight(guide: Guide, spec: TypeRole) -> tuple[str, bool]:
    """400 and 700 map to the OOXML bold toggle; any other weight needs a named
    face in weight_faces, else a refusal (never collapsed to bold or regular). The
    family returned is the one the file names; Context.face picks what measures it."""
    family = spec.family
    if spec.weight == 400:
        return family, False
    if spec.weight == 700:
        return family, True
    face = guide.weight_faces.get(f"{spec.family_token}:{spec.weight}") if spec.family_token else None
    if face is None:
        raise LayoutContractError(f"weight {spec.weight} has no named face in the guide and the bold toggle cannot express it")
    return face, False

def resolve_type_entry(guide: Guide, role: str, scale: Fraction) -> TypeEntry:
    spec = type_role(guide, role)
    sz = snap_sz(spec.size_pt, scale)
    if sz < 100 or sz > 40_000:
        raise LayoutContractError(f"type role {role!r} leaves the 1..400 pt emittable domain at scale {scale}")
    family, bold = face_for_weight(guide, spec)
    return TypeEntry(
        role=role, size_pt=sz / 100,
        space_before_pt=snap_hundredths(spec.space_before_pt, scale) / 100,
        space_after_pt=snap_hundredths(spec.space_after_pt, scale) / 100,
        tracking_pt=snap_hundredths(spec.tracking_pt, scale) / 100,
        line_spacing=spec.line_spacing, family=family, bold=bold, italic=spec.italic,
        case=spec.case, weight=spec.weight,
    )

def element_roles(element: Element) -> tuple[str, ...]:
    if element.kind == "text":
        return tuple(dict.fromkeys(p.role for p in element.paragraphs))
    if element.table is not None:
        return (element.table.header_role, element.table.cell_role) if element.table.header_rows else (element.table.cell_role,)
    return ()

def roles_in_use(spec: Spec, tables: bool | None = None) -> frozenset[str]:
    """Every role a SCALING element sets text in: the set the floor must clear. tables=True
    keeps the roles tables set their cells and header in (these clear the table floor),
    False the roles text elements set (these clear their own family's floor)."""
    return frozenset(r for n, _ in walk(spec.root) if isinstance(n, Element) and n.scale_class != "fixed"
                     and (tables is None or (n.table is not None) == tables) for r in element_roles(n))

def table_floor_breaches(guide: Guide, spec: Spec, scale: Fraction = Fraction(1)) -> list[str]:
    """Each table whose cells or header sit below the table floor at `scale`, in words."""
    floor = guide.table_floor_pt
    if floor is None:
        return []
    out = []
    for n, _ in walk(spec.root):
        if isinstance(n, Element) and n.table is not None:
            for role in dict.fromkeys(element_roles(n)):
                size = snap_sz(type_role(guide, role).size_pt, Fraction(1) if n.scale_class == "fixed" else scale) / 100
                if size < floor:
                    out.append(f"table {n.id!r} sets {role} at {size:g}pt, below the table floor {floor:g}pt")
    return out

def hierarchy_levels(guide: Guide) -> tuple[tuple[Fraction, tuple[str, ...]], ...]:
    by_size: dict[Fraction, list[str]] = {}
    for role, spec in guide.roles.items():
        by_size.setdefault(decimal_fraction(spec.size_pt), []).append(role)
    return tuple((size, tuple(sorted(by_size[size]))) for size in sorted(by_size, reverse=True))

def admit_scale_candidates(guide: Guide, candidates: Sequence[Fraction]) -> tuple[tuple[Fraction, ...], tuple[dict[str, Any], ...]]:
    """Exclude every scale where two ADJACENT hierarchy levels snap to one size;
    the snap is monotone, so adjacency is the complete check."""
    levels = hierarchy_levels(guide)
    admitted: list[Fraction] = []
    excluded: list[dict[str, Any]] = []
    for scale in candidates:
        collision = None
        for (upper, upper_roles), (lower, lower_roles) in zip(levels, levels[1:]):
            if snap_pt(upper, scale) == snap_pt(lower, scale):
                collision = {"scale": str(scale), "upper": upper_roles, "lower": lower_roles, "aliased_pt": float(snap_pt(upper, scale))}
                break
        (excluded if collision else admitted).append(collision or scale)
    return tuple(admitted), tuple(excluded)

def scale_clears_floors(guide: Guide, roles: frozenset[str], scale: Fraction, table_roles: frozenset[str] = frozenset()) -> bool:
    """Every role a text element sets (`roles`) clears its own family's floor at `scale`;
    every role a table sets (`table_roles`) clears the table floor (table_floor_pt), the
    one rule the package validator reads off a table run."""
    for role in roles:
        floor = guide.floor_by_role.get(role)
        if floor is not None and snap_sz(type_role(guide, role).size_pt, scale) / 100 < floor:
            return False
    for role in table_roles:
        floor = guide.table_floor_pt if guide.table_floor_pt is not None else guide.floor_by_role.get(role)
        if floor is not None and snap_sz(type_role(guide, role).size_pt, scale) / 100 < floor:
            return False
    return True

def floor_admitted_candidates(guide: Guide, spec: Spec) -> tuple[Fraction, ...]:
    """1.00 then the admitted ladder, truncated at the first scale that undercuts
    an in-use role's floor (snap is monotone, so every lower scale fails too)."""
    roles, table_roles = roles_in_use(spec, tables=False), roles_in_use(spec, tables=True)
    admitted, _ = admit_scale_candidates(guide, (Fraction(1), *SCALE_LADDER))
    allowed: list[Fraction] = []
    for candidate in admitted:
        if not scale_clears_floors(guide, roles, candidate, table_roles):
            break
        allowed.append(candidate)
    return tuple(allowed)

# --- the geometry core (deckgen solver.py) -----------------------------------------

@dataclass(frozen=True)
class IntrinsicSize:
    """A MEASURED extent; None on an axis = flexible on that axis. A flexible height
    still has a floor, its measured content, which a column never cuts below."""

    width_emu: int | None = None
    height_emu: int | None = None
    min_height_emu: int = 0

def pad_emu(layout: Flex | Grid, guide: Guide, scale: Fraction) -> tuple[int, int, int, int]:
    """The region's padding in EMU, left, top, right, bottom."""
    return tuple(space_emu(guide, role, scale, "x" if i % 2 == 0 else "y") if role is not None else 0
                 for i, role in enumerate(layout.pads))  # type: ignore[return-value]


def content_box(box: Box, layout: Flex | Grid, guide: Guide, scale: Fraction) -> Box:
    left, top, right, bottom = pad_emu(layout, guide, scale)
    if not (left or top or right or bottom):
        return box
    return Box(min(box.left + left, box.right), min(box.top + top, box.bottom), max(0, box.width - left - right), max(0, box.height - top - bottom))

def solve_tree(spec: Spec, guide: Guide, scale: float | Fraction, intrinsics: Mapping[str, IntrinsicSize] | None = None) -> dict[str, Box]:
    """Every node's box at `scale`, from weights, tracks and measured extents.
    Pure: no measurement happens here. Measured extents are never altered."""
    s = checked_scale(scale)
    intr = dict(intrinsics or {})
    ids = {n.id for n, _ in walk(spec.root)}
    if set(intr) - ids:
        raise LayoutContractError(f"intrinsic sizes name nodes not in the tree: {sorted(set(intr) - ids)}")
    boxes: dict[str, Box] = {}
    _solve_node(spec.root, Box(0, 0, spec.page_width, spec.page_height), spec, guide, s, intr, boxes, True)
    return boxes

def _solve_node(node: Region | Element, box: Box, spec: Spec, guide: Guide, s: Fraction, intr: Mapping[str, IntrinsicSize], boxes: dict[str, Box], is_root: bool) -> None:
    boxes[node.id] = box
    if isinstance(node, Element):
        return
    content = content_box(box, node.layout, guide, s)
    if is_root:
        content = _reserve_edge_zones(content, spec, guide)
    if not node.children:
        return
    if isinstance(node.layout, Flex):
        child_boxes = _flex_child_boxes(node, node.layout, content, guide, s, intr)
    else:
        child_boxes = _grid_child_boxes(node, node.layout, content, guide, s)
    for child, child_box in zip(node.children, child_boxes):
        _solve_node(child, child_box, spec, guide, s, intr, boxes, False)

def _reserve_edge_zones(content: Box, spec: Spec, guide: Guide) -> Box:
    """Every reserved zone that reaches the page's margin band (space.margin at
    scale 1.00, the page's own band) costs the root content box a full-width
    strip from the nearer edge; interior zones are boundaries validation
    guards (deckgen solver.py:731)."""
    margin_y = space_emu(guide, MARGIN_ROLE, Fraction(1), "y") if MARGIN_ROLE in guide.steps else 0
    remaining = content
    for zone, source in spec.zones:
        if zone.top > margin_y and zone.bottom < spec.page_height - margin_y:
            continue
        top, bottom = max(zone.top, content.top), min(zone.bottom, content.bottom)
        if top >= bottom or zone.right <= content.left or zone.left >= content.right:
            continue
        if content.bottom - bottom <= top - content.top:
            new_top, new_bottom = remaining.top, min(remaining.bottom, top)
        else:
            new_top, new_bottom = max(remaining.top, bottom), remaining.bottom
        if new_bottom - new_top <= 0:
            raise LayoutContractError(f"reserved zone {source!r} leaves no content area")
        remaining = Box(remaining.left, new_top, remaining.width, new_bottom - new_top)
    return remaining

def _justify_offsets(justify: str, free: Fraction, n: int) -> tuple[Fraction, Fraction]:
    if free <= 0 or n == 0:
        return Fraction(0), Fraction(0)
    if justify == "center":
        return free / 2, Fraction(0)
    if justify == "end":
        return free, Fraction(0)
    if justify == "space_between":
        return (Fraction(0), Fraction(0)) if n == 1 else (Fraction(0), free / (n - 1))
    if justify == "space_around":
        return free / n / 2, free / n
    return Fraction(0), Fraction(0)

def _weighted_sizes(children: Sequence[Region | Element], mains: list[int | None], floors: list[int], remaining: int) -> list[int]:
    """Flexible children split `remaining` by weight, none below its floor: a child whose
    share falls under its floor is frozen at the floor and the rest re-split (CSS flex's
    freeze loop). Integer EMU by largest remainder, so the shares sum exactly to what was
    split and a measured sibling keeps its exact size (cumulative rounding once solved a
    1 EMU rule to 0 or 2)."""
    sizes = [m if m is not None else 0 for m in mains]
    open_ = [i for i, m in enumerate(mains) if m is None]
    pool = remaining
    while open_:
        weights = {i: decimal_fraction(children[i].weight if children[i].weight is not None else 1.0) for i in open_}
        total = sum(weights.values(), Fraction(0))
        share = {i: Fraction(max(pool, 0)) * weights[i] / total for i in open_}
        under = [i for i in open_ if share[i] < floors[i]]
        if not under:
            whole = {i: int(share[i]) for i in open_}
            left = max(pool, 0) - sum(whole.values())
            for i in sorted(open_, key=lambda k: (-(share[k] - whole[k]), k))[:left]:
                whole[i] += 1
            for i in open_:
                sizes[i] = whole[i]
            break
        for i in under:
            sizes[i] = floors[i]
            pool -= floors[i]
            open_.remove(i)
    return sizes

def _flex_child_boxes(region: Region, layout: Flex, content: Box, guide: Guide, s: Fraction, intr: Mapping[str, IntrinsicSize]) -> list[Box]:
    """Intrinsic main sizes are taken EXACTLY; weight shares split the rest (never below
    a flexible child's measured floor), so sibling sizes sum exactly to the distributable
    extent. Offset and size boundary quantize separately (half-even is not
    translation-invariant)."""
    is_row = layout.direction == "row"
    extent, cross_extent = (content.width, content.height) if is_row else (content.height, content.width)
    gap = gap_emu(guide, layout.gap_role, s, "x" if is_row else "y")
    n = len(region.children)
    distributable = max(extent - gap * (n - 1), 0)
    mains = [(h.width_emu if is_row else h.height_emu) if (h := intr.get(c.id)) else None for c in region.children]
    floors = [0 if is_row or (h := intr.get(c.id)) is None else h.min_height_emu for c in region.children]
    fixed_total = sum(m for m in mains if m is not None)
    flexible = any(m is None for m in mains)
    remaining = max(distributable - fixed_total, 0)
    sizes = _weighted_sizes(region.children, mains, floors, remaining)
    free = Fraction(0) if flexible else Fraction(remaining)
    lead, extra = _justify_offsets(layout.justify, free, n)
    out: list[Box] = []
    cumulative = 0
    for index, (child, size) in enumerate(zip(region.children, sizes)):
        offset = quantize_emu(lead + (gap + extra) * index)
        start, end = offset + cumulative, offset + cumulative + size
        cumulative += size
        cross_size, cross_off = cross_extent, 0
        hint = intr.get(child.id)
        cross_hint = (hint.height_emu if is_row else hint.width_emu) if hint else None
        if layout.align != "stretch" and cross_hint is not None:
            cross_size = cross_hint
            slack = cross_extent - cross_size
            cross_off = quantize_emu(Fraction(slack, 2)) if layout.align == "center" else slack if layout.align == "end" else 0
        if is_row:
            out.append(Box(content.left + start, content.top + cross_off, end - start, cross_size))
        else:
            out.append(Box(content.left + cross_off, content.top + start, cross_size, end - start))
    return out

def _grid_child_boxes(region: Region, layout: Grid, content: Box, guide: Guide, s: Fraction) -> list[Box]:
    """Uniform tracks, gutters between, spans across cumulative boundaries."""
    gutter_x, gutter_y = space_emu(guide, layout.gutter_role, s, "x"), space_emu(guide, layout.gutter_role, s, "y")
    span_x = max(content.width - gutter_x * (layout.cols - 1), 0)
    span_y = max(content.height - gutter_y * (layout.rows - 1), 0)
    bound_x = [quantize_emu(Fraction(span_x * k, layout.cols)) for k in range(layout.cols + 1)]
    bound_y = [quantize_emu(Fraction(span_y * k, layout.rows)) for k in range(layout.rows + 1)]
    areas = {a.child_id: a for a in layout.areas}
    out: list[Box] = []
    for child in region.children:
        a = areas[child.id]
        col_end, row_end = a.col + a.col_span, a.row + a.row_span
        x1, x2 = bound_x[a.col] + a.col * gutter_x, bound_x[col_end] + (col_end - 1) * gutter_x
        y1, y2 = bound_y[a.row] + a.row * gutter_y, bound_y[row_end] + (row_end - 1) * gutter_y
        out.append(Box(content.left + x1, content.top + y1, x2 - x1, y2 - y1))
    return out

# --- validation (deckgen validation.py) ------------------------------------------

@dataclass(frozen=True)
class Violation:
    code: str
    node_id: str
    related_node_id: str | None
    detail: str
    shortfall_emu: int | None
    scale_fixable: bool

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

def _overlaps(a: Box, b: Box) -> bool:
    return min(a.right, b.right) > max(a.left, b.left) and min(a.bottom, b.bottom) > max(a.top, b.top)

def _depth(a: Box, b: Box) -> int:
    return min(min(a.right, b.right) - max(a.left, b.left), min(a.bottom, b.bottom) - max(a.top, b.top))

def validate(spec: Spec, guide: Guide, scale: Fraction, boxes: Mapping[str, Box], table_fits: Mapping[str, TableFit]) -> list[Violation]:
    nodes = [n for n, _ in walk(spec.root)]
    elements = [n for n in nodes if isinstance(n, Element)]
    page = Box(0, 0, spec.page_width, spec.page_height)
    out: list[Violation] = []
    for node in nodes:
        b = boxes[node.id]
        if b.left < 0 or b.top < 0 or b.right > page.width or b.bottom > page.height:
            out.append(Violation("exceeds_page", node.id, None, f"box {b.as_dict()} exceeds the page", max(-b.left, -b.top, b.right - page.width, b.bottom - page.height), True))
    for el in elements:
        b = boxes[el.id]
        if b.width == 0 or b.height == 0:
            out.append(Violation("zero_dimension", el.id, None, f"element box is {b.width} x {b.height} EMU", None, False))
    for region in (n for n in nodes if isinstance(n, Region)):
        content = content_box(boxes[region.id], region.layout, guide, scale)
        for child in region.children:
            b = boxes[child.id]
            if b.left < content.left or b.top < content.top or b.right > content.right or b.bottom > content.bottom:
                out.append(Violation("containment", child.id, region.id, f"box {b.as_dict()} leaves {region.id}'s content box {content.as_dict()}", max(content.left - b.left, content.top - b.top, b.right - content.right, b.bottom - content.bottom), True))
        if isinstance(region.layout, Flex) and region.children:
            is_row = region.layout.direction == "row"
            distributable = (content.width if is_row else content.height) - gap_emu(guide, region.layout.gap_role, scale, "x" if is_row else "y") * (len(region.children) - 1)
            if distributable <= 0:
                out.append(Violation("overcommit", region.id, None, f"gaps and padding leave {distributable} EMU for {len(region.children)} children", -distributable, False))
        elif isinstance(region.layout, Grid) and region.children:
            track_x = content.width - space_emu(guide, region.layout.gutter_role, scale, "x") * (region.layout.cols - 1)
            track_y = content.height - space_emu(guide, region.layout.gutter_role, scale, "y") * (region.layout.rows - 1)
            if track_x <= 0 or track_y <= 0:
                out.append(Violation("overcommit", region.id, None, f"gutters and padding leave {track_x} x {track_y} EMU of track space", max(-track_x, -track_y), False))
    for i, a in enumerate(elements):
        for b in elements[i + 1:]:
            if _overlaps(boxes[a.id], boxes[b.id]):
                out.append(Violation("overlap", a.id, b.id, f"boxes of {a.id} and {b.id} share area", _depth(boxes[a.id], boxes[b.id]), True))
    for el in elements:
        for zone, source in spec.zones:
            if _overlaps(boxes[el.id], zone):
                out.append(Violation("reserved_zone", el.id, None, f"box crosses the zone reserved by {source!r}", _depth(boxes[el.id], zone), True))
    for el_id, fit in table_fits.items():
        if fit.width_deficit_emu > 0:
            out.append(Violation("containment", el_id, None, f"columns at their minimum widths need {fit.width_deficit_emu} EMU more than the table box", fit.width_deficit_emu, True))
    return out

# --- text measurement bridge (deckgen measure_bridge.py) ------------------------

def apply_case(text: str, case: str) -> str:
    """The guide's case convention over one whole paragraph (deckgen lineage/text.py:77)."""
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        out, prev = [], None
        for ch in text:
            out.append(ch.upper() if prev is None or prev.isspace() else ch)
            prev = ch
        return "".join(out)
    if case == "sentence" and text:
        return text[:1].upper() + text[1:]
    return text

def apply_case_runs(texts: Sequence[str], case: str | None) -> list[str]:
    """apply_case over a paragraph written as runs: the joined text is cased once (title
    case reads a run boundary inside a word as inside the word) and cut back at the runs'
    own boundaries. The solver measures apply_case(paragraph) and the emitter writes this,
    so the file draws the measured text."""
    full = "".join(texts)
    cased = apply_case(full, case or "as_typed")
    if len(cased) != len(full):
        raise LayoutContractError(f"case {case!r} changes the length of {full!r} (to {cased!r}); write the paragraph already cased")
    out, at = [], 0
    for t in texts:
        out.append(cased[at:at + len(t)])
        at += len(t)
    return out

def tracked_width_emu(width_emu: int, text: str, tracking_pt: float) -> int:
    """What a measured line DRAWS once OOXML spc adds tracking per character:
    one rounding over the whole run (deckgen measure/text.py:385)."""
    return width_emu + round(tracking_pt * len(text) * EMU_PER_POINT)

@dataclass(frozen=True)
class ParagraphMeasurement:
    index: int
    entry: TypeEntry
    text: str
    face: Face
    indent_emu: int
    allowance_emu: int
    lines: tuple[MeasuredLine, ...]

    @property
    def stack_emu(self) -> int:
        return len(self.lines) * self.entry.pitch_emu

@dataclass
class Context:
    """One solve's instruments: the guide, the ruler and the face index. `spec` is
    None for a measuring-only context (component_api.py): one_line_width and the
    cell measurers read the ruler alone, and nothing else is reachable without a
    tree to solve."""

    guide: Guide
    ruler: Ruler
    index: FaceIndex
    spec: Spec | None = None

    def entry(self, element: Element, role: str, scale: Fraction) -> TypeEntry:
        return resolve_type_entry(self.guide, role, Fraction(1) if element.scale_class == "fixed" else scale)

    def face(self, entry: TypeEntry, *, bold: bool | None = None, italic: bool | None = None) -> Face:
        """The face `entry` is measured with: its family, a metric alias, or the guide's
        stand-in, which must be the face the renderer draws (textfit.resolve_measured). A
        style the family has no file for (an italic run of a face installed upright only)
        is refused, never measured upright."""
        try:
            return resolve_measured(self.index, entry.family, bold=entry.bold if bold is None else bold, italic=entry.italic if italic is None else italic,
                                    substitute=self.guide.substitutes.get(entry.family))
        except (SubstituteMismatchError, UnknownFamilyError, UnknownStyleError) as error:
            raise FaceRefused(str(error)) from None

def measure_element(ctx: Context, element: Element, box: Box, scale: Fraction) -> list[ParagraphMeasurement]:
    """Wrapped at allowance - FIT_EPSILON, charged at the full allowance."""
    out: list[ParagraphMeasurement] = []
    for index, paragraph in enumerate(element.paragraphs):
        entry = ctx.entry(element, paragraph.role, scale)
        runs = run_faces(paragraph)
        cased = apply_case_runs([r[0] for r in runs], entry.case)
        text = "".join(cased)
        faces = [ctx.face(entry, bold=b, italic=i) for _, b, i in runs]
        face = faces[0]
        indent = 0
        if paragraph.bullet_level is not None:
            role = ctx.spec.bullet_indent_roles.get(paragraph.bullet_level, ctx.guide.bullet_indent_roles.get(paragraph.bullet_level))
            if role is None:
                raise LayoutContractError(f"element {element.id!r}: no indent role for bullet level {paragraph.bullet_level} (guide bullets or spec bullet_indent_roles)")
            indent = space_emu(ctx.guide, role, scale, "x")
        allowance = box.width - indent
        if allowance <= 0:
            raise CandidateRefused(f"element {element.id!r} paragraph {index}: the indent leaves {allowance} EMU of usable width")
        spans, at = [], 0
        for part, f in zip(cased, faces, strict=True):
            spans.append((at, at + len(part), f.path, entry.size_pt))
            at += len(part)
        lines = measure_runs(ctx.ruler, text, [sp for sp in spans if sp[1] > sp[0]], max(1, allowance - ctx.ruler.fit_epsilon_emu))
        if entry.tracking_pt > 0:
            for line in lines:
                drawn = tracked_width_emu(line.width_emu, line.text, entry.tracking_pt)
                if drawn > allowance:
                    raise CandidateRefused(f"element {element.id!r}: tracked line {line.text!r} draws {drawn - allowance} EMU past its box")
        out.append(ParagraphMeasurement(index, entry, text, face, indent, allowance, lines))
    return out

def element_height_emu(measurements: Sequence[ParagraphMeasurement]) -> int:
    """Every line plus EVERY paragraph's written spcBef and spcAft, trailing one
    included: exactly what the emit gate charges."""
    return sum(m.stack_emu + m.entry.spacing_emu for m in measurements)

def split_words(m: ParagraphMeasurement) -> list[str]:
    """Words the wrap cut between characters: a line that starts where the text offers
    no break (wrap_text breaks a token wider than the line, as PowerPoint does)."""
    stops = set(break_opportunities(m.text))
    out: list[str] = []
    for line in m.lines[1:]:
        q = line.start
        while q not in stops and q > 0 and m.text[q - 1] == " ":
            q -= 1
        if q in stops:
            continue
        left = max((s for s in stops if s <= q), default=0)
        right = min((s for s in stops if s > q), default=len(m.text))
        out.append(m.text[left:right].strip(" "))
    return out

def measured_violations(ctx: Context, boxes: Mapping[str, Box], measurements: Mapping[str, Sequence[ParagraphMeasurement]], fits: Mapping[str, TableFit]) -> list[Violation]:
    """Every measured element against its OWN solved box: the stack of lines (or the
    table's rows) must fit the box's height, whatever region placed it, and no word may
    be cut between characters. Containment compares boxes only, so a box a stretch row
    or a grid track sized below its text passed it."""
    out: list[Violation] = []
    sized = {node.id for node, _ in walk(ctx.spec.root) if isinstance(node, Element) and node.kind == "text" and node.width_emu is not None}
    for el_id, rows in measurements.items():
        box = boxes[el_id]
        if el_id in sized:
            for m in rows:
                if len(m.lines) > 1:
                    over = advance_emu(ctx.ruler, m.text, m.face.path, m.entry.size_pt) - (m.allowance_emu - ctx.ruler.fit_epsilon_emu)
                    out.append(Violation("sized_text_wraps", el_id, None, f"paragraph {m.index}: a text with a width is a no-wrap label, and {m.text!r} "
                                         f"takes {len(m.lines)} lines in it; a width on text must be the label's measured one-line extent", max(1, over), True))
        need = element_height_emu(rows)
        if need > box.height:
            out.append(Violation("overflow", el_id, None, f"the measured text needs {need} EMU and its box is {box.height} EMU tall", need - box.height, True))
        for m in rows:
            for word in split_words(m):
                width = advance_emu(ctx.ruler, word, m.face.path, m.entry.size_pt)
                out.append(Violation("word_split", el_id, None, f"paragraph {m.index}: {word!r} at {m.entry.size_pt}pt measures {width} EMU, wider than the {m.allowance_emu - ctx.ruler.fit_epsilon_emu} EMU line, so it breaks between characters",
                                     width - (m.allowance_emu - ctx.ruler.fit_epsilon_emu), True))
    for el_id, fit in fits.items():
        box = boxes[el_id]
        if fit.total_height_emu > box.height + EMIT_SLACK_EMU:
            out.append(Violation("overflow", el_id, None, f"the fitted rows need {fit.total_height_emu} EMU and the table's box is {box.height} EMU tall", fit.total_height_emu - box.height, True))
    return out

# --- the dense-table fitter (deckgen table_fitter.py, table_text.py) ----------------

@dataclass(frozen=True)
class DrawnRole:
    entry: TypeEntry
    path: str

@dataclass(frozen=True)
class TableFit:
    column_widths: dict[str, int]
    column_deficits: dict[str, int]
    row_heights: tuple[int, ...]
    cell_lines: dict[tuple[int, str], tuple[str, ...]]
    total_height_emu: int
    overflow: bool
    width_deficit_emu: int
    fitting_row_prefix: int
    box_width: int
    header_rows: int
    padding_emu: int
    header: DrawnRole | None
    cell: DrawnRole

def _cell_lines(ctx: Context, text: str, budget: int, kind: DrawnRole) -> tuple[MeasuredLine, ...]:
    return measure_text(ctx.ruler, text, budget, kind.path, kind.entry.size_pt)

def one_line_width(ctx: Context, text: str, kind: DrawnRole) -> int:
    """The narrowest width this string DRAWS on one line, confirmed with the
    ruler (its EMU conversion can sit half an EMU under the advance), then
    charged for tracking."""
    reported = _cell_lines(ctx, text, 10**8, kind)[0].width_emu
    width = reported
    for _ in range(4):
        if len(_cell_lines(ctx, text, width, kind)) == 1:
            return tracked_width_emu(width, text, kind.entry.tracking_pt)
        width += 1
    raise LayoutContractError(f"the ruler still wraps {text!r} four EMU above its own reported advance {reported}")

def min_content_width(ctx: Context, text: str, kind: DrawnRole) -> int:
    """The widest unbreakable segment, cut at the ruler's own break opportunities."""
    widest, start = 0, 0
    for stop in break_opportunities(text):
        segment = text[start:stop].strip(" ")
        start = stop
        if segment:
            widest = max(widest, one_line_width(ctx, segment, kind))
    return widest

def _drawn_width(ctx: Context, text: str, kind: DrawnRole) -> int:
    stripped = text.rstrip(" ")
    if not stripped:
        return 0
    return tracked_width_emu(_cell_lines(ctx, stripped, 10**8, kind)[0].width_emu, stripped, kind.entry.tracking_pt)

def wrapped_lines(ctx: Context, text: str, budget: int, kind: DrawnRole) -> tuple[str, ...]:
    """One cell's lines. Untracked: the ruler's wrap IS the answer. Tracked: the
    break is walked segment by segment at the DRAWN width of each whole
    candidate line, since the file adds spc after shaping."""
    if not text.strip():
        return ("",)  # a blank cell is one drawn line, never zero
    if not kind.entry.tracking_pt:
        return tuple(line.text for line in _cell_lines(ctx, text, budget, kind))
    stops, segments, start = break_opportunities(text), [], 0
    for stop in stops:
        segments.append(text[start:stop])
        start = stop
    lines: list[str] = []
    line = ""
    for segment in segments:
        if line and _drawn_width(ctx, line + segment, kind) <= budget:
            line += segment
            continue
        if line:
            lines.append(line.rstrip(" "))
        tail = segment[len(segment.rstrip(" ")):]
        core = segment.strip(" ")
        if _drawn_width(ctx, core, kind) <= budget:
            pieces = [core]
        else:
            charge = max(0, tracked_width_emu(0, core, kind.entry.tracking_pt))
            pieces = [ln.text for ln in _cell_lines(ctx, core, max(1, budget - charge), kind)]
        lines.extend(p.rstrip(" ") for p in pieces[:-1])
        line = pieces[-1] + tail
    if line:
        lines.append(line.rstrip(" "))
    return tuple(lines)

def required_line_box_emu(size_hundredths: int, requested_spacing_hundredths: int | None) -> int:
    """PowerPoint's line box in a cell: exact at 1.2 x size with no a:lnSpc, an
    upper bound (never exceeded on 200 E38 cases) with an explicit a:spcPts."""
    natural = POWERPOINT_LINE_HEIGHT_RATIO * size_hundredths * EMU_PER_HUNDREDTH_POINT
    requested = 0.0 if requested_spacing_hundredths is None else requested_spacing_hundredths * EMU_PER_HUNDREDTH_POINT + REQUESTED_SPACING_SLACK_EMU
    return round(max(natural, requested))

def required_row_height_emu(line_counts: Sequence[int], size_hundredths: int, requested_spacing_hundredths: int | None, inset_top: int, inset_bottom: int) -> int:
    """a:tr/@h is a MINIMUM: PowerPoint realises lines x line_box + marT + marB
    (E38, 114 graded cases), so this is what the row is declared at."""
    return max(line_counts, default=0) * required_line_box_emu(size_hundredths, requested_spacing_hundredths) + inset_top + inset_bottom

def _spread_surplus(keys: list[str], natural: dict[str, int], surplus: int) -> dict[str, int]:
    widths, total, handed = dict(natural), sum(natural.values()), 0
    if total <= 0 or surplus <= 0:
        return widths
    for key in keys[:-1]:
        share = surplus * natural[key] // total
        widths[key] += share
        handed += share
    widths[keys[-1]] += surplus - handed
    return widths

def _level_down(keys: list[str], natural: dict[str, int], minimum: dict[str, int], target: int) -> tuple[dict[str, int], int]:
    """Water level: width(k) = max(min_k, min(nat_k, level)), the highest level
    the box pays for found by bisection; the last EMU go one at a time to the
    columns AT the level. Minimums alone past the target: the shortfall is
    returned, never an exception, and nothing is dropped."""
    floors = sum(minimum[k] for k in keys)
    if floors >= target:
        return dict(minimum), floors - target

    def at(level: int) -> dict[str, int]:
        return {k: max(minimum[k], min(natural[k], level)) for k in keys}

    low, high = 0, max(natural[k] for k in keys)
    while low < high:
        middle = (low + high + 1) // 2
        if sum(at(middle).values()) <= target:
            low = middle
        else:
            high = middle - 1
    widths = at(low)
    at_level = [k for k in keys if widths[k] == low and natural[k] > low]
    for i in range(target - sum(widths.values())):
        widths[at_level[i % len(at_level)]] += 1
    return widths, 0

def fit_table(ctx: Context, element: Element, box: Box, scale: Fraction) -> TableFit:
    """Columns then rows, jointly, at this candidate's sizes; never a size change,
    never a dropped row."""
    table = element.table
    assert table is not None
    guide = ctx.guide
    pad_role = table.cell_padding_role or guide.cell_padding_role
    if pad_role is not None:
        padding = space_emu(guide, pad_role, scale, "x")
    else:
        padding = guide.cell_padding_emu if guide.cell_padding_emu is not None else DEFAULT_CELL_INSET_EMU
    cell = DrawnRole(e := ctx.entry(element, table.cell_role, scale), ctx.face(e).path)
    # a totals row is written bold: measured bold too, or a cell that fits by a hair breaks a word
    cell_bold = DrawnRole(e, ctx.face(e, bold=True).path)
    header = None
    if table.header_rows:
        h = ctx.entry(element, table.header_role, scale)
        header = DrawnRole(h, ctx.face(h, bold=True).path if table.header_bold else ctx.face(h).path)
    case = header.entry.case if header else "as_typed"
    header_text = [[apply_case(c.labels[r] if r < len(c.labels) else "", case) for c in table.columns] for r in range(table.header_rows)]
    spans = header_spans([[header_text[r][ci] for r in range(table.header_rows)] for ci in range(len(table.columns))], table.header_rows)
    grid: list[list[str]] = [list(row) for row in header_text]
    grid.extend([apply_case(v, cell.entry.case) for v in row] for row in table.rows)
    keys = [c.key for c in table.columns]
    charge = 2 * padding + ctx.ruler.fit_epsilon_emu
    natural, minimum = {}, {}
    styled = {(r, c): (b, i, ind) for r, c, b, i, ind in table.cell_styles}
    kinds: dict[tuple, DrawnRole] = {}

    def kind_of(gr: int, ci: int) -> DrawnRole:
        """A cell's face: its own setting (cell_styles), else its row's."""
        base = header if gr < table.header_rows and header else cell
        if (gr, ci) not in styled:
            return cell_bold if base is cell and table.totals_last_row and gr == len(grid) - 1 else base
        b, i, _ = styled[(gr, ci)]
        if (base.entry.role, b, i) not in kinds:
            kinds[(base.entry.role, b, i)] = DrawnRole(base.entry, ctx.face(base.entry, bold=b, italic=i).path)
        return kinds[(base.entry.role, b, i)]

    def indent_of(gr: int, ci: int) -> int:
        """A cell's own indent (an emphasis group's indent_role, written as its marL)."""
        role = styled.get((gr, ci), (None, None, None))[2]
        return space_emu(guide, role, scale, "x") if role else 0

    for ci, column in enumerate(table.columns):
        # a header cell narrows only its own column; a spanner is measured across its span below
        heads = [r for r in range(table.header_rows) if (ci, ci) in spans[r]] if header else []
        texts = ([(header_text[r][ci], kind_of(r, ci), False, indent_of(r, ci)) for r in heads]
                 + [(grid[gr][ci], kind_of(gr, ci), True, indent_of(gr, ci)) for gr in range(table.header_rows, len(grid))])
        widest = widest_segment = widest_value = 0
        for text, kind, is_value, indent in texts:
            if not text.strip():
                continue
            one = one_line_width(ctx, text, kind) + indent
            widest = max(widest, one)
            widest_segment = max(widest_segment, min_content_width(ctx, text, kind) + indent)
            if is_value:
                widest_value = max(widest_value, one)
        floor = max(widest_segment, widest_value) if column.value_kind in NUMERIC_VALUE_KINDS else widest_segment
        natural[column.key], minimum[column.key] = widest + charge, min(widest + charge, floor + charge)
        if column.min_width_role is not None:
            least = space_emu(guide, column.min_width_role, scale, "x")
            natural[column.key], minimum[column.key] = max(natural[column.key], least), max(minimum[column.key], least)
    # a share is the spec's width, taken as given; the column's measured minimum still
    # stands, and a share below it is a deficit reported against that column
    fixed = {c.key: quantize_emu(c.width_share * box.width) for c in table.columns if c.width_share is not None}
    column_deficits = {k: minimum[k] - w for k, w in fixed.items() if minimum[k] > w}
    free = [k for k in keys if k not in fixed]
    target = box.width - sum(fixed.values())
    if not free:
        last = keys[-1]
        fixed[last] += box.width - sum(fixed.values())
        widths, shortfall = dict(fixed), 0
    else:
        nat, low = {k: natural[k] for k in free}, {k: minimum[k] for k in free}
        if sum(nat.values()) <= target:
            free_widths, shortfall = _spread_surplus(free, nat, target - sum(nat.values())), 0
        else:
            free_widths, shortfall = _level_down(free, nat, low, max(target, 0))
            shortfall += max(0, -target)
        widths = {k: fixed.get(k, free_widths.get(k)) for k in keys}
    if shortfall:
        column_deficits["unshared columns"] = shortfall
    for r in range(table.header_rows if header else 0):
        for c0, c1 in spans[r]:
            if c1 > c0 and grid[r][c0].strip():
                # a spanner's widest word must fit across the columns it spans
                need = min_content_width(ctx, grid[r][c0], header) + charge - sum(widths[keys[c]] for c in range(c0, c1 + 1))
                if need > 0:
                    column_deficits[f"header row {r} span {keys[c0]}..{keys[c1]}"] = need
    deficit = sum(column_deficits.values())
    cell_lines: dict[tuple[int, str], tuple[str, ...]] = {}
    row_heights: list[int] = []
    for ri, texts in enumerate(grid):
        row_kind = header if (ri < table.header_rows and header) else (cell_bold if (table.totals_last_row and ri == len(grid) - 1) else cell)
        counts = []
        cells = spans[ri] if ri < table.header_rows else [(ci, ci) for ci in range(len(keys))]
        for c0, c1 in cells:
            key, text = keys[c0], texts[c0]
            kind = kind_of(ri, c0)
            # a spanner wraps across the columns it spans (their widths, less one inset pair)
            width = sum(widths[keys[c]] for c in range(c0, c1 + 1))
            lines = wrapped_lines(ctx, text, max(1, width - 2 * padding - indent_of(ri, c0) - ctx.ruler.fit_epsilon_emu), kind)
            cell_lines[(ri, key)] = lines
            for c in range(c0 + 1, c1 + 1):
                cell_lines[(ri, keys[c])] = ()
            counts.append(len(lines))
        row_heights.append(required_row_height_emu(counts, hundredths(row_kind.entry.size_pt), hundredths(row_kind.entry.line_spacing * row_kind.entry.size_pt), padding, padding))
    total, budget = sum(row_heights), box.height + EMIT_SLACK_EMU
    return TableFit(widths, column_deficits, tuple(row_heights), cell_lines, total, total > budget or deficit > 0, deficit, fitting_prefix(row_heights, table.header_rows, budget), box.width, table.header_rows, padding, header, cell)

def fitting_prefix(row_heights: Sequence[int], header_rows: int, budget: int) -> int:
    """The largest body-row prefix that fits `budget` under the header rows."""
    running = sum(row_heights[:header_rows])
    if running > budget:
        return 0
    prefix = 0
    for height in row_heights[header_rows:]:
        if running + height > budget:
            break
        running += height
        prefix += 1
    return prefix

# --- the two-pass fixed point --------------------------------------------------------

def _region_heights(node: Region | Element, guide: Guide, scale: Fraction, heights: dict[str, int], floors: dict[str, int], root: bool, in_column: bool = False) -> tuple[int | None, int]:
    """(height, floor) bottom-up. A region is as tall as its content (column: the sum and
    gaps, row: the tallest child, plus padding) unless it is flexible: the root, a grid,
    an ancestor of a flexible child, or a region with a weight inside a column, which
    asks for its share. A flexible region keeps its content as a floor, so a share never
    cuts measured text or a table short. A row's align is cross-axis placement only."""
    if isinstance(node, Element):
        height = heights.get(node.id)
        if in_column and node.weight is not None and node.kind == "text" and height is not None and node.height_emu is None:
            # a weighted text element in a column takes its share of the spare height, as a
            # weighted region does, never less than its lines (its weight was read by
            # nothing: rows of text beside each other's labels came out misaligned)
            del heights[node.id]
            floors[node.id] = height
            return None, height
        return height, height or 0
    is_column = isinstance(node.layout, Flex) and node.layout.direction == "column"
    child = [_region_heights(c, guide, scale, heights, floors, False, is_column) for c in node.children]
    if isinstance(node.layout, Grid) or not node.children:
        return None, 0
    _, pad_top, _, pad_bottom = pad_emu(node.layout, guide, scale)
    pad = pad_top + pad_bottom
    if is_column:
        floor = sum(f for _, f in child) + gap_emu(guide, node.layout.gap_role, scale, "y") * (len(child) - 1) + pad
    else:
        floor = max(f for _, f in child) + pad
    if root or any(h is None for h, _ in child) or (in_column and node.weight is not None):
        floors[node.id] = floor
        return None, floor
    heights[node.id] = floor
    return floor, floor

@dataclass
class Resolved:
    scale: Fraction
    boxes: dict[str, Box]
    measurements: dict[str, list[ParagraphMeasurement]]
    table_fits: dict[str, TableFit]
    violations: list[Violation]
    ruler: str
    fit_epsilon_emu: int

    @property
    def fits(self) -> bool:
        return not self.violations

def solve_measured(ctx: Context, scale: float | Fraction) -> Resolved:
    """ONE honest candidate: probe, measure, final solve, re-measure, validate.
    Floors are candidate ADMISSION (descend, the CLI), not checked here."""
    spec, guide = ctx.spec, ctx.guide
    s = checked_scale(scale)
    elements = [n for n, _ in walk(spec.root) if isinstance(n, Element)]
    intrinsics = {e.id: IntrinsicSize(e.width_emu, e.height_emu) for e in elements if e.width_emu is not None or e.height_emu is not None}
    probe = solve_tree(spec, guide, s, intrinsics)
    measurements: dict[str, list[ParagraphMeasurement]] = {}
    fits: dict[str, TableFit] = {}
    heights: dict[str, int] = {}
    for element in elements:
        if element.kind == "text":
            measurements[element.id] = measure_element(ctx, element, probe[element.id], s)
            # a declared height is the box (the title band above a top rule); text taller
            # than it is refused as overflow, never given more room
            heights[element.id] = element.height_emu if element.height_emu is not None else element_height_emu(measurements[element.id])
        elif element.table is not None:
            fits[element.id] = fit_table(ctx, element, probe[element.id], s)
            heights[element.id] = fits[element.id].total_height_emu
        elif element.height_emu is not None:
            heights[element.id] = element.height_emu
    floors: dict[str, int] = {}
    _region_heights(spec.root, guide, s, heights, floors, True)
    for node_id, height in heights.items():
        intrinsics[node_id] = IntrinsicSize(intrinsics.get(node_id, IntrinsicSize()).width_emu, height)
    for node_id, floor in floors.items():
        intrinsics[node_id] = IntrinsicSize(intrinsics.get(node_id, IntrinsicSize()).width_emu, None, floor)
    solved = solve_tree(spec, guide, s, intrinsics)
    final: dict[str, list[ParagraphMeasurement]] = {}
    for element in elements:
        if element.kind == "text":
            final[element.id] = measure_element(ctx, element, solved[element.id], s)
            before = [ln.text for m in measurements[element.id] for ln in m.lines]
            after = [ln.text for m in final[element.id] for ln in m.lines]
            if before != after:
                raise CandidateRefused(f"element {element.id!r} measured {len(before)} line(s) at the probe width and {len(after)} at the solved width")
        elif element.id in fits and solved[element.id].width != fits[element.id].box_width:
            raise CandidateRefused(f"table {element.id!r} was fitted at {fits[element.id].box_width} EMU wide and solved to {solved[element.id].width}")
    return Resolved(s, solved, final, fits, validate(spec, guide, s, solved, fits) + measured_violations(ctx, solved, final, fits), ctx.ruler.name, ctx.ruler.fit_epsilon_emu)

# --- scale descent (deckgen content/design_scale.py, docs/measurements/E21-decision.md)

@dataclass
class Attempt:
    scale: Fraction
    resolved: Resolved | None
    refusal: str | None

    @property
    def fits(self) -> bool:
        return self.resolved is not None and self.resolved.fits

    def summary(self) -> dict[str, Any]:
        if self.resolved is None:
            return {"scale": str(self.scale), "result": "refused", "reason": self.refusal}
        return {"scale": str(self.scale), "result": "fit" if self.fits else f"{len(self.resolved.violations)} violation(s)"}

@dataclass
class Outcome:
    status: str  # "fit" | "unfittable"
    resolved: Resolved | None
    attempts: list[Attempt] = field(default_factory=list)
    reason: str = ""
    scale_min: Fraction | None = None

def _attempt(ctx: Context, scale: Fraction) -> Attempt:
    try:
        return Attempt(scale, solve_measured(ctx, scale), None)
    except (CandidateRefused, UnmeasurableTextError) as error:
        return Attempt(scale, None, str(error))

def descend(ctx: Context) -> Outcome:
    """Solve at 1.00; when every violation is scale-fixable, bisect the admitted
    candidates down to the floor (fit is monotone in s, E21); else Unfittable."""
    candidates = floor_admitted_candidates(ctx.guide, ctx.spec)
    if not candidates:
        breaches = table_floor_breaches(ctx.guide, ctx.spec)
        return Outcome("unfittable", None, [], "no scale clears the legibility floor for the roles in use"
                       + (f": {'; '.join(breaches)} (validate --emit refuses the same runs). A house that sets its tables smaller "
                          "inside pasted pictures states that size measured: /tables/picture_text in the completion" if breaches else ""))
    first = _attempt(ctx, candidates[0])
    attempts = [first]
    if first.fits:
        return Outcome("fit", first.resolved, attempts)
    if first.resolved is not None and any(not v.scale_fixable for v in first.resolved.violations):
        return Outcome("unfittable", first.resolved, attempts, "a violation no smaller scale can remove", candidates[0])
    if len(candidates) == 1:
        return Outcome("unfittable", first.resolved, attempts, "the floor admits no smaller scale", candidates[0])
    last = _attempt(ctx, candidates[-1])
    attempts.append(last)
    if not last.fits:
        return Outcome("unfittable", last.resolved or first.resolved, attempts, f"does not fit at the smallest admitted scale {candidates[-1]}", candidates[-1])
    lo, hi = 0, len(candidates) - 1  # lo fails, hi fits
    while hi - lo > 1:
        mid = (lo + hi) // 2
        attempt = _attempt(ctx, candidates[mid])
        attempts.append(attempt)
        if attempt.fits:
            hi, last = mid, attempt
        else:
            lo = mid
    return Outcome("fit", last.resolved, attempts)

# --- output ------------------------------------------------------------------------------

#: What the emitter writes from the solver's resolved entry (_entry_hints), the one
#: source of a written size: the page's fitted scale, not the guide's scale-1 sizes.
FIT_KEYS = ("sz", "b", "lnSpc_spcPts", "spcBef", "spcAft", "spc")


def _entry_hints(entry: TypeEntry) -> dict[str, Any]:
    """What a pptx writer sets so the file draws what was measured."""
    return {"role": entry.role, "latin": entry.family, "sz": hundredths(entry.size_pt), "b": entry.bold, "i": entry.italic, "lnSpc_spcPts": hundredths(entry.line_spacing * entry.size_pt), "spcBef": hundredths(entry.space_before_pt), "spcAft": hundredths(entry.space_after_pt), "spc": hundredths(entry.tracking_pt)}

def resolved_json(ctx: Context, resolved: Resolved) -> dict[str, Any]:
    elements: dict[str, Any] = {}
    for node, _ in walk(ctx.spec.root):
        if not isinstance(node, Element):
            continue
        if node.kind == "text":
            paragraphs = [{**_entry_hints(m.entry), "marL": m.indent_emu, "text": m.text, "measured_face": f"{m.face.family} {m.face.style} ({m.face.provenance})", "allowance_emu": m.allowance_emu, "lines": [ln.text for ln in m.lines], "line_widths_emu": [ln.width_emu for ln in m.lines], "pitch_emu": m.entry.pitch_emu} for m in resolved.measurements[node.id]]
            elements[node.id] = {"kind": "text", "lines": sum(len(p["lines"]) for p in paragraphs), "height_emu": element_height_emu(resolved.measurements[node.id]), "bodyPr": {"wrap": "square", "anchor": "t", "lIns": 0, "tIns": 0, "rIns": 0, "bIns": 0, "autofit": "noAutofit"}, "paragraphs": paragraphs}
        elif node.table is not None:
            fit = resolved.table_fits[node.id]
            elements[node.id] = {"kind": "table", "gridCol_w": [fit.column_widths[c.key] for c in node.table.columns], "tr_h": list(fit.row_heights), "total_height_emu": fit.total_height_emu, "cell_margins_emu": {"marL": fit.padding_emu, "marR": fit.padding_emu, "marT": fit.padding_emu, "marB": fit.padding_emu}, "header_rows": fit.header_rows, "header": _entry_hints(fit.header.entry) if fit.header else None, "cell": _entry_hints(fit.cell.entry), "overflow": fit.overflow, "width_deficit_emu": fit.width_deficit_emu, "column_deficits_emu": fit.column_deficits, "fitting_row_prefix": fit.fitting_row_prefix, "cells": {f"{r},{k}": list(v) for (r, k), v in fit.cell_lines.items()},
                                 # the indent each cell's indent role measured at this scale: the file writes these marL
                                 "cell_indents_emu": {ind: space_emu(ctx.guide, ind, resolved.scale, "x") for *_, ind in node.table.cell_styles if ind}}
        else:
            elements[node.id] = {"kind": node.kind}
    return {"scale": str(resolved.scale), "scale_float": float(resolved.scale), "ruler": resolved.ruler, "fit_epsilon_emu": resolved.fit_epsilon_emu, "boxes": {k: v.as_dict() for k, v in resolved.boxes.items()}, "elements": elements, "violations": [v.as_dict() for v in resolved.violations]}

def outcome_json(ctx: Context, outcome: Outcome) -> dict[str, Any]:
    out: dict[str, Any] = {"status": outcome.status, "attempts": [a.summary() for a in outcome.attempts]}
    if outcome.resolved is not None:
        out["resolved"] = resolved_json(ctx, outcome.resolved)
    if outcome.status == "unfittable":
        resolved = outcome.resolved
        # `fitting_row_prefix` is deckgen's: body rows that fit the PROBE box
        # (the weight share) at the fitted widths. `rows_to_fit_slide` is the
        # split cut: the prefix left once the slide's largest overshoot at
        # scale_min is taken out of this table alone (other content unchanged).
        overshoot = max((v.shortfall_emu or 0 for v in (resolved.violations if resolved else []) if v.code in ("containment", "exceeds_page")), default=0)
        out["unfittable"] = {
            "reason": outcome.reason, "scale_min": None if outcome.scale_min is None else str(outcome.scale_min),
            "overshoot_emu": overshoot,
            "splittable_groups": [g.__dict__ for g in ctx.spec.groups],
            "tables": {k: {"rows": len(f.row_heights) - f.header_rows, "row_heights_emu": list(f.row_heights), "fitting_row_prefix": f.fitting_row_prefix, "rows_to_fit_slide": fitting_prefix(f.row_heights, f.header_rows, f.total_height_emu - overshoot + EMIT_SLACK_EMU), "width_deficit_emu": f.width_deficit_emu} for k, f in (resolved.table_fits if resolved else {}).items()},
        }
    return out

def _print_outcome(ctx: Context, outcome: Outcome) -> None:
    for attempt in outcome.attempts:
        print("attempt", json.dumps(attempt.summary()))
    print(f"status: {outcome.status}")
    resolved = outcome.resolved
    if resolved is None:
        print(f"reason: {outcome.reason}")
        return
    print(f"scale: {resolved.scale} ({float(resolved.scale):.2f})  ruler: {resolved.ruler}  fit_epsilon_emu: {resolved.fit_epsilon_emu}")
    for node_id, box in resolved.boxes.items():
        print(f"  box {node_id:<20} left={box.left:>9} top={box.top:>9} width={box.width:>9} height={box.height:>9}")
    for node_id, rows in resolved.measurements.items():
        print(f"  text {node_id:<19} lines={sum(len(m.lines) for m in rows)} height_emu={element_height_emu(rows)}")
    for node_id, fit in resolved.table_fits.items():
        print(f"  table {node_id:<18} rows={len(fit.row_heights)} height_emu={fit.total_height_emu} widths={list(fit.column_widths.values())} deficit={fit.width_deficit_emu} prefix={fit.fitting_row_prefix}")
    for v in resolved.violations:
        print(f"  violation {v.code} {v.node_id} {v.related_node_id or ''} shortfall={v.shortfall_emu} scale_fixable={v.scale_fixable}: {v.detail}")
    if outcome.status == "unfittable":
        report = outcome_json(ctx, outcome)["unfittable"]
        print(f"unfittable: {outcome.reason}; overshoot {report['overshoot_emu']} EMU; splittable groups: {[g.group_id for g in ctx.spec.groups]}")
        for node_id, info in report["tables"].items():
            print(f"  table {node_id}: {info['rows']} body rows, fitting_row_prefix (probe box) {info['fitting_row_prefix']}, rows_to_fit_slide {info['rows_to_fit_slide']}")

def build_context(spec_path: str, guide_path: str) -> Context:
    raw = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    raw_guide = json.loads(Path(guide_path).read_text(encoding="utf-8"))
    # the page the build enforces: the guide's page size, the chrome zones and the title band
    from build_deck import mark_measured_weights, normalise, prepare_page
    if "root" in raw:
        slide: dict = {}
        raw["root"] = _components_as_boxes(raw["root"])
        raw["root"] = normalise(raw["root"], slide)
        mark_measured_weights(raw["root"], slide, raw_guide)
    prepare_page(raw, raw_guide)
    spec = parse_spec(raw)
    guide = load_guide(raw_guide)
    return Context(guide, ruler_for(raw_guide), default_index(), spec)


def _components_as_boxes(node: dict) -> dict:
    """A component node held as a flexible box of its own id and weight, the stand-in
    build_deck solves before it expands (its first pass), for `solve` on a bare spec."""
    if node.get("type") == "region":
        return {**node, "children": [_components_as_boxes(c) for c in node.get("children", [])]}
    if node.get("type") == "component":
        print(f"component {node['id']!r} ({node.get('kind')}): solved as a flexible box; its own text is measured by component_api", file=sys.stderr)
        return {"type": "element", "id": node["id"], "kind": "image", **({"weight": node["weight"]} if "weight" in node else {})}
    return node


def capacity_slide(path: str, slide_id: str | None) -> dict:
    """The slide `capacity` budgets: a deck JSON's slide by id (the only slide when the
    deck holds one), or a bare page spec wrapped as one slide."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "slides" in raw:
        slides = raw["slides"]
        found = [s for s in slides if slide_id is None or s.get("id") == slide_id]
        if slide_id is None and len(slides) != 1:
            raise SystemExit(f"capacity: {path} holds {len(slides)} slides; name one with --slide ({[s.get('id') for s in slides]})")
        if len(found) != 1:
            raise SystemExit(f"capacity: slide {slide_id!r} is {'not' if not found else 'more than once'} in {path} ({[s.get('id') for s in slides]})")
        return found[0]
    if "root" not in raw:
        raise SystemExit(f"capacity: {path} is neither a deck ({{\"slides\": [...]}}) nor a page spec ({{\"root\": ...}})")
    return {"id": Path(path).stem, "spec": raw}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Solve a slide spec to EMU boxes with measured text fit.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("solve")
    p.add_argument("spec")
    p.add_argument("--guide", required=True)
    p.add_argument("--scale", type=float, default=None, help="one scale only (no descent)")
    p.add_argument("-o", "--out", default=None)
    p = sub.add_parser("capacity", help="each text element's budget on the page the build solves")
    p.add_argument("spec", help="a deck JSON (with --slide ID) or one page spec")
    p.add_argument("--slide", default=None, help="the slide id in a deck JSON")
    p.add_argument("--guide", required=True)
    p.add_argument("--chrome", default="auto", choices=["auto", "none", "draw"], help="as the build will run")
    p.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)
    import cli
    cli.guard_args(args, "out")
    if args.command == "capacity":
        from build_deck import capacity
        payload = capacity(capacity_slide(args.spec, args.slide), json.loads(Path(args.guide).read_text(encoding="utf-8")), args.chrome)
        print(f"{payload['id']}: {payload['status']} at scale {payload['scale']} ({payload['ruler']})")
        for e in payload["elements"]:
            print(f"  {e['id']:<18} {e['role'] or '':<18} box {e['box_in']} in  lines {e['lines_now']}  chars {e['chars_now']}"
                  f"  free {e['chars_free']} chars" + (f" (+{e['lines_free']} lines)" if "lines_free" in e else f"  ({e.get('why')})"))
        for c in payload.get("components", []):
            print(f"  {c['id']:<18} component {c['kind']}: {c['budget']}")
        for t in payload.get("tables", []):
            print(f"  {t['id']:<18} table: {t['body_rows']} body rows need {t['rows_need_in']} in, box {t['box_in']} in; "
                  f"rows_to_fit {t['rows_to_fit']}" + (f", {t['height_free_in']} in free" if "height_free_in" in t else "")
                  + "; tallest rows " + ", ".join(f"{x['row']} ({x['lines']} lines)" for x in t["tallest_rows"]))
        for cause in payload.get("why_not_full_scale", []):
            print(f"  why not at full scale: {cause}")
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
            print(f"wrote {args.out}")
        return 0 if payload["status"] == "fit" else 1
    ctx = build_context(args.spec, args.guide)
    if args.command == "solve":
        if args.scale is None:
            outcome = descend(ctx)
        else:
            scale = checked_scale(args.scale)
            if not scale_clears_floors(ctx.guide, roles_in_use(ctx.spec, tables=False), scale, roles_in_use(ctx.spec, tables=True)):
                print(f"refused: scale {scale} undercuts the legibility floor of an in-use role")
                return 2
            attempt = _attempt(ctx, scale)
            outcome = Outcome("fit" if attempt.fits else "unfittable", attempt.resolved, [attempt], attempt.refusal or "violations at the requested scale", attempt.scale)
        _print_outcome(ctx, outcome)
        payload = outcome_json(ctx, outcome)
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0 if payload.get("status", "fit") == "fit" else 1

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
