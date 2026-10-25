#!/usr/bin/env python3
"""The page library: real pages, tagged by the model after looking, retrieved by tags
when a page is planned (TARGET_SPEC 10.4, 7, A.11).

    library.py permit  --lib LIB DECK --owner NAME --source-type company|external
                       --images yes|no --by WHO --basis TEXT [--licence TEXT] [--id ID]
    library.py build   --lib LIB DECK... [--keep ID:PAGES] [--skip ID:PAGES] [--exclude ID[:PAGES]]
    library.py tag     --lib LIB TAGS.json
    library.py check   --lib LIB [--seal]
    library.py pick    --intent TEXT [--composition C] [--exhibit F] [--move M]... [--data-shape TEXT]
                       [--aspect W:H] [--gallery DIR] [--own LIB] [--library LIB] [--exclude ID] [--top N]
    library.py import  --lib LIB SRC/library.json --by WHO --basis TEXT
    library.py forget  --lib LIB --deck ID
    library.py vocab

permit records, per deck, who allowed what. build refuses a deck with no record: page
images are kept only under `--images yes`; under `no` the renders live in LIB/work only
for the model to look at while tagging, entries carry no image, and `check --seal`
deletes those renders once every entry passes (TARGET_SPEC 7.3: tags, structure and the
reasoning note without a client page image).

build renders every page that is not excluded, proposes a triage (content, cover,
divider, disclaimer, hidden, generated) from measured page facts, writes a labelled
contact sheet of all rendered pages, and a stub entry per content page. The proposal is
mechanical and the model overrides it with --keep and --skip after looking at the sheet.
Every tag field of a stub is null until the model fills it with `tag`; null means not
tagged yet, an empty list means looked and found none.

Confidentiality: no network module is imported and no subprocess here or in render.py
opens a socket (soffice, pdftoppm, pdffonts, fc-match). Every file under LIB is listed in
LIB/manifest.json with the hash of the deck it came from; `check` refuses a file on disk
that the manifest does not list and a listed file whose hash moved; `forget` deletes one
deck's files and entries as a set. A library inside the skill directory is refused unless
it is git-ignored and its owner is `external`; one pick never mixes two owners' libraries.

pick searches the reference's own gallery first (gallery.py's word-overlap ranking:
gallery exemplars carry no tags), then the owner's library, then the external library, and
says where each result came from. Library entries rank by structured tags (composition,
exhibit family, annotation moves, aspect, then data-shape words) and by intent words only
after them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image

import gallery
import ooxml
import render
from extract_style import quant

SKILL_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_LIBRARY = SKILL_ROOT / "refs" / "library"
RENDER_WIDTH_PX = 1600  # TARGET_SPEC 10.1: all pages at 1600 px
EMU_PER_INCH = 914_400

# --- vocabulary -------------------------------------------------------------------------------
# The synthesis taxonomy that tagged the 578-page development corpus (pagecraft
# synth/analyze_all.py: page_family, EX_RULES, MOVES); TARGET_SPEC A.2, A.5 and A.6 count
# these categories under longer spellings. The corpus starter set uses exactly these strings.

HOUSE_TYPES = ("investment bank", "consulting", "chart book", "other")
TITLE_REGISTERS = ("topic", "claim", "question")
COMPOSITIONS = (
    "single chart, full width",
    "single table, full width",
    "exhibit + side text or takeaway column",
    "two or more exhibits (panels, small multiples, chart + table)",
    "structured text (rows, columns, cards)",
    "diagram / process / timeline",
    "text only (bullets / paragraphs)",
    "image / logo / evidence wall",
    "exhibit + text above or below",
    "big numbers / KPI panel",
)
EXHIBIT_FAMILIES = (
    "line", "column", "text / data table", "stacked bar / column / area", "financial / projection table",
    "process / timeline / plan", "sensitivity grid", "diagram / framework", "framework matrix / placemat",
    "image / logo / evidence wall", "structured text (rows, cards, quotes)", "horizontal bar", "status / check matrix",
    "comps / benchmark table", "combo (bar + line/dot)", "football field / range bars", "pie / donut",
    "table with in-cell bars", "waterfall / bridge", "map", "big numbers / KPI", "scatter / bubble", "histogram",
    "funnel", "heatmap", "other",
)
ANNOTATION_MOVES = (
    "data labels on all marks", "selective data labels", "end / direct labels instead of legend",
    "reference / benchmark / average line", "highlight one item, mute the rest", "median / stat row or block emphasised",
    "sorted order", "totals above stacks / 100%= bases", "shaded / bold total row", "column spanners / grouped headers",
    "bracket / brace (often with sum)", "callout box / arrow / leader to the insight", "circled or boxed mark",
    "delta / growth / CAGR label", "event markers on time axis", "forecast / period demarcation", "footnote markers",
    "NM / NA / n.q. markers", "data rows / table aligned under the chart", "inset stats table in the plot",
    "italic ratio rows", "logos as labels", "numbered / lettered keys tied to text",
    "semantic colour (sign, status, sentiment, heat)", "status glyphs (check, cross, dots)",
    "shared scale / order held across panels", "axis break / inversion / rebasing", "percent-of-total labels",
    "reading key / how-to-read note", "zone / quadrant shading", "regression line / R2",
    "connectors / zoom lines between marks", "derivation shown on the exhibit",
    "uncertainty (ranges, scenario lines, stamps)", "input cells / base case marked",
)
# Fields the model fills after looking. Everything else in an entry is measured or recorded.
TAG_FIELDS = ("house_type", "composition_family", "composition_as_recorded", "title", "title_register", "exhibits",
              "emphasis_devices", "craft", "why_instructive", "designer_questions")
EXHIBIT_FIELDS = ("type", "family", "data_shape", "message", "annotation_moves", "annotations_as_recorded")

# --- triage proposal -------------------------------------------------------------------------
DIVIDER_WORD_SHARE = 0.2
# Definition, unmeasured: a page with no table, chart or picture and fewer words than this
# share of the deck's median page is proposed as a divider. The model overrides it.
DISCLAIMER_WORDS = re.compile(r"\b(disclaimer|important (information|notice)|forward[- ]looking statements|not an offer|"
                              r"notice to recipients?|legal notice)\b", re.IGNORECASE)
# Definition, unmeasured: one of these phrases on a page with no table or chart proposes it as
# a disclaimer page.
ASPECT_TOLERANCE = 0.02  # definition: 4:3 (1.333), letter (1.294) and 16:9 (1.778) stay apart
PICK_TOP = 3  # TARGET_SPEC 10.4 asks 3 to 5 examples per intent (external guidance, unmeasured)


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_pages(spec: str) -> set[int]:
    out: set[int] = set()
    for piece in spec.split(","):
        piece = piece.strip()
        if "-" in piece:
            lo, hi = piece.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        elif piece:
            out.add(int(piece))
    return out


def deck_pages(items: list[str] | None) -> dict[str, set[int] | None]:
    """ID:PAGES items; a bare ID means every page of that deck."""
    out: dict[str, set[int] | None] = {}
    for item in items or []:
        deck_id, _, pages = item.partition(":")
        if not pages or (deck_id in out and out[deck_id] is None):
            out[deck_id] = None
        else:
            out[deck_id] = (out.get(deck_id) or set()) | parse_pages(pages)
    return out


def named(selection: dict[str, set[int] | None], deck_id: str, page: int) -> bool:
    return deck_id in selection and (selection[deck_id] is None or page in selection[deck_id])  # type: ignore[operator]


# --- the library on disk ---------------------------------------------------------------------

class Library:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.manifest_path = self.root / "manifest.json"
        self.entries_path = self.root / "library.json"
        self.manifest: dict = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {
            "schema": 1, "owner": None, "decks": {}, "files": {}}
        self.pages: list[dict] = json.loads(self.entries_path.read_text())["pages"] if self.entries_path.exists() else []

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.pages.sort(key=lambda e: (e["deck"], e["page"]))
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")
        self.entries_path.write_text(json.dumps({"schema": 1, "owner": self.manifest["owner"], "pages": self.pages}, indent=1) + "\n")

    def guard_location(self, owner: str) -> None:
        """TARGET_SPEC 7.2: nothing derived from company material is written into the skill
        directory; third-party page images are never committed."""
        inside = self.root == SKILL_ROOT or SKILL_ROOT in self.root.parents
        if not inside:
            return
        if owner != "external":
            raise Refused("library_in_skill_dir", f"{self.root} is inside the skill directory; a library owned by {owner!r} lives in the company's working directory")
        probe = self.root / "manifest.json"
        ignored = subprocess.run(["git", "-C", str(SKILL_ROOT), "check-ignore", "-q", str(probe)], capture_output=True, check=False).returncode == 0
        if not ignored:
            raise Refused("library_not_ignored", f"{self.root} is inside the skill directory and git does not ignore it: its page images would be committable")

    def add_file(self, path: Path, deck_id: str, kind: str) -> str:
        rel = str(path.resolve().relative_to(self.root))
        self.manifest["files"][rel] = {"sha256": sha256(path), "deck": deck_id, "kind": kind,
                                       "source_sha256": self.manifest["decks"][deck_id]["sha256"]}
        return rel

    def drop_files(self, deck_id: str, pages: set[int] | None = None, kinds: set[str] | None = None) -> int:
        dropped = 0
        for rel, info in list(self.manifest["files"].items()):
            if info["deck"] != deck_id or (kinds is not None and info["kind"] not in kinds):
                continue
            if pages is not None and info.get("page") not in pages:
                continue
            (self.root / rel).unlink(missing_ok=True)
            del self.manifest["files"][rel]
            dropped += 1
        return dropped


def permit(lib: Library, deck: Path | None, deck_id: str, owner: str, source_type: str, images: bool, by: str, basis: str,
           licence: str | None) -> dict:
    if lib.manifest["owner"] not in (None, owner):
        raise Refused("owner_mismatch", f"{lib.root} belongs to {lib.manifest['owner']!r}; one company's library is never shared with another")
    if source_type == "company" and owner == "external":
        raise Refused("company_deck_external_owner", "a company deck enters that company's library, not the external one")
    lib.guard_location(owner)
    lib.manifest["owner"] = owner
    record = lib.manifest["decks"].setdefault(deck_id, {})
    record.update({"file_name": deck.name if deck else None, "sha256": sha256(deck) if deck else None, "source_type": source_type,
                   "permission": {"keep_images": images, "by": by, "basis": basis, "licence_basis": licence}})
    record.setdefault("excluded_pages", [])
    record.setdefault("excluded", False)
    lib.save()
    return record


# --- page facts and the triage proposal ------------------------------------------------------

def page_facts(deck: Path) -> tuple[list[dict], tuple[int, int]]:
    """What the file states about each page, read through ooxml.py (pptx parts or the PDF
    reader). Nothing here is a judgement about the page."""
    prints = ooxml.fingerprint_deck(str(deck))
    if not prints:
        raise Refused("no_pages", f"{deck.name} has no pages")
    pkg = None if gallery.is_pdf(deck) else ooxml.Package(str(deck))
    shapes_of = [[sh for sh in sp.shapes if sh.layer == "slide"] if sp.source == "pptx" else sp.shapes for sp in prints]
    # A picture at the same box (extract_style's 6pt position grid) on at least half the pages
    # is furniture or the page itself (a printed deck's page image), not an exhibit.
    seen = Counter(b for shapes in shapes_of for b in {quant(sh.box) for sh in shapes if sh.kind == "picture" and sh.box})
    furniture = {b for b, n in seen.items() if n >= max(2, len(prints) / 2)}
    facts = []
    for sp, slide_shapes in zip(prints, shapes_of, strict=True):
        kinds = [sh.kind for sh in slide_shapes]
        recurring = sum(1 for sh in slide_shapes if sh.kind == "picture" and sh.box and quant(sh.box) in furniture)
        layout_type = pkg.root(sp.layout_part).get("type") if pkg is not None and sp.layout_part else None
        title_ph = any(sh.ph_type == "ctrTitle" for sh in sp.shapes)
        text = " ".join(r.text for r in sp.runs if r.text)
        facts.append({
            "page": sp.index + 1, "hidden": sp.hidden, "generated": sp.generated, "source": sp.source,
            "layout": sp.layout_name or None, "layout_type": layout_type, "ctr_title": title_ph,
            "page_class": sp.page_class if sp.source == "pdf" else None,
            "words": sum(r.words for r in sp.runs),
            "tables": max(kinds.count("table"), len(sp.tables)),
            "charts": kinds.count("chart"),
            "pictures": kinds.count("picture") - recurring,
            "recurring_pictures": recurring,
            "text_elements": sum(1 for sh in slide_shapes if sh.kind in ("text_box", "text_shape")),
            "disclaimer_phrase": (m.group(0) if (m := DISCLAIMER_WORDS.search(text)) else None),
        })
    return facts, (prints[0].width, prints[0].height)


def propose(facts: list[dict]) -> list[dict]:
    words = [f["words"] for f in facts if not f["hidden"]]
    deck_median = median(words) if words else 0
    out = []
    for f in facts:
        exhibit = f["tables"] + f["charts"] + f["pictures"]
        if f["hidden"]:
            call, why = "hidden", "hidden slide (show=0)"
        elif f["generated"]:
            call, why = "generated", "carries the pptx-skill origin tag"
        elif f["layout_type"] == "title" or f["ctr_title"]:
            call, why = "cover", f"the file declares a title slide (layout type {f['layout_type']}, ctrTitle {f['ctr_title']})"
        elif f["page"] == 1:
            call, why = "cover", "first page"
        elif f["layout_type"] == "secHead":
            call, why = "divider", "the file declares a section header layout"
        elif f["disclaimer_phrase"] and not (f["tables"] or f["charts"]):
            call, why = "disclaimer", f"says {f['disclaimer_phrase']!r} and holds no table or chart"
        elif not exhibit and f["words"] < DIVIDER_WORD_SHARE * deck_median:
            call, why = "divider", f"{f['words']} words against the deck median {deck_median:g}, no table, chart or picture"
        else:
            call, why = "content", f"{f['words']} words, {f['tables']} tables, {f['charts']} charts, {f['pictures']} pictures"
        out.append({"page": f["page"], "proposal": call, "evidence": why})
    return out


# --- build -----------------------------------------------------------------------------------

def render_deck(deck: Path, pages: list[int], facts: list[dict], tmp: Path) -> tuple[dict[int, Path], dict]:
    """The pages asked for, at RENDER_WIDTH_PX, through render.py (gallery.py's renderer for
    a pptx, so a face that cannot draw the deck's characters is refused the same way)."""
    if gallery.is_pdf(deck):
        fonts = render.pdf_font_report(deck)
        drawn = render.rasterize(deck, tmp / "pages", 110, pages, RENDER_WIDTH_PX)
        return dict(zip(pages, drawn, strict=True)), fonts
    try:
        drawn, fonts = gallery.render_pages(deck, tmp / "pages", RENDER_WIDTH_PX)
    except gallery.GalleryRefused as refused:
        raise Refused(refused.reason, str(refused)) from refused
    shown = [f["page"] for f in facts if not f["hidden"]]
    if len(drawn) != len(shown):
        raise Refused("page_count_mismatch", f"{len(drawn)} rendered pages against {len(shown)} visible slides")
    by_page = dict(zip(shown, drawn, strict=True))
    return {p: by_page[p] for p in pages if p in by_page}, fonts


def stub(deck_id: str, page: int, record: dict, size: dict, layout: str | None, fidelity: str, image: str | None, coder: str) -> dict:
    entry: dict = {"entry_id": f"{deck_id}-p{page}", "deck": deck_id, "page": page, "source_type": record["source_type"],
                   "coder": coder, "page_size": size, "layout": layout, "render_fidelity": fidelity, "image": image,
                   "image_withheld": None if image else "no permission recorded to keep this deck's page images"}
    entry.update({field: None for field in TAG_FIELDS})
    return entry


def build(lib: Library, decks: list[Path], keep: dict, skip: dict, exclude: dict, coder: str) -> list[str]:
    report = []
    for deck_id, pages in exclude.items():
        if deck_id not in lib.manifest["decks"]:
            raise Refused("exclude_unknown_deck", f"{deck_id} has no permission record in {lib.manifest_path}")
        record = lib.manifest["decks"][deck_id]
        if pages is None:
            record["excluded"] = True
        else:
            record["excluded_pages"] = sorted(set(record["excluded_pages"]) | pages)
        # an excluded page loses everything derived from it at once, built again or not
        gone = lib.drop_files(deck_id, None if pages is None else pages)
        before = len(lib.pages)
        lib.pages = [e for e in lib.pages if not (e["deck"] == deck_id and (pages is None or e["page"] in pages))]
        report.append(f"{deck_id}: exclude {'every page' if pages is None else sorted(pages)} recorded; {gone} files and {before - len(lib.pages)} entries deleted")
    for deck in decks:
        deck_id = next((i for i, r in lib.manifest["decks"].items() if r["sha256"] == sha256(deck)), None)
        if deck_id is None:
            raise Refused("no_permission", f"{deck.name} (sha256 {sha256(deck)[:12]}) has no permission record in {lib.manifest_path}: run library.py permit first")
        record = lib.manifest["decks"][deck_id]
        lib.guard_location(lib.manifest["owner"])
        excluded = set(record["excluded_pages"])
        if record["excluded"]:
            report.append(f"{deck_id}: on the exclude list whole; nothing rendered")
            continue
        facts, (w, h) = page_facts(deck)
        size = {"width_in": round(w / EMU_PER_INCH, 3), "height_in": round(h / EMU_PER_INCH, 3), "aspect": round(w / h, 3),
                "measured_from": "the deck's page size"}
        triage = propose(facts)
        for row in triage:
            p = row["page"]
            if p in excluded:
                row["decision"], row["by"] = "excluded", "manifest exclude list"
            elif named(keep, deck_id, p):
                row["decision"], row["by"] = "content", "--keep"
            elif named(skip, deck_id, p):
                row["decision"], row["by"] = "skip", "--skip"
            else:
                row["decision"], row["by"] = ("content" if row["proposal"] == "content" else "skip"), "proposal"
        renderable = [r["page"] for r in triage if r["decision"] != "excluded" and not facts[r["page"] - 1]["hidden"]]
        keep_images = bool(record["permission"]["keep_images"])
        work = lib.root / "work" / deck_id
        page_dir = lib.root / "pages" / deck_id
        lib.drop_files(deck_id, None, {"page_image", "withheld_render", "contact_sheet", "triage"})
        work.mkdir(parents=True, exist_ok=True)
        if keep_images:
            page_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="library-render-") as tmp:
            drawn, fonts = render_deck(deck, renderable, facts, Path(tmp))
            fidelity = gallery.render_fidelity(fonts)
            record.update({"render_fidelity": fidelity, "page_size": size, "pages": len(facts)})
            labelled = []
            for row in triage:
                if row["page"] in drawn:
                    target = Path(tmp) / "sheet" / f"p{row['page']:03d} {row['decision']} ({row['proposal']})"
                    target.parent.mkdir(exist_ok=True)
                    labelled.append(Path(shutil.copyfile(drawn[row["page"]], target.with_suffix(".png"))))
            sheet_kind = "contact_sheet" if keep_images else "withheld_render"
            sheet = render.grid(labelled, work / "triage.png", cols=6, cell_w=320) if labelled else None
            if sheet:
                lib.add_file(sheet, deck_id, sheet_kind)
            kept = {e["page"]: e for e in lib.pages if e["deck"] == deck_id}
            entries = []
            for row in triage:
                if row["decision"] != "content" or row["page"] not in drawn:
                    continue
                p = row["page"]
                target = (page_dir if keep_images else work) / f"p-{p:03d}.png"
                shutil.copyfile(drawn[p], target)
                rel = lib.add_file(target, deck_id, "page_image" if keep_images else "withheld_render")
                lib.manifest["files"][rel]["page"] = p
                entry = stub(deck_id, p, record, size, facts[p - 1]["layout"], fidelity, rel if keep_images else None, coder)
                prior = kept.get(p)
                if prior is not None and prior.get("source_sha256") == record["sha256"]:
                    entry.update({k: prior[k] for k in TAG_FIELDS})
                entry["source_sha256"] = record["sha256"]
                entry["look_at"] = rel
                entries.append(entry)
        lib.pages = [e for e in lib.pages if e["deck"] != deck_id] + entries
        triage_path = work / "triage.json"
        triage_path.write_text(json.dumps({"deck": deck_id, "rule": {"divider_word_share": DIVIDER_WORD_SHARE, "disclaimer_words": DISCLAIMER_WORDS.pattern},
                                           "pages": [dict(row, **facts[row["page"] - 1]) for row in triage]}, indent=1) + "\n")
        lib.add_file(triage_path, deck_id, "triage")
        report.append(f"{deck_id}: {len(facts)} pages, render {fidelity}, images {'kept' if keep_images else 'withheld (tags only)'}; "
                      f"contact sheet {sheet}")
        report.append("  page  proposal    decision  by          evidence")
        for row in triage:
            report.append(f"  {row['page']:>4}  {row['proposal']:<10}  {row['decision']:<8}  {row['by']:<10}  {row['evidence']}")
        report.append(f"  {len(entries)} stub entries; tag them with library.py tag after looking at each look_at image")
    lib.save()
    return report


