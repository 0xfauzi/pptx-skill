#!/usr/bin/env python3
"""The page library: real pages, tagged by the model after looking, retrieved by tags
when a page is planned.

    library.py permit  --lib LIB DECK --owner NAME --source-type company|external
                       --images yes|no --by WHO --basis TEXT [--licence TEXT] [--id ID]
    library.py build   --lib LIB DECK... [--keep ID:PAGES] [--skip ID:PAGES] [--exclude ID[:PAGES]]
    library.py tag     --lib LIB TAGS.json
    library.py check   --lib LIB [--seal]
    library.py pick    --intent TEXT [--composition C] [--data-shape TEXT]
                       [--aspect W:H] [--gallery DIR] [--own LIB] [--library LIB] [--exclude ID] [--top N]
    library.py import  --lib LIB SRC/library.json --by WHO --basis TEXT
    library.py forget  --lib LIB --deck ID
    library.py vocab

permit records, per deck, who allowed what, and the deck's page count. build refuses a
deck with no record: page images and contact sheets are kept only under `--images yes`;
under `no` the renders live in LIB/work only for the model to look at while tagging,
entries carry no image, and `check --seal` deletes those renders once every entry passes
(tags, structure and the reasoning note survive without a client page image).
Withdrawing image permission (permit again with `--images no`) deletes the kept images at
once, and `check` refuses any kept image on a deck whose permission keeps none.

build renders every page that is not excluded, proposes a triage (content, cover,
divider, disclaimer, hidden, generated) from measured page facts, writes a labelled
contact sheet of the rendered pages, and a stub entry per content page. The proposal is
mechanical and the model overrides it with --keep and --skip after looking at the sheet.
Every tag field of a stub is null until the model fills it with `tag`; null means not
tagged yet, an empty list means looked and found none. A PDF states no tables or charts,
so on a PDF those counts are null, and no divider or disclaimer is proposed from them.

An excluded page is never rendered or tagged: a pptx is rendered from a copy whose
excluded slides are emptied and hidden, a PDF rasterises only the pages kept, and no fact
of an excluded page is written. Each manifest file names the pages it derives from;
excluding a page deletes every file that names it (contact sheets and triage name every
page they show), and `check` refuses a file that names an excluded page.

Confidentiality: no network module is imported and no subprocess here or in render.py
opens a socket (soffice, pdftoppm, pdffonts, fc-match, git check-ignore). Every file under
LIB is listed in LIB/manifest.json with the hash of the deck it came from; `check` refuses
a file on disk that the manifest does not list and a listed file whose hash moved;
`forget` deletes one deck's files and entries as a set. A library inside the skill
directory is refused unless git ignores the directory itself (git never re-includes a
file under an ignored directory) and its owner is `external`; one pick never mixes two
owners' libraries.

pick searches the reference's own gallery first (gallery.py's word-overlap ranking:
gallery exemplars carry no tags), then the owner's library, then the external library, and
says where each result came from. Library entries rank by composition, aspect, then
data-shape words and intent words over what the model wrote of each exhibit. An exhibit
is tagged in the model's own words (what it is, its data, its message, how it is
annotated), never from a list of exhibit types or moves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from statistics import median

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gallery
import ooxml
import render
from complete_guide import VOCABULARY
from extract_style import quant
from lxml import etree
from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_LIBRARY = SKILL_ROOT / "refs" / "library"
RENDER_WIDTH_PX = 1600  # TARGET_SPEC 10.1: all pages at 1600 px
EMU_PER_INCH = 914_400
MANIFEST_SCHEMA = 4  # 2: every file names the pages it derives from ("pages"); 3: tags are vocabulary slugs; 4: exhibits in words
# The kinds that hold a picture of a page. Kept kinds need `--images yes`; a withheld render
# exists only while the model tags a tags-only deck, and `check --seal` deletes it.
KEPT_IMAGE_KINDS = frozenset({"page_image", "contact_sheet"})
WITHHELD_KIND = "withheld_render"

# --- vocabulary -------------------------------------------------------------------------------
# House type and composition: the synthesis taxonomy that tagged the 578-page development
# corpus (pagecraft synth/analyze_all.py: page_family); TARGET_SPEC A.2 counts these
# compositions under longer spellings. The corpus starter set uses exactly these strings.

HOUSE_TYPES = ("investment bank", "consulting", "chart book", "other")
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
# The title register is the title vocabulary's (references/page_craft_vocabulary.json). An
# exhibit is tagged in words: what it is, its data, its message and how it is annotated.
TITLE_REGISTERS: dict[str, str] = VOCABULARY["title_register"]
# Fields the model fills after looking. Everything else in an entry is measured or recorded.
TAG_FIELDS = ("house_type", "composition_family", "composition_as_recorded", "title", "title_register", "exhibits",
              "emphasis_devices", "craft", "why_instructive", "designer_questions")
EXHIBIT_TEXT_FIELDS = ("type", "data_shape", "message")
EXHIBIT_FIELDS = (*EXHIBIT_TEXT_FIELDS, "annotations_as_recorded")

# --- triage proposal -------------------------------------------------------------------------
DIVIDER_WORD_SHARE = 0.2
# Definition, unmeasured: a page with no table, chart or picture and fewer words than this
# share of the deck's median page is proposed as a divider. The model overrides it.
DISCLAIMER_WORDS = re.compile(r"\b(disclaimer|important (information|notice)|forward[- ]looking statements|not an offer|"
                              r"notice to recipients?|legal notice)\b", re.IGNORECASE)
# Definition, unmeasured: one of these phrases on a page with no table or chart proposes it as
# a disclaimer page. Neither rule fires where the file cannot state tables and charts (a PDF).
QUESTION_LEAD = re.compile(r"^[^.!?]*\w[^.!?]*\?")
# Definition: a designer question opens with a sentence that ends in a question mark; a
# follow-up after it ("Then re-sort each period.") is allowed, as in TARGET_SPEC Appendix B.
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
        lo, dash, hi = piece.partition("-")
        if not (lo.isdigit() and (hi.isdigit() if dash else True)) or int(lo) < 1 or (dash and int(hi) < int(lo)):
            raise Refused("bad_pages", f"{spec!r}: pages are 1-based numbers and ranges such as 2,5-7")
        out.update(range(int(lo), int(hi or lo) + 1))
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

def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Refused("library_unreadable", f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise Refused("library_unreadable", f"{path} is not a JSON object")
    return value


class Library:
    def __init__(self, root: Path, create: bool = False) -> None:
        """create: permit and import start a library; every other command refuses a path
        that holds none (an empty answer from a missing library would read as zero)."""
        self.root = root.resolve()
        self.manifest_path = self.root / "manifest.json"
        self.entries_path = self.root / "library.json"
        if not self.manifest_path.exists():
            if not create:
                raise Refused("no_library", f"{self.root} holds no library (no manifest.json)")
            self.manifest: dict = {"schema": MANIFEST_SCHEMA, "owner": None, "decks": {}, "files": {}}
            self.pages: list[dict] = []
            return
        self.manifest = _read_json(self.manifest_path)
        if self.manifest.get("schema") != MANIFEST_SCHEMA:
            raise Refused("manifest_schema", f"{self.manifest_path} is schema {self.manifest.get('schema')!r}, this script reads "
                          f"{MANIFEST_SCHEMA}: build or import it again")
        files = self.manifest.get("files")
        if not isinstance(self.manifest.get("decks"), dict) or not isinstance(files, dict):
            raise Refused("library_unreadable", f"{self.manifest_path} has no decks and files objects")
        for rel, info in files.items():
            pages = info.get("pages") if isinstance(info, dict) else None
            if not (isinstance(pages, list) and pages and all(isinstance(n, int) and n >= 1 for n in pages)):
                raise Refused("library_unreadable", f"{self.manifest_path}: file {rel} names no pages it derives from")
        entries = _read_json(self.entries_path).get("pages") if self.entries_path.exists() else []
        if not isinstance(entries, list):
            raise Refused("library_unreadable", f"{self.entries_path} has no pages list")
        self.pages = entries

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.pages.sort(key=lambda e: (e["deck"], e["page"]))
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")
        self.entries_path.write_text(json.dumps({"schema": MANIFEST_SCHEMA, "owner": self.manifest["owner"], "pages": self.pages}, indent=1) + "\n")

    def guard_location(self, owner: str) -> None:
        """Nothing derived from company material is written into the skill directory
        (cli.inside_skill); third-party page images are never committed."""
        import cli
        if not cli.inside_skill(self.root):
            return
        if owner != "external":
            raise Refused("library_in_skill_dir", f"{self.root} is inside the skill directory; a library owned by {owner!r} lives in the company's working directory")
        # The directory itself, with the slash that makes git test it as one: a pattern that
        # ignores only some files under it (its manifest.json) leaves the page images committable.
        answer = subprocess.run(["git", "-C", str(SKILL_ROOT), "check-ignore", "-q", f"{self.root}/"], capture_output=True, text=True, check=False)
        if answer.returncode == 1:
            raise Refused("library_not_ignored", f"{self.root}/ is inside the skill directory and git does not ignore the directory: its page images would be committable")
        if answer.returncode != 0:
            raise Refused("library_not_ignored", f"{self.root}/ is inside the skill directory and git could not say whether it is ignored "
                          f"(exit {answer.returncode}: {answer.stderr.strip()})")

    def add_file(self, path: Path, deck_id: str, kind: str, pages: list[int]) -> str:
        """pages: every page the file is derived from (a contact sheet: each page it shows)."""
        if not pages:
            raise ValueError(f"{path}: a library file derives from at least one page")
        rel = str(path.resolve().relative_to(self.root))
        self.manifest["files"][rel] = {"sha256": sha256(path), "deck": deck_id, "kind": kind, "pages": sorted(pages),
                                       "source_sha256": self.manifest["decks"][deck_id]["sha256"]}
        return rel

    def drop_files(self, deck_id: str, pages: set[int] | None = None, kinds: frozenset[str] | set[str] | None = None) -> int:
        """Delete the deck's files of these kinds that derive from any of these pages."""
        dropped = 0
        for rel, info in list(self.manifest["files"].items()):
            if info["deck"] != deck_id or (kinds is not None and info["kind"] not in kinds):
                continue
            if pages is not None and not pages & set(info["pages"]):
                continue
            (self.root / rel).unlink(missing_ok=True)
            del self.manifest["files"][rel]
            dropped += 1
        return dropped


