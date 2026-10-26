#!/usr/bin/env python3
"""The section plan and the house's variety.

    plan.py check plan.json --guide guide.json [--house-deck other.guide.json ...] [-o check.json]
    plan.py house --guide guide.json [--house-deck other.guide.json ...]

One definition of variety serves three readers: the guide (the house's own content pages,
extract_style.py and complete_guide.py), the plan (this script's `check`) and the build
(build_deck.py, the solved pages). Over the adjacent pairs of a sequence of pages:

- V (composition) = pairs whose composition differs / pairs;
- V (structures) = pairs whose exhibit structure differs / pairs. A page's exhibit
  structure is read from the file (ooxml.exhibit_facts: its native charts by the plot
  types and series counts the chart XML states, its tables, its pictures, drawn shapes,
  and how many panels): the house's off the reference's own pages, the build's off the
  file it wrote. Nobody names it, so renaming an exhibit cannot move it; a pair with a page
  whose structure was not read is left out (and counted as unread, never as a change or a
  repeat). A plan declares no structure: it describes each exhibit in a brief;
- V (kinds) = the same over each page's exhibit kinds (exhibit_facts' `kinds`: the
  structure with every chart read as "chart"), where a section that sets a table beside a
  chart on page after page reads as the repeat it is whatever the charts plot;
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
 "schema": "pptx-skill section plan v2",
 "reference_sha256": "<the guide's reference.sha256: archetype ids belong to one reference>",
 "pages": [
  {"id": "<the deck slide id it becomes>", "intent": "...",
   "message": "the page's message, or what the reader looks up on a reference page",
   "composition": "arch-3 | new:<name>",
   "title_register": "the title's register in words, or a term the house's titles are coded in",
   "deliberate_parallel": null,
   "exhibits": [<one brief per exhibit; [] on a page that holds none>]}
 ]
}

An exhibit brief, every field in the model's own words (nothing is chosen from a list):

{"reader_must_see": "what the reader must see on it",
 "comparison": "what is compared against what",
 "data": "the data's shape, in words",
 "forms_considered": [{"form": "...", "reason": "why not, or why"}, ...],   (two or more distinct forms)
 "chosen_form": "...", "why": "why this form shows what the reader must see",
 "nearest_house_exhibit": {"page": N, "what": "what that page does that this takes or departs from"}
                          | {"none": "why no page of the reference is near, because ..."},
 "marks": "what will be marked, where the claim lives, and why"}

`check` reads a brief for completeness only, never for what it says: every field present,
each text field a phrase of at least BRIEF_MIN_WORDS distinct words (a form's name at least
one; placeholders such as TBD or n/a and a lone letter do not count), at least two
distinct forms considered (_form_key: case, punctuation, fullwidth letters, a leading
article and a plural s folded; a form spelt in two scripts refused), a chosen form that
is one of them, a nearest page that is a content page of the reference (1 to
reference.slides, and not a cover, divider or disclaimer where the guide says which pages
are content) or a reason why none is near, and no brief given twice across the plan.

A title register is the model's words. When it names a term the house's titles are coded
in (references/page_craft_vocabulary.json, by slug or label: register_term), it is held to
the house's count of that term; otherwise it is reported as no house count, with the
house's counts beside it. Only a register that is not words is refused.

`check` refuses (exit 1), by name: a guide made before the current readings
(old_guide_error), a plan that is not this shape, a brief that is not complete, a title
register that is not words, an archetype the guide does not hold, a reason on a page that
repeats nothing, and an UNDECLARED repeat that makes a run longer than the house's longest.
With no house evidence for its longest run, the corpus's measure stands in
(CORPUS_LONGEST_RUN): an undeclared run of that length warns, a longer one is refused, and
a reason in deliberate_parallel clears it. It warns when the plan's V falls below the
house's 10th percentile deck, when its distinct compositions per page fall below the
house's 10th percentile window, when a DECLARED run is longer than the house's longest (or
the corpus's, where the house has none: the reason is the model's; the length is the
measure), and when a coded register is one the house never writes. Those thresholds are
choices, not measurements: nothing has measured what V a reader calls samey.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
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
VARIETY_MIN_PAGES = 3  # definition: two pages make one pair, which is one observation, not a rate
#: The longest run of one composition the corpus shows without a declared reason, and where
#: it was measured: the evidence a plan is held to when its house has no run evidence of its own
CORPUS_LONGEST_RUN = 2
CORPUS_RUN_BASIS = ("references/planning-and-variety.md, measured tendencies: three native-pptx bank pitch books never ran one composition longer than 2 pages, and every longer run in the "
                    "23 coded decks was a deliberate sibling template; no coder found an accidental one")
WARN_PERCENTILE = 0.1  # unmeasured: the house's 10th percentile deck, a choice and not a reader's threshold
PLAN_SCHEMA = "pptx-skill section plan v2"
PAGE_KEYS = ("id", "intent", "message", "composition", "title_register", "deliberate_parallel", "exhibits")
BRIEF_KEYS = ("reader_must_see", "comparison", "data", "forms_considered", "chosen_form", "why", "nearest_house_exhibit", "marks")
BRIEF_TEXT = ("reader_must_see", "comparison", "data", "chosen_form", "why", "marks")
BRIEF_MIN_WORDS = 3  # definition, unmeasured: a reason is a phrase ("n/a", "see above", "TBD" are not reasons)
NAME_FIELDS = frozenset({"chosen_form"})  # a form's name may be one word
_WORD = re.compile(r"[^\W_][\w'%.,/-]*")
NEW_COMPOSITION = re.compile(r"new:[a-z0-9][a-z0-9_-]*")  # fullmatch: `$` also matches before a final newline
CONTENT = "content"
METHOD = ("Composition per page is the extractor's archetype (composition.archetypes): the page's content boxes (layout and master "
          "chrome and recurring furniture left out, the title kept) leader-clustered by slide_similarity, the Hungarian assignment of box "
          "IoU over the larger set, at 0.5. Exhibit structure per page is read from the file (ooxml.exhibit_facts): native charts by their plot "
          "types and series counts, tables, pictures, drawn shapes, panels; nobody names it. Content pages are "
          "library.py's triage proposal (cover, divider, disclaimer, hidden and generated pages are not content) until /variety/content_pages "
          "answers it.")
WEAKNESSES = (
    ("Boxes only: a full-width table and a full-width bullet block of the same extent are one archetype; what the boxes hold is not "
     "compared."),
    ("Arrangement, not kind: a table beside a chart, mirrored or re-weighted, is a different arrangement to box IoU (such pairs score "
     "0.30 to 0.40), so the realised composition cannot see that kind of sameness; the exhibit structure read from the file, and "
     "the plan's named compositions, are where it shows."),
    ("Leader clustering is order-dependent and not transitive: a page joins the first archetype whose anchor it matches, so two pages "
     "that match each other but not an earlier anchor can land in different archetypes."),
    ("The title is content to the extractor, so pages that differ only below the title look more alike than the build's frame-free "
     "measure sees them: the house is held to the more lenient count."),
    ("On a PDF the reader's text blocks stand in for shapes, and a page set as many small blocks rarely matches another at 0.5, so a "
     "PDF house can read every page as its own archetype."),
    ("V counts adjacent pairs only: an arrangement used on every other page (A B A C A) reads 1.0; distinct compositions per page "
     "is the figure that shows it."),
    ("A picture carries no structure: a house that pastes its charts and tables as pictures reads every such page as 'picture', so its "
     "structure V is low and the build is held to a lenient line; what the picture shows is the digest's reading, never measured."),
    ("A PDF states rectangles, paths and text, never a chart or a table, so a PDF house's structure reads only pictures, drawn shapes "
     "and text, coarser than a native build's: the two are held to each other as change rates, each over its own pages."),
    ("Structure is kind and count, not form: two column charts of three series are one structure whatever they compare, and a "
     "waterfall drawn as stacked columns is a stacked column chart."),
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


STRUCTURE_UNREAD = "the guide carries no exhibit facts per page (extracted before they were read): re-run extract_style.py"
#: the measures read from each page's file (ooxml.exhibit_facts), by the key each page carries
FACT_MEASURES = (("structures", "structure"), ("kinds", "kinds"))


def _structure_measure(pages: list[dict], pairs: list[tuple[dict, dict]], unread_why: str, key: str) -> dict:
    """V over one exhibit fact of each page (ooxml.exhibit_facts' `structure` or `kinds`
    string): a pair with an unread page (None) is left out and counted as unread, never as
    a change or a repeat."""
    read = [(a[key], b[key]) for a, b in pairs if a[key] is not None and b[key] is not None]
    unread = sorted({p["slide"] for p in pages if p[key] is None})
    if not read:
        return {"status": "no evidence", "why": f"{key} not read on {len(unread)} of {len(pages)} content pages ({unread_why})" if unread else "no pair read"}
    changed = sum(1 for a, b in read if a != b)
    return {"V": round(changed / len(read), 3), "changed": changed, "pairs": len(read), "pages_unread": unread}


def distinct_windows(sequences: list[list[str]], n: int) -> list[float]:
    """Distinct compositions per page over every window of n pages in a row (within one
    sequence): the house's distinct-per-page at the length of the sequence it is held against,
    since a short sequence reads more distinct than a long one by arithmetic alone."""
    return [round(len(set(seq[i:i + n])) / n, 3) for seq in sequences for i in range(len(seq) - n + 1)]


def measure_deck(name: str, segments: list[list[dict]], unread_why: str = STRUCTURE_UNREAD) -> dict:
    """One deck's variety. `segments` are lists of pages the reader sees in a row, each page
    {"slide", "composition", "structure", "kinds"}; `structure` and `kinds` are read from the
    page's file, or None when it was not read, and `unread_why` says why. Evidence needs
    one segment of VARIETY_MIN_PAGES pages: pairs from shorter segments still count once a
    deck has it, never on their own."""
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
            **{name: _structure_measure(pages, pairs, unread_why, key) for name, key in FACT_MEASURES},
            "distinct": {"compositions": distinct, "pages": n, "per_page": round(distinct / n, 3)},
            "longest_run": max(len(r) for r in runs),
            "runs": [{"composition": r[0]["composition"], "pages": [p["slide"] for p in r]} for r in runs if len(r) > 1],
            "sequences": [[p["composition"] for p in seg] for seg in segments]}


def _pool_sets(measured: list[dict], field: str) -> dict:
    ex = [d for d in measured if "V" in d[field]]
    if not ex:
        return {"status": "no evidence", "why": f"no deck's {field} were read: " + "; ".join(f"{d['deck']}: {d[field].get('why')}" for d in measured)}
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
            **{name: _pool_sets(measured, name) for name, _ in FACT_MEASURES},
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

def content_segments(variety: dict) -> list[list[dict]]:
    """The guide's page sequence cut into the runs of content pages a reader sees in a row.
    A hidden page is not in the reading order and is skipped; any other page that is not
    content breaks the sequence, and so does a gap in the page numbers (a page not read).
    Each page carries its exhibit structure as the extractor read it from the file, or None
    on a guide extracted before exhibit facts were read."""
    content = set(variety["content_pages"]["pages"])
    segments: list[list[dict]] = [[]]
    last = None
    for page in variety["pages"]:
        if page["triage"] == "hidden":
            continue
        if page["slide"] not in content or (last is not None and page["slide"] != last + 1 and not _hidden_between(variety, last, page["slide"])):
            segments.append([])
        if page["slide"] in content:
            facts = page.get("exhibit_facts")
            segments[-1].append({"slide": page["slide"], "composition": page["composition"],
                                 **{key: facts.get(key) if isinstance(facts, dict) else None for _, key in FACT_MEASURES}})
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
    with its number, composition and triage, names its content pages among them, and gives
    each page's exhibit facts a structure string. Anything else is refused by name: a plan,
    a list, a guide from before the variety measure, and a guide made before the current
    readings (old_guide_error) are not evidence about the house's pages."""
    if not isinstance(guide, dict) or not isinstance(guide.get("reference"), dict) or not (isinstance(guide["reference"].get("sha256"), str) and guide["reference"]["sha256"]):
        raise Refused(f"{where}: not a style guide (no reference.sha256): a house deck is a guide or draft from extract_style.py")
    stale = old_guide_error(guide, where)
    if stale:
        raise Refused(stale)
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
    bad = [p["slide"] for p in pages if "exhibit_facts" in p and not (isinstance(p["exhibit_facts"], dict)
                                                                     and all(isinstance(p["exhibit_facts"].get(key), str) for _, key in FACT_MEASURES))]
    if bad:
        raise Refused(f"{where}: variety.pages on slides {bad} carry exhibit_facts without structure and kinds strings (re-run extract_style.py)")
    return guide


