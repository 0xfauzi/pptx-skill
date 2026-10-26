#!/usr/bin/env python3
"""The section plan and the reference's variety.

    plan.py check plan.json --guide guide.json [-o check.json]
    plan.py reference --guide guide.json

One definition of variety serves three readers: the guide (the reference's own content
pages, extract_style.py and complete_guide.py), the plan (this script's `check`) and the
build (build_deck.py, the solved pages). Over the adjacent pairs of a sequence of pages:

- V (composition) = pairs whose composition differs / pairs;
- V (structures) = pairs whose exhibit structure differs / pairs. A page's exhibit
  structure is read from the file (ooxml.exhibit_facts: its native charts by the plot
  types and series counts the chart XML states, its tables, its pictures, drawn shapes,
  and how many panels): the reference's off its own pages, the build's off the file it
  wrote. Nobody names it, so renaming an exhibit cannot move it; a pair with a page whose
  structure was not read is left out (and counted as unread, never as a change or a
  repeat). A plan declares no structure: it describes each exhibit in a brief;
- V (kinds) = the same over each page's exhibit kinds (exhibit_facts' `kinds`: the
  structure with every chart read as "chart"), where a section that sets a table beside a
  chart on page after page reads as the repeat it is whatever the charts plot;
- distinct compositions per page = distinct compositions / pages, held against the
  reference's 10th percentile window of the same number of pages (distinct_windows);
- the longest run of one composition, and every run of two or more with its pages.

Pairs are counted only between pages the reader sees next to each other: a sequence breaks
at a page that is not content (a cover, a divider, a disclaimer) and at a page that was not
read, so with one unbroken sequence pairs = n - 1. A deck with no stretch of
VARIETY_MIN_PAGES content pages in a row is no evidence, and every figure says so rather
than reading 0 or 1. The guide is proven at the boundary (read_reference_guide). The skill
takes one reference deck: a user who gives several names the one to follow, or is asked.

A guide made with no reference (extract_style.py --blank) has no variety to hold a plan
to: every comparison reports "no reference" (has_reference is the one test), never a
warning, a score or a value taken from the corpus in its place.

plan.json (every key required; `deliberate_parallel` is null on a page that does not
repeat the previous page's composition, and the reason in words on one that does):

{
 "schema": "pptx-skill section plan v2",
 "reference_sha256": "<the guide's reference.sha256: archetype ids belong to one reference; null with no reference>",
 "pages": [
  {"id": "<the deck slide id it becomes>", "intent": "...",
   "message": "the page's message, or what the reader looks up on a reference page",
   "composition": "arch-3 | new:<name>",
   "title_register": "the title's register in words, or a term the reference's titles are coded in",
   "deliberate_parallel": null,
   "exhibits": [<one brief per exhibit; [] on a page that holds none>]}
 ]
}

An exhibit brief, every field in the model's own words (nothing is chosen from a list).
Design starts from the reader and the data; a reference governs the look only:

{"reader_must_see": "what the reader must see on it",
 "comparison": "what is compared against what",
 "data": "the data's shape, in words",
 "forms_considered": [{"form": "...", "reason": "why not, or why"}, ...],   (two or more distinct forms)
 "chosen_form": "...", "why": "why this form shows what the reader must see",
 "marks": "what will be marked, where the claim lives, and why",
 "in_reference_look": "optional: how the reference's look (faces, colours, spacing, how its marks are drawn) applies to the chosen form"}

`check` reads a brief for completeness only, never for what it says: every required field
present, each text field a phrase of at least BRIEF_MIN_WORDS distinct words (a form's name
at least one; placeholders such as TBD or n/a and a lone letter do not count), at least two
distinct forms considered (_form_key: case, punctuation, fullwidth letters, a leading
article and a plural s folded; a form spelt in two scripts refused), a chosen form that is
one of them, `in_reference_look` a phrase when given (and not given on a guide with no
reference), and no brief given twice across the plan. The key it replaced,
`nearest_house_exhibit`, is refused by name.

A title register is the model's words. When it names a term the reference's titles are
coded in (references/page_craft_vocabulary.json, by slug or label: register_term), the
reference's count of that term is shown beside it; otherwise it is reported as no count,
with the reference's counts beside it. Only a register that is not words is refused.

`check` refuses (exit 1), by name: a guide made before the current readings
(old_guide_error), a plan that is not this shape, a brief that is not complete, a title
register that is not words, an archetype the guide does not hold, and a reason on a page
that repeats nothing. The reference's habits are evidence shown beside each choice, never a
refusal: it warns when an undeclared repeat makes a run longer than the reference's
longest, when the plan's V falls below the reference's (its 10th percentile is the deck's
own value), when its distinct compositions per page fall below the reference's 10th
percentile window, and when a coded register is one the reference never writes; each
warning is a departure answered in one line in the report. With no run evidence in the
reference, no run is judged and the report says so. Those thresholds are choices, not
measurements: nothing has measured what V a reader calls samey.
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
WARN_PERCENTILE = 0.1  # unmeasured: the reference's 10th percentile window, a choice and not a reader's threshold
PLAN_SCHEMA = "pptx-skill section plan v2"
PAGE_KEYS = ("id", "intent", "message", "composition", "title_register", "deliberate_parallel", "exhibits")
BRIEF_KEYS = ("reader_must_see", "comparison", "data", "forms_considered", "chosen_form", "why", "marks")
#: optional: how the reference's look applies to the chosen form (never on a guide with no reference)
LOOK_KEY = "in_reference_look"
#: keys a plan once took, each refused by name with what replaced it
RENAMED_BRIEF_KEYS = {"nearest_house_exhibit": (
    "nearest_house_exhibit was removed: an exhibit's design starts from reader_must_see, comparison and data, and a reference "
    "governs its look only; say how the reference's look applies to the chosen form under in_reference_look (optional, a phrase), "
    "or leave it out")}
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
     "measure sees them: the reference is held to the more lenient count."),
    ("On a PDF the reader's text blocks stand in for shapes, and a page set as many small blocks rarely matches another at 0.5, so a "
     "PDF reference can read every page as its own archetype."),
    ("V counts adjacent pairs only: an arrangement used on every other page (A B A C A) reads 1.0; distinct compositions per page "
     "is the figure that shows it."),
    ("A picture carries no structure: a reference that pastes its charts and tables as pictures reads every such page as 'picture', so its "
     "structure V is low and the build is held to a lenient line; what the picture shows is the digest's reading, never measured."),
    ("A PDF states rectangles, paths and text, never a chart or a table, so a PDF reference's structure reads only pictures, drawn shapes "
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
    sequence): the reference's distinct-per-page at the length of the sequence it is held against,
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


def distinct_against(value: float, n: int, ref: dict) -> dict:
    """A sequence's distinct compositions per page against the reference's 10th percentile
    window of the same length (distinct_windows): how an A B A B A sequence is held to the
    reference."""
    if ref.get("status") == NO_REFERENCE:
        return {"value": value, "verdict": NO_REFERENCE}
    if ref.get("status") != "measured":
        return {"value": value, "verdict": "no evidence in the reference: " + ref["why"]}
    windows = distinct_windows(ref["sequences"], n)
    if not windows:
        return {"value": value, "verdict": f"no evidence in the reference: no stretch of {n} content pages in a row"}
    p10 = round(percentile(windows, WARN_PERCENTILE), 3)
    return {"value": value, "reference_p10_window": p10, "windows": len(windows), "window_pages": n,
            "verdict": "below the reference's 10th percentile window" if value < p10 else "at or above the reference's 10th percentile window",
            "threshold": "unmeasured: the 10th percentile window is a choice"}


# --- the reference, from a guide ---------------------------------------------------------------

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


#: the verdict every comparison with a reference gives on a guide made with no reference
NO_REFERENCE = "no reference"
#: reference.format of a guide made with no reference deck (extract_style.py --blank)
NO_REFERENCE_FORMAT = "none"
#: the provenance of every value on a guide made with no reference: chosen by the model, not
#: inferred from evidence, so nothing in it reads as a reference's habit
MODEL_CHOICE = "model_choice"


def has_reference(guide, where: str = "guide") -> bool:
    """Whether the guide was made from a reference deck, proven at the boundary: a draft from
    extract_style.py names its reference's sha256; a blank draft (extract_style.py --blank)
    says reference.format "none" and names no sha256. Anything else is refused by name,
    since a guide that cannot say which it is would be read as one or the other in silence."""
    ref = guide.get("reference") if isinstance(guide, dict) else None
    if not isinstance(ref, dict):
        raise Refused(f"{where}: not a style guide (no reference object): a guide is a draft from extract_style.py, made from a "
                      "reference deck or with --blank")
    sha = ref.get("sha256")
    if ref.get("format") == NO_REFERENCE_FORMAT:
        if sha is not None:
            raise Refused(f"{where}: reference.format is {NO_REFERENCE_FORMAT!r} (no reference) yet names sha256 {sha!r}; re-make the draft")
        return False
    if isinstance(sha, str) and sha:
        return True
    raise Refused(f"{where}: not a style guide (no reference.sha256, and not a blank draft): a guide is a draft from extract_style.py, "
                  "made from a reference deck or with --blank")


def read_reference_guide(guide, where: str) -> dict:
    """The guide proven at the boundary: a style guide (has_reference), whose variety, when
    it carries pages, lists each page once with its number, composition and triage, names its
    content pages among them, and gives each page's exhibit facts a structure string.
    Anything else is refused by name: a plan, a list, a guide from before the variety
    measure, and a guide made before the current readings (old_guide_error) are not evidence
    about the reference's pages."""
    has_reference(guide, where)
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
    check, build), not only where a reference precedent is looked up."""
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


def deck_variety(guide: dict) -> dict:
    """The reference deck's variety measured, or no evidence with the reason the guide gives,
    or "no reference" on a guide made with none."""
    if not has_reference(guide):
        return {"deck": None, "content_pages": 0, "pairs": 0, "status": NO_REFERENCE,
                "why": "the guide was made with no reference deck: no variety to hold a plan or a build to"}
    name = Path(guide["reference"].get("file") or "reference").name
    variety = guide.get("variety")
    if not isinstance(variety, dict) or not variety.get("pages"):
        why = (variety or {}).get("why") if isinstance(variety, dict) else None
        return {"deck": name, "content_pages": 0, "pairs": 0, "status": "no evidence",
                "why": why or "the guide carries no variety pages (extracted before plan.py, or a raster reference with no shapes): re-run extract_style.py"}
    return measure_deck(name, content_segments(variety))


def reference_variety(guide: dict, where: str = "--guide") -> dict:
    """The reference's variety, the guide proven at the boundary first."""
    read_reference_guide(guide, where)
    return deck_variety(guide)