# --- tags and the check ----------------------------------------------------------------------

def check_entry(entry: dict) -> list[str]:
    problems = []
    untagged = [f for f in TAG_FIELDS if entry.get(f) is None]
    if untagged:
        problems.append(f"not tagged yet: {', '.join(untagged)}")

    def one_of(field: str, value: object, allowed: tuple[str, ...]) -> None:
        if value is not None and value not in allowed:
            problems.append(f"{field} {value!r} is not in the vocabulary (library.py vocab)")

    one_of("house_type", entry.get("house_type"), HOUSE_TYPES)
    if entry.get("house_type") == "other" and not entry.get("house_type_as_recorded"):
        problems.append("house_type 'other' needs house_type_as_recorded")
    one_of("composition_family", entry.get("composition_family"), COMPOSITIONS)
    one_of("title_register", entry.get("title_register"), TITLE_REGISTERS)
    for field in ("composition_as_recorded", "title", "why_instructive"):
        value = entry.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip() or "\n" in value):
            problems.append(f"{field} must be one non-empty line")
    for field in ("emphasis_devices", "craft"):
        value = entry.get(field)
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)):
            problems.append(f"{field} must be a list of non-empty strings ([] = looked, none)")
    questions = entry.get("designer_questions")
    if questions is not None:
        if not isinstance(questions, list) or not questions:
            problems.append("designer_questions must be a non-empty list")
        else:
            problems += [f"designer question {q!r} is not a question (TARGET_SPEC Appendix B: questions, never rules)"
                         for q in questions if not isinstance(q, str) or "?" not in q]
    exhibits = entry.get("exhibits")
    if exhibits is not None:
        if not isinstance(exhibits, list):
            problems.append("exhibits must be a list ([] = a page with no exhibit)")
        else:
            for i, ex in enumerate(exhibits):
                if not isinstance(ex, dict):
                    problems.append(f"exhibit {i} is not an object")
                    continue
                missing = [f for f in EXHIBIT_FIELDS if ex.get(f) is None]
                if missing:
                    problems.append(f"exhibit {i} not tagged: {', '.join(missing)}")
                one_of(f"exhibit {i} family", ex.get("family"), EXHIBIT_FAMILIES)
                for move in ex.get("annotation_moves") or []:
                    one_of(f"exhibit {i} annotation move", move, ANNOTATION_MOVES)
                for field in ("annotation_moves", "annotations_as_recorded"):
                    if ex.get(field) is not None and not isinstance(ex[field], list):
                        problems.append(f"exhibit {i} {field} must be a list")
    return problems