#: the keys complete_guide.exhibit_habits writes: the digest in words, and the source-line count
EXHIBIT_HABIT_KEYS = ("source_lines", "sample", "records", "provenance")


def old_guide_error(guide: dict, where: str) -> str | None:
    """Why a guide was made before the current readings, or None. Two ways, each by name:
    its pages' exhibit facts were read under another definition than ooxml.exhibit_facts'
    (EXHIBIT_FACTS_READER; none at all on a guide from before the facts were read), so its
    structure and its marks are not this build's reading of a page; or its digest
    (exhibit_habits) carries keys the digest in words no longer writes (the closed lists:
    types, classes, annotation moves ...). Either is refused wherever a guide is read (plan
    check, build, house decks), not only where a house precedent is looked up."""
    from ooxml import EXHIBIT_FACTS_READER
    pages = (guide.get("variety") or {}).get("pages") if isinstance(guide.get("variety"), dict) else None
    if isinstance(pages, list) and pages:
        stale = [p.get("slide") for p in pages if not (isinstance(p, dict) and isinstance(p.get("exhibit_facts"), dict)
                                                         and p["exhibit_facts"].get("reader") == EXHIBIT_FACTS_READER)]
        if stale:
            return (f"{where}: extracted before the current exhibit reading ({EXHIBIT_FACTS_READER!r}): {len(stale)} of {len(pages)} pages "
                    f"carry {'no exhibit facts' if all(not isinstance(p.get('exhibit_facts'), dict) for p in pages if isinstance(p, dict)) else 'facts read another way'} "
                    f"(slides {stale[:8]}{' ...' if len(stale) > 8 else ''}). Re-run extract_style.py on the reference, then complete_guide.py with the completion "
                    "and a digest answered in words")
    habits = guide.get("exhibit_habits")
    if isinstance(habits, dict):
        stray = sorted(set(habits) - set(EXHIBIT_HABIT_KEYS))
        if stray:
            return (f"{where}: exhibit_habits carries {stray}, written from the closed lists the digest no longer has. Re-run gallery.py "
                    "digest, answer each exhibit in words (what, message, how_drawn, marks) and complete the guide again")
    return None


