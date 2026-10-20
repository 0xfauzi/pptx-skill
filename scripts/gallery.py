#!/usr/bin/env python3
"""Component gallery and exemplars for a reference deck: cropped renders of its
interesting components, one whole-slide render per composition family, and a
text-free skeleton of each exemplar.

    gallery.py deck.pptx --out DIR [--width 1600] [--guide guide.style.json]

Writes DIR/pages/slide-NN.png + fonts.json (render.py's output), then
DIR/crops/crop-NN.png, DIR/exemplars/ex-NN.png + ex-NN.skeleton.json,
DIR/manifest.json and DIR/MANIFEST.md.

A port of deckgen's style/gallery.py and style/shapes.py. Every decision is
integer EMU geometry read from the OOXML: the render is only ever CUT, never
measured, because LibreOffice breaks lines differently from PowerPoint and a
pixel cannot judge fit or position. Captions are mechanical. No document text
reaches a caption, a skeleton or the manifest.

The parameters are deckgen's measured values (deckgen
docs/measurements/S1B3-decision.md parts 2 and 4), cited where declared. They
were CHECKED on a three-deck 4:3 investment-banking corpus, not tuned until the
output looked nice: no crop is evidence that a component is well designed, only
that it carries arrangement the numeric guide cannot state and is big enough to
read.

--guide takes extract_style.py's guide JSON for two things: the mined gutter
(the grouping threshold becomes min(ceiling, gutter // 2), protecting a deck
laid out tighter than the corpus) and the per-shape evidence behind each mined
token (when the crop cap binds, crops are chosen by greedy set cover over the
tokens they show). Without a guide the ceiling groups and the cut falls back to
recurrence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lxml import etree
from PIL import Image

import ooxml
import render
from extract_style import hungarian_max

Box = tuple[int, int, int, int]  # x, y, width, height in EMU

# --- parameters -------------------------------------------------------------------------

COMPONENT_GAP_EMU = 114_300
# 9 pt, a CEILING. Measured (S1B3 part 2): nearest-neighbour gaps between content
# shapes on the corpus are bimodal with the 1 pt bins [8,9) and [9,10) empty on
# all three decks; counts are identical at 8, 9 and 10 pt (96/74/46), 12 pt
# merges. Points, not a page fraction: gutters are set in points. A deck laid
# out tighter has no band there (a 6 pt grid chains all its tiles), hence the
# min(ceiling, mined gutter // 2) rule in component_gap_emu.
COMPONENT_SIMILARITY_TAU = 0.95
# Two components are the SAME crop at or above this: a judgement bounded by
# measurement (S1B3 part 2): no valley in pairwise similarity, adjacent-threshold
# agreement 100% at 0.95-1.00, and at 0.70 visibly different proportions collapse.
ARCHETYPE_IOU_THRESHOLD = 0.5  # slide families: the PASCAL VOC match criterion
MOTIF_MIN_OCCURRENCES = 2  # definition, not measurement: the smallest count that is "recurring"
MIN_CROP_AREA_PX = 200 * 200
# AREA floor in raster pixels (deckgen engineering guidance: models hallucinate
# under ~200px images). Area, not short side: the short-side reading rejected the
# 1748x148 header banner that is each corpus deck's most repeated component.
CROP_PAD_MIN_RASTER_PX = 2  # rounding at either edge cannot clip a boundary pixel
GALLERY_POOL_MAX = 24  # provisional in deckgen (config/provisional.py), binds only on jazz
EXEMPLAR_POOL_MAX = 8  # provisional in deckgen, binds only on jazz (13 families)
MAX_SHAPE_PAIRS = 5_000_000  # grouping is quadratic per slide; 0.53 us per pair (deckgen)
MAX_COMPONENTS = 1_000  # clustering is quadratic over components; 4 s at 1000 (deckgen)

NON_TEXT_KINDS = frozenset({"table", "chart", "image", "graphic"})
KIND_ORDER = ("table", "chart", "image", "graphic", "connector", "shape")
EMU_PER_INCH = 914_400
A, P = ooxml.A, ooxml.P
NV_WRAPPERS = ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr", "nvCxnSpPr")
INWARD_EFFECTS = frozenset({"softEdge", "innerShdw"})
LINE_FILLS = frozenset({"solidFill", "gradFill", "pattFill"})
FIDELITY_NOTES = {
    "faithful": "Every declared font rendered with itself: letterforms and layout are both evidence.",
    "metric_substituted": "**Every image is flagged `metric_substituted`.** The renderer drew metric-compatible aliases "
    "(Liberation, Carlito, Caladea) for the declared faces: layout is faithful, letterforms are not. A designer reading "
    "these images must NOT copy letterforms from them; take the typeface from the guide.",
    "unknown_substitution": "**Every image is flagged `unknown_substitution`.** At least one declared font was drawn with "
    "an unrelated substitute, so text extents, wrapping AND letterforms are not evidence. Read arrangement and colour only.",
}


class GalleryRefused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


# --- the shape join -----------------------------------------------------------------------

@dataclass(frozen=True)
class Leaf:
    ref: str  # deckgen's spelling: spTree/sp[3](id=6), position among ALL container children
    shape_ref: str  # ooxml.py's spelling (sp[id=6]), the key a guide's evidence carries
    kind: str  # shape | connector | image | table | chart | graphic
    role: str  # placeholder type, or "none"
    chrome: bool
    bounds: Box | None  # declared, pre-rotation
    rotation: int  # 60000ths of a degree
    runs: int
    filled: bool
    lined: bool
    ink_emu: int  # how far the shape's own stroke or effects reach outside its bounds


@dataclass(frozen=True)
class Slide:
    index: int
    surface: str
    hidden: bool
    leaves: tuple[Leaf, ...]  # document (z) order


@dataclass(frozen=True)
class Deck:
    path: Path
    width_emu: int
    height_emu: int
    slides: tuple[Slide, ...]


def _int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _cnv_id(element: etree._Element) -> str:
    for wrapper in NV_WRAPPERS:
        cnv = element.find(f"{{{P}}}{wrapper}/{{{P}}}cNvPr")
        if cnv is not None:
            return str(cnv.get("id", "?"))
    return "?"


def _leaf_elements(container: etree._Element, prefix: str) -> Iterator[tuple[str, etree._Element]]:
    """Leaves in document order, the same walk ooxml.SlideWalker.walk_tree makes."""
    for position, child in enumerate(container):
        tag = etree.QName(child).localname
        if tag not in ("sp", "pic", "cxnSp", "graphicFrame", "grpSp"):
            continue
        ref = f"{prefix}/{tag}[{position}](id={_cnv_id(child)})"
        if tag == "grpSp":
            yield from _leaf_elements(child, ref)
        else:
            yield ref, child


def _leaf_kind(tag: str, shape: ooxml.Shape) -> str:
    if tag == "graphicFrame":
        return shape.kind if shape.kind in ("table", "chart") else "graphic"
    return {"pic": "image", "cxnSp": "connector"}.get(tag, "shape")


def _ink_reach(element: etree._Element, shape: ooxml.Shape) -> tuple[int, bool]:
    """(reach outside the bounds, lined). A stroke straddles its path, so half of
    it lies outside; a shadow reaches dist + blurRad, a glow its rad; softEdge and
    innerShdw draw inward and reach nothing. Furthest contributor, not the sum."""
    lined = shape.line is not None
    reach = (shape.line_w_emu or 0) // 2 if lined else 0
    sppr = element.find(f"{{{P}}}spPr")
    if sppr is None:
        return reach, lined
    if shape.kind == "picture":
        # ooxml.py resolves fill and line for sp and cxnSp only; a keylined
        # picture's frame is its own a:ln and reaches out exactly as a keyline does.
        ln = sppr.find(f"{{{A}}}ln")
        if ln is not None and any(etree.QName(c).localname in LINE_FILLS for c in ln):
            lined = True
            reach = max(reach, (_int(ln.get("w")) or ooxml.DEFAULT_LINE_WIDTH_EMU) // 2)
    effects = sppr.find(f"{{{A}}}effectLst")
    for effect in effects if effects is not None else ():
        if etree.QName(effect).localname in INWARD_EFFECTS:
            continue
        reach = max(reach, _int(effect.get("dist")) + _int(effect.get("blurRad")), _int(effect.get("rad")))
    return reach, lined


def join_deck(path: Path) -> Deck:
    """ooxml.py's per-slide shapes (placeholder geometry inherited, group transforms
    applied) joined, in document order, to the XML leaf each came from, for the
    facts ooxml.py does not record: deckgen's ref spelling, the a:r count, and the
    ink reach. Any disagreement between the two walks refuses the deck."""
    prints = ooxml.fingerprint_deck(str(path))
    if not prints:
        raise GalleryRefused("no_slides", "the deck lists no slides")
    pkg = ooxml.Package(str(path))
    slides: list[Slide] = []
    for print_ in prints:
        root = pkg.root(print_.part)
        tree = root.find(f"{{{P}}}cSld/{{{P}}}spTree")
        elements = list(_leaf_elements(tree, "spTree")) if tree is not None else []
        if len(elements) != len(print_.shapes):
            raise GalleryRefused(
                "shape_join", f"{print_.part}: {len(elements)} leaves in the XML against {len(print_.shapes)} from ooxml.py"
            )
        leaves: list[Leaf] = []
        for (ref, element), shape in zip(elements, print_.shapes, strict=True):
            if ref.rsplit("id=", 1)[1].rstrip(")") != shape.ref.rsplit("id=", 1)[1].rstrip("]"):
                raise GalleryRefused("shape_join", f"{print_.part}: {ref} paired with {shape.ref}")
            reach, lined = _ink_reach(element, shape)
            leaves.append(
                Leaf(
                    ref=ref,
                    shape_ref=shape.ref,
                    kind=_leaf_kind(etree.QName(element).localname, shape),
                    role=shape.ph_type or "none",
                    chrome=shape.ph_type in ooxml.CHROME_TYPES,
                    bounds=shape.box,
                    rotation=shape.rotation,
                    runs=sum(1 for _ in element.iter(f"{{{A}}}r")),
                    filled=shape.fill is not None,
                    lined=lined,
                    ink_emu=reach,
                )
            )
        slides.append(Slide(print_.index, print_.part, root.get("show") == "0", tuple(leaves)))
    if prints[0].width <= 0 or prints[0].height <= 0:
        raise GalleryRefused("no_page_size", "the deck declares no usable p:sldSz")
    return Deck(path, prints[0].width, prints[0].height, tuple(slides))


def content_leaves(slide: Slide) -> list[Leaf]:
    """Leaves with geometry, chrome dropped, sorted by ref: deckgen's shape join
    sorts its keys, and that order fixes which member names a component."""
    return sorted((leaf for leaf in slide.leaves if leaf.bounds is not None and not leaf.chrome), key=lambda leaf: leaf.ref)


# --- geometry ------------------------------------------------------------------------------

def visual_extent(bounds: Box, rotation: int) -> Box:
    """The axis-aligned box a rotated shape occupies: OOXML rotates about the
    centre, so w' = |w cos| + |h sin|. Exact for any angle."""
    if not rotation:
        return bounds
    x, y, w, h = bounds
    radians = math.radians(rotation / 60_000)
    cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
    tw, th = round(w * cos + h * sin), round(w * sin + h * cos)
    return x + (w - tw) // 2, y + (h - th) // 2, tw, th


