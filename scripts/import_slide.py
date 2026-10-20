#!/usr/bin/env python3
"""Import a reference slide into a page spec of roles, for the round trip.

    python3 scripts/import_slide.py ref.pptx --slide 3 --guide guide.json -o page.deck.json
    python3 scripts/build_deck.py page.deck.json --guide guide.json --template tpl.pptx -o rt.pptx --reference ref.pptx

The round trip is the one acceptance test the extractor cannot game: a slide the house
made, read into roles and weights (never its coordinates), solved with measured fit,
emitted on the reference's own master, must land near the house when the judge compares
it with the reference. It proves the extractor, the solver and the emitter agree. It is
also the seed for new pages: a spec imported from the exemplar of a composition family
starts inside the house's own bands and columns.

What survives the import: the title, every text shape's paragraphs with their bullet
levels, bold runs, fills and inverse ink, the row and column arrangement (shapes that
overlap vertically share a row, weights follow widths) and pictures (as sized images
without their bytes, so the render shows an empty frame). What does not: charts and
tables are left as notes in the spec for the agent to rebuild from data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ooxml import EMU_PER_PT, Shape, delta_e, fingerprint_deck  # noqa: E402

EMU_PER_INCH = 914400
CHROME_PH = {"sldNum", "ftr", "dt"}


def role_table(guide: dict) -> list[tuple[str, float, int]]:
    out = []
    for name, spec in guide["typography"]["roles"].items():
        if spec.get("size_pt"):
            out.append((name, float(spec["size_pt"]), int(spec.get("weight") or 400)))
    return out


PREFERENCE = ["type.body", "type.h2", "type.h1", "type.emphasis", "type.caption", "type.footnote", "type.source_line",
              "type.kicker", "type.table_cell", "type.table_header", "type.axis_label", "type.data_label", "type.title", "type.subtitle"]


def bind_role(size: float, bold: bool, is_title: bool, roles: list[tuple[str, float, int]]) -> str:
    if is_title and any(r[0] == "type.title" for r in roles):
        return "type.title"
    weight = 700 if bold else 400
    best = None
    for name, rsize, rweight in roles:
        if name == "type.title":
            continue
        cost = abs(rsize - size) * 10 + (0 if rweight == weight else 3) + (PREFERENCE.index(name) if name in PREFERENCE else 20) * 0.01
        if best is None or cost < best[0]:
            best = (cost, name)
    return best[1] if best else "type.body"


def colour_roles(guide: dict) -> dict[str, str]:
    out = {}
    for name, spec in guide.get("color", {}).get("roles", {}).items():
        if spec.get("hex"):
            out[name] = spec["hex"].upper()
    for name, spec in guide.get("extra_roles", {}).items():
        if spec.get("hex"):
            out[name] = spec["hex"].upper()
    return out


def nearest_colour(hex_value: str, roles: dict[str, str], prefixes: tuple[str, ...] = ()) -> tuple[str | None, float]:
    """Nearest role by CIE76; `prefixes` keeps text ink away from surface roles of the same
    hex (white text on a blue box is ink_inverse, not surface)."""
    best = None
    for name, h in roles.items():
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        d = delta_e(hex_value.upper(), h)
        if best is None or d < best[1]:
            best = (name, d)
    return best if best else (None, 999.0)


def overlap_v(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    top = max(a[1], b[1])
    bottom = min(a[1] + a[3], b[1] + b[3])
    return max(0, bottom - top) / max(1, min(a[3], b[3]))


def rows_of(shapes: list[Shape]) -> list[list[Shape]]:
    """Shapes overlapping vertically by half their smaller height share a row."""
    rows: list[list[Shape]] = []
    for sh in sorted(shapes, key=lambda s: (s.box[1], s.box[0])):  # type: ignore[index]
        for row in rows:
            if any(overlap_v(sh.box, o.box) >= 0.5 for o in row):  # type: ignore[arg-type]
                row.append(sh)
                break
        else:
            rows.append([sh])
    for row in rows:
        row.sort(key=lambda s: s.box[0])  # type: ignore[index]
    return rows


def text_element(sh: Shape, ident: str, roles: list[tuple[str, float, int]], colours: dict[str, str], styling: dict, notes: list[str]) -> dict:
    paragraphs = []
    para_style: dict[str, dict] = {}
    inverse = None
    for i, para in enumerate(sh.paragraphs or []):
        runs = [r for r in para["runs"] if r["text"].strip()]
        if not runs:
            continue
        lead = runs[0]
        all_bold = all(r["bold"] for r in runs)
        role = bind_role(lead["size_pt"], all_bold, sh.ph_type == "title", roles)
        text = "".join(r["text"] for r in runs)
        p = {"role": role, "text": text}
        if para["bullet"].startswith("char") or para["bullet"] == "auto":
            p["bullet_level"] = int(para["level"])
        paragraphs.append(p)
        if not all_bold and any(r["bold"] for r in runs):
            para_style[str(len(paragraphs) - 1)] = {"runs": [{"text": r["text"], **({"emphasis": True} if r["bold"] else {})} for r in runs]}
        if para.get("align") in ("ctr", "r"):
            para_style.setdefault(str(len(paragraphs) - 1), {})["align"] = {"ctr": "center", "r": "right"}[para["align"]]
        if lead.get("color"):
            name, d = nearest_colour(lead["color"], colours, ("color.ink", "color.accent", "color.rule"))
            if name and d < 12 and name not in ("color.ink",):
                para_style.setdefault(str(len(paragraphs) - 1), {})["ink_role"] = name
                if name == "color.ink_inverse":
                    inverse = name
    el = {"type": "element", "id": ident, "kind": "text", "paragraphs": paragraphs}
    st: dict = {}
    if sh.text_anchor in ("ctr", "b"):
        st["anchor"] = "m" if sh.text_anchor == "ctr" else "b"
    if sh.fill:
        name, d = nearest_colour(sh.fill, colours, ("color.surface", "color.accent", "color.rule"))
        if name and d < 12:
            st["fill_role"] = name
            st["pad_role"] = "space.xs"
        else:
            notes.append(f"{ident}: fill {sh.fill} has no colour role within CIE76 12 (nearest {name} at {d:.1f}); left unfilled")
    if para_style:
        st["paragraphs"] = para_style
    if st:
        styling[ident] = st
    return el


def import_slide(path: str, index: int, guide: dict) -> dict:
    slides = fingerprint_deck(path)
    s = slides[index]
    roles = role_table(guide)
    colours = colour_roles(guide)
    notes: list[str] = []
    styling: dict = {}
    content = [sh for sh in s.shapes if sh.box and sh.ph_type not in CHROME_PH and sh.kind not in ("line",) and (sh.text_chars or sh.kind in ("picture", "table", "chart"))]
    title = next((sh for sh in content if sh.ph_type == "title"), None)
    body = [sh for sh in content if sh is not title]
    children: list[dict] = []
    if title is not None:
        children.append(text_element(title, "title", roles, colours, styling, notes))
    n = 0
    for row in rows_of(body):
        elems = []
        for sh in row:
            n += 1
            ident = f"e{n}"
            if sh.kind == "picture":
                elems.append({"type": "element", "id": ident, "kind": "image", "size": {"width_emu": sh.box[2], "height_emu": sh.box[3]}})  # type: ignore[index]
                notes.append(f"{ident}: picture {sh.box[2] / EMU_PER_INCH:.2f} x {sh.box[3] / EMU_PER_INCH:.2f} in, bytes not imported")  # type: ignore[index]
            elif sh.kind in ("table", "chart"):
                elems.append({"type": "element", "id": ident, "kind": "text", "paragraphs": [{"role": "type.body", "text": f"[{sh.kind} to rebuild from data]"}]})
                notes.append(f"{ident}: {sh.kind} left as a placeholder; rebuild it from the dataset")
            else:
                elems.append(text_element(sh, ident, roles, colours, styling, notes))
        if len(elems) == 1:
            children.append(elems[0])
        else:
            total = sum(sh.box[2] for sh in row)  # type: ignore[index]
            for el, sh in zip(elems, row):
                el["weight"] = round(sh.box[2] / total, 4)  # type: ignore[index]
            # a stretched row is flexible, so the body's rows share the content height by
            # weight instead of packing at the top (the reference's label boxes are taller
            # than their text and sit at one pitch down the page)
            children.append({"type": "region", "id": f"row{len(children)}", "layout": {"kind": "flex", "direction": "row", "gap_role": "space.gutter",
                                                                                          "pad_role": None, "align": "stretch", "justify": "start"},
                             "children": elems})
    # the house fills its page: the body rows share the content height (weights), as the
    # reference's rows do (keybank slide 3: seven rows at one pitch down to the footer rule)
    title_el = children[0] if children and children[0].get("id") == "title" else None
    body_children = children[1:] if title_el else children
    for row in body_children:
        if row.get("type") == "region" or row.get("kind") == "text":
            row["weight"] = 1.0
    body = {"type": "region", "id": "body", "weight": 1.0, "layout": {"kind": "flex", "direction": "column", "gap_role": "space.sm",
                                                                     "pad_role": None, "align": "stretch", "justify": "start"},
            "children": body_children}
    root = {"type": "region", "id": "root", "layout": {"kind": "flex", "direction": "column", "gap_role": "space.sm", "pad_role": "space.margin",
                                                        "align": "stretch", "justify": "start"},
            "children": ([title_el] if title_el else []) + [body]}
    slide = {"id": f"import-{index + 1}", "layout": s.layout_name or "Title and Content",
             "notes": f"round trip of {Path(path).name} slide {index + 1}: roles and weights only, no coordinates",
             "spec": {"root": root, "splittable_groups": []}, "styling": styling, "import_notes": notes}
    return {"slides": [slide]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference")
    ap.add_argument("--slide", type=int, required=True, help="1-based slide number")
    ap.add_argument("--guide", required=True, help="the completed guide (roles and colours to bind to)")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    guide = json.loads(Path(args.guide).read_text())
    deck = import_slide(args.reference, args.slide - 1, guide)
    Path(args.out).write_text(json.dumps(deck, indent=1))
    sl = deck["slides"][0]
    print(json.dumps({"out": args.out, "layout": sl["layout"], "elements": sum(1 for _ in json.dumps(sl["spec"]).split('"kind":')) - 1,
                      "styled": sorted(sl["styling"]), "notes": sl["import_notes"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