def tag(lib: Library, tags: dict) -> list[str]:
    by_id = {e["entry_id"]: e for e in lib.pages}
    unknown = sorted(set(tags) - set(by_id))
    if unknown:
        raise Refused("unknown_entries", f"no stub for {', '.join(unknown)}")
    for entry_id, fields in tags.items():
        outside = sorted(set(fields) - set(TAG_FIELDS) - {"house_type_as_recorded"})
        if outside:
            raise Refused("not_a_tag_field", f"{entry_id}: {', '.join(outside)} are measured or recorded, not tags ({', '.join(TAG_FIELDS)})")
    refused = []
    for entry_id, fields in tags.items():
        # a partial tagging may leave fields null; a value outside the vocabulary never enters
        wrong = [q for q in check_entry(dict(by_id[entry_id], **fields)) if not q.startswith("not tagged yet")]
        if wrong:
            refused.append(f"{entry_id}: {'; '.join(wrong)}")
    if refused:
        raise Refused("tags_refused", "nothing written; " + " | ".join(refused))
    for entry_id, fields in tags.items():
        by_id[entry_id].update(fields)
    lib.save()
    return [f"{entry_id}: {'; '.join(check_entry(by_id[entry_id])) or 'ok'}" for entry_id in tags]


def check(lib: Library, seal: bool) -> tuple[list[str], int]:
    lines, failures = [], 0
    for entry in lib.pages:
        problems = check_entry(entry)
        record = lib.manifest["decks"].get(entry["deck"])
        if record is None:
            problems.append("its deck has no permission record")
        else:
            if entry["page"] in record["excluded_pages"] or record["excluded"]:
                problems.append("the page is on the exclude list")
            if entry.get("image") and not record["permission"]["keep_images"]:
                problems.append("carries an image though its deck's permission keeps none")
        if entry.get("image") and entry["image"] not in lib.manifest["files"]:
            problems.append(f"image {entry['image']} is not in the manifest")
        failures += bool(problems)
        lines.append(f"{entry['entry_id']}: {'; '.join(problems) or 'ok'}")
    listed = set(lib.manifest["files"])
    on_disk = {str(p.relative_to(lib.root)) for p in lib.root.rglob("*") if p.is_file()} - {"manifest.json", "library.json"}
    for rel in sorted(on_disk - listed):
        lines.append(f"file {rel}: on disk and not in the manifest (a derived file nobody can delete as a set)")
        failures += 1
    for rel in sorted(listed - on_disk):
        lines.append(f"file {rel}: in the manifest and missing on disk")
        failures += 1
    for rel in sorted(listed & on_disk):
        if sha256(lib.root / rel) != lib.manifest["files"][rel]["sha256"]:
            lines.append(f"file {rel}: hash differs from the manifest")
            failures += 1
    lines.append(f"{len(lib.pages)} entries, {len(listed)} manifest files, {failures} problems")
    if seal:
        if failures:
            lines.append("not sealed: fix the problems first")
        else:
            gone = sum(lib.drop_files(d, None, {"withheld_render"}) for d in lib.manifest["decks"])
            for entry in lib.pages:
                if entry.get("image") is None:
                    entry["look_at"] = None
            lib.save()
            lines.append(f"sealed: {gone} withheld renders deleted")
    return lines, failures