def extent_of(leaf: Leaf) -> Box:
    if leaf.bounds is None:
        raise ValueError(f"{leaf.ref} has no geometry")
    return visual_extent(leaf.bounds, leaf.rotation)


def box_gap_emu(a: Box, b: Box) -> int:
    """The larger of the two axis gaps; zero when the boxes touch or overlap."""
    horizontal = max(0, max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2]))
    vertical = max(0, max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3]))
    return max(horizontal, vertical)


def iou(a: Box, b: Box) -> float:
    """Degenerate boxes compare EXACTLY: a zero-height rule must match itself, or
    a title-plus-rule motif scores 0.5 against its own copy and never deduplicates."""
    inter_w = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    inter_h = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = inter_w * inter_h
    union = a[2] * a[3] + b[2] * b[3] - inter
    if union > 0:
        return inter / union
    return 1.0 if a == b else 0.0


def slide_similarity(
    a: Sequence[Box], b: Sequence[Box], labels_a: Sequence[str] | None = None, labels_b: Sequence[str] | None = None
) -> float:
    """Hungarian optimal assignment on pairwise IoU, scored over the larger set;
    role-wise when labelled (a mismatched pair scores 0 and cannot be assigned)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    matrix = [
        [iou(x, y) if labels_a is None or labels_b is None or labels_a[i] == labels_b[j] else 0.0 for j, y in enumerate(b)]
        for i, x in enumerate(a)
    ]
    return hungarian_max(matrix) / max(len(a), len(b))


def leader_clusters(
    groups: Sequence[Sequence[Box]], labels: Sequence[Sequence[str]] | None = None, threshold: float = ARCHETYPE_IOU_THRESHOLD
) -> list[tuple[int, list[int]]]:
    """Greedy leader clustering, first-appearance order, compared to the anchor only."""
    clusters: list[tuple[int, list[int]]] = []
    for index, group in enumerate(groups):
        for anchor, members in clusters:
            la, lb = (None, None) if labels is None else (labels[anchor], labels[index])
            if slide_similarity(groups[anchor], group, la, lb) >= threshold:
                members.append(index)
                break
        else:
            clusters.append((index, [index]))
    return clusters


def structural_medoid(members: Sequence[int], groups: Sequence[Sequence[Box]], labels: Sequence[Sequence[str]] | None) -> int:
    """The member most like all the others by the metric that formed the cluster;
    ties go to the lowest index, which is deck order."""
    best, best_total = members[0], -math.inf
    for index in members:
        la = None if labels is None else labels[index]
        total = sum(
            slide_similarity(groups[index], groups[other], la, None if labels is None else labels[other])
            for other in members
            if other != index
        )
        if total > best_total:
            best, best_total = index, total
    return best


# --- components and the two filters -------------------------------------------------------

@dataclass(frozen=True)
class Component:
    slide: Slide
    members: tuple[Leaf, ...]
    box: Box  # union of the members' occupied extents

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(leaf.kind for leaf in self.members)

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(leaf.role for leaf in self.members)

    @property
    def run_count(self) -> int:
        return sum(leaf.runs for leaf in self.members)

    @property
    def sort_key(self) -> tuple[int, str]:
        return self.slide.index, self.members[0].ref


def _find(parent: list[int], node: int) -> int:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def components(deck: Deck, slides: Sequence[Slide], gap_emu: int) -> list[Component]:
    """Single-linkage grouping of each slide's content leaves by occupied-box gap.
    A component with no area on the page is dropped: its crop would be a
    one-pixel sliver and its box would dominate any comparison."""
    found: list[Component] = []
    for slide in slides:
        keys = content_leaves(slide)
        extents = [extent_of(leaf) for leaf in keys]
        parent = list(range(len(keys)))
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if box_gap_emu(extents[i], extents[j]) <= gap_emu:
                    root_i, root_j = _find(parent, i), _find(parent, j)
                    if root_i != root_j:
                        parent[max(root_i, root_j)] = min(root_i, root_j)
        grouped: dict[int, list[int]] = {}
        for index in range(len(keys)):
            grouped.setdefault(_find(parent, index), []).append(index)
        for root in sorted(grouped):
            indices = sorted(grouped[root])
            boxes = [extents[i] for i in indices]
            left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
            right, bottom = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
            if right <= 0 or bottom <= 0 or left >= deck.width_emu or top >= deck.height_emu:
                continue
            found.append(Component(slide, tuple(keys[i] for i in indices), (left, top, right - left, bottom - top)))
    return found


def is_substantive(component: Component) -> bool:
    """More than one part (an arrangement), a non-text kind (internal arrangement
    the tokens never state), or more than one run (internal text structure). A
    single shape with a single run is already fully stated by the guide's numbers;
    measured, this filter does most of the work (96 -> 36, 74 -> 20, 46 -> 25)."""
    if len(component.members) > 1 or any(kind in NON_TEXT_KINDS for kind in component.kinds):
        return True
    return component.run_count > 1


def is_legible(box: Box, emu_per_px: float) -> bool:
    """Judged on the crop that will actually be sent (padded, clamped), in pixels."""
    return (box[2] / emu_per_px) * (box[3] / emu_per_px) >= MIN_CROP_AREA_PX


def normalized_members(component: Component) -> list[Box]:
    """Member extents moved to the component's origin. Translation ONLY: scaling
    into a unit box would make every lone shape the same rectangle and would make
    a component at twice the size the same crop."""
    x0, y0 = component.box[0], component.box[1]
    return [(e[0] - x0, e[1] - y0, e[2], e[3]) for e in (extent_of(leaf) for leaf in component.members)]


def member_labels(component: Component) -> list[str]:
    return [f"{leaf.kind}:{leaf.role}" for leaf in component.members]


def categories_of(component: Component, occurrences: int) -> tuple[str, ...]:
    labels = ["recurring" if occurrences >= MOTIF_MIN_OCCURRENCES else "singleton"]
    if len(component.members) >= 2:
        labels.append("composite")
    return tuple(labels)


# --- selection -------------------------------------------------------------------------------

EvidenceIndex = dict[tuple[str, str], frozenset[str]]  # (slide part, ooxml shape ref) -> token pointers


@dataclass(frozen=True)
class Candidate:
    cluster: int
    component: Component
    index: int
    occurrences: int
    categories: tuple[str, ...]


def _covers(candidate: Candidate, evidence: EvidenceIndex) -> frozenset[str]:
    found: set[str] = set()
    for leaf in candidate.component.members:
        found |= evidence.get((candidate.component.slide.surface, leaf.shape_ref), frozenset())
    return frozenset(found)


def select(
    found: Sequence[Component],
    clusters: Sequence[tuple[int, list[int]]],
    groups: Sequence[Sequence[Box]],
    labels: Sequence[Sequence[str]],
    keep: Callable[[int], bool],
    budget: int,
    evidence: EvidenceIndex,
) -> list[Candidate]:
    """One crop per cluster with a showable member, the medoid of the showable
    ones. Clustering ran over ALL components so a cluster's size is the deck's
    true repetition count; only the representative must pass the filters. When
    the cap binds: greedy set cover over the mined tokens the candidates show
    (S1B3 part 4: recurrence ordering lost ten mined tokens on jazz, coverage
    lost none), ties by recurrence, part count, deck order; with no evidence
    index every candidate covers nothing and the ties decide."""
    candidates: list[Candidate] = []
    for cluster_index, (_anchor, members) in enumerate(clusters):
        eligible = [index for index in members if keep(index)]
        if not eligible:
            continue
        pick = structural_medoid(eligible, groups, labels)
        candidates.append(Candidate(cluster_index, found[pick], pick, len(members), categories_of(found[pick], len(members))))
    if len(candidates) <= budget:
        return sorted(candidates, key=lambda c: c.component.sort_key)
    remaining, covered, chosen = list(candidates), set[str](), list[Candidate]()
    while remaining and len(chosen) < budget:
        best = min(
            remaining,
            key=lambda c: (-len(_covers(c, evidence) - covered), -c.occurrences, -len(c.component.members), c.component.sort_key),
        )
        covered |= _covers(best, evidence)
        chosen.append(best)
        remaining.remove(best)
    return sorted(chosen, key=lambda c: c.component.sort_key)


# --- cropping --------------------------------------------------------------------------------

def crop_box(component: Component, pad_floor_emu: int, deck: Deck) -> Box:
    """The component box grown by the pad and clamped to the page. Each member's
    ink pad is bounded by THAT member's own longest side: dist and blurRad are
    unbounded values off an untrusted file, and one declared 100-inch shadow
    otherwise turns every crop on the slide into the whole slide."""
    pad = max((min(leaf.ink_emu, max(extent_of(leaf)[2], extent_of(leaf)[3])) for leaf in component.members), default=0)
    pad = max(pad_floor_emu, pad)
    x, y, w, h = component.box
    left = min(max(0, x - pad), deck.width_emu)
    top = min(max(0, y - pad), deck.height_emu)
    right = min(deck.width_emu, x + w + pad)
    bottom = min(deck.height_emu, y + h + pad)
    return left, top, max(0, right - left), max(0, bottom - top)


def cut(page_png: Path, box: Box, deck: Deck, target: Path) -> tuple[int, int]:
    """EMU to pixels by the page's own scale per axis, clamped to the image."""
    with Image.open(page_png) as image:
        width_px, height_px = image.size
        left = round(box[0] * width_px / deck.width_emu)
        top = round(box[1] * height_px / deck.height_emu)
        right = round((box[0] + box[2]) * width_px / deck.width_emu)
        bottom = round((box[1] + box[3]) * height_px / deck.height_emu)
        left, top = max(0, min(width_px - 1, left)), max(0, min(height_px - 1, top))
        right, bottom = max(left + 1, min(width_px, right)), max(top + 1, min(height_px, bottom))
        image.crop((left, top, right, bottom)).save(target, format="PNG")
    return right - left, bottom - top