def house_deck(guide: dict) -> dict:
    """One guide's deck measured, or no evidence with the reason the guide gives."""
    name = Path(guide["reference"].get("file") or "reference").name
    variety = guide.get("variety")
    if not isinstance(variety, dict) or not variety.get("pages"):
        why = (variety or {}).get("why") if isinstance(variety, dict) else None
        return {"deck": name, "content_pages": 0, "pairs": 0, "status": "no evidence",
                "why": why or "the guide carries no variety pages (extracted before plan.py, or a raster reference with no shapes): re-run extract_style.py"}
    return measure_deck(name, content_segments(variety))


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
    """The plan proven at the boundary: every page every key, every exhibit brief complete
    (brief_errors), every title register in the title vocabulary, every archetype one the
    guide holds. All problems in one refusal."""
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
    ids: list[str] = []
    briefed: dict[str, list[str]] = {}
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
        if "exhibits" in page:
            if not isinstance(page["exhibits"], list):
                errors.append(f"{where} exhibits: a list of exhibit briefs ([] states the page holds none)")
            else:
                for j, brief in enumerate(page["exhibits"]):
                    errors += brief_errors(brief, f"{where} exhibits[{j}]", guide)
                    if isinstance(brief, dict):
                        briefed.setdefault(_brief_key(brief), []).append(f"{where} exhibits[{j}]")
        if "title_register" in page and not (isinstance(page["title_register"], str) and _words(page["title_register"]) >= 1):
            errors.append(f"{where} title_register: the title's register in words (or a term the house's titles are coded in: "
                          f"{'|'.join(VOCABULARY['title_register'])}), not {page['title_register']!r}")
        reason = page.get("deliberate_parallel")
        if "deliberate_parallel" in page and reason is not None and not (isinstance(reason, str) and reason.strip()):
            errors.append(f"{where} deliberate_parallel: null, or the reason in words")
    errors += [f"{', '.join(at)}: one brief given {len(at)} times (identical after case, punctuation and plurals); each exhibit is "
               "briefed for itself" for at in briefed.values() if len(at) > 1]
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


