#!/usr/bin/env python3
"""The section plan and the house's variety.

    plan.py check plan.json --guide guide.json [--house-deck other.guide.json ...] [-o check.json]
    plan.py house --guide guide.json [--house-deck other.guide.json ...]

One definition of variety serves three readers: the guide (the house's own content pages,
extract_style.py and complete_guide.py), the plan (this script's `check`) and the build
(build_deck.py, the solved pages). Over the adjacent pairs of a sequence of pages:

- V (composition) = pairs whose composition differs / pairs;
- V (exhibits) = pairs whose exhibit-type set differs / pairs, a page with no exhibit
  counting as the set {text_only}, a pair with a page whose exhibits were not read
  left out (and counted as unread, never as a change or a repeat);
- V (classes) = the same over exhibit-class sets: the house's from the digest, the build's
  from its element kinds (the plan declares none). A class cannot be renamed the way a
  plan's composition name can;
- distinct compositions per page = distinct compositions / pages, held against the house's
  10th percentile window of the same number of pages (distinct_windows);
- the longest run of one composition, and every run of two or more with its pages.

Pairs are counted only between pages the reader sees next to each other: a sequence breaks
at a page that is not content (a cover, a divider, a disclaimer) and at a page that was not
read, so with one unbroken sequence pairs = n - 1. A deck with no stretch of
VARIETY_MIN_PAGES content pages in a row is no evidence, and every figure says so rather
than reading 0 or 1. Every guide given as house evidence is proven at the boundary
(read_house_guide) and each reference counts once (a repeated sha256 is refused).

plan.json (every key required; `deliberate_parallel` is null on a page that does not
repeat the previous page's composition, and the reason in words on one that does):

{
 "schema": "pptx-skill section plan v1",
 "reference_sha256": "<the guide's reference.sha256: archetype ids belong to one reference>",
 "pages": [
  {"id": "<the deck slide id it becomes>", "intent": "...", "message": "the one message",
   "composition": "arch-3 | new:<name>", "exhibit_types": ["<exhibit_type slug>", ...],
   "data_shapes": ["<data_shape slug>", ...], "title_register": "topic|claim|question",
   "deliberate_parallel": null}
 ]
}

`check` refuses (exit 1), by name: a plan that is not this shape, a value outside the
vocabulary, an archetype the guide does not hold, a reason on a page that repeats nothing,
and an UNDECLARED repeat that makes a run longer than the house's longest (with no house
evidence for the longest run, every undeclared repeat is refused: there is nothing to hold
it to). It warns when the plan's V falls below the house's 10th percentile deck, when its
distinct compositions per page fall below the house's 10th percentile window, and when a
DECLARED run is longer than the house's longest (the reason is the model's; the length is
the house's measure). Those thresholds are choices, not measurements: nothing has measured
what V a reader calls samey.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import pairwise
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))

VOCABULARY = json.loads((Path(__file__).resolve().parent.parent / "references" / "page_craft_vocabulary.json").read_text())


def nearest(value, vocab) -> str:
    """' (nearest: a, b)' for a value outside a closed vocabulary: the entries spelt most
    like it, and those sharing its first word (stacked_column: stacked, stacked_or_100).
    Empty when nothing is near; the full list follows in the refusal either way."""
    import difflib
    if not isinstance(value, str):
        return ""
    words = list(vocab)
    near = difflib.get_close_matches(value, words, n=3, cutoff=0.5)
    head = value.split("_")[0]
    near += [w for w in words if w.split("_")[0] == head and w not in near][:3]
    return f" (nearest: {', '.join(near[:4])})" if near else ""
#: Element kinds whose exhibit class is the kind itself (page_craft_vocabulary exhibit_class).
#: Their classes are the data exhibits: a page holding one is a data page, which the
#: source-line habit is measured over (the digest) and held to (the build).
REALISED_CLASS = {"table": "table", "chart": "data_chart"}
DATA_CLASSES = frozenset(REALISED_CLASS.values())
VARIETY_MIN_PAGES = 3  # definition: two pages make one pair, which is one observation, not a rate
TEXT_ONLY = "text_only"  # the exhibit-type set of a page with no exhibit (A.10's {text only})
WARN_PERCENTILE = 0.1  # unmeasured: the house's 10th percentile deck, a choice and not a reader's threshold
PLAN_SCHEMA = "pptx-skill section plan v1"
PAGE_KEYS = ("id", "intent", "message", "composition", "exhibit_types", "data_shapes", "title_register", "deliberate_parallel")
NEW_COMPOSITION = re.compile(r"new:[a-z0-9][a-z0-9_-]*")  # fullmatch: `$` also matches before a final newline
CONTENT = "content"
METHOD = ("Composition per page is the extractor's archetype (composition.archetypes): the page's content boxes (layout and master "
          "chrome and recurring furniture left out, the title kept) leader-clustered by slide_similarity, the Hungarian assignment of box "
          "IoU over the larger set, at 0.5. Exhibit types per page are the completed digest's records (/exhibit_habits). Content pages are "
          "library.py's triage proposal (cover, divider, disclaimer, hidden and generated pages are not content) until /variety/content_pages "
          "answers it.")
WEAKNESSES = (
    ("Boxes only: a full-width table and a full-width bullet block of the same extent are one archetype; what the boxes hold is not "
     "compared."),
    ("Arrangement, not kind: a table beside a chart, mirrored or re-weighted, is a different arrangement to box IoU (such pairs score "
     "0.30 to 0.40), so the realised composition cannot see that kind of sameness; the exhibit classes the build reads, and the "
     "plan's named compositions, are where it shows."),
    ("Leader clustering is order-dependent and not transitive: a page joins the first archetype whose anchor it matches, so two pages "
     "that match each other but not an earlier anchor can land in different archetypes."),
    ("The title is content to the extractor, so pages that differ only below the title look more alike than the build's frame-free "
     "measure sees them: the house is held to the more lenient count."),
    ("On a PDF the reader's text blocks stand in for shapes, and a page set as many small blocks rarely matches another at 0.5, so a "
     "PDF house can read every page as its own archetype."),
    ("V counts adjacent pairs only: an arrangement used on every other page (A B A C A) reads 1.0; distinct compositions per page "
     "is the figure that shows it."),
    ("The exhibit-type vocabulary has 25 types, finer than the 10 families the corpus rates were counted in, so exhibit V comes out "
     "higher than those rates."),
)


class Refused(SystemExit):
    pass


# --- the one measure --------------------------------------------------------------------------

def percentile(values: list[float], q: float) -> float:
    """The extractor's linear-interpolation percentile (imported here: the extractor imports this module)."""
    from extract_style import percentile as linear
    return linear(values, q)


