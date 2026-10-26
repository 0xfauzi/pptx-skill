#!/usr/bin/env python3
"""Style fingerprint of a .pptx, and the distance between fingerprints.

The outside judge for style adherence. It reads OOXML directly (zipfile + lxml,
nothing else) and resolves inherited text and shape properties through the
slide -> layout -> master -> theme chain, so a deck that declares Arial 12pt once
on its master and a deck that writes it on every run fingerprint the same.

    fingerprint.py print  deck.pptx                      # per-deck summary
    fingerprint.py compare cand.pptx --reference ref.pptx [--others a.pptx ...]
    fingerprint.py calibrate house1=a.pptx,b.pptx house2=c.pptx ...  [--json out]
    fingerprint.py calibrate --houses-file oracles/calibration-houses.txt --corpus-root CORPUS \
                   --max-pages 25 --fit-weights        # the corpus DEFAULT_WEIGHTS was scored on

`compare` prints every distance component, so a bad component names the defect
(sizes off the reference ladder, a colour outside the palette, margins wrong).
`calibrate` runs leave-one-slide-out and leave-one-deck-out 1-nearest-neighbour
over the houses given and prints accuracy against the binomial chance bound: it
is how the measure itself is checked before it judges anything.

The style walker (inheritance order, colour transforms) is ported, with the
port audit in ../PORT_AUDIT.md. No value in here is a design standard.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ooxml import SlidePrint, delta_e, fingerprint_deck, is_type_evidence  # noqa: E402



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
    overlap: list[float] = field(default_factory=list)  # per slide: intersecting area among content shapes over their area
    overflow: list[float] = field(default_factory=list)  # per slide: share of measured text shapes whose text outgrows the box

    def add(self, other: "Features") -> None:
        for name in ("families", "sizes", "title_sizes", "text_colors", "fills", "lines", "aligns", "kinds", "prsts", "backgrounds", "chrome_boxes"):
            getattr(self, name).update(getattr(other, name))
        self.bold_chars += other.bold_chars
        self.chars += other.chars
        self.margins.extend(other.margins)
        self.counts.extend(other.counts)
        self.coverage.extend(other.coverage)
        self.overlap.extend(other.overlap)
        self.overflow.extend(other.overflow)


_MEASURE: dict = {}


def _measurer():
    """The ruler and face index, built once: overflow is measured with the same ruler the
    solver uses, so a page the solver fitted never reads as overflowing here."""
    if not _MEASURE:
        from textfit import default_index, default_ruler, measure_text
        _MEASURE["ruler"], _MEASURE["index"], _MEASURE["measure"] = default_ruler(), default_index(), measure_text
    return _MEASURE["ruler"], _MEASURE["index"], _MEASURE["measure"]


CONTENT_KINDS = ("text_box", "text_shape", "table", "chart", "picture")


def overlap_rate(s: SlidePrint, chrome_keys: set) -> float | None:
    """Pairwise intersection area among content shapes over their summed area. Text over
    text, text over a table or a chart, is a defect on every reference measured; a text
    box inside a filled rectangle is one shape in this reader, so it does not count."""
    boxes = []
    for sh in s.shapes:
        if sh.box and sh.kind in CONTENT_KINDS and sh.box[2] > 0 and sh.box[3] > 0 and (sh.kind, _quant(sh.box, s.width, s.height)) not in chrome_keys:
            if sh.kind in ("text_box", "text_shape") and not sh.text_chars:
                continue
            boxes.append(sh.box)
    if len(boxes) < 2:
        return 0.0 if boxes else None
    total = sum(b[2] * b[3] for b in boxes)
    inter = 0
    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
            h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            if w > 0 and h > 0:
                inter += w * h
    return min(1.0, inter / total) if total else None


#: The build's emitted-file check forgives what the solver's own emit gate forgives
#: between two measurements of the same text (layout.EMIT_SLACK_EMU, deckgen tolerance.py).
STRICT_SLACK_EMU = 13


def _pitch_emu(para: dict, size_pt: float) -> float:
    """The line pitch the file draws: lnSpc spcPts as written (negative from the reader),
    spcPct as a share of single spacing (1.2 x size, E16), else single spacing."""
    ls = para.get("line_spacing")
    if ls is None:
        return size_pt * 1.2 * 12700
    return (-ls if ls < 0 else ls * 1.2 * size_pt) * 12700


def _spacing_emu(value: float, size_pt: float) -> float:
    return (value if value >= 0 else -value * 1.2 * size_pt) * 12700


def text_overflows(s: SlidePrint, *, strict: bool = False, substitutes: dict | None = None) -> tuple[list[dict], list[dict], int]:
    """Every text shape on the slide whose paragraphs, wrapped by wrap_shape, need more
    height than the box holds. Returns (findings, unmeasured, measured count); each
    finding names the slide, the shape and its lines, so a rate is never the only answer.

    strict (the build's check of its own file): a written line must stay one line at the
    width less the ruler's fit epsilon (the solver wrapped at exactly that), the slack is
    the emit gate's, and a face is measured as the guide's substitute for it. Not strict
    (the judge, on any deck): half a line of slack and the renderer's face for a family the
    sandbox lacks. Shapes under autofit and furniture placeholders are skipped in both."""
    findings: list[dict] = []
    unmeasured: list[dict] = []
    measured = 0
    for sh in s.shapes:
        if not sh.box or sh.kind not in ("text_box", "text_shape") or not sh.paragraphs:
            continue
        if sh.ph_type in ("sldNum", "ftr", "dt"):
            continue  # furniture in a box PowerPoint lets a line overhang; never content
        if sh.text_wrap == "none":
            continue  # one line that never wraps (drawn chrome, a turned copyright line): it overhangs its box by design
        runs = [r for p in sh.paragraphs for r in p["runs"] if not r.get("br")]
        if not runs:
            continue
        where = {"slide": s.index + 1, "shape": sh.name, "ref": sh.ref}
        width, budget = _inner_box(sh, strict)
        if width <= 0 or budget <= 0:
            unmeasured.append({**where, "why": f"inner box {width} x {budget} EMU"})
            continue
        if any(r.size_layer == "autofit" for r in s.runs if r.ref.startswith(sh.ref)):
            continue
        got = wrap_shape(s, sh, strict=strict, substitutes=substitutes)
        if "why" in got:
            unmeasured.append({**where, "why": got["why"]})
            continue
        measured += 1
        slack = STRICT_SLACK_EMU if strict else 0.5 * got["pitch_emu"]
        if got["needed_emu"] > budget + slack or got["rewrapped"]:
            findings.append({**where, "needed_emu": round(got["needed_emu"]), "budget_emu": budget, "lines": got["lines"],
                             **({"rewrapped_lines": got["rewrapped"]} if got["rewrapped"] else {})})
    return findings, unmeasured, measured


def _inner_box(sh, strict: bool) -> tuple[int, int]:
    """(width, height) inside the shape's insets; strict narrows the width by the ruler's
    fit epsilon, the width the solver wrapped at."""
    ruler = _measurer()[0]
    lin, tin, rin, bin_ = sh.text_inset_emu or (91440, 45720, 91440, 45720)
    return sh.box[2] - lin - rin - (ruler.fit_epsilon_emu if strict else 0), sh.box[3] - tin - bin_


def wrap_shape(s: SlidePrint, sh, *, strict: bool = False, substitutes: dict | None = None) -> dict:
    """One text shape's paragraphs wrapped at its inner width (less marL) with the solver's
    ruler: {"lines", "needed_emu", "rewrapped", "pitch_emu"}, or {"why"} when it cannot be
    measured. Height is what the file draws: lines at the paragraph's own pitch, plus every
    spcBef and spcAft in strict mode (what the solver charges). strict also measures a face
    as the guide's substitute for it; not strict, a family the sandbox lacks is measured in
    the renderer's face."""
    ruler, index, measure = _measurer()
    from textfit import resolve_measured
    width, budget = _inner_box(sh, strict)
    if width <= 0 or budget <= 0:
        return {"why": f"inner box {width} x {budget} EMU"}
    needed = 0.0
    pitch = 0.0
    lines: list[str] = []
    rewrapped: list[str] = []
    drawn = [para for para in sh.paragraphs if any(not r.get("br") for r in para["runs"])]
    for para in drawn:
        real = [r for r in para["runs"] if not r.get("br")]
        lead = real[0]
        text = "".join(r["text"] for r in para["runs"])
        pitch = _pitch_emu(para, lead["size_pt"])
        if strict:  # what the solver charges: every spcBef and spcAft
            needed += _spacing_emu(para.get("space_before") or 0.0, lead["size_pt"]) + _spacing_emu(para.get("space_after") or 0.0, lead["size_pt"])
        if not text.strip():
            needed += pitch
            continue
        family = lead.get("family") or next((r.family for r in s.runs if r.ref.startswith(sh.ref) and r.family), None)
        if not family:
            return {"why": "no face declared or inherited"}
        try:
            face = resolve_measured(index, family, bold=bool(lead["bold"]), italic=bool(lead["italic"]),
                                    substitute=(substitutes or {}).get(family), renderer_ok=not strict)
        except LookupError as error:
            return {"why": str(error)}
        for segment in text.split("\n"):
            if not segment.strip():
                needed += pitch
                continue
            got = measure(ruler, segment, max(1, width - int(para.get("mar_l_emu") or 0)), face.path, lead["size_pt"])
            if strict and len(got) > 1:
                rewrapped.append(segment)
            lines.extend(ln.text for ln in got)
            needed += len(got) * pitch
    return {"lines": lines, "needed_emu": needed, "rewrapped": rewrapped, "pitch_emu": pitch}


def overflow_rate(s: SlidePrint) -> float | None:
    """Share of measured text shapes text_overflows finds outgrowing their box."""
    findings, _, measured = text_overflows(s)
    return len(findings) / measured if measured else None


def slide_features(s: SlidePrint) -> Features:
    """A raster PDF page (ooxml.is_type_evidence) yields empty features: its text layer is
    a wrapper or OCR, and its rects and lines are the print around the image."""
    f = Features()
    if not is_type_evidence(s):
        return f
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
        ov = overlap_rate(s, chrome_keys)
        if ov is not None:
            f.overlap.append(ov)
        of = overflow_rate(s)
        if of is not None:
            f.overflow.append(of)
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
    "overlap", "overflow",
)