#: words that stand in for an answer not given; with a lone letter other than "a" and "I"
#: ("x y z"), they never count toward a phrase's words. A refusal of non-answers, not a
#: list of anything to choose
PLACEHOLDERS = frozenset({"tbd", "tbc", "tba", "todo", "na", "n/a", "n.a", "n.a.", "nil", "null", "xx", "xxx", "placeholder",
                          "lorem", "ipsum", "etc", "etc.", "...", "same", "ditto"})


def _counted(token: str) -> bool:
    t = token.lower().rstrip(".,")
    return t not in PLACEHOLDERS and not (len(t) == 1 and t.isalpha() and t not in ("a", "i"))


def _words(text) -> int:
    """The distinct words of a phrase that answer something: a word given twice counts once,
    and placeholders (PLACEHOLDERS, a lone letter) not at all, so "TBD TBD TBD" is no phrase."""
    if not isinstance(text, str):
        return 0
    return len({t.lower() for t in _WORD.findall(unicodedata.normalize("NFKC", text)) if _counted(t)})


def _phrase_error(value, where: str, least: int) -> str | None:
    if not isinstance(value, str) or _words(value) < least:
        return (f"{where}: {'a phrase of at least ' + str(least) + ' distinct words' if least > 1 else 'words'} "
                f"(placeholders such as TBD or n/a, and a word repeated, do not count), not {value!r}")
    return None


