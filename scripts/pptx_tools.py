#!/usr/bin/env python3
"""Package-level tools for .pptx files: read, template, duplicate, delete, clean, validate.

    pptx_tools.py text deck.pptx                      # text per slide, tables as rows (JSON with --json)
    pptx_tools.py layouts deck.pptx                   # masters, layouts, placeholders with boxes, usage counts
    pptx_tools.py template ref.pptx -o tpl.pptx       # the reference with every slide removed: masters, layouts,
                                                      # theme and chrome intact (master reuse)
    pptx_tools.py template ref.pptx -o tpl.pptx --keep 3,7   # keep those slides (page reuse)
    pptx_tools.py duplicate deck.pptx --slide 3 -o out.pptx [--after 5]
    pptx_tools.py delete deck.pptx --slides 2,5 -o out.pptx
    pptx_tools.py clean deck.pptx -o out.pptx         # drop parts nothing references
    pptx_tools.py validate deck.pptx [--render]       # package checks, then a LibreOffice round trip with --render
    pptx_tools.py validate deck.pptx --emit [--guide guide.json]   # plus the emitter read-back (below)

Original code; python-pptx for the package graph, lxml for the XML. Nothing here changes
a slide's content: content edits go through the layout solver and the emitter, or through
python-pptx in a script the model writes.

`validate --emit` walks the saved package for what the two renderers draw differently
(measured on both renderers) and reports each as a problem: a table whose shared interior edge differs
between its two declaring cells (class 4: PowerPoint keeps the first-declared side and
writes it back, LibreOffice draws the heavier one); a stroke with w below 6350 EMU, 0.5pt
(class 5: at 0.25pt PowerPoint inks 0.48px, LibreOffice 1.27px), unless the guide's own
rule width says so, which is reported and not failed; a gradient fill on a slide or in
its charts (classes 6-7); a chart plot group without c:varyColors (class 10); a run whose
size is below the legibility floor (the guide's floors, max(floor_pt, absolute_floor_pt)
per family, resolved by where the run sits: table cells to the table roles' family, chart
parts to the chart family, everything else to the lowest family floor because the file
does not carry the role; without a guide, 7.0pt, measured); a slide-number placeholder
whose text is digits instead of a slidenum field. It also counts the slides carrying the
emitter's origin tag (p:tag name="pptx-skill"), which `text` prints per slide.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn
from pptx.util import Emu

EMU_PER_INCH = 914400
EMU_PER_PT = 12700
sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
from emit_pptx import ORIGIN_TAG_NAME  # noqa: E402  one definition, the producer's
from ooxml import visual_extent  # noqa: E402  the area a rotated shape covers, one definition
# 0.5pt: the thinnest stroke PowerPoint still inks above one pixel (deckgen E38 class 5).
RULE_WEIGHT_FLOOR_EMU = 6350
# The product safety floor: 7.0pt on both render media (deckgen E45), the floor with no guide.
PRODUCT_SAFETY_FLOOR_PT = 7.0
# Every DrawingML stroke: a:ln on shapes and charts, the six table cell borders.
LINE_TAGS = ("a:ln", "a:lnL", "a:lnR", "a:lnT", "a:lnB", "a:lnTlToBr", "a:lnBlToTr")
# Plot groups whose schema carries c:varyColors (ECMA-376 21.2.2).
VARY_COLORS_GROUPS = {"barChart", "bar3DChart", "lineChart", "line3DChart", "pieChart", "pie3DChart", "ofPieChart", "doughnutChart",
                      "areaChart", "area3DChart", "scatterChart", "radarChart", "bubbleChart"}
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


# --- text ---------------------------------------------------------------------------------------


def slide_origin(slide) -> str | None:
    """The emitter's origin tag read back from the slide's tags parts: the name of the
    tag whose value says what made the slide, or None for a slide the deck already had."""
    for rel in slide.part.rels.values():
        if rel.reltype != RT.TAGS or rel.is_external:
            continue
        try:
            root = etree.fromstring(rel.target_part.blob, parser=etree.XMLParser(resolve_entities=False))
        except etree.XMLSyntaxError:
            continue
        for tag in root.iter(qn("p:tag")):
            if tag.get("name") == ORIGIN_TAG_NAME:
                return tag.get("val")
    return None


def _leaf_shapes(shapes):
    """Shapes with the groups opened: a run inside p:grpSp is text too."""
    for shape in shapes:
        if shape.shape_type is not None and "GROUP" in str(shape.shape_type):
            yield from _leaf_shapes(shape.shapes)
        else:
            yield shape


def sniff(path: str) -> None:
    """Refuse what is not a presentation before any library traceback can."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"{path}: no such file")
    head = p.read_bytes()[:4]
    if head.startswith(b"%PDF"):
        raise SystemExit(f"{path}: a PDF; this command reads .pptx (extract_style.py and render.py read PDFs)")
    if head[:2] != b"PK":
        raise SystemExit(f"{path}: not a zip, so not a .pptx")
    with zipfile.ZipFile(path) as z:
        if "ppt/presentation.xml" not in z.namelist():
            raise SystemExit(f"{path}: a zip without ppt/presentation.xml; not a presentation")