def excess(cand: list, house: list, span: float) -> float | None:
    """How much worse the candidate's defect rate is than the house's own, over `span`.
    A house is allowed its own rate; only the excess counts, and only upward."""
    if not cand or not house:
        return None
    return min(1.0, max(0.0, sum(cand) / len(cand) - sum(house) / len(house)) / span)


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
        "overlap": excess(cand.overlap, house.overlap, 0.10),
        "overflow": excess(cand.overflow, house.overflow, 0.25),
    }
    return out


DEFAULT_WEIGHTS: dict[str, float] = {
    "families": 0.4427, "size_hist": 0.3281, "size_ladder": 0.5365, "title_size": 0.8105,
    "bold_ratio": 0.1354, "text_colors": 0.651, "fills": 0.7171, "lines": 0.7648,
    "aligns": 0.4386, "kinds": 0.5295, "background": 0.0823, "margins": 0.2668,
    "coverage": 0.0245, "count": 0.3295,
    "overlap": 1.0, "overflow": 1.0,
}
"""Per-component weight = that component's 1-NN accuracy above chance, FITTED on the
even-numbered slides of the eight houses in ../oracles/calibration-houses.txt (gs: 3
Mergers & Inquisitions pitch books; header and themes: the 2 Apache POI test decks, one
house each; taste: 20 taste-spike slides; mckinsey: 6, bcg: 3, bain: 1, jpm: 1 public
PDFs; 25 pages each, raster pages not scored) and JUDGED on the odd-numbered slides.

These shipped weights, re-scored on 2026-10-20 with the command in the module docstring:
152/165 odd slides correct, against 132/165 with equal weights, chance bound 29. The
same run re-fits weights on the even slides (families 0.4331, count 0.2083, ...: the
`fitted_weights_on_even_slides` it prints) and those score 151/165, so the shipped set
is kept. Before raster pages left the scoring (ooxml.is_type_evidence), 6 OCR pages were
scored as type and the figures were 158/171 shipped, 157/171 fitted, 132/171 equal.
Re-fit when the corpus changes; never tune on the slides being judged.

`overlap` and `overflow` are not the fitted values: the same fit gives them 0.4083 and
0.4464 (the reference decks differ a little in their own overlap and overflow rates).
They are ASSERTED at 1.0, above the largest fitted weight, because the review of
2026-10-20 built decks a rater calls wrong (keybank's shapes at random positions:
0.013; all stacked at one point: 0.044; nine random boxes per page: 0.122; every text
box overflowing twelve times over: 0.192) and the fourteen style components filed every
one under keybank. Separating houses is not their job; reading whether the page is laid
out at all is, and DEFECT_GATE holds that line on its own."""