def _mixed_scripts(text: str) -> list[str]:
    """The words of a text that mix letters of two scripts (a Cyrillic "а" inside a Latin
    word reads the same and is another word to a comparison)."""
    out = []
    for word in re.findall(r"[^\W\d_]+", unicodedata.normalize("NFKC", text)):
        scripts = {unicodedata.name(ch, "?").split(" ")[0] for ch in word}
        if len(scripts) > 1:
            out.append(word)
    return out


def _form_key(form: str) -> str:
    """A form's name for telling two apart: compatibility forms folded (fullwidth letters),
    case, spacing and punctuation left out, a leading article dropped, and each word's
    plural s (on words of four letters or more, not "ss") dropped: "Bar charts" and "the
    BAR CHART." are one form."""
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", form).casefold())
    if words and words[0] in ("a", "an", "the"):
        words = words[1:]
    return " ".join(w[:-1] if len(w) >= 4 and w.endswith("s") and not w.endswith("ss") else w for w in words)


def _brief_key(brief: dict) -> str:
    """A brief with every phrase keyed as forms are: two exhibits whose briefs key the same
    were briefed once and pasted."""
    def key(v):
        if isinstance(v, str):
            return _form_key(v)
        if isinstance(v, list):
            return [key(x) for x in v]
        if isinstance(v, dict):
            return {k: key(x) for k, x in v.items()}
        return v
    return json.dumps(key(brief), sort_keys=True)


def reference_pages(guide: dict) -> int | None:
    """How many pages the reference holds (reference.slides), or None when the guide does not say."""
    n = (guide.get("reference") or {}).get("slides")
    return n if _is_int(n) and n > 0 else None