def forget(lib: Library, deck_id: str) -> str:
    if deck_id not in lib.manifest["decks"]:
        raise Refused("unknown_deck", f"{deck_id} is not in {lib.manifest_path}")
    gone = lib.drop_files(deck_id)
    before = len(lib.pages)
    lib.pages = [e for e in lib.pages if e["deck"] != deck_id]
    del lib.manifest["decks"][deck_id]
    lib.save()
    for d in (lib.root / "pages" / deck_id, lib.root / "work" / deck_id):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return f"{deck_id}: {gone} files and {before - len(lib.pages)} entries deleted, permission record removed"


# --- the corpus starter set ------------------------------------------------------------------

CORPUS_HOUSE = {"investment bank": "investment bank", "consulting": "consulting", "asset manager market guide (JPM)": "chart book"}


def import_corpus(lib: Library, source: Path, by: str, basis: str) -> list[str]:
    """The development corpus's curated pages (pagecraft library.json) as external entries.
    The corpus kept no deck files beside the images, so a deck's sha256 is null (no
    evidence) and the page size is the stored image's own aspect."""
    payload = json.loads(source.read_text())
    lines = []
    for page in payload["pages"]:
        deck_id = page["deck"]
        if deck_id not in lib.manifest["decks"]:
            permit(lib, None, deck_id, "external", "external", True, by, basis, None)
        record = lib.manifest["decks"][deck_id]
        image = Path(page["path"])
        target = lib.root / "pages" / deck_id / f"p-{page['page']:03d}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target)
        with Image.open(target) as im:
            wpx, hpx = im.size
        rel = lib.add_file(target, deck_id, "page_image")
        lib.manifest["files"][rel]["page"] = page["page"]
        size = {"width_in": None, "height_in": None, "aspect": round(wpx / hpx, 3),
                "measured_from": f"the stored image ({wpx} x {hpx} px); the corpus kept no page size"}
        entry = stub(deck_id, page["page"], record, size, None, "no evidence: rendered by the corpus readers", rel, page["reader"])
        entry["source_sha256"] = None
        entry["look_at"] = rel
        house = page["house_type"]
        entry.update({k: page[k] for k in TAG_FIELDS})
        entry["house_type"] = CORPUS_HOUSE.get(house, "other")
        if entry["house_type"] != house:
            entry["house_type_as_recorded"] = house
        lib.pages = [e for e in lib.pages if e["entry_id"] != entry["entry_id"]] + [entry]
        lines.append(f"{entry['entry_id']}: {'; '.join(check_entry(entry)) or 'ok'}")
    lib.save()
    return lines