def total(d: dict[str, float | None], weights: dict[str, float] | None = None) -> float:
    weights = DEFAULT_WEIGHTS if weights is None else weights
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


def calibrate(houses: dict[str, list[str]], weights: dict[str, float] | None = None, max_pages: int | None = None,
              by_deck: bool = False, split: str | None = None) -> dict:
    """Leave-one-out 1-NN over houses. `by_deck` makes every deck its own class (the
    skill's real question: does this slide belong to THIS reference deck?). `split`
    is 'even' or 'odd': only slides with that parity are scored, so weights fitted on
    one half can be judged on the other."""
    prints: dict[str, dict[str, list[SlidePrint]]] = {}
    for house, decks in houses.items():
        for deck in decks:
            slides = fingerprint_deck(deck, max_pages)
            # a deck class is keyed by house and path, never by file stem: four taste decks
            # named slide1.pptx once collapsed into one class and a BCG page was filed under it
            key = f"{house}/{Path(deck).as_posix()}" if by_deck else house
            prints.setdefault(key, {})[deck] = slides
    house_feats = {h: house_features([s for d in decks.values() for s in d]) for h, decks in prints.items()}
    n_classes = len(prints)

    deck_rank: dict[str, int] = {}
    for house, decks in prints.items():
        for i, deck in enumerate(decks):
            deck_rank[deck] = i

    def scored(s: SlidePrint, deck: str = "", single: bool = False) -> bool:
        # a single-slide deck has only slide 0: its parity is the deck's rank in the house,
        # so a house of single-slide decks is split too (the taste house was never judged)
        if split is None:
            return True
        parity = deck_rank.get(deck, 0) if single else s.index
        return (parity % 2 == 0) == (split == "even")

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
                if not scored(s, deck, len(slides) == 1) or not is_type_evidence(s):
                    continue  # a raster page has no features to file: scoring it files a tie
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
            if not scorable(df):
                continue
            pred, scores = predict(df, house, df)
            lodo.append({"house": house, "deck": deck, "pred": pred, "scores": scores})
    return {
        "n_slides": n,
        "n_houses": n_classes,
        "by_deck": by_deck,
        "split": split,
        "weights": weights,
        "slide_loo_correct": correct,
        "slide_loo_accuracy": correct / n if n else None,
        "n_houses_judged": len({r["house"] for r in per_slide}),
        "chance_bound_k": binomial_bound(n, max(2, len({r["house"] for r in per_slide}))),
        "per_component_accuracy": {c: (per_component_correct[c] / per_component_n[c] if per_component_n[c] else None) for c in COMPONENTS},
        "confusion": {f"{a}->{b}": v for (a, b), v in sorted(confusion.items())},
        "leave_one_deck_out": lodo,
        "per_slide": per_slide,
    }