def slide_count(path: str) -> int:
    with zipfile.ZipFile(path) as z:
        pres = etree.fromstring(z.read("ppt/presentation.xml"))
    return len(list(pres.iter(qn("p:sldId"))))


def check_slide_numbers(path: str, numbers: list[int]) -> None:
    n = slide_count(path)
    bad = [k for k in numbers if not 1 <= k <= n]
    if bad:
        raise SystemExit(f"{path}: slide numbers {bad} are outside 1..{n}")


def _soft_breaks_as_spaces(text: str) -> str:
    """python-pptx returns an a:br as a vertical tab. The emitter writes the measured
    wrap as a:br in place of the space it broke at, or after the hyphen it broke at
    (textfit.break_opportunities). A word too wide for its line is broken between
    letters with no mark in the file, and reads here as two words."""
    return re.sub(r"(?<=-)\v", "", text).replace("\v", " ")


def slide_text(path: str) -> list[dict]:
    prs = Presentation(path)
    out = []
    for i, slide in enumerate(prs.slides, 1):
        entry: dict = {"slide": i, "layout": slide.slide_layout.name, "origin": slide_origin(slide), "title": None, "blocks": [], "tables": [], "notes": None}
        for shape in _leaf_shapes(slide.shapes):
            if shape.has_text_frame and shape.text_frame.text.strip():
                text = "\n".join(_soft_breaks_as_spaces(p.text) for p in shape.text_frame.paragraphs)
                if shape.is_placeholder and shape.placeholder_format.type is not None and "TITLE" in str(shape.placeholder_format.type) and entry["title"] is None:
                    entry["title"] = text
                else:
                    entry["blocks"].append({"name": shape.name, "text": text})
            if shape.has_table:
                rows = [[_soft_breaks_as_spaces(cell.text) for cell in row.cells] for row in shape.table.rows]
                entry["tables"].append({"name": shape.name, "rows": rows})
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            entry["notes"] = notes or None
        out.append(entry)
    return out


def print_text(entries: list[dict]) -> None:
    for e in entries:
        origin = f" [{ORIGIN_TAG_NAME}: {e['origin']}]" if e.get("origin") else ""
        print(f"--- slide {e['slide']} ({e['layout']}){origin} ---")
        if e["title"]:
            print(f"# {e['title']}")
        for b in e["blocks"]:
            print(b["text"])
        for t in e["tables"]:
            for row in t["rows"]:
                print(" | ".join(row))
        if e["notes"]:
            print(f"[notes] {e['notes']}")
        print()


# --- layouts ---------------------------------------------------------------------------------------


def layouts(path: str) -> dict:
    prs = Presentation(path)
    usage: dict[str, int] = {}
    for slide in prs.slides:
        usage[slide.slide_layout.name] = usage.get(slide.slide_layout.name, 0) + 1
    masters = []
    for mi, master in enumerate(prs.slide_masters):
        lay = []
        for layout in master.slide_layouts:
            phs = []
            for shape in layout.placeholders:
                phs.append({"idx": shape.placeholder_format.idx, "type": str(shape.placeholder_format.type).split(".")[-1].split(" ")[0],
                            "name": shape.name,
                            "box_in": [round(v / EMU_PER_INCH, 3) for v in (shape.left or 0, shape.top or 0, shape.width or 0, shape.height or 0)]})
            others = [{"name": s.name, "kind": str(s.shape_type).split(" ")[0] if s.shape_type else "?",
                       "box_in": [round(v / EMU_PER_INCH, 3) for v in (s.left or 0, s.top or 0, s.width or 0, s.height or 0)]}
                      for s in layout.shapes if not s.is_placeholder]
            lay.append({"name": layout.name, "part": str(layout.part.partname), "used_by_slides": usage.get(layout.name, 0),
                        "placeholders": phs, "other_shapes": others})
        masters.append({"index": mi, "part": str(master.part.partname), "layouts": lay,
                        "shapes": [{"name": s.name, "placeholder": s.is_placeholder} for s in master.shapes]})
    return {"slide_width_in": round(prs.slide_width / EMU_PER_INCH, 3), "slide_height_in": round(prs.slide_height / EMU_PER_INCH, 3),
            "slides": len(prs.slides), "masters": masters}


# --- slide list surgery ---------------------------------------------------------------------------------