# --- pick ------------------------------------------------------------------------------------

def _vocab(value: str | None, allowed: tuple[str, ...], flag: str) -> str | None:
    if value is None:
        return None
    hit = [a for a in allowed if a.lower() == value.strip().lower()]
    if not hit:
        near = sorted(allowed, key=lambda a: -len(gallery.words(a) & gallery.words(value)))[:4]
        raise Refused("not_in_vocabulary", f"{flag} {value!r}; nearest: {' | '.join(near)} (library.py vocab lists all)")
    return hit[0]


def _aspect(value: str | None) -> float | None:
    if value is None:
        return None
    w, _, h = value.partition(":")
    return float(w) / float(h) if h else float(w)


def entry_words(entry: dict) -> frozenset[str]:
    text = [entry.get("title"), entry.get("composition_as_recorded"), entry.get("why_instructive"),
            *(entry.get("designer_questions") or []), *(entry.get("emphasis_devices") or [])]
    for ex in entry.get("exhibits") or []:
        text += [ex.get("type"), ex.get("message"), *(ex.get("annotation_moves") or [])]
    return frozenset().union(*(gallery.words(t) for t in text if isinstance(t, str)))


def score(entry: dict, intent: frozenset[str], composition: str | None, exhibit: str | None, moves: list[str],
          shape: frozenset[str], aspect: float | None) -> dict:
    exhibits = entry.get("exhibits") or []
    entry_aspect = (entry.get("page_size") or {}).get("aspect")
    return {
        "composition": composition is not None and entry.get("composition_family") == composition,
        "exhibit": exhibit is not None and any(ex.get("family") == exhibit for ex in exhibits),
        "moves": len(set(moves) & {m for ex in exhibits for m in ex.get("annotation_moves") or []}),
        "aspect": aspect is not None and entry_aspect is not None and abs(entry_aspect - aspect) <= ASPECT_TOLERANCE,
        # one-character tokens ("x" between dimensions, a lone count) are in nearly every recorded shape
        "data_shape": len({w for w in shape if len(w) > 1} & frozenset().union(*(gallery.words(ex.get("data_shape") or "") for ex in exhibits))),
        "words": len(intent & entry_words(entry)),
    }