def runs_of(segment: list[dict]) -> list[list[dict]]:
    """Maximal runs of one composition within one unbroken segment, in order."""
    out: list[list[dict]] = []
    for page in segment:
        if out and out[-1][-1]["composition"] == page["composition"]:
            out[-1].append(page)
        else:
            out.append([page])
    return out


SET_FIELDS = (("exhibits", "/exhibit_habits not answered"), ("classes", "/exhibit_habits not answered"))


def _sets_measure(pages: list[dict], pairs: list[tuple[dict, dict]], field: str, unread_why: str) -> dict:
    """V over one per-page set field ("exhibits": exhibit-type slugs, "classes": exhibit-class
    slugs): a page with none counts as {text_only}; a pair with an unread page (None) is left
    out and counted as unread, never as a change or a repeat."""
    def as_set(p: dict) -> frozenset | None:
        return None if p[field] is None else frozenset(p[field] or [TEXT_ONLY])

    read = [(as_set(a), as_set(b)) for a, b in pairs if as_set(a) is not None and as_set(b) is not None]
    unread = sorted({p["slide"] for p in pages if p[field] is None})
    if not read:
        return {"status": "no evidence", "why": f"{field} not read on {len(unread)} of {len(pages)} content pages ({unread_why})" if unread else "no pair read"}
    changed = sum(1 for a, b in read if a != b)
    return {"V": round(changed / len(read), 3), "changed": changed, "pairs": len(read), "pages_unread": unread}


def distinct_windows(sequences: list[list[str]], n: int) -> list[float]:
    """Distinct compositions per page over every window of n pages in a row (within one
    sequence): the house's distinct-per-page at the length of the sequence it is held against,
    since a short sequence reads more distinct than a long one by arithmetic alone."""
    return [round(len(set(seq[i:i + n])) / n, 3) for seq in sequences for i in range(len(seq) - n + 1)]


