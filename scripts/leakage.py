#!/usr/bin/env python3
"""The leakage report: content of the past decks found in a new deck.

    leakage.py NEW.pptx --past REF.pptx [--past OTHER.pdf ...] [--brief brief.txt ...]
               [--template tpl.pptx] [-o leakage.json]

The build runs this on every deck it writes (its `leakage` field), against the reference
and the house decks it was given; this command runs it on any deck. A new deck may carry
only what the user supplied for it and the house's own furniture. Every page of the new
deck is compared with every page of the past decks, and each match is listed on the page
where it appears:

- phrase: a run of PHRASE_WORDS or more words that a past page also carries;
- name: two or more capitalised words in a row (a client, a bank, a product) that a past
  page also carries;
- figure: a number with a unit or of three or more digits ($4.1, 40%, 2016, 11.40) that a
  past page also carries.

Not reported: chrome, which is any text a past deck repeats on at least CHROME_SHARE of its
pages (the bank name in the footer, a confidentiality line) and the text the template
itself draws; and anything found in a --brief file (the user's brief and data, as text).
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
CHROME_SHARE = 0.5  # unmeasured: repeated on half the pages or more is the house's furniture
_TOKEN = re.compile(r"[$€£]?\d[\d,.]*%?x?|[A-Za-z][A-Za-z&'\-]*")
_FIGURE = re.compile(r"^[$€£]\d|\d\d%$|^\d{3,}|\d[.,]\d")
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


def media_hashes(path: str) -> dict[str, str]:
    if not path.lower().endswith(".pptx"):
        return {}
    with zipfile.ZipFile(path) as z:
        return {hashlib.sha256(z.read(n)).hexdigest(): n for n in z.namelist() if n.startswith("ppt/media/")}


def leakage(new: str, past: list[str], briefs: list[str] | None = None, template: str | None = None, page_ids: list | None = None) -> dict:
    briefs = briefs or []
    allowed = features([Path(b).read_text(errors="replace") for b in briefs])
    excluded: dict[str, set] = {k: set(v) for k, v in allowed.items()}
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
    report_pages = []
    for i, strings in enumerate(page_texts(new)):
        mine = features(strings)
        found = []
        for kind in ("name", "figure", "phrase"):
            for f in sorted(mine[kind] - excluded[kind]):
                where = [f"{d} p{n}" for d, n, p in past_pages if f in p[kind]]
                if where:
                    found.append({"kind": kind, "text": " ".join(f), "past": where[:3] + ([f"and {len(where) - 3} more"] if len(where) > 3 else [])})
        if found:
            report_pages.append({"page": i + 1, **({"id": page_ids[i]} if page_ids and i < len(page_ids) else {}), "findings": found})
    template_media = set(media_hashes(template)) if template else set()
    past_media = {h: f"{Path(d).name}:{n}" for d in past for h, n in media_hashes(d).items()}
    images = [{"new": n, "past": past_media[h]} for h, n in media_hashes(new).items() if h in past_media and h not in template_media]
    return {"past_decks": [Path(d).name for d in past], "briefs": [Path(b).name for b in briefs],
            "findings": sum(len(p["findings"]) for p in report_pages), "pages": report_pages, "images": images,
            "chrome_excluded": chrome_counts,
            "images_checked": "pptx media by sha256" + ("" if all(d.lower().endswith(".pptx") for d in past) else "; a PDF's pictures are not checked"),
            "method": f"names (2+ capitalised words), figures and {PHRASE_WORDS}-word phrases of each new page found on a past page; "
                      f"chrome (on {CHROME_SHARE:.0%}+ of a past deck's pages), template text and --brief text excluded; thresholds unmeasured",
            "verdict": "clean" if not report_pages and not images else "possible carry-over: remove each, or confirm the user supplied it for this deck"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new")
    ap.add_argument("--past", action="append", required=True, help="a past deck used as evidence (.pptx or .pdf), repeatable")
    ap.add_argument("--brief", action="append", default=[], help="the user's brief or data as a text file: its words are allowed")
    ap.add_argument("--template", default=None, help="the template the deck was built on: its own text and pictures are furniture")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out")
    report = leakage(args.new, args.past, args.brief, args.template)
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    import cli
    cli.run(main)
