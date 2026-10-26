#!/usr/bin/env python3
"""Extract a style guide draft from a reference deck (.pptx, or .pdf with less).

    extract_style.py reference.pptx -o guide.json [--report guide.md]

What comes out is a reference-mode cascade: observe every
inheritance-resolved run, fill, line, table and chart on the slide layer; cluster
sizes into levels and bind them to type roles; pool colours by how they are
used and assign colour roles by painted area and WCAG contrast; mine spacing
from the gaps between boxes; mine chrome, motifs, tables, charts, composition
archetypes, register and density bands, legibility floors, and the page titles by
position (text, length, lines, the blocks above and below). Every value
carries provenance (observed | deterministic_inference, assigned | inferred,
evidence, frequency, master_membership, confidence). Whatever one reproducible
rule cannot decide is listed under `unresolved` with its constraints: the model
completes those while looking at the renders, and never overwrites an observed
value. No house value enters a reference guide.

The report (--report) is the evidence digest the model reads before completing.

Slides carrying the pptx-skill origin tag (emit_pptx.py write_origin_tag) are this
skill's own output and are skipped unless --include-generated; the count is in the
notes and on stdout.
"""

from __future__ import annotations

import argparse
import bisect
import colorsys
import hashlib
import json
import math
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import ClassVar

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan  # noqa: E402
import textfit  # noqa: E402
from ooxml import CHROME_TYPES, EMU_PER_PT, RECURRENCE_FLOOR, TITLE_TYPES, Run, Shape, SlidePrint, fingerprint_deck, is_type_evidence, paragraphs_words, pdf_triage, vector_shapes, visual_extent  # noqa: E402

EMU_PER_INCH = 914400
#: a PDF's chrome bands and rules are measured on the page as pdftoppm draws it at this
#: density (0.24pt a pixel): the file's geometry ignores clipping paths and stroke widths
DRAWN_EXTENT_DPI = 300
#: how far past its geometry a band's or rule's ink is looked for: a stroke drawn about
#: its path reaches half its width beyond it
DRAWN_EXTENT_MARGIN_PT = 6.0
#: a pixel is the entry's ink when its RGB lies within this L1 distance of it (anti-aliased
#: edge pixels fall outside, so an extent reads up to one pixel, 0.24pt, short)
DRAWN_EXTENT_TOLERANCE = 30


def drawn_extent_emu(pdf: Path, page_index: int, box: tuple[int, int, int, int], ink_hex: str, cache: dict) -> tuple[int, int, int, int] | None:
    """The box (EMU) the reference's renderer paints `ink_hex` in, around a chrome entry's
    geometry `box` on page `page_index`: bain's navy title band is a rect from 12.7pt
    that a clipping path shows from 16.8pt (an 8px inset at 1600px wide), bcg's title
    rule a line path whose 2.25pt stroke sits half above it. None when the ink is not
    found there (a pattern, a picture) or the page cannot be drawn."""
    import subprocess
    import tempfile

    from PIL import Image
    key = (str(pdf), page_index)
    if key not in cache:
        with tempfile.TemporaryDirectory(prefix="extract-") as tmp:
            stem = Path(tmp) / "page"
            try:
                subprocess.run(["pdftoppm", "-png", "-r", str(DRAWN_EXTENT_DPI), "-f", str(page_index + 1), "-l", str(page_index + 1), "-singlefile",
                                str(pdf), str(stem)], capture_output=True, timeout=120, check=True)
                with Image.open(stem.with_suffix(".png")) as im:
                    cache[key] = im.convert("RGB")
            except (OSError, subprocess.SubprocessError):
                cache[key] = None
    im = cache[key]
    if im is None:
        return None
    k = DRAWN_EXTENT_DPI / EMU_PER_INCH
    margin = DRAWN_EXTENT_MARGIN_PT * EMU_PER_PT * k
    x0, y0 = max(0, int(box[0] * k - margin)), max(0, int(box[1] * k - margin))
    x1, y1 = min(im.width, int((box[0] + box[2]) * k + margin) + 1), min(im.height, int((box[1] + box[3]) * k + margin) + 1)
    target = tuple(int(ink_hex[i:i + 2], 16) for i in (0, 2, 4))
    px = im.load()
    # a band or rule fills its width: a row counts when the ink runs at least half the
    # entry's width along it (bcg's green title text, inside the margin above its green
    # rule, is not the rule); the extent across is read on those rows only
    need = max(1, int(0.5 * box[2] * k))
    rows: list[tuple[int, int, int]] = []
    for y in range(y0, y1):
        hits = [x for x in range(x0, x1)
                if abs(px[x, y][0] - target[0]) + abs(px[x, y][1] - target[1]) + abs(px[x, y][2] - target[2]) <= DRAWN_EXTENT_TOLERANCE]
        if len(hits) >= need:
            rows.append((y, hits[0], hits[-1]))
    if not rows:
        return None
    top, bottom = rows[0][0], rows[-1][0] + 1
    left, right = min(r[1] for r in rows), max(r[2] for r in rows) + 1
    return (round(left / k), round(top / k), round((right - left) / k), round((bottom - top) / k))

