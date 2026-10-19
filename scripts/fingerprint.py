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
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ooxml import SlidePrint, delta_e, fingerprint_deck  # noqa: E402



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


DEFAULT_WEIGHTS: dict[str, float] = {
    "families": 0.4427, "size_hist": 0.3281, "size_ladder": 0.5365, "title_size": 0.8105,
    "bold_ratio": 0.1354, "text_colors": 0.651, "fills": 0.7171, "lines": 0.7648,
    "aligns": 0.4386, "kinds": 0.5295, "background": 0.0823, "margins": 0.2668,
    "coverage": 0.0245, "count": 0.3295,
}
"""Per-component weight = that component's 1-NN accuracy above chance, FITTED on the
even-numbered slides of an eight-house corpus (3 Mergers & Inquisitions pitch books,
2 Apache POI test decks, 20 taste-spike slides, 6 McKinsey + 3 BCG + 1 Bain + 1 JPM
public PDFs, 25 pages each) and JUDGED on the odd-numbered slides: 147/161 correct
against 122/161 with equal weights, chance bound 28. Re-fit with
`fingerprint.py calibrate ... --fit-weights` when the corpus changes; never tune on
the slides being judged."""


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
            key = Path(deck).stem if by_deck else house
            prints.setdefault(key, {})[deck] = slides
    house_feats = {h: house_features([s for d in decks.values() for s in d]) for h, decks in prints.items()}
    n_classes = len(prints)

    def scored(s: SlidePrint) -> bool:
        return split is None or (s.index % 2 == 0) == (split == "even")

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
                if not scored(s):
                    continue
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
        "by_deck": by_deck,
        "split": split,
        "weights": weights,
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
    s_cal.add_argument("--by-deck", action="store_true", help="every deck is its own class")
    s_cal.add_argument("--fit-weights", action="store_true", help="fit component weights on even slides, judge on odd slides, and print both")
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
        if args.fit_weights:
            weights = fit_weights(houses, args.max_pages, args.by_deck)
            equal = calibrate(houses, {k: 1.0 for k in COMPONENTS}, args.max_pages, args.by_deck, split="odd")
            fitted = calibrate(houses, weights, args.max_pages, args.by_deck, split="odd")
            result = {
                "fitted_weights_on_even_slides": weights,
                "odd_slides_equal_weights": {k: v for k, v in equal.items() if k in ("n_slides", "n_houses", "slide_loo_correct", "slide_loo_accuracy", "chance_bound_k")},
                "odd_slides_fitted_weights": {k: v for k, v in fitted.items() if k in ("n_slides", "n_houses", "slide_loo_correct", "slide_loo_accuracy", "chance_bound_k")},
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
    sys.exit(main(sys.argv[1:]))