def page_count(deck: Path) -> int:
    """The deck's pages as the file lists them (pptx sldIdLst, PDF page tree), hidden
    slides included. An unreadable file is refused here, at the door."""
    try:
        n = render.page_count(deck) if gallery.is_pdf(deck) else len(ooxml.Package(str(deck)).slide_parts())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as error:
        raise Refused("deck_unreadable", f"{deck.name}: {error}") from error
    if n < 1:
        raise Refused("no_pages", f"{deck.name} lists no pages")
    return n


def withdraw_images(lib: Library, deck_id: str) -> tuple[int, int]:
    """Permission to keep page images withdrawn: every kept image of the deck goes now."""
    gone = lib.drop_files(deck_id, None, KEPT_IMAGE_KINDS)
    changed = 0
    for entry in lib.pages:
        if entry["deck"] == deck_id and entry.get("image") is not None:
            entry.update({"image": None, "look_at": None, "image_withheld": "image permission withdrawn"})
            changed += 1
    return gone, changed


def permit(lib: Library, deck: Path | None, deck_id: str, owner: str, source_type: str, images: bool, by: str, basis: str,
           licence: str | None) -> tuple[dict, str | None]:
    if lib.manifest["owner"] not in (None, owner):
        raise Refused("owner_mismatch", f"{lib.root} belongs to {lib.manifest['owner']!r}; one company's library is never shared with another")
    if source_type == "company" and owner == "external":
        raise Refused("company_deck_external_owner", "a company deck enters that company's library, not the external one")
    lib.guard_location(owner)
    pages = page_count(deck) if deck else None
    lib.manifest["owner"] = owner
    record = lib.manifest["decks"].setdefault(deck_id, {})
    note = None
    if not images and record.get("permission", {}).get("keep_images"):
        gone, changed = withdraw_images(lib, deck_id)
        note = f"{deck_id}: image permission withdrawn; {gone} kept image files deleted, {changed} entries now carry no image"
    record.update({"file_name": deck.name if deck else None, "sha256": sha256(deck) if deck else None, "source_type": source_type,
                   "pages": pages, "permission": {"keep_images": images, "by": by, "basis": basis, "licence_basis": licence}})
    record.setdefault("excluded_pages", [])
    record.setdefault("excluded", False)
    lib.save()
    return record, note