def ground_picture(guide: dict, reference: str, folder: Path) -> None:
    """The ground picture's own bytes (pdfimages, the file's image as stored, no content
    over it) for guide.ground.image_path: --chrome draw paints it as every page's
    background, so the build's pages stand on the house's ground and not on its flat
    surface colour. A picture, not a gradient fill: both renderers draw a bitmap alike,
    where an authored gradFill's midpoint lands 20 points apart (validate --emit, E38)."""
    import subprocess
    import tempfile
    ground = guide.get("ground")
    if not ground:
        return
    with tempfile.TemporaryDirectory(prefix="ground-") as tmp:
        try:
            subprocess.run(["pdfimages", "-png", "-f", str(ground["sample_page"]), "-l", str(ground["sample_page"]), reference, str(Path(tmp) / "im")],
                           capture_output=True, timeout=300, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            ground["image_basis"] = f"not cut: pdfimages failed ({error})"
            return
        from PIL import Image
        for path in sorted(Path(tmp).glob("im-*.png")):
            with Image.open(path) as im:
                if list(im.size) == ground["picture_px"] and im.mode != "L":
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / "ground.png"
                    im.convert("RGB").save(dest)
                    ground["image_path"] = str(dest.resolve())
                    ground["image_basis"] = f"the picture page {ground['sample_page']} paints under its content, as the file stores it (pdfimages)"
                    return
    ground["image_basis"] = "not cut: pdfimages found no picture of that size on the sample page"


def chrome_pictures(guide: dict, reference: str, folder: Path) -> None:
    """Every logo the PDF chrome miner found (a pasted picture, or a vector wordmark drawn
    as paths) gets the pixels the reference draws it with, cut from its sample page at 600
    dpi into `folder`, as the entry's image_path: an entry with no image drew nothing, so
    bcg's wordmark and its second top-rule strip were lost from every built page. An entry
    too small to cut (a sliver at the page edge) is left without one and says why."""
    import images
    for ch in guide.get("chrome") or []:
        if ch.get("kind") != "logo" or ch.get("image_path") or not ch.get("sample_page"):
            continue
        x, y, w, h = ch["box_in"]
        bbox = [round(x * 72, 2), round(y * 72, 2), round((x + w) * 72, 2), round((y + h) * 72, 2)]
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{ch['chrome_id']}.png"
        try:
            images.extract(reference, str(dest), None, ch["sample_page"], bbox, 600)
        except images.ImageRefused as error:
            ch["image_basis"] = f"not cut: {error}"
            continue
        ch["image_path"] = str(dest.resolve())
        ch["image_basis"] = (f"cut from page {ch['sample_page']} of the reference as pdftoppm draws it at 600 dpi (the mark's own pixels, "
                             "with the page's ground around them)")


# --- constants, with where each comes from -------------------------------------------
SIZE_LEVEL_RATIO = 1.10  # deckgen tokens.py:199; asserted: the smallest classic type step is 1.125
GAP_LEVEL_RATIO = 1.25  # deckgen tokens.py:200; asserted
MIN_LEVEL_OBSERVATIONS = 2  # deckgen tokens.py:202; one observation is an exception, not a level
#: two boxes this close touch: ooxml._pdf_box truncates a PDF box's origin and extent to whole
#: EMU separately, so abutting boxes read up to 2 EMU apart (nycha's space.xs came out 1 EMU)
ABUTTING_EMU = 2
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
MOTIF_RECURRENCE_FLOOR = RECURRENCE_FLOOR  # deckgen tokens.py:5754, defined once in ooxml.py (the PDF title slot reads it too)
MOTIF_FULL_SPAN = 0.9  # deckgen tokens.py:5761
MOTIF_RULE_ASPECT = 20  # deckgen tokens.py:5767
ALIGNMENT_EDGE_MIN_MEMBERS = 3
ALIGNMENT_EDGE_CAP = 53
EVIDENCE_CAP = 8
# Asserted, unmeasured: a block counts as sitting at the kicker (above) or subtitle and
# units-line (below) position when its gap to the title is within one title line pitch.
TITLE_COMPANION_GAP_PITCHES = 1.0
#: The closed vocabulary (TARGET_SPEC Appendix A) the model classifies titles and exhibits in.
VOCABULARY = json.loads((Path(__file__).resolve().parent.parent / "references" / "page_craft_vocabulary.json").read_text())
MIN_SECONDARY_INK_COUNT = 2  # DEVIATION from deckgen: ink_muted/rule need two votes (keybank bound #113D63 on one run)
# Product safety floor: the smallest size the specimen stays legible at on both render media,
# measured in deckgen docs/measurements/E45-decision.md (recorded 7.0 pt for display, body,
# annotation and chart, Calibri 700 being the binding face). Never generate below it.
PRODUCT_SAFETY_FLOOR_PT = {"body": 7.0, "annotation": 7.0, "display": 7.0, "chart": 7.0}
CORE_TYPE_ROLES = ("type.title", "type.kicker", "type.h1", "type.h2", "type.body", "type.emphasis", "type.caption",
                   "type.footnote", "type.source_line", "type.table_header", "type.table_cell", "type.axis_label", "type.data_label")
CORE_COLOR_ROLES = ("color.surface", "color.surface_alt", "color.ink", "color.ink_muted", "color.accent1", "color.accent2",
                    "color.accent3", "color.rule", "color.positive", "color.negative", "color.emphasis")
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


def slide_similarity(a: list[tuple], b: list[tuple], la: list[str] | None = None, lb: list[str] | None = None,
                     at_least: float | None = None, overlap=None) -> float:
    """Hungarian optimal assignment on pairwise IoU, scored over the larger set; role-wise when labelled.
    deckgen shapes.py:432. With `at_least`, a pair an upper bound proves to fall below it
    returns that bound instead of the exact score (leader clustering only compares).
    `overlap` scores a box pair (default iou; gallery.py passes its own, which scores two
    identical zero-area boxes 1, so x-ranges that only touch are still scored).

    Exact, and fast on PDF pages of a hundred boxes: only boxes whose x-ranges meet get a score,
    and the optimum is the sum of the optima of the connected components of the
    positive-IoU graph (a pair across components scores 0 and adds nothing), so one O(n^3)
    assignment becomes many small ones. On bain (205 pages) composition took 95 of the
    extraction's 118 s on its first 40 pages under cProfile before this."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    big = max(len(a), len(b))
    if at_least is not None and min(len(a), len(b)) / big < at_least:
        return min(len(a), len(b)) / big  # every matched pair scores at most 1
    order = sorted(range(len(b)), key=lambda j: b[j][0])
    starts = [b[j][0] for j in order]
    edges: dict[int, dict[int, float]] = {}
    for i, x in enumerate(a):
        for j in order[:bisect.bisect_right(starts, x[0] + x[2])]:
            y = b[j]
            if y[0] + y[2] < x[0] or (la is not None and lb is not None and la[i] != lb[j]):
                continue
            v = (overlap or iou)(x, y)
            if v > 0:
                edges.setdefault(i, {})[j] = v
    if at_least is not None:
        rows = sum(max(r.values()) for r in edges.values())
        cols: dict[int, float] = {}
        for r in edges.values():
            for j, v in r.items():
                cols[j] = max(cols.get(j, 0.0), v)
        bound = min(rows, sum(cols.values())) / big  # an assignment takes at most one entry per row and per column
        if bound < at_least:
            return bound
    parent = list(range(len(a) + len(b)))

    def find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, r in edges.items():
        for j in r:
            parent[find(i)] = find(len(a) + j)
    comps: dict[int, tuple[list[int], list[int]]] = {}
    for i in edges:
        comps.setdefault(find(i), ([], []))[0].append(i)
    for j in {j for r in edges.values() for j in r}:
        comps[find(len(a) + j)][1].append(j)
    total = sum(hungarian_max([[edges[i].get(j, 0.0) for j in cs] for i in rs]) for rs, cs in comps.values())
    return total / big


def leader_clusters(groups: list[list[tuple]], labels: list[list[str]] | None = None, threshold: float = ARCHETYPE_IOU_THRESHOLD) -> list[tuple[int, list[int]]]:
    clusters: list[tuple[int, list[int]]] = []
    for index, group in enumerate(groups):
        for anchor, members in clusters:
            if slide_similarity(groups[anchor], group, None if labels is None else labels[anchor], None if labels is None else labels[index],
                                at_least=threshold) >= threshold:
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


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[0] + inner[2] <= outer[0] + outer[2] and inner[1] + inner[3] <= outer[1] + outer[3]


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
    def __init__(self, path: str, max_pages: int | None = None, pages: tuple[int, int] | None = None,
                 include_generated: bool = False) -> None:
        self.path = path
        self._clock = time.monotonic()
        self.timings: dict[str, float] = {}
        self.slides: list[SlidePrint] = fingerprint_deck(path, max_pages)
        self._stage("read", f"{len(self.slides)} slides")
        self.notes: list[str] = []
        generated = [s.index + 1 for s in self.slides if s.generated]
        self.generated_skipped = 0 if include_generated else len(generated)
        if generated and include_generated:
            self.notes.append(f"{len(generated)} generated slides (pptx-skill origin tag) counted as evidence by --include-generated: {generated}")
        elif generated:
            self.slides = [s for s in self.slides if not s.generated]
            self.notes.append(f"{len(generated)} generated slides (pptx-skill origin tag) skipped, they are this skill's output, not the reference: {generated}; "
                              "--include-generated counts them")
            if not self.slides:
                raise SystemExit(f"{path}: every slide is generated ({len(generated)}); pass --include-generated to read them anyway")
        if not self.slides:
            raise SystemExit(f"{path}: no slides")
        self.is_pdf = self.slides[0].source == "pdf"
        self.unresolved: list[dict] = []
        self.guide: dict = {}
        self.triage: dict | None = None
        self.raster = False
        if self.is_pdf:
            self.triage = pdf_triage(path, max_pages)
            unread = sum(s.unread_glyphs for s in self.slides)
            if unread:
                self.notes.append(f"{unread} glyphs are set at an angle that is neither upright nor a quarter turn: no type size can be read along "
                                  "them, so they are left out of the runs")
            slot = self.triage.get("title_slot") or {}
            if slot.get("pages"):
                self.notes.append(f"title evidence: a block sits at the recurring title position on {slot.get('marked', 0)} of {slot.get('pages', 0)} "
                                  f"vector pages (at least {slot.get('needed', 0)} needed); those blocks are the title runs"
                                  if slot.get("marked") else
                                  f"title evidence: no position holds a top block on {slot.get('needed', 0)} of {slot.get('pages', 0)} vector pages, "
                                  "so no block is a title and type.title stays open")
            if pages is not None:
                lo, hi = pages
                self.slides = [s for s in self.slides if lo <= s.index + 1 <= hi]
                self.notes.append(f"pages restricted to {lo}-{hi} by --pages")
            dropped = [s.index + 1 for s in self.slides if not is_type_evidence(s)]
            evidence = [s for s in self.slides if is_type_evidence(s)]
            if self.triage["deck_class"] == "raster" and pages is None:
                # the text layer is a wrapper or OCR: nothing on these pages is type evidence
                self.raster = True
                size_in = self.triage.get("slide_size_in")
                if size_in:
                    for s in self.slides:  # the slide is the image, not the letter page around it, at its unscaled size
                        s.width, s.height = int(size_in[0] * EMU_PER_INCH), int(size_in[1] * EMU_PER_INCH)
            elif dropped:
                self.slides = evidence or self.slides
                self.notes.append(f"pages excluded from the evidence by triage ({self.triage['counts']}): {dropped[:40]}{' ...' if len(dropped) > 40 else ''}; "
                                  f"evidence pages: {self.triage['evidence_pages'][:12]}{' ...' if len(self.triage['evidence_pages']) > 12 else ''}")
        self.w = self.slides[0].width
        self.h = self.slides[0].height
        self.page_area = self.w * self.h
        # chrome keys: (kind, quantised box) of layout/master shapes, plus slide-layer shapes
        # repeated at one position on at least half the slides
        self.chrome_keys: set[tuple] = set()
        counts: Counter = Counter()
        for s in self.slides:
            for c in s.chrome:
                if c.box:
                    self.chrome_keys.add((c.kind, quant(c.box)))
            seen = set()
            for sh in s.shapes + vector_shapes(s):
                # Only furniture can be chrome: rules, bands, pictures and the date/footer/number
                # placeholders. A title repeated at one position is composition, not chrome. A PDF
                # has no placeholders, so a short text line repeated at one position (a footer
                # label, a page number) counts there.
                furniture = sh.ph_type in CHROME_TYPES or (sh.text_chars == 0 and sh.kind in ("line", "shape", "picture"))
                # a rotated line (a copyright up the page edge) is furniture wherever it sits
                # and however long; recurrence at one position below still decides it
                # (no length bound: bcg's 61-character file-name footer recurs on every page and is furniture;
                # recurrence at one position with the same words decides it, below)
                pdf_label = self.is_pdf and sh.text is not None and (bool(sh.rotation) or sh.box[1] > 0.8 * self.h)  # type: ignore[index]
                if sh.box and (furniture or pdf_label):
                    if pdf_label:
                        # a footer line often carries the page number: key on the words and the
                        # line's left edge and row, not on its width
                        label = re.sub(r"\s*\d+\s*$", "", sh.text or "").strip()
                        k = (sh.kind, (quant(sh.box)[0], quant(sh.box)[1]), label or "<page number>")
                    else:
                        k = (sh.kind, quant(sh.box), None)
                    if k not in seen:
                        seen.add(k)
                        counts[k] += 1
        self.recurring_slide_chrome = {(k[0], k[1]) for k, n in counts.items() if n >= max(2, MOTIF_RECURRENCE_FLOOR * len(self.slides))}
        self.pdf_label_keys = {k[1]: k[2] for k, n in counts.items() if k[2] is not None and n >= max(2, MOTIF_RECURRENCE_FLOOR * len(self.slides))}
        self.chrome_keys |= self.recurring_slide_chrome
        self.color_roles: dict[str, str] = {}  # hex -> role

    # ---- content boxes ----
    def is_chrome(self, sh: Shape) -> bool:
        if not sh.box:
            return False
        if (sh.kind, quant(sh.box)) in self.chrome_keys:
            return True
        if self.is_pdf and sh.text is not None:
            q = quant(sh.box)
            return (q[0], q[1]) in getattr(self, "pdf_label_keys", {})
        return False

    def _inset(self, box: tuple[int, int, int, int], side: str) -> int:
        x, y, w, h = box
        return {"left": x, "right": self.w - x - w, "top": y, "bottom": self.h - y - h}[side]

    def _bleeds(self, sh: Shape, side: str) -> bool:
        """A textless band, picture or rule that reaches the page edge on `side` (within
        half a position diameter, 3pt) or runs past it."""
        return not sh.text_chars and sh.kind in ("shape", "picture", "line") and self._inset(sh.box, side) <= POSITION_DIAMETER_EMU // 2  # type: ignore[arg-type]

    def content_boxes(self, s: SlidePrint) -> list[Shape]:
        """The slide's content shapes, each with the page area it covers as its box (a
        rotated shape's declared box is its pre-rotation box, which can lie off the page)."""
        return [replace(sh, box=visual_extent(sh.box, sh.rotation)) if sh.rotation else sh
                for sh in s.shapes if sh.box and sh.box[2] > 0 and sh.box[3] > 0 and not self.is_chrome(sh)]

    def _stage(self, name: str, detail: str = "") -> None:
        """One progress line per stage on stderr, so a long reference never runs silent."""
        now = time.monotonic()
        self.timings[name] = round(now - self._clock, 2)
        self._clock = now
        print(f"extract_style: {name} {self.timings[name]:.1f}s{(' (' + detail + ')') if detail else ''}", file=sys.stderr, flush=True)

    def open(self, path: str, reason: str, constraints: dict | None = None, candidates: list | None = None) -> None:
        if any(u["path"] == path for u in self.unresolved):
            return  # the first reason given for an address is the specific one
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

        # title: the level holding most of the title runs (a title placeholder in a pptx, the
        # recurring title slot in a PDF, ooxml._pdf_title_slot). Size alone is no evidence:
        # the largest level was a 44pt numeral on one reference whose titles are 25pt. With
        # no title run, or when no level holds RECURRENCE_FLOOR of them, the role stays open
        # with the levels the title runs did reach as candidates.
        title_votes = [sum(1 for m in lm if m.ph_class == "title") for lm in level_members]
        if levels:
            top = max(range(len(levels)), key=lambda i: (title_votes[i], levels[i].representative))
            total = sum(title_votes)
            if total and title_votes[top] >= RECURRENCE_FLOOR * total:
                bind("type.title", top, "assigned" if not self.is_pdf else "inferred")
            else:
                held = sorted(((levels[i].representative, title_votes[i]) for i in range(len(levels)) if title_votes[i]), key=lambda t: -t[1])
                self.open("/typography/roles/type.title",
                          ("no title placeholder and no recurring title position: the largest size is not evidence of the title" if not total else
                           f"the title runs split across levels, none holding {RECURRENCE_FLOOR:.0%} of them"),
                          {"title_run_levels_pt_votes": held, "ladder_sizes_pt": sorted(lv.representative for lv in levels)},
                          [{"size_pt": s, "title_runs": n} for s, n in held])
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
            # a level under the product safety floor is not a role (4.5pt with two votes bound
            # type.footnote on one reference and made every page with a source line unfittable)
            below = [i for i in range(len(levels)) if i not in assigned and i < body_idx and levels[i].representative >= PRODUCT_SAFETY_FLOOR_PT["annotation"]]
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
                # the glyph's own ink, where it has one other than its text's (bcg's green
                # squares beside black text): a role the emitter writes as a:buClr
                inks = [r.bullet_color for r in lvl_runs if r.bullet_color and r.bullet_color != r.color]
                ink = modal(inks) if len(inks) * 2 >= len(lvl_runs) else None
                bullets[lvl] = {"glyph": modal([r.bullet_glyph for r in lvl_runs if r.bullet_glyph]),
                                "font": modal([r.bullet_font for r in lvl_runs if r.bullet_font]), "runs": len(lvl_runs),
                                "ink_hex": ink, "ink_role": None,
                                "mar_l_emu": modal([r.mar_l_emu for r in lvl_runs if r.mar_l_emu is not None]),
                                "hanging_emu": modal([-r.indent_emu for r in lvl_runs if r.indent_emu is not None])}
        self._bullets = bullets
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
            for sh in s.chrome:
                # the rules the layout draws on every page are the house's rules; without this
                # vote five red highlight outlines on the slide layer won colour.rule on netflix
                if sh.line and sh.line_w_emu and 0 < sh.line_w_emu <= RULE_LINE_MAX_WIDTH_EMU and (sh.kind == "line" or (sh.box and min(sh.box[2], sh.box[3]) <= RULE_LINE_MAX_WIDTH_EMU)):
                    votes_rule.setdefault(sh.line, Votes()).add(f"{sid}#{sh.ref}", True)
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
                          {"candidates": [h for h in inks_sorted if h != ink][:5], "deviation": "one run is not enough; a secondary ink needs two"})
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
            inks_sorted = sorted(votes_ink, key=lambda h: (-votes_ink[h].count, -votes_ink[h].master, h))
            for role, why in (("color.ink", "no ground to measure contrast against"), ("color.ink_muted", "no ground"), ("color.rule", "no ground")):
                self.open(f"/color/roles/{role}", f"{why}: pick from the run inks and strokes", {"candidates": [{"hex": h, "count": votes_ink[h].count} for h in inks_sorted[:6]]})
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
        # the house's "look here" colour (the red box round a figure, the circle, the
        # highlight bar) is a reading of what the house marks and how, which no hue band
        # decides: it is always the model's to answer from the renders and the digest, and
        # it is not color.negative, which colours a bad value
        self.open("/color/roles/color.emphasis", "the colour the house marks emphasis with (outline boxes, circles, a highlighted bar, an "
                  "emphasis rule) is read off the renders, never inferred from a hue band; it is not color.negative, which colours a bad value",
                  {"saturated_inks_and_accents": sorted((h for h in pool if sat[h][1] >= SEMANTIC_MIN_SATURATION), key=lambda h: -pool[h])[:5]})
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

    def role_of(self, hexv: str | None, use: str | None = None) -> str | None:
        """The role holding this hex. One hex can hold several roles (white is the surface and
        the inverse ink on most decks; the rule and accent1 share the navy on netflix), so `use`
        says which family the caller means: "ink" prefers ink roles, "fill" prefers surface
        and accent roles."""
        if hexv is None:
            return None
        roles = self.guide.get("color", {}).get("roles", {})
        holders = [name for name, spec in roles.items() if spec.get("hex") == hexv]
        if use == "ink":
            pref = [n for n in holders if n.startswith("color.ink")]
        elif use == "fill":
            pref = [n for n in holders if n.startswith(("color.surface", "color.accent"))]
        else:
            pref = []
        if pref:
            return pref[0]
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
            content = self.content_boxes(s)
            boxes = [(sh.ref, sh.box) for sh in content]
            if not boxes:
                continue
            sid = s.part or f"page{s.index + 1}"
            by_y = sorted(boxes, key=lambda b: (b[1][1], b[0]))
            for (ra, a), (_, b) in zip(by_y, by_y[1:]):
                gap = b[1] - (a[1] + a[3])
                if ABUTTING_EMU < gap < 2 * EMU_PER_INCH:
                    pool.setdefault(float(gap), Votes()).add(f"{sid}#{ra}", False)
            by_x = sorted(boxes, key=lambda b: (b[1][0], b[0]))
            for i, (ra, a) in enumerate(by_x):
                for _, b in by_x[i + 1:]:
                    overlap = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                    if overlap < max(1, min(a[3], b[3])) / 2:
                        continue
                    gap = b[0] - (a[0] + a[2])
                    if ABUTTING_EMU < gap < 2 * EMU_PER_INCH:
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
            # a margin is where the content stops short of the page edge: a band, picture or
            # rule that runs to an edge (a full-page ground, a half-page photo) bleeds and says
            # nothing about that side's margin, so it is not a vote of 0 for it
            for side, sink in (("left", lefts), ("right", rights), ("top", tops), ("bottom", bottoms)):
                inset = [self._inset(sh.box, side) for sh in content if not self._bleeds(sh, side)]  # type: ignore[arg-type]
                if inset:
                    sink.append(min(inset))
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

    # ---- titles ----
    def titles(self) -> None:
        """Every page title, found by position (the title placeholder in a pptx, the
        recurring title slot in a PDF; never by size): its text, characters, words and
        lines, the length distribution, and the text block that sits directly above or
        below it (the kicker and the subtitle or units-line positions). Register is a
        reading of the words, so it stays open for the model with every title listed."""
        records: list[dict] = []
        unmeasured: list[dict] = []
        for s in self.slides:
            heads = sorted((sh for sh in s.shapes if sh.ph_type in TITLE_TYPES and sh.box and sh.paragraphs and sh.text_chars),
                           key=lambda sh: (sh.box[1], sh.box[0]))  # type: ignore[index]
            if not heads:
                continue
            sh = heads[0]  # one title per page: the topmost title shape
            text = paragraphs_words(sh.paragraphs)
            if not text:
                continue
            sizes = [r["size_pt"] for p in sh.paragraphs for r in p["runs"] if r.get("size_pt") and not r.get("br")]
            rec = {"slide": s.index + 1, "text": text, "chars": len(text), "words": len(text.split()), "placeholder": sh.ph_type,
                   "size_pt": modal([round(v * 2) / 2 for v in sizes]), "ref": sh.ref}
            if sh.drawn_lines is not None:
                rec["lines"], rec["lines_basis"] = sh.drawn_lines, "drawn: the glyph lines the PDF page sets"
            else:
                from fingerprint import wrap_shape
                got = wrap_shape(s, sh)
                if "why" in got:
                    rec["lines"], rec["lines_basis"] = None, f"not measured: {got['why']}"
                    unmeasured.append({"slide": s.index + 1, "why": got["why"]})
                else:
                    rec["lines"], rec["lines_basis"] = len(got["lines"]), "measured: the solver's ruler at the placeholder's inner width"
            pitch = (rec["size_pt"] or 0) * 1.2 * EMU_PER_PT
            rec["above"] = self._title_neighbour(s, sh, pitch, above=True)
            rec["below"] = self._title_neighbour(s, sh, pitch, above=False)
            records.append(rec)
        # a cover title (ctrTitle) names the deck, not a page: listed, never part of the page distribution
        pages = [r for r in records if r["placeholder"] != "ctrTitle"]

        def dist(values: list) -> dict:
            if not values:
                return {"n": 0, "median": None, "p90": None, "max": None}
            return {"n": len(values), "median": round(percentile(values, 0.5), 2), "p90": round(percentile(values, 0.9), 2), "max": max(values)}

        measured_lines = [r["lines"] for r in pages if r["lines"] is not None]
        self.guide["titles"] = {
            "records": records,
            "distribution": {"chars": dist([r["chars"] for r in pages]), "words": dist([r["words"] for r in pages]),
                             "lines": {**dist(measured_lines), "unmeasured": len(pages) - len(measured_lines)}},
            "positions": {"pages_with_title": len(pages), "above": sum(1 for r in pages if r["above"]), "below": sum(1 for r in pages if r["below"]),
                          "gap_rule": f"a text block within {TITLE_COMPANION_GAP_PITCHES:g} title line pitch (1.2 x the title size) of the title's top or bottom edge, overlapping it across the page"},
            "register": None,
            "provenance": observed([f"slide{r['slide']}#{r['ref']}" for r in records], len(records), False, 1.0),
        }
        if unmeasured:
            self.notes.append(f"title lines not measured on {len(unmeasured)} pages: {unmeasured[:4]}")
        if not pages:
            self.notes.append("no page title found by position (no title placeholder, no recurring title slot): /titles has no evidence and register cannot be read")
            return
        companions = {str(r["slide"]): {k: r[k]["text"] for k in ("above", "below") if r[k]} for r in pages if r["above"] or r["below"]}
        self.open("/titles/register", "register is a reading of each title's words (topic phrase, claim sentence, question), and what the "
                  "blocks above and below the title are: judgment, so the model classifies every title listed here",
                  {"titles": {str(r["slide"]): r["text"] for r in pages}, "companions": companions,
                   "shape": {"per_title": {"<slide>": "|".join(VOCABULARY["title_register"])},
                             "companions": {"<slide>": {"above": "|".join(VOCABULARY["title_companion_above"]), "below": "|".join(VOCABULARY["title_companion_below"])}},
                             "claims_elsewhere": {"<slide of a topic title>": "where the page states its claim, or null when it states none"},
                             "why": "..."}})

    def variety(self, archetype_of: dict[int, str]) -> None:
        """The house's variety over its content pages (plan.py holds the measure): each page's
        archetype in page order with library.py's triage proposal, which pages are content
        (the proposal, until /variety/content_pages answers it), and the measure. Exhibit types
        are not read here: complete_guide.py measures them once /exhibit_habits is answered."""
        from library import facts_of, propose  # library imports gallery, which imports this module
        from ooxml import Package
        facts = facts_of(self.slides, None if self.is_pdf else Package(self.path))
        triage = {t["page"]: t for t in propose(list(facts.values()))}
        pages = [{"slide": s.index + 1, "composition": archetype_of[i], "triage": triage[s.index + 1]["proposal"], "why": triage[s.index + 1]["evidence"]}
                 for i, s in enumerate(self.slides)]
        content = [p["slide"] for p in pages if p["triage"] == plan.CONTENT]
        self.guide["variety"] = {
            "pages": pages,
            "content_pages": {"pages": content, "basis": "proposal: library.py's triage definitions (unmeasured), not confirmed by looking"},
            "method": plan.METHOD, "weaknesses": list(plan.WEAKNESSES),
            "measure": plan.measure_deck(Path(self.path).name, plan.content_segments({"pages": pages, "content_pages": {"pages": content}}, None)),
        }
        self.open("/variety/content_pages", "which pages are content is a reading: look at the renders and list the content pages (the triage "
                  "proposal is in the candidates); the house's variety is measured over them, and stays on the proposal until answered",
                  {"shape": "[<slide>, ...]: the content pages, in any order, each a page listed here", "pages": [p["slide"] for p in pages if p["triage"] != "hidden"]},
                  [{"slide": p["slide"], "proposal": p["triage"], "why": p["why"]} for p in pages])

    def _title_neighbour(self, s: SlidePrint, title: Shape, pitch: float, above: bool) -> dict | None:
        """The nearest content text block directly above (or below) the title: its gap to
        the title edge within TITLE_COMPANION_GAP_PITCHES title pitches, overlapping the
        title across the page. Chrome and other title shapes are not candidates."""
        tx, ty, tw, th = title.box  # type: ignore[misc]
        best: tuple[float, Shape] | None = None
        for sh in self.content_boxes(s):
            if sh is title or sh.ph_type in TITLE_TYPES or not sh.text_chars or not sh.paragraphs or sh.ref == title.ref:
                continue
            x, y, w, h = sh.box  # type: ignore[misc]
            if min(x + w, tx + tw) <= max(x, tx):
                continue
            gap = (ty - (y + h)) if above else (y - (ty + th))
            if gap < -0.5 * pitch or gap > TITLE_COMPANION_GAP_PITCHES * pitch:
                continue
            if best is None or gap < best[0]:
                best = (gap, sh)
        if best is None:
            return None
        sh = best[1]
        words = paragraphs_words(sh.paragraphs)
        sizes = [r["size_pt"] for p in sh.paragraphs for r in p["runs"] if r.get("size_pt") and not r.get("br")]
        return {"text": words[:120], "size_pt": modal([round(v * 2) / 2 for v in sizes]), "paragraphs": len(sh.paragraphs),
                "gap_pt": round(best[0] / EMU_PER_PT, 1), "ref": sh.ref}

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
        self.variety({m: f"arch-{fi + 1}" for fi, (_, members) in enumerate(fams) for m in members})
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

        # the text container the house draws by hand: a text box (txBox="1") or a plain shape.
        # The judge counts the two apart, and a deck of text boxes on a house of shapes is a tell.
        containers: Counter = Counter()
        for s in self.slides:
            for sh in s.shapes:
                if sh.layer == "slide" and not sh.is_placeholder and sh.text_chars and sh.kind in ("text_box", "text_shape"):
                    containers[sh.kind] += 1
        self.guide["register_stats"] = {
            "text_container": (containers.most_common(1)[0][0] if containers else "text_shape"),
            "text_container_counts": dict(containers),
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
    _page_renders: ClassVar[dict] = {}  # one render per (reference, page) for drawn_extent_emu, shared by every run in the process

    def chrome_and_motifs(self) -> None:
        chrome = []
        seen: set = set()
        samples: dict[tuple, Shape] = {}
        first_page: dict[tuple, int] = {}  # the page each entry was first seen on: a PDF's drawn extent is read there
        presence: Counter = Counter()
        text_of: dict[tuple, str] = {}
        # each entry's rank in its page's painting sequence, per page it is on: the drawn
        # chrome must paint in the reference's order (a full-page band drawn last buries
        # every other entry)
        paint_ranks: dict[tuple, list[float]] = {}
        content_on: Counter = Counter()  # key -> pages on which a content box lies inside it
        for s in self.slides:
            on_page: dict[tuple, int] = {}
            for c in s.chrome:
                if c.box:
                    k = (c.kind, quant(c.box), c.layer)
                    samples.setdefault(k, c)
                    presence[k] += 1
                    on_page.setdefault(k, c.paint_order)
            for sh in s.shapes + vector_shapes(s):
                if not sh.box or not self.is_chrome(sh):
                    continue
                if self.is_pdf and sh.text is not None:
                    q = quant(sh.box)
                    label = getattr(self, "pdf_label_keys", {}).get((q[0], q[1]))
                    k = (sh.kind, (q[0], q[1], 0, 0), "slide")
                    samples.setdefault(k, sh)
                    presence[k] += 1
                    on_page.setdefault(k, sh.paint_order)
                    if k not in text_of:
                        has_number = bool(re.search(r"\d+\s*$", sh.text or ""))
                        text_of[k] = (label if label != "<page number>" else "") + (" <page number>" if has_number or label == "<page number>" else "")
                    continue
                k = (sh.kind, quant(sh.box), "slide")
                samples.setdefault(k, sh)
                first_page.setdefault(k, s.index)
                presence[k] += 1
                on_page.setdefault(k, sh.paint_order)
                if sh.text_chars and k not in text_of:
                    text_of[k] = " ".join(r.text_sample for r in s.runs if r.ref.startswith(sh.ref + "/"))[:60]
            ordered = sorted(on_page, key=lambda key: on_page[key])
            for rank, k in enumerate(ordered):
                paint_ranks.setdefault(k, []).append(rank / max(1, len(ordered) - 1))
            content = self.content_boxes(s)
            for k in on_page:
                box = samples[k].box
                if box and any(_inside(c.box, box) for c in content):  # type: ignore[arg-type]
                    content_on[k] += 1
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
            elif sh.text is not None and (text_of.get(k, "") or "").strip() in ("<page number>", ""):
                kind = "page_number"
            elif sh.text_chars and sh.text is not None:
                kind = "label"
            elif sh.kind == "line" or (h * MOTIF_RULE_ASPECT <= w) or (w * MOTIF_RULE_ASPECT <= h):
                kind = "rule"
            elif sh.text_chars:
                kind = "label"
            elif sh.fill:
                kind = "band"
            vx, vy, vw, vh = visual_extent(sh.box, sh.rotation)  # type: ignore[arg-type]
            span = "full" if (vw >= MOTIF_FULL_SPAN * self.w or vh >= MOTIF_FULL_SPAN * self.h) else "partial"
            dist = {"slide_top": vy / self.h, "slide_bottom": (self.h - vy - vh) / self.h, "slide_left": vx / self.w, "slide_right": (self.w - vx - vw) / self.w}
            if vw >= MOTIF_FULL_SPAN * self.w:  # a full-width mark anchors to a horizontal edge
                dist = {k: v for k, v in dist.items() if k in ("slide_top", "slide_bottom")}
            elif vh >= MOTIF_FULL_SPAN * self.h:
                dist = {k: v for k, v in dist.items() if k in ("slide_left", "slide_right")}
            anchor = min(dist, key=dist.get)
            if dist[anchor] > 0.15:
                anchor = "center"
            box_basis = None
            ink = sh.fill if kind == "band" else sh.line if kind == "rule" else None
            if self.is_pdf and ink and k in first_page and ink != self.slides[first_page[k]].background:
                drawn = drawn_extent_emu(self.path, first_page[k], (x, y, w, h), ink, self._page_renders)
                if drawn is not None and drawn != (x, y, w, h):
                    x, y, w, h = drawn
                    box_basis = ("drawn extent on the reference's own page render (pdftoppm, the renderer that reads the file): "
                                 f"its geometry in the PDF was {[round(v / EMU_PER_INCH, 3) for v in sh.box]} in, moved by a clipping path "  # type: ignore[union-attr]
                                 "or a stroke's width")
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
                "paint_rank": statistics.median(paint_ranks.get(k) or [0.0]),
                "carries_content_on": content_on[k],
            }
            if box_basis:
                entry["box_basis"] = box_basis
            if k in first_page:
                entry["sample_page"] = first_page[k] + 1
            if sh.rotation:
                entry["rotation_deg"] = round(sh.rotation / 60000, 2)  # clockwise about the centre of box_in, the pre-rotation box
            if self.is_pdf and sh.text is not None and sh.line_style:
                entry["text_style"] = dict(sh.line_style)
            if sh.layer != "slide" and sh.text_chars:
                runs = [r for s in self.slides[:1] for r in s.chrome_runs if r.ref.startswith(sh.ref)]
                if runs:
                    entry["text_style"] = {"family": modal([r.family for r in runs]), "size_pt": modal([r.size_pt for r in runs]),
                                           "ink_hex": modal([r.color for r in runs]), "bold": modal([r.bold for r in runs])}
            chrome.append(entry)
        for order, i in enumerate(sorted(range(len(chrome)), key=lambda i: (chrome[i]["paint_rank"], i))):
            chrome[i]["paint_order"] = order
        for entry in chrome:
            del entry["paint_rank"]
        self.guide["chrome"] = chrome
        # the picture a PDF paints under every page's content (mckinsey's navy-to-blue
        # ground is a 1920 x 1080 image over its flat surface): measured here, cut in main()
        grounds = Counter(s.pdf_ground for s in self.slides if self.is_pdf and s.pdf_ground)
        if grounds:
            size, n = grounds.most_common(1)[0]
            if n >= MOTIF_RECURRENCE_FLOOR * len(self.slides):
                self.guide["ground"] = {"picture_px": list(size), "pages": n, "of_pages": len(self.slides),
                                        "sample_page": next(s.index + 1 for s in self.slides if s.pdf_ground == size),
                                        "image_path": None,
                                        "provenance": observed([f"page{s.index + 1}#ground" for s in self.slides if s.pdf_ground == size][:EVIDENCE_CAP], n, False,
                                                               n / len(self.slides), "inferred")}
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
            "header_fill_role": self.role_of(header_fill, "fill"), "header_fill_hex": header_fill,
            "header_ink_role": self.role_of(modal([r.color for r in header_runs]), "ink") if header_runs else None,
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
    def corner_radii(self) -> None:
        """Votes the drawn roundRect radius over every slide-layer shape (deckgen
        style/tokens.py: shape language is measured usage, so layout and master shapes,
        which walk whether or not a slide shows them, do not vote). Opened only when no
        slide-layer shape declares a preset, the one case the file cannot answer."""
        preset = [(s, sh) for s in self.slides for sh in s.shapes if sh.prst]
        if not preset:
            self.open("/shape_language/corner_radii", "no slide-layer shape declares a preset geometry (a PDF never does), so the file says nothing about "
                      "corners; read them off the renders, in the shape the file would have given",
                      {"value_shape": {"modal_radius_emu": "int, 0 for square corners", "rounded_share": "share of boxes with rounded corners, 0..1",
                                       "why": "the pages and boxes you read it from"}})
            return
        rounded = [(s, sh) for s, sh in preset if sh.prst == "roundRect"]
        pool: dict[float, Votes] = {}
        unreadable = 0
        for s, sh in rounded:
            if sh.corner_radius_emu is None:
                unreadable += 1
                continue
            pool.setdefault(float(sh.corner_radius_emu), Votes()).add(f"{s.part}#{sh.ref}", False)
        modal = winner(pool) if pool else None
        votes = sum(v.count for v in pool.values())
        self.guide["shape_language"]["corner_radii"] = {
            "modal_radius_emu": int(modal) if modal is not None else None,
            "modal_radius_pt": round(modal / EMU_PER_PT, 2) if modal is not None else None,
            "rounded_share": round(len(rounded) / len(preset), 4),
            "rounded_shapes": len(rounded),
            "preset_shapes": len(preset),
            "unreadable_adj": unreadable,
            "radii_emu": [(int(r), pool[r].count) for r in sorted(pool, key=lambda k: (-pool[k].count, k))[:6]],
            "provenance": observed(pool[modal].evidence if modal is not None else [], votes if modal is not None else len(preset), False,
                                   pool[modal].count / votes if modal is not None else 1.0),
        }

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
        self.corner_radii()
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
        pages_at: dict[str, dict[float, set[int]]] = defaultdict(lambda: defaultdict(set))  # family -> size -> pages that set it
        # text turned off the horizontal (a copyright up the page edge, overprinted glyph by
        # glyph on bcg) is furniture in the margin, not a size the house sets content in
        turned_refs = {(s.index, sh.ref) for s in self.slides for sh in s.shapes if sh.rotation and sh.text_chars}
        page_of = {id(r): s.index for s in self.slides for r in s.runs}
        turned = 0
        for r in self._runs:
            page = page_of.get(id(r), -1)
            if (page, r.ref.split("/", 1)[0]) in turned_refs:
                turned += 1
                continue
            if r.ph_class == "title":
                fam = "display"
            elif r.row_class is not None:
                fam = "body"
            elif not role_sizes:
                continue
            else:
                nearest = min(role_sizes, key=lambda role: abs(math.log(r.size_pt / role_sizes[role])))
                fam = fam_of_role.get(nearest, "body")
            samples[fam].append(r.size_pt)
            pages_at[fam][r.size_pt].add(page)
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
            # the fence trims a stray size, never one the reference sets again and again: a
            # size on MIN_LEVEL_OBSERVATIONS pages or more is the house's own (mckinsey's 8pt
            # source lines are 10 of 44 annotation runs on 9 pages, under a 9pt fence)
            kept = [v for v in vals if v >= fence or len(pages_at[fam][v]) >= MIN_LEVEL_OBSERVATIONS]
            floors[fam] = {"roles": list(roles), "floor_pt": min(kept), "trimmed_outlier_count": len(vals) - len(kept), "sample_size": len(vals),
                           "absolute_floor_pt": PRODUCT_SAFETY_FLOOR_PT[fam],
                           "provenance": observed([], len(vals), False, 1.0)}
        self.guide["floors"] = floors
        self.guide["floors_note"] = ("absolute_floor_pt: product safety floor (7.0pt, measured on two screen media); never generate below max(floor_pt, absolute_floor_pt). "
                                     f"floor_pt is the smallest size the reference sets that is inside the Tukey lower fence or recurs on {MIN_LEVEL_OBSERVATIONS} or more pages; "
                                     f"{turned} runs in turned text (rotated shapes or blocks) are not samples")
        # an inferred role below its own family's measured floor cannot be emitted (the solver
        # refuses it), so it is unbound here and reopened with the floor as its constraint
        for role, fam in (("type.caption", "annotation"), ("type.footnote", "annotation"), ("type.source_line", "annotation"), ("type.kicker", "annotation")):
            spec = self._roles.get(role)
            if not spec or spec.get("provenance", {}).get("role_provenance") != "inferred":
                continue
            f = floors.get(fam) or {}
            floor = max(float(f.get("floor_pt") or 0.0), float(f.get("absolute_floor_pt") or 0.0))
            if spec.get("size_pt") is not None and float(spec["size_pt"]) < floor:
                del self._roles[role]
                self.open(f"/typography/roles/{role}", f"the inferred {spec['size_pt']}pt level is below the {fam} floor {floor}pt",
                          {"min_size_pt": floor, "ladder_sizes_pt": [lv.get("size_pt") for lv in self.guide.get("typography", {}).get("levels", [])]})

    # ---- assembly ----
    def run(self) -> dict:
        hidden = [s.index + 1 for s in self.slides if getattr(s, "hidden", False)]
        if hidden:
            self.notes.append(f"hidden slides counted as evidence (delete them from a copy with pptx_tools.py delete to exclude): {hidden}")
        if self.raster:
            return self.run_raster()
        for stage in (self.typography, self.color, self.spacing, self.composition, self.chrome_and_motifs, self.titles, self.tables, self.charts,
                      self.shapes_and_imagery):
            stage()
            self._stage(stage.__name__)
        # bullet indents bind to the nearest spacing step (the solver and emitter read roles, never EMU)
        steps = self.guide.get("spacing", {}).get("steps", {})
        for lvl, b in self._bullets.items():
            for src, dst in (("mar_l_emu", "indent_role"), ("hanging_emu", "hanging_indent_role")):
                v = b.get(src)
                if v and steps:
                    b[dst] = min(steps, key=lambda n: abs(steps[n]["emu"] - v))
                elif b.get("mar_l_emu") and steps and dst == "hanging_indent_role":
                    b[dst] = b.get("indent_role")
        # bind role inks and chrome colours to roles (after colour roles exist)
        for role, spec in self._roles.items():
            spec["ink_role"] = self.role_of(spec.get("ink"), "ink") if spec.get("ink") else None
        for b in self._bullets.values():
            b["ink_role"] = self.role_of(b.get("ink_hex")) if b.get("ink_hex") else None
        for path, reason in (("/description", "written by the model from the renders and this draft: summary, typography, color, layout, tables, imagery, motifs, never_does, tone"),
                             ("/derivation_rules", "how to extend the palette and the type ladder to roles the reference never showed"),
                             ("/continuation", "header repeat, cont'd mark and takeaway policy when a slide splits")):
            self.open(path, reason)
        self.open("/exhibit_habits", "how the house builds its exhibits is read by looking at them: run the digest, look at every crop, copy the "
                  "stub to digest.json beside it, complete every page of the copy in the vocabulary it names, and answer with complete_guide.py --digest <dir>",
                  {"command": "python3 scripts/gallery.py digest <reference> --out work/ref/digest --guide work/ref/draft.json",
                   "vocabulary": "references/page_craft_vocabulary.json"})
        self.notes.append("gallery crops and exemplars live in the gallery manifest (gallery.py --out), not in this guide")
        text_layer = {"status": "typographic"}
        if self.is_pdf:
            sizes = [r.size_pt for r in self._runs]
            tiny = sum(1 for v in sizes if v < 4.0) / len(sizes) if sizes else 1.0
            body = self._roles.get("type.body", {}).get("size_pt")
            if tiny > 0.3 or (body is not None and body < 5.0) or not sizes:
                text_layer = {"status": "suspect", "reason": f"{tiny:.0%} of characters are under 4pt and the body role reads {body}pt: a scanned or OCR text layer. Sizes, families and inks from this file are not evidence; use the renders and complete the guide from them, or find the native deck.",
                              "tiny_share": round(tiny, 3)}
                self.notes.append(text_layer["reason"])
        self.guide = {
            "schema": "pptx-skill style guide draft v1",
            "measurement": textfit.ruler_pin(),
            "reference": {"file": str(self.path), "sha256": hashlib.sha256(Path(self.path).read_bytes()).hexdigest(), "slides": len(self.slides),
                          "format": "pdf" if self.is_pdf else "pptx", "text_layer": text_layer,
                          "triage": ({k: self.triage[k] for k in ("deck_class", "counts", "evidence_pages", "raster_pages", "modal_page_pt")} if self.triage else None),
                          "page": {"width_emu": self.w, "height_emu": self.h, "width_in": round(self.w / EMU_PER_INCH, 3), "height_in": round(self.h / EMU_PER_INCH, 3),
                                   "orientation": "landscape" if self.w >= self.h else "portrait"},
                          "layouts_used": Counter(s.layout_name for s in self.slides).most_common() if not self.is_pdf else None},
            **self.guide,
            "unresolved": self.unresolved,
            "notes": self.notes,
        }
        return self.guide