def measure_deck(name: str, segments: list[list[dict]], unread_why: dict[str, str] | None = None) -> dict:
    """One deck's variety. `segments` are lists of pages the reader sees in a row, each page
    {"slide", "composition", "exhibits", "classes"}; `exhibits` and `classes` are lists of
    slugs ([] for a page with none) or None when nobody read them, and `unread_why` names why
    for each field. Evidence needs one segment of VARIETY_MIN_PAGES pages: pairs from shorter
    segments still count once a deck has it, never on their own."""
    whys = {**dict(SET_FIELDS), **(unread_why or {})}
    pages = [p for seg in segments for p in seg]
    n = len(pages)
    pairs = [(a, b) for seg in segments for a, b in pairwise(seg)]
    longest_segment = max((len(s) for s in segments), default=0)
    out: dict = {"deck": name, "content_pages": n, "segments": [[p["slide"] for p in seg] for seg in segments], "pairs": len(pairs)}
    if longest_segment < VARIETY_MIN_PAGES:
        why = (f"no evidence: {n} content page{'s' if n != 1 else ''}, the longest stretch read in a row {longest_segment} "
               f"(at least {VARIETY_MIN_PAGES} pages in a row are needed: two pages make one pair, one observation)")
        return {**out, "status": "no evidence", "why": why}
    changed = sum(1 for a, b in pairs if a["composition"] != b["composition"])
    runs = [r for seg in segments for r in runs_of(seg)]
    distinct = len({p["composition"] for p in pages})
    return {**out, "status": "measured",
            "composition": {"V": round(changed / len(pairs), 3), "changed": changed, "pairs": len(pairs)},
            **{field: _sets_measure(pages, pairs, field, whys[field]) for field, _ in SET_FIELDS},
            "distinct": {"compositions": distinct, "pages": n, "per_page": round(distinct / n, 3)},
            "longest_run": max(len(r) for r in runs),
            "runs": [{"composition": r[0]["composition"], "pages": [p["slide"] for p in r]} for r in runs if len(r) > 1],
            "sequences": [[p["composition"] for p in seg] for seg in segments]}


def _pool_sets(measured: list[dict], field: str) -> dict:
    ex = [d for d in measured if "V" in d[field]]
    if not ex:
        return {"status": "no evidence", "why": f"no deck's {field} were read (/exhibit_habits not answered)"}
    pairs = sum(d[field]["pairs"] for d in ex)
    changed = sum(d[field]["changed"] for d in ex)
    return {"V": round(changed / pairs, 3), "changed": changed, "pairs": pairs,
            "p10_deck_V": round(percentile([d[field]["V"] for d in ex], WARN_PERCENTILE), 3),
            "deck_V": [d[field]["V"] for d in ex], "decks_unread": [d["deck"] for d in measured if d not in ex]}


def pool(decks: list[dict]) -> dict:
    """Pairs pooled over the decks that carry evidence (a pair never crosses two decks), the
    longest run over them, and the 10th percentile deck. Distinct compositions are not pooled:
    archetype ids belong to one reference each."""
    measured = [d for d in decks if d["status"] == "measured"]
    if not measured:
        return {"status": "no evidence", "decks": len(decks),
                "why": f"no deck of {len(decks)} has evidence: " + "; ".join(f"{d['deck']}: {d['why']}" for d in decks)}
    pairs = sum(d["composition"]["pairs"] for d in measured)
    changed = sum(d["composition"]["changed"] for d in measured)
    vs = [d["composition"]["V"] for d in measured]
    one = " (one deck: the 10th percentile is that deck)" if len(measured) == 1 else ""
    return {"status": "measured", "decks": len(measured), "decks_without_evidence": [{"deck": d["deck"], "why": d["why"]} for d in decks if d["status"] != "measured"],
            "composition": {"V": round(changed / pairs, 3), "changed": changed, "pairs": pairs,
                            "p10_deck_V": round(percentile(vs, WARN_PERCENTILE), 3), "deck_V": vs, "p10_note": "unmeasured threshold" + one},
            **{field: _pool_sets(measured, field) for field, _ in SET_FIELDS},
            "distinct_per_page": {d["deck"]: d["distinct"]["per_page"] for d in measured},
            "longest_run": max(d["longest_run"] for d in measured),
            "sequences": [s for d in measured for s in d["sequences"]]}