# --- captions (deckgen's wording, byte for byte) ------------------------------------------

def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _kind_phrase(kinds: Sequence[str]) -> str:
    counts = Counter(kinds)
    return " + ".join(_plural(counts[kind], kind) for kind in KIND_ORDER if counts.get(kind))


def _role_phrase(roles: Sequence[str]) -> str:
    named = sorted({role for role in roles if role != "none"})
    return "roles " + ", ".join(named) if named else "no placeholder roles"


def _dominant_kind(component: Component) -> str:
    """A component containing a table, chart, image or graphic is named for it;
    among text-only parts the count decides, and a shape with runs is text."""
    counts = Counter(component.kinds)
    telling = [name for name in KIND_ORDER if name in NON_TEXT_KINDS and counts[name]]
    if telling:
        return telling[0]
    kind = min(counts, key=lambda name: (-counts[name], KIND_ORDER.index(name) if name in KIND_ORDER else len(KIND_ORDER)))
    return "text" if kind == "shape" and component.run_count else kind


def crop_name(component: Component, occurrences: int) -> str:
    parts = len(component.members)
    kind = _dominant_kind(component)
    head = f"{parts}-part {kind} group" if parts > 1 else f"{kind} block"
    return f"recurring {head}" if occurrences >= MOTIF_MIN_OCCURRENCES else head


