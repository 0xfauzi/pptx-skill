#!/usr/bin/env python3
"""The leakage report: content of the past decks found in a new deck.

    leakage.py NEW.pptx --past REF.pptx [--past OTHER.pdf ...] [--brief brief.txt ...]
               [--computed figures.txt ...] [--template tpl.pptx] [-o leakage.json]

The build runs this on every deck it writes (its `leakage` field), against the reference
and the reference decks it was given; this command runs it on any deck. A new deck may carry
only what the user supplied for it and the reference's own furniture. Every page of the new
deck is compared with every page of the past decks, and each match is listed on the page
where it appears:

- phrase: a run of PHRASE_WORDS or more words that a past page also carries;
- name: two or more capitalised words in a row (a client, a bank, a product) that a past
  page also carries;
- figure: a number with a unit or of three or more digits ($4.1, 40%, 2016, 11.40) that a
  past page also carries.

Each finding is ranked by rarity. A name or phrase whose words run in that order in a
public deck of another firm (the judge's panel in refs/files, past decks and their twins
left out), or a name every word of which those decks use, is a term of the trade, not
this reference's content; a round figure (at most two significant
digits, the second 0 or 5: 10%, 15%, $1,000, 4.0x) and a year carry no information about
where they came from. Those are listed once under `low`, with what to do; everything else
is `distinctive`, listed per page, rarest first (most words no public deck uses).

Not reported: chrome, which is any text a past deck repeats on at least CHROME_SHARE of its
pages (the bank name in the footer, a confidentiality line) and the text the template
itself draws; and anything found in a --brief file (the user's brief and data, as text).
A figure found in a --computed file (the output of the model's own arithmetic over the
user's data, as text) is not distinctive either, and not silent: it is listed under
`declared_computed` with the past pages it coincides with. A figure matches on its value
and its unit, however the thousands and decimals are spelled: 36% on the page is matched by
36% in the file, never by a bare 36 (a JSON count is not a percentage), so the file writes
each figure with the unit the page shows. Only figures: a name or phrase
in a --computed file is still reported, since arithmetic produces no names.
Pictures are compared by hash: a picture of a past deck in the new deck is listed unless
the template carries it too (a logo on the master).

The thresholds are unmeasured choices. The report is a list for the model and the user,
not a gate: each finding is removed, or confirmed as supplied for this deck.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))

PHRASE_WORDS = 5  # unmeasured
CHROME_SHARE = 0.5  # unmeasured: repeated on half the pages or more is the reference's furniture
_TOKEN = re.compile(r"[$€£]?\d[\d,.]*%?x?|[A-Za-z][A-Za-z&'\-]*")
_FIGURE = re.compile(r"^[$€£]\d|\d\d%$|^\d{3,}|\d[.,]\d")
#: a figure: its currency, its number (thousands groups only as three digits after a comma,
#: so a JSON list [36,24] reads as two numbers, never as 3624) and its unit. A unit is part
#: of the value: a count of 36 is not 36%, so a bare number never stands for a percentage
_FIGURE_PARTS = re.compile(r"([$€£]?)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(%|x(?![A-Za-z]))?")


def _figure_keys(text: str) -> list[tuple[str, str, str]]:
    """Every figure `text` writes as (currency, number, unit), one spelling per value: no
    thousands commas, no trailing decimal zeros (24.0 is 24), the unit kept ("36%" is
    ('', '36', '%'), a JSON 36 is ('', '36', ''))."""
    out = []
    for cur, n, unit in _FIGURE_PARTS.findall(text):
        n = n.replace(",", "")
        out.append((cur, n.rstrip("0").rstrip(".") if "." in n else n, unit))
    return out


_STOP_CAPS = {"The", "A", "An", "In", "On", "Of", "And", "For", "To", "At", "By", "With", "From", "As", "Is", "Our", "We", "This", "That"}


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text or "")


def norm(word: str) -> str:
    return word.casefold().rstrip(".,")


def page_texts(path: str) -> list[list[str]]:
    """The text each page draws, as a list of strings (paragraphs, cells), slide layer only
    for a .pptx (master and layout text is the template's), every word for a PDF."""
    if path.lower().endswith(".pdf"):
        import annotate
        return [[" ".join(w for _, w in words)] for words in annotate.pdf_words(path)]
    from pptx_tools import slide_text
    out = []
    for e in slide_text(path):
        strings = [e["title"] or ""] + [b["text"] for b in e["blocks"]] + [c for t in e["tables"] for row in t["rows"] for c in row]
        out.append([s for s in strings if s])
    return out


def features(strings: list[str]) -> dict[str, set[tuple[str, ...]]]:
    """Phrases, names and figures in a page's strings, normalised. Phrases never cross a
    string (a cell, a paragraph), so two cells side by side do not make a phrase."""
    phrase: set[tuple[str, ...]] = set()
    name: set[tuple[str, ...]] = set()
    figure: set[tuple[str, ...]] = set()
    for s in strings:
        for line in s.split("\n"):
            words = tokens(line)
            low = [norm(w) for w in words]
            for i in range(len(low) - PHRASE_WORDS + 1):
                phrase.add(tuple(low[i:i + PHRASE_WORDS]))
            run: list[str] = []
            for w in words + [""]:
                if w[:1].isupper() and w not in _STOP_CAPS and len(w) > 1:
                    run.append(norm(w))
                    continue
                if len(run) >= 2:
                    name.add(tuple(run))
                run = []
            figure.update((norm(w),) for w in words if _FIGURE.search(w))
    return {"phrase": phrase, "name": name, "figure": figure}


def chrome_of(pages: list[dict[str, set]]) -> dict[str, set]:
    """Features a deck repeats on at least CHROME_SHARE of its pages: its furniture."""
    out: dict[str, set] = {"phrase": set(), "name": set(), "figure": set()}
    if len(pages) < 2:
        return out
    for kind in out:
        counts: dict[tuple, int] = {}
        for p in pages:
            for f in p[kind]:
                counts[f] = counts.get(f, 0) + 1
        out[kind] = {f for f, n in counts.items() if n >= CHROME_SHARE * len(pages)}
    return out


BACKGROUND_DIR = Path(__file__).resolve().parent.parent / "refs" / "files"


def _twin_key(path: str | Path) -> str:
    return Path(path).stem.lower()


def background(past: list[str]) -> tuple[list[tuple[str, str]], str]:
    """The public decks of other firms (refs/files, fetched by refs/fetch.sh), each as
    its words normalised and joined (" w1 w2 ... ", one line break between strings),
    with the past decks and their twins (the same stem: a pptx and its PDF rendition)
    left out; and a note naming the basis. A finding is a term of the trade when its words
    run in that order in such a deck, in any case and inside any longer name."""
    skip = {_twin_key(p) for p in past} | {str(Path(p).resolve()) for p in past}
    decks: list[tuple[str, str]] = []
    unread: list[str] = []
    if BACKGROUND_DIR.is_dir():
        for f in sorted(BACKGROUND_DIR.iterdir()):
            if f.suffix.lower() not in (".pptx", ".pdf") or _twin_key(f) in skip or str(f.resolve()) in skip:
                continue
            try:
                strings = [x for page in page_texts(str(f)) for x in page]
            except Exception as error:  # noqa: BLE001 - an unreadable public deck is left out, and named in the note
                unread.append(f"{f.name} ({type(error).__name__})")
                continue
            words = "\n".join(" " + " ".join(norm(w) for w in tokens(line)) + " " for x in strings for line in x.split("\n"))
            decks.append((f.name, words))
    note = (f"{len(decks)} public decks of other firms in {BACKGROUND_DIR}" + (f"; not read: {', '.join(unread)}" if unread else "") if decks
            else f"not measured: no public decks in {BACKGROUND_DIR} (run refs/fetch.sh); terms of the trade cannot be told from this reference's own words")
    return decks, note


def _figure_value(text: str) -> float | None:
    t = text.replace("$", "").replace("€", "").replace("£", "").replace(",", "").rstrip("%x").rstrip(".")
    try:
        return float(t)
    except ValueError:
        return None


def round_or_year(text: str) -> str | None:
    """Why a figure says nothing about its source: a year, or a round figure."""
    if re.fullmatch(r"(19|20)\d\d", text):
        return "a year"
    v = _figure_value(text)
    if v is None or v == 0:
        return None
    digits = re.sub(r"[^0-9]", "", f"{abs(v):.10g}").strip("0")
    if len(digits) <= 1 or (len(digits) == 2 and digits[1] in "05"):
        return "a round figure"
    return None


def rarity(kind: str, key: tuple, text: str, decks: list[tuple[str, str]], vocabulary: set[str]) -> dict:
    """low or distinctive, with the reason. A figure: low when round or a year. A name or
    phrase: low when its words run in that order in a public deck of another firm; a name
    is low too when every one of its words is in those decks' vocabulary (senior notes,
    debt ebitda: products and ratios), and distinctive when any word is not (a company, a
    place, a person). `rare_words` ranks the distinctive ones."""
    if kind == "figure":
        why = round_or_year(text)
        return {"tier": "low", "why": why} if why else {"tier": "distinctive", "rare_words": 1}
    needle = " " + " ".join(key) + " "
    found = [name for name, words in decks if needle in words]
    if found:
        return {"tier": "low", "why": f"a term of the trade: also in {len(found)} public deck(s) of other firms ({', '.join(found[:2])})"}
    rare = [w for w in key if w not in vocabulary]
    if kind == "name" and decks and not rare:
        return {"tier": "low", "why": "a term of the trade: every word of it is in the public decks of other firms"}
    return {"tier": "distinctive", "rare_words": len(rare)}


def media_hashes(path: str) -> dict[str, str]:
    if not path.lower().endswith(".pptx"):
        return {}
    with zipfile.ZipFile(path) as z:
        return {hashlib.sha256(z.read(n)).hexdigest(): n for n in z.namelist() if n.startswith("ppt/media/")}


def leakage(new: str, past: list[str], briefs: list[str] | None = None, template: str | None = None, page_ids: list | None = None,
            computed: list[str] | None = None, furniture: list[str] | None = None) -> dict:
    briefs = briefs or []
    computed = computed or []
    computed_text = [Path(c).read_text(errors="replace") for c in computed]
    declared = {k for t in computed_text for k in _figure_keys(t)}
    coincident: dict[str, dict] = {}
    allowed = features([Path(b).read_text(errors="replace") for b in briefs])
    excluded: dict[str, set] = {k: set(v) for k, v in allowed.items()}
    for k, v in features(list(furniture or [])).items():
        excluded[k] |= v  # the chrome the build drew (its text lines), furniture like the template's
    if template:
        for strings in page_texts(template):
            for k, v in features(strings).items():
                excluded[k] |= v
    past_pages: list[tuple[str, int, dict]] = []
    chrome_counts = {}
    for deck in past:
        pages = [features(s) for s in page_texts(deck)]
        chrome = chrome_of(pages)
        chrome_counts[Path(deck).name] = {k: len(v) for k, v in chrome.items()}
        for k, v in chrome.items():
            excluded[k] |= v
        past_pages += [(Path(deck).name, i + 1, p) for i, p in enumerate(pages)]
    decks, basis = background(past)
    vocabulary = {w for _, words in decks for w in words.split()}
    report_pages = []
    low: dict[str, dict] = {}
    for i, strings in enumerate(page_texts(new)):
        mine = features(strings)
        found = []
        for kind in ("name", "phrase", "figure"):
            for f in sorted(mine[kind] - excluded[kind]):
                where = [f"{d} p{n}" for d, n, p in past_pages if f in p[kind]]
                if not where:
                    continue
                text = " ".join(f)
                keys = _figure_keys(text) if kind == "figure" else []
                if len(keys) == 1 and keys[0] in declared:
                    entry = coincident.setdefault(text, {"text": text, "past": where[:3], "pages": [], "computed_as": "".join(keys[0])})
                    entry["pages"].append(i + 1)
                    continue
                rank = rarity(kind, f, text, decks, vocabulary)
                if rank["tier"] == "low":
                    entry = low.setdefault(text, {"kind": kind, "text": text, "why": rank["why"], "pages": []})
                    entry["pages"].append(i + 1)
                    continue
                found.append({"kind": kind, "text": text, "past": where[:3] + ([f"and {len(where) - 3} more"] if len(where) > 3 else []),
                              "past_pages": len(where), "rare_words": rank["rare_words"]})
        if found:
            # rarest first: most words no public deck uses, then a name before a phrase before a figure
            found.sort(key=lambda x: (-x["rare_words"], ("name", "phrase", "figure").index(x["kind"]), x["past_pages"]))
            report_pages.append({"page": i + 1, **({"id": page_ids[i]} if page_ids and i < len(page_ids) else {}), "findings": found})
    template_media = set(media_hashes(template)) if template else set()
    past_media = {h: f"{Path(d).name}:{n}" for d in past for h, n in media_hashes(d).items()}
    images = [{"new": n, "past": past_media[h]} for h, n in media_hashes(new).items() if h in past_media and h not in template_media]
    distinctive = sum(len(p["findings"]) for p in report_pages)
    if report_pages or images:
        verdict = (f"possible carry-over: {distinctive} distinctive finding(s){' and ' + str(len(images)) + ' picture(s)' if images else ''}: "
                   "remove each, or confirm the user supplied it for this deck")
    elif low:
        verdict = f"no distinctive carry-over; {len(low)} low finding(s): keep each that your own data or brief produces"
    else:
        verdict = "clean"
    return {"past_decks": [Path(d).name for d in past], "briefs": [Path(b).name for b in briefs], "computed": [Path(c).name for c in computed],
            "declared_computed": sorted(coincident.values(), key=lambda x: x["text"]),
            "findings": distinctive, "distinctive": distinctive, "low": len(low), "pages": report_pages, "images": images,
            "low_findings": sorted(low.values(), key=lambda x: x["text"]),
            "what_to_do": {"distinctive": "a name, phrase or figure of the past deck found on no public deck of another firm: remove it, "
                                          "or confirm the user supplied it (pass their brief and data with --brief and it is not listed)",
                           "low": "a term of the trade, a round figure or a year: carry-over only if it came from the past deck rather than from "
                                  "your data; keep each one your data or brief produces, and check any figure you did not compute"},
            "rarity_basis": basis,
            "chrome_excluded": chrome_counts,
            "images_checked": "pptx media by sha256" + ("" if all(d.lower().endswith(".pptx") for d in past) else "; a PDF's pictures are not checked"),
            "method": f"names (2+ capitalised words), figures and {PHRASE_WORDS}-word phrases of each new page found on a past page; "
                      f"chrome (on {CHROME_SHARE:.0%}+ of a past deck's pages), template text and --brief text excluded; thresholds unmeasured",
            "verdict": verdict}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new")
    ap.add_argument("--past", action="append", required=True, help="a past deck used as evidence (.pptx or .pdf), repeatable")
    ap.add_argument("--brief", action="append", default=[], help="the user's brief or data as a text file: its words are allowed")
    ap.add_argument("--computed", action="append", default=[], help="figures your own arithmetic produced from the user's data, as text: "
                    "a matching figure is listed under declared_computed, not as distinctive")
    ap.add_argument("--template", default=None, help="the template the deck was built on: its own text and pictures are furniture")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out")
    report = leakage(args.new, args.past, args.brief, args.template, computed=args.computed)
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    import cli
    cli.run(main)