# --- page facts and the triage proposal ------------------------------------------------------

def without_pages(deck: Path, pages: set[int], tmp: Path) -> Path:
    """A copy of the pptx in which the excluded slides are empty and hidden, and every part
    only they reached (charts, images, notes) is gone: nothing reads or renders them. The
    slide list keeps its length, so page numbers stay the deck's own."""
    pkg = ooxml.Package(str(deck))
    slides = pkg.slide_parts()
    gone_slides = {slides[n - 1] for n in pages}
    keep_rels: dict[str, bytes] = {}
    blank: dict[str, bytes] = {}
    for part in gone_slides:
        root = pkg.root(part)
        tree = root.find(f"{{{ooxml.P}}}cSld/{{{ooxml.P}}}spTree")
        for child in list(tree if tree is not None else []):
            if etree.QName(child).localname not in ("nvGrpSpPr", "grpSpPr"):
                tree.remove(child)  # type: ignore[union-attr]
        for child in list(root):
            if etree.QName(child).localname not in ("cSld", "clrMapOvr"):
                root.remove(child)  # transitions, timing, extensions: nothing of the page remains
        root.set("show", "0")
        blank[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        folder, _, name = part.rpartition("/")
        rels_part = f"{folder}/_rels/{name}.rels"
        rels = pkg.root(rels_part)
        for rel in list(rels):
            if rel.get("Type") != ooxml.REL_LAYOUT:
                rels.remove(rel)
        keep_rels[rels_part] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
    # what the package still reaches once those slides point at their layout only
    reached, queue = {"_rels/.rels", "[Content_Types].xml"}, [t for _, t in pkg.rels("").values()] if "_rels/.rels" in pkg.names else []
    while queue:
        part = queue.pop()
        if part in reached or part not in pkg.names:
            continue
        reached.add(part)
        folder, _, name = part.rpartition("/")
        rels_part = f"{folder}/_rels/{name}.rels" if folder else f"_rels/{name}.rels"
        if rels_part in pkg.names:
            reached.add(rels_part)
        targets = pkg.rels(part).values()
        queue += [t for kind, t in targets if part not in gone_slides or kind == ooxml.REL_LAYOUT]
    out = tmp / deck.name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in pkg.zip.infolist():
            if info.filename in reached:
                z.writestr(info.filename, blank.get(info.filename) or keep_rels.get(info.filename) or pkg.zip.read(info.filename))
    return out


def page_facts(deck: Path, excluded: set[int]) -> tuple[dict[int, dict], tuple[int, int]]:
    """What the file states about each page that is not excluded, read through ooxml.py
    (pptx parts or the PDF reader). Nothing here is a judgement about the page. A PDF
    states no tables or charts: their counts are None there, not zero."""
    prints = ooxml.fingerprint_deck(str(deck))
    if not prints:
        raise Refused("no_pages", f"{deck.name} has no pages")
    size = (prints[0].width, prints[0].height)
    prints = [sp for sp in prints if sp.index + 1 not in excluded]
    return facts_of(prints, None if gallery.is_pdf(deck) else ooxml.Package(str(deck))), size


def facts_of(prints: list, pkg) -> dict[int, dict]:
    """page_facts over prints already read (extract_style.py reads them once for the guide's
    variety; `pkg` is the pptx package, None for a PDF)."""
    shapes_of = [[sh for sh in sp.shapes if sh.layer == "slide"] if sp.source == "pptx" else sp.shapes for sp in prints]
    # A picture at the same box (extract_style's 6pt position grid) on at least half the pages
    # is furniture or the page itself (a printed deck's page image), not an exhibit.
    seen = Counter(b for shapes in shapes_of for b in {quant(sh.box) for sh in shapes if sh.kind == "picture" and sh.box})
    furniture = {b for b, n in seen.items() if n >= max(2, len(prints) / 2)}
    facts = {}
    for sp, slide_shapes in zip(prints, shapes_of, strict=True):
        kinds = [sh.kind for sh in slide_shapes]
        recurring = sum(1 for sh in slide_shapes if sh.kind == "picture" and sh.box and quant(sh.box) in furniture)
        layout_type = pkg.root(sp.layout_part).get("type") if pkg is not None and sp.layout_part else None
        title_ph = any(sh.ph_type == "ctrTitle" for sh in sp.shapes)
        text = " ".join(r.text for r in sp.runs if r.text)
        pdf = sp.source == "pdf"
        facts[sp.index + 1] = {
            "page": sp.index + 1, "hidden": sp.hidden, "generated": sp.generated, "source": sp.source,
            "layout": sp.layout_name or None, "layout_type": layout_type, "ctr_title": title_ph,
            "page_class": sp.page_class if pdf else None,
            "words": sum(r.words for r in sp.runs),
            "tables": None if pdf else max(kinds.count("table"), len(sp.tables)),
            "charts": None if pdf else kinds.count("chart"),
            "pictures": kinds.count("picture") - recurring,
            "recurring_pictures": recurring,
            "text_elements": sum(1 for sh in slide_shapes if sh.kind in ("text_box", "text_shape")),
            "disclaimer_phrase": (m.group(0) if (m := DISCLAIMER_WORDS.search(text)) else None),
        }
    return facts


def propose(facts: list[dict]) -> list[dict]:
    words = [f["words"] for f in facts if not f["hidden"]]
    deck_median = median(words) if words else 0
    out = []
    for f in facts:
        stated = f["tables"] is not None and f["charts"] is not None
        exhibit = (f["tables"] or 0) + (f["charts"] or 0) + f["pictures"]
        found = (f"{f['tables']} tables, {f['charts']} charts" if stated else "tables and charts not stated by a PDF") + f", {f['pictures']} pictures"
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
        elif stated and f["disclaimer_phrase"] and not (f["tables"] or f["charts"]):
            call, why = "disclaimer", f"says {f['disclaimer_phrase']!r} and holds no table or chart"
        elif stated and not exhibit and f["words"] < DIVIDER_WORD_SHARE * deck_median:
            call, why = "divider", f"{f['words']} words against the deck median {deck_median:g}, no table, chart or picture"
        else:
            unstated = "" if stated else " (no divider or disclaimer is proposed without them: look)"
            phrase = f", says {f['disclaimer_phrase']!r}" if f["disclaimer_phrase"] else ""
            call, why = "content", f"{f['words']} words against the deck median {deck_median:g}{phrase}, {found}{unstated}"
        out.append({"page": f["page"], "proposal": call, "evidence": why})
    return out


# --- build -----------------------------------------------------------------------------------

def render_deck(deck: Path, pages: list[int], tmp: Path) -> tuple[dict[int, Path], dict]:
    """The pages asked for (visible and not excluded), at RENDER_WIDTH_PX, through render.py
    (gallery.py's renderer for a pptx, so a face that cannot draw the deck's characters is
    refused the same way). A pptx arrives here with its excluded slides already hidden."""
    if gallery.is_pdf(deck):
        fonts = render.pdf_font_report(deck)
        drawn = render.rasterize(deck, tmp / "pages", 110, pages, RENDER_WIDTH_PX)
        return dict(zip(pages, drawn, strict=True)), fonts
    try:
        drawn, fonts = gallery.render_pages(deck, tmp / "pages", RENDER_WIDTH_PX)
    except gallery.GalleryRefused as refused:
        raise Refused(refused.reason, str(refused)) from refused
    if len(drawn) != len(pages):
        raise Refused("page_count_mismatch", f"{len(drawn)} rendered pages against {len(pages)} visible slides not excluded")
    return dict(zip(pages, drawn, strict=True)), fonts


def stub(deck_id: str, page: int, record: dict, size: dict, layout: str | None, fidelity: str, image: str | None, coder: str) -> dict:
    entry: dict = {"entry_id": f"{deck_id}-p{page}", "deck": deck_id, "page": page, "source_type": record["source_type"],
                   "coder": coder, "page_size": size, "layout": layout, "render_fidelity": fidelity, "image": image,
                   "image_withheld": None if image else "no permission recorded to keep this deck's page images"}
    entry.update({field: None for field in TAG_FIELDS})
    return entry


def check_selection(lib: Library, selection: dict[str, set[int] | None], flag: str, deck_ids: set[str] | None) -> None:
    """Every deck an ID:PAGES item names has a record (and is being built, when deck_ids is
    given), and every page it names exists in that deck."""
    for deck_id, pages in selection.items():
        record = lib.manifest["decks"].get(deck_id)
        if record is None:
            raise Refused("unknown_deck", f"{flag} {deck_id}: no permission record in {lib.manifest_path}")
        if deck_ids is not None and deck_id not in deck_ids:
            raise Refused("deck_not_built", f"{flag} {deck_id}: that deck is not among the decks this build reads ({', '.join(sorted(deck_ids))})")
        n = record.get("pages")
        if pages and n is not None and max(pages) > n:
            raise Refused("page_out_of_range", f"{flag} {deck_id}:{max(pages)}: the deck has {n} pages")


def build(lib: Library, decks: list[Path], keep: dict, skip: dict, exclude: dict, coder: str) -> list[str]:
    report = []
    ids = {}
    for deck in decks:
        deck_id = next((i for i, r in lib.manifest["decks"].items() if r["sha256"] == sha256(deck)), None)
        if deck_id is None:
            raise Refused("no_permission", f"{deck.name} (sha256 {sha256(deck)[:12]}) has no permission record in {lib.manifest_path}: run library.py permit first")
        ids[deck] = deck_id
    check_selection(lib, exclude, "--exclude", None)
    check_selection(lib, keep, "--keep", set(ids.values()))
    check_selection(lib, skip, "--skip", set(ids.values()))
    for deck_id in set(keep) & set(skip):
        both = None if keep[deck_id] is None and skip[deck_id] is None else (keep[deck_id] or set()) & (skip[deck_id] or set())
        if both is None or both:
            raise Refused("keep_and_skip", f"{deck_id}: {'every page' if both is None else sorted(both)} named by both --keep and --skip")
    for deck_id, pages in exclude.items():
        record = lib.manifest["decks"][deck_id]
        if pages is None:
            record["excluded"] = True
        else:
            record["excluded_pages"] = sorted(set(record["excluded_pages"]) | pages)
        # an excluded page loses everything derived from it at once, built again or not:
        # its page image, and every contact sheet and triage file that shows or lists it
        gone = lib.drop_files(deck_id, None if pages is None else pages)
        before = len(lib.pages)
        lib.pages = [e for e in lib.pages if not (e["deck"] == deck_id and (pages is None or e["page"] in pages))]
        unchecked = "" if record.get("pages") is not None else " (no deck file recorded: the page range is not checked)"
        report.append(f"{deck_id}: exclude {'every page' if pages is None else sorted(pages)} recorded{unchecked}; "
                      f"{gone} files and {before - len(lib.pages)} entries deleted")
    lib.save()
    for deck in decks:
        deck_id = ids[deck]
        record = lib.manifest["decks"][deck_id]
        lib.guard_location(lib.manifest["owner"])
        excluded = set(record["excluded_pages"])
        if record["excluded"]:
            report.append(f"{deck_id}: on the exclude list whole; nothing rendered")
            continue
        with tempfile.TemporaryDirectory(prefix="library-render-") as tmp:
            source = without_pages(deck, excluded, Path(tmp)) if excluded and not gallery.is_pdf(deck) else deck
            report += build_deck(lib, deck_id, record, source, excluded, keep, skip, coder, Path(tmp))
        lib.save()
    return report


def build_deck(lib: Library, deck_id: str, record: dict, deck: Path, excluded: set[int], keep: dict, skip: dict, coder: str,
               tmp: Path) -> list[str]:
    report = []
    facts, (w, h) = page_facts(deck, excluded)
    if len(facts) + len(excluded) != record["pages"]:
        raise Refused("page_count_mismatch", f"{deck_id}: {len(facts)} pages read and {len(excluded)} excluded against {record['pages']} at permit")
    size = {"width_in": round(w / EMU_PER_INCH, 3), "height_in": round(h / EMU_PER_INCH, 3), "aspect": round(w / h, 3),
            "measured_from": "the deck's page size"}
    triage = propose(list(facts.values())) + [{"page": p, "proposal": None, "evidence": None} for p in sorted(excluded)]
    triage.sort(key=lambda r: r["page"])
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
    renderable = [p for p, f in facts.items() if not f["hidden"]]
    keep_images = bool(record["permission"]["keep_images"])
    work = lib.root / "work" / deck_id
    page_dir = lib.root / "pages" / deck_id
    lib.drop_files(deck_id, None, KEPT_IMAGE_KINDS | {WITHHELD_KIND, "triage"})
    work.mkdir(parents=True, exist_ok=True)
    if keep_images:
        page_dir.mkdir(parents=True, exist_ok=True)
    drawn, fonts = render_deck(deck, renderable, tmp)
    fidelity = gallery.render_fidelity(fonts)
    record.update({"render_fidelity": fidelity, "page_size": size})
    labelled = []
    for row in triage:
        if row["page"] in drawn:
            target = tmp / "sheet" / f"p{row['page']:03d} {row['decision']} ({row['proposal']})"
            target.parent.mkdir(exist_ok=True)
            labelled.append(Path(shutil.copyfile(drawn[row["page"]], target.with_suffix(".png"))))
    sheet = render.grid(labelled, work / "triage.png", cols=6, cell_w=320) if labelled else None
    if sheet:
        lib.add_file(sheet, deck_id, "contact_sheet" if keep_images else WITHHELD_KIND, sorted(drawn))
    kept = {e["page"]: e for e in lib.pages if e["deck"] == deck_id}
    entries = []
    for row in triage:
        if row["decision"] != "content" or row["page"] not in drawn:
            continue
        p = row["page"]
        target = (page_dir if keep_images else work) / f"p-{p:03d}.png"
        shutil.copyfile(drawn[p], target)
        rel = lib.add_file(target, deck_id, "page_image" if keep_images else WITHHELD_KIND, [p])
        entry = stub(deck_id, p, record, size, facts[p]["layout"], fidelity, rel if keep_images else None, coder)
        prior = kept.get(p)
        if prior is not None and prior.get("source_sha256") == record["sha256"]:
            entry.update({k: prior[k] for k in TAG_FIELDS})
        entry["source_sha256"] = record["sha256"]
        entry["look_at"] = rel
        entries.append(entry)
    lib.pages = [e for e in lib.pages if e["deck"] != deck_id] + entries
    triage_path = work / "triage.json"
    # an excluded page appears by number and decision only: none of its facts is written
    triage_path.write_text(json.dumps({"deck": deck_id, "rule": {"divider_word_share": DIVIDER_WORD_SHARE, "disclaimer_words": DISCLAIMER_WORDS.pattern},
                                       "pages": [dict(row, **facts.get(row["page"], {})) for row in triage]}, indent=1) + "\n")
    lib.add_file(triage_path, deck_id, "triage", sorted(facts))
    report.append(f"{deck_id}: {record['pages']} pages ({len(excluded)} excluded), render {fidelity}, images {'kept' if keep_images else 'withheld (tags only)'}; "
                  f"contact sheet {sheet}")
    report.append("  page  proposal    decision  by          evidence")
    for row in triage:
        report.append(f"  {row['page']:>4}  {row['proposal'] or '-':<10}  {row['decision']:<8}  {row['by']:<10}  {row['evidence'] or ''}")
    report.append(f"  {len(entries)} stub entries; tag them with library.py tag after looking at each look_at image")
    return report


# --- tags and the check ----------------------------------------------------------------------

def check_entry(entry: dict) -> list[str]:
    problems = []
    untagged = [f for f in TAG_FIELDS if entry.get(f) is None]
    if untagged:
        problems.append(f"not tagged yet: {', '.join(untagged)}")

    def one_of(field: str, value: object, allowed: tuple[str, ...] | dict[str, str]) -> None:
        if value is not None and not (isinstance(value, str) and value in allowed):
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
            problems += [f"designer question {q!r} does not open with a question (designer questions are questions, never rules)"
                         for q in questions if not isinstance(q, str) or not QUESTION_LEAD.match(q.strip())]
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
                stray = sorted(set(ex) - set(EXHIBIT_FIELDS))
                if missing:
                    problems.append(f"exhibit {i} not tagged: {', '.join(missing)}")
                if stray:
                    problems.append(f"exhibit {i} carries {', '.join(stray)}: an exhibit is tagged in words ({', '.join(EXHIBIT_FIELDS)})")
                for field in EXHIBIT_TEXT_FIELDS:
                    value = ex.get(field)
                    if value is not None and not (isinstance(value, str) and value.strip()):
                        problems.append(f"exhibit {i} {field} must be words")
                notes = ex.get("annotations_as_recorded")
                if notes is not None and not (isinstance(notes, list) and all(isinstance(v, str) and v.strip() for v in notes)):
                    problems.append(f"exhibit {i} annotations_as_recorded must be a list of words ([] = looked, none)")
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
    # every file, not only those an entry points at: a contact sheet belongs to no entry
    for rel, info in sorted(lib.manifest["files"].items()):
        record = lib.manifest["decks"].get(info["deck"])
        if record is None:
            lines.append(f"file {rel}: its deck {info['deck']} has no permission record")
            failures += 1
            continue
        shown = sorted(set(info["pages"]) & set(record["excluded_pages"])) if not record["excluded"] else info["pages"]
        if shown:
            lines.append(f"file {rel}: derives from excluded pages {shown}")
            failures += 1
        if info["kind"] in KEPT_IMAGE_KINDS and not record["permission"]["keep_images"]:
            lines.append(f"file {rel}: a kept {info['kind']} though its deck's permission keeps no page image")
            failures += 1
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
            gone = sum(lib.drop_files(d, None, {WITHHELD_KIND}) for d in lib.manifest["decks"])
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

#: the corpus coders' closed-list tags, left behind on import: the entry keeps the words
#: each exhibit was recorded in (type, data shape, message, annotations as recorded)
CORPUS_LIST_TAGS = ("family", "annotation_moves")


def _corpus_problems(page: dict) -> list[str]:
    """Every corpus exhibit that does not carry its words (type, data shape, message as
    strings, annotations as recorded as a list of strings), and an exhibits value that is not
    a list (never read as empty)."""
    where = f"{page.get('deck')}-p{page.get('page')}"
    exhibits = page.get("exhibits")
    if not isinstance(exhibits, list):
        return [f"{where}: exhibits {exhibits!r} is not a list"]
    out: list[str] = []
    for i, ex in enumerate(exhibits):
        if not isinstance(ex, dict):
            out.append(f"{where}: exhibit {i} {ex!r} is not an object")
            continue
        out += [f"{where}: exhibit {i} {f} {ex.get(f)!r} is not words" for f in EXHIBIT_TEXT_FIELDS if not (isinstance(ex.get(f), str) and ex[f].strip())]
        notes = ex.get("annotations_as_recorded")
        if not (isinstance(notes, list) and all(isinstance(v, str) for v in notes)):
            out.append(f"{where}: exhibit {i} annotations_as_recorded {notes!r} is not a list of words")
    return out


CORPUS_HOUSE = {"investment bank": "investment bank", "consulting": "consulting", "asset manager market guide (JPM)": "chart book"}


def import_corpus(lib: Library, source: Path, by: str, basis: str) -> list[str]:
    """The development corpus's curated pages (pagecraft library.json) as external entries.
    The corpus kept no deck files beside the images, so a deck's sha256 is null (no
    evidence) and the page size is the stored image's own aspect."""
    payload = json.loads(source.read_text())
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list) or not all(isinstance(p, dict) for p in pages):
        raise Refused("corpus_unreadable", f"{source} has no pages list of objects")
    unknown = [problem for p in pages for problem in _corpus_problems(p)]
    if unknown:
        raise Refused("corpus_unreadable", f"nothing imported; {len(unknown)} corpus exhibits refused: {'; '.join(unknown)}")
    lines = []
    for page in pages:
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
        rel = lib.add_file(target, deck_id, "page_image", [page["page"]])
        size = {"width_in": None, "height_in": None, "aspect": round(wpx / hpx, 3),
                "measured_from": f"the stored image ({wpx} x {hpx} px); the corpus kept no page size"}
        entry = stub(deck_id, page["page"], record, size, None, "no evidence: rendered by the corpus readers", rel, page["reader"])
        entry["source_sha256"] = None
        entry["look_at"] = rel
        house = page["house_type"]
        entry.update({k: page[k] for k in TAG_FIELDS})
        entry["exhibits"] = [{k: v for k, v in ex.items() if k not in CORPUS_LIST_TAGS} for ex in page["exhibits"]]
        entry["house_type"] = CORPUS_HOUSE.get(house, "other")
        if entry["house_type"] != house:
            entry["house_type_as_recorded"] = house
        lib.pages = [e for e in lib.pages if e["entry_id"] != entry["entry_id"]] + [entry]
        lines.append(f"{entry['entry_id']}: {'; '.join(check_entry(entry)) or 'ok'}")
    lib.save()
    return lines