def _drop_slide(prs, index: int) -> None:
    """Remove slide `index` (0-based) from the list and drop its relationship so the part
    is not written on save. Parts reachable only through it (notes, charts it alone used)
    disappear with it; shared parts stay.

    A custom show that names the slide holds a second reference, and python-pptx's
    drop_rel declines while any reference remains: the part would survive and collide
    with the next added slide's partname (deckgen render/emit/master.py found this on a
    reference deck). Custom shows over removed slides mean nothing, so they go first."""
    root = prs.part._element
    for custom_shows in root.findall(qn("p:custShowLst")):
        root.remove(custom_shows)
    sld_id_lst = prs.slides._sldIdLst
    sld_id = list(sld_id_lst)[index]
    rid = sld_id.get(qn("r:id"))
    prs.part.drop_rel(rid)
    if rid in prs.part.rels:
        raise SystemExit(f"slide relationship {rid} is referenced more than once in presentation.xml; refusing to leave a colliding part")
    sld_id_lst.remove(sld_id)


def template(path: str, out: str, keep: list[int]) -> dict:
    prs = Presentation(path)
    n = len(prs.slides)
    keep_set = {k for k in keep if 1 <= k <= n}
    for index in range(n - 1, -1, -1):
        if index + 1 not in keep_set:
            _drop_slide(prs, index)
    prs.save(out)
    check = Presentation(out)
    return {"out": out, "slides_kept": len(check.slides), "masters": len(check.slide_masters),
            "layouts": sum(len(m.slide_layouts) for m in check.slide_masters)}


def delete(path: str, out: str, slides: list[int]) -> dict:
    prs = Presentation(path)
    n = len(prs.slides)
    for index in sorted({s - 1 for s in slides if 1 <= s <= n}, reverse=True):
        _drop_slide(prs, index)
    prs.save(out)
    return {"out": out, "slides": len(Presentation(out).slides)}


def duplicate(path: str, out: str, slide_no: int, after: int | None) -> dict:
    """Copy slide `slide_no` (1-based) as a NEW part with its own copies of charts and
    notes, so editing the copy never edits the original. Media (pictures) are shared by
    relationship, which is what PowerPoint itself does."""
    prs = Presentation(path)
    src = prs.slides[slide_no - 1]
    new = prs.slides.add_slide(src.slide_layout)
    # replace the new slide's shape tree with a deep copy of the source's
    sp_tree = new.shapes._spTree
    for child in list(sp_tree):
        if child.tag in (qn("p:sp"), qn("p:pic"), qn("p:graphicFrame"), qn("p:grpSp"), qn("p:cxnSp")):
            sp_tree.remove(child)
    for child in src.shapes._spTree:
        if child.tag in (qn("p:sp"), qn("p:pic"), qn("p:graphicFrame"), qn("p:grpSp"), qn("p:cxnSp")):
            sp_tree.append(copy.deepcopy(child))
    # background and colour map override travel with the slide
    src_csld = src._element.find(qn("p:cSld"))
    bg = src_csld.find(qn("p:bg")) if src_csld is not None else None
    if bg is not None:
        new_csld = new._element.find(qn("p:cSld"))
        new_csld.insert(0, copy.deepcopy(bg))
    # relationships: re-point every r:id in the copied tree
    rid_map: dict[str, str] = {}
    for rel in src.part.rels.values():
        if rel.reltype in (RT.SLIDE_LAYOUT, RT.NOTES_SLIDE):
            continue
        if rel.is_external:
            rid_map[rel.rId] = new.part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
            continue
        target = rel.target_part
        if rel.reltype in (RT.CHART, RT.TAGS):
            # a chart part must be copied, or both slides edit one chart; a tags part is
            # one slide's own record (deckgen 2E-1: a tags part merely related from a
            # slide marked it as generated)
            new_part = _copy_part(prs, target)
            rid_map[rel.rId] = new.part.relate_to(new_part, rel.reltype)
        else:
            rid_map[rel.rId] = new.part.relate_to(target, rel.reltype)
    for el in new._element.iter():
        for attr in (qn("r:embed"), qn("r:link"), qn("r:id"), qn("r:pict")):
            v = el.get(attr)
            if v in rid_map:
                el.set(attr, rid_map[v])
    # unique shape ids within the slide
    used: set[int] = set()
    for cnv in new._element.iter(qn("p:cNvPr")):
        try:
            sid = int(cnv.get("id", "0"))
        except ValueError:
            sid = 0
        if sid in used or sid <= 0:
            sid = max(used, default=1) + 1
            cnv.set("id", str(sid))
        used.add(sid)
    # position in the slide list
    sld_id_lst = prs.slides._sldIdLst
    ids = list(sld_id_lst)
    moved = ids[-1]
    sld_id_lst.remove(moved)
    target_index = (after if after is not None else slide_no)
    sld_id_lst.insert(min(target_index, len(ids) - 1), moved)
    prs.save(out)
    return {"out": out, "copied_slide": slide_no, "new_position": target_index + 1, "slides": len(Presentation(out).slides)}