def distinct_against(value: float, n: int, house: dict) -> dict:
    """A sequence's distinct compositions per page against the house's 10th percentile window
    of the same length (distinct_windows): how an A B A B A sequence is held to the house."""
    if house.get("status") != "measured":
        return {"value": value, "verdict": "no evidence in the house: " + house["why"]}
    windows = distinct_windows(house["sequences"], n)
    if not windows:
        return {"value": value, "verdict": f"no evidence in the house: no stretch of {n} content pages in a row"}
    p10 = round(percentile(windows, WARN_PERCENTILE), 3)
    return {"value": value, "house_p10_window": p10, "windows": len(windows), "window_pages": n,
            "verdict": "below the house's 10th percentile window" if value < p10 else "at or above the house's 10th percentile window",
            "threshold": "unmeasured: the 10th percentile window is a choice"}


# --- the house, from a guide -------------------------------------------------------------------

def content_segments(variety: dict, exhibit_habits: dict | None) -> list[list[dict]]:
    """The guide's page sequence cut into the runs of content pages a reader sees in a row.
    A hidden page is not in the reading order and is skipped; any other page that is not
    content breaks the sequence, and so does a gap in the page numbers (a page not read).
    Each page carries its exhibit types and exhibit classes from the digest's records, or
    None when the digest did not read it (no digest, or the page outside its sample)."""
    content = set(variety["content_pages"]["pages"])
    read = None
    by_slide: dict[int, dict[str, list[str]]] = {}
    if exhibit_habits:
        read = {r["slide"] for r in exhibit_habits["records"]} | set(exhibit_habits["sample"]["pages_without"])
        for r in exhibit_habits["records"]:
            got = by_slide.setdefault(r["slide"], {"exhibits": [], "classes": []})
            for field, key in (("exhibits", "type"), ("classes", "class")):
                if r[key] not in got[field]:
                    got[field].append(r[key])
    segments: list[list[dict]] = [[]]
    last = None
    for page in variety["pages"]:
        if page["triage"] == "hidden":
            continue
        if page["slide"] not in content or (last is not None and page["slide"] != last + 1 and not _hidden_between(variety, last, page["slide"])):
            segments.append([])
        if page["slide"] in content:
            got = None if read is None or page["slide"] not in read else by_slide.get(page["slide"], {"exhibits": [], "classes": []})
            segments[-1].append({"slide": page["slide"], "composition": page["composition"],
                                 "exhibits": None if got is None else got["exhibits"], "classes": None if got is None else got["classes"]})
        last = page["slide"]
    return [s for s in segments if s]


def _hidden_between(variety: dict, a: int, b: int) -> bool:
    """Every page strictly between a and b is listed and hidden: the reader sees a then b."""
    listed = {p["slide"]: p["triage"] for p in variety["pages"]}
    return all(listed.get(n) == "hidden" for n in range(a + 1, b))


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def read_house_guide(guide, where: str) -> dict:
    """A guide given as the house's evidence, proven at the boundary: a style guide (a
    reference with its sha256), whose variety, when it carries pages, lists each page once
    with its number, composition and triage and names its content pages among them, and
    whose exhibit digest, when there is one, gives every record a page, type and class.
    Anything else is refused by name: a plan, a list or a guide from before the variety
    measure is not evidence about the house's pages."""
    if not isinstance(guide, dict) or not isinstance(guide.get("reference"), dict) or not (isinstance(guide["reference"].get("sha256"), str) and guide["reference"]["sha256"]):
        raise Refused(f"{where}: not a style guide (no reference.sha256): a house deck is a guide or draft from extract_style.py")
    variety = guide.get("variety")
    if variety is None:
        return guide
    if not isinstance(variety, dict):
        raise Refused(f"{where}: variety is {type(variety).__name__}, not an object")
    pages = variety.get("pages")
    if not pages:
        return guide
    if not isinstance(pages, list) or not all(isinstance(p, dict) for p in pages):
        raise Refused(f"{where}: variety.pages is not a list of pages")
    bad = [i for i, p in enumerate(pages) if not (_is_int(p.get("slide")) and isinstance(p.get("composition"), str) and isinstance(p.get("triage"), str))]
    if bad:
        raise Refused(f"{where}: variety.pages{bad} lack a slide number, composition or triage (a guide from before plan.py: re-run extract_style.py)")
    slides = [p["slide"] for p in pages]
    if len(set(slides)) != len(slides) or slides != sorted(slides):
        raise Refused(f"{where}: variety.pages slides {slides} are not each listed once, in order")
    cp = (variety.get("content_pages") or {}).get("pages") if isinstance(variety.get("content_pages"), dict) else None
    if not isinstance(cp, list) or not all(_is_int(v) and v in slides for v in cp) or len(set(cp)) != len(cp):
        raise Refused(f"{where}: variety.content_pages.pages {cp!r} is not a list of listed slides, each once")
    eh = guide.get("exhibit_habits")
    if eh is not None:
        records = eh.get("records") if isinstance(eh, dict) else None
        without = (eh.get("sample") or {}).get("pages_without") if isinstance(eh, dict) and isinstance(eh.get("sample"), dict) else None
        if not isinstance(records, list) or not all(isinstance(r, dict) and _is_int(r.get("slide")) and isinstance(r.get("type"), str) and isinstance(r.get("class"), str) for r in records):
            raise Refused(f"{where}: exhibit_habits.records is not a list of records with a slide, type and class")
        if not isinstance(without, list) or not all(_is_int(v) for v in without):
            raise Refused(f"{where}: exhibit_habits.sample.pages_without is not a list of slide numbers")
    return guide


