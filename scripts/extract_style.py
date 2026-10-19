#!/usr/bin/env python3
"""Extract a style guide draft from a reference deck (.pptx, or .pdf with less).

    extract_style.py reference.pptx -o guide.json [--report guide.md]

What comes out is deckgen's reference-mode cascade, ported: observe every
inheritance-resolved run, fill, line, table and chart on the slide layer; cluster
sizes into levels and bind them to type roles; pool colours by how they are
used and assign colour roles by painted area and WCAG contrast; mine spacing
from the gaps between boxes; mine chrome, motifs, tables, charts, composition
archetypes, register and density bands, and legibility floors. Every value
carries provenance (observed | deterministic_inference, assigned | inferred,
evidence, frequency, master_membership, confidence). Whatever one reproducible
rule cannot decide is listed under `unresolved` with its constraints: the model
completes those while looking at the renders, and never overwrites an observed
value. No house value enters a reference guide.

The report (--report) is the evidence digest the model reads before completing.
"""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ooxml import CHROME_TYPES, EMU_PER_PT, Run, Shape, SlidePrint, fingerprint_deck  # noqa: E402

EMU_PER_INCH = 914400

# --- constants, with where each comes from -------------------------------------------
SIZE_LEVEL_RATIO = 1.10  # deckgen tokens.py:199; asserted: the smallest classic type step is 1.125
GAP_LEVEL_RATIO = 1.25  # deckgen tokens.py:200; asserted
MIN_LEVEL_OBSERVATIONS = 2  # deckgen tokens.py:202; one observation is an exception, not a level
CASE_CONVENTION_SHARE = 0.8  # deckgen tokens.py:204; asserted
RULE_LINE_MAX_WIDTH_EMU = 38100  # 3pt; deckgen tokens.py:210; PowerPoint's line-weight gallery steps
INK_CONTRAST_MIN = 4.5  # WCAG 2.x AA
INK_MUTED_CONTRAST_MIN = 3.0  # WCAG 2.1 SC 1.4.11 non-text
INK_INVERSE_CONTRAST_MAX = 2.0  # deckgen tokens.py:236; asserted
RULE_CONTRAST_FLOOR = 1.05  # deckgen tokens.py:226; asserted
SURFACE_MIN_BOX_FRACTION = 0.25  # deckgen tokens.py:220; asserted ('a panel or a sidebar')
SEMANTIC_MIN_SATURATION = 0.2  # deckgen tokens.py:241; asserted
POSITIVE_HUE = (90, 165)  # deckgen tokens.py:242; asserted hue bands
NEGATIVE_HUE = (345, 15)
POSITION_DIAMETER_EMU = 76_200  # 6pt; deckgen shapes.py:34
ARCHETYPE_IOU_THRESHOLD = 0.5  # PASCAL VOC match criterion; deckgen shapes.py:38
MOTIF_RECURRENCE_FLOOR = 0.5  # deckgen tokens.py:5754
MOTIF_FULL_SPAN = 0.9  # deckgen tokens.py:5761
MOTIF_RULE_ASPECT = 20  # deckgen tokens.py:5767
ALIGNMENT_EDGE_MIN_MEMBERS = 3
ALIGNMENT_EDGE_CAP = 53
EVIDENCE_CAP = 8
MIN_SECONDARY_INK_COUNT = 2  # DEVIATION from deckgen: ink_muted/rule need two votes (keybank bound #113D63 on one run)
# Product safety floors: the smallest size a LibreOffice render of the specimen stays legible at,
# measured in deckgen docs/measurements/E45-decision.md (Arial 400/700 6.0pt; Calibri 400 6.5pt, 700 7.0pt).
PRODUCT_SAFETY_FLOOR_PT = {"body": 6.0, "annotation": 6.0, "display": 6.0, "chart": 6.0}
CORE_TYPE_ROLES = ("type.title", "type.kicker", "type.h1", "type.h2", "type.body", "type.emphasis", "type.caption",
                   "type.footnote", "type.source_line", "type.table_header", "type.table_cell", "type.axis_label", "type.data_label")
CORE_COLOR_ROLES = ("color.surface", "color.surface_alt", "color.ink", "color.ink_muted", "color.accent1", "color.accent2",
                    "color.accent3", "color.rule", "color.positive", "color.negative")
STEP_NAMES = ("space.xs", "space.sm", "space.md", "space.lg", "space.xl")
FLOOR_FAMILIES = {
    "body": ("type.body", "type.emphasis", "type.h1", "type.h2", "type.table_header", "type.table_cell"),
    "annotation": ("type.kicker", "type.caption", "type.footnote", "type.source_line"),
    "display": ("type.title",),
    "chart": ("type.axis_label", "type.data_label"),
}


# --- provenance ------------------------------------------------------------------------


def prov(kind: str, role: str, evidence: list[str], frequency: int, master: bool, confidence: float) -> dict:
    return {"value_provenance": kind, "role_provenance": role, "evidence": evidence[:EVIDENCE_CAP],
            "frequency": frequency, "master_membership": master, "confidence": round(min(1.0, max(0.0, confidence)), 4)}


def observed(evidence: list[str], frequency: int, master: bool, confidence: float, role: str = "assigned") -> dict:
    return prov("observed", role, evidence, frequency, master, confidence)


def inferred(evidence: list[str], frequency: int, master: bool, confidence: float) -> dict:
    return prov("deterministic_inference", "inferred", evidence, frequency, master, 0.75 * confidence)


# --- votes and levels --------------------------------------------------------------------


@dataclass
class Votes:
    count: int = 0
    master: int = 0
    evidence: list[str] = field(default_factory=list)

    def add(self, ev: str, master: bool, weight: int = 1) -> None:
        self.count += weight
        if master:
            self.master += weight
        if len(self.evidence) < EVIDENCE_CAP:
            self.evidence.append(ev)


@dataclass
class Level:
    representative: float
    members: dict[float, Votes]

    @property
    def count(self) -> int:
        return sum(v.count for v in self.members.values())

    @property
    def master_count(self) -> int:
        return sum(v.master for v in self.members.values())

    @property
    def evidence(self) -> list[str]:
        out: list[str] = []
        for v in self.members.values():
            out.extend(v.evidence)
        return out[:EVIDENCE_CAP]

    @property
    def share(self) -> float:
        return self.members[self.representative].count / self.count if self.count else 0.0


def winner(pool: dict[float, Votes]) -> float:
    """Conflict rule: most votes, then most master votes, then the smaller value."""
    return sorted(pool, key=lambda k: (-pool[k].count, -pool[k].master, k))[0]


def cluster_levels(pool: dict[float, Votes], ratio_cap: float | None, diameter_cap: float | None) -> list[Level]:
    """Complete-linkage merge of adjacent values while the merged span stays under the cap
    (ratio in log space, or absolute diameter). Input-order independent."""
    clusters: list[list[float]] = [[k] for k in sorted(pool)]
    while len(clusters) > 1:
        best = None
        for i in range(len(clusters) - 1):
            lo = clusters[i][0]
            hi = clusters[i + 1][-1]
            if ratio_cap is not None:
                if lo <= 0 or hi / lo > ratio_cap:
                    continue
                cost = math.log(hi / lo)
            else:
                if hi - lo > (diameter_cap or 0):
                    continue
                cost = hi - lo
            if best is None or cost < best[0]:
                best = (cost, i)
        if best is None:
            break
        i = best[1]
        clusters[i: i + 2] = [clusters[i] + clusters[i + 1]]
    out = []
    for members in clusters:
        sub = {k: pool[k] for k in members}
        out.append(Level(winner(sub), sub))
    return out


# --- colour maths --------------------------------------------------------------------------