def brief_errors(brief, where: str, guide: dict) -> list[str]:
    """An exhibit brief checked for completeness, never for what it says: every key (BRIEF_KEYS)
    and no other; each text field a phrase of BRIEF_MIN_WORDS words or more (a form's name one
    word or more); forms_considered a list of {"form", "reason"} naming at least two distinct
    forms; nearest_house_exhibit {"page": N, "what": ...} with N a page of the reference, or
    {"none": ...} saying why no page is near."""
    if not isinstance(brief, dict):
        return [f"{where}: an exhibit brief ({', '.join(BRIEF_KEYS)}), not {type(brief).__name__}"]
    out: list[str] = []
    missing = [k for k in BRIEF_KEYS if k not in brief]
    stray = sorted(set(brief) - set(BRIEF_KEYS))
    if missing:
        out.append(f"{where}: {missing} not answered")
    if stray:
        out.append(f"{where}: unknown keys {stray}")
    for key in BRIEF_TEXT:
        if key in brief:
            e = _phrase_error(brief[key], f"{where} {key}", 1 if key in NAME_FIELDS else BRIEF_MIN_WORDS)
            if e:
                out.append(e)
    forms = brief.get("forms_considered")
    if "forms_considered" in brief:
        if not isinstance(forms, list):
            out.append(f"{where} forms_considered: a list of {{\"form\", \"reason\"}}, two or more")
        else:
            names = []
            for k, f in enumerate(forms):
                if not isinstance(f, dict) or set(f) != {"form", "reason"}:
                    out.append(f"{where} forms_considered[{k}]: exactly {{\"form\", \"reason\"}} (the reason: why not, or why)")
                    continue
                out += [e for e in (_phrase_error(f["form"], f"{where} forms_considered[{k}] form", 1),
                                    _phrase_error(f["reason"], f"{where} forms_considered[{k}] reason", BRIEF_MIN_WORDS)) if e]
                if isinstance(f["form"], str):
                    names.append(_form_key(f["form"]))
            distinct = sorted({n for n in names if n})
            if len(distinct) < 2:
                out.append(f"{where} forms_considered: {len(distinct)} distinct form{'' if len(distinct) == 1 else 's'} ({distinct}); "
                           "weigh at least two forms for what the reader must see, each with why not or why")
            mixed = [w for f in forms if isinstance(f, dict) and isinstance(f.get("form"), str) for w in _mixed_scripts(f["form"])]
            if mixed:
                out.append(f"{where} forms_considered: {mixed} mix{'es' if len(mixed) == 1 else ''} letters of two scripts; spell each form in one")
            chosen = brief.get("chosen_form")
            if isinstance(chosen, str) and distinct and _form_key(chosen) not in distinct:
                weighed = [f["form"] for f in forms if isinstance(f, dict) and isinstance(f.get("form"), str)]
                out.append(f"{where} chosen_form: {chosen!r} is none of the forms considered ({weighed}); the chosen form is one of those "
                           "weighed, named the same way (case, punctuation and plurals aside)")
    near = brief.get("nearest_house_exhibit")
    if "nearest_house_exhibit" in brief:
        n = reference_pages(guide)
        if isinstance(near, dict) and set(near) == {"page", "what"}:
            if not _is_int(near["page"]) or n is None or not 1 <= near["page"] <= n:
                out.append(f"{where} nearest_house_exhibit: page {near['page']!r} is not a page of the reference "
                           f"({'1 to ' + str(n) if n else 'the guide states no page count (reference.slides)'})")
            else:
                variety = guide.get("variety") if isinstance(guide.get("variety"), dict) else {}
                listed = {p.get("slide"): p for p in variety.get("pages") or [] if isinstance(p, dict)}
                content = (variety.get("content_pages") or {}).get("pages") if isinstance(variety.get("content_pages"), dict) else None
                if near["page"] in listed and isinstance(content, list) and near["page"] not in content:
                    out.append(f"{where} nearest_house_exhibit: page {near['page']} is not a content page of the reference "
                               f"(variety reads it as {listed[near['page']].get('triage')!r}); cite a content page, or say why none is near")
            e = _phrase_error(near["what"], f"{where} nearest_house_exhibit what", BRIEF_MIN_WORDS)
            if e:
                out.append(e)
        elif isinstance(near, dict) and set(near) == {"none"}:
            e = _phrase_error(near["none"], f"{where} nearest_house_exhibit none", BRIEF_MIN_WORDS)
            if e:
                out.append(e + " (say why no page of the reference is near)")
        else:
            out.append(f"{where} nearest_house_exhibit: {{\"page\": N, \"what\": ...}} for a page of the reference, "
                       f"or {{\"none\": \"why none is near\"}}; not {near!r}")
    return out