def house_deck(guide: dict) -> dict:
    """One guide's deck measured, or no evidence with the reason the guide gives."""
    name = Path(guide["reference"].get("file") or "reference").name
    variety = guide.get("variety")
    if not isinstance(variety, dict) or not variety.get("pages"):
        why = (variety or {}).get("why") if isinstance(variety, dict) else None
        return {"deck": name, "content_pages": 0, "pairs": 0, "status": "no evidence",
                "why": why or "the guide carries no variety pages (extracted before plan.py, or a raster reference with no shapes): re-run extract_style.py"}
    return measure_deck(name, content_segments(variety, guide.get("exhibit_habits")))


def house_of(guides: list[dict], names: list[str] | None = None) -> dict:
    """The house's variety over the guide and its other decks, each proven at the boundary
    and each reference counted once: a deck given twice would weigh its pairs twice and move
    the 10th percentile toward itself."""
    names = names or [f"guide {i}" for i in range(len(guides))]
    seen: dict[str, str] = {}
    for guide, where in zip(guides, names, strict=True):
        read_house_guide(guide, where)
        sha = guide["reference"]["sha256"]
        if sha in seen:
            raise Refused(f"{where}: the same reference as {seen[sha]} (sha256 {sha[:12]}): a deck counts once in the house")
        seen[sha] = where
    decks = [house_deck(g) for g in guides]
    return {"decks": decks, "pooled": pool(decks)}


# --- the plan --------------------------------------------------------------------------------

