#!/usr/bin/env python3
"""Build a deck: solve every slide with measured fit, emit on the reference package,
validate, render and judge. The one command the model runs after writing a deck spec.

    build_deck.py deck.json --guide guide.json --template tpl.pptx -o out.pptx
                  [--reference ref.pptx] [--others a.pptx b.pdf] [--renders DIR] [--no-render]

deck.json:
{
 "slides": [
  {"id": "s1", "layout": "Title and Content", "notes": "...",
   "spec": { "page": {...}, "root": {...tree...}, "splittable_groups": [...] },   # layout.py's spec
   "styling": {"takeaway": {"fill_role": "color.accent1", "pad_role": "space.sm", "anchor": "m"},
               "left": {"paragraphs": {"1": {"runs": [{"text": "Cost synergies of "}, {"text": "40%", "emphasis": true}]}}}},
   "charts": {"chart": {"chart_kind": "column", "categories": [...], "series": [...], "number_format": "$0.00", "data_labels": true, "legend": "b"}},
   "images": {"logo": {"path": "logo.png"}},
   "rules": {"rule1": {"line_role": "color.rule"}},
   "rects": {"band": {"fill_role": "color.accent2", "prst": "rect"}}
  }
 ]
}
`spec.page` may omit `reserved_zones`: the guide's chrome (footer, page number, logo,
rules, bands on the layout or master) is reserved automatically so content never
collides with the page furniture. Element kinds in the tree: text, table, image,
chart, rule; a `rect` is a text element with a fill (styling) or an image/rule.

The report (stdout and <out>.build.json) carries, per slide: fit or unfittable, the
scale chosen, lines per text element, every violation, the fitting row prefix of each
table when a split is needed, and after rendering the judge's distance to the reference
and to every other house given. An unfittable slide is still emitted from its last
attempt and marked, so the render shows what did not fit; nothing is dropped silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L  # noqa: E402
from emit_pptx import emit as emit_slides  # noqa: E402

EMU_PER_INCH = 914400


def chrome_zones(guide: dict) -> list[dict]:
    """Reserved zones from the guide's chrome. Furniture anchored to the bottom edge
    reserves everything below it (the reference's content never runs under its footer
    rule); a top-anchored rule stays a thin boundary, because the title band sits above
    it and the solver must be free to place the title there."""
    zones = []
    n = max(1, guide.get("reference", {}).get("slides", 1))
    page_h = guide["reference"]["page"]["height_emu"]
    page_w = guide["reference"]["page"]["width_emu"]
    for ch in guide.get("chrome", []):
        if ch.get("slides_present", 0) < 0.5 * n:
            continue
        if ch["kind"] not in ("footer", "page_number", "date", "logo", "rule", "band", "label"):
            continue
        x, y, w, h = ch["box_in"]
        left, top, width, height = int(x * EMU_PER_INCH), int(y * EMU_PER_INCH), int(w * EMU_PER_INCH), int(h * EMU_PER_INCH)
        if ch.get("anchor") == "slide_bottom":
            # the reference's content stops a spacing step above its footer rule, never on it:
            # the zone grows upward by the smallest spacing step so a source line keeps that air
            clearance = (guide.get("spacing", {}).get("steps", {}).get("space.xs") or {}).get("emu") or 0
            top = max(0, top - int(clearance))
            left, width, height = 0, page_w, page_h - top
        zones.append({"left": left, "top": top, "width": width, "height": height, "source": f"{ch['chrome_id']}:{ch['kind']}"})
    return zones


def title_band_emu(guide: dict) -> int | None:
    """Height of the band above the top rule, measured from the reference's own top
    margin: the title must fit there, as every reference title does."""
    n = max(1, guide.get("reference", {}).get("slides", 1))
    rules = [ch for ch in guide.get("chrome", []) if ch["kind"] == "rule" and ch.get("anchor") == "slide_top" and ch.get("slides_present", 0) >= 0.5 * n]
    if not rules:
        return None
    rule_top = min(ch["box_in"][1] for ch in rules) * EMU_PER_INCH
    top_margin = (guide.get("spacing", {}).get("margins", {}).get("top") or {}).get("emu")
    if top_margin is None or rule_top <= top_margin:
        return None
    return int(rule_top - top_margin)


PRESENTATION_KEYS = ("fill_role", "line_role", "pad_role", "prst", "line_width_emu", "anchor", "ink_role", "dash", "_spacer")


def mark_measured_weights(node: dict, slide: dict) -> None:
    """The emitter bolds emphasis runs and totals rows; the solver must measure them bold."""
    styling = slide.get("styling", {})
    if node.get("type") == "region":
        for c in node.get("children", []):
            mark_measured_weights(c, slide)
        return
    st = styling.get(node.get("id"), {})
    if node.get("kind") == "text":
        for i, p in enumerate(node.get("paragraphs", [])):
            ps = (st.get("paragraphs") or {}).get(str(i), {})
            if any(r.get("emphasis") for r in ps.get("runs") or []):
                p["emphasis"] = True
    elif node.get("kind") == "table":
        if st.get("totals_last_row") or node.get("totals_last_row"):
            node.setdefault("table", {})["totals_last_row"] = True
        if st.get("emphasis_rows"):
            node.setdefault("table", {})["emphasis_rows"] = list(st["emphasis_rows"])


def normalise(node: dict, slide: dict) -> dict:
    """Move presentation keys off tree nodes into the slide's styling tables (the solver
    reads geometry and roles only), turn `rect` into a sized `image` carrying its fill, and
    mark spacers so the emitter skips them."""
    node = dict(node)
    styling = slide.setdefault("styling", {})
    if node.get("type") == "region":
        st = {k: node.pop(k) for k in list(node) if k in PRESENTATION_KEYS}
        if st:
            styling.setdefault(node["id"], {}).update(st)
        node["children"] = [normalise(c, slide) for c in node.get("children", [])]
        return node
    if node.get("type") == "component":
        return node
    st = {k: node.pop(k) for k in list(node) if k in PRESENTATION_KEYS}
    if node.get("kind") == "rect":
        node["kind"] = "image"
        slide.setdefault("rects", {})[node["id"]] = {k: v for k, v in st.items() if k in ("fill_role", "line_role", "prst", "line_width_emu", "dash")}
        st = {k: v for k, v in st.items() if k not in ("fill_role", "line_role", "prst", "line_width_emu", "dash")}
    if st.get("_spacer"):
        # a spacer is a width device: one EMU tall, so the row it sits in takes its height
        # from the real children instead of turning flexible
        node["kind"] = "image"
        node.setdefault("size", {"width_emu": None, "height_emu": 1})
        slide.setdefault("spacers", set()).add(node["id"])
        st.pop("_spacer")
    if st:
        styling.setdefault(node["id"], {}).update(st)
    return node


def density_of(elements: list[dict], resolved: dict, guide: dict, spec_raw: dict) -> dict:
    """Words, elements and covered area of the page against the reference's own bands
    (10th to 90th percentile): below the band is sparse for this house, above it denser
    than the house ever goes. The build reports it because a page that fits can still end
    half-way down the canvas, and nothing else here notices."""
    words = 0
    for el in elements:
        if el.get("kind") == "text":
            for p in el.get("paragraphs", []):
                words += sum(len(r.get("text", "").split()) for r in p.get("runs", []))
        elif el.get("kind") == "table":
            words += sum(len(str(c).split()) for row in el.get("rows", []) for c in row) + sum(len(c.get("label", "").split()) for c in el.get("columns", []))
    n_elements = sum(1 for el in elements if el.get("kind") not in ("rule",) and not el.get("_spacer"))
    page = spec_raw.get("page", {})
    page_area = max(1, page.get("width_emu", 1) * page.get("height_emu", 1))
    covered = sum(el["box"][2] * el["box"][3] for el in elements if el.get("box")) / page_area
    bands = guide.get("density_bands", {})
    out = {"words": words, "elements": n_elements, "covered_area_fraction": round(covered, 3)}
    for key, value in (("words_per_slide", words), ("elements_per_slide", n_elements), ("content_area_fraction", covered)):
        band = bands.get(key) or {}
        lo, hi = band.get("low"), band.get("high")
        if lo is None or hi is None:
            continue
        out[key] = {"value": round(value, 3), "band": [lo, hi], "verdict": "below" if value < lo else "above" if value > hi else "in band"}
    return out


def position_drift(slides: list[dict], guide: dict) -> dict:
    """An element id that appears on more than one page should sit where it sat: a source
    line at 5.54, 6.78, 3.87 and 6.78 in reads as four different pages, and the eye is the
    only instrument SKILL.md had for it. Flagged when the top varies by more than space.sm."""
    step = (guide.get("spacing", {}).get("steps", {}).get("space.sm") or {}).get("emu") or 182880
    tops: dict[str, list[tuple[int, int]]] = {}
    for i, sd in enumerate(slides, 1):
        for el in sd.get("elements", []):
            if el.get("box") and not el.get("_spacer"):
                tops.setdefault(el.get("id", "?"), []).append((i, el["box"][1]))
    out = {}
    for ident, seen in tops.items():
        if len(seen) < 2:
            continue
        ys = [y for _, y in seen]
        if max(ys) - min(ys) > step:
            out[ident] = {"pages": [p for p, _ in seen], "top_in": [round(y / EMU_PER_INCH, 2) for y in ys], "drift_in": round((max(ys) - min(ys)) / EMU_PER_INCH, 2)}
    return out


def prepare_page(spec_raw: dict, guide: dict) -> None:
    """The page as the build enforces it: the guide's page size, the chrome zones, the
    indent progression for a bullet-less reference, and the title band. `layout.py
    capacity` calls this too, so the budget it prints is the budget the build solves."""
    page = spec_raw.setdefault("page", {})
    page.setdefault("width_emu", guide["reference"]["page"]["width_emu"])
    page.setdefault("height_emu", guide["reference"]["page"]["height_emu"])
    if "reserved_zones" not in page:
        page["reserved_zones"] = chrome_zones(guide)
    if "bullet_indent_roles" not in spec_raw and not guide.get("typography", {}).get("bullets"):
        # a reference with no bullets (a PDF, a deck of prose) gets the indent progression
        # of the spacing scale: sm, md, lg (deckgen 4b row 1: continue the indent progression)
        spec_raw["bullet_indent_roles"] = {"0": "space.sm", "1": "space.md", "2": "space.lg", "3": "space.xl"}
    band = title_band_emu(guide)
    root_children = spec_raw.get("root", {}).get("children", [])
    if band and root_children and root_children[0].get("kind") == "text" and root_children[0].get("paragraphs", [{}])[0].get("role") == "type.title" and "size" not in root_children[0]:
        # the reference keeps its titles above the top rule: a title that needs more
        # lines than the band holds is refused, never pushed under the rule
        pad_top = (guide.get("spacing", {}).get("steps", {}).get("space.margin") or {}).get("emu", 0)
        top_margin = (guide.get("spacing", {}).get("margins", {}).get("top") or {}).get("emu") or pad_top
        root_children[0]["size"] = {"width_emu": None, "height_emu": max(1, band - max(0, pad_top - top_margin))}
        root_children[0]["scale_class"] = "fixed"


def admission_note(kind: str, guide: dict) -> str | None:
    """Admission is bound to the guide it was checked with: a component admitted on keybank
    overflowed its band on netflix (12pt floor, different padding). Say so when the guide
    differs, and point at the check."""
    rec_path = Path(__file__).resolve().parent.parent / "components" / kind / "admitted.json"
    if not rec_path.exists():
        return f"component {kind!r} is not admitted; run component.py check and admit"
    rec = json.loads(rec_path.read_text())
    sha = guide.get("reference", {}).get("sha256")
    if rec.get("guide_reference_sha256") and sha and rec["guide_reference_sha256"] != sha:
        return f"component {kind!r} was admitted against another reference ({rec.get('guide_reference', '?')}); run component.py check with this guide before trusting its fit"
    return None


def load_component(kind: str):
    import importlib.util
    root = Path(__file__).resolve().parent.parent / "components" / kind
    spec_file = root / "expand.py"
    if not spec_file.exists():
        raise SystemExit(f"component {kind!r}: no components/{kind}/expand.py")
    module_spec = importlib.util.spec_from_file_location(f"component_{kind}", spec_file)
    module = importlib.util.module_from_spec(module_spec)  # type: ignore[arg-type]
    module_spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.expand


def expand_components(tree: dict, slide: dict, guide: dict, boxes: dict | None) -> tuple[dict, bool]:
    """Replace component nodes. With no boxes yet, each becomes a flexible placeholder so a
    probe solve can learn its box; with boxes, each is expanded at its box."""
    pending = False

    def visit(node: dict) -> dict:
        nonlocal pending
        if node.get("type") == "region":
            node = dict(node)
            node["children"] = [visit(c) for c in node.get("children", [])]
            return node
        if node.get("type") == "component":
            box = (boxes or {}).get(node["id"])
            if box is None:
                pending = True
                return {"type": "element", "id": node["id"], "kind": "image", "weight": node.get("weight")}
            data = dict(node.get("data", {}))
            data["_id"] = node["id"]
            note = admission_note(node["kind"], guide)
            if note:
                slide.setdefault("component_notes", []).append(note)
            sub = load_component(node["kind"])(data, {"width_emu": box["width"], "height_emu": box["height"]}, guide)
            sub = normalise(sub, slide)
            sub["weight"] = node.get("weight")
            if sub.get("id") != node["id"]:
                raise SystemExit(f"component {node['kind']}: expand must return a region whose id is the instance id {node['id']!r}")
            return sub
        return node

    return visit(tree), pending


def flatten(slide: dict, resolved: dict, spec_raw: dict) -> list[dict]:
    """The solver's boxes and measured lines, joined with the slide's styling, charts,
    images and rules, into the emitter's flat element list."""
    styling = slide.get("styling", {})
    charts = slide.get("charts", {})
    images = slide.get("images", {})
    rules = slide.get("rules", {})
    rects = slide.get("rects", {})
    out = []

    def visit(node: dict) -> None:
        if node.get("type") == "region":
            st = styling.get(node["id"])
            if st and (st.get("fill_role") or st.get("line_role")):
                box = resolved["boxes"][node["id"]]
                out.append({"id": node["id"] + "-fill", "kind": "rect", "box": [box["left"], box["top"], box["width"], box["height"]],
                            "fill_role": st.get("fill_role"), "line_role": st.get("line_role"), "prst": st.get("prst", "rect"), "line_width_emu": st.get("line_width_emu")})
            for child in node.get("children", []):
                visit(child)
            return
        nid = node["id"]
        if nid in slide.get("spacers", set()):
            return
        box = resolved["boxes"].get(nid)
        if box is None:
            raise SystemExit(f"{nid}: no box in the resolved layout")
        b = [box["left"], box["top"], box["width"], box["height"]]
        kind = node["kind"]
        extra = dict(styling.get(nid, {}))
        para_style = extra.pop("paragraphs", {})
        if kind == "text":
            measured = resolved["elements"][nid]["paragraphs"]
            paragraphs = []
            for i, (p_spec, p_meas) in enumerate(zip(node["paragraphs"], measured)):
                ps = para_style.get(str(i), {})
                para = {"role": p_spec["role"], "bullet_level": p_spec.get("bullet_level"), "lines": p_meas["lines"], "indent_emu": p_meas.get("marL", 0),
                        "runs": ps.get("runs") or [{"text": p_spec["text"]}], "ink_role": ps.get("ink_role"), "align": ps.get("align")}
                paragraphs.append(para)
            out.append({"id": nid, "kind": "text", "box": b, "paragraphs": paragraphs, **extra})
        elif kind == "table":
            t = node["table"]
            r = resolved["elements"][nid]
            out.append({"id": nid, "kind": "table", "box": b, "columns": t["columns"], "rows": t["rows"], "header_rows": t.get("header_rows", 1),
                        "column_widths_emu": r["gridCol_w"], "row_heights_emu": r["tr_h"], **extra})
        elif kind == "chart":
            c = charts.get(nid)
            if not c:
                raise SystemExit(f"{nid}: chart element without chart data under slide.charts")
            out.append({"id": nid, "kind": "chart", "box": b, **c, **extra})
        elif kind == "image":
            img = images.get(nid)
            if img and img.get("path"):
                out.append({"id": nid, "kind": "image", "box": b, **img, **extra})
            elif nid in rects or extra.get("fill_role"):
                out.append({"id": nid, "kind": "rect", "box": b, **rects.get(nid, {}), **extra})
            else:
                raise SystemExit(f"{nid}: image element needs slide.images[{nid}].path or a fill under slide.rects")
        elif kind == "rule":
            out.append({"id": nid, "kind": "rule", "box": b, **rules.get(nid, {}), **extra})
        else:
            raise SystemExit(f"{nid}: unknown kind {kind}")

    visit(spec_raw["root"])
    return out