def _arch_order(a: str) -> tuple:
    m = re.match(r"arch-(\d+)$", a)
    return (0, int(m.group(1))) if m else (1, a)


def plan_segments(pages: list[dict]) -> list[list[dict]]:
    return [[{"slide": i, "id": p["id"], "composition": p["composition"], **{key: None for _, key in FACT_MEASURES}} for i, p in enumerate(pages, 1)]]


PLAN_UNREAD = "a plan describes its exhibits in briefs and declares no structure: the build reads the structure from the file it writes"


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
    house_longest = pooled.get("longest_run") if pooled["status"] == "measured" else None
    # the measure a run is held to: the house's own longest run, or the corpus's where the
    # house has no run evidence (never nothing: no evidence is not a licence and not a ban)
    longest, whose = (house_longest, "the house's") if house_longest is not None else (CORPUS_LONGEST_RUN, "the corpus's")
    basis = ("the house's own content pages" if house_longest is not None
             else f"the corpus, since the house has no run evidence ({pooled.get('why')}): {CORPUS_RUN_BASIS}")
    repeats = []
    run = 1
    for prev, page in pairwise(pages):
        run = run + 1 if page["composition"] == prev["composition"] else 1
        if run == 1:
            continue
        declared = page["deliberate_parallel"]
        rec = {"pages": [prev["id"], page["id"]], "composition": page["composition"], "run_length": run, "deliberate_parallel": declared,
               "house_longest_run": house_longest if house_longest is not None else "no evidence",
               "held_to": {"longest_run": longest, "basis": basis}}
        if declared:
            rec["verdict"] = "declared" + (f"; the run of {run} is longer than {whose} {longest}" if run > longest else "")
            if run > longest:
                warnings.append(f"page {page['id']!r} makes a declared run of {run} of {page['composition']}, longer than {whose} longest "
                                f"({longest}): the reason is the model's, the length is the measure ({basis})")
        elif run > longest:
            rec["verdict"] = f"refused: undeclared, and the run of {run} is longer than {whose} longest {longest}"
            refusals.append(f"page {page['id']!r} repeats {page['composition']} undeclared, making a run of {run} where {whose} longest is "
                            f"{longest} ({basis}): declare the parallel in deliberate_parallel or vary the composition")
        else:
            rec["verdict"] = f"undeclared repeat within {whose} longest run ({longest})"
            warnings.append(f"page {page['id']!r} repeats {page['composition']} without a deliberate_parallel reason"
                            + ("" if house_longest is not None else f"; held to {basis}"))
        repeats.append(rec)
    comparison = {}
    if mine["status"] == "measured":
        comparison = {"composition_V": against(mine["composition"]["V"], pooled, "composition"),
                      **{f"{name}_V": {"value": None, "verdict": PLAN_UNREAD,
                                        "house": (pooled.get(name) or {}).get("V", (pooled.get(name) or {}).get("why"))
                                        if pooled["status"] == "measured" else "no evidence"} for name, _ in FACT_MEASURES},
                      "distinct_per_page": {**distinct_against(mine["distinct"]["per_page"], mine["content_pages"], pooled),
                                            "house_decks": pooled.get("distinct_per_page") if pooled["status"] == "measured" else "no evidence"},
                      "longest_run": {"plan": mine["longest_run"], "house": house_longest if house_longest is not None else "no evidence",
                                      "held_to": longest, "basis": basis}}
        c = comparison["composition_V"]
        if c["verdict"].startswith("below"):
            warnings.append(f"composition_V {c['value']} is below the house's 10th percentile deck {c['house_p10_deck']} (pooled {c['house_pooled']}); "
                            "the threshold is unmeasured" + parallels_note(repeats, mine["composition"]))
        d = comparison["distinct_per_page"]
        if d["verdict"].startswith("below"):
            warnings.append(f"distinct compositions per page {d['value']} is below the house's 10th percentile window of {d['window_pages']} pages "
                            f"({d['house_p10_window']}, {d['windows']} windows): the plan reuses compositions more than the house does; the threshold is unmeasured")
    else:
        comparison = {"plan": mine["why"]}
    archetypes = {a["archetype_id"]: a for a in (guide.get("composition") or {}).get("archetypes") or []}
    new = sorted({p["composition"] for p in pages if p["composition"] not in archetypes})
    house_registers = (((guide.get("titles") or {}).get("register")) or {}).get("counts")
    per_page = {}
    for p in pages:
        term = register_term(p["title_register"])
        if house_registers is None:
            per_page[p["id"]] = {"stated": p["title_register"], "term": term, "verdict": "no evidence: /titles/register not completed"}
        elif term is None:
            per_page[p["id"]] = {"stated": p["title_register"], "term": None, "house_counts": house_registers,
                                 "verdict": "no house count: the register is in words, none of the terms the house's titles are coded in"}
        else:
            per_page[p["id"]] = {"stated": p["title_register"], "term": term, "house_count": house_registers.get(term, 0), "house_counts": house_registers,
                                 "verdict": "the house writes none" if not house_registers.get(term) else "a register the house writes"}
            if not house_registers.get(term):
                warnings.append(f"page {p['id']!r} title_register {p['title_register']!r}: the house writes none ({house_registers})")
    coded = [register_term(p["title_register"]) for p in pages]
    return {"status": "refused" if refusals else "pass", "refusals": refusals, "warnings": warnings,
            "plan": mine, "house": house, "comparison": comparison, "repeats": repeats,
            "exhibit_briefs": {p["id"]: len(p["exhibits"]) for p in pages},
            "compositions": {"house_archetypes_used": sorted({p["composition"] for p in pages} - set(new), key=_arch_order), "new": new},
            "title_registers": {"house": house_registers if house_registers is not None else "no evidence: /titles/register not completed",
                                "plan": {**{r: coded.count(r) for r in VOCABULARY["title_register"]},
                                         "in_words": {p["id"]: p["title_register"] for p, t in zip(pages, coded, strict=True) if t is None}},
                                "pages": per_page}}