def read_plan(plan, guide: dict) -> list[dict]:
    """The plan proven at the boundary: every page every key, every value in its vocabulary,
    every archetype one the guide holds. All problems in one refusal."""
    errors: list[str] = []
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA or not isinstance(plan.get("pages"), list):
        raise Refused(f"plan: expected {{\"schema\": \"{PLAN_SCHEMA}\", \"reference_sha256\", \"pages\": [...]}}")
    sha = (guide.get("reference") or {}).get("sha256")
    if plan.get("reference_sha256") != sha:
        raise Refused(f"plan: reference_sha256 {plan.get('reference_sha256')!r} is not this guide's reference ({sha}); archetype ids belong to one reference")
    if len(plan["pages"]) < 1:
        raise Refused("plan: no pages")
    raw_archetypes = (guide.get("composition") or {}).get("archetypes") or []
    if not isinstance(raw_archetypes, list) or not all(isinstance(a, dict) and isinstance(a.get("archetype_id"), str) for a in raw_archetypes):
        raise Refused("guide: composition.archetypes is not a list of {\"archetype_id\": \"arch-N\", ...}; answer /composition with "
                      "complete_guide.py, which checks that shape")
    archetypes = {a["archetype_id"] for a in raw_archetypes}
    registers = VOCABULARY["title_register"]
    ids: list[str] = []
    for i, page in enumerate(plan["pages"]):
        where = f"pages[{i}]"
        if not isinstance(page, dict):
            errors.append(f"{where}: not an object")
            continue
        where = f"page {page.get('id', i)!r}"
        missing = [k for k in PAGE_KEYS if k not in page]
        stray = sorted(set(page) - set(PAGE_KEYS))
        if missing:
            errors.append(f"{where}: {missing} not answered")
        if stray:
            errors.append(f"{where}: unknown keys {stray}")
        for key in ("id", "intent", "message"):
            if key in page and not (isinstance(page[key], str) and page[key].strip()):
                errors.append(f"{where} {key}: words, not {page[key]!r}")
        if isinstance(page.get("id"), str):
            if page["id"] in ids:
                errors.append(f"{where}: id given twice")
            ids.append(page["id"])
        comp = page.get("composition")
        if "composition" in page and not (isinstance(comp, str) and (comp in archetypes or NEW_COMPOSITION.fullmatch(comp))):
            errors.append(f"{where} composition: {comp!r} is neither an archetype of this guide ({sorted(archetypes, key=_arch_order)}) "
                          "nor a named new one (new:<lowercase-name>)")
        for key, vocab in (("exhibit_types", "exhibit_type"), ("data_shapes", "data_shape")):
            if key not in page:
                continue
            got = page[key]
            if not isinstance(got, list):
                errors.append(f"{where} {key}: a list ([] states the page has none)")
                continue
            bad = [v for v in got if not (isinstance(v, str) and v in VOCABULARY[vocab])]
            if bad:
                errors.append(f"{where} {key}: " + "; ".join(f"{v!r}{nearest(v, VOCABULARY[vocab])}" for v in bad)
                              + f" not in {vocab} ({'|'.join(VOCABULARY[vocab])})")
            twice = sorted({v for v in got if isinstance(v, str) and got.count(v) > 1})
            if twice:
                errors.append(f"{where} {key}: {twice} named more than once (the list is a set: two exhibits of one type are one entry)")
        if "title_register" in page and not (isinstance(page["title_register"], str) and page["title_register"] in registers):
            errors.append(f"{where} title_register: {page['title_register']!r}{nearest(page['title_register'], registers)} not in {'|'.join(registers)}")
        reason = page.get("deliberate_parallel")
        if "deliberate_parallel" in page and reason is not None and not (isinstance(reason, str) and reason.strip()):
            errors.append(f"{where} deliberate_parallel: null, or the reason in words")
    pages = plan["pages"]
    for prev, page in pairwise(pages):
        if isinstance(prev, dict) and isinstance(page, dict) and isinstance(page.get("deliberate_parallel"), str) and page.get("composition") != prev.get("composition"):
            errors.append(f"page {page.get('id')!r} deliberate_parallel: given, but its composition {page.get('composition')!r} does not repeat "
                          f"the previous page's {prev.get('composition')!r}; the reason names a repeat or is null")
    if isinstance(pages[0], dict) and isinstance(pages[0].get("deliberate_parallel"), str):
        errors.append(f"page {pages[0].get('id')!r} deliberate_parallel: the first page repeats nothing")
    if errors:
        raise Refused(f"plan: {len(errors)} problem{'s' if len(errors) > 1 else ''}: " + "; ".join(errors))
    return pages


def _arch_order(a: str) -> tuple:
    m = re.match(r"arch-(\d+)$", a)
    return (0, int(m.group(1))) if m else (1, a)


def plan_segments(pages: list[dict]) -> list[list[dict]]:
    return [[{"slide": i, "id": p["id"], "composition": p["composition"], "exhibits": list(p["exhibit_types"]), "classes": None}
             for i, p in enumerate(pages, 1)]]


PLAN_UNREAD = {"classes": "the plan declares exhibit types, not classes: the build measures the classes it realises"}


def against(value: float | None, house: dict, key: str) -> dict:
    """A plan or build figure against the pooled house and its 10th percentile deck."""
    h = house.get(key) if house.get("status") == "measured" else None
    if value is None:
        return {"value": None, "verdict": "no evidence on this side"}
    if not h or "V" not in h:
        return {"value": value, "verdict": "no evidence in the house: " + ((h or house).get("why") or "not measured")}
    verdict = "below the house's 10th percentile deck" if value < h["p10_deck_V"] else "at or above the house's 10th percentile deck"
    return {"value": value, "house_pooled": h["V"], "house_p10_deck": h["p10_deck_V"], "verdict": verdict,
            "threshold": "unmeasured: the 10th percentile deck is a choice; no reader has measured where V reads as samey"}