def caption(candidate: Candidate, box: Box) -> str:
    component = candidate.component
    occurrences = (
        f"appears {candidate.occurrences} times in the deck"
        if candidate.occurrences >= MOTIF_MIN_OCCURRENCES
        else "appears once in the deck"
    )
    return (
        f"{crop_name(component, candidate.occurrences)}: "
        f"{_kind_phrase(component.kinds)}, "
        f"{_plural(len(component.members), 'part')}, "
        f"{_plural(component.run_count, 'run')}; "
        f"{_role_phrase(component.roles)}; "
        f"{box[2] / EMU_PER_INCH:.1f} x {box[3] / EMU_PER_INCH:.1f} in on slide {component.slide.index + 1}; "
        f"{occurrences}"
    )


# --- exemplars --------------------------------------------------------------------------------

def _declared_boxes(slides: Sequence[Slide]) -> list[list[Box]]:
    return [[leaf.bounds for leaf in content_leaves(slide) if leaf.bounds is not None] for slide in slides]


def slide_families(slides: Sequence[Slide]) -> list[tuple[int, list[int]]]:
    """Leader clustering of slides on their DECLARED content boxes, unlabelled, at
    the archetype threshold. The declared rectangle, not the occupied one: this is
    layout as authored, and extract_style.py's archetypes are numbered the same way."""
    return leader_clusters(_declared_boxes(slides))