# --- pick ------------------------------------------------------------------------------------

def _vocab(value: str | None, allowed: tuple[str, ...] | dict[str, str], flag: str) -> str | None:
    """The term asked, by its slug or its label; the slug is what entries store."""
    if value is None:
        return None
    labels = allowed if isinstance(allowed, dict) else {a: a for a in allowed}
    asked = value.strip().lower()
    hit = [slug for slug, label in labels.items() if asked in (slug.lower(), label.lower())]
    if not hit:
        near = sorted(labels, key=lambda a: -len(gallery.words(labels[a]) & gallery.words(value)))[:4]
        raise Refused("not_in_vocabulary", f"{flag} {value!r}; nearest: {' | '.join(f'{a} ({labels[a]})' if a != labels[a] else a for a in near)} (library.py vocab lists all)")
    return hit[0]


def _aspect(value: str | None) -> float | None:
    if value is None:
        return None
    w, colon, h = value.partition(":")
    try:
        ratio = float(w) / float(h) if colon else float(w)
    except (ValueError, ZeroDivisionError):
        ratio = math.nan
    if not (math.isfinite(ratio) and ratio > 0):
        raise Refused("bad_aspect", f"--aspect {value!r}: give the page asked as W:H with both positive (4:3, 16:9, 11:8.5) or one positive ratio")
    return ratio