def parallels_note(repeats: list[dict], measured: dict) -> str:
    """What a low composition V owes to repeats the plan declared: each declared pair with
    its reason, and V over the other pairs. A declared parallel is the model's reason; the
    warning stands, and names it, so the report answers it with the plan's own words."""
    declared = [r for r in repeats if r.get("deliberate_parallel")]
    if not declared:
        return "; no repeat in it is a declared parallel"
    pairs, changed = measured.get("pairs") or 0, measured.get("changed") or 0
    rest = pairs - len(declared)
    cited = "; ".join(f"{r['pages'][0]!r} to {r['pages'][1]!r} ({r['deliberate_parallel']})" for r in declared)
    without = f"; over the other {rest} pair(s) V is {round(changed / rest, 3)}" if rest > 0 else ""
    return f"; {len(declared)} of its unchanged pairs {'is a' if len(declared) == 1 else 'are'} declared parallel{'s' if len(declared) > 1 else ''}: {cited}{without}"


def check(plan, guide: dict, others: list[dict], names: list[str] | None = None) -> dict:
    pages = read_plan(plan, guide)
    house = house_of([guide, *others], names)
    pooled = house["pooled"]
    mine = measure_deck("plan", plan_segments(pages), PLAN_UNREAD)
    refusals: list[str] = []
    warnings: list[str] = []
    longest = pooled.get("longest_run") if pooled["status"] == "measured" else None
    repeats = []
    run = 1
    for prev, page in pairwise(pages):
        run = run + 1 if page["composition"] == prev["composition"] else 1
        if run == 1:
            continue
        declared = page["deliberate_parallel"]
        rec = {"pages": [prev["id"], page["id"]], "composition": page["composition"], "run_length": run, "deliberate_parallel": declared,
               "house_longest_run": longest if longest is not None else "no evidence"}
        if declared:
            rec["verdict"] = "declared" + (f"; the run of {run} is longer than the house's {longest}" if longest is not None and run > longest else "")
            if longest is None or run > longest:
                warnings.append(f"page {page['id']!r} makes a declared run of {run} of {page['composition']}, longer than the house's longest "
                                f"({longest if longest is not None else 'no evidence'}): the reason is the model's, the length is the house's measure")
        elif longest is None:
            rec["verdict"] = "refused: undeclared, and the house has no evidence for its longest run to hold it to"
            refusals.append(f"page {page['id']!r} repeats {page['composition']} undeclared and the house's longest run is no evidence "
                            f"({pooled.get('why')}): declare it in deliberate_parallel or vary the composition")
        elif run > longest:
            rec["verdict"] = f"refused: undeclared, and the run of {run} is longer than the house's longest {longest}"
            refusals.append(f"page {page['id']!r} repeats {page['composition']} undeclared, making a run of {run} where the house's longest is "
                            f"{longest}: declare the parallel in deliberate_parallel or vary the composition")
        else:
            rec["verdict"] = f"undeclared repeat within the house's longest run ({longest})"
            warnings.append(f"page {page['id']!r} repeats {page['composition']} without a deliberate_parallel reason")
        repeats.append(rec)
    comparison = {}
    if mine["status"] == "measured":
        comparison = {"composition_V": against(mine["composition"]["V"], pooled, "composition"),
                      "exhibits_V": against(mine["exhibits"].get("V"), pooled, "exhibits"),
                      "distinct_per_page": {**distinct_against(mine["distinct"]["per_page"], mine["content_pages"], pooled),
                                            "house_decks": pooled.get("distinct_per_page") if pooled["status"] == "measured" else "no evidence"},
                      "longest_run": {"plan": mine["longest_run"], "house": longest if longest is not None else "no evidence"}}
        for key in ("composition_V", "exhibits_V"):
            if comparison[key]["verdict"].startswith("below"):
                c = comparison[key]
                warnings.append(f"{key} {c['value']} is below the house's 10th percentile deck {c['house_p10_deck']} (pooled {c['house_pooled']}); "
                                "the threshold is unmeasured" + (parallels_note(repeats, mine["composition"]) if key == "composition_V" else ""))
        d = comparison["distinct_per_page"]
        if d["verdict"].startswith("below"):
            warnings.append(f"distinct compositions per page {d['value']} is below the house's 10th percentile window of {d['window_pages']} pages "
                            f"({d['house_p10_window']}, {d['windows']} windows): the plan reuses compositions more than the house does; the threshold is unmeasured")
    else:
        comparison = {"plan": mine["why"]}
    archetypes = {a["archetype_id"]: a for a in (guide.get("composition") or {}).get("archetypes") or []}
    new = sorted({p["composition"] for p in pages if p["composition"] not in archetypes})
    house_registers = (((guide.get("titles") or {}).get("register")) or {}).get("counts")
    for p in pages:
        if house_registers is None:
            continue
        if not house_registers.get(p["title_register"]):
            warnings.append(f"page {p['id']!r} title_register {p['title_register']!r}: the house writes none ({house_registers})")
    return {"status": "refused" if refusals else "pass", "refusals": refusals, "warnings": warnings,
            "plan": mine, "house": house, "comparison": comparison, "repeats": repeats,
            "compositions": {"house_archetypes_used": sorted({p["composition"] for p in pages} - set(new), key=_arch_order), "new": new},
            "title_registers": {"house": house_registers if house_registers is not None else "no evidence: /titles/register not completed",
                                "plan": {r: sum(1 for p in pages if p["title_register"] == r) for r in VOCABULARY["title_register"]}}}