RASTER_OPEN = (
    ("/typography/roles/type.title", "size, face, weight, case and ink of the title"),
    ("/typography/roles/type.h1", "section heading inside the page"),
    ("/typography/roles/type.body", "running text"),
    ("/typography/roles/type.caption", "chart and table labels"),
    ("/typography/roles/type.footnote", "source lines and notes"),
    ("/typography/families", "the faces in use (the raster carries letterforms, not names: match by eye with fc-match candidates)"),
    ("/typography/bullets", "the bullet per level as the pages draw it, {\"0\": {\"glyph\": \"<the glyph>\", \"font\": \"<its face>\", \"indent_role\": \"space.<step>\", \"hanging_indent_role\": \"space.<step>\"}}; the indent roles are required by the solver"),
    ("/color/roles/color.surface", "page ground"),
    ("/color/roles/color.ink", "primary text colour"),
    ("/color/roles/color.ink_muted", "secondary text colour"),
    ("/color/roles/color.rule", "rule colour"),
    ("/color/roles/color.accent1", "first chart and emphasis colour"),
    ("/color/roles/color.accent2", "second accent"),
    ("/color/roles/color.accent3", "third accent"),
    ("/color/roles/color.accent4", "fourth accent"),
    ("/color/roles/color.surface_alt", "panel and band fill"),
    ("/color/roles/color.ink_inverse", "text on dark fills"),
    ("/color/roles/color.emphasis", "the look-here colour of outline boxes, rings and highlights, read off the pages (null when the house marks nothing)"),
    ("/spacing/steps", "the spacing scale"),
    ("/spacing/margins", "page margins per side"),
    ("/chrome", "recurring furniture: rules, bands, logo block, page number"),
    ("/composition", "the arrangements the house uses"),
    ("/tables", "rule classes and header treatment"),
    ("/charts", "series colours, label and axis treatment"),
    ("/floors", "smallest sizes the house uses, per family"),
)