def pick(intent_text: str, composition: str | None, exhibit: str | None, move_names: list[str], data_shape: str | None, aspect_text: str | None,
         gallery_dir: Path | None, own: Path | None, external: list[Path], exclude: set[str], top: int) -> str:
    composition = _vocab(composition, COMPOSITIONS, "--composition")
    exhibit = _vocab(exhibit, EXHIBIT_FAMILIES, "--exhibit")
    moves = [m for m in (_vocab(name, ANNOTATION_MOVES, "--move") for name in move_names) if m]
    aspect = _aspect(aspect_text)
    intent, shape = gallery.words(intent_text), gallery.words(data_shape or "")
    libraries: list[tuple[str, Library]] = []
    if own is not None:
        lib = Library(own)
        if lib.manifest["owner"] in (None, "external"):
            raise Refused("own_is_external", f"--own {own} is owned by {lib.manifest['owner']!r}; the owner's library is a company's")
        libraries.append((f"the owner's library ({lib.manifest['owner']})", lib))
    for path in external:
        lib = Library(path)
        if lib.manifest["owner"] != "external":
            raise Refused("library_not_external", f"--library {path} is owned by {lib.manifest['owner']!r}; pass a company's own pages with --own")
        libraries.append(("the external library", lib))
    lines = [f"intent words: {' '.join(sorted(intent))}",
             f"asked: composition={composition} exhibit={exhibit} moves={moves or None} data shape words={' '.join(sorted(shape)) or None} aspect={aspect_text}",
             "searched in order: " + "; ".join(
                 ([f"the reference's own gallery {gallery_dir}"] if gallery_dir else ["no reference gallery given"])
                 + [f"{label} {lib.root} ({len(lib.pages)} entries)" for label, lib in libraries])]
    if gallery_dir is not None:
        # a word in every crop caption ("the", "deck", "appears") tells no crop from another
        captions = [gallery.words(c["caption"]) for c in json.loads((gallery_dir / "manifest.json").read_text())["crops"]]
        common = frozenset.intersection(*captions) if len(captions) > 1 else frozenset()
        if intent & common:
            lines.append(f"   words in every gallery caption, left out: {' '.join(sorted(intent & common))}")
        exemplars, crops = gallery.rank(gallery_dir, " ".join(sorted(intent - common)))
        best = max([o for _, o, _ in exemplars] + [o for _, o in crops], default=0)
        lines.append("1. the reference's own gallery (untagged: word overlap only, measured weak, TARGET_SPEC 10.2)")
        if best == 0:
            lines.append("   no evidence: overlap 0 on every exemplar and crop; the reference shows nothing for this intent")
        else:
            for e, o, _ in exemplars:
                if o:
                    lines.append(f"   exemplar {e['exemplar_id']} overlap {o}: {(gallery_dir / e['render_file']).resolve()}")
            for c, o in crops:
                if o:
                    lines.append(f"   crop {c['gallery_id']} overlap {o}: {c['caption']} {(gallery_dir / c['file']).resolve()}")
    for n, (label, lib) in enumerate(libraries, start=2 if gallery_dir else 1):
        ranked = []
        usable = [e for e in lib.pages if not (e["entry_id"] in exclude or e["deck"] in exclude)]
        # an untagged stub or a failing entry carries nothing to rank on
        good = [e for e in usable if not check_entry(e)]
        untagged = len(usable) - len(good)
        # a word every entry carries tells no entry from another
        common = frozenset.intersection(*(entry_words(e) for e in good)) if len(good) > 1 else frozenset()
        for entry in good:
            s = score(entry, intent - common, composition, exhibit, moves, shape, aspect)
            structured = s["composition"] + s["exhibit"] + s["moves"]
            # the page size orders examples within a tier and never makes one relevant by itself
            if structured or s["data_shape"] or s["words"]:
                ranked.append(([-structured, -s["aspect"], -s["data_shape"], -s["words"], entry["entry_id"]], entry, s))
        ranked.sort(key=lambda r: r[0])
        # diverse examples: within one tier of structured matches a deck's second page waits
        # behind every other deck's first; a structured match never waits behind a weaker one
        repeat: dict[tuple[int, str], int] = {}
        for r in ranked:
            r[0].insert(1, repeat.setdefault((r[0][0], r[1]["deck"]), 0))
            repeat[(r[0][0], r[1]["deck"])] += 1
        chosen = sorted(ranked, key=lambda r: r[0])[:top]
        lines.append(f"{n}. {label}: {len(ranked)} entries share a tag or a word" + (f"; {untagged} entries untagged or failing check, not ranked" if untagged else ""))
        if not chosen:
            lines.append("   no evidence: no entry shares a tag or a word with this intent")
        for _, entry, s in chosen:
            entry_aspect = (entry.get("page_size") or {}).get("aspect")
            flags = [k for k in ("composition", "exhibit", "aspect") if s[k]] + ([f"{s['moves']} moves"] if s["moves"] else [])
            lines.append(f"   {entry['entry_id']} [{entry['house_type']}; {entry['composition_family']}] tags {'+'.join(flags) or 'none'}, "
                         f"data-shape words {s['data_shape']}, intent words {s['words']}, aspect {entry_aspect}"
                         + (" (does not match the page asked: examples do not transfer across aspect ratios)" if aspect is not None and not s["aspect"] else ""))
            image = entry.get("image")
            lines.append(f"   image: {(lib.root / image).resolve() if image else 'withheld (no permission to keep the page image)'}")
            lines.append(f"   why: {entry['why_instructive']}")
            lines.extend(f"   ask: {q}" for q in entry["designer_questions"])
    return "\n".join(lines)