def build(deck: dict, guide: dict, template: str, out: str, reference: str | None, others: list[str], renders: str | None, do_render: bool, chrome: str = "auto") -> dict:
    lg = L.load_guide(guide)
    ruler = L.default_ruler()
    index = L.default_index()
    emit_spec = {"slides": []}
    report = {"out": out, "ruler": ruler.name, "slides": []}
    for slide in deck["slides"]:
        spec_raw = json.loads(json.dumps(slide["spec"]))
        spec_raw["root"] = normalise(spec_raw["root"], slide)
        mark_measured_weights(spec_raw["root"], slide)
        prepare_page(spec_raw, guide)
        # components: probe once with placeholders to learn their boxes, then expand at those boxes
        tree, pending = expand_components(spec_raw["root"], slide, guide, None)
        if pending:
            # the probe measures the text around the placeholder first, so the component gets
            # the space the text leaves and not an equal share with a one-line source
            probe_spec = L.parse_spec({**spec_raw, "root": tree})
            attempt = L._attempt(L.Context(lg, ruler, index, probe_spec), L.Fraction(1))
            probe_boxes = attempt.resolved.boxes if attempt.resolved is not None else L.solve_tree(probe_spec, lg, 1.0)
            tree, _ = expand_components(spec_raw["root"], slide, guide, {k: v.as_dict() for k, v in probe_boxes.items()})
        spec_raw["root"] = tree
        spec = L.parse_spec(spec_raw)
        ctx = L.Context(lg, ruler, index, spec)
        outcome = L.descend(ctx)
        entry = {"id": slide.get("id"), "status": outcome.status, "attempts": [a.summary() for a in outcome.attempts]}
        if slide.get("component_notes"):
            entry["component_notes"] = sorted(set(slide["component_notes"]))
        if outcome.resolved is None:
            entry["reason"] = outcome.reason
            entry["unfittable"] = L.outcome_json(ctx, outcome).get("unfittable")
            report["slides"].append(entry)
            continue
        title_lines = sum(len(m.lines) for m in outcome.resolved.measurements.get("title", []))
        if outcome.status != "fit" and title_lines > 1 and title_band_emu(guide):
            # the first cause named first: every other violation on the page follows from a
            # title that pushed the content down
            entry["reason"] = f"title needs {title_lines} lines; the band above the top rule holds 1. Shorten the title before anything else."
        resolved = L.resolved_json(ctx, outcome.resolved)
        entry["scale"] = resolved["scale_float"]
        entry["violations"] = resolved["violations"]
        entry["text_lines"] = {k: v["lines"] for k, v in resolved["elements"].items() if v.get("kind") == "text"}
        # the fitter's overflow flag is relative to the PROBE box; after the intrinsic pass the
        # containment check is the verdict, so the flag is only reported when the slide did not fit
        entry["tables"] = {k: {"rows": len(v["tr_h"]), "height_emu": v["total_height_emu"], "column_widths_emu": v["gridCol_w"],
                               **({"fitting_row_prefix": v["fitting_row_prefix"], "width_deficit_emu": v["width_deficit_emu"]} if outcome.status != "fit" or resolved["violations"] else {})}
                           for k, v in resolved["elements"].items() if v.get("kind") == "table"}
        if outcome.status == "unfittable":
            entry["unfittable"] = L.outcome_json(ctx, outcome).get("unfittable")
        elements = flatten(slide, resolved, spec_raw)
        entry["density"] = density_of(elements, resolved, guide, spec_raw)
        emit_spec["slides"].append({"layout": slide.get("layout"), "notes": slide.get("notes"), "elements": elements})
        report["slides"].append(entry)
    report["position_drift"] = position_drift(emit_spec["slides"], guide)
    emit_report = emit_slides(emit_spec, template, guide, out, chrome)
    report["emitted_slides"] = len(emit_report["slides"])
    from pptx_tools import validate
    report["validation"] = validate(out, render=False)
    if do_render:
        import subprocess
        rdir = renders or str(Path(out).with_name(Path(out).stem + "-renders"))
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name("render.py")), out, "--out", rdir, "--width", "1600"], capture_output=True, text=True, timeout=900)
        try:
            report["renders"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            report["renders"] = {"error": completed.stderr[-500:]}
    if reference:
        from fingerprint import distance, fingerprint_deck, house_features, house_spread, layout_clean, panel, same_house, scorable, slide_features, total
        ref_slides = fingerprint_deck(reference)
        ref = house_features(ref_slides)
        cand = fingerprint_deck(out)
        d = distance(house_features(cand), ref)
        judge = {"reference": reference, "total": round(total(d), 3), "components": {k: (round(v, 3) if v is not None else None) for k, v in d.items()},
                 "per_slide": [round(total(distance(slide_features(s), ref)), 3) for s in cand], "others": {}}
        chosen = panel(others, reference)
        skipped = []
        kin = {}
        judge["house_spread"] = house_spread(ref_slides)
        for o in chosen:
            hf = house_features(fingerprint_deck(o, 25))
            if not scorable(hf):
                skipped.append(o)
                continue
            if same_house(hf, ref, judge["house_spread"]):
                kin[o] = round(total(distance(house_features(cand), hf)), 3)
                continue
            judge["others"][o] = round(total(distance(house_features(cand), hf)), 3)
        if skipped:
            judge["panel_skipped"] = {"reason": "no measured type (a scan or an empty deck)", "files": skipped}
        judge["same_house_on_panel"] = kin
        judge["panel"] = "given" if others else "refs/files (default)"
        judge["nearest_is_reference"] = all(judge["total"] < v for v in judge["others"].values()) if judge["others"] else None
        judge["reference_rank"] = 1 + sum(1 for v in judge["others"].values() if v <= judge["total"]) if judge["others"] else None
        # the judge reads style; fit is the solver's verdict and validity the package's. A
        # page is filed under the house only when all three hold.
        all_fit = all(sl.get("status") == "fit" and not sl.get("violations") for sl in report["slides"])
        judge["within_house_spread"] = judge["total"] <= judge["house_spread"]["p90"] if judge["house_spread"] else None
        judge["layout_clean"] = layout_clean(d)
        judge["filed_under_reference"] = (bool(judge["nearest_is_reference"]) and bool(judge["within_house_spread"]) and judge["layout_clean"]
                                          and all_fit and bool(report.get("validation", {}).get("ok")))
        report["judge"] = judge
    Path(out).with_suffix(".build.json").write_text(json.dumps(report, indent=1, default=str))
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck")
    ap.add_argument("--guide", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--reference", default=None)
    ap.add_argument("--others", nargs="*", default=[])
    ap.add_argument("--renders", default=None)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--chrome", default="auto", choices=["auto", "none", "draw"])
    args = ap.parse_args(argv)
    deck = json.loads(Path(args.deck).read_text())
    guide = json.loads(Path(args.guide).read_text())
    report = build(deck, guide, args.template, args.out, args.reference, args.others, args.renders, not args.no_render, args.chrome)
    brief = {"out": report["out"], "ruler": report["ruler"],
             "slides": [{k: v for k, v in s.items() if k in ("id", "status", "scale", "violations", "text_lines", "tables", "reason", "density", "component_notes")} for s in report["slides"]],
             "position_drift": report.get("position_drift"),
             "validation_ok": report.get("validation", {}).get("ok"), "problems": report.get("validation", {}).get("problems"),
             "judge": report.get("judge"), "renders": (report.get("renders") or {}).get("images")}
    print(json.dumps(brief, indent=1, default=str))
    return 0 if all(s["status"] == "fit" for s in report["slides"]) and report.get("validation", {}).get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