def _copy_part(prs, part):
    """A byte-level copy of a part under a fresh partname, with its own relationships
    copied (chart -> embedded workbook, colors, style)."""
    from pptx.opc.package import Part

    partname = part.partname
    base = re.sub(r"\d+(\.\w+)$", r"\1", str(partname))
    ext = Path(str(partname)).suffix
    existing = {str(p.partname) for p in prs.part.package.iter_parts()}
    n = 1
    while True:
        candidate = f"{base[:-len(ext)]}{n}{ext}"
        if candidate not in existing:
            break
        n += 1
    new = Part(PackURI(candidate), part.content_type, prs.part.package, copy.deepcopy(part.blob))
    if hasattr(part, "_element"):
        new._blob = etree.tostring(part._element, xml_declaration=True, encoding="UTF-8", standalone=True)
    for rel in part.rels.values():
        if rel.is_external:
            new.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            # the chart's workbook, colours and style are its own: a shared workbook would
            # make an edit of one chart's data in PowerPoint rewrite the other's
            new.relate_to(_copy_part(prs, rel.target_part), rel.reltype)
    return new


# --- clean ----------------------------------------------------------------------------------------------


def clean(path: str, out: str) -> dict:
    """Rewrite the zip keeping only parts reachable from the package relationships plus
    [Content_Types].xml. python-pptx already drops unreachable parts on save; this handles
    packages edited by hand whose stale parts python-pptx would carry as unknown blobs."""
    prs = Presentation(path)
    reachable = {str(p.partname) for p in prs.part.package.iter_parts()}
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        kept = dropped = 0
        for info in zin.infolist():
            name = "/" + info.filename
            if info.filename == "[Content_Types].xml" or info.filename.endswith(".rels") or name in reachable:
                zout.writestr(info, zin.read(info.filename))
                kept += 1
            else:
                dropped += 1
    return {"out": out, "kept": kept, "dropped": dropped}


# --- validate ---------------------------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def undrawn_paragraphs(path: str, pdf: Path) -> list[str]:
    """Paragraph texts of each slide against pdftotext of the rendered page: a paragraph
    whose first twelve letters do not appear on its page did not draw."""
    out: list[str] = []
    prs = Presentation(path)
    for i, slide in enumerate(prs.slides, 1):
        try:
            page = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            return out
        haystack = _norm(page)
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                key = _norm("".join(r.text for r in para.runs))[:12]
                if len(key) >= 6 and key not in haystack:
                    out.append(f"slide {i}: paragraph {key!r}... in {shape.name!r} did not draw")
    return out


def _safe_xml(data: bytes) -> etree._Element:
    return etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, huge_tree=False))


def _edge_bytes(tc: etree._Element, side: str) -> bytes:
    """One cell border, canonicalised with its name erased: the two sides of an edge are
    lnB and lnT (or lnR and lnL) by construction, and everything else must match."""
    tc_pr = tc.find(qn("a:tcPr"))
    el = tc_pr.find(qn(side)) if tc_pr is not None else None
    if el is None:
        return b""
    edge = copy.deepcopy(el)
    edge.tag = qn("a:edge")
    return etree.tostring(edge, method="c14n")


def _draws(line: etree._Element) -> bool:
    """a:noFill is how a stroke says draw nothing; the emitter pairs it with w=0 on every
    table edge the guide leaves blank."""
    return line.find(qn("a:noFill")) is None


def _guide_floors(guide: dict | None) -> dict:
    """Legibility floors by where a run sits. A run's role is not in the file, so the
    floor for a slide run is the lowest family floor (a run below it is below every
    role's floor); table cells resolve to the table roles' family and chart parts to
    the chart family, whose roles the location fixes."""
    floors = (guide or {}).get("floors") or {}
    by_family: dict[str, float] = {}
    by_role: dict[str, float] = {}
    absolute = PRODUCT_SAFETY_FLOOR_PT
    for fam, f in floors.items():
        if not isinstance(f, dict):
            continue
        absolute = max(absolute, float(f.get("absolute_floor_pt") or 0.0))
        floor = max(float(f.get("floor_pt") or 0.0), float(f.get("absolute_floor_pt") or 0.0))
        if floor <= 0:
            continue
        by_family[fam] = floor
        for role in f.get("roles") or []:
            by_role[role] = floor
    any_floor = min(by_family.values()) if by_family else absolute
    table = min([by_role[r] for r in ("type.table_cell", "type.table_header") if r in by_role] or [any_floor])
    chart = min([by_role[r] for r in ("type.axis_label", "type.data_label") if r in by_role] or [by_family.get("chart", any_floor)])
    return {"slide": any_floor, "table": table, "chart": chart, "source": "guide floors" if by_family else f"no guide: {absolute}pt product safety floor (deckgen E45)"}