def load(path: str):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise Refused(f"{path}: {error}") from None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate a plan against the guide and report its variety against the house's")
    c.add_argument("plan")
    c.add_argument("--guide", required=True, help="the guide the section is built with (its archetype ids are the plan's)")
    c.add_argument("--house-deck", action="append", default=[], help="another guide of the same house, pooled into the house's variety")
    c.add_argument("-o", "--out", default=None, help="write the full report as JSON")
    c.add_argument("--json", action="store_true", help="print the full report instead of the verdict")
    h = sub.add_parser("house", help="the house's variety, per deck and pooled")
    h.add_argument("--guide", required=True)
    h.add_argument("--house-deck", action="append", default=[])
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out")
    guide = load(args.guide)
    others = [load(p) for p in args.house_deck]
    names = [f"--guide {args.guide}", *(f"--house-deck {p}" for p in args.house_deck)]
    if args.cmd == "house":
        print(json.dumps(house_of([guide, *others], names), indent=1))
        return 0
    try:
        report = check(load(args.plan), guide, others, names)
    except Refused as error:
        report = {"status": "refused", "refusals": [str(error)]}
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n")
    if args.json:
        print(text)
    else:
        print(verdict(report, args.out))
    return 0 if report["status"] == "pass" else 1


def verdict(report: dict, out: str | None) -> str:
    """The check in a few lines: status, every refusal and warning, each variety measure
    against the house; the whole report is the JSON (-o, or --json)."""
    lines = [f"plan check: {report['status']}"]
    lines += [f"  refused: {r}" for r in report.get("refusals") or []]
    lines += [f"  warning: {w}" for w in report.get("warnings") or []]
    for key, v in (report.get("comparison") or {}).items():
        if isinstance(v, dict) and "verdict" in v:
            house = v.get("house_p10_deck", v.get("house_p10_window"))
            lines.append(f"  {key}: {v.get('value')}, house 10th percentile {house} ({v['verdict']})")
        elif isinstance(v, dict):
            lines.append(f"  {key}: " + ", ".join(f"{k} {x}" for k, x in v.items()))
        else:
            lines.append(f"  {key}: {v}")
    decks = (report.get("house") or {}).get("decks") or []
    if len(decks) == 1:
        lines.append("  note: the house is one deck, so each 10th percentile is that deck's own value; its exhibit and class V come "
                     "from your digest reading, so a different reading moves these lines (pool sister decks with --house-deck)")
    regs = report.get("title_registers") or {}
    if regs:
        lines.append(f"  title registers: plan {regs.get('plan')}, house {regs.get('house')}")
    lines.append(f"  full report: {out}" if out else "  full report: pass -o FILE or --json")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
