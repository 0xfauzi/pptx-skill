#!/usr/bin/env python3
"""The font report, and the extraction of fonts a .pptx reference embeds. Nothing here
downloads, fetches or installs a font: a face this machine lacks is reported, and the user
supplies the file.

    fonts.py report [REF.pptx|REF.pdf] [--guide GUIDE.json] -o OUT.json [--pages A-B]
    fonts.py extract REF.pptx --licence-confirmed "WHAT THE USER SAID"

Both read and write the work folder's fonts directory that DECK_FONTS names (created when
missing), and refuse by name when DECK_FONTS is unset.

report: every face the reference names (theme, runs, bullets, a .pptx's embedded fonts, a
PDF's font list, subset names included) or, with --guide alone, every face the guide
names. Each face is resolved in this order: a file in the fonts folder; an installed file
of the face or of a metric-compatible face (fontconfig's folders and the standard macOS and
Windows folders); a font the .pptx embeds whose fsType allows embedding (extractable once
the user confirms a licence). A PDF's embedded copy is never used: a subset holds only the
glyphs the PDF sets. For each face still missing: the stand-in the build would measure
(fc-match's answer, the face the renderer draws, marked metric-compatible or not), the
width that stand-in sets the reference's own text at against the reference face (measured
from a PDF's own glyph widths; a .pptx stores no widths, so there it says it cannot be
measured), and what the user can supply. Writes OUT.json and OUT.md (the report to show
the user) and prints OUT.md. Exit 0: every face that sets text is resolved, or has its
stand-in named under typography.families.substitutes in --guide; with --guide, only the
faces the guide sets count, and a face only the reference sets is listed. Exit 3: the user must
act (supply files, confirm a licence, or approve the stand-ins). Nothing is embedded in the
built deck (references/fonts.md, "Embedding"), so the report also lists the faces a
recipient must have.

extract: writes each font the .pptx embeds whose fsType is installable or editable, and
that is complete (not a subset), into the fonts folder as a .ttf or .otf, and appends the
confirmation, with the file's sha256 and the reference's, to licence-confirmations.json
there. Without --licence-confirmed it lists what it would write and exits 2. A restricted
or preview-and-print font, a subset, and a MicroType Express payload are never written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli  # noqa: E402
import fontfiles  # noqa: E402
import ooxml  # noqa: E402
import textfit  # noqa: E402

EXIT_USER_MUST_ACT = 3
EXIT_NOT_CONFIRMED = 2
REL_FONT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
EMBED_STYLES = {"regular": (False, False), "bold": (True, False), "italic": (False, True), "boldItalic": (True, True)}
#: the share of runs the width spread leaves out at each end: the 10th to 90th percentile,
#: the same band the draft's density bands use (references/intake.md)
SPREAD_PERCENTILE = 10
STATUS_RESOLVED = ("work_folder", "installed", "metric_compatible", "stand_in_approved")
EMBEDDING_NOTE = ("not written: LibreOffice 24.2, the one renderer here, drew none of three test decks with an embedded font "
                  "(sfnt bytes, EOT, EOT with XOR) in that font, so a written font could not be checked; PowerPoint was not measured")


def fonts_folder() -> Path:
    value = os.environ.get(textfit.WORK_FONTS_ENV, "")
    if not value.strip():
        raise SystemExit(f"refused: {textfit.WORK_FONTS_ENV} is not set. Set it in the same shell call: "
                         f"export {textfit.WORK_FONTS_ENV}=\"$DECK_WORK/fonts\" (the work folder's fonts directory; {cli.UNSET_HINT})")
    folder = cli.out_path(value, f"fonts folder ({textfit.WORK_FONTS_ENV})")
    if not folder.is_absolute():
        raise SystemExit(f"refused: {textfit.WORK_FONTS_ENV}={value!r} is not an absolute path")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def styles_of(bold: bool, italic: bool) -> str:
    return {(False, False): "regular", (True, False): "bold", (False, True): "italic", (True, True): "bold italic"}[(bold, italic)]


# --- the faces a reference or a guide names ----------------------------------------------

def pptx_faces(ref: Path) -> dict[str, dict]:
    """face -> {used_for, styles}: text (a run or chart text resolves to it), bullets (a
    bullet glyph only) or declared (named in a theme or a property, setting no text)."""
    import render
    declared = render.declared_fonts(ref)
    used, text_faces = render.codepoints_by_face(ref)
    styles: dict[str, set[tuple[bool, bool]]] = {}
    for slide in ooxml.fingerprint_deck(str(ref)):
        for run in (*slide.runs, *slide.chrome_runs):
            if run.family and run.text.strip():
                styles.setdefault(run.family, set()).add((bool(run.bold), bool(run.italic)))
    out = {}
    for face in sorted(declared | set(used)):
        used_for = "text" if face in text_faces else "bullets" if face in used else "declared"
        out[face] = {"used_for": used_for, "styles": sorted(styles.get(face) or ({(False, False)} if used_for == "text" else set()))}
    return out


def embedded_fonts(ref: Path) -> dict[str, list[dict]]:
    """typeface -> one entry per embedded style: the sfnt read from its part, or why not."""
    pkg = ooxml.Package(str(ref))
    out: dict[str, list[dict]] = {}
    with pkg.zip:
        if "ppt/presentation.xml" not in pkg.names:
            return out
        root = pkg.root("ppt/presentation.xml")
        rels = pkg.rels("ppt/presentation.xml")
        for entry in root.iter(f"{{{P}}}embeddedFont"):
            font = entry.find(f"{{{P}}}font")
            typeface = (font.get("typeface") if font is not None else None) or ""
            if not typeface.strip():
                continue
            for tag, (bold, italic) in EMBED_STYLES.items():
                el = entry.find(f"{{{P}}}{tag}")
                if el is None:
                    continue
                rid = el.get(f"{{{R}}}id")
                record: dict = {"style": styles_of(bold, italic), "bold": bold, "italic": italic}
                kind, target = rels.get(rid, (None, None))
                if kind != REL_FONT or target not in pkg.names:
                    record["unusable"] = f"relationship {rid} names no font part in the package"
                    out.setdefault(typeface, []).append(record)
                    continue
                record["part"] = target
                try:
                    unwrapped = fontfiles.unwrap_embedded(pkg.zip.read(target), target)
                    info = fontfiles.faces_in_bytes(unwrapped.data, target)[0]
                except fontfiles.FontFileError as error:
                    record["unusable"] = str(error)
                    out.setdefault(typeface, []).append(record)
                    continue
                permission = info.embedding
                if unwrapped.eot_fs_type is not None and unwrapped.eot_fs_type != info.fs_type:
                    # the wrapper and the font disagree: the more restrictive of the two holds
                    wrapper = fontfiles.embedding_of(unwrapped.eot_fs_type, info.os2_version)[0]
                    order = ["installable", "editable", "preview_print", "restricted"]
                    permission = max(permission, wrapper, key=order.index)
                record.update({"wrapper": unwrapped.wrapper, "subset": unwrapped.subset, "permission": permission, "fs_type": info.fs_type,
                               "family_in_file": info.legacy_family, "data": unwrapped.data,
                               "suffix": ".otf" if unwrapped.data[:4] == b"OTTO" else ".ttf"})
                if textfit.normalize_family(info.legacy_family) != textfit.normalize_family(typeface) and \
                        textfit.normalize_family(info.family) != textfit.normalize_family(typeface):
                    record["unusable"] = f"the font in {target} is named {info.legacy_family!r}, not {typeface!r}"
                elif unwrapped.subset:
                    record["unusable"] = "a subset: the deck embedded only the characters it sets, so new text would lack glyphs"
                elif not fontfiles.PERMITS[permission]["embed"] or info.bitmap_only:
                    record["unusable"] = f"fsType {info.fs_type} ({permission}): the licence bits do not allow taking it out of the deck to set new text"
                out.setdefault(typeface, []).append(record)
    return out


_PDFFONTS_ROW = re.compile(r"^(\S+)\s+.*?\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$")


def pdf_faces(ref: Path) -> dict[str, dict]:
    """face -> {used_for, styles, embedded, subset, names}: pdffonts' list, family names
    read as ooxml.py reads them (a subset tag ABCDEF+ removed)."""
    try:
        listing = subprocess.run(["pdffonts", str(ref)], capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"refused: pdffonts did not run on {ref}: {error}") from None
    out: dict[str, dict] = {}
    for line in listing.splitlines()[2:]:
        m = _PDFFONTS_ROW.match(line)
        if not m or m.group(1) == "[none]":
            continue
        family, bold = ooxml._pdf_family(m.group(1))
        if not family:
            continue
        e = out.setdefault(family, {"used_for": "text", "styles": set(), "embedded": True, "subset": True, "names": []})
        italic = "italic" in m.group(1).lower() or "oblique" in m.group(1).lower()
        e["styles"].add((bold, italic))
        e["embedded"] = e["embedded"] and m.group(2) == "yes"
        e["subset"] = e["subset"] and m.group(3) == "yes"
        e["names"].append(m.group(1))
    for e in out.values():
        e["styles"] = sorted(e["styles"])
    return out


def guide_faces(guide: dict) -> dict[str, dict]:
    """The faces the build sets text in: the major and minor families and each role's
    face, with the bold and italic the roles ask for (fallbacks set no text)."""
    t = guide.get("typography") or {}
    fam = t.get("families") or {}
    names: dict[str, set[tuple[bool, bool]]] = {}
    for key in ("major", "minor"):
        if isinstance(fam.get(key), str):
            names.setdefault(fam[key], set()).add((False, False))
    for role in (t.get("roles") or {}).values():
        if isinstance(role, dict) and isinstance(role.get("family"), str):
            face = fam.get(role["family"]) if role["family"] in ("major", "minor") else role["family"]
            if isinstance(face, str):
                names.setdefault(face, set()).add((int(role.get("weight") or 400) >= 600, bool(role.get("italic"))))
    return {face: {"used_for": "text", "styles": sorted(s or {(False, False)})} for face, s in sorted(names.items())}


# --- the width of a stand-in against the reference's own text -------------------------------

def pdf_width_difference(ref: Path, face: str, stand_in_path: str, ruler: textfit.Ruler, pages: tuple[int, int] | None) -> dict:
    """The stand-in's width against the reference face's, over every upright word the PDF
    sets in `face`: the reference width is the word's box on the page (the PDF's own glyph
    widths and positions), the stand-in's is the word shaped whole at the same size. Spaces
    are left out: a PDF moves words apart when it justifies a line."""
    import pdfplumber
    ratios: list[float] = []
    total_ref = total_new = 0.0
    with pdfplumber.open(str(ref)) as pdf:
        for i, page in enumerate(pdf.pages):
            if pages and not pages[0] <= i + 1 <= pages[1]:
                continue
            words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, use_text_flow=True)
            for word in words:
                family, bold = ooxml._pdf_family(word.get("fontname"))
                if family != face or bold:
                    continue
                if not word.get("upright", True):
                    continue
                text = str(word["text"])
                ref_pt = float(word["x1"]) - float(word["x0"])
                size = float(word["size"])
                if ref_pt <= 0 or size <= 0 or not text.strip():
                    continue
                new_pt = textfit.advance_emu(ruler, text, stand_in_path, size) / textfit.EMU_PER_POINT
                ratios.append(new_pt / ref_pt)
                total_ref += ref_pt
                total_new += new_pt
    if not ratios:
        return {"measurable": False, "why": f"the PDF sets no upright regular-weight word in {face} on the pages read"}
    ratios.sort()
    k = len(ratios) * SPREAD_PERCENTILE // 100
    return {"measurable": True, "percent": round(100 * (total_new / total_ref - 1), 1), "runs": len(ratios),
            "spread_percent": [round(100 * (ratios[k] - 1), 1), round(100 * (ratios[len(ratios) - 1 - k] - 1), 1)],
            "basis": f"every upright regular-weight word the PDF sets in {face}, measured whole in the stand-in at its own size against "
                     f"its box on the page; spread: {SPREAD_PERCENTILE}th to {100 - SPREAD_PERCENTILE}th percentile of words; spaces left out"}


# --- the report --------------------------------------------------------------------------------

def user_path(path: str) -> str:
    work = textfit.work_fonts()
    return (work.copies.get(path) if work else None) or path


def resolve_face(face: str, info: dict, index: textfit.FaceIndex, embedded: dict[str, list[dict]], substitutes: dict,
                 ref: Path | None, kind: str, ruler: textfit.Ruler, folder: Path, pages: tuple[int, int] | None) -> dict:
    entry: dict = {"face": face, "used_for": info["used_for"], "styles": [styles_of(*s) for s in info["styles"]]}
    if face.lower().startswith(ooxml.SYMBOL_FACES):
        entry["status"] = "symbol"
        entry["note"] = "a symbol face: bullets and marks, never measured as text"
        return entry
    try:
        found = index.resolve(face)
    except LookupError:
        found = None
    if found is not None:
        work = textfit.work_fonts()
        in_folder = bool(work and found.path in work.copies)
        entry["status"] = "work_folder" if in_folder and found.provenance == "exact" else "installed" if found.provenance == "exact" else "metric_compatible"
        entry["file"] = user_path(found.path)
        entry["measured_with"] = {"family": found.family, "file": user_path(found.path)}
        missing_styles = []
        for bold, italic in info["styles"]:
            try:
                index.resolve(face, bold=bold, italic=italic)
            except LookupError:
                missing_styles.append(styles_of(bold, italic))
        if missing_styles:
            entry["styles_missing"] = missing_styles
            entry["user_can_supply"] = f"licensed .ttf or .otf files of {face} in {', '.join(missing_styles)}, put in {folder}; then run this report again"
        drawn = textfit.fc_match(face)[0]
        if textfit.normalize_family(drawn) != textfit.normalize_family(found.family):
            entry["renderer_draws"] = drawn
            entry["warning"] = (f"the text ruler measures {found.family} ({entry['file']}) but fontconfig draws {face} as {drawn}: "
                                f"the renderer does not see that file; put a copy in {folder}")
        return entry
    # not on this machine
    entry["status"] = "missing"
    entry["source"] = "named"
    entry["width_difference"] = {"measurable": False, "why": "a .pptx stores no glyph widths, and no file of the face is here"}
    if kind == "pdf":
        entry["source"] = "pdf_subset" if info.get("subset") else "pdf_embedded" if info.get("embedded") else "pdf_named"
        entry["pdf_names"] = sorted(set(info.get("names") or []))
        if info.get("embedded"):
            entry["note"] = ("the PDF embeds a subset of this face: it holds only the glyphs the PDF sets, so it never sets new text" if info.get("subset")
                             else "the PDF embeds this face; the skill does not take fonts out of a PDF")
    elif kind == "guide":
        entry["width_difference"] = {"measurable": False, "why": "no reference: there is no reference text to measure against"}
    for record in embedded.get(face, []):
        entry["source"] = "pptx_embedded"
        entry.setdefault("embedded", []).append({k: v for k, v in record.items() if k not in ("data", "bold", "italic")})
        if "permission" in record:
            entry["permission"] = record["permission"]
    extractable = [r for r in embedded.get(face, []) if "unusable" not in r]
    if extractable:
        entry["status"] = "embedded_extractable"
        entry["width_difference"] = {"measurable": False, "why": "measurable once the face is extracted; then no stand-in is needed"}
        entry["user_can_supply"] = (f"the reference embeds {face} ({', '.join(r['style'] for r in extractable)}) and its fsType allows embedding. "
                                    "Ask the user whether they hold a licence for it; when they confirm, run: python3 scripts/fonts.py extract "
                                    f"REF --licence-confirmed \"<their words>\". Or they put licensed files of {face} in {folder}")
        return entry
    drawn = textfit.fc_match(face)[0]
    if textfit.normalize_family(drawn) == textfit.normalize_family(face):
        entry["note"] = (f"fontconfig draws {face} from {textfit.fc_match(face)[1]}, a folder the text ruler does not read: "
                         f"put a copy of that file in {folder}")
    approved = substitutes.get(face)
    known = sorted(next((cls for cls in textfit.METRIC_ALIAS_CLASSES if textfit.normalize_family(face) in cls), frozenset())
                   - {textfit.normalize_family(face)})
    entry["stand_in"] = {"face": drawn, "metric_compatible": textfit.metric_alias(face, drawn),
                         "rule": "fc-match's answer, the face the renderer draws: the build measures text in it only when it is named "
                                 "under typography.families.substitutes, and refuses the page until then"}
    if approved:
        entry["stand_in"]["named_in_guide"] = approved
        if textfit.normalize_family(approved) == textfit.normalize_family(drawn):
            entry["status"] = "stand_in_approved"
        else:
            entry["status"] = "stand_in_mismatch"
            entry["stand_in"]["problem"] = f"the guide names {approved!r} but the renderer draws {face!r} as {drawn!r}: the build refuses it"
    try:
        stand_in_face = index.resolve(drawn)
        entry["stand_in"]["file"] = user_path(stand_in_face.path)
    except LookupError:
        stand_in_face = None
        entry["stand_in"]["file"] = None
    if kind == "pdf" and stand_in_face is not None:
        entry["width_difference"] = pdf_width_difference(ref, face, stand_in_face.path, ruler, pages)  # type: ignore[arg-type]
    styles = ", ".join(entry["styles"]) or "regular"
    entry["user_can_supply"] = (f"licensed .ttf, .otf or .ttc files of {face} ({styles}), put in {folder}; then run this report again"
                                + (f"; or files of a metric-compatible face ({', '.join(known)}, as fontconfig's metric table spells them)" if known else ""))
    return entry


def report(args) -> int:
    folder = fonts_folder()
    ref = cli.in_path(args.reference, "reference") if args.reference else None
    guide = json.loads(cli.in_path(args.guide, "--guide").read_text()) if args.guide else None
    if ref is None and guide is None:
        raise SystemExit("refused: give a reference, --guide, or both")
    out = cli.out_path(args.o, "-o report")
    pages = cli.page_range(args.pages) if args.pages else None
    try:
        index = textfit.default_index()
    except textfit.WorkFontsError as error:
        raise SystemExit(f"refused: {error}") from None
    ruler = textfit.ruler_for(guide)
    substitutes = (((guide or {}).get("typography") or {}).get("families") or {}).get("substitutes") or {}
    faces: dict[str, dict] = {}
    embedded: dict[str, list[dict]] = {}
    kind = "guide"
    if ref is not None and ref.suffix.lower() == ".pdf":
        kind, faces = "pdf", pdf_faces(ref)
    elif ref is not None:
        kind = "pptx"
        faces = pptx_faces(ref)
        embedded = embedded_fonts(ref)
        for face in embedded:
            faces.setdefault(face, {"used_for": "declared", "styles": []})
    in_guide: set[str] = set()
    if guide is not None:
        for face, info in guide_faces(guide).items():
            in_guide.add(face)
            if face not in faces or faces[face]["used_for"] != "text":
                faces[face] = {**faces.get(face, {}), **info}
    entries = [resolve_face(face, info, index, embedded, substitutes, ref, kind, ruler, folder, pages) for face, info in sorted(faces.items())]
    if guide is not None:
        # the guide decides what the new deck sets: a face only the reference sets is listed, never blocking
        for e in entries:
            e["in_guide"] = e["face"] in in_guide
    work = textfit.work_fonts()
    blocking = [e for e in entries if e["used_for"] == "text" and e.get("in_guide", True)
                and (e["status"] not in (*STATUS_RESOLVED, "symbol") or e.get("styles_missing"))]
    recipient = []
    for e in entries:
        if e["used_for"] != "text" or e["status"] == "symbol" or not e.get("in_guide", True):
            continue
        line = f"{e['face']}: the deck names it and embeds no font, so a recipient's PowerPoint draws it only if their machine has {e['face']}"
        if e["status"] in ("work_folder", "metric_compatible", "stand_in_approved"):
            line += f" (this machine has it only as {'a file in the fonts folder' if e['status'] == 'work_folder' else 'a stand-in'}: tell the user)"
        recipient.append(line)
    result = {"reference": str(ref) if ref else None, "guide": args.guide, "fonts_folder": str(folder), "ruler": ruler.name,
              "faces": entries, "needs_the_user": [e["face"] for e in blocking], "recipient": recipient, "embedding": EMBEDDING_NOTE,
              "fonts_folder_files_not_used": [{"file": f, "why": w} for f, w in (work.rejected if work else ())],
              "never_downloaded": "the skill never downloads or installs a font; missing faces come from the user, as files they license"}
    out.write_text(json.dumps(result, indent=1))
    md = markdown(result)
    out.with_suffix(".md").write_text(md)
    print(md)
    return EXIT_USER_MUST_ACT if blocking else 0


def markdown(r: dict) -> str:
    lines = ["# Font report", "", f"Reference: {r['reference'] or 'none'}" + (f"; guide: {r['guide']}" if r["guide"] else ""),
             f"Fonts folder: {r['fonts_folder']}", ""]
    lines += ["| Face | Sets | Where it resolves | Stand-in | Width of the stand-in |", "|---|---|---|---|---|"]
    for e in r["faces"]:
        where = {"work_folder": f"fonts folder: {e.get('file')}", "installed": f"installed: {e.get('file')}",
                 "metric_compatible": f"metric-compatible face {e.get('measured_with', {}).get('family')}",
                 "stand_in_approved": "missing; stand-in named in the guide", "stand_in_mismatch": "missing; the guide names another stand-in",
                 "embedded_extractable": "embedded in the reference; extractable after the user confirms a licence",
                 "symbol": "symbol face", "missing": "MISSING"}.get(e["status"], e["status"])
        if e["status"] == "missing" and e.get("source") not in (None, "named"):
            where += f" ({e['source'].replace('_', ' ')}{', ' + e['permission'] if e.get('permission') else ''})"
        if e.get("styles_missing"):
            where += f"; styles missing: {', '.join(e['styles_missing'])}"
        s = e.get("stand_in")
        stand = f"{s['face']} ({'metric-compatible' if s['metric_compatible'] else 'NOT metric-compatible'})" if s else ""
        wd = e.get("width_difference") or {}
        width = (f"{wd['percent']:+.1f}% over {wd['runs']} words (spread {wd['spread_percent'][0]:+.1f}% to {wd['spread_percent'][1]:+.1f}%)"
                 if wd.get("measurable") else (f"cannot be measured: {wd['why']}" if s and wd else ""))
        sets = e["used_for"] + ("" if e.get("in_guide", True) else ", reference only: the guide does not set it")
        lines.append(f"| {e['face']} | {sets} | {where} | {stand} | {width} |")
    lines.append("")
    if r["needs_the_user"]:
        lines += ["## What the user can do", ""]
        for e in r["faces"]:
            if e["face"] in r["needs_the_user"] and e.get("user_can_supply"):
                lines.append(f"- {e['face']}: {e['user_can_supply']}")
        lines += ["- Or approve each stand-in above, knowing the text will set at the width shown; it is then named under "
                  "typography.families.substitutes in the completion.", ""]
    for e in r["faces"]:
        if e.get("warning"):
            lines.append(f"- WARNING {e['face']}: {e['warning']}")
        elif e.get("note") and e["status"] == "missing":
            lines.append(f"- {e['face']}: {e['note']}")
    if r["fonts_folder_files_not_used"]:
        lines += ["## Files in the fonts folder that are not used", ""] + [f"- {x['file']}: {x['why']}" for x in r["fonts_folder_files_not_used"]] + [""]
    lines += ["## For the recipient", "", f"Embedding: {r['embedding']}.", ""] + [f"- {x}" for x in r["recipient"]] + ["",
              "The skill never downloads or installs a font.", ""]
    return "\n".join(lines)


def extract(args) -> int:
    folder = fonts_folder()
    ref = cli.in_path(args.reference, "reference")
    if ref.suffix.lower() != ".pptx":
        raise SystemExit(f"refused: {ref} is not a .pptx; only a .pptx reference embeds whole fonts (a PDF's are subsets)")
    embedded = embedded_fonts(ref)
    writable = [(face, r) for face, records in embedded.items() for r in records if "unusable" not in r]
    refused = [(face, r) for face, records in embedded.items() for r in records if "unusable" in r]
    for face, r in refused:
        print(f"not written: {face} {r['style']}: {r['unusable']}")
    if not embedded:
        print(f"{ref} embeds no font")
    if not writable:
        return 1 if refused else 0
    if not (args.licence_confirmed or "").strip():
        for face, r in writable:
            print(f"would write: {face} {r['style']} (fsType {r['fs_type']}, {r['permission']})")
        print("refused: the user has not confirmed a licence. Ask the user whether they hold a licence for each face above; when they "
              "confirm, run again with --licence-confirmed \"<their words>\"", file=sys.stderr)
        return EXIT_NOT_CONFIRMED
    record_path = folder / textfit.LICENCE_RECORD
    try:
        records = json.loads(record_path.read_text()) if record_path.exists() else []
    except ValueError:
        raise SystemExit(f"refused: {record_path} is not JSON; move it aside and run again") from None
    ref_sha = hashlib.sha256(ref.read_bytes()).hexdigest()
    for face, r in writable:
        name = re.sub(r"[^A-Za-z0-9]+", "", face) + "-" + r["style"].replace(" ", "") + r["suffix"]
        target = folder / name
        target.write_bytes(r["data"])
        records.append({"face": face, "style": r["style"], "file": str(target), "sha256": hashlib.sha256(r["data"]).hexdigest(),
                        "fs_type": r["fs_type"], "permission": r["permission"], "reference": str(ref), "reference_sha256": ref_sha,
                        "confirmation": args.licence_confirmed, "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"wrote {target} ({face} {r['style']}, fsType {r['fs_type']}, {r['permission']})")
    record_path.write_text(json.dumps(records, indent=1))
    print(f"recorded the confirmation in {record_path}")
    return 1 if refused else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    rp = sub.add_parser("report", help="the font report")
    rp.add_argument("reference", nargs="?", default=None)
    rp.add_argument("--guide", default=None)
    rp.add_argument("-o", required=True, help="the report's JSON; the Markdown goes beside it")
    rp.add_argument("--pages", default=None, help="PDF only: the pages to measure widths on, e.g. 3-40")
    ep = sub.add_parser("extract", help="write the fonts a .pptx embeds into the fonts folder")
    ep.add_argument("reference")
    ep.add_argument("--licence-confirmed", default=None, help="the user's own words confirming they hold a licence for the fonts")
    args = ap.parse_args(argv)
    return report(args) if args.command == "report" else extract(args)


if __name__ == "__main__":
    cli.run(main)