def _guide_rule_widths_emu(guide: dict | None) -> set[int]:
    """Every stroke width the guide itself declares: a rule below the floor that the
    guide asks for is the house's choice, reported and not failed."""
    widths: set[int] = set()
    if not guide:
        return widths

    def take(pt, emu) -> None:
        if emu:
            widths.add(int(emu))
        elif pt:
            widths.add(int(round(float(pt) * EMU_PER_PT)))

    tables = guide.get("tables") or {}
    for rule in (tables.get("edge_rules") or {}).values():
        if isinstance(rule, dict):
            take(rule.get("width_pt"), rule.get("width_emu"))
    if isinstance(tables.get("totals_rule"), dict):
        take(tables["totals_rule"].get("width_pt"), tables["totals_rule"].get("width_emu"))
    for item in list(guide.get("motifs") or []) + list(guide.get("chrome") or []):
        if isinstance(item, dict):
            take(item.get("line_width_pt"), item.get("line_width_emu"))
    for spec in (guide.get("charts") or {}).get("per_kind", {}).values():
        if isinstance(spec, dict):
            take(spec.get("gridline_width_pt"), None)
            take(spec.get("axis_line_width_pt"), None)
    return widths


def _check_strokes(part: str, root: etree._Element, guide_widths: set[int], problems: list[str], info: dict) -> None:
    for tag in LINE_TAGS:
        for line in root.iter(qn(tag)):
            info["strokes_checked"] += 1
            if not _draws(line):
                continue
            w = line.get("w")
            if w is None or int(w) >= RULE_WEIGHT_FLOOR_EMU:
                continue
            if int(w) in guide_widths:
                info["guide_rule_widths_below_floor"].append({"part": part, "tag": tag, "w_emu": int(w), "w_pt": round(int(w) / EMU_PER_PT, 2)})
                continue
            problems.append(f"{part}: {tag} w={w} EMU ({int(w) / EMU_PER_PT:.2f}pt) is below the 6350 EMU (0.5pt) floor: at 0.25pt PowerPoint inks 0.48px where LibreOffice inks 1.27px (E38 class 5)")


def _check_sizes(part: str, nodes, floor_pt: float, where: str, problems: list[str], info: dict) -> None:
    for node in nodes:
        sz = node.get("sz")
        if sz is None:
            continue
        info["runs_checked"] += 1
        if int(sz) < int(round(floor_pt * 100)):
            problems.append(f"{part}: run sz={sz} ({int(sz) / 100:g}pt) is below the {where} floor {floor_pt:g}pt")


