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
   "charts": {"chart": {"type": "COLUMN_CLUSTERED", "categories": [...], "series": [{..., "fill_role": ..., "labels": {...}}],
                        "axes": {...}, "gap_width": 60, "overlap": 0, "legend": "none", ...}},   # emit_pptx.py's chart spec
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

After the solve and before the emit, four more instruments read the resolved page:
`contrast` (WCAG 2.2 ratio of every text run, table row class and chart text, data
labels included, against the fill the page draws behind it; below 3.0:1 refuses the
page with reason "contrast", below AA warns; no ink is ever swapped to pass it), `register` (kind counts, decoration count and container ratio against the
reference's register_stats bands), `tieouts` (a totals row that is not the column sum,
a warning listed first under `problems`), and the source-line rule (a table or chart
with no type.source_line or type.footnote paragraph refuses the page with reason "no
source line"). `repetition` at deck level is the arrangement similarity of each
consecutive pair of pages (the extractor's own slide_similarity) with any run of
look-alike pages longer than the reference's longest. After the emit, each page with a
chart carries `chart_defaults_taken`: every chart choice its spec left out, with the
value the file got for it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import component_api  # noqa: E402
import layout as L  # noqa: E402
from emit_pptx import HEX_RE, Guide as EmitGuide, chart_label_inks, emit as emit_slides, table_row_styles  # noqa: E402
from extract_style import ARCHETYPE_IOU_THRESHOLD, contrast as contrast_ratio, slide_similarity  # noqa: E402

EMU_PER_INCH = 914400
#: WCAG 2.2 SC 1.4.3 minimums and the large-scale sizes (deckgen style/contrast.py:
#: AA_NORMAL, AA_LARGE, LARGE_REGULAR_PT, LARGE_BOLD_PT), cited there to
#: https://www.w3.org/TR/WCAG22/#contrast-minimum and #dfn-large-scale.
AA_NORMAL, AA_LARGE, LARGE_REGULAR_PT, LARGE_BOLD_PT = 4.5, 3.0, 18.0, 14.0
#: Below this a run is refused, not warned: AA_LARGE, the weakest pair WCAG accepts for
#: any text. Nothing in the emitter corrects an ink, so this gate is the only catch.
CONTRAST_REFUSAL = 3.0
SOURCE_ROLES = ("type.source_line", "type.footnote")
#: A totals row headed by one of these is a statistic over the column, not its sum.
STATISTIC_LABELS = ("median", "average", "mean")
TIEOUT_KINDS = ("number", "currency", "percent")


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


# --- contrast on the resolved page (deckgen quality/contrast.py, style/contrast.py) -------


def aa_threshold(size_pt: float, bold: bool) -> float:
    """The SC 1.4.3 minimum for a run of this size and weight."""
    return AA_LARGE if size_pt >= LARGE_REGULAR_PT or (bold and size_pt >= LARGE_BOLD_PT) else AA_NORMAL


def _intersects(a: list, b: list) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _contains(outer: list, inner: list) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[0] + outer[2] >= inner[0] + inner[2] and outer[1] + outer[3] >= inner[1] + inner[3]


def _lower_backings(elements: list[dict], index: int, eg: EmitGuide, names: dict[str, str]) -> tuple[list[str], bool]:
    """Every colour that can lie under element `index`, and whether an image can: the
    guide's color.surface (the emitter's ground), then every earlier-drawn element whose
    box intersects, in draw order (flatten's order is the emitter's). An opaque fill
    whose box CONTAINS the element's box becomes the new ground and the only backing (a
    region's fill rect is drawn before its children, so the nearest enclosing filled
    region wins); a fill with another preset is one more possibility. The guide's colour
    roles carry no alpha, so nothing composites. `names` collects a role name per hex."""
    surface = eg.colors.get("color.surface", {}).get("hex")
    box = elements[index]["box"]
    backings = [surface] if surface else []
    if surface:
        names.setdefault(surface, "color.surface")
    undecidable = surface is None
    for earlier in elements[:index]:
        if not _intersects(earlier["box"], box):
            continue
        if earlier["kind"] == "image":
            undecidable = True
            continue
        if earlier["kind"] not in ("rect", "text") or not earlier.get("fill_role"):
            continue  # a table cannot overlap (the solver refuses it); a chart draws no plot fill here; a rule is a line
        fill = eg.hex(earlier["fill_role"], where=earlier.get("id", "fill"))
        if fill is None:
            continue
        full_rect = earlier["kind"] == "text" or (earlier.get("prst") or "rect") == "rect"
        if full_rect and _contains(earlier["box"], box):
            backings, undecidable = [fill], False
            names.setdefault(fill, f"{earlier['fill_role']} of {earlier.get('id')}")
        else:
            backings.append(fill)
            names.setdefault(fill, f"{earlier['fill_role']} of {earlier.get('id')} (partial)")
    return list(dict.fromkeys(backings)), undecidable


def _spec_ink(eg: EmitGuide, spec: dict, ink_role: str | None, where: str) -> tuple[str | None, str | None]:
    """The ink the emitter writes for a run: the paragraph's ink_role, else the type
    role's ink_role, else the role's observed literal (emit_pptx.write_text)."""
    role = ink_role or spec.get("ink_role")
    if role:
        return eg.hex(role, where=where), role
    literal = spec.get("ink")
    if literal and HEX_RE.match(literal):
        return literal, f"{where} observed ink"
    return None, None


def _score(ink: str, backings: list[str], size_pt: float, bold: bool, names: dict[str, str]) -> dict:
    """The worst (ink, backing) pair against its AA threshold, as deckgen reports it."""
    worst = min(backings, key=lambda b: contrast_ratio(ink, b))
    ratio = contrast_ratio(ink, worst)
    return {"ratio": round(ratio, 2), "threshold": aa_threshold(size_pt, bold), "size_pt": size_pt, "bold": bold, "backing": names.get(worst, worst)}


def contrast_of(elements: list[dict], resolved: dict, guide: dict) -> dict:
    """WCAG 2.2 contrast of every text run, every table row class and every chart text
    against the fill the page draws behind it. A text run's backing: the element's own
    fill, else the chain under it. A table's: the row's own fill as the emitter writes it
    (emit_pptx.table_row_styles: header, banding, data, emphasis), else the chain. A
    chart's data labels: the series or point fill for a position on the mark, the plot
    fill or the chain under the chart for a position off it, both when the spec leaves
    the position open (emit_pptx.chart_label_inks); axis labels and the legend: the plot.
    The ink scored is the ink the spec names: nothing swaps it, so a wrong one is
    refused here by name."""
    eg = EmitGuide(guide)
    out: dict = {"checked": 0, "violations": [], "warnings": [], "undecidable": [], "unbound": [], "nearest_pass": None}

    def file(finding: dict) -> None:
        out["checked"] += 1
        if finding["ratio"] < CONTRAST_REFUSAL:
            out["violations"].append(finding)
        elif finding["ratio"] < finding["threshold"]:
            out["warnings"].append(finding)
        elif out["nearest_pass"] is None or finding["ratio"] / finding["threshold"] < out["nearest_pass"]["ratio"] / out["nearest_pass"]["threshold"]:
            out["nearest_pass"] = finding  # the tightest pair that passed, so a near miss is visible

    for i, el in enumerate(elements):
        if el["kind"] not in ("text", "table", "chart"):
            continue
        names: dict[str, str] = {}
        lower, image_below = _lower_backings(elements, i, eg, names)
        own = eg.hex(el.get("fill_role"), where=el.get("id", el["kind"])) if el.get("fill_role") else None
        if own:
            names.setdefault(own, f"{el['fill_role']} of {el.get('id')}")
        measured = resolved["elements"].get(el["id"], {})
        if el["kind"] == "text":
            if image_below and not own:
                out["undecidable"].append({"element": el["id"], "why": "an image lies under the text; contrast needs pixels"})
                continue
            for pi, para in enumerate(el["paragraphs"]):
                spec = eg.type_spec(para["role"], where=el["id"])
                ink, ink_name = _spec_ink(eg, spec, para.get("ink_role"), para["role"])
                if ink is None:
                    out["unbound"].append({"element": el["id"], "paragraph": pi, "role": para["role"], "why": "no ink role or observed ink; the run inherits the master's text colour"})
                    continue
                meas = measured.get("paragraphs", [{}])[pi] if pi < len(measured.get("paragraphs", [])) else {}
                size_pt = (meas.get("sz") or round(float(spec["size_pt"]) * 100)) / 100
                for ri, run in enumerate(para.get("runs") or [{"text": ""}]):
                    bold = bool(meas.get("b") or run.get("emphasis") or spec.get("weight", 400) >= 700)
                    finding = {"element": el["id"], "paragraph": pi, "run": ri, "role": para["role"], "ink": ink_name,
                               "text": (run.get("text") or "")[:40], **_score(ink, [own] if own else lower, size_pt, bold, names)}
                    file(finding)
            continue
        if el["kind"] == "chart":
            plot_role = el.get("plot_fill_role")
            plot = [eg.hex(plot_role, where=el["id"])] if plot_role and plot_role != "none" else lower
            if plot_role and plot_role != "none":
                names.setdefault(plot[0], f"{plot_role} plot of {el['id']}")
            for item in chart_label_inks(el, eg):
                where = {"element": el["id"], "part": item["part"], **({"points": item["points"]} if item["points"] else {})}
                if item["ink"] is None:
                    out["unbound"].append({**where, "why": "no ink_role on the part or on the chart text; it inherits the theme's text colour"})
                    continue
                backings: list[str] = []
                unknown = [b[1] for b in item["on"] if b[0] == "unknown"]
                for b in item["on"]:
                    if b[0] == "fill":
                        backings.append(b[1])
                        names.setdefault(b[1], f"{b[2]} fill of {item['part']}")
                    elif b[0] == "plot":
                        if plot is lower and image_below:
                            unknown.append("an image lies under the chart; contrast needs pixels")
                        backings.extend(plot)
                if unknown or not backings:
                    out["undecidable"].append({**where, "why": "; ".join(unknown) or "no backing"})
                    if not backings:
                        continue
                spec = item["spec"] or {}
                size_pt = float(spec.get("size_pt") or 0) or None
                bold = spec.get("weight", 400) >= 700
                finding = {**where, "ink": item["ink_name"] or "chart text ink", **_score(item["ink"], list(dict.fromkeys(backings)), size_pt or 0.0, bold, names)}
                if size_pt is None:
                    finding["threshold"], finding["size_pt"] = AA_NORMAL, "theme default"
                file(finding)
            continue
        # a table: every row class as emit_pptx.table_row_styles writes it
        header_sz = (measured.get("header") or {}).get("sz")
        cell_sz = (measured.get("cell") or {}).get("sz")
        cell_spec = eg.type_spec("type.table_cell" if "type.table_cell" in eg.roles else "type.body", where="table")
        classes: dict[tuple, dict] = {}
        for st in table_row_styles(el, eg):
            if st["fill_hex"]:
                names.setdefault(st["fill_hex"], f"{st['fill_name']} of {el['id']}")
            size_pt = ((header_sz if st["header"] else cell_sz) or round(float(cell_spec["size_pt"]) * 100)) / 100
            key = (st["class"], st["ink_hex"], st["fill_hex"], st["bold"])
            entry = classes.setdefault(key, {"element": el["id"], "row_class": st["class"], "rows": [], "ink": st["ink_name"], "fill": names.get(st["fill_hex"]) if st["fill_hex"] else None, "size_pt": size_pt, "bold": st["bold"]})
            entry["rows"].append(st["row"])
        for (_, ink_hex, fill_hex, _), entry in classes.items():
            if ink_hex is None:
                out["unbound"].append({"element": el["id"], "row_class": entry["row_class"], "why": "no ink role bound; the cells inherit the master's text colour"})
                continue
            if fill_hex is None and image_below:
                out["undecidable"].append({"element": el["id"], "row_class": entry["row_class"], "why": "an image lies under unfilled rows; contrast needs pixels"})
                continue
            file({**entry, **_score(ink_hex, [fill_hex] if fill_hex else lower, entry["size_pt"], entry["bold"], names)})
    return out


# --- register against the reference's bands (extract_style.composition) --------------------

REGISTER_KIND = {"text": "text", "image": "image", "rect": "shape", "table": "table", "chart": "chart", "rule": "line"}


def _against_band(value: float | None, band: dict | None, digits: int = 3) -> dict:
    lo, hi = (band or {}).get("low"), (band or {}).get("high")
    if value is None:
        return {"value": None, "band": [lo, hi], "verdict": "no text on the page"}
    if lo is None or hi is None:
        return {"value": round(value, digits), "band": None, "verdict": "no band in the guide"}
    return {"value": round(value, digits), "band": [lo, hi], "verdict": "below" if value < lo else "above" if value > hi else "in band"}


def register_of(elements: list[dict], guide: dict) -> dict:
    """The page's register as the extractor measures a reference slide's: per-kind
    counts of the drawn shapes (a region's fill is a shape, a rule is a line), the
    decoration count (fills and lines without text), and the container ratio (text
    shapes carrying their own fill or outline over all text shapes), each against the
    reference's 10th to 90th percentile band. A takeaway set in a filled REGION counts
    as one decoration and one bare text shape, which is what the emitter draws."""
    stats = guide.get("register_stats") or {}
    kinds = Counter(REGISTER_KIND[el["kind"]] for el in elements if el["kind"] in REGISTER_KIND)
    texty = [el for el in elements if el["kind"] == "text"]
    container = (sum(1 for el in texty if el.get("fill_role") or el.get("line_role")) / len(texty)) if texty else None
    decoration = sum(1 for el in elements if el["kind"] in ("rect", "rule"))
    return {"kind_counts": {k: _against_band(kinds.get(k, 0), (stats.get("kind_counts") or {}).get(k)) for k in ("text", "image", "shape", "table", "chart", "line")},
            "decoration_count": _against_band(decoration, stats.get("decoration_counts")),
            "container_ratio": _against_band(container, stats.get("container_ratio"))}


def repetition_of(pages: list[tuple[int, list[dict]]], guide: dict) -> dict:
    """Arrangement similarity of each consecutive pair of emitted pages: the extractor's
    slide_similarity (Hungarian on box IoU over the larger set) on the flattened
    elements' boxes, similar at the archetype threshold it clusters the reference with.
    A run of similar consecutive pages longer than the reference's longest run of one
    archetype (composition.archetypes consecutive_max) is flagged."""
    archetypes = (guide.get("composition") or {}).get("archetypes") or []
    reference_max = max((int(a.get("consecutive_max") or 1) for a in archetypes), default=None)
    pairs, runs = [], []
    run = [pages[0][0]] if pages else []
    for (pa, ea), (pb, eb) in zip(pages, pages[1:]):
        sim = slide_similarity([tuple(el["box"]) for el in ea], [tuple(el["box"]) for el in eb])
        similar = sim >= ARCHETYPE_IOU_THRESHOLD
        pairs.append({"pages": [pa, pb], "similarity": round(sim, 3), "similar": similar})
        if similar:
            run.append(pb)
        else:
            runs.append(run)
            run = [pb]
    if run:
        runs.append(run)
    over = [{"pages": r, "length": len(r)} for r in runs if reference_max is not None and len(r) > reference_max]
    return {"threshold": ARCHETYPE_IOU_THRESHOLD, "pairs": pairs, "reference_consecutive_max": reference_max, "runs_over_reference": over}


# --- tie-outs and the source line ------------------------------------------------------------

_FIGURE_STRIP = str.maketrans("", "", "$,%x ")


def parse_figure(text: str) -> float | None:
    """A table figure as a number: $ , % x and spaces stripped, parentheses negative,
    a Unicode minus honoured. None for anything else (n.a., n.m., a dash, blank)."""
    s = str(text).strip()
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = s.replace("−", "-").translate(_FIGURE_STRIP)
    if not s:
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _decimals(text: str) -> int:
    m = re.search(r"\.(\d+)", str(text))
    return len(m.group(1)) if m else 0


def tieouts_of(elements: list[dict]) -> list[dict]:
    """For every table with totals_last_row: each number, currency or percent column's
    body sum against its totals cell, compared at the totals cell's own precision. A
    totals row headed median, average or mean is a statistic and is skipped; a column
    with an unparseable cell (n.a., n.m.) is skipped and says which cell."""
    out = []
    for el in elements:
        if el["kind"] != "table" or not el.get("totals_last_row") or len(el["rows"]) < 2:
            continue
        head = str(el["rows"][-1][0]).strip().lower()
        if any(word in head for word in STATISTIC_LABELS):
            out.append({"table": el["id"], "status": "skipped", "note": f"totals row {el['rows'][-1][0]!r} is a statistic over the column, not its sum"})
            continue
        for ci, col in enumerate(el["columns"]):
            if col.get("value_kind") not in TIEOUT_KINDS:
                continue
            total_text = str(el["rows"][-1][ci])
            total = parse_figure(total_text)
            rec = {"table": el["id"], "column": col.get("label", col.get("key")), "total": total_text}
            if total is None:
                out.append({**rec, "status": "skipped", "note": "the totals cell is blank or not a figure"})
                continue
            body = [(str(r[ci]), parse_figure(r[ci])) for r in el["rows"][:-1]]
            bad = [text for text, value in body if value is None]
            if bad:
                out.append({**rec, "status": "skipped", "note": f"cells not figures: {bad}"})
                continue
            d = _decimals(total_text)
            total_sum = sum(value for _, value in body)
            rec.update({"sum": f"{total_sum:.{d}f}", "precision": d, "status": "ok" if abs(round(total_sum, d) - round(total, d)) < 10 ** -(d + 6) else "mismatch"})
            out.append(rec)
    return out


def bridge_ties(elements: list[dict]) -> list[dict]:
    """A chart that declares `bridge: {"deltas", "totals"}` is checked two ways: every
    total equals the running sum of the steps before it, and every category's DRAWN
    span (the stacked series with a fill, positives stacking up from zero and negatives
    down, in series order, as both renderers stack them) equals the span that step
    covers. The second catches a base series computed wrong, which the eye reads as a
    wrong number. Tolerance is the one the emitter's waterfall used: 0.5% of the
    larger magnitude."""
    out = []
    for el in elements:
        decl = el.get("bridge") if el["kind"] == "chart" else None
        if not decl:
            continue
        where = el.get("id", "chart")
        cats = el.get("categories") or []
        deltas = [float(v) for v in decl.get("deltas") or []]
        totals = {int(i) for i in decl.get("totals") or []}
        if "STACKED" not in str(el.get("type")) or len(deltas) != len(cats) or not totals <= set(range(len(cats))):
            out.append({"chart": where, "detail": f"bridge declaration needs a stacked type, one delta per category ({len(deltas)} for {len(cats)}) and totals inside 0..{len(cats) - 1}"})
            continue
        scale = max([abs(d) for d in deltas] + [1e-9])
        tol = 0.005 * scale
        running = 0.0
        for i, d in enumerate(deltas):
            if i in totals:
                if i > 0 and abs(d - running) > tol:
                    out.append({"chart": where, "detail": f"total {cats[i]!r} is {d:g} but the steps before it sum to {running:g}"})
                want, running = (min(0.0, d), max(0.0, d)), d
            else:
                want, running = (min(running, running + d), max(running, running + d)), running + d
            up = down = 0.0
            lo = hi = None
            for s in el["series"]:
                v = float(s["values"][i])
                fill = next((p.get("fill_role", s.get("fill_role")) for p in s.get("points") or [] if p.get("index") == i), s.get("fill_role"))
                a, b = (up, up + v) if v >= 0 else (down + v, down)
                if v >= 0:
                    up += v
                else:
                    down += v
                if v != 0 and fill != "none":
                    lo, hi = (a, b) if lo is None else (min(lo, a), max(hi, b))
            drawn = (lo or 0.0, hi or 0.0)
            if abs(drawn[0] - want[0]) > tol or abs(drawn[1] - want[1]) > tol:
                out.append({"chart": where, "detail": f"{cats[i]!r} draws {drawn[0]:g} to {drawn[1]:g}; the bridge step covers {want[0]:g} to {want[1]:g}"})
    return out


def source_line_missing(elements: list[dict]) -> bool:
    """A page carrying a table or a chart needs a type.source_line or type.footnote."""
    exhibit = any(el["kind"] in ("table", "chart") for el in elements)
    sourced = any(p["role"] in SOURCE_ROLES for el in elements if el["kind"] == "text" for p in el["paragraphs"])
    return exhibit and not sourced


def page_problems(entry: dict, elements: list[dict], resolved: dict, guide: dict) -> list[dict]:
    """The ordered problem list: tie-out warnings first (a totals row can be a subtotal
    the agent meant), then the refusals (contrast, no source line). A refusal turns a fit
    page unfittable with the refusal's name as the reason; a page the solver already
    refused keeps the solver's reason, the first cause."""
    entry["contrast"] = contrast_of(elements, resolved, guide)
    entry["register"] = register_of(elements, guide)
    entry["tieouts"] = tieouts_of(elements)
    problems = [{"kind": "tieout", "severity": "warning", "detail": f"{t['table']} column {t['column']!r}: body rows sum to {t['sum']}, the totals cell reads {t['total']}"} for t in entry["tieouts"] if t["status"] == "mismatch"]
    for v in entry["contrast"]["violations"]:
        if "run" in v:
            where = f"{v['element']} paragraph {v['paragraph']} run {v['run']}"
        elif "part" in v:
            where = f"{v['element']} {v['part']}" + (f" (points {v['points']})" if v.get("points") else "")
        else:
            where = f"{v['element']} {v['row_class']} rows"
        problems.append({"kind": "contrast", "severity": "refusal", "detail": f"{where}: {v['ink']} over {v['backing']} is {v['ratio']}:1, under {CONTRAST_REFUSAL}:1 (AA asks {v['threshold']}:1 at {v['size_pt']}pt{' bold' if v['bold'] else ''})"})
    entry["bridge_ties"] = bridge_ties(elements)
    problems.extend({"kind": "bridge does not tie", "severity": "refusal", "detail": f"{b['chart']}: {b['detail']}"} for b in entry["bridge_ties"])
    if source_line_missing(elements):
        problems.append({"kind": "no source line", "severity": "refusal", "detail": "the page carries a table or a chart and no paragraph in type.source_line or type.footnote"})
    refusals = list(dict.fromkeys(p["kind"] for p in problems if p["severity"] == "refusal"))
    entry["solver_status"] = entry["status"]  # the geometry verdict alone; component.py's harness page reads it
    if refusals and entry["status"] == "fit":
        entry["status"], entry["reason"] = "unfittable", "; ".join(refusals)
    return problems


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


def component_root(kind: str) -> Path:
    """A component's directory: `components/<kind>` in the repo, or the directory itself
    when `kind` is a path (a component under development outside the library)."""
    if "/" in kind or kind.startswith("."):
        return Path(kind).resolve()
    return Path(__file__).resolve().parent.parent / "components" / kind


def admission_note(kind: str, guide: dict) -> str | None:
    """Admission is bound to the guide it was checked with: a component admitted on keybank
    overflowed its band on netflix (12pt floor, different padding). Say so when the guide
    differs, and point at the check."""
    rec_path = component_root(kind) / "admitted.json"
    if not rec_path.exists():
        return f"component {kind!r} is not admitted; run component.py check and admit"
    rec = json.loads(rec_path.read_text())
    sha = guide.get("reference", {}).get("sha256")
    if rec.get("guide_reference_sha256") and sha and rec["guide_reference_sha256"] != sha:
        return f"component {kind!r} was admitted against another reference ({rec.get('guide_reference', '?')}); run component.py check with this guide before trusting its fit"
    return None


def load_component(kind: str):
    import importlib.util
    root = component_root(kind)
    spec_file = root / "expand.py"
    if not spec_file.exists():
        raise SystemExit(f"component {kind!r}: no {spec_file}")
    module_spec = importlib.util.spec_from_file_location(f"component_{root.name}", spec_file)
    module = importlib.util.module_from_spec(module_spec)  # type: ignore[arg-type]
    module_spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.expand


def expand_components(tree: dict, slide: dict, guide: dict, boxes: dict | None, api: dict | None = None) -> tuple[dict, bool]:
    """Replace component nodes. With no boxes yet, each becomes a flexible placeholder so a
    probe solve can learn its box; with boxes, each is expanded at its box. Every expand
    call receives the guide with `_api` (component_api.py: the solver's own text width
    and line pitch) so a component measures instead of estimating."""
    pending = False
    api = api if api is not None else component_api.make_api(guide)
    guide_for_components = component_api.with_api(guide, api)

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
            if box["width"] <= 0 or box["height"] <= 0:
                # the page left the component no room; expanding into nothing emits debris
                raise SystemExit(f"component {node['id']}: the page leaves it a {box['width']} x {box['height']} EMU box; cut or split the page before the component")
            sub = load_component(node["kind"])(data, {"width_emu": box["width"], "height_emu": box["height"]}, guide_for_components)
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
                        "runs": ps.get("runs") or [{"text": p_spec["text"]}], "ink_role": ps.get("ink_role") or p_spec.get("ink_role"), "align": ps.get("align") or p_spec.get("align")}
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
    api = component_api.make_api(guide, lg, ruler, index)
    emit_spec = {"slides": []}
    report = {"out": out, "ruler": ruler.name, "slides": []}
    pages: list[tuple[int, list[dict]]] = []  # (deck page number, flattened elements) of every emitted page
    emitted: list[dict] = []  # the report entry of every emitted page, in emit order
    for number, slide in enumerate(deck["slides"], 1):
        spec_raw = json.loads(json.dumps(slide["spec"]))
        spec_raw["root"] = normalise(spec_raw["root"], slide)
        mark_measured_weights(spec_raw["root"], slide)
        prepare_page(spec_raw, guide)
        # components: probe once with placeholders to learn their boxes, then expand at those boxes
        tree, pending = expand_components(spec_raw["root"], slide, guide, None, api)
        if pending:
            # the probe measures the text around the placeholder first, so the component gets
            # the space the text leaves and not an equal share with a one-line source
            probe_spec = L.parse_spec({**spec_raw, "root": tree})
            attempt = L._attempt(L.Context(lg, ruler, index, probe_spec), L.Fraction(1))
            probe_boxes = attempt.resolved.boxes if attempt.resolved is not None else L.solve_tree(probe_spec, lg, 1.0)
            tree, _ = expand_components(spec_raw["root"], slide, guide, {k: v.as_dict() for k, v in probe_boxes.items()}, api)
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
                               **({"fitting_row_prefix": v["fitting_row_prefix"], "width_deficit_emu": v["width_deficit_emu"], "column_deficits_emu": v["column_deficits_emu"]} if outcome.status != "fit" or resolved["violations"] else {})}
                           for k, v in resolved["elements"].items() if v.get("kind") == "table"}
        if outcome.status == "unfittable":
            entry["unfittable"] = L.outcome_json(ctx, outcome).get("unfittable")
        elements = flatten(slide, resolved, spec_raw)
        entry["density"] = density_of(elements, resolved, guide, spec_raw)
        entry["problems"] = page_problems(entry, elements, resolved, guide)
        pages.append((number, elements))
        emit_spec["slides"].append({"layout": slide.get("layout"), "notes": slide.get("notes"), "elements": elements})
        report["slides"].append(entry)
        emitted.append(entry)
    report["position_drift"] = position_drift(emit_spec["slides"], guide)
    report["repetition"] = repetition_of(pages, guide)
    emit_report = emit_slides(emit_spec, template, guide, out, chrome)
    report["emitted_slides"] = len(emit_report["slides"])
    for entry, page in zip(emitted, emit_report["slides"]):
        if page.get("charts"):
            # every chart choice the spec left out, with the value written for it
            entry["chart_defaults_taken"] = {c["id"]: c["defaults_taken"] for c in page["charts"]}
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
    shown = ("id", "status", "reason", "problems", "scale", "violations", "text_lines", "tables", "density", "contrast", "register", "tieouts", "component_notes", "chart_defaults_taken")
    brief = {"out": report["out"], "ruler": report["ruler"],
             "slides": [{k: s[k] for k in shown if k in s} for s in report["slides"]],  # problems first: the warnings and refusals before the figures
             "position_drift": report.get("position_drift"), "repetition": report.get("repetition"),
             "validation_ok": report.get("validation", {}).get("ok"), "problems": report.get("validation", {}).get("problems"),
             "judge": report.get("judge"), "renders": (report.get("renders") or {}).get("images")}
    print(json.dumps(brief, indent=1, default=str))
    return 0 if all(s["status"] == "fit" for s in report["slides"]) and report.get("validation", {}).get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