def _raster_run(self: "Extractor") -> dict:
    """A raster reference: every text-derived address opens; raster_style.py and the agent's
    eyes fill them with raster_inference provenance at confidence <= 0.5."""
    tri = self.triage or {}
    for path, reason in RASTER_OPEN:
        self.open(path, f"raster reference: {reason}", {"provenance": "raster_inference", "max_confidence": 0.5})
    for path, reason in (("/description", "written by the model from the page images: summary, typography, color, layout, tables, imagery, motifs, never_does, tone"),
                         ("/derivation_rules", "how to extend the palette and the type ladder to roles the reference never showed"),
                         ("/continuation", "header repeat, cont'd mark and takeaway policy when a slide splits")):
        self.open(path, reason)
    self.open("/exhibit_habits", "how the house builds its exhibits is read by looking at its pages: the digest of a raster reference "
              "cuts whole pages (no shapes to crop); copy the stub to digest.json beside it, complete every page, and answer with "
              "complete_guide.py --digest <dir>",
              {"command": "python3 scripts/gallery.py digest <reference> --out work/ref/digest --guide work/ref/draft.json",
               "vocabulary": "references/page_craft_vocabulary.json"})
    self.notes.append("raster reference: the text layer is a wrapper or an OCR layer and was not mined. Next: "
                      "python3 scripts/raster_style.py <ref.pdf> --out work/ref/raster, read raster.md and the chrome mask, "
                      "then complete the guide from the page images with raster_inference provenance at confidence <= 0.5.")
    self.guide = {
        "schema": "pptx-skill style guide draft v1",
        "measurement": textfit.ruler_pin(),
        "reference": {"file": str(self.path), "sha256": hashlib.sha256(Path(self.path).read_bytes()).hexdigest(), "slides": len(self.slides),
                      "format": "pdf", "text_layer": {"status": "raster", "deck_class": tri.get("deck_class"), "counts": tri.get("counts"),
                                                       "raster_pages": tri.get("raster_pages"), "slide_box_pt": tri.get("slide_box_pt"),
                                                       "slide_size_in": tri.get("slide_size_in"), "size_basis": tri.get("size_basis"), "print_scale": tri.get("print_scale"),
                                                       "effective_dpi": tri.get("effective_dpi"), "modal_page_pt": tri.get("modal_page_pt")},
                      "page": {"width_emu": self.w, "height_emu": self.h, "width_in": round(self.w / EMU_PER_INCH, 3), "height_in": round(self.h / EMU_PER_INCH, 3),
                               "orientation": "landscape" if self.w >= self.h else "portrait"},
                      "layouts_used": None},
        "typography": {"families": {"major": None, "minor": None, "fallbacks": []}, "levels": [], "roles": {}, "scale_ratio": None, "bullets": {}},
        "color": {"theme": {}, "roles": {}, "usage": {}},
        "spacing": {"steps": {}, "margins": {}, "baseline_emu": None, "gap_levels": []},
        "composition": {"archetypes": [], "bands": [], "column_grids": [], "alignment_edges": []},
        "variety": {"pages": [], "why": "a raster reference: its pages are images with no shapes, so no page has a composition archetype"},
        "register_stats": {},
        "density_bands": {},
        "chrome": [],
        "motifs": [],
        "tables": None,
        "charts": None,
        "shape_language": {},
        "imagery": {},
        "floors": {},
        "unresolved": self.unresolved,
        "notes": self.notes,
    }
    return self.guide