# --- command line ----------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("permit")
    p.add_argument("deck")
    p.add_argument("--lib", required=True)
    p.add_argument("--id", default=None, help="deck id (default: the file stem)")
    p.add_argument("--owner", required=True, help="the company whose library this is, or 'external'")
    p.add_argument("--source-type", required=True, choices=("company", "external"))
    p.add_argument("--images", required=True, choices=("yes", "no"), help="may page images of this deck be kept")
    p.add_argument("--by", required=True, help="who gave the permission")
    p.add_argument("--basis", required=True, help="what the permission rests on")
    p.add_argument("--licence", default=None, help="licence basis of an external public deck")
    p = sub.add_parser("build")
    p.add_argument("decks", nargs="+")
    p.add_argument("--lib", required=True)
    p.add_argument("--keep", action="append", help="ID:PAGES the model keeps as content against the proposal")
    p.add_argument("--skip", action="append", help="ID:PAGES the model skips against the proposal")
    p.add_argument("--exclude", action="append", help="ID[:PAGES] never to derive anything from; recorded in the manifest")
    p.add_argument("--coder", default="model", help="who tags these pages")
    p = sub.add_parser("tag")
    p.add_argument("tags")
    p.add_argument("--lib", required=True)
    p = sub.add_parser("check")
    p.add_argument("--lib", required=True)
    p.add_argument("--seal", action="store_true", help="after a clean check, delete the renders of decks whose images may not be kept")
    p = sub.add_parser("pick")
    p.add_argument("--intent", required=True)
    p.add_argument("--composition")
    p.add_argument("--exhibit")
    p.add_argument("--move", action="append", default=[], help="an annotation move the page needs (repeatable)")
    p.add_argument("--data-shape")
    p.add_argument("--aspect", help="the page asked, as W:H (4:3, 16:9, 11:8.5)")
    p.add_argument("--gallery", help="the reference's own gallery.py output")
    p.add_argument("--own", help="the owner's library (the company's own pages)")
    p.add_argument("--library", action="append", help=f"external library (default {EXTERNAL_LIBRARY} when it exists)")
    p.add_argument("--exclude", action="append", default=[], help="entry or deck id to leave out")
    p.add_argument("--top", type=int, default=PICK_TOP)
    p = sub.add_parser("import")
    p.add_argument("source")
    p.add_argument("--lib", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--basis", required=True)
    p = sub.add_parser("forget")
    p.add_argument("--lib", required=True)
    p.add_argument("--deck", required=True)
    sub.add_parser("vocab")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "permit":
            deck = Path(args.deck).resolve()
            record = permit(Library(Path(args.lib)), deck, args.id or deck.stem, args.owner, args.source_type, args.images == "yes",
                            args.by, args.basis, args.licence)
            print(json.dumps(record, indent=1))
        elif args.cmd == "build":
            print("\n".join(build(Library(Path(args.lib)), [Path(d).resolve() for d in args.decks], deck_pages(args.keep),
                                  deck_pages(args.skip), deck_pages(args.exclude), args.coder)))
        elif args.cmd == "tag":
            print("\n".join(tag(Library(Path(args.lib)), json.loads(Path(args.tags).read_text()))))
        elif args.cmd == "check":
            lines, failures = check(Library(Path(args.lib)), args.seal)
            print("\n".join(lines))
            return 1 if failures else 0
        elif args.cmd == "pick":
            external = [Path(p) for p in args.library] if args.library else ([EXTERNAL_LIBRARY] if (EXTERNAL_LIBRARY / "manifest.json").exists() else [])
            print(pick(args.intent, args.composition, args.exhibit, args.move, args.data_shape, args.aspect, Path(args.gallery) if args.gallery else None,
                       Path(args.own) if args.own else None, external, set(args.exclude), args.top))
        elif args.cmd == "import":
            lib = Library(Path(args.lib))
            lib.guard_location("external")
            print("\n".join(import_corpus(lib, Path(args.source), args.by, args.basis)))
        elif args.cmd == "forget":
            print(forget(Library(Path(args.lib)), args.deck))
        elif args.cmd == "vocab":
            print(json.dumps({"house_type": HOUSE_TYPES, "title_register": TITLE_REGISTERS, "composition_family": COMPOSITIONS,
                              "exhibit_family": EXHIBIT_FAMILIES, "annotation_moves": ANNOTATION_MOVES,
                              "tag_fields": TAG_FIELDS, "exhibit_fields": EXHIBIT_FIELDS}, indent=1))
    except Refused as refused:
        print(json.dumps({"refused": refused.reason, "detail": str(refused)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