def _channel(v: int) -> float:
    s = v / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def hue_sat(hex_color: str) -> tuple[float, float]:
    r, g, b = (int(hex_color[i: i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s


def in_band(hue: float, band: tuple[int, int]) -> bool:
    lo, hi = band
    return lo <= hue <= hi if lo <= hi else (hue >= lo or hue <= hi)


# --- geometry helpers ------------------------------------------------------------------------


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def hungarian_max(matrix: list[list[float]]) -> float:
    """Optimal assignment on a rectangular score matrix (maximise), pure Python O(n^3)."""
    if not matrix or not matrix[0]:
        return 0.0
    n, m = len(matrix), len(matrix[0])
    transpose = n > m
    if transpose:
        matrix = [[matrix[i][j] for i in range(n)] for j in range(m)]
        n, m = m, n
    big = max(max(row) for row in matrix) + 1.0
    cost = [[big - v for v in row] for row in matrix]
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [math.inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = math.inf
            j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    total = 0.0
    for j in range(1, m + 1):
        if p[j]:
            total += matrix[p[j] - 1][j - 1]
    return total


def slide_similarity(a: list[tuple], b: list[tuple], la: list[str] | None = None, lb: list[str] | None = None) -> float:
    """Hungarian optimal assignment on pairwise IoU, scored over the larger set; role-wise when labelled.
    deckgen shapes.py:432."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    matrix = [[iou(x, y) if (la is None or lb is None or la[i] == lb[j]) else 0.0 for j, y in enumerate(b)] for i, x in enumerate(a)]
    return hungarian_max(matrix) / max(len(a), len(b))


def leader_clusters(groups: list[list[tuple]], labels: list[list[str]] | None = None, threshold: float = ARCHETYPE_IOU_THRESHOLD) -> list[tuple[int, list[int]]]:
    clusters: list[tuple[int, list[int]]] = []
    for index, group in enumerate(groups):
        for anchor, members in clusters:
            if slide_similarity(groups[anchor], group, None if labels is None else labels[anchor], None if labels is None else labels[index]) >= threshold:
                members.append(index)
                break
        else:
            clusters.append((index, [index]))
    return clusters


def union_area(boxes: list[tuple[int, int, int, int]], w: int, h: int) -> int:
    clipped = []
    for x, y, bw, bh in boxes:
        x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + bw), min(h, y + bh)
        if x1 > x0 and y1 > y0:
            clipped.append((x0, y0, x1, y1))
    if not clipped:
        return 0
    xs = sorted({c[0] for c in clipped} | {c[2] for c in clipped})
    total = 0
    for xl, xr in zip(xs, xs[1:]):
        ys = sorted((c[1], c[3]) for c in clipped if c[0] <= xl and c[2] >= xr)
        covered = 0
        cur_lo = cur_hi = None
        for y0, y1 in ys:
            if cur_hi is None or y0 > cur_hi:
                if cur_hi is not None:
                    covered += cur_hi - cur_lo
                cur_lo, cur_hi = y0, y1
            else:
                cur_hi = max(cur_hi, y1)
        if cur_hi is not None:
            covered += cur_hi - cur_lo
        total += covered * (xr - xl)
    return total


def quant(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(v // POSITION_DIAMETER_EMU for v in box)  # type: ignore[return-value]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def modal(values: list, default=None):
    c = Counter(values)
    return c.most_common(1)[0][0] if c else default


# --- the extractor ----------------------------------------------------------------------------


class Extractor:
    def __init__(self, path: str, max_pages: int | None = None) -> None:
        self.path = path
        self.slides: list[SlidePrint] = fingerprint_deck(path, max_pages)
        if not self.slides:
            raise SystemExit(f"{path}: no slides")
        self.is_pdf = self.slides[0].source == "pdf"
        self.w = self.slides[0].width
        self.h = self.slides[0].height
        self.page_area = self.w * self.h
        self.unresolved: list[dict] = []
        self.guide: dict = {}
        self.notes: list[str] = []
        # chrome keys: (kind, quantised box) of layout/master shapes, plus slide-layer shapes
        # repeated at one position on at least half the slides
        self.chrome_keys: set[tuple] = set()
        counts: Counter = Counter()
        for s in self.slides:
            for c in s.chrome:
                if c.box:
                    self.chrome_keys.add((c.kind, quant(c.box)))
            seen = set()
            for sh in s.shapes:
                # Only furniture can be chrome: rules, bands, pictures and the date/footer/number
                # placeholders. A title repeated at one position is composition, not chrome.
                if sh.box and (sh.ph_type in CHROME_TYPES or (sh.text_chars == 0 and sh.kind in ("line", "shape", "picture"))):
                    k = (sh.kind, quant(sh.box))
                    if k not in seen:
                        seen.add(k)
                        counts[k] += 1
        self.recurring_slide_chrome = {k for k, n in counts.items() if n >= max(2, MOTIF_RECURRENCE_FLOOR * len(self.slides))}
        self.chrome_keys |= self.recurring_slide_chrome
        self.color_roles: dict[str, str] = {}  # hex -> role

    # ---- content boxes ----
    def content_boxes(self, s: SlidePrint) -> list[Shape]:
        return [sh for sh in s.shapes if sh.box and sh.box[2] > 0 and sh.box[3] > 0 and (sh.kind, quant(sh.box)) not in self.chrome_keys]

    def open(self, path: str, reason: str, constraints: dict | None = None, candidates: list | None = None) -> None:
        self.unresolved.append({"path": path, "reason": reason, "constraints": constraints or {}, "candidates": candidates or []})

    # ---- typography ----
    def eligible_runs(self) -> list[Run]:
        out = []
        for s in self.slides:
            for r in s.runs:
                if 1.0 <= r.size_pt <= 400.0 and r.size_layer != "autofit":
                    out.append(r)
        return out

    def typography(self) -> None:
        runs = self.eligible_runs()
        pool: dict[float, Votes] = {}
        members: dict[float, list[Run]] = defaultdict(list)
        for r in runs:
            if r.row_class is not None:
                continue  # table text binds to table roles below, like deckgen's _collect_table_text
            size = round(r.size_pt * 2) / 2
            pool.setdefault(size, Votes()).add(f"{r.surface}#{r.ref}", r.size_layer in ("master", "layout", "presentation", "theme"))
            members[size].append(r)
        levels = cluster_levels(pool, SIZE_LEVEL_RATIO, None) if pool else []
        level_members = [[m for size in lv.members for m in members[size]] for lv in levels]
        roles: dict[str, dict] = {}
        assigned: dict[int, str] = {}

        def bind(role: str, idx: int, role_prov: str) -> None:
            lv = levels[idx]
            spec = self.role_spec(level_members[idx], lv, role)
            spec["provenance"] = observed(lv.evidence, lv.count, lv.master_count > 0, lv.share, role_prov)
            roles[role] = spec
            assigned[idx] = role

        # title: the level with the most title-placeholder runs; else the largest level, inferred
        title_votes = [sum(1 for m in lm if m.ph_class == "title") for lm in level_members]
        if levels:
            if max(title_votes) > 0:
                bind("type.title", max(range(len(levels)), key=lambda i: (title_votes[i], levels[i].representative)), "assigned")
            else:
                bind("type.title", len(levels) - 1, "inferred")
        title_idx = next((i for i, r in assigned.items() if r == "type.title"), None)
        # body: most frequent remaining level with >= 2 votes or a body-placeholder anchor; smaller size breaks ties
        body_candidates = [i for i in range(len(levels)) if i not in assigned and (levels[i].count >= MIN_LEVEL_OBSERVATIONS or any(m.ph_class == "body" for m in level_members[i]))]
        if body_candidates:
            i = max(body_candidates, key=lambda i: (levels[i].count, levels[i].master_count, -levels[i].representative))
            bind("type.body", i, "assigned" if any(m.ph_class == "body" for m in level_members[i]) else "inferred")
        body_idx = next((i for i, r in assigned.items() if r == "type.body"), None)
        if body_idx is not None and title_idx is not None:
            between = [i for i in range(len(levels)) if i not in assigned and levels[i].count >= MIN_LEVEL_OBSERVATIONS and body_idx < i < title_idx]
            for role, i in zip(("type.h1", "type.h2"), sorted(between, reverse=True)):
                bind(role, i, "inferred")
            below = [i for i in range(len(levels)) if i not in assigned and i < body_idx]
            if below:
                cap = max(below, key=lambda i: (levels[i].count, levels[i].master_count, levels[i].representative))
                bind("type.caption", cap, "inferred")
                smaller = [i for i in below if i < cap and i not in assigned]
                if smaller:
                    bind("type.footnote", min(smaller), "inferred")
        # emphasis: body size, bold, when bold runs exist at the body level
        if body_idx is not None:
            bold = [m for m in level_members[body_idx] if m.bold]
            if bold:
                spec = self.role_spec(bold, levels[body_idx], "type.emphasis")
                spec["weight"] = 700
                spec["provenance"] = observed([f"{m.surface}#{m.ref}" for m in bold], len(bold), False, 1.0, "inferred")
                roles["type.emphasis"] = spec
        # kicker: an unmapped level between caption and h-levels that is mostly caps or bold
        for i in range(len(levels)):
            if i in assigned or "type.kicker" in roles or body_idx is None:
                continue
            lm = level_members[i]
            share = sum(1 for m in lm if m.caps or m.bold or m.text_sample.isupper()) / len(lm) if lm else 0.0
            cap_size = roles.get("type.caption", {}).get("size_pt", 0.0)
            body_size = roles["type.body"]["size_pt"]
            # a kicker sits between caption and body size: a tiny all-caps level is a footnote or a superscript
            if share >= CASE_CONVENTION_SHARE and levels[i].count >= MIN_LEVEL_OBSERVATIONS and cap_size <= levels[i].representative <= body_size * 1.5:
                bind("type.kicker", i, "inferred")
        # ladder interpolation (deckgen tokens.py:1872): an interior gap between two extracted
        # neighbours takes geometric steps; the size is the only derived member.
        ladder = ("type.footnote", "type.caption", "type.body", "type.h2", "type.h1", "type.title")
        ladder_sizes = {r: roles[r]["size_pt"] for r in ladder if r in roles}
        for pos, role in enumerate(ladder):
            if role in roles:
                continue
            lower = [(i, n) for i, n in enumerate(ladder[:pos]) if n in ladder_sizes]
            upper = [(pos + 1 + o, n) for o, n in enumerate(ladder[pos + 1:]) if n in ladder_sizes]
            if lower and upper:
                li, ln = lower[-1]
                hi, hn = upper[0]
                step = (ladder_sizes[hn] / ladder_sizes[ln]) ** (1 / (hi - li))
                derived = max(1.0, round(ladder_sizes[ln] * step ** (pos - li) * 2) / 2)
                conf = min(roles[ln]["provenance"]["confidence"], roles[hn]["provenance"]["confidence"])
                roles[role] = {"size_pt": derived, "weight": None, "italic": None, "family": None, "alignment": None, "line_spacing": None,
                               "space_before_pt": None, "space_after_pt": None, "tracking_pt": None, "case": None, "ink": None,
                               "partial": True, "derived_from": [ln, hn],
                               "provenance": inferred(roles[ln]["provenance"]["evidence"] + roles[hn]["provenance"]["evidence"],
                                                      roles[ln]["provenance"]["frequency"] + roles[hn]["provenance"]["frequency"], False, conf)}
                ladder_sizes[role] = derived
                self.open(f"/typography/roles/{role}/members", "the ladder interpolation determines the size only; weight, family, case and spacing await completion",
                          {"size_pt": derived, "between": [ln, hn]})
        # table and chart roles
        header = [r for r in runs if r.row_class == "header"]
        cells = [r for r in runs if r.row_class in ("data", "totals")]
        if header:
            lv_pool = {round(r.size_pt * 2) / 2: Votes() for r in header}
            for r in header:
                lv_pool[round(r.size_pt * 2) / 2].add(f"{r.surface}#{r.ref}", False)
            spec = self.role_spec(header, Level(winner(lv_pool), lv_pool), "type.table_header")
            spec["provenance"] = observed([f"{r.surface}#{r.ref}" for r in header], len(header), False, 1.0, "assigned")
            roles["type.table_header"] = spec
        if cells:
            lv_pool = {round(r.size_pt * 2) / 2: Votes() for r in cells}
            for r in cells:
                lv_pool[round(r.size_pt * 2) / 2].add(f"{r.surface}#{r.ref}", False)
            spec = self.role_spec(cells, Level(winner(lv_pool), lv_pool), "type.table_cell")
            spec["provenance"] = observed([f"{r.surface}#{r.ref}" for r in cells], len(cells), False, 1.0, "assigned")
            roles["type.table_cell"] = spec
        chart_sizes = [c.text_size_pt for s in self.slides for c in s.charts if c.text_size_pt]
        chart_colors = [c.text_color for s in self.slides for c in s.charts if c.text_color]
        if chart_sizes:
            size = modal([round(v * 2) / 2 for v in chart_sizes])
            fam = roles.get("type.body", {}).get("family", "minor")
            for role in ("type.axis_label", "type.data_label"):
                roles[role] = {"size_pt": size, "weight": 400, "italic": False, "family": fam, "alignment": "left", "line_spacing": None,
                               "space_before_pt": 0.0, "space_after_pt": 0.0, "tracking_pt": 0.0, "case": "as_typed",
                               "ink": modal(chart_colors),
                               "provenance": observed([f"chart#{i}" for i in range(len(chart_sizes))], len(chart_sizes), False, 1.0, "inferred")}
        # families
        title_faces = Counter(m.family for m in (level_members[title_idx] if title_idx is not None else []) if m.family)
        other_faces = Counter(r.family for r in runs if r.ph_class != "title" and r.family)
        major = title_faces.most_common(1)[0][0] if title_faces else None
        minor = other_faces.most_common(1)[0][0] if other_faces else None
        theme_major = theme_minor = None
        fallbacks = [f for f, _ in (title_faces + other_faces).most_common() if f not in (major, minor)]
        families = {"major": major or minor, "minor": minor or major, "fallbacks": fallbacks,
                    "provenance": observed([f"{r.surface}#{r.ref}" for r in runs[:EVIDENCE_CAP]], len(runs), False, 1.0)}
        if families["major"] is None:
            self.open("/typography/families", "no run declared or inherited a typeface")
        # scale ratio
        sizes = sorted(lv.representative for lv in levels)
        scale_ratio = None
        if len(sizes) >= 3:
            ratios = [b / a for a, b in zip(sizes, sizes[1:])]
            gm = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
            if all(abs(math.log(r / gm)) <= math.log(1.10) for r in ratios):
                scale_ratio = round(gm, 4)
        if scale_ratio is None:
            self.open("/typography/scale_ratio", "the observed size levels are not a geometric ladder within 10%",
                      {"extracted_sizes_pt": sizes})
        # bullets by level
        bullets: dict[int, dict] = {}
        for lvl in range(0, 5):
            lvl_runs = [r for r in runs if r.level == lvl and r.bullet == "char"]
            if lvl_runs:
                bullets[lvl] = {"glyph": modal([r.bullet_glyph for r in lvl_runs if r.bullet_glyph]),
                                "font": modal([r.bullet_font for r in lvl_runs if r.bullet_font]), "runs": len(lvl_runs)}
        # unresolved core roles
        for role in CORE_TYPE_ROLES:
            if role not in roles:
                self.open(f"/typography/roles/{role}", "no observed level binds to this role and no ladder pair brackets it",
                          {"ladder_sizes_pt": sizes, "body_pt": roles.get("type.body", {}).get("size_pt"),
                           "title_pt": roles.get("type.title", {}).get("size_pt"),
                           "rule": {"type.kicker": "small caps or bold label above a title or section, between caption and body size",
                                    "type.footnote": "smaller than caption; the smallest text on the page",
                                    "type.source_line": "the source/note line at the bottom of a slide, usually footnote size",
                                    "type.h1": "between body and title", "type.h2": "between body and h1",
                                    "type.axis_label": "chart tick labels, usually caption size", "type.data_label": "chart value labels, usually caption size"}.get(role, "")})
        for role, spec in roles.items():
            if spec.get("line_spacing") is None:
                self.open(f"/typography/roles/{role}/line_spacing", "no paragraph declared a:lnSpc; the renderer draws single spacing (1.2 x size, measured) when absent",
                          {"default_if_absent": 1.2})
        self.guide["typography"] = {
            "families": families,
            "levels": [{"size_pt": lv.representative, "votes": lv.count, "master_votes": lv.master_count, "share": round(lv.share, 3),
                        "sizes": sorted(lv.members), "role": assigned.get(i)} for i, lv in enumerate(levels)],
            "roles": roles,
            "scale_ratio": scale_ratio,
            "bullets": bullets,
        }
        self._runs = runs
        self._levels = levels
        self._level_members = level_members
        self._roles = roles

    def role_spec(self, members: list[Run], level: Level, role: str) -> dict:
        n = len(members) or 1
        bold_share = sum(1 for m in members if m.bold) / n
        upper = [m for m in members if any(ch.isalpha() for ch in m.text_sample)]
        case = "as_typed"
        if upper:
            if sum(1 for m in upper if m.caps or m.text_sample.isupper()) / len(upper) >= CASE_CONVENTION_SHARE:
                case = "upper"
            elif sum(1 for m in upper if m.text_sample.istitle()) / len(upper) >= CASE_CONVENTION_SHARE:
                case = "title"
        align_map = {"l": "left", "ctr": "center", "r": "right", "just": "justify"}
        aligns = [align_map[m.align] for m in members if m.align in align_map]
        lnspc = [m.line_spacing for m in members if m.line_spacing is not None and m.line_spacing > 0]
        faces = Counter(m.family for m in members if m.family)
        inks = Counter(m.color for m in members if m.color)
        return {
            "size_pt": level.representative,
            "weight": 700 if bold_share > 0.5 else 400,
            "italic": sum(1 for m in members if m.italic) / n > 0.5,
            "family": faces.most_common(1)[0][0] if faces else None,
            "alignment": modal(aligns, "left"),
            "line_spacing": modal(lnspc) if lnspc else None,
            "space_before_pt": round(modal([m.space_before_pt for m in members], 0.0), 2),
            "space_after_pt": round(modal([m.space_after_pt for m in members], 0.0), 2),
            "tracking_pt": 0.0,
            "case": case,
            "ink": inks.most_common(1)[0][0] if inks else None,
            "bold_share": round(bold_share, 3),
        }

    # ---- colour ----
    def color(self) -> None:
        surface_area: dict[str, float] = defaultdict(float)
        ground: dict[str, float] = defaultdict(float)
        votes_surface: dict[str, Votes] = {}
        votes_ink: dict[str, Votes] = {}
        votes_rule: dict[str, Votes] = {}
        votes_accent: dict[str, Votes] = {}
        accent_area: dict[str, float] = defaultdict(float)
        series_slots: dict[int, dict[str, Votes]] = defaultdict(dict)
        for s in self.slides:
            sid = s.part or f"page{s.index + 1}"
            if s.background:
                surface_area[s.background] += self.page_area
                ground[s.background] = 1.0
                votes_surface.setdefault(s.background, Votes()).add(f"{sid}#bg", s.background_layer != "slide")
            for sh in self.content_boxes(s):
                area = sh.box[2] * sh.box[3]  # type: ignore[index]
                if sh.fill and sh.kind not in ("line",):
                    surface_area[sh.fill] += area
                    ground[sh.fill] = max(ground[sh.fill], area / self.page_area)
                    votes_surface.setdefault(sh.fill, Votes()).add(f"{sid}#{sh.ref}", False)
                    votes_accent.setdefault(sh.fill, Votes()).add(f"{sid}#{sh.ref}", False)
                    accent_area[sh.fill] += area
                if sh.line and sh.line_w_emu and 0 < sh.line_w_emu <= RULE_LINE_MAX_WIDTH_EMU:
                    votes_rule.setdefault(sh.line, Votes()).add(f"{sid}#{sh.ref}", False)
            for r in s.runs:
                if r.color and r.row_class is None:
                    votes_ink.setdefault(r.color, Votes()).add(f"{sid}#{r.ref}", r.color_layer in ("master", "layout", "presentation", "theme"))
                elif r.color:
                    votes_ink.setdefault(r.color, Votes()).add(f"{sid}#{r.ref}", False)
            for t in s.tables:
                for f in t.header_fills:
                    if f:
                        votes_accent.setdefault(f, Votes()).add(f"{sid}#{t.ref}/header", False)
                for klass, rules in t.edges.items():
                    for color, width in rules:
                        if color and 0 < width <= RULE_LINE_MAX_WIDTH_EMU:
                            votes_rule.setdefault(color, Votes()).add(f"{sid}#{t.ref}/{klass}", False)
            for c in s.charts:
                for i, f in enumerate(c.series_fills):
                    if f and c.series_fill_layers[i] == "explicit":
                        votes_accent.setdefault(f, Votes()).add(f"{sid}#{c.ref}/ser{i}", False)
                        series_slots[i].setdefault(f, Votes()).add(f"{sid}#{c.ref}/ser{i}", False)
        roles: dict[str, dict] = {}

        def put(role: str, hexv: str, p: dict) -> None:
            roles[role] = {"hex": hexv, "provenance": p}
            self.color_roles.setdefault(hexv, role)

        grounds = [h for h, g in ground.items() if g >= SURFACE_MIN_BOX_FRACTION]
        if grounds:
            surface = max(grounds, key=lambda h: surface_area[h])
            put("color.surface", surface, observed(votes_surface[surface].evidence, votes_surface[surface].count, votes_surface[surface].master > 0,
                                                   surface_area[surface] / max(1.0, sum(surface_area.values()))))
            alts = [h for h in grounds if h != surface]
            if alts:
                alt = max(alts, key=lambda h: surface_area[h])
                put("color.surface_alt", alt, observed(votes_surface[alt].evidence, votes_surface[alt].count, False,
                                                       surface_area[alt] / max(1.0, sum(surface_area.values()))))
            else:
                self.open("/color/roles/color.surface_alt", "no second ground colour covers a quarter of a page",
                          {"candidates": sorted(surface_area, key=surface_area.get, reverse=True)[:5]})
            inks_sorted = sorted(votes_ink, key=lambda h: (-votes_ink[h].count, -votes_ink[h].master, h))
            ink = next((h for h in inks_sorted if contrast(h, surface) >= INK_CONTRAST_MIN), None)
            if ink:
                put("color.ink", ink, observed(votes_ink[ink].evidence, votes_ink[ink].count, votes_ink[ink].master > 0,
                                               votes_ink[ink].count / max(1, sum(v.count for v in votes_ink.values()))))
            else:
                self.open("/color/roles/color.ink", "no run ink reaches 4.5:1 on the surface", {"candidates": inks_sorted[:5]})
            muted = next((h for h in inks_sorted if h != ink and contrast(h, surface) >= INK_MUTED_CONTRAST_MIN and votes_ink[h].count >= MIN_SECONDARY_INK_COUNT), None)
            if muted:
                put("color.ink_muted", muted, observed(votes_ink[muted].evidence, votes_ink[muted].count, False,
                                                       votes_ink[muted].count / max(1, sum(v.count for v in votes_ink.values()))))
            else:
                self.open("/color/roles/color.ink_muted", "no second ink with two or more runs reaches 3:1 on the surface",
                          {"candidates": [h for h in inks_sorted if h != ink][:5], "deviation": "deckgen accepts one run; this port needs two"})
            inverse = next((h for h in inks_sorted if contrast(h, surface) < INK_INVERSE_CONTRAST_MAX and votes_ink[h].count >= 2), None)
            if inverse:
                put("color.ink_inverse", inverse, observed(votes_ink[inverse].evidence, votes_ink[inverse].count, False, 1.0))
            rules_sorted = sorted(votes_rule, key=lambda h: (-votes_rule[h].count, h))
            rule = next((h for h in rules_sorted if contrast(h, surface) >= INK_MUTED_CONTRAST_MIN and votes_rule[h].count >= MIN_SECONDARY_INK_COUNT), None)
            conf = 1.0
            if rule is None:
                rule = next((h for h in rules_sorted if contrast(h, surface) >= RULE_CONTRAST_FLOOR and votes_rule[h].count >= MIN_SECONDARY_INK_COUNT), None)
                conf = 0.5
            if rule:
                put("color.rule", rule, observed(votes_rule[rule].evidence, votes_rule[rule].count, False, conf * votes_rule[rule].count / max(1, sum(v.count for v in votes_rule.values()))))
            else:
                self.open("/color/roles/color.rule", "no thin stroke with two or more occurrences contrasts with the surface",
                          {"candidates": [{"hex": h, "count": votes_rule[h].count} for h in rules_sorted[:5]]})
        else:
            self.open("/color/roles/color.surface", "no background or quarter-page box was observed")
            surface = None
        # accents: chart series order first, then votes, with area as the reported second signal
        taken = {roles[r]["hex"] for r in roles}
        order: list[str] = []
        for slot in sorted(series_slots):
            best = winner_hex(series_slots[slot])
            if best and best not in taken and best not in order:
                order.append(best)
        by_votes = sorted((h for h in votes_accent if h not in taken and h not in order), key=lambda h: (-votes_accent[h].count, -accent_area[h], h))
        order.extend(by_votes)
        for i, h in enumerate(order[:3]):
            put(f"color.accent{i + 1}", h, observed(votes_accent[h].evidence, votes_accent[h].count, False,
                                                     votes_accent[h].count / max(1, sum(v.count for v in votes_accent.values()))))
        for i in range(len(order[:3]), 3):
            self.open(f"/color/roles/color.accent{i + 1}", "fewer accent colours observed than the core vocabulary names",
                      {"theme_accents": self.theme_accents(), "stepping_hint": "extend the observed accents' hue and value stepping"})
        # semantic colours by hue among saturated accents and inks
        pool = {h: votes_accent[h].count for h in votes_accent} | {h: votes_ink[h].count for h in votes_ink}
        sat = {h: hue_sat(h) for h in pool}
        pos = [h for h in pool if sat[h][1] >= SEMANTIC_MIN_SATURATION and in_band(sat[h][0], POSITIVE_HUE)]
        neg = [h for h in pool if sat[h][1] >= SEMANTIC_MIN_SATURATION and in_band(sat[h][0], NEGATIVE_HUE)]
        for role, cands in (("color.positive", pos), ("color.negative", neg)):
            if cands:
                h = max(cands, key=lambda x: pool[x])
                put(role, h, inferred([f"hue {sat[h][0]:.0f} sat {sat[h][1]:.2f}"], pool[h], False, pool[h] / max(1, sum(pool.values()))))
            else:
                self.open(f"/color/roles/{role}", "no saturated colour in the hue band was used", {"hue_band": POSITIVE_HUE if role.endswith("positive") else NEGATIVE_HUE})
        usage = {
            "surface_area_fraction": {h: round(a / max(1.0, sum(surface_area.values())), 4) for h, a in sorted(surface_area.items(), key=lambda kv: -kv[1])[:10]},
            "ink_runs": {h: v.count for h, v in sorted(votes_ink.items(), key=lambda kv: -kv[1].count)[:10]},
            "accent_votes": {h: v.count for h, v in sorted(votes_accent.items(), key=lambda kv: -kv[1].count)[:10]},
            "rule_votes": {h: v.count for h, v in sorted(votes_rule.items(), key=lambda kv: -kv[1].count)[:10]},
            "series_order": [winner_hex(series_slots[i]) for i in sorted(series_slots)],
        }
        self.guide["color"] = {"theme": self.theme_slots(), "roles": roles, "usage": usage}
        self._surface = surface

    def theme_slots(self) -> dict:
        try:
            from ooxml import Package, load_theme
            pkg = Package(self.path)
            chain_master = self.slides[0].master_part
            theme_part = pkg.rel_target(chain_master, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme") if chain_master else None
            if theme_part:
                t = load_theme(pkg, theme_part)
                return {"colors": t.colors, "major_font": t.major_latin, "minor_font": t.minor_latin, "part": theme_part}
        except Exception:  # noqa: BLE001 - PDFs and odd packages have no theme
            pass
        return {}

    def theme_accents(self) -> list[str]:
        th = self.guide.get("color", {}).get("theme") or self.theme_slots()
        cols = th.get("colors", {}) if th else {}
        return [cols[k] for k in ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6") if k in cols]

    def role_of(self, hexv: str | None) -> str | None:
        if hexv is None:
            return None
        if hexv in self.color_roles:
            return self.color_roles[hexv]
        extra = self.guide.setdefault("extra_roles", {})
        name = f"color.extra_{len(extra) + 1}"
        extra[name] = {"hex": hexv, "provenance": observed([], 0, False, 1.0, "inferred")}
        self.color_roles[hexv] = name
        return name

    # ---- spacing ----
    def spacing(self) -> None:
        pool: dict[float, Votes] = {}
        horizontal: dict[float, Votes] = {}
        lefts: list[int] = []
        rights: list[int] = []
        tops: list[int] = []
        bottoms: list[int] = []
        for s in self.slides:
            boxes = [(sh.ref, sh.box) for sh in self.content_boxes(s)]
            if not boxes:
                continue
            sid = s.part or f"page{s.index + 1}"
            by_y = sorted(boxes, key=lambda b: (b[1][1], b[0]))
            for (ra, a), (_, b) in zip(by_y, by_y[1:]):
                gap = b[1] - (a[1] + a[3])
                if 0 < gap < 2 * EMU_PER_INCH:
                    pool.setdefault(float(gap), Votes()).add(f"{sid}#{ra}", False)
            by_x = sorted(boxes, key=lambda b: (b[1][0], b[0]))
            for i, (ra, a) in enumerate(by_x):
                for _, b in by_x[i + 1:]:
                    overlap = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                    if overlap < max(1, min(a[3], b[3])) / 2:
                        continue
                    gap = b[0] - (a[0] + a[2])
                    if 0 < gap < 2 * EMU_PER_INCH:
                        pool.setdefault(float(gap), Votes()).add(f"{sid}#{ra}", False)
                        horizontal.setdefault(float(gap), Votes()).add(f"{sid}#{ra}", False)
                    break
            for sh in self.content_boxes(s):
                if sh.text_inset_emu and sh.text_chars:
                    for inset in sh.text_inset_emu:
                        if 0 < inset < 2 * EMU_PER_INCH:
                            pool.setdefault(float(inset), Votes()).add(f"{sid}#{sh.ref}/bodyPr", False)
            for t in s.tables:
                for m in t.cell_margins_emu:
                    for inset in m:
                        if 0 < inset < 2 * EMU_PER_INCH:
                            pool.setdefault(float(inset), Votes()).add(f"{sid}#{t.ref}/tcPr", False)
            lefts.append(min(b[1][0] for b in boxes))
            rights.append(self.w - max(b[1][0] + b[1][2] for b in boxes))
            tops.append(min(b[1][1] for b in boxes))
            bottoms.append(self.h - max(b[1][1] + b[1][3] for b in boxes))
        levels = [lv for lv in cluster_levels(pool, GAP_LEVEL_RATIO, None) if lv.count >= MIN_LEVEL_OBSERVATIONS]
        by_freq = sorted(levels, key=lambda lv: (-lv.count, -lv.master_count))
        chosen = sorted(by_freq[:5], key=lambda lv: lv.representative)
        steps: dict[str, dict] = {}
        if len(chosen) >= 5:
            for name, lv in zip(STEP_NAMES, chosen):
                steps[name] = {"emu": round(lv.representative), "provenance": observed(lv.evidence, lv.count, False, lv.share, "inferred")}
        elif len(chosen) >= 2:
            slots: list[dict | None] = [None] * 5
            lo, hi = chosen[0].representative, chosen[-1].representative
            slots[0] = {"emu": round(lo), "provenance": observed(chosen[0].evidence, chosen[0].count, False, chosen[0].share, "inferred")}
            slots[4] = {"emu": round(hi), "provenance": observed(chosen[-1].evidence, chosen[-1].count, False, chosen[-1].share, "inferred")}
            for lv in chosen[1:-1]:
                pos = math.log(lv.representative / lo) / math.log(hi / lo) if hi > lo else 0.0
                idx = min(3, max(1, round(pos * 4)))
                while idx < 4 and slots[idx] is not None:
                    idx += 1
                if idx < 4 and slots[idx] is None:
                    slots[idx] = {"emu": round(lv.representative), "provenance": observed(lv.evidence, lv.count, False, lv.share, "inferred")}
            for i in range(1, 4):
                if slots[i] is None:
                    prev_i = max(j for j in range(i) if slots[j] is not None)
                    next_i = min(j for j in range(i + 1, 5) if slots[j] is not None)
                    a, b = slots[prev_i]["emu"], slots[next_i]["emu"]  # type: ignore[index]
                    frac = (i - prev_i) / (next_i - prev_i)
                    slots[i] = {"emu": round(a * (b / a) ** frac) if a > 0 else round(b * frac), "provenance": inferred([f"geometric interpolation between {STEP_NAMES[prev_i]} and {STEP_NAMES[next_i]}"], 0, False, 1.0)}
            for name, slot in zip(STEP_NAMES, slots):
                steps[name] = slot  # type: ignore[assignment]
        else:
            for name in STEP_NAMES:
                self.open(f"/spacing/steps/{name}", "fewer than two gap levels with two or more occurrences",
                          {"observed_gaps_emu": sorted(round(k) for k in pool)[:20]})
        if horizontal:
            hl = sorted(cluster_levels(horizontal, GAP_LEVEL_RATIO, None), key=lambda lv: (-lv.count, lv.representative))
            steps["space.gutter"] = {"emu": round(hl[0].representative), "provenance": observed(hl[0].evidence, hl[0].count, False, hl[0].share, "inferred")}
        else:
            self.open("/spacing/steps/space.gutter", "no side-by-side boxes share a band")
        margins = {}
        for name, vals in (("left", lefts), ("right", rights), ("top", tops), ("bottom", bottoms)):
            if vals:
                p = {float(v): Votes() for v in vals}
                for v in vals:
                    p[float(v)].add("slide", False)
                lv = sorted(cluster_levels(p, None, float(POSITION_DIAMETER_EMU)), key=lambda l: (-l.count, l.representative))[0]
                margins[name] = {"emu": round(lv.representative), "slides": lv.count, "min_emu": min(vals), "median_emu": round(statistics.median(vals))}
        if margins:
            side = min((margins["left"], margins.get("right", margins["left"])), key=lambda m: m["emu"])
            steps["space.margin"] = {"emu": side["emu"], "provenance": observed(["per-slide content extent"], side["slides"], False, side["slides"] / len(self.slides), "inferred")}
        self.guide["spacing"] = {"steps": steps, "margins": margins, "baseline_emu": None,
                                 "gap_levels": [{"emu": round(lv.representative), "votes": lv.count} for lv in sorted(levels, key=lambda lv: lv.representative)]}
        self.open("/spacing/baseline_emu", "a baseline grid is not observable in OOXML; leave null unless the renders show one",
                  {"body_line_pitch_emu": round(1.2 * self._roles.get("type.body", {}).get("size_pt", 0) * EMU_PER_PT) if self._roles.get("type.body") else None})

    # ---- composition, register, density ----
    def composition(self) -> None:
        groups: list[list[tuple]] = []
        labels: list[list[str]] = []
        for s in self.slides:
            cb = self.content_boxes(s)
            groups.append([sh.box for sh in cb])  # type: ignore[misc]
            labels.append([sh.kind for sh in cb])
        fams = leader_clusters(groups)
        archetypes = []
        bands = []
        grids = []
        for fi, (anchor, members) in enumerate(fams):
            boxes = groups[anchor]
            quantized = sorted(quant(b) for b in boxes)
            digest = hashlib.sha256(json.dumps(quantized).encode()).hexdigest()[:12]
            longest = run = 1
            for a, b in zip(members, members[1:]):
                run = run + 1 if b == a + 1 else 1
                longest = max(longest, run)
            archetypes.append({"archetype_id": f"arch-{fi + 1}", "slide_family": f"family-{fi + 1}", "signature": f"sig-{digest}",
                               "occurrence_count": len(members), "consecutive_max": longest, "slides": [m + 1 for m in members],
                               "anchor_slide": anchor + 1, "kinds": Counter(labels[anchor]).most_common()})
            if not boxes:
                continue
            lp = {float(b[0]): Votes() for b in boxes}
            for b in boxes:
                lp[float(b[0])].add("anchor", False)
            cols = [lv for lv in cluster_levels(lp, None, float(POSITION_DIAMETER_EMU)) if lv.count >= 2]
            if 2 <= len(cols) <= 24:
                grids.append({"grid_id": f"grid-{fi + 1}", "columns": len(cols), "left_edges_emu": [round(lv.representative) for lv in cols], "slide_family": f"family-{fi + 1}"})
            intervals = sorted((b[1], b[1] + b[3]) for b in boxes)
            merged: list[list[int]] = []
            for y0, y1 in intervals:
                if merged and y0 <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], y1)
                else:
                    merged.append([y0, y1])
            if 2 <= len(merged) <= 8:
                for bi, (y0, y1) in enumerate(merged):
                    bands.append({"band_id": f"band-{fi + 1}-{bi + 1}", "role": f"band_{bi + 1}", "height_fraction": round((y1 - y0) / self.h, 4),
                                  "top_fraction": round(y0 / self.h, 4), "slide_family": f"family-{fi + 1}"})
        edges = []
        for axis, kind, fn in (("x", "leading", lambda b: b[0]), ("x", "trailing", lambda b: b[0] + b[2]), ("x", "center", lambda b: b[0] + b[2] // 2),
                               ("y", "leading", lambda b: b[1]), ("y", "trailing", lambda b: b[1] + b[3])):
            p: dict[float, Votes] = {}
            for si, g in enumerate(groups):
                for b in g:
                    p.setdefault(float(fn(b)), Votes()).add(f"slide{si + 1}", False)
            for lv in cluster_levels(p, None, float(POSITION_DIAMETER_EMU)) if p else []:
                if lv.count >= ALIGNMENT_EDGE_MIN_MEMBERS:
                    edges.append({"axis": axis, "edge_kind": kind, "position_emu": max(0, round(lv.representative)), "member_count": lv.count})
        edges.sort(key=lambda e: (-e["member_count"], e["position_emu"]))
        self.guide["composition"] = {"archetypes": archetypes, "bands": bands, "column_grids": grids, "alignment_edges": edges[:ALIGNMENT_EDGE_CAP]}
        # register and density
        per_kind: dict[str, list[int]] = defaultdict(list)
        decoration: list[int] = []
        container: list[float] = []
        uniformity: list[float] = []
        elements: list[int] = []
        area_fraction: list[float] = []
        words: list[int] = []
        rows_per_inch: list[float] = []
        cooccur: Counter = Counter()
        for s in self.slides:
            cb = self.content_boxes(s)
            kinds = Counter(_register_kind(sh) for sh in cb)
            for k in ("text", "image", "shape", "table", "chart", "line"):
                per_kind[k].append(kinds.get(k, 0))
            cooccur[tuple(sorted(k for k in kinds if kinds[k]))] += 1
            decoration.append(sum(1 for sh in cb if _register_kind(sh) in ("shape", "line") and sh.text_chars == 0))
            texty = [sh for sh in cb if sh.text_chars > 0]
            if texty:
                container.append(sum(1 for sh in texty if sh.fill or sh.line) / len(texty))
            areas = [sh.box[2] * sh.box[3] for sh in cb]  # type: ignore[index]
            if len(areas) >= 2:
                m = statistics.mean(areas)
                uniformity.append(max(0.0, 1.0 - statistics.pstdev(areas) / m) if m else 0.0)
            elements.append(len(cb))
            area_fraction.append(union_area([sh.box for sh in cb], self.w, self.h) / self.page_area)  # type: ignore[misc]
            words.append(sum(r.words for r in s.runs))
            for t in s.tables:
                height_in = sum(t.row_heights_emu) / EMU_PER_INCH
                if height_in > 0:
                    rows_per_inch.append(t.rows / height_in)

        def band(values: list, name: str) -> dict:
            return {"metric": name, "low": round(percentile(values, 0.1), 4), "high": round(percentile(values, 0.9), 4),
                    "median": round(percentile(values, 0.5), 4), "n": len(values)} if values else {"metric": name, "low": None, "high": None, "n": 0}

        self.guide["register_stats"] = {
            "kind_counts": {k: band(v, "kind_count") for k, v in per_kind.items()},
            "kind_cooccurrence": [{"kinds": list(k), "slides": n} for k, n in cooccur.most_common(8)],
            "decoration_counts": band(decoration, "decoration_count"),
            "container_ratio": band(container, "container_ratio"),
            "element_area_uniformity": band(uniformity, "element_area_uniformity"),
            "low_confidence": len(self.slides) < 8,
            "definitions": {"decoration_count": "filled shapes and lines without text per slide, chrome excluded",
                            "container_ratio": "text-bearing shapes with a fill or outline over all text-bearing shapes",
                            "element_area_uniformity": "1 minus the coefficient of variation of element areas (1 = equal tiles)"},
        }
        self.guide["density_bands"] = {
            "elements_per_slide": band(elements, "elements_per_slide"),
            "content_area_fraction": band(area_fraction, "content_area_fraction"),
            "words_per_slide": band(words, "words_per_slide"),
            "table_rows_per_inch": band(rows_per_inch, "table_rows_per_inch"),
        }
        if not rows_per_inch:
            self.open("/density_bands/table_rows_per_inch", "no table with row heights observed")

    # ---- chrome and motifs ----
    def chrome_and_motifs(self) -> None:
        chrome = []
        seen: set = set()
        samples: dict[tuple, Shape] = {}
        presence: Counter = Counter()
        text_of: dict[tuple, str] = {}
        for s in self.slides:
            for c in s.chrome:
                if c.box:
                    k = (c.kind, quant(c.box), c.layer)
                    samples.setdefault(k, c)
                    presence[k] += 1
            for sh in s.shapes:
                if sh.box and (sh.kind, quant(sh.box)) in self.recurring_slide_chrome:
                    k = (sh.kind, quant(sh.box), "slide")
                    samples.setdefault(k, sh)
                    presence[k] += 1
                    if sh.text_chars and k not in text_of:
                        text_of[k] = " ".join(r.text_sample for r in s.runs if r.ref.startswith(sh.ref + "/"))[:60]
            for r in s.chrome_runs:
                pass
        chrome_text: dict[str, str] = {}
        for s in self.slides[:1]:
            for r in s.chrome_runs:
                key = r.ref.split("/p[")[0]
                chrome_text[key] = (chrome_text.get(key, "") + " " + r.text_sample).strip()[:60]
        merged: dict[tuple, tuple[Shape, list[str], int]] = {}
        for k, sh in samples.items():
            key = (k[0], k[1])
            if key in merged:
                prev, layers, n = merged[key]
                layers.append(k[2])
                merged[key] = (prev if prev.layer != "slide" or sh.layer == "slide" else sh, layers, max(n, presence[k]))
            else:
                merged[key] = (sh, [k[2]], presence[k])
        for key, (sh, layers, present) in sorted(merged.items(), key=lambda kv: (kv[1][0].box[1], kv[1][0].box[0])):  # type: ignore[index]
            k = (key[0], key[1], sh.layer)
            x, y, w, h = sh.box  # type: ignore[misc]
            kind = "other"
            if sh.ph_type == "ftr":
                kind = "footer"
            elif sh.ph_type == "sldNum":
                kind = "page_number"
            elif sh.ph_type == "dt":
                kind = "date"
            elif sh.kind == "picture":
                kind = "logo"
            elif sh.kind == "line" or (h * MOTIF_RULE_ASPECT <= w) or (w * MOTIF_RULE_ASPECT <= h):
                kind = "rule"
            elif sh.text_chars:
                kind = "label"
            elif sh.fill:
                kind = "band"
            span = "full" if (w >= MOTIF_FULL_SPAN * self.w or h >= MOTIF_FULL_SPAN * self.h) else "partial"
            dist = {"slide_top": y / self.h, "slide_bottom": (self.h - y - h) / self.h, "slide_left": x / self.w, "slide_right": (self.w - x - w) / self.w}
            if w >= MOTIF_FULL_SPAN * self.w:  # a full-width mark anchors to a horizontal edge
                dist = {k: v for k, v in dist.items() if k in ("slide_top", "slide_bottom")}
            elif h >= MOTIF_FULL_SPAN * self.h:
                dist = {k: v for k, v in dist.items() if k in ("slide_left", "slide_right")}
            anchor = min(dist, key=dist.get)
            if dist[anchor] > 0.15:
                anchor = "center"
            entry = {
                "chrome_id": f"chrome-{len(chrome) + 1}", "kind": kind, "source_layer": sh.layer, "shape_kind": sh.kind,
                "box_in": [round(v / EMU_PER_INCH, 3) for v in (x, y, w, h)], "anchor": anchor, "span": span,
                "fill_role": self.role_of(sh.fill) if sh.fill else None, "fill_hex": sh.fill,
                "line_role": self.role_of(sh.line) if sh.line else None, "line_hex": sh.line,
                "line_width_pt": round(sh.line_w_emu / EMU_PER_PT, 2) if sh.line_w_emu else None,
                "text": text_of.get(k) or chrome_text.get(sh.ref) or None,
                "layers": sorted(set(layers)),
                "slides_present": present, "of_slides": len(self.slides),
                "exclusion_zone_in": [round(v / EMU_PER_INCH, 3) for v in (x, y, w, h)],
            }
            if sh.layer != "slide" and sh.text_chars:
                runs = [r for s in self.slides[:1] for r in s.chrome_runs if r.ref.startswith(sh.ref)]
                if runs:
                    entry["text_style"] = {"family": modal([r.family for r in runs]), "size_pt": modal([r.size_pt for r in runs]),
                                           "ink_hex": modal([r.color for r in runs]), "bold": modal([r.bold for r in runs])}
            chrome.append(entry)
        self.guide["chrome"] = chrome
        motifs = []
        for c in chrome:
            if c["kind"] in ("rule", "band") and c["slides_present"] >= MOTIF_RECURRENCE_FLOOR * len(self.slides):
                motifs.append({"motif_id": f"motif-{len(motifs) + 1}",
                               "name": f"{'Full-width' if c['span'] == 'full' else 'Partial'} {c['kind']} at {c['anchor'].replace('slide_', '')}, on {c['slides_present']} of {len(self.slides)} slides",
                               "geometry_preset": "line" if c["kind"] == "rule" else "rect",
                               "line_role": c["line_role"], "fill_role": c["fill_role"], "line_width_pt": c["line_width_pt"],
                               "anchor": c["anchor"], "span": c["span"], "box_in": c["box_in"], "effect": "none",
                               "provenance": observed([c["chrome_id"]], c["slides_present"], c["source_layer"] != "slide", c["slides_present"] / len(self.slides), "inferred")})
        self.guide["motifs"] = motifs

    # ---- tables and charts ----
    def tables(self) -> None:
        obs = [t for s in self.slides for t in s.tables]
        if not obs:
            self.guide["tables"] = None
            self.open("/tables", "no table on the slide layer", {"rule": "derive header from the strongest ink-on-surface pairing; banding from the surface scale; padding from the smallest spacing step"})
            return
        header_fill = modal([f for t in obs for f in t.header_fills if f])
        header_runs = [r for s in self.slides for r in s.runs if r.row_class == "header"]
        cell_runs = [r for s in self.slides for r in s.runs if r.row_class == "data"]
        band_fill = modal([f for t in obs for f in t.band_fills if f])
        data_fill = modal([f for t in obs for f in t.data_fills if f])
        edges = {}
        for klass in ("table_top", "header_bottom", "row_interior", "table_bottom", "table_left", "column_interior", "table_right"):
            rules = [rule for t in obs for rule in t.edges.get(klass, [])]
            if not rules:
                continue
            m = modal([(c, w) for c, w in rules])
            edges[klass] = ({"width_emu": m[1], "width_pt": round(m[1] / EMU_PER_PT, 2), "color_role": self.role_of(m[0]), "color_hex": m[0]} if m and m[0] else {"width_emu": 0, "none": True})
        margins = [m for t in obs for m in t.cell_margins_emu]
        pad = modal([m[0] for m in margins]) if margins else 45720
        steps = self.guide.get("spacing", {}).get("steps", {})
        nearest_step = min(steps, key=lambda n: abs(steps[n]["emu"] - pad)) if steps else None
        col_align_by_type: dict[str, Counter] = {"numeric": Counter(), "text": Counter()}
        for t in obs:
            for a, num in zip(t.col_aligns, t.col_numeric):
                col_align_by_type["numeric" if num >= 0.5 else "text"][{"l": "left", "ctr": "center", "r": "right", "just": "justify"}.get(a, a)] += 1
        self.guide["tables"] = {
            "count": len(obs),
            "header_fill_role": self.role_of(header_fill), "header_fill_hex": header_fill,
            "header_ink_role": self.role_of(modal([r.color for r in header_runs])) if header_runs else None,
            "header_bold": (sum(1 for r in header_runs if r.bold) / len(header_runs)) > 0.5 if header_runs else None,
            "banding_role": self.role_of(band_fill) if band_fill and band_fill != data_fill else None, "banding_hex": band_fill if band_fill != data_fill else None,
            "data_fill_hex": data_fill,
            "edge_rules": edges,
            "cell_padding_emu": pad, "cell_padding_role": nearest_step,
            "alignment_by_column_type": {k: (v.most_common(1)[0][0] if v else None) for k, v in col_align_by_type.items()},
            "header_size_pt": modal([r.size_pt for r in header_runs]) if header_runs else None,
            "cell_size_pt": modal([r.size_pt for r in cell_runs]) if cell_runs else None,
            "rows_cols": [(t.rows, t.cols) for t in obs][:10],
            "provenance": observed([t.ref for t in obs], len(obs), False, 1.0),
        }

    def charts(self) -> None:
        obs = [c for s in self.slides for c in s.charts]
        if not obs:
            self.guide["charts"] = None
            self.open("/charts", "no native chart on the slide layer", {"rule": "use the accent order for series; axis labels at caption size in ink_muted; no gridlines unless the register shows them"})
            return
        per_kind: dict[str, dict] = {}
        for kind in sorted({k for c in obs for k in c.kinds}):
            cs = [c for c in obs if kind in c.kinds]
            per_kind[kind] = {
                "count": len(cs),
                "gridlines_major": sum(1 for c in cs if c.gridlines_major) / len(cs),
                "gridline_color_hex": modal([c.gridline_color for c in cs if c.gridline_color]),
                "gridline_width_pt": (modal([c.gridline_w_emu for c in cs if c.gridline_w_emu]) or 0) / EMU_PER_PT,
                "data_labels": sum(1 for c in cs if c.data_labels) / len(cs),
                "legend_position": modal([c.legend_pos for c in cs]),
                "title_present": sum(1 for c in cs if c.has_title) / len(cs),
                "text_size_pt": modal([c.text_size_pt for c in cs if c.text_size_pt]),
                "text_color_hex": modal([c.text_color for c in cs if c.text_color]),
                "axis_line_hex": modal([c.axis_line_color for c in cs if c.axis_line_color]),
            }
        order: list[str | None] = []
        for i in range(6):
            fills = [c.series_fills[i] for c in obs if len(c.series_fills) > i and c.series_fills[i]]
            order.append(modal(fills))
        self.guide["charts"] = {"count": len(obs), "per_kind": per_kind,
                                "series_color_order": [self.role_of(h) if h else None for h in order if h],
                                "series_color_hex": [h for h in order if h],
                                "provenance": observed([c.ref for c in obs], len(obs), False, 1.0)}

    # ---- shape language, imagery, floors ----
    def shapes_and_imagery(self) -> None:
        shapes = [sh for s in self.slides for sh in self.content_boxes(s)]
        prst = Counter(sh.prst for sh in shapes if sh.prst)
        widths = Counter(sh.line_w_emu for sh in shapes if sh.line and sh.line_w_emu)
        dashes = Counter(sh.dash for sh in shapes if sh.line and sh.dash)
        effects = sum(1 for sh in shapes if sh.has_effects)
        pics = [sh for sh in shapes if sh.kind == "picture"]
        self.guide["shape_language"] = {
            "preset_geometries": prst.most_common(8),
            "line_widths_pt": [(round(w / EMU_PER_PT, 2), n) for w, n in widths.most_common(6)],
            "dash_styles": dashes.most_common(4),
            "effects": "none_flat" if effects == 0 else f"effects on {effects} of {len(shapes)} shapes",
            "rounded_corners": prst.get("roundRect", 0),
            "icon_style": None,
        }
        self.open("/shape_language/icon_style", "icon style is read from renders, not OOXML")
        self.open("/shape_language/corner_radii", "roundRect adjustment values are not read by this port; measure on the renders if rounded shapes recur",
                  {"round_rect_count": prst.get("roundRect", 0)})
        classes = Counter()
        for p in pics:
            area = p.box[2] * p.box[3] / self.page_area  # type: ignore[index]
            aspect = p.box[2] / max(1, p.box[3])  # type: ignore[index]
            classes["full_bleed" if area >= 0.5 else "wide" if aspect >= 1.5 else "tall" if aspect <= 0.67 else "square"] += 1
        self.guide["imagery"] = {"pictures": len(pics), "per_slide": round(len(pics) / len(self.slides), 2), "crop_convention": modal(list(classes.elements())),
                                 "classes": dict(classes), "framed": sum(1 for p in pics if p.line)}
        self.open("/imagery/register_kind", "photo vs illustration vs logo wall is read from renders", {"pictures": len(pics)})
        # floors: Tukey lower fence per family over eligible runs, filed by nearest role size
        role_sizes = {r: spec["size_pt"] for r, spec in self._roles.items() if spec.get("size_pt")}
        fam_of_role = {role: fam for fam, roles in FLOOR_FAMILIES.items() for role in roles}
        samples: dict[str, list[float]] = defaultdict(list)
        for r in self._runs:
            if r.ph_class == "title":
                samples["display"].append(r.size_pt)
                continue
            if r.row_class is not None:
                samples["body"].append(r.size_pt)
                continue
            if not role_sizes:
                continue
            nearest = min(role_sizes, key=lambda role: abs(math.log(r.size_pt / role_sizes[role])))
            samples[fam_of_role.get(nearest, "body")].append(r.size_pt)
        for s in self.slides:
            for c in s.charts:
                if c.text_size_pt:
                    samples["chart"].append(c.text_size_pt)
        floors = {}
        for fam, roles in FLOOR_FAMILIES.items():
            vals = samples.get(fam, [])
            if not vals:
                self.open(f"/floors/{fam}/floor_pt", "no run filed to this family", {"roles": list(roles), "absolute_floor_pt": PRODUCT_SAFETY_FLOOR_PT[fam]})
                floors[fam] = {"roles": list(roles), "floor_pt": None, "absolute_floor_pt": PRODUCT_SAFETY_FLOOR_PT[fam], "sample_size": 0}
                continue
            q1, q3 = percentile(vals, 0.25), percentile(vals, 0.75)
            fence = q1 - 1.5 * (q3 - q1)
            kept = [v for v in vals if v >= fence]
            floors[fam] = {"roles": list(roles), "floor_pt": min(kept), "trimmed_outlier_count": len(vals) - len(kept), "sample_size": len(vals),
                           "absolute_floor_pt": PRODUCT_SAFETY_FLOOR_PT[fam],
                           "provenance": observed([], len(vals), False, 1.0)}
        self.guide["floors"] = floors
        self.guide["floors_note"] = "absolute_floor_pt: product safety floor measured in deckgen E45 on LibreOffice renders (Arial 6.0pt); never generate below max(floor_pt, absolute_floor_pt)"

    # ---- assembly ----
    def run(self) -> dict:
        self.typography()
        self.color()
        self.spacing()
        self.composition()
        self.chrome_and_motifs()
        self.tables()
        self.charts()
        self.shapes_and_imagery()
        # bind role inks and chrome colours to roles (after colour roles exist)
        for role, spec in self._roles.items():
            spec["ink_role"] = self.role_of(spec.get("ink")) if spec.get("ink") else None
        for path, reason in (("/description", "written by the model from the renders and this draft: summary, typography, color, layout, tables, imagery, motifs, never_does, tone"),
                             ("/derivation_rules", "how to extend the palette and the type ladder to roles the reference never showed"),
                             ("/continuation", "header repeat, cont'd mark and takeaway policy when a slide splits"),
                             ("/gallery", "cropped renders of interesting components, with captions (gallery.py)"),
                             ("/exemplars", "one whole-slide render per composition family (gallery.py)")):
            self.open(path, reason)
        self.guide = {
            "schema": "pptx-skill style guide draft v1",
            "reference": {"file": str(self.path), "sha256": hashlib.sha256(Path(self.path).read_bytes()).hexdigest(), "slides": len(self.slides),
                          "format": "pdf" if self.is_pdf else "pptx",
                          "page": {"width_emu": self.w, "height_emu": self.h, "width_in": round(self.w / EMU_PER_INCH, 3), "height_in": round(self.h / EMU_PER_INCH, 3),
                                   "orientation": "landscape" if self.w >= self.h else "portrait"},
                          "layouts_used": Counter(s.layout_name for s in self.slides).most_common() if not self.is_pdf else None},
            **self.guide,
            "unresolved": self.unresolved,
            "notes": self.notes,
        }
        return self.guide


def winner_hex(pool: dict[str, Votes]) -> str | None:
    if not pool:
        return None
    return sorted(pool, key=lambda k: (-pool[k].count, -pool[k].master, k))[0]


def _register_kind(sh: Shape) -> str:
    if sh.kind in ("text_box", "text_shape"):
        return "text"
    if sh.kind == "picture":
        return "image"
    if sh.kind in ("table", "chart", "line"):
        return sh.kind
    return "shape"


# --- report ------------------------------------------------------------------------------------


def report(guide: dict) -> str:
    g = guide
    out = [f"# Style evidence: {Path(g['reference']['file']).name}", "",
           f"{g['reference']['slides']} slides, {g['reference']['page']['width_in']} x {g['reference']['page']['height_in']} in, format {g['reference']['format']}.", ""]
    t = g.get("typography", {})
    out.append("## Typography")
    fam = t.get("families", {})
    out.append(f"Families: major {fam.get('major')}, minor {fam.get('minor')}, fallbacks {fam.get('fallbacks')}.")
    out.append("")
    out.append("| level size pt | votes | master votes | bound role |")
    out.append("|---|---|---|---|")
    for lv in t.get("levels", []):
        out.append(f"| {lv['size_pt']} | {lv['votes']} | {lv['master_votes']} | {lv.get('role') or ''} |")
    out.append("")
    out.append("| role | size | weight | italic | family | align | line spacing | before/after pt | case | ink | provenance | conf |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for role, sp in t.get("roles", {}).items():
        p = sp.get("provenance", {})
        out.append(f"| {role} | {sp.get('size_pt')} | {sp.get('weight')} | {sp.get('italic')} | {sp.get('family')} | {sp.get('alignment')} | {sp.get('line_spacing')} | {sp.get('space_before_pt')}/{sp.get('space_after_pt')} | {sp.get('case')} | {sp.get('ink')} | {p.get('value_provenance')}/{p.get('role_provenance')} | {p.get('confidence')} |")
    out.append("")
    out.append(f"Scale ratio: {t.get('scale_ratio')}. Bullets by level: {json.dumps(t.get('bullets'))}.")
    c = g.get("color", {})
    out += ["", "## Colour", "", "| role | hex | provenance | freq | conf |", "|---|---|---|---|---|"]
    for role, v in c.get("roles", {}).items():
        p = v["provenance"]
        out.append(f"| {role} | {v['hex']} | {p['value_provenance']}/{p['role_provenance']} | {p['frequency']} | {p['confidence']} |")
    out.append("")
    out.append(f"Theme slots: {json.dumps(c.get('theme', {}).get('colors'))}")
    out.append(f"Usage: surface area {json.dumps(c.get('usage', {}).get('surface_area_fraction'))}; ink runs {json.dumps(c.get('usage', {}).get('ink_runs'))}; accent votes {json.dumps(c.get('usage', {}).get('accent_votes'))}; rule votes {json.dumps(c.get('usage', {}).get('rule_votes'))}")
    s = g.get("spacing", {})
    out += ["", "## Spacing", ""]
    out.append("| step | inches | emu | provenance |")
    out.append("|---|---|---|---|")
    for name, v in s.get("steps", {}).items():
        out.append(f"| {name} | {round(v['emu'] / EMU_PER_INCH, 3)} | {v['emu']} | {v['provenance']['value_provenance']} conf {v['provenance']['confidence']} |")
    out.append("")
    out.append(f"Margins (modal per side): {json.dumps({k: round(v['emu'] / EMU_PER_INCH, 3) for k, v in s.get('margins', {}).items()})} in; gap levels {[(round(l['emu'] / EMU_PER_INCH, 3), l['votes']) for l in s.get('gap_levels', [])]}")
    comp = g.get("composition", {})
    out += ["", "## Composition", ""]
    for a in comp.get("archetypes", []):
        out.append(f"- {a['archetype_id']}: slides {a['slides']} (anchor {a['anchor_slide']}), kinds {a['kinds']}, longest run {a['consecutive_max']}")
    out.append(f"Column grids: {json.dumps(comp.get('column_grids'))}")
    out.append(f"Bands: {[(b['band_id'], b['top_fraction'], b['height_fraction']) for b in comp.get('bands', [])][:16]}")
    out.append(f"Alignment edges (top): {[(e['axis'], e['edge_kind'], round(e['position_emu'] / EMU_PER_INCH, 2), e['member_count']) for e in comp.get('alignment_edges', [])][:12]}")
    out += ["", "## Chrome and motifs", ""]
    for ch in g.get("chrome", []):
        out.append(f"- {ch['chrome_id']} {ch['kind']} ({ch['shape_kind']}, {ch['source_layer']}) box {ch['box_in']} in, {ch['anchor']}, {ch['span']}, fill {ch['fill_hex']}, line {ch['line_hex']} {ch['line_width_pt']}pt, text {ch['text']!r}, style {ch.get('text_style')}, on {ch['slides_present']}/{ch['of_slides']} slides")
    for m in g.get("motifs", []):
        out.append(f"- {m['motif_id']}: {m['name']}, line {m['line_role']} {m['line_width_pt']}pt, fill {m['fill_role']}")
    out += ["", "## Register and density", ""]
    out.append(json.dumps(g.get("register_stats"), indent=0)[:1500])
    out.append(json.dumps(g.get("density_bands"), indent=0))
    out += ["", "## Tables", "", json.dumps(g.get("tables"), indent=0, default=str)[:2500]]
    out += ["", "## Charts", "", json.dumps(g.get("charts"), indent=0, default=str)[:2500]]
    out += ["", "## Shape language and imagery", "", json.dumps(g.get("shape_language"), default=str), json.dumps(g.get("imagery"), default=str)]
    out += ["", "## Floors", "", json.dumps(g.get("floors"), default=str)]
    out += ["", "## Unresolved (the model completes these from the renders; observed values above are never overwritten)", ""]
    for u in g.get("unresolved", []):
        out.append(f"- `{u['path']}`: {u['reason']}" + (f" constraints {json.dumps(u['constraints'], default=str)[:300]}" if u.get("constraints") else ""))
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference")
    ap.add_argument("-o", "--out", default=None, help="guide JSON (default: <stem>.style.json next to the reference)")
    ap.add_argument("--report", default=None, help="evidence digest markdown (default: alongside the JSON)")
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args(argv)
    ex = Extractor(args.reference, args.max_pages)
    guide = ex.run()
    out = Path(args.out) if args.out else Path(args.reference).with_suffix(".style.json")
    out.write_text(json.dumps(guide, indent=1, default=str))
    rep = Path(args.report) if args.report else out.with_suffix(".md")
    rep.write_text(report(guide))
    roles = guide.get("typography", {}).get("roles", {})
    print(json.dumps({"guide": str(out), "report": str(rep), "slides": guide["reference"]["slides"],
                      "type_roles": {r: roles[r]["size_pt"] for r in roles},
                      "color_roles": {r: v["hex"] for r, v in guide.get("color", {}).get("roles", {}).items()},
                      "spacing": {k: v["emu"] for k, v in guide.get("spacing", {}).get("steps", {}).items()},
                      "unresolved": len(guide["unresolved"])}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