def skeleton(slide: Slide, deck: Deck) -> dict[str, object]:
    """Structure in document order with no document text: it rides into prompts."""
    return {
        "slide_index": slide.index,
        "surface": slide.surface,
        "page": {"width_emu": deck.width_emu, "height_emu": deck.height_emu},
        "shapes": [
            {
                "ref": leaf.ref,
                "kind": leaf.kind,
                "role": leaf.role,
                "box": dict(zip(("x_emu", "y_emu", "width_emu", "height_emu"), extent_of(leaf), strict=True)),
                "runs": leaf.runs,
                "filled": leaf.filled,
                "lined": leaf.lined,
            }
            for leaf in slide.leaves
            if leaf.bounds is not None and not leaf.chrome
        ],
    }


def select_exemplars(slides: Sequence[Slide], budget: int) -> list[tuple[int, Slide, int]]:
    """(family index, representative slide, family size), biggest families first.
    Numbered by first appearance BEFORE the cap, so dropping a small family never
    renumbers the rest; the representative is the medoid, not the earliest slide."""
    boxes = _declared_boxes(slides)
    ranked = sorted(enumerate(leader_clusters(boxes)), key=lambda entry: (-len(entry[1][1]), entry[1][0]))
    return [(index, slides[structural_medoid(members, boxes, None)], len(members)) for index, (_anchor, members) in ranked[:budget]]