def emit_checks(z: zipfile.ZipFile, names: set[str], slide_parts: list[str], guide: dict | None) -> tuple[list[str], dict]:
    """The emitter read-back (module docstring): what the saved bytes carry that the two
    renderers draw differently, read off the package alone."""
    problems: list[str] = []
    info: dict = {"tables": 0, "shared_edges_checked": 0, "strokes_checked": 0, "chart_parts": 0, "runs_checked": 0,
                  "generated_slides": 0, "guide_rule_widths_below_floor": [], "floors": _guide_floors(guide)}
    guide_widths = _guide_rule_widths_emu(guide)
    floors = info["floors"]
    for sp in slide_parts:
        if sp not in names:
            continue
        root = _safe_xml(z.read(sp))
        rels_name = sp.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
        rels = _safe_xml(z.read(rels_name)) if rels_name in names else None
        chart_parts: list[str] = []
        if rels is not None:
            for rel in rels:
                kind = (rel.get("Type") or "").rsplit("/", 1)[-1]
                target = "ppt/" + (rel.get("Target") or "").replace("../", "")
                if kind == "chart" and target in names:
                    chart_parts.append(target)
                if kind == "tags" and target in names:
                    tag_root = _safe_xml(z.read(target))
                    if any(t.get("name") == ORIGIN_TAG_NAME for t in tag_root.iter(qn("p:tag"))):
                        info["generated_slides"] += 1
        # shared table edges, byte for byte on both declaring cells (E38 class 4)
        for tbl in root.iter(qn("a:tbl")):
            info["tables"] += 1
            frame = next(tbl.iterancestors(qn("p:graphicFrame")), None)
            cnv = frame.find(".//" + qn("p:cNvPr")) if frame is not None else None
            name = cnv.get("name") if cnv is not None else f"table#{info['tables']}"
            grid = [row.findall(qn("a:tc")) for row in tbl.findall(qn("a:tr"))]
            mismatches: list[str] = []
            for ri, row in enumerate(grid):
                for ci, cell in enumerate(row):
                    if ri + 1 < len(grid) and ci < len(grid[ri + 1]):
                        info["shared_edges_checked"] += 1
                        if _edge_bytes(cell, "a:lnB") != _edge_bytes(grid[ri + 1][ci], "a:lnT"):
                            mismatches.append(f"row {ri} lnB vs row {ri + 1} lnT at column {ci}")
                    if ci + 1 < len(row):
                        info["shared_edges_checked"] += 1
                        if _edge_bytes(cell, "a:lnR") != _edge_bytes(row[ci + 1], "a:lnL"):
                            mismatches.append(f"column {ci} lnR vs column {ci + 1} lnL at row {ri}")
            if mismatches:
                problems.append(f"{sp}: table {name!r} declares {len(mismatches)} shared edge(s) differently on its two cells ({mismatches[0]}{'; ...' if len(mismatches) > 1 else ''}): "
                                "PowerPoint keeps the first-declared side and writes it back on save, LibreOffice draws the heavier one (E38 class 4)")
        _check_strokes(sp, root, guide_widths, problems, info)
        for grad in root.iter(qn("a:gradFill")):
            problems.append(f"{sp}: a:gradFill: the two renderers put a gradient's midpoint 20 points apart and a radial's dark area a factor of 2.7 apart (E38 classes 6-7)")
            break
        # run sizes against the floor of where the run sits
        # membership by ancestry: lxml recreates element proxies, so identity sets drop runs
        runs = list(root.iter(qn("a:rPr")))
        in_table = [r for r in runs if any(a.tag == qn("a:tbl") for a in r.iterancestors())]
        _check_sizes(sp, in_table, floors["table"], "table family", problems, info)
        _check_sizes(sp, [r for r in runs if not any(a.tag == qn("a:tbl") for a in r.iterancestors())], floors["slide"], "lowest family", problems, info)
        # a literal number in the slide-number placeholder instead of the field
        for sp_el in root.iter(qn("p:sp")):
            ph = sp_el.find(f"{qn('p:nvSpPr')}/{qn('p:nvPr')}/{qn('p:ph')}")
            if ph is None or ph.get("type") != "sldNum":
                continue
            for run in sp_el.iter(qn("a:r")):
                text = "".join(t.text or "" for t in run.iter(qn("a:t")))
                if re.fullmatch(r"\s*\d+\s*", text):
                    problems.append(f"{sp}: slide-number placeholder carries the literal {text.strip()!r} instead of a slidenum field: the number is wrong after any reorder")
        for cp in chart_parts:
            croot = _safe_xml(z.read(cp))
            info["chart_parts"] += 1
            area = croot.find(".//" + qn("c:plotArea"))
            groups = [g for g in area if etree.QName(g).localname in VARY_COLORS_GROUPS] if area is not None else []
            for g in groups:
                if g.find(qn("c:varyColors")) is None:
                    problems.append(f"{cp}: c:{etree.QName(g).localname} writes no c:varyColors: the element defaults to true and PowerPoint paints one series in five theme colours where LibreOffice paints one (E38 class 10)")
            _check_strokes(cp, croot, guide_widths, problems, info)
            for grad in croot.iter(qn("a:gradFill")):
                problems.append(f"{cp}: a:gradFill in a chart part (E38 classes 6-7)")
                break
            _check_sizes(cp, croot.iter(), floors["chart"], "chart family", problems, info)
    return problems, info


