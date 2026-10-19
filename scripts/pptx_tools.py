#!/usr/bin/env python3
"""Package-level tools for .pptx files: read, template, duplicate, delete, clean, validate.

    pptx_tools.py text deck.pptx                      # text per slide, tables as rows (JSON with --json)
    pptx_tools.py layouts deck.pptx                   # masters, layouts, placeholders with boxes, usage counts
    pptx_tools.py template ref.pptx -o tpl.pptx       # the reference with every slide removed: masters, layouts,
                                                      # theme and chrome intact (deckgen E18: master reuse)
    pptx_tools.py template ref.pptx -o tpl.pptx --keep 3,7   # keep those slides (page reuse)
    pptx_tools.py duplicate deck.pptx --slide 3 -o out.pptx [--after 5]
    pptx_tools.py delete deck.pptx --slides 2,5 -o out.pptx
    pptx_tools.py clean deck.pptx -o out.pptx         # drop parts nothing references
    pptx_tools.py validate deck.pptx [--render]       # package checks, then a LibreOffice round trip with --render

Original code; python-pptx for the package graph, lxml for the XML. Nothing here changes
a slide's content: content edits go through the layout solver and the emitter, or through
python-pptx in a script the model writes.
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


# --- text ---------------------------------------------------------------------------------------


def slide_text(path: str) -> list[dict]:
    prs = Presentation(path)
    out = []
    for i, slide in enumerate(prs.slides, 1):
        entry: dict = {"slide": i, "layout": slide.slide_layout.name, "title": None, "blocks": [], "tables": [], "notes": None}
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                text = "\n".join(p.text for p in shape.text_frame.paragraphs)
                if shape.is_placeholder and shape.placeholder_format.type is not None and "TITLE" in str(shape.placeholder_format.type) and entry["title"] is None:
                    entry["title"] = text
                else:
                    entry["blocks"].append({"name": shape.name, "text": text})
            if shape.has_table:
                rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
                entry["tables"].append({"name": shape.name, "rows": rows})
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            entry["notes"] = notes or None
        out.append(entry)
    return out


def print_text(entries: list[dict]) -> None:
    for e in entries:
        print(f"--- slide {e['slide']} ({e['layout']}) ---")
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
        if rel.reltype == RT.CHART:
            # a chart part must be copied, or both slides edit one chart
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
    new = Part(PackURI(candidate), part.content_type, copy.deepcopy(part.blob) if isinstance(part.blob, bytes) else part.blob, prs.part.package)
    if hasattr(part, "_element"):
        new._blob = etree.tostring(part._element, xml_declaration=True, encoding="UTF-8", standalone=True)
    for rel in part.rels.values():
        if rel.is_external:
            new.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            new.relate_to(rel.target_part, rel.reltype)
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


def validate(path: str, render: bool) -> dict:
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
                                x, y = int(off.get("x", "0")), int(off.get("y", "0"))
                                if x + int(ext.get("cx", "0")) > w + 9525 or y + int(ext.get("cy", "0")) > h + 9525 or x < -9525 or y < -9525:
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
    args = ap.parse_args(argv)
    if args.cmd == "blank":
        print(json.dumps(blank(args.out, args.width_emu, args.height_emu))); return 0
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
        result = validate(args.deck, args.render)
        print(json.dumps(result, indent=1))
        return 0 if result["ok"] else 1
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