Extractor.run_raster = _raster_run


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


def variety_report(v: dict | None) -> list[str]:
    """The draft's variety section: how it is computed, where it is weak, the page sequence
    with the triage proposal, and the measure (plan.py's)."""
    out = ["", "## Variety (content pages)", ""]
    if not v or not v.get("pages"):
        return out + [f"No evidence: {(v or {}).get('why') or 'no page sequence'}."]
    out += [f"How: {v['method']}", "", "Where it is weak:"] + [f"- {w}" for w in v["weaknesses"]] + [""]
    out.append(f"Content pages ({v['content_pages']['basis']}): {v['content_pages']['pages']}")
    out.append("| slide | composition | triage | why |")
    out.append("|---|---|---|---|")
    out += [f"| {p['slide']} | {p['composition']} | {p['triage']} | {p['why']} |" for p in v["pages"]]
    m = v["measure"]
    out.append("")
    if m["status"] != "measured":
        return out + [f"Measure: {m['why']}."]
    out.append(f"V (composition) {m['composition']['V']} ({m['composition']['changed']} of {m['composition']['pairs']} adjacent pairs change); "
               f"distinct compositions {m['distinct']['compositions']} over {m['distinct']['pages']} pages ({m['distinct']['per_page']} per page); "
               f"longest run {m['longest_run']}; segments {m['segments']}")
    out.append(f"Runs of one composition: {m['runs'] or 'none'}")
    ex = m["exhibits"]
    out.append(f"V (exhibit-type sets): {ex['V'] if 'V' in ex else ex['why']}")
    cl = m["classes"]
    out.append(f"V (exhibit-class sets): {cl['V'] if 'V' in cl else cl['why']}")
    return out


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
    out += variety_report(g.get("variety"))
    out += ["", "## Chrome and motifs", ""]
    for ch in g.get("chrome", []):
        out.append(f"- {ch['chrome_id']} {ch['kind']} ({ch['shape_kind']}, {ch['source_layer']}) box {ch['box_in']} in"
                   + (f" turned {ch['rotation_deg']} deg" if ch.get("rotation_deg") else "")
                   + f", {ch['anchor']}, {ch['span']}, fill {ch['fill_hex']}, line {ch['line_hex']} {ch['line_width_pt']}pt, text {ch['text']!r}, style {ch.get('text_style')}, on {ch['slides_present']}/{ch['of_slides']} slides"
                   + f", paints {ch.get('paint_order')}" + (f", content inside on {ch['carries_content_on']} slides" if ch.get("carries_content_on") else ""))
    for m in g.get("motifs", []):
        out.append(f"- {m['motif_id']}: {m['name']}, line {m['line_role']} {m['line_width_pt']}pt, fill {m['fill_role']}")
    ti = g.get("titles")
    if ti:
        out += ["", "## Titles (by position)", ""]
        d = ti["distribution"]
        out.append(f"Characters {d['chars']}; words {d['words']}; lines {d['lines']}. Blocks at the kicker position (above): {ti['positions']['above']} "
                   f"of {ti['positions']['pages_with_title']} pages; at the subtitle or units-line position (below): {ti['positions']['below']} ({ti['positions']['gap_rule']}).")
        out += ["", "| slide | title | chars | words | lines | above | below |", "|---|---|---|---|---|---|---|"]
        for r in ti["records"]:
            out.append(f"| {r['slide']}{' (cover)' if r['placeholder'] == 'ctrTitle' else ''} | {r['text']} | {r['chars']} | {r['words']} | {r['lines']} | "
                       f"{(r['above'] or {}).get('text', '')} | {(r['below'] or {}).get('text', '')} |")
        reg = ti.get("register")
        out.append("")
        out.append(f"Register: {json.dumps(reg['counts']) if reg else 'open (/titles/register): classify every title above'}.")
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
    ap.add_argument("--pages", default=None, help="PDF page range to treat as the deck, 1-based inclusive, e.g. 7-60 (after reading the triage)")
    ap.add_argument("--include-generated", action="store_true", help="count slides carrying the pptx-skill origin tag as evidence (skipped by default)")
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out", "report")
    import cli
    pages = cli.page_range(args.pages) if args.pages else None
    ex = Extractor(args.reference, args.max_pages, pages, args.include_generated)
    guide = ex.run()
    out = cli.out_path(Path(args.out) if args.out else Path(args.reference).with_suffix(".style.json"), "guide draft")
    cli.out_path(Path(args.report) if args.report else out.with_suffix(".md"), "report")
    out.parent.mkdir(parents=True, exist_ok=True)
    if ex.is_pdf:
        chrome_pictures(guide, args.reference, out.parent / "chrome")
        ground_picture(guide, args.reference, out.parent / "chrome")
    out.write_text(json.dumps(guide, indent=1, default=str))
    rep = Path(args.report) if args.report else out.with_suffix(".md")
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(report(guide))
    roles = guide.get("typography", {}).get("roles", {})
    print(json.dumps({"guide": str(out), "report": str(rep), "slides": guide["reference"]["slides"],
                      "generated_slides_skipped": ex.generated_skipped,
                      "type_roles": {r: roles[r]["size_pt"] for r in roles},
                      "color_roles": {r: v["hex"] for r, v in guide.get("color", {}).get("roles", {}).items()},
                      "spacing": {k: v["emu"] for k, v in guide.get("spacing", {}).get("steps", {}).items()},
                      "unresolved": len(guide["unresolved"])}, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