def validate(path: str, render: bool, emit: bool = False, guide: dict | None = None) -> dict:
    problems: list[str] = []
    info: dict = {"file": path}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "[Content_Types].xml" not in names:
            problems.append("missing [Content_Types].xml")
        else:
            ct = etree.fromstring(z.read("[Content_Types].xml"))
            defaults = {d.get("Extension").lower() for d in ct if d.tag.endswith("Default")}
            overrides = {o.get("PartName") for o in ct if o.tag.endswith("Override")}
            for n in names:
                if n.endswith("/") or n == "[Content_Types].xml":
                    continue
                ext = n.rsplit(".", 1)[-1].lower() if "." in n else ""
                if "/" + n not in overrides and ext not in defaults:
                    problems.append(f"part without content type: {n}")
        # every relationship target must exist
        for n in names:
            if not n.endswith(".rels"):
                continue
            folder = n.rsplit("/_rels/", 1)[0] if "/_rels/" in n else ""
            rels = etree.fromstring(z.read(n))
            for rel in rels:
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target") or ""
                if target.startswith("/"):
                    resolved = target[1:]
                else:
                    parts = (folder.split("/") if folder else [])
                    for piece in target.split("/"):
                        if piece == "..":
                            if parts:
                                parts.pop()
                        elif piece and piece != ".":
                            parts.append(piece)
                    resolved = "/".join(parts)
                if resolved not in names:
                    problems.append(f"{n}: {rel.get('Id')} -> {target} missing")
        # every slide needs its layout and every layout its master, or the text, layouts and
        # duplicate commands crash on the same file that validated
        for n in names:
            if n.startswith("ppt/slides/slide") and n.endswith(".xml"):
                rels_name = n.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
                kinds = []
                if rels_name in names:
                    kinds = [r.get("Type", "").rsplit("/", 1)[-1] for r in etree.fromstring(z.read(rels_name))]
                if kinds.count("slideLayout") != 1:
                    problems.append(f"{n}: {kinds.count('slideLayout')} slideLayout relationships (needs exactly one)")
            if n.startswith("ppt/slideLayouts/slideLayout") and n.endswith(".xml"):
                rels_name = n.replace("ppt/slideLayouts/", "ppt/slideLayouts/_rels/") + ".rels"
                kinds = [r.get("Type", "").rsplit("/", 1)[-1] for r in etree.fromstring(z.read(rels_name))] if rels_name in names else []
                if kinds.count("slideMaster") != 1:
                    problems.append(f"{n}: {kinds.count('slideMaster')} slideMaster relationships (needs exactly one)")
        # slide list consistency and per-slide shape ids
        pres = etree.fromstring(z.read("ppt/presentation.xml"))
        pres_rels = etree.fromstring(z.read("ppt/_rels/presentation.xml.rels"))
        rid_to_target = {r.get("Id"): r.get("Target") for r in pres_rels}
        seen_ids: set[str] = set()
        slide_parts = []
        for sld in pres.iter(qn("p:sldId")):
            sid = sld.get("id")
            if sid in seen_ids:
                problems.append(f"duplicate slide id {sid}")
            seen_ids.add(sid)
            rid = sld.get(qn("r:id"))
            if rid not in rid_to_target:
                problems.append(f"sldId {sid} has no relationship {rid}")
            else:
                slide_parts.append("ppt/" + rid_to_target[rid].lstrip("/").removeprefix("ppt/"))
        info["slides"] = len(slide_parts)
        for sp in slide_parts:
            if sp not in names:
                problems.append(f"slide part missing: {sp}")
                continue
            root = etree.fromstring(z.read(sp))
            ids = [c.get("id") for c in root.iter(qn("p:cNvPr"))]
            dup = {i for i in ids if ids.count(i) > 1}
            if dup:
                problems.append(f"{sp}: duplicate shape ids {sorted(dup)}")
            for tag in ("p:sp", "p:pic", "p:graphicFrame", "p:cxnSp"):
                for el in root.iter(qn(tag)):
                    xfrm = el.find(".//" + qn("a:xfrm"))
                    if xfrm is not None:
                        ext = xfrm.find(qn("a:ext"))
                        off = xfrm.find(qn("a:off"))
                        if ext is not None and (int(ext.get("cx", "0")) < 0 or int(ext.get("cy", "0")) < 0):
                            problems.append(f"{sp}: negative extent on shape {el.find('.//' + qn('p:cNvPr')).get('id') if el.find('.//' + qn('p:cNvPr')) is not None else '?'}")
                        if off is not None:
                            sz = pres.find(qn("p:sldSz"))
                            if sz is not None and ext is not None:
                                w, h = int(sz.get("cx")), int(sz.get("cy"))
                                # the page area the shape covers: off and ext are the box before
                                # xfrm/@rot turns it about its centre (a label up the page edge
                                # declares a box that runs off the slide and draws inside it)
                                x, y, cx, cy = visual_extent((int(off.get("x", "0")), int(off.get("y", "0")), int(ext.get("cx", "0")), int(ext.get("cy", "0"))),
                                                             int(xfrm.get("rot") or 0))
                                # a title box a tenth of an inch above the slide is how three of five
                                # real references are built; it is a warning, not a broken package
                                tol = 91440 if el.find(qn("p:txBody")) is not None else 9525
                                if x + cx > w + tol or y + cy > h + tol or x < -tol or y < -tol:
                                    problems.append(f"{sp}: shape {el.find('.//' + qn('p:cNvPr')).get('id') if el.find('.//' + qn('p:cNvPr')) is not None else '?'} extends past the slide")
            for gf in root.iter(qn("p:graphicFrame")):
                for ch in gf.iter(qn("c:chart")):
                    pass
        # charts parse
        for n in names:
            if n.startswith("ppt/charts/chart") and n.endswith(".xml"):
                try:
                    croot = etree.fromstring(z.read(n))
                    if croot.find(".//" + qn("c:plotArea")) is None:
                        problems.append(f"{n}: no plotArea")
                except etree.XMLSyntaxError as exc:
                    problems.append(f"{n}: {exc}")
        if emit:
            emit_problems, info["emit"] = emit_checks(z, names, slide_parts, guide)
            problems.extend(emit_problems)
    try:
        Presentation(path)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"python-pptx cannot open: {exc}")
    if render:
        with tempfile.TemporaryDirectory(prefix="validate-") as tmp:
            profile = Path(tmp) / "profile"
            cmd = ["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--norestore", "--nolockcheck",
                   "--convert-to", "pdf", "--outdir", tmp, path]
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                pdf = Path(tmp) / (Path(path).stem + ".pdf")
                if not pdf.exists():
                    problems.append("LibreOffice produced no PDF")
                else:
                    pages = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=60).stdout
                    m = re.search(r"^Pages:\s+(\d+)", pages, re.M)
                    info["rendered_pages"] = int(m.group(1)) if m else None
                    if m and info.get("slides") and int(m.group(1)) != info["slides"]:
                        problems.append(f"rendered {m.group(1)} pages for {info['slides']} slides (hidden slides are not exported)")
                    # every paragraph the file carries must draw: a schema-invalid value once
                    # blanked sixteen bullets on a page that validated and judged clean
                    problems.extend(undrawn_paragraphs(path, pdf))
            except (OSError, subprocess.TimeoutExpired) as exc:
                problems.append(f"render failed: {exc}")
    info["problems"] = problems
    info["ok"] = not problems
    return info