# --- the guide, when one is given -------------------------------------------------------------

def read_guide(path: Path) -> tuple[int | None, EvidenceIndex]:
    """The mined gutter and an inverted evidence index: which mined tokens each
    slide shape is evidence for. Evidence naming a layout, master or theme is
    dropped: a crop of a slide cannot contain a shape the slide does not carry."""
    guide = json.loads(path.read_text())
    gutter: int | None = None
    steps = guide.get("spacing", {}).get("steps", {}) if isinstance(guide, dict) else {}
    value = steps.get("space.gutter", {}).get("emu") if isinstance(steps, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        gutter = value
    index: dict[tuple[str, str], set[str]] = {}

    def walk(node: object, pointer: str) -> None:
        if isinstance(node, dict):
            provenance = node.get("provenance")
            if isinstance(provenance, dict) and isinstance(provenance.get("evidence"), list):
                for item in provenance["evidence"]:
                    part, _, ref = str(item).partition("#")
                    if "/slides/" in part and ref:
                        index.setdefault((part, ref.split("/", 1)[0]), set()).add(pointer)
            for key, child in node.items():
                walk(child, f"{pointer}/{key}")
        elif isinstance(node, list):
            for position, child in enumerate(node):
                walk(child, f"{pointer}/{position}")

    walk(guide, "")
    return gutter, {key: frozenset(pointers) for key, pointers in index.items()}


def component_gap_emu(gutter_emu: int | None) -> int:
    """The tighter of the measured ceiling and half the deck's own gutter: parts of
    one component sit closer than the deck sets its columns apart. On the corpus
    the ceiling wins (gutters 24-87 pt); on a 6 pt grid the gutter wins."""
    return COMPONENT_GAP_EMU if gutter_emu is None else min(COMPONENT_GAP_EMU, gutter_emu // 2)


# --- rendering (render.py) --------------------------------------------------------------------

def render_pages(deck_path: Path, out: Path, width: int) -> tuple[list[Path], dict[str, dict[str, object]]]:
    out.mkdir(parents=True, exist_ok=True)
    fonts = render.font_report(render.declared_fonts(deck_path))
    (out / "fonts.json").write_text(json.dumps(fonts, indent=1))
    with tempfile.TemporaryDirectory(prefix="gallery-render-") as tmp:
        pdf = render.to_pdf(deck_path, Path(tmp))
        count = render.page_count(pdf)
        pages = render.rasterize(pdf, out, 110, list(range(1, count + 1)), width)
    return pages, fonts


def render_fidelity(fonts: dict[str, dict[str, object]]) -> str:
    """deckgen's worst-family verdict. A metric alias (Liberation, Carlito,
    Caladea) keeps the layout faithful and the letterforms not; an unrelated
    substitute changes text extents too; a deck that vouches for nothing is unknown."""
    verdicts = {str(entry.get("fidelity")) for entry in fonts.values()}
    if not verdicts or "substituted" in verdicts:
        return "unknown_substitution"
    return "metric_substituted" if "metric_alias" in verdicts else "faithful"


# --- the pipeline ------------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(
    deck_path: Path,
    out: Path,
    width: int,
    guide_path: Path | None,
    pool_max: int = GALLERY_POOL_MAX,
    exemplar_max: int = EXEMPLAR_POOL_MAX,
) -> dict[str, object]:
    deck = join_deck(deck_path)
    gutter, evidence = read_guide(guide_path) if guide_path else (None, {})
    gap_emu = component_gap_emu(gutter)
    # Plain LibreOffice export omits hidden slides, so the page sequence is the
    # visible slides in sldIdLst order, and the count must agree exactly.
    shown = [slide for slide in deck.slides if not slide.hidden]
    pair_count = sum(len(content_leaves(s)) * (len(content_leaves(s)) - 1) // 2 for s in shown)
    if pair_count > MAX_SHAPE_PAIRS:
        raise GalleryRefused("too_many_shape_pairs", f"{pair_count} shape pairs to group against {MAX_SHAPE_PAIRS}")

    pages, fonts = render_pages(deck_path, out / "pages", width)
    if len(pages) != len(shown):
        raise GalleryRefused("page_count_mismatch", f"{len(pages)} rendered pages against {len(shown)} visible slides")
    page_of = {slide.index: page for slide, page in zip(shown, pages, strict=True)}
    fidelity = render_fidelity(fonts)
    with Image.open(pages[0]) as first:
        raster_w, raster_h = first.size
    # The raster preserves the page aspect and a pixel is square, so one scale
    # serves both axes; the floor and the pad are judged on the image actually sent.
    emu_per_px = deck.width_emu / raster_w
    pad_floor = math.ceil(CROP_PAD_MIN_RASTER_PX * emu_per_px)

    found = components(deck, shown, gap_emu)
    if not found:
        raise GalleryRefused("no_components", "the deck declares no content shapes to crop")
    if len(found) > MAX_COMPONENTS:
        raise GalleryRefused("too_many_components", f"{len(found)} components against {MAX_COMPONENTS}")
    groups = [normalized_members(c) for c in found]
    labels = [member_labels(c) for c in found]
    boxes = [crop_box(c, pad_floor, deck) for c in found]
    survives = [is_substantive(c) and is_legible(boxes[i], emu_per_px) for i, c in enumerate(found)]
    clusters = leader_clusters(groups, labels=labels, threshold=COMPONENT_SIMILARITY_TAU)
    chosen = select(found, clusters, groups, labels, lambda i: survives[i], pool_max, evidence)
    if not chosen:
        raise GalleryRefused("no_crops", f"{len(found)} components, none both substantive and {MIN_CROP_AREA_PX} px in area")

    for generated in ("crops", "exemplars"):
        shutil.rmtree(out / generated, ignore_errors=True)
        (out / generated).mkdir(parents=True)
    crops: list[dict[str, object]] = []
    crop_rows: list[str] = []
    for position, candidate in enumerate(chosen):
        component, box = candidate.component, boxes[candidate.index]
        gallery_id = f"crop-{position + 1:02d}"
        target = out / "crops" / f"{gallery_id}.png"
        size = cut(page_of[component.slide.index], box, deck, target)
        text = caption(candidate, box)
        crops.append(
            {
                "gallery_id": gallery_id,
                "file": f"crops/{gallery_id}.png",
                "sha256": _sha256(target),
                "pixel_size": list(size),
                "source_slide_index": component.slide.index,
                "slide_render_file": f"pages/{page_of[component.slide.index].name}",
                "crop_box_emu": dict(zip(("left", "top", "width", "height"), box, strict=True)),
                "caption": text,
                "categories": list(candidate.categories),
                "cluster_id": f"comp-{candidate.cluster + 1}",
                "occurrences": candidate.occurrences,
                "members": [leaf.ref for leaf in component.members],
            }
        )
        crop_rows.append(
            f"| `{gallery_id}` | {component.slide.index + 1} | {', '.join(candidate.categories)} | {candidate.occurrences} | {text} |"
        )
    exemplars: list[dict[str, object]] = []
    exemplar_rows: list[str] = []
    for family_index, slide, family_size in select_exemplars(shown, exemplar_max):
        exemplar_id = f"ex-{family_index + 1:02d}"
        png = out / "exemplars" / f"{exemplar_id}.png"
        shutil.copyfile(page_of[slide.index], png)
        skeleton_path = out / "exemplars" / f"{exemplar_id}.skeleton.json"
        skeleton_path.write_text(json.dumps(skeleton(slide, deck), indent=2, sort_keys=True) + "\n")
        exemplars.append(
            {
                "exemplar_id": exemplar_id,
                "render_file": f"exemplars/{exemplar_id}.png",
                "skeleton_file": f"exemplars/{exemplar_id}.skeleton.json",
                "render_sha256": _sha256(png),
                "slide_family": f"family-{family_index + 1}",
                "cluster_id": f"arch-{family_index + 1}",
                "family_size": family_size,
                "source_slide_index": slide.index,
            }
        )
        exemplar_rows.append(f"| `{exemplar_id}` | {slide.index + 1} | `family-{family_index + 1}` | {family_size} |")
    totals = {
        "slides": len(deck.slides),
        "hidden_slides": len(deck.slides) - len(shown),
        "components": len(found),
        "candidates": sum(survives),
        "clusters": len(clusters),
        "crops": len(crops),
        "families": len(slide_families(shown)),
        "exemplars": len(exemplars),
    }
    # No wall-clock timestamp: a rebuild that changed nothing is an empty diff.
    manifest: dict[str, object] = {
        "schema_version": 2,
        "producer": "pptx-skill/scripts/gallery.py (port of deckgen style/gallery.py)",
        "reference": deck_path.name,
        "reference_sha256": _sha256(deck_path),
        "render_fidelity": fidelity,
        "fonts": fonts,
        "raster": {"width_px": raster_w, "height_px": raster_h, "emu_per_px": emu_per_px},
        "parameters": {
            "component_gap_emu_ceiling": COMPONENT_GAP_EMU,
            "component_similarity_tau": COMPONENT_SIMILARITY_TAU,
            "crop_pad_min_raster_px": CROP_PAD_MIN_RASTER_PX,
            "motif_min_occurrences": MOTIF_MIN_OCCURRENCES,
            "min_crop_area_px": MIN_CROP_AREA_PX,
            "gallery_pool_max": pool_max,
            "exemplar_pool_max": exemplar_max,
            "guide": str(guide_path) if guide_path else None,
            "mined_gutter_emu": gutter,
        },
        "totals": totals,
        "component_gap_emu_used": gap_emu,
        "crops_per_slide": dict(sorted(Counter(c.component.slide.index + 1 for c in chosen).items())),
        "crops": crops,
        "exemplars": exemplars,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "MANIFEST.md").write_text(manifest_markdown(manifest, totals, fonts, crop_rows, exemplar_rows))
    return manifest


def manifest_markdown(
    manifest: dict[str, object],
    totals: dict[str, int],
    fonts: dict[str, dict[str, object]],
    crop_rows: list[str],
    exemplar_rows: list[str],
) -> str:
    """The gallery in words, so a reader can choose which images to look at."""
    fidelity = str(manifest["render_fidelity"])
    fields = (
        ("reference sha256", f"`{manifest['reference_sha256']}`"),
        ("render fidelity", f"`{fidelity}`"),
        ("slides / hidden", f"{totals['slides']} / {totals['hidden_slides']}"),
        ("components", str(totals["components"])),
        ("candidates after the two filters", str(totals["candidates"])),
        ("clusters / crops", f"{totals['clusters']} / {totals['crops']}"),
        ("families / exemplars", f"{totals['families']} / {totals['exemplars']}"),
        ("component gap used", f"{manifest['component_gap_emu_used']} EMU"),
    )
    lines = [
        f"# Gallery: {manifest['reference']}",
        "",
        "Cropped renders of the deck's components and one whole-slide exemplar per",
        "composition family, selected by geometry alone. Nothing here is a design",
        "standard: a crop shows arrangement the numeric guide cannot state, nothing more.",
        "",
        "| Field | Value |",
        "|---|---|",
        *(f"| {label} | {value} |" for label, value in fields),
        "",
        FIDELITY_NOTES[fidelity],
        "",
        "| declared font | rendered with | fidelity |",
        "|---|---|---|",
        *(f"| {face} | {entry['rendered_with']} | {entry['fidelity']} |" for face, entry in fonts.items()),
        "",
        "## Crops",
        "",
        "| id | slide | labels | occurrences | caption |",
        "|---|---|---|---|---|",
        *crop_rows,
        "",
        "## Exemplars",
        "",
        "| id | slide | family | slides in family |",
        "|---|---|---|---|",
        *exemplar_rows,
        "",
        "Each exemplar is a whole-slide PNG plus a `.skeleton.json` of leaf boxes in EMU with kind,",
        "role and run count and NO document text. Each crop row in manifest.json names the full-page",
        "render it was cut from (`slide_render_file`).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    for a in argv:
        if a.lower().endswith(".pdf"):
            print("gallery.py reads .pptx only: for a PDF reference look at the page renders (render.py) and the triage table (ooxml.py triage); the crops a PDF could give are its pages")
            return 2
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1600, help="raster width in pixels (default 1600)")
    ap.add_argument("--guide", default=None, help="extract_style.py guide JSON: mined gutter and token evidence")
    ap.add_argument("--pool-max", type=int, default=GALLERY_POOL_MAX)
    ap.add_argument("--exemplar-max", type=int, default=EXEMPLAR_POOL_MAX)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        manifest = build(
            Path(args.deck).resolve(), out, args.width, Path(args.guide) if args.guide else None, args.pool_max, args.exemplar_max
        )
    except GalleryRefused as refused:
        print(json.dumps({"refused": refused.reason, "detail": str(refused)}), file=sys.stderr)
        return 2
    print(json.dumps({"out": str(out), "render_fidelity": manifest["render_fidelity"], "totals": manifest["totals"]}, indent=1))
    if manifest["render_fidelity"] != "faithful":
        print(f"WARNING: render fidelity is {manifest['render_fidelity']}; see MANIFEST.md before reading letterforms", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