# --- the plan --------------------------------------------------------------------------------

def read_plan(plan, guide: dict) -> list[dict]:
    """The plan proven at the boundary: every page every key, every exhibit brief complete
    (brief_errors), every title register in the title vocabulary, every archetype one the
    guide holds. All problems in one refusal."""
    errors: list[str] = []
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA or not isinstance(plan.get("pages"), list):
        raise Refused(f"plan: expected {{\"schema\": \"{PLAN_SCHEMA}\", \"reference_sha256\", \"pages\": [...]}}")
    sha = guide["reference"]["sha256"] if has_reference(guide) else None
    if "reference_sha256" not in plan:
        raise Refused(f"plan: reference_sha256 not answered: the guide's reference.sha256 ({sha}), or null on a guide made with no reference")
    if plan["reference_sha256"] != sha:
        raise Refused(f"plan: reference_sha256 {plan['reference_sha256']!r} is not this guide's reference ({sha}); archetype ids belong to one reference"
                      + ("; with no reference it is null" if sha is None else ""))
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
            errors.append(f"{where} title_register: the title's register in words (or a term the reference's titles are coded in: "
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
    """An exhibit brief checked for completeness, never for what it says: every key (BRIEF_KEYS),
    the optional LOOK_KEY and no other (a removed key refused by name, RENAMED_BRIEF_KEYS);
    each text field a phrase of BRIEF_MIN_WORDS words or more (a form's name one word or more);
    forms_considered a list of {"form", "reason"} naming at least two distinct forms."""
    if not isinstance(brief, dict):
        return [f"{where}: an exhibit brief ({', '.join(BRIEF_KEYS)}, optional {LOOK_KEY}), not {type(brief).__name__}"]
    out: list[str] = []
    missing = [k for k in BRIEF_KEYS if k not in brief]
    out += [f"{where}: {RENAMED_BRIEF_KEYS[k]}" for k in sorted(set(brief) & set(RENAMED_BRIEF_KEYS))]
    stray = sorted(set(brief) - set(BRIEF_KEYS) - {LOOK_KEY} - set(RENAMED_BRIEF_KEYS))
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
    if LOOK_KEY in brief:
        if not has_reference(guide):
            out.append(f"{where} {LOOK_KEY}: the guide was made with no reference, so there is no reference look to apply; leave it out")
        else:
            e = _phrase_error(brief[LOOK_KEY], f"{where} {LOOK_KEY}", BRIEF_MIN_WORDS)
            if e:
                out.append(e + " (how the reference's look applies to the chosen form)")
    return out


def _arch_order(a: str) -> tuple:
    m = re.match(r"arch-(\d+)$", a)
    return (0, int(m.group(1))) if m else (1, a)


def plan_segments(pages: list[dict]) -> list[list[dict]]:
    return [[{"slide": i, "id": p["id"], "composition": p["composition"], **{key: None for _, key in FACT_MEASURES}} for i, p in enumerate(pages, 1)]]


PLAN_UNREAD = "a plan describes its exhibits in briefs and declares no structure: the build reads the structure from the file it writes"


def against(value: float | None, ref: dict, key: str) -> dict:
    """A plan or build figure against the reference deck's own (reference_variety)."""
    if ref.get("status") == NO_REFERENCE:
        return {"value": value, "verdict": NO_REFERENCE}
    h = ref.get(key) if ref.get("status") == "measured" else None
    if value is None:
        return {"value": None, "verdict": "no evidence on this side"}
    if not h or "V" not in h:
        return {"value": value, "verdict": "no evidence in the reference: " + ((h or ref).get("why") or "not measured")}
    verdict = "below the reference's" if value < h["V"] else "at or above the reference's"
    return {"value": value, "reference_V": h["V"], "verdict": verdict,
            "threshold": "unmeasured: the reference's own V is a choice of line; no reader has measured where V reads as samey"}


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


def check(plan, guide: dict) -> dict:
    pages = read_plan(plan, guide)
    ref = reference_variety(guide)
    mine = measure_deck("plan", plan_segments(pages), PLAN_UNREAD)
    refusals: list[str] = []
    warnings: list[str] = []
    referenced = ref["status"] != NO_REFERENCE
    longest = ref.get("longest_run") if ref["status"] == "measured" else None
    # the reference's longest run is evidence beside a repeat, never a ban; with no run
    # evidence (or no reference) no run is judged, and nothing stands in for it
    held = (longest if longest is not None else NO_REFERENCE if not referenced
            else f"not judged: the reference's longest run is no evidence ({ref.get('why')})")
    repeats = []
    run = 1
    for prev, page in pairwise(pages):
        run = run + 1 if page["composition"] == prev["composition"] else 1
        if run == 1:
            continue
        declared = page["deliberate_parallel"]
        rec = {"pages": [prev["id"], page["id"]], "composition": page["composition"], "run_length": run, "deliberate_parallel": declared,
               "reference_longest_run": held}
        over = longest is not None and run > longest
        if declared:
            rec["verdict"] = "declared" + (f"; the run of {run} is longer than the reference's {longest}" if over else "")
        else:
            rec["verdict"] = "undeclared" + (f"; the run of {run} is longer than the reference's {longest}" if over else "")
        if over:
            warnings.append(f"page {page['id']!r} makes a{' declared' if declared else 'n undeclared'} run of {run} of {page['composition']}, "
                            f"longer than the reference's longest ({longest}): a departure; answer it in one line in the report"
                            + ("" if declared else ", or declare the parallel in deliberate_parallel"))
        elif not declared:
            warnings.append(f"page {page['id']!r} repeats {page['composition']} without a deliberate_parallel reason: was the repeat meant?")
        repeats.append(rec)
    comparison: dict = {}
    if mine["status"] == "measured":
        comparison = {"composition_V": against(mine["composition"]["V"], ref, "composition"),
                      **{f"{name}_V": {"value": None, "verdict": PLAN_UNREAD,
                                        "reference": (ref.get(name) or {}).get("V", (ref.get(name) or {}).get("why"))
                                        if ref["status"] == "measured" else ref["status"]} for name, _ in FACT_MEASURES},
                      "distinct_per_page": {**distinct_against(mine["distinct"]["per_page"], mine["content_pages"], ref),
                                            "reference": (ref.get("distinct") or {}).get("per_page") if ref["status"] == "measured" else ref["status"]},
                      "longest_run": {"plan": mine["longest_run"], "reference": held}}
        c = comparison["composition_V"]
        if c["verdict"].startswith("below"):
            warnings.append(f"composition_V {c['value']} is below the reference's {c['reference_V']}: a departure (the line is unmeasured); "
                            "answer it in one line in the report" + parallels_note(repeats, mine["composition"]))
        d = comparison["distinct_per_page"]
        if d["verdict"].startswith("below"):
            warnings.append(f"distinct compositions per page {d['value']} is below the reference's 10th percentile window of {d['window_pages']} pages "
                            f"({d['reference_p10_window']}, {d['windows']} windows): the plan reuses compositions more than the reference does (the "
                            "line is unmeasured); answer it in one line in the report")
    else:
        comparison = {"plan": mine["why"]}
    archetypes = {a["archetype_id"]: a for a in (guide.get("composition") or {}).get("archetypes") or []}
    new = sorted({p["composition"] for p in pages if p["composition"] not in archetypes})
    ref_registers = (((guide.get("titles") or {}).get("register")) or {}).get("counts") if referenced else None
    per_page = {}
    for p in pages:
        term = register_term(p["title_register"])
        if not referenced:
            per_page[p["id"]] = {"stated": p["title_register"], "term": term, "verdict": NO_REFERENCE}
        elif ref_registers is None:
            per_page[p["id"]] = {"stated": p["title_register"], "term": term, "verdict": "no evidence: /titles/register not completed"}
        elif term is None:
            per_page[p["id"]] = {"stated": p["title_register"], "term": None, "reference_counts": ref_registers,
                                 "verdict": "no count: the register is in words, none of the terms the reference's titles are coded in"}
        else:
            per_page[p["id"]] = {"stated": p["title_register"], "term": term, "reference_count": ref_registers.get(term, 0),
                                 "reference_counts": ref_registers,
                                 "verdict": "the reference writes none" if not ref_registers.get(term) else "a register the reference writes"}
            if not ref_registers.get(term):
                warnings.append(f"page {p['id']!r} title_register {p['title_register']!r}: the reference writes none ({ref_registers}): a departure; "
                                "answer it in one line in the report")
    coded = [register_term(p["title_register"]) for p in pages]
    return {"status": "refused" if refusals else "pass", "refusals": refusals, "warnings": warnings,
            "plan": mine, "reference": ref, "comparison": comparison, "repeats": repeats,
            "exhibit_briefs": {p["id"]: len(p["exhibits"]) for p in pages},
            "compositions": {"reference_archetypes_used": sorted({p["composition"] for p in pages} - set(new), key=_arch_order), "new": new},
            "title_registers": {"reference": (ref_registers if ref_registers is not None else "no evidence: /titles/register not completed")
                                if referenced else NO_REFERENCE,
                                "plan": {**{r: coded.count(r) for r in VOCABULARY["title_register"]},
                                         "in_words": {p["id"]: p["title_register"] for p, t in zip(pages, coded, strict=True) if t is None}},
                                "pages": per_page}}


def register_term(stated: str) -> str | None:
    """The term of the title vocabulary a stated register names, by its slug or its label
    (folded as forms are: case, punctuation, a leading article, a plural s), or None when it
    names none: then it is the model's own words, with no count of the reference's beside it."""
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


#: subcommands a script once took, each refused by name with its new spelling
RENAMED_COMMANDS = {"house": "plan.py house is now plan.py reference (the reference's variety); the skill takes one reference deck, so nothing is pooled"}


def main(argv: list[str]) -> int:
    if argv and argv[0] in RENAMED_COMMANDS:
        raise Refused(f"refused: {RENAMED_COMMANDS[argv[0]]}")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate a plan against the guide and report its variety beside the reference's")
    c.add_argument("plan")
    c.add_argument("--guide", required=True, help="the guide the section is built with (its archetype ids are the plan's)")
    c.add_argument("-o", "--out", default=None, help="write the full report as JSON")
    c.add_argument("--json", action="store_true", help="print the full report instead of the verdict")
    h = sub.add_parser("reference", help="the reference's variety")
    h.add_argument("--guide", required=True)
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out")
    guide = load(args.guide)
    if args.cmd == "reference":
        print(json.dumps(reference_variety(guide), indent=1))
        return 0
    try:
        report = check(load(args.plan), guide)
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
    beside the reference's; the whole report is the JSON (-o, or --json)."""
    lines = [f"plan check: {report['status']}"]
    lines += [f"  refused: {r}" for r in report.get("refusals") or []]
    lines += [f"  warning: {w}" for w in report.get("warnings") or []]
    for key, v in (report.get("comparison") or {}).items():
        if key in {f"{name}_V" for name, _ in FACT_MEASURES} and isinstance(v, dict) and v.get("value") is None:
            lines.append(f"  {key}: reference {v.get('reference')}; {v.get('verdict')}")
        elif isinstance(v, dict) and "verdict" in v:
            line = v.get("reference_V", v.get("reference_p10_window"))
            lines.append(f"  {key}: {v.get('value')}" + (f", reference {line}" if line is not None else "") + f" ({v['verdict']})")
        elif isinstance(v, dict):
            lines.append(f"  {key}: " + ", ".join(f"{k} {x}" for k, x in v.items()))
        else:
            lines.append(f"  {key}: {v}")
    regs = report.get("title_registers") or {}
    if regs:
        lines.append(f"  title registers: plan {regs.get('plan')}, reference {regs.get('reference')}")
    lines.append(f"  full report: {out}" if out else "  full report: pass -o FILE or --json")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