def entry_words(entry: dict) -> frozenset[str]:
    text = [entry.get("title"), entry.get("composition_as_recorded"), entry.get("why_instructive"),
            *(entry.get("designer_questions") or []), *(entry.get("emphasis_devices") or [])]
    for ex in entry.get("exhibits") or []:
        text += [ex.get("type"), ex.get("message"), *(ex.get("annotations_as_recorded") or [])]
    return frozenset().union(*(gallery.words(t) for t in text if isinstance(t, str)))


def score(entry: dict, intent: frozenset[str], composition: str | None, shape: frozenset[str], aspect: float | None) -> dict:
    exhibits = entry.get("exhibits") or []
    entry_aspect = (entry.get("page_size") or {}).get("aspect")
    return {
        "composition": composition is not None and entry.get("composition_family") == composition,
        "aspect": aspect is not None and entry_aspect is not None and abs(entry_aspect - aspect) <= ASPECT_TOLERANCE,
        # one-character tokens ("x" between dimensions, a lone count) are in nearly every recorded shape
        "data_shape": len({w for w in shape if len(w) > 1} & frozenset().union(*(gallery.words(ex.get("data_shape") or "") for ex in exhibits))),
        "words": len(intent & entry_words(entry)),
    }


def pick(intent_text: str, composition: str | None, data_shape: str | None, aspect_text: str | None,
         gallery_dir: Path | None, own: Path | None, external: list[Path], exclude: set[str], top: int, guide: dict | None = None) -> str:
    composition = _vocab(composition, COMPOSITIONS, "--composition")
    aspect = _aspect(aspect_text)
    intent, shape = gallery.words(intent_text), gallery.words(data_shape or "")
    libraries: list[tuple[str, Library]] = []
    if gallery_dir is not None and not (gallery_dir / "manifest.json").is_file():
        raise Refused("no_gallery", f"--gallery {gallery_dir} holds no gallery.py manifest.json")
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
             f"asked: composition={composition} data shape words={' '.join(sorted(shape)) or None} aspect={aspect_text}",
             "searched in order: " + "; ".join(
                 ([f"the reference's own gallery {gallery_dir}"] if gallery_dir else ["no reference gallery given"])
                 + [f"{label} {lib.root} ({len(lib.pages)} entries)" for label, lib in libraries])]
    if not external:
        lines.append(f"   not searched: no external library ({EXTERNAL_LIBRARY} does not exist; build it with library.py import, "
                     "or pass --library DIR)")
    if own is None:
        lines.append("   not searched: no company library (--own DIR)")
    if gallery_dir is not None:
        # a word in every crop caption ("the", "deck", "appears") tells no crop from another
        captions = [gallery.words(c["caption"]) for c in json.loads((gallery_dir / "manifest.json").read_text())["crops"]]
        common = frozenset.intersection(*captions) if len(captions) > 1 else frozenset()
        if intent & common:
            lines.append(f"   words in every gallery caption, left out: {' '.join(sorted(intent & common))}")
        # the data shape asked is in words the digest records carry too
        asked = " ".join([*sorted(intent - common), *sorted(shape)])
        exemplars, crops = gallery.rank(gallery_dir, asked, guide)
        best = max([o for _, o, _ in exemplars] + [o for _, o in crops], default=0)
        lines.append("1. the reference's own gallery, " + ("tagged by the completed digest (each page's title and records)" if gallery.page_words(guide) else
                     "UNTAGGED: pass --guide (the completed guide) so each page carries its title and digest records; "
                     "without it the overlap reads shape kinds only and is 0 for nearly every intent"))
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
        untagged = sum(1 for e in usable if any(e.get(f) is None for f in TAG_FIELDS))
        failing = len(usable) - len(good) - untagged
        # a word every entry carries tells no entry from another
        common = frozenset.intersection(*(entry_words(e) for e in good)) if len(good) > 1 else frozenset()
        for entry in good:
            s = score(entry, intent - common, composition, shape, aspect)
            structured = int(s["composition"])
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
        lines.append(f"{n}. {label}: {len(good)} tagged entries, {len(ranked)} share a tag or a word"
                     + (f"; not ranked: {untagged} not tagged yet" if untagged else "")
                     + (f"; not ranked: {failing} tagged and failing check" if failing else ""))
        if not good:
            lines.append("   no evidence: the library holds no tagged entry that passes check")
        elif not chosen:
            lines.append("   no evidence: no tagged entry shares a tag or a word with this intent")
        for _, entry, s in chosen:
            entry_aspect = (entry.get("page_size") or {}).get("aspect")
            flags = [k for k in ("composition", "aspect") if s[k]]
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
    p.add_argument("--data-shape", help="the data's shape in words; matched against the words each exhibit was tagged in")
    p.add_argument("--aspect", help="the page asked, as W:H (4:3, 16:9, 11:8.5)")
    p.add_argument("--gallery", help="the reference's own gallery.py output")
    p.add_argument("--guide", help="the completed guide: its digest records and titles tag the gallery's pages")
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
        if args.cmd == "pick" and args.top < 1:
            raise Refused("bad_top", f"--top {args.top}: ask for at least one example")
        if args.cmd == "permit":
            deck = Path(args.deck).resolve()
            record, note = permit(Library(Path(args.lib), create=True), deck, args.id or deck.stem, args.owner, args.source_type,
                                  args.images == "yes", args.by, args.basis, args.licence)
            print(json.dumps(record, indent=1))
            if note:
                print(note)
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
            print(pick(args.intent, args.composition, args.data_shape, args.aspect, Path(args.gallery) if args.gallery else None,
                       Path(args.own) if args.own else None, external, set(args.exclude), args.top,
                       json.loads(Path(args.guide).read_text()) if args.guide else None))
        elif args.cmd == "import":
            lib = Library(Path(args.lib), create=True)
            lib.guard_location("external")
            print("\n".join(import_corpus(lib, Path(args.source), args.by, args.basis)))
        elif args.cmd == "forget":
            print(forget(Library(Path(args.lib)), args.deck))
        elif args.cmd == "vocab":
            print(json.dumps({"house_type": HOUSE_TYPES, "title_register": TITLE_REGISTERS, "composition_family": COMPOSITIONS,
                              "spelling": "a title register is the slug; an exhibit is tagged in words, never from a list",
                              "tag_fields": TAG_FIELDS, "exhibit_fields": EXHIBIT_FIELDS}, indent=1))
    except Refused as refused:
        print(json.dumps({"refused": refused.reason, "detail": str(refused)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