def register_term(stated: str) -> str | None:
    """The term of the title vocabulary a stated register names, by its slug or its label
    (folded as forms are: case, punctuation, a leading article, a plural s), or None when it
    names none: then it is the model's own words, with no house count to hold it to."""
    key = _form_key(stated)
    for slug, label in VOCABULARY["title_register"].items():
        if key in (_form_key(slug), _form_key(label)):
            return slug
    return None


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
        if key in {f"{name}_V" for name, _ in FACT_MEASURES} and isinstance(v, dict) and v.get("value") is None:
            lines.append(f"  {key}: house {v.get('house')}; {v.get('verdict')}")
        elif isinstance(v, dict) and "verdict" in v:
            house = v.get("house_p10_deck", v.get("house_p10_window"))
            lines.append(f"  {key}: {v.get('value')}, house 10th percentile {house} ({v['verdict']})")
        elif isinstance(v, dict):
            lines.append(f"  {key}: " + ", ".join(f"{k} {x}" for k, x in v.items()))
        else:
            lines.append(f"  {key}: {v}")
    decks = (report.get("house") or {}).get("decks") or []
    if len(decks) == 1:
        lines.append("  note: the house is one deck, so each 10th percentile is that deck's own value (pool sister decks with --house-deck)")
    regs = report.get("title_registers") or {}
    if regs:
        lines.append(f"  title registers: plan {regs.get('plan')}, house {regs.get('house')}")
    lines.append(f"  full report: {out}" if out else "  full report: pass -o FILE or --json")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