DEFECT_GATE = 0.2
"""A defect component past this share of its span fails the page outright: overlap over
2% of the content area, or more than 5% of text shapes overflowing. Averaged into the
distance these would still let a page of keybank's shapes at random positions (overlap
1.0) sit at 0.134, nearer keybank than jazz; a gate is the only honest reading of a
measurement that says the page is not laid out."""


def layout_clean(components: dict) -> bool:
    return all((components.get(k) or 0.0) < DEFECT_GATE for k in ("overlap", "overflow"))


def house_spread(slides: list[SlidePrint]) -> dict | None:
    """How far the reference's own slides sit from the rest of the reference (leave one
    out). A candidate inside this spread is as much the house as the house's own pages;
    one outside it is not, however near it sits to the other decks on the panel (a page
    of keybank's shapes at random positions is nearer keybank than jazz and still wrong)."""
    slides = [s for s in slides if is_type_evidence(s)]
    if len(slides) < 3:
        return None
    feats = [slide_features(s) for s in slides]
    whole = Features()
    for f in feats:
        whole.add(f)
    dists = []
    for f in feats:
        rest = Features()
        rest.add(whole)
        _subtract(rest, f)
        dists.append(total(distance(f, rest)))
    dists.sort()
    n = len(dists)
    return {"n": n, "min": round(dists[0], 3), "median": round(dists[n // 2], 3), "p90": round(dists[min(n - 1, int(0.9 * (n - 1)))], 3), "max": round(dists[-1], 3)}


def panel(others: list[str], reference: str) -> list[str]:
    """The comparison panel. Given explicitly, it is used as given; otherwise every deck
    under refs/files (the public references refs/fetch.sh collects) except the reference
    itself, because a pass against two alien decks and a fail against the reference's
    sister decks is the same deck, and the agent must not be the one choosing."""
    if others:
        return list(others)
    import hashlib
    root = Path(__file__).resolve().parent.parent / "refs" / "files"
    ref_sha = hashlib.sha256(Path(reference).read_bytes()).hexdigest()
    found = []
    for p in sorted(root.glob("*")):
        if p.suffix.lower() not in (".pptx", ".pdf"):
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() == ref_sha:
            continue  # the reference under another name is not another house
        found.append(str(p))
    return found


def same_house(other: Features, reference: Features, spread: dict | None) -> bool:
    """A panel deck that sits inside the reference's own spread is the same house in
    another file (the three Mergers & Inquisitions books carry one fictional bank on one
    master: keybank to netflix is 0.077 against keybank's own slides at 0.055 to 0.372).
    It cannot be a rival in the nearest test; it is reported as the same house."""
    if not spread:
        return False
    return total(distance(other, reference)) <= spread["p90"]


def scorable(house: Features) -> bool:
    """A house with no measured type (a scan, an empty deck) cannot be a neighbour: every
    style component is None against it and the distance collapses to the few that remain."""
    return house.chars > 0


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
    for name in ("overlap", "overflow"):
        tgt = getattr(target, name)
        for c in getattr(part, name):
            if c in tgt:
                tgt.remove(c)


def fit_weights(houses: dict[str, list[str]], max_pages: int | None, by_deck: bool) -> dict[str, float]:
    """Weights from per-component 1-NN accuracy on EVEN slides only: a component
    that beats chance by a margin gets that margin as its weight, one that does not
    gets zero. Judge them on the ODD slides, never on the slides they were fitted on."""
    fit = calibrate(houses, {k: 1.0 for k in COMPONENTS}, max_pages, by_deck, split="even")
    chance = 1.0 / fit["n_houses"]
    out = {}
    for comp, acc in fit["per_component_accuracy"].items():
        out[comp] = round(max(0.0, (acc or 0.0) - chance), 4)
    return out


# --- the judge -------------------------------------------------------------------------------

PANEL_PAGES = 25
RENDITION_WORD_OVERLAP = 0.9
"""Two files whose words (3+ letters, first PANEL_PAGES pages) overlap at least this much
(Jaccard) are one deck in two formats: the jazz book as PDF and as pptx share 0.992 of
their words, while every other pair of panel decks shares under 0.2 (2026-10-20)."""


def deck_words(slides: list[SlidePrint]) -> set[str]:
    import re
    return {w for s in slides for r in s.runs for w in re.findall(r"[a-z0-9]{3,}", (r.text or r.text_sample or "").lower())}


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0
"""Pages read per panel deck: PDF references run to hundreds of pages and the panel is a
dozen decks; the reference and the candidate are read whole."""


def judge(candidate: str, reference: str, others: list[str] | None = None, ref_slides: list[SlidePrint] | None = None,
          max_pages: int | None = None) -> dict:
    """The candidate's distance to the reference and to every panel deck, with the gates the
    verdict needs (nearest, within the house's own spread, layout clean). A reference with
    no type evidence (a scan, a browser print, an OCR layer: ooxml.is_type_evidence) cannot
    be judged by this instrument, and the result says so instead of a distance: its only
    "type" is the OCR layer, and every faithful deck would sit far from it."""
    ref_slides = ref_slides if ref_slides is not None else fingerprint_deck(reference, max_pages)
    ref = house_features(ref_slides)
    out: dict = {"reference": reference}
    if not scorable(ref):
        raster = [s.index + 1 for s in ref_slides if not is_type_evidence(s)]
        out["cannot_judge"] = (f"the reference carries no type evidence: {len(raster)} of {len(ref_slides)} pages are raster "
                               "(ooxml.pdf_triage) and their text layer is a wrapper or OCR, not the house's type. "
                               "Judge style against the raster evidence (raster_style.py) and the renders by eye.")
        out["raster_pages"] = raster
        return out
    cand = fingerprint_deck(candidate, max_pages)
    cf = house_features(cand)
    d = distance(cf, ref)
    out["total"] = round(total(d), 3)
    out["components"] = {k: (round(v, 3) if v is not None else None) for k, v in d.items()}
    per_slide = []
    for s in cand:
        sd = distance(slide_features(s), ref)
        worst = sorted(((v, k) for k, v in sd.items() if v is not None), reverse=True)[:3]
        per_slide.append({"slide": s.index + 1, "total": round(total(sd), 3), "worst": [(k, round(v, 3)) for v, k in worst]})
    out["per_slide"] = per_slide
    # the shapes behind the overflow component, by page and shape name
    out["overflow_where"] = [f for s in cand for f in text_overflows(s)[0]]
    spread = house_spread(ref_slides)
    out["house_spread"] = spread
    rivals, kin, skipped, renditions = {}, {}, [], {}
    ref_words = deck_words(ref_slides[:PANEL_PAGES])
    words: dict[str, set[str]] = {}
    for o in panel(others or [], reference):
        o_slides = fingerprint_deck(o, PANEL_PAGES)
        words[o] = deck_words(o_slides)
        if _overlap(words[o], ref_words) >= RENDITION_WORD_OVERLAP:
            renditions[o] = "the reference in another format"  # panel() drops a byte-identical copy; this is the same deck printed
            continue
        hf = house_features(o_slides)
        if not scorable(hf):
            skipped.append(o)
            continue
        if same_house(hf, ref, spread):
            kin[o] = round(total(distance(cf, hf)), 3)
            continue
        rivals[o] = round(total(distance(cf, hf)), 3)
    # a rival that is a kin deck in another format (a PDF print of a sister pptx) is that
    # deck: a print reads farther from the reference than its source (PDF blocks hug their
    # glyphs where a pptx box keeps its insets), so its house is the source's
    for o in list(rivals):
        twin = next((k for k in kin if _overlap(words[o], words[k]) >= RENDITION_WORD_OVERLAP), None)
        if twin is not None:
            kin[o] = rivals.pop(o)
            renditions[o] = f"{twin} in another format"
    if renditions:
        out["renditions"] = renditions
    out["others"] = rivals
    if skipped:
        out["panel_skipped"] = {"reason": "no type evidence (a scan, a browser print or an empty deck)", "files": skipped}
    out["same_house_on_panel"] = kin
    out["panel"] = "given" if others else "refs/files (default)"
    out["nearest_is_reference"] = all(out["total"] < v for v in rivals.values()) if rivals else None
    out["reference_rank"] = 1 + sum(1 for v in rivals.values() if v <= out["total"]) if rivals else None
    out["within_house_spread"] = out["total"] <= spread["p90"] if spread else None
    out["layout_clean"] = layout_clean(d)
    return out


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
    s_cal.add_argument("houses", nargs="*", help="name=deck1.pptx,deck2.pdf,...")
    s_cal.add_argument("--houses-file", default=None, help="one name=deck,deck,... per line (# comments); paths under refs/ resolve against this repo, others against --corpus-root")
    s_cal.add_argument("--corpus-root", default=".", help="where the relative corpus paths of --houses-file live (a checkout holding the calibration corpus)")
    s_cal.add_argument("--json")
    s_cal.add_argument("--max-pages", type=int, default=None, help="cap pages read per file (PDF references can run to hundreds)")
    s_cal.add_argument("--by-deck", action="store_true", help="every deck is its own class")
    s_cal.add_argument("--fit-weights", action="store_true", help="fit component weights on even slides, judge on odd slides, and print both")
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "json")

    if args.cmd == "print":
        slides = fingerprint_deck(args.deck, args.max_pages)
        print(json.dumps({"deck": args.deck, "slides": len(slides), "house": summarise(house_features(slides))}, indent=1))
        if args.per_slide:
            for s in slides:
                print(json.dumps({"slide": s.index + 1, **summarise(slide_features(s))}))
        return 0
    if args.cmd == "compare":
        report = judge(args.candidate, args.reference, args.others, max_pages=args.max_pages)
        text = json.dumps(report, indent=1, default=str)
        print(text)
        if args.json:
            Path(args.json).write_text(text)
        return 0
    if args.cmd == "calibrate":
        houses = {}
        specs = list(args.houses)
        if args.houses_file:
            repo = Path(__file__).resolve().parent.parent
            for line in Path(args.houses_file).read_text().splitlines():
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                name, _, decks = line.partition("=")
                paths = [str(repo / d) if d.startswith("refs/") else str(Path(args.corpus_root) / d) for d in decks.split(",")]
                specs.append(f"{name}={','.join(paths)}")
        if not specs:
            raise SystemExit("calibrate: no houses (give name=decks or --houses-file)")
        for spec in specs:
            name, _, decks = spec.partition("=")
            houses[name] = decks.split(",")
        if args.fit_weights:
            weights = fit_weights(houses, args.max_pages, args.by_deck)
            equal = calibrate(houses, {k: 1.0 for k in COMPONENTS}, args.max_pages, args.by_deck, split="odd")
            fitted = calibrate(houses, weights, args.max_pages, args.by_deck, split="odd")
            shipped = calibrate(houses, DEFAULT_WEIGHTS, args.max_pages, args.by_deck, split="odd")
            brief = ("n_slides", "n_houses", "slide_loo_correct", "slide_loo_accuracy", "chance_bound_k")
            result = {
                "houses": {h: len(d) for h, d in houses.items()},
                "fitted_weights_on_even_slides": weights,
                "odd_slides_equal_weights": {k: v for k, v in equal.items() if k in brief},
                "odd_slides_fitted_weights": {k: v for k, v in fitted.items() if k in brief},
                # the weights the judge ships with, scored on the same odd slides: the figure the docs quote
                "odd_slides_shipped_weights": {k: v for k, v in shipped.items() if k in brief},
                "odd_confusion_fitted": fitted["confusion"],
                "leave_one_deck_out_fitted": fitted["leave_one_deck_out"],
            }
            print(json.dumps(result, indent=1, default=str))
            if args.json:
                Path(args.json).write_text(json.dumps(result, indent=1, default=str))
            return 0
        result = calibrate(houses, max_pages=args.max_pages, by_deck=args.by_deck)
        brief = {k: v for k, v in result.items() if k != "per_slide"}
        print(json.dumps(brief, indent=1, default=str))
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=1, default=str))
        return 0
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