def blank(out: str, width_emu: int, height_emu: int) -> dict:
    """A slide-free package at the given page size with python-pptx's stock master, for a
    reference that has no master to reuse (a PDF). The guide then supplies everything the
    master would have: background, chrome, fonts; emit_pptx.py --chrome draw paints them."""
    prs = Presentation()
    prs.slide_width = Emu(width_emu)
    prs.slide_height = Emu(height_emu)
    prs.save(out)
    return {"out": out, "width_emu": width_emu, "height_emu": height_emu, "layouts": [lay.name for lay in prs.slide_layouts]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("blank"); s.add_argument("-o", "--out", required=True); s.add_argument("--width-emu", type=int, required=True); s.add_argument("--height-emu", type=int, required=True)
    s = sub.add_parser("text"); s.add_argument("deck"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("layouts"); s.add_argument("deck")
    s = sub.add_parser("template"); s.add_argument("deck"); s.add_argument("-o", "--out", required=True); s.add_argument("--keep", default="")
    s = sub.add_parser("duplicate"); s.add_argument("deck"); s.add_argument("--slide", type=int, required=True); s.add_argument("-o", "--out", required=True); s.add_argument("--after", type=int, default=None)
    s = sub.add_parser("delete"); s.add_argument("deck"); s.add_argument("--slides", required=True); s.add_argument("-o", "--out", required=True)
    s = sub.add_parser("clean"); s.add_argument("deck"); s.add_argument("-o", "--out", required=True)
    s = sub.add_parser("validate"); s.add_argument("deck"); s.add_argument("--render", action="store_true")
    s.add_argument("--emit", action="store_true", help="the emitter read-back: shared table edges, stroke floor, gradients, varyColors, size floors, literal page numbers")
    s.add_argument("--guide", default=None, help="style guide for the floors and the rule widths the house itself declares (with --emit)")
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out")
    if args.cmd == "validate" and args.guide and not args.emit:
        ap.error("--guide needs --emit")
    if args.cmd == "blank":
        print(json.dumps(blank(args.out, args.width_emu, args.height_emu))); return 0
    if args.cmd in ("text", "layouts", "template", "duplicate", "delete", "clean", "validate"):
        sniff(args.deck)
    if args.cmd == "template":
        check_slide_numbers(args.deck, [int(k) for k in args.keep.split(",") if k.strip()])
    if args.cmd == "duplicate":
        check_slide_numbers(args.deck, [args.slide] + ([args.after] if args.after is not None else []))
    if args.cmd == "delete":
        check_slide_numbers(args.deck, [int(k) for k in args.slides.split(",") if k.strip()])
    if args.cmd == "text":
        entries = slide_text(args.deck)
        print(json.dumps(entries, indent=1)) if args.json else print_text(entries)
        return 0
    if args.cmd == "layouts":
        print(json.dumps(layouts(args.deck), indent=1)); return 0
    if args.cmd == "template":
        keep = [int(k) for k in args.keep.split(",") if k.strip()]
        print(json.dumps(template(args.deck, args.out, keep))); return 0
    if args.cmd == "duplicate":
        print(json.dumps(duplicate(args.deck, args.out, args.slide, args.after))); return 0
    if args.cmd == "delete":
        print(json.dumps(delete(args.deck, args.out, [int(k) for k in args.slides.split(",") if k.strip()]))); return 0
    if args.cmd == "clean":
        print(json.dumps(clean(args.deck, args.out))); return 0
    if args.cmd == "validate":
        guide = json.loads(Path(args.guide).read_text()) if args.guide else None
        result = validate(args.deck, args.render, emit=args.emit, guide=guide)
        print(json.dumps(result, indent=1))
        return 0 if result["ok"] else 1
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
