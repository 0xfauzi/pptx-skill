#!/usr/bin/env python3
"""Build a deck: solve every slide with measured fit, emit on the reference package,
validate, render and judge. The one command the model runs after writing a deck spec.

    build_deck.py deck.json --guide guide.json --template tpl.pptx -o out.pptx
                  [--reference ref.pptx] [--others a.pptx b.pdf] [--renders DIR] [--no-render]
                  [--plan plan.json] [--house-deck other.guide.json ...]

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
a warning listed first under `problems`), the source-line check (a table or chart with
no type.source_line or type.footnote paragraph refuses the page where the house's digest
shows source lines on at least 80% of its data pages and warns where 50% or more do or
the habit is unmeasured; a page WITH one warns where under 50% of the house's data pages
carry one; both lines unmeasured, and the deck-level `source_lines` sets the deck's count
beside the house's), and `title` (the page title's characters, words and lines against the house's
titles, and the register the slide states against the house's register counts; warnings only).
`repetition` at deck level is the section's realised variety: each page's content (the
frame left out) assigned a realised composition by the extractor's own leader clustering,
measured by plan.py (V, distinct per page, runs) against the house's content pages, with
any run longer than the house's longest flagged and, given --plan, every page whose
realised composition disagrees with the plan's. After the emit, each page with a
chart carries `chart_defaults_taken`: every chart choice its spec left out, with the
value the file got for it.

A slide's `annotations` (annotate.py) are resolved on the solved page, before those
instruments, into rect, rule and text elements; their collisions refuse the page, and
after the render the words LibreOffice drew are checked against what each one covers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import annotate  # noqa: E402
import component_api  # noqa: E402
import images
import layout as L  # noqa: E402
import plan  # noqa: E402
from chart_geometry import bar_thickness, plot_rect  # noqa: E402
from emit_pptx import EMPHASIS_EXAMPLE, HEX_RE, OLD_EMPHASIS_KEYS, TABLE_STYLE_KEYS, table_emphasis, Guide as EmitGuide, chart_label_inks, chrome_hex, chrome_on_page, chrome_text, emit as emit_slides, table_header_bold, table_roles, table_row_styles  # noqa: E402
from extract_style import ARCHETYPE_IOU_THRESHOLD, contrast as contrast_ratio, leader_clusters, slide_similarity, union_area  # noqa: E402
from ooxml import paragraphs_words, visual_extent  # noqa: E402

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


def chrome_box_emu(ch: dict) -> tuple[int, int, int, int]:
    """The page area a chrome entry covers, in EMU: its box_in turned by its rotation_deg."""
    box = tuple(int(v * EMU_PER_INCH) for v in ch["box_in"])
    return visual_extent(box, round(float(ch.get("rotation_deg") or 0) * 60000))  # type: ignore[arg-type]


def is_surface(ch: dict) -> bool:
    """A band the reference builds its pages on: a content box lies inside it on at least
    half the slides that carry it (bain's white page frame and body band, its navy title
    band). It is ground, not furniture: no zone is reserved for it, and the contrast gate
    scores whatever lands on it against its fill."""
    return ch["kind"] == "band" and ch.get("carries_content_on", 0) >= 0.5 * max(1, ch.get("slides_present", 0))


def chrome_zones(guide: dict, mode: str = "auto") -> list[dict]:
    """Reserved zones from the chrome a page carries in this --chrome mode
    (emit_pptx.chrome_on_page). Furniture anchored to the bottom edge reserves everything
    below it (the reference's content never runs under its footer rule); a top-anchored
    rule stays a thin boundary, because the title band sits above it and the solver must
    be free to place the title there. A surface band reserves nothing (is_surface)."""
    zones = []
    page_h = guide["reference"]["page"]["height_emu"]
    page_w = guide["reference"]["page"]["width_emu"]
    for ch in chrome_on_page(guide, mode):
        if ch["kind"] not in ("footer", "page_number", "date", "logo", "rule", "band", "label") or is_surface(ch):
            continue
        left, top, width, height = chrome_box_emu(ch)
        if ch.get("anchor") == "slide_bottom":
            # the reference's content stops a spacing step above its footer rule, never on it:
            # the zone grows upward by the smallest spacing step so a source line keeps that air
            clearance = (guide.get("spacing", {}).get("steps", {}).get("space.xs") or {}).get("emu") or 0
            top = max(0, top - int(clearance))
            left, width, height = 0, page_w, page_h - top
        zones.append({"left": left, "top": top, "width": width, "height": height, "source": f"{ch['chrome_id']}:{ch['kind']}"})
    return zones


def top_rules(guide: dict) -> list[dict]:
    """The guide's top rules: rules on at least half the reference's slides, across at
    least half the page's width, in the upper half of the page and not anchored to its
    bottom edge: the rule under the title. The title band is everything above them. The
    miner's edge anchor is not the test: bain's yellow rule sits 1.42 in down an 8.5 in
    page, past the miner's edge distance, and is still the rule its titles sit on."""
    ref = guide.get("reference", {})
    n = max(1, ref.get("slides", 1))
    page = ref.get("page") or {}
    page_w, page_h = page.get("width_emu"), page.get("height_emu")
    if not page_w or not page_h:
        return []
    return [ch for ch in guide.get("chrome", []) if ch["kind"] == "rule" and ch.get("slides_present", 0) >= 0.5 * n
            and ch.get("anchor") != "slide_bottom" and ch["box_in"][2] * EMU_PER_INCH >= 0.5 * page_w
            and (ch["box_in"][1] + ch["box_in"][3]) * EMU_PER_INCH <= 0.5 * page_h]


def ruler_basis(guide: dict) -> str:
    """Why this ruler measured: the guide's pin, or this machine's default for a guide that
    pins none. Printed on every build's brief, so a ruler that changed is seen."""
    pinned = (guide.get("measurement") or {}).get("ruler")
    if pinned:
        return "pinned by the guide when its draft was extracted; every build on this guide measures with it"
    return ("NOT pinned: the guide predates the pin, so this machine's default measured; it changes when uharfbuzz is "
            "installed or removed. Pin it: extract the draft again (extract_style.py pins this machine's ruler) and fold the completion again")


def title_rule_top_emu(guide: dict) -> int | None:
    """The top edge of the highest top rule: the title's box ends there."""
    rules = top_rules(guide)
    return int(min(ch["box_in"][1] for ch in rules) * EMU_PER_INCH) if rules else None


def title_band_emu(guide: dict, spec_raw: dict | None = None) -> int | None:
    """Height of the band the title sits in: from the root's content top (its top padding
    at full scale; space.margin when no spec is given) down to the top rule. The title
    must fit there, as every reference title does."""
    rule_top = title_rule_top_emu(guide)
    if rule_top is None:
        return None
    pad_top = (guide.get("spacing", {}).get("steps", {}).get("space.margin") or {}).get("emu", 0)
    root = (spec_raw or {}).get("root") or {}
    if root.get("layout"):
        try:
            pad_top = L.pad_emu(L._parse_layout(root["layout"], "root"), L.load_guide(guide), L.Fraction(1))[1]
        except (L.LayoutContractError, KeyError, TypeError, ValueError):
            pass  # a malformed root layout is refused by name when the page is solved
    return rule_top - pad_top if rule_top > pad_top else None


FIT_KEYS = L.FIT_KEYS
PRESENTATION_KEYS = ("fill_role", "line_role", "pad_role", "prst", "line_width_emu", "anchor", "ink_role", "dash", "_spacer")


# What the solver reads on a table node and in its table spec; every other key there
# is refused by name, so a misplaced key cannot be dropped in silence.
TABLE_NODE_KEYS = {"type", "node_type", "id", "kind", "table", "weight", "scale_class", "size"}
TABLE_SPEC_KEYS = {"columns", "rows", "header_rows", "header_role", "cell_role", "cell_padding_role"}


def lift_table_style(node: dict, styling: dict) -> None:
    """Gather a table's drawing keys (emit_pptx.TABLE_STYLE_KEYS) into slide.styling.<id>,
    the one place the emitter and the contrast gate read them. They may be written on the
    table element, inside its `table` spec, or under styling; a key given in two of those
    places with different values is refused, and so is any key none of them knows."""
    nid = node["id"]
    st = styling.setdefault(nid, {})
    origin = {k: "slide.styling" for k in st}
    table = dict(node.get("table") or {})
    for source, label in ((node, "the table element"), (table, "its table spec")):
        for key in [k for k in source if k in TABLE_STYLE_KEYS]:
            value = source.pop(key)
            if key in st and st[key] != value:
                raise SystemExit(f"table {nid!r}: {key} is {st[key]!r} under {origin[key]} and {value!r} on {label}; write it once")
            st[key], origin[key] = value, label
    node["table"] = table
    for keys, allowed, label in ((set(node), TABLE_NODE_KEYS, "table element"), (set(table), TABLE_SPEC_KEYS, "table spec"),
                                 (set(st), TABLE_STYLE_KEYS | set(PRESENTATION_KEYS), f"slide.styling.{nid}")):
        unknown = sorted(keys - allowed)
        if unknown and set(unknown) & OLD_EMPHASIS_KEYS:
            raise SystemExit(f"table {nid!r}: {sorted(set(unknown) & OLD_EMPHASIS_KEYS)} became one key, emphasis, a list of groups: {EMPHASIS_EXAMPLE}")
        if unknown:
            raise SystemExit(f"table {nid!r}: unknown keys {unknown} on the {label}. The {label} takes {sorted(allowed)}; "
                             f"drawing keys {sorted(TABLE_STYLE_KEYS)} may sit on the element, in its table spec or under slide.styling.{nid}")


def mark_measured_weights(node: dict, slide: dict, guide: dict) -> None:
    """The emitter bolds emphasis runs, totals and emphasis rows and a bold header; the
    solver must measure them bold, so the table spec it parses gets what the emitter reads.
    A picture sized by a role (images.box_size) gets that size as a fixed box here, so the
    solver places the box the emitter fills."""
    styling = slide.get("styling", {})
    if node.get("type") == "region":
        for c in node.get("children", []):
            mark_measured_weights(c, slide, guide)
        return
    st = styling.get(node.get("id"), {})
    if node.get("kind") == "image" and node.get("id") in (slide.get("images") or {}):
        pic = slide_picture(slide, node["id"], guide)
        size = images.box_size(pic, guide)
        if size is not None:
            if node.get("size") not in (None, size):
                raise SystemExit(f"image {node['id']!r}: its size comes from slide.images[{node['id']!r}]'s "
                                 f"{'height_role' if 'height_role' in pic.entry else 'width_role'}; remove the node's own size")
            node["size"] = size
            node["scale_class"] = "fixed"
        return
    if node.get("kind") == "text":
        for i, p in enumerate(node.get("paragraphs", [])):
            ps = (st.get("paragraphs") or {}).get(str(i), {})
            if any(r.get("emphasis") for r in ps.get("runs") or []):
                p["emphasis"] = True
    elif node.get("kind") == "table":
        table = node.setdefault("table", {})
        table["totals_last_row"] = bool(st.get("totals_last_row"))
        # the cells the emitter bolds, as the emitter reads them (emit_pptx.table_emphasis)
        groups = table_emphasis({"id": node.get("id"), "columns": table.get("columns") or [], "rows": table.get("rows") or [], **st})
        table["emphasis_rows"] = sorted({r for g in groups if g["rows"] is not None and g["bold"] for r in g["rows"]})
        table["emphasis_columns"] = sorted({c for g in groups if g["columns"] is not None and g["bold"] for c in g["columns"]})
        table["header_bold"] = table_header_bold(st, EmitGuide(guide))


def spanned_tables(node: dict) -> dict[str, int]:
    """{table id: header_rows} for every table whose header has a spanner (layout.header_spans)."""
    out: dict[str, int] = {}
    if node.get("type") == "region":
        for c in node.get("children", []):
            out.update(spanned_tables(c))
    elif node.get("kind") == "table":
        t = node.get("table") or {}
        n = int(t.get("header_rows", 1))
        try:
            labels = [L.header_labels(c, n, "table") for c in t.get("columns") or []]
        except L.LayoutContractError:
            return out  # refused by name when the page is solved
        if any(c1 > c0 for row in L.header_spans(labels, n) for c0, c1 in row):
            out[node["id"]] = n
    return out


def slide_picture(slide: dict, nid: str, guide: dict) -> images.Picture:
    """slide.images[nid] validated once per build (images.picture: the source read and
    refused at the boundary by name)."""
    cache = slide.setdefault("_pictures", {})
    if nid not in cache:
        try:
            cache[nid] = images.picture(slide["images"][nid], f"slide.images[{nid!r}]", guide)
        except images.ImageRefused as error:
            raise SystemExit(f"image {nid!r}: {error}") from None
    return cache[nid]


#: What the solver reads on an element node, by kind (layout._parse_node); a presentation
#: key (PRESENTATION_KEYS) is lifted into styling first. Anything else on a node is read by
#: nothing, so it is refused by name instead of being dropped in silence: a chart's
#: plot_area written on its tree node left the chart auto-placed and every annotation on
#: it refused for a plot_area the spec seemed to hold.
NODE_KEYS = {"type", "node_type", "id", "kind", "weight", "scale_class", "size"}
NODE_KIND_KEYS = {"text": {"paragraphs"}, "table": {"table"}, "chart": set(), "image": set(), "rule": set(), "rect": set()}
#: where each element kind's own data lives on the slide, for the refusal's instruction
NODE_DATA_HOME = {"chart": "slide.charts", "image": "slide.images", "rule": "slide.rules"}


#: what a text box's `anchor` takes (emit_pptx._body_props): top, middle, bottom
TEXT_ANCHORS = ("t", "m", "b")
#: the paragraph keys the solver reads on a text node; runs (bold or coloured words) go
#: under styling, where the emitter reads them, never on the node
PARAGRAPH_KEYS = {"role", "text", "bullet_level", "ink_role", "align", "emphasis"}


def check_presentation(nid: str, kind: str, st: dict) -> None:
    """A presentation value nothing would draw is refused by name, never dropped: an
    anchor outside t, m, b fell back to top in silence (round 5: "middle" on three
    houses), and a prst on a text element drew a plain box."""
    from emit_pptx import RECT_PRESETS
    if "anchor" in st and st["anchor"] not in TEXT_ANCHORS:
        raise SystemExit(f"{kind} {nid!r}: anchor {st['anchor']!r} is not one of {list(TEXT_ANCHORS)} (t top, m middle, b bottom)")
    if kind == "text" and st.get("pad_role") is not None:
        raise SystemExit(f"text {nid!r}: pad_role insets nothing on a text element (the solver measures its words at the box's full width). "
                         "Put the text in a region whose layout carries pad_role (or pad_roles, per side) and whose styling carries the fill")
    if "prst" in st:
        if kind == "text":
            raise SystemExit(f"text {nid!r}: prst draws nothing on a text element (a text box is a rectangle). Put the text in a region whose "
                             "styling carries fill_role, prst and a pad_role deep enough to keep the words inside the shape's body; the region's fill is drawn under them")
        if st["prst"] not in RECT_PRESETS:
            raise SystemExit(f"{kind} {nid!r}: prst {st['prst']!r} is not one of {sorted(RECT_PRESETS)}")


def check_node_keys(node: dict) -> None:
    kind = node.get("kind")
    if kind == "text":
        for i, p in enumerate(node.get("paragraphs") or []):
            if not isinstance(p, dict) or "text" not in p or set(p) - PARAGRAPH_KEYS:
                extra = sorted(set(p) - PARAGRAPH_KEYS) if isinstance(p, dict) else []
                raise SystemExit(f"text {node.get('id')!r} paragraph {i}: a paragraph is {{\"role\", \"text\"}} plus {sorted(PARAGRAPH_KEYS - {'role', 'text'})}"
                                 + (f"; {extra} {'is' if len(extra) == 1 else 'are'} not read here" if extra else "; it has no text")
                                 + (". Runs go under styling: \"styling\": {\"" + str(node.get("id")) + "\": {\"paragraphs\": {\"" + str(i)
                                    + "\": {\"runs\": [{\"text\": ...}, {\"text\": ..., \"emphasis\": true}]}}}}, and the paragraph keeps the whole text"
                                    if isinstance(p, dict) and "runs" in p else ""))
        if node.get("size") is not None:
            # a literal height on text would be a coordinate; the title's band is the build's
            raise SystemExit(f"text {node.get('id')!r}: size is not read on text; a text box is as tall as its measured lines, or takes a "
                             "share of a column by weight (inside a region with a weight). Space above or below it is a gap_role or "
                             "a region's pad_roles; the title's height above a top rule is the build's own band")
    if kind not in NODE_KIND_KEYS or kind == "table":
        return  # an unknown kind is layout's to refuse; a table's keys are lift_table_style's
    stray = sorted(set(node) - NODE_KEYS - NODE_KIND_KEYS[kind] - set(PRESENTATION_KEYS))
    if not stray:
        return
    nid = node.get("id")
    home = NODE_DATA_HOME.get(kind)
    if kind == "chart":
        from emit_pptx import CHART_KEYS
        chart_keys = sorted(set(stray) & CHART_KEYS)
        if chart_keys:
            raise SystemExit(f"chart {nid!r}: {chart_keys} {'is' if len(chart_keys) == 1 else 'are'} written on the chart's node in the spec "
                             f"tree, where nothing reads {'it' if len(chart_keys) == 1 else 'them'}. Move every chart key into "
                             f"slide.charts[{nid!r}] (the node keeps only id, kind and weight): "
                             f"\"charts\": {{\"{nid}\": {{\"type\": ..., \"categories\": ..., \"series\": ..., \"plot_area\": ..., \"axes\": ...}}}}")
    raise SystemExit(f"{kind} {nid!r}: unknown keys {stray} on its node in the spec tree; a {kind} node takes "
                     f"{sorted(NODE_KEYS | NODE_KIND_KEYS[kind])} plus the styling keys {sorted(k for k in PRESENTATION_KEYS if not k.startswith('_'))}"
                     + (f", and its data goes under {home}[{nid!r}]" if home else ""))


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
    check_node_keys(node)
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
    if node.get("kind") == "table":
        lift_table_style(node, styling)
    return node


#: A text box whose lines fill less than this share of its height is listed under density
#: (unmeasured: a reading aid for the review, never a gate).
EMPTY_BOX_SHARE = 0.4


def ink_boxes(elements: list[dict], resolved: dict) -> list[tuple[int, int, int, int]]:
    """What a page draws, as boxes: a text element's measured lines (from its box top, at
    the paragraph spacing and pitch the solver measured, each line as wide as its text),
    a table's fitted rows, every other element's box. An annotation's text, which the
    solver did not measure, counts at its box."""
    out: list[tuple[int, int, int, int]] = []
    for el in elements:
        box = el.get("box")
        if not box:
            continue
        measured = (resolved.get("elements") or {}).get(el.get("id"))
        if el.get("kind") == "text" and measured and measured.get("kind") == "text":
            y = box[1]
            for p in measured["paragraphs"]:
                y += p["spcBef"] * L.EMU_PER_HUNDREDTH_POINT
                for width in p["line_widths_emu"]:
                    out.append((box[0] + int(p.get("marL") or 0), y, int(width), int(p["pitch_emu"])))
                    y += int(p["pitch_emu"])
                y += p["spcAft"] * L.EMU_PER_HUNDREDTH_POINT
        elif el.get("kind") == "table" and measured and measured.get("kind") == "table":
            out.append((box[0], box[1], box[2], min(box[3], int(measured["total_height_emu"]))))
        else:
            out.append(tuple(box))  # type: ignore[arg-type]
    return out


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
            words += sum(len(str(c).split()) for row in el.get("rows", []) for c in row) + sum(len(t.split()) for t in L.header_texts(el.get("columns", []), int(el.get("header_rows", 1))))
    n_elements = sum(1 for el in elements if el.get("kind") not in ("rule",) and not el.get("_spacer"))
    page = spec_raw.get("page", {})
    pw, ph = page.get("width_emu", 1), page.get("height_emu", 1)
    covered = union_area(ink_boxes(elements, resolved), pw, ph) / max(1, pw * ph)
    bands = guide.get("density_bands", {})
    empty = []
    for el in elements:
        measured = (resolved.get("elements") or {}).get(el.get("id"))
        if el.get("kind") == "text" and measured and measured.get("kind") == "text" and el["box"][3] > 0:
            share = 1 - min(1.0, measured["height_emu"] / el["box"][3])
            if share >= EMPTY_BOX_SHARE:
                empty.append({"id": el["id"], "text_ends_in": round((el["box"][1] + measured["height_emu"]) / EMU_PER_INCH, 2),
                              "box_ends_in": round((el["box"][1] + el["box"][3]) / EMU_PER_INCH, 2), "empty_share": round(share, 2)})
    out = {"words": words, "elements": n_elements, "covered_area_fraction": round(covered, 3),
           "text_boxes_mostly_empty": empty or "none",
           "covered_basis": "ink: each measured text line at its width and pitch, each table at its fitted rows, each chart, image "
                            "and fill at its box, unioned; a text box stretched past its lines is not covered. The house band "
                            "unions the reference's shape boxes, which count a stretched box whole, so the band is the more generous"}
    for key, value in (("words_per_slide", words), ("elements_per_slide", n_elements), ("content_area_fraction", covered)):
        band = bands.get(key) or {}
        if band.get("low") is None or band.get("high") is None:
            continue
        out[key] = _against_band(value, band)
    return out


def drift_step(guide: dict) -> int:
    return (guide.get("spacing", {}).get("steps", {}).get("space.sm") or {}).get("emu") or 182880


def element_tracks(pages: list[tuple[int, list[dict]]], step: int) -> list[dict]:
    """One element followed across pages: the same id and kind, with its left edge and
    width each within `step` of where the track first had them. An id reused for a
    different column in a different arrangement (bcg's right-t: 7.45 in from the left and
    5.31 wide on one page, 0.57 and 4.32 on another) starts a new track instead of
    reading as one element that drifted."""
    tracks: list[dict] = []
    for number, els in pages:
        for el in els:
            if not el.get("box") or el.get("_spacer"):
                continue
            x, y, w, _ = el["box"]
            for t in tracks:
                if (t["id"] == el.get("id", "?") and t["kind"] == el["kind"] and abs(t["left"] - x) <= step and abs(t["width"] - w) <= step
                        and number not in t["pages"]):
                    t["pages"].append(number)
                    t["tops"].append(y)
                    t["boxes"].append(el["box"])
                    break
            else:
                tracks.append({"id": el.get("id", "?"), "kind": el["kind"], "left": x, "width": w, "pages": [number], "tops": [y], "boxes": [el["box"]]})
    return tracks


def position_drift(pages: list[tuple[int, list[dict]]], guide: dict) -> dict:
    """An element that appears on more than one page should sit where it sat: a source
    line at 5.54, 6.78, 3.87 and 6.78 in reads as four different pages, and the eye is the
    only instrument SKILL.md had for it. Flagged when the top of one element_track varies
    by more than space.sm; an id that splits into several tracks is listed as reused
    across arrangements, never as drift."""
    step = drift_step(guide)
    tracks = element_tracks(pages, step)
    out: dict = {}
    split = Counter(t["id"] for t in tracks)
    for t in tracks:
        if len(t["pages"]) < 2:
            continue
        if max(t["tops"]) - min(t["tops"]) > step:
            key = t["id"] if split[t["id"]] == 1 else f"{t['id']} (pages {t['pages']})"
            out[key] = {"pages": t["pages"], "top_in": [round(y / EMU_PER_INCH, 2) for y in t["tops"]], "drift_in": round((max(t["tops"]) - min(t["tops"])) / EMU_PER_INCH, 2)}
    reused = {i: [t["pages"] for t in tracks if t["id"] == i] for i, n in split.items() if n > 1}
    if reused:
        out["_ids_reused_across_arrangements"] = reused
    return out


# --- contrast on the resolved page (deckgen quality/contrast.py, style/contrast.py) -------


def aa_threshold(size_pt: float, bold: bool) -> float:
    """The SC 1.4.3 minimum for a run of this size and weight."""
    return AA_LARGE if size_pt >= LARGE_REGULAR_PT or (bold and size_pt >= LARGE_BOLD_PT) else AA_NORMAL


def _intersects(a: list, b: list) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _contains(outer: list, inner: list) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[0] + outer[2] >= inner[0] + inner[2] and outer[1] + outer[3] >= inner[1] + inner[3]


def _ellipse_contains(outer: list, inner: list) -> bool:
    """Whether the ellipse inscribed in `outer` holds every corner of `inner` (an
    annotation badge's label inside its circle)."""
    cx, cy, rx, ry = outer[0] + outer[2] / 2, outer[1] + outer[3] / 2, outer[2] / 2, outer[3] / 2
    if rx <= 0 or ry <= 0:
        return False
    return all(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0 for x in (inner[0], inner[0] + inner[2]) for y in (inner[1], inner[1] + inner[3]))


def preset_holds(prst: str, outer: list, inner: list) -> bool:
    """Whether a filled preset drawn in `outer` lies under every point of `inner`, at the
    preset's default adjustments (the emitter writes none): the solid body of each shape,
    taken conservatively (a homePlate's body before its point, a chevron's between its
    notch and its point, a right arrow's shaft, a rounded rectangle without its corners)."""
    x, y, w, h = outer
    ss = min(w, h)
    if prst == "rect":
        return _contains(outer, inner)
    if prst == "ellipse":
        return _ellipse_contains(outer, inner)
    if prst == "roundRect":
        r = ss * 16667 / 100000
        return _contains([x, y + r, w, h - 2 * r], inner) or _contains([x + r, y, w - 2 * r, h], inner)
    if prst == "homePlate":
        return _contains([x, y, w - ss * 0.5, h], inner)
    if prst == "chevron":
        return _contains([x + ss * 0.5, y, w - ss, h], inner)
    if prst == "rightArrow":
        return _contains([x, y + h * 0.25, w - ss * 0.5, h * 0.5], inner)
    return False  # a bracket, brace, diamond or triangle: no body to stand text on


def chrome_layers(guide: dict, mode: str) -> list[dict]:
    """The page's chrome as the contrast gate reads it, in paint order: bands (a fill
    under whatever lands on them) and text lines (a run to score), each with its EMU page
    box. Drawn chrome lies under every content element."""
    eg = EmitGuide(guide)
    page_w, page_h = guide["reference"]["page"]["width_emu"], guide["reference"]["page"]["height_emu"]
    out = []
    for ch in chrome_on_page(guide, mode):
        box = list(chrome_box_emu(ch))
        if not _intersects(box, [0, 0, page_w, page_h]):
            continue  # off the slide (netflix's master keeps its colour swatches there): nothing a reader sees
        fill = chrome_hex(ch, eg, "fill")
        if ch["kind"] == "band" and fill:
            out.append({"kind": "band", "id": ch["chrome_id"], "box": box, "fill_hex": fill})
        elif chrome_text(ch) is not None:
            if fill:
                # a text shape with its own fill draws its words on that fill
                out.append({"kind": "band", "id": ch["chrome_id"], "box": box, "fill_hex": fill})
            out.append({"kind": "text", "id": ch["chrome_id"], "box": box, "text": chrome_text(ch) or "<page number>", "style": ch.get("text_style") or {}})
    return out


def _lower_backings(elements: list[dict], index: int, eg: EmitGuide, names: dict[str, str], chrome: list[dict] | None = None) -> tuple[list[str], bool]:
    """Every colour that can lie under element `index`, and whether an image can: the
    guide's color.surface (the emitter's ground), then every chrome band whose box
    intersects (chrome is drawn under the content, in its paint order), then every
    earlier-drawn element whose box intersects, in draw order (flatten's order is the
    emitter's). An opaque fill whose box CONTAINS the element's box becomes the new
    ground and the only backing (a region's fill rect is drawn before its children, so the
    nearest enclosing filled region wins); a fill with another preset is one more
    possibility. The guide's colour roles carry no alpha, so nothing composites. `names`
    collects a role name per hex."""
    surface = eg.colors.get("color.surface", {}).get("hex")
    box = elements[index]["box"]
    backings = [surface] if surface else []
    if surface:
        names.setdefault(surface, "color.surface")
    undecidable = surface is None
    for band in chrome or []:
        if band["kind"] != "band" or not _intersects(band["box"], box):
            continue
        if _contains(band["box"], box):
            backings, undecidable = [band["fill_hex"]], False
            names.setdefault(band["fill_hex"], f"chrome {band['id']}")
        else:
            backings.append(band["fill_hex"])
            names.setdefault(band["fill_hex"], f"chrome {band['id']} (partial)")
    for earlier in elements[:index]:
        if not _intersects(earlier["box"], box):
            continue
        if earlier["kind"] == "image":
            undecidable = True
            continue
        if earlier["kind"] == "chart" and earlier.get("plot_fill_role") not in (None, "none"):
            # an annotation inside a chart's fixed plot rectangle stands on the plot fill
            plot = plot_rect(earlier, earlier["box"])
            plot = None if plot is None else [round(v) for v in plot]  # whole EMU, as the boxes it is compared with
            if plot is not None and _intersects(plot, box):
                fill = eg.hex(earlier["plot_fill_role"], where=earlier.get("id", "chart"))
                if _contains(plot, box):
                    backings, undecidable = [fill], False
                    names.setdefault(fill, f"{earlier['plot_fill_role']} plot of {earlier.get('id')}")
                else:
                    backings.append(fill)
                    names.setdefault(fill, f"{earlier['plot_fill_role']} plot of {earlier.get('id')} (partial)")
            continue
        if earlier["kind"] not in ("rect", "text") or not earlier.get("fill_role"):
            continue  # a table cannot overlap (the solver refuses it); a rule is a line
        fill = eg.hex(earlier["fill_role"], where=earlier.get("id", "fill"))
        if fill is None:
            continue
        prst = "rect" if earlier["kind"] == "text" else earlier.get("prst") or "rect"
        if preset_holds(prst, earlier["box"], box):
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
    return {"ratio": round(ratio, 2), "threshold": aa_threshold(size_pt, bold), "size_pt": size_pt, "bold": bold, "backing": names.get(worst, worst),
            "ink_hex": ink, "backing_hex": worst}


def contrast_of(elements: list[dict], resolved: dict, guide: dict, chrome_mode: str = "auto", precedent: dict | None = None) -> dict:
    """WCAG 2.2 contrast of every text run, every table row class, every chart text and
    every chrome text line against the fill the page draws behind it. A text run's backing: the element's own
    fill, else the chain under it. A table's: the row's own fill as the emitter writes it
    (emit_pptx.table_row_styles: header, banding, data, emphasis), else the chain. A
    chart's data labels: the series or point fill for a position on the mark, the plot
    fill or the chain under the chart for a position off it, both when the spec leaves
    the position open (emit_pptx.chart_label_inks); axis labels and the legend: the plot.
    The ink scored is the ink the spec names: nothing swaps it, so a wrong one is
    refused here by name.

    House precedent: a pair under AA that the reference itself draws (the same ink hex
    over the same backing hex, ooxml.ink_backings) at this size or smaller is the house's
    own choice, not a defect of the deck. It is filed under `house_precedent` with the
    reference's evidence, neither refused nor warned. `precedent` None means no reference
    was given, and every pair is judged on WCAG alone."""
    eg = EmitGuide(guide)
    out: dict = {"checked": 0, "violations": [], "warnings": [], "house_precedent": [], "undecidable": [], "unbound": [], "nearest_pass": None,
                 "precedent_source": "reference" if precedent is not None else "none: no --reference, so no pair can claim the house's precedent"}

    def file(finding: dict) -> None:
        out["checked"] += 1
        seen = (precedent or {}).get((finding["ink_hex"], finding["backing_hex"]))
        if finding["ratio"] < finding["threshold"] and seen and isinstance(finding["size_pt"], (int, float)) and seen["min_size_pt"] <= finding["size_pt"]:
            out["house_precedent"].append({**finding, "reference": {"min_size_pt": seen["min_size_pt"], "chars": seen["chars"], "pages": sorted(seen["pages"])[:12]}})
            return
        if finding["ratio"] < CONTRAST_REFUSAL:
            out["violations"].append(finding)
        elif finding["ratio"] < finding["threshold"]:
            out["warnings"].append(finding)
        elif out["nearest_pass"] is None or finding["ratio"] / finding["threshold"] < out["nearest_pass"]["ratio"] / out["nearest_pass"]["threshold"]:
            out["nearest_pass"] = finding  # the tightest pair that passed, so a near miss is visible

    chrome = chrome_layers(guide, chrome_mode)
    for ci, line in enumerate(chrome):
        # a chrome line is scored like a run: its observed ink over the surface and the
        # chrome bands painted before it (_lower_backings over the chrome alone)
        if line["kind"] != "text":
            continue
        style = line["style"]
        where = {"element": line["id"], "part": "chrome text", "text": line["text"][:40]}
        if not style.get("ink_hex"):
            out["unbound"].append({**where, "why": "the chrome entry carries no text_style.ink_hex; the drawn run inherits the master's text colour"})
            continue
        names: dict[str, str] = {}
        lower, _ = _lower_backings([line], 0, eg, names, chrome[:ci])
        line_pt = float(style.get("size_pt") or eg.roles.get("type.caption", {}).get("size_pt") or 9)  # the size draw_chrome writes
        file({**where, "ink": f"observed ink {style['ink_hex']} of {line['id']}", **_score(style["ink_hex"], lower, line_pt, bool(style.get("bold")), names)})
    for i, el in enumerate(elements):
        if el["kind"] not in ("text", "table", "chart"):
            continue
        names = {}
        lower, image_below = _lower_backings(elements, i, eg, names, chrome)
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
                spec = item["spec"] or {}
                over = label_overflows_bar(el, item, spec) if backings and "series" in item else []
                if over:
                    # a label taller than its bar spills onto the plot: scored there too
                    backings.extend(plot)
                    where["overflows_bar_at_points"] = over
                if unknown or not backings:
                    out["undecidable"].append({**where, "why": "; ".join(unknown) or "no backing"})
                    if not backings:
                        continue
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
        _, cell_spec = table_roles(el, eg)
        classes: dict[tuple, dict] = {}
        for row in table_row_styles(el, eg):
            size_pt = ((header_sz if row["header"] else cell_sz) or round(float(cell_spec["size_pt"]) * 100)) / 100
            for st in row["cells"]:
                if st["fill_hex"]:
                    names.setdefault(st["fill_hex"], f"{st['fill_name']} of {el['id']}")
                key = (st["class"], st["ink_hex"], st["fill_hex"], st["bold"])
                entry = classes.setdefault(key, {"element": el["id"], "row_class": st["class"], "rows": [], "ink": st["ink_name"], "fill": names.get(st["fill_hex"]) if st["fill_hex"] else None, "size_pt": size_pt, "bold": st["bold"]})
                if row["row"] not in entry["rows"]:
                    entry["rows"].append(row["row"])
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


NO_EVIDENCE = "no evidence: the reference band is 0 to 0 (none on at least nine slides in ten; an exhibit pasted as a picture counts as an image)"


def _against_band(value: float | None, band: dict | None, digits: int = 3) -> dict:
    """A value against the reference's 10th to 90th percentile band. A band of [0, 0] is
    absence, not a ceiling: a reference that pastes its exhibits as pictures has no
    native table or chart to count, and a PDF whose words were not read has no word
    count. A value above such a band is reported as no evidence, never as 'above'."""
    lo, hi = (band or {}).get("low"), (band or {}).get("high")
    if value is None:
        return {"value": None, "band": [lo, hi], "verdict": "no text on the page"}
    if lo is None or hi is None:
        return {"value": round(value, digits), "band": None, "verdict": "no band in the guide"}
    if hi == 0 and value > 0:
        return {"value": round(value, digits), "band": [lo, hi], "verdict": NO_EVIDENCE}
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


def frame_tracks(pages: list[tuple[int, list[dict]]], guide: dict) -> list[dict]:
    """The page frame: element_tracks present on EVERY emitted page (the title, the units
    line, the lead, the source line, a drawn band). The frame is the same on every page
    by construction, so counting it makes any two pages alike before their content is
    compared (netflix: title, units, lead and source gave 4/8 on pages whose exhibits all
    differed). A table, chart or image on every page is content repeating, never frame.
    A one-page deck has no frame."""
    if len(pages) < 2:
        return []
    every = {n for n, _ in pages}
    return [t for t in element_tracks(pages, drift_step(guide)) if set(t["pages"]) == every and t["kind"] not in ("table", "chart", "image")]


REALISED_CLASS = plan.REALISED_CLASS
BUILD_UNREAD = {"exhibits": "the build knows element kinds, not exhibit types; the plan's exhibit types are declared",
                "classes": "a component or an image on the page: its exhibit class is not its element kind"}


def realised_classes(spec_root: dict) -> list[str] | None:
    """The exhibit classes a page's spec realises, read from its element kinds: a table is
    class table, a chart is data_chart, text, rules and shapes are no exhibit. A component
    or an image could be any class (a kpi row is big numbers, a picture may be a chart), so
    a page holding one is unread (None), never text only."""
    found: list[str] = []

    def walk(node: dict) -> bool:
        if node.get("type") == "region":
            return all(walk(c) for c in node.get("children", []))
        if node.get("type") == "component" or (node.get("kind") == "image" and not node.get("_spacer")):
            return False
        cls = REALISED_CLASS.get(node.get("kind"))
        if cls and cls not in found:
            found.append(cls)
        return True

    return found if walk(spec_root) else None


#: Unmeasured: a pair of pages whose box similarity lies this close to the archetype
#: line is marked borderline (round 5: one lead-in wrapping to two lines moved a keybank
#: pair from 0.434 to 0.543 and flipped the realised variety).
BORDERLINE_SIMILARITY = 0.1


def repetition_of(pages: list[tuple[int, list[dict]]], guide: dict, plan_pages: list[dict] | None = None, others: list[dict] | None = None,
                  slide_ids: dict[int, str] | None = None, classes: dict[int, list[str] | None] | None = None,
                  names: list[str] | None = None, plan_check: dict | None = None) -> dict:
    """The built section's realised variety. Each solved page's content is its flattened
    elements' boxes with the page frame (frame_tracks) left out; pages get a realised
    composition by the extractor's own leader clustering (leader_clusters on
    slide_similarity, Hungarian box IoU over the larger set, at the archetype threshold),
    which is how the house's archetypes were assigned, and are measured by plan.py's one
    measure: V, distinct compositions per page, the longest run and every run. A page that
    did not solve breaks the sequence (absence, not a change). Against the house
    (guide.variety, pooled with `others`), a run longer than the house's longest is flagged;
    with no house evidence none is judged, and the report says so. Against the plan, each
    adjacent pair where plan and build disagree (the plan repeats a composition and the
    build changes it, or the reverse) flags the later page. The exhibit classes each page
    realises (realised_classes) are measured the same way against the house's digest
    classes: unlike the plan's composition names they cannot be renamed, so a section of
    pages that each set a table beside a chart reads as the repeat it is however the plan
    names them. The house's measure keeps its
    title as content where the build leaves the frame out: the house is held to the more
    lenient count, never the stricter one."""
    frame = frame_tracks(pages, guide)
    framed = {(n, tuple(b)) for t in frame for n, b in zip(t["pages"], t["boxes"])}

    def content(number: int, els: list[dict]) -> list[tuple]:
        return [tuple(el["box"]) for el in els if (number, tuple(el["box"])) not in framed]

    boxes = [content(n, els) for n, els in pages]
    realised = {pages[m][0]: f"b{fi + 1}" for fi, (_, members) in enumerate(leader_clusters(boxes)) for m in members}
    segments: list[list[dict]] = []
    for number, _ in pages:
        if not segments or segments[-1][-1]["slide"] != number - 1:
            segments.append([])
        segments[-1].append({"slide": number, "composition": realised[number], "exhibits": None, "classes": (classes or {}).get(number)})
    pairs = []
    for (pa, ea), (pb, eb) in zip(pages, pages[1:]):
        if pb == pa + 1:
            sim = slide_similarity(content(pa, ea), content(pb, eb))
            pairs.append({"pages": [pa, pb], "similarity": round(sim, 3), "similar": sim >= ARCHETYPE_IOU_THRESHOLD,
                          **({"borderline": True} if abs(sim - ARCHETYPE_IOU_THRESHOLD) < BORDERLINE_SIMILARITY else {})})
    built = plan.measure_deck("built", segments, BUILD_UNREAD)
    house = plan.house_of([guide, *(others or [])], names)
    pooled = house["pooled"]
    longest = pooled.get("longest_run") if pooled["status"] == "measured" else None
    runs = built.get("runs") or []
    over: list[dict] | str = ([{"pages": r["pages"], "length": len(r["pages"]), "realised": r["composition"]} for r in runs if len(r["pages"]) > longest]
                              if longest is not None else f"not judged: the house's longest run is no evidence ({pooled.get('why')})")
    out: dict = {"threshold": ARCHETYPE_IOU_THRESHOLD, "frame_left_out": sorted(t["id"] for t in frame), "pairs": pairs,
                 "realised": [{"page": n, "composition": realised[n]} for n, _ in pages], "measure": built,
                 "house": {"decks": [{k: d[k] for k in ("deck", "status", "content_pages", "composition", "longest_run", "why") if k in d} for d in house["decks"]],
                           "pooled": pooled},
                 "against_house": ({"composition_V": plan.against(built["composition"]["V"], pooled, "composition"),
                                    "classes_V": plan.against(built["classes"].get("V"), pooled, "classes"),
                                    "distinct_per_page": plan.distinct_against(built["distinct"]["per_page"], built["content_pages"], pooled),
                                    "longest_run": {"built": built["longest_run"], "house": longest if longest is not None else "no evidence"}}
                                   if built["status"] == "measured" else {"built": built["why"]}),
                 "house_longest_run": longest if longest is not None else "no evidence", "runs_over_reference": over}
    warnings = [f"{k} {v['value']} {v['verdict']} ({v.get('house_p10_deck', v.get('house_p10_window'))}); the threshold is unmeasured"
                for k, v in (out["against_house"].items() if built["status"] == "measured" else []) if isinstance(v, dict) and v.get("verdict", "").startswith("below")]
    edge = [p for p in pairs if p["similar"] and p.get("borderline")]
    if edge:
        note = ("; of the repeats, " + ", ".join(f"pages {p['pages'][0]}-{p['pages'][1]} ({p['similarity']})" for p in edge)
                + f" sit within {BORDERLINE_SIMILARITY} of the {ARCHETYPE_IOU_THRESHOLD} line: a line of text more or less can flip them")
        warnings = [w + note if w.startswith("composition_V") else w for w in warnings]
    out["warnings"] = warnings
    if plan_pages is None:
        out["plan"] = "not given: build with --plan plan.json to compare the realised compositions with the planned ones"
        return out
    by_id = {p["id"]: p for p in plan_pages}
    mine = plan.measure_deck("plan", plan.plan_segments(plan_pages), plan.PLAN_UNREAD)
    flags = []
    for pair in pairs:
        a, b = (by_id[(slide_ids or {})[n]] for n in pair["pages"])
        planned_same = a["composition"] == b["composition"]
        built_same = realised[pair["pages"][0]] == realised[pair["pages"][1]]
        if planned_same != built_same:
            flags.append({"page": pair["pages"][1], "id": b["id"], "after": a["id"], "planned": [a["composition"], b["composition"]],
                          "realised": [realised[pair["pages"][0]], realised[pair["pages"][1]]], "similarity": pair["similarity"],
                          "detail": (f"planned to repeat {a['composition']} ({b['deliberate_parallel'] or 'undeclared'}) but built differently"
                                     if planned_same else f"planned {a['composition']} then {b['composition']} but built alike")
                                    + (f"; borderline: similarity {pair['similarity']} against the {ARCHETYPE_IOU_THRESHOLD} line, so a text block "
                                       "wrapping one line more or less can flip it: change the arrangement, not the words, if the pages must differ"
                                       if pair.get("borderline") else "")})
    ids = slide_ids or {}
    repeats = [{"pages": [ids.get(pair["pages"][0]), ids.get(pair["pages"][1])], "deliberate_parallel": by_id[ids[pair["pages"][1]]]["deliberate_parallel"]}
               for pair in pairs if realised[pair["pages"][0]] == realised[pair["pages"][1]] and ids.get(pair["pages"][1]) in by_id]
    if built["status"] == "measured":
        out["warnings"] = [w + plan.parallels_note(repeats, built["composition"]) if w.startswith("composition_V") else w for w in warnings]
    out["plan"] = {"check": {k: (plan_check or {}).get(k) for k in ("status", "refusals", "warnings", "subset")}, "measure": mine,
                   "realised_by_page": [{"page": n, "id": ids.get(n), "planned": (by_id.get(ids.get(n)) or {}).get("composition"), "realised": realised[n]}
                                        for n, _ in pages],
                   "names": "realised names (b1, b2, ...) are this build's own clusters of pages with alike boxes, not the plan's names: "
                            "two pages share a realised name when they share an arrangement",
                   "composition_V": {"planned": (mine.get("composition") or {}).get("V"), "realised": (built.get("composition") or {}).get("V")},
                   "exhibits_V": {"planned": (mine.get("exhibits") or {}).get("V"), "realised": "not measured: " + BUILD_UNREAD["exhibits"]},
                   "classes_V": {"planned": "not declared: " + plan.PLAN_UNREAD["classes"], "realised": (built.get("classes") or {}).get("V", (built.get("classes") or {}).get("why"))},
                   "pages_differing_from_plan": flags}
    return out


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
            rec = {"table": el["id"], "column": " ".join(t for t in L.header_labels(col, int(el.get("header_rows", 1)), "table") if t) or col.get("key"), "total": total_text}
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


def source_line_of(elements: list[dict]) -> dict:
    """Whether the page holds a data exhibit (a table or a chart, plan.REALISED_CLASS) and
    whether it carries a type.source_line or type.footnote paragraph of its own (an
    annotation's label is not one)."""
    return {"data_page": any(el["kind"] in REALISED_CLASS for el in elements),
            "source_line": any(p["role"] in SOURCE_ROLES for el in elements if el["kind"] == "text" and not el.get("annotation")
                               for p in el["paragraphs"])}


#: Unmeasured: the house carries source lines "as a rule" when at least this share of its
#: data pages does, and "rarely" below SOURCE_LINE_RARE, read from the completed digest
#: over at least SOURCE_LINE_MIN_PAGES data pages. The numbers are choices; no reader has
#: been asked where a rule begins.
SOURCE_LINE_HOUSE_SHARE = 0.8
SOURCE_LINE_RARE = 0.5
SOURCE_LINE_MIN_PAGES = 3


#: what each habit asks of a new page, as source_line_problem enforces it
SOURCE_LINE_ADVICE = {
    "rule": "the house carries them as a rule: a data page without one is refused",
    "common": "add one where the house would (a data page without one is warned)",
    "unmeasured": "add one where the house would (a data page without one is warned)",
    "rare": "the house's data pages mostly carry none: keep one only where the user's data needs it (a page with one is warned)",
}


def source_line_habit(guide: dict) -> dict:
    """The house's source-line habit from the digest, with its count: `rule` (refuse a data
    page without one), `common` (warn without one), `rare` (warn WITH one: the house's
    data pages mostly carry none), or `unmeasured` (no answers, or too few data pages to
    say: warn without one, never read as 'the house carries none')."""
    lines = (guide.get("exhibit_habits") or {}).get("source_lines")
    if not isinstance(lines, dict) or lines.get("share") is None:
        return {"habit": "unmeasured", "evidence": "not measured: the guide's digest answers no source_line (re-run gallery.py digest and answer it)"}
    n, k = lines["data_pages"], lines["with_source_line"]
    if n < SOURCE_LINE_MIN_PAGES:
        return {"habit": "unmeasured", "evidence": f"{k} of {n} data pages carry one: fewer than {SOURCE_LINE_MIN_PAGES} data pages is no evidence of a habit"}
    share = lines["share"]
    habit = "rule" if share >= SOURCE_LINE_HOUSE_SHARE else "common" if share >= SOURCE_LINE_RARE else "rare"
    return {"habit": habit, "share": share, "pages_with": lines.get("pages_with"),
            "evidence": f"{k} of {n} house data pages carry one ({share:.0%}"
                        + (f": pages {', '.join(str(x) for x in lines.get('pages_with') or [])}" if 0 < k <= 5 else "")
                        + f"; the lines at {SOURCE_LINE_HOUSE_SHARE:.0%} and {SOURCE_LINE_RARE:.0%} are unmeasured)"}


def source_line_problem(elements: list[dict], guide: dict) -> dict | None:
    """The page's source line against the house's habit: a data page without one where the
    house carries them as a rule (refusal) or commonly or unmeasured (warning); a page
    with one where the house rarely carries one (warning, `source line the house rarely
    carries`). A page that does what the house mostly does is no problem."""
    page = source_line_of(elements)
    habit = source_line_habit(guide)
    if page["data_page"] and not page["source_line"] and habit["habit"] != "rare":
        refuse = habit["habit"] == "rule"
        return {"kind": "no source line", "severity": "refusal" if refuse else "warning",
                "detail": "the page carries a table or a chart and no paragraph in type.source_line or type.footnote; house: " + habit["evidence"]
                          + ("; the house carries them as a rule, so the page is refused: add one" if refuse else "; add one where the house would")}
    if page["source_line"] and habit["habit"] == "rare":
        return {"kind": "source line the house rarely carries", "severity": "warning",
                "detail": "the page carries a type.source_line or type.footnote paragraph; house: " + habit["evidence"]
                          + ". Keep it only where the user's data needs one (an illustrative-figures note the brief asks for), and say why in the report"}
    return None


def page_problems(entry: dict, elements: list[dict], resolved: dict, guide: dict, measured: list[dict] | None = None, chrome_mode: str = "auto",
                  precedent: dict | None = None) -> list[dict]:
    """The ordered problem list: tie-out warnings first (a totals row can be a subtotal
    the agent meant), then the refusals (contrast, bridge ties, the measured checks), then
    the source-line problem (source_line_habit). A refusal turns a fit
    page unfittable with the refusal's name as the reason; a page the solver already
    refused keeps the solver's reason, the first cause."""
    entry["contrast"] = contrast_of(elements, resolved, guide, chrome_mode, precedent)
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
    problems.extend(measured or [])
    entry["source_line"] = source_line_of(elements)
    found = source_line_problem(elements, guide)
    if found:
        problems.append(found)
    refusals = list(dict.fromkeys(p["kind"] for p in problems if p["severity"] == "refusal"))
    entry["solver_status"] = entry["status"]  # the geometry verdict alone; component.py's harness page reads it
    if refusals and entry["status"] == "fit":
        entry["status"], entry["reason"] = "unfittable", "; ".join(refusals)
    return problems


# --- measured fit of what the file carries --------------------------------------------------


def emitted_fit(out: str, emitted: list[dict], emit_pages: list[dict], guide: dict, ctx: L.Context) -> list[list[dict]]:
    """The written file read back and measured against the solver's boxes, per emitted
    page: every text shape through fingerprint.text_overflows in strict mode (the file's
    own sizes, breaks, pitch, spacing and marL, at the width the solver wrapped at), and
    every table's rows re-wrapped at the file's column widths, cell margins and run sizes
    with the fitter's own functions, summed against the table's solved box. A page the
    solver fitted but the file overflows is a defect in the path between them, and the
    page is refused by name."""
    from fingerprint import fingerprint_deck, text_overflows
    from pptx import Presentation
    from pptx.oxml.ns import qn as pqn
    prints = fingerprint_deck(out)
    slides = list(Presentation(out).slides)
    offset = len(slides) - len(emitted)
    substitutes = ((guide.get("typography") or {}).get("families") or {}).get("substitutes") or {}
    per_page: list[list[dict]] = []
    for i, page in enumerate(emit_pages):
        found: list[dict] = []
        # the solver's text elements only: chrome is drawn in the reference's own boxes
        solved = {el["id"] for el in page["elements"] if el["kind"] == "text"}
        findings, unmeasured, _ = text_overflows(prints[offset + i], strict=True, substitutes=substitutes)
        findings = [f for f in findings if f["shape"] in solved]
        unmeasured = [u for u in unmeasured if u["shape"] in solved]
        for f in findings:
            found.append({"shape": f["shape"], "detail": f"the file's text needs {f['needed_emu']} EMU in a {f['budget_emu']} EMU box"
                          + (f"; written line(s) {f['rewrapped_lines']} re-wrap at the box width" if f.get("rewrapped_lines") else "")})
        for u in unmeasured:
            found.append({"shape": u["shape"], "detail": f"not measurable from the file: {u['why']}"})
        boxes = {el["id"]: el["box"] for el in page["elements"] if el["kind"] == "table"}
        for shape in slides[offset + i].shapes:
            if not shape.has_table or shape.name not in boxes:
                continue
            total, grown = 0, []
            for ri, row in enumerate(shape.table.rows):
                counts, size_h = [], 0
                for ci, cell in enumerate(row.cells):
                    runs = [r for p in cell.text_frame.paragraphs for r in p.runs]
                    text = "".join(r.text for r in runs)
                    if not runs:
                        counts.append(1)
                        continue
                    rpr = runs[0]._r.find(pqn("a:rPr"))
                    sz = int(rpr.get("sz")) if rpr is not None and rpr.get("sz") else None
                    latin = rpr.find(pqn("a:latin")) if rpr is not None else None
                    if sz is None or latin is None:
                        found.append({"shape": shape.name, "detail": "a table run carries no size or face; nothing in the file says what it draws"})
                        continue
                    bold = rpr.get("b") == "1"
                    entry = L.TypeEntry("file", sz / 100, 0.0, 0.0, int(rpr.get("spc") or 0) / 100, 1.2, latin.get("typeface"), bold, rpr.get("i") == "1", "as_typed", 700 if bold else 400)
                    kind = L.DrawnRole(entry, ctx.face(entry).path)
                    budget = max(1, shape.table.columns[ci].width - (cell.margin_left or 0) - (cell.margin_right or 0) - ctx.ruler.fit_epsilon_emu)
                    counts.append(len(L.wrapped_lines(ctx, text, budget, kind)))
                    size_h = max(size_h, sz)
                margins = (row.cells[0].margin_top or 0) + (row.cells[0].margin_bottom or 0)
                drawn = max(counts, default=1) * L.required_line_box_emu(size_h, None) + margins
                if drawn > int(row.height):
                    grown.append(f"row {ri} wraps to {max(counts)} line(s) and draws {drawn} EMU over its written {int(row.height)}")
                total += max(int(row.height), drawn)
            if total > boxes[shape.name][3] + L.EMIT_SLACK_EMU:
                found.append({"shape": shape.name, "detail": f"the file's rows draw {total} EMU in the table's {boxes[shape.name][3]} EMU box" + (f" ({'; '.join(grown[:3])})" if grown else "")})
        per_page.append(found)
    return per_page


_NUMBER_FORMAT = re.compile(r'^(?P<pre>(?:"[^"]*")*)(?P<int>[#,]*0)(?:\.(?P<dec>0+))?(?P<pct>%?)(?P<post>(?:"[^"]*"|x|%)*)$')


def label_text(value: float, number_format: str | None) -> str | None:
    """A value label as the file's number format writes it, for the formats the chart
    recipes use (0, 0.0, #,##0, 0%, quoted literals); None for anything else, which the
    check reports as unmeasured rather than guess."""
    if number_format in (None, "General"):
        return f"{value:g}"
    m = _NUMBER_FORMAT.match(number_format)
    if not m:
        return None
    v = value * (100 if m["pct"] else 1)
    body = f"{v:{',' if ',' in m['int'] else ''}.{len(m['dec'] or '')}f}"
    lit = lambda part: re.sub(r'"([^"]*)"', r"\1", part or "")  # noqa: E731
    return lit(m["pre"]) + body + m["pct"] + lit(m["post"])


def label_overflows_bar(el: dict, item: dict, spec: dict) -> list[int]:
    """The points whose label, set on its column's fill, is taller than the column's
    segment along the value axis (horizontal bars are not measured here): one line of the
    label's role at its size (1.2 x size, PowerPoint's single line) against the segment
    chart_geometry computes. Empty when the chart's geometry is not computable (no
    plot_area or no axis range): nothing is claimed then."""
    from chart_geometry import ChartGeometry, GeometryRefused
    size_pt = float(spec.get("size_pt") or 0)
    if not size_pt or not str(el.get("type", "")).startswith("COLUMN_"):
        return []
    try:
        geo = ChartGeometry(el, el["box"])
        if geo.series_family(item["series"]) not in ("bar", "bar_stacked"):
            return []
        line = size_pt * L.POWERPOINT_LINE_HEIGHT_RATIO * L.EMU_PER_POINT
        return [i for i in item["points"] if geo.bar_rect(item["series"], i)[3] < line]
    except GeometryRefused:
        return []


def chart_label_breaks(elements: list[dict], ctx: L.Context) -> tuple[list[dict], list[dict]]:
    """Chart text a renderer must break between characters, measured with the solver's
    ruler and faces at the size the emitter writes (the guide role, scale 1). A bar or
    column chart's category slot is at most the chart box's extent along the category
    axis over the category count; a column chart's tick label wraps to its slot, and a
    centred data label wraps to the bar's thickness, at most the slot less the gap
    (gap_width, else none) and, clustered, shared by the series (overlap, else full).
    Both are upper bounds, since the plot is smaller than the box: a word wider than the
    bound breaks for certain, one under it may still break. Observed in LibreOffice
    renders: a centred label wraps to the bar's thickness on a horizontal bar too (bain
    build 3: 'Remaini / ng' in a bar 0.75 in tall), while an inside_base label wider
    than its 0.47 in bar stayed on one line (bain page 5), so only centred labels are
    held to the thickness. Returns (findings, unmeasured)."""
    findings: list[dict] = []
    unmeasured: list[dict] = []
    for el in elements:
        if el["kind"] != "chart" or not str(el.get("type", "")).startswith(("COLUMN_", "BAR_")):
            continue
        cats = el.get("categories") or []
        if not cats:
            continue
        horizontal = str(el["type"]).startswith("BAR_")
        extent = el["box"][3] if horizontal else el["box"][2]
        pr = plot_rect(el, el["box"])
        if pr is not None:
            # a fixed plot rectangle is the categories' own extent, not the frame's
            extent = pr[3] if horizontal else pr[2]
        slot = extent / len(cats)
        # gap and overlap at their thickest when left out: an upper bound
        # the chart type's own plot group (a combo's other series are another group)
        own = [x for x in el["series"] if x.get("plot_type", el["type"]) == el["type"] and x.get("axis", "primary") == "primary"] or el["series"]
        bar = bar_thickness(slot, el["type"], len(own), float(el.get("gap_width", 0)), float(el.get("overlap", 100)))

        def words_over(text: str, role: str | None, limit: float, part: str) -> None:
            role = role or (el.get("text") or {}).get("role")
            if not role:
                unmeasured.append({"chart": el["id"], "part": part, "why": "no type role: the theme sets the size"})
                return
            entry = L.resolve_type_entry(ctx.guide, role, L.Fraction(1))
            face = ctx.face(entry)
            for word in str(text).split():
                width = L.advance_emu(ctx.ruler, word, face.path, entry.size_pt)
                if width > limit:
                    findings.append({"chart": el["id"], "part": part, "word": word, "width_emu": width, "limit_emu": round(limit), "size_pt": entry.size_pt})

        cat_axis = (el.get("axes") or {}).get("category") or {}
        if not horizontal and cat_axis.get("visible", True) and (cat_axis.get("labels") or {}).get("show", True):
            for c in cats:
                words_over(c, (cat_axis.get("labels") or {}).get("role"), slot, f"category {c!r}")
        for si, s in enumerate(el["series"]):
            if s.get("plot_type", el["type"]) != el["type"]:
                continue  # a combo's line or area series: its labels are not in a bar
            labels = s.get("labels") or {}
            points = {p["index"]: p for p in s.get("points") or []}
            for pi, value in enumerate(s["values"]):
                own = points.get(pi, {}).get("label")
                merged = {**labels, **(own or {})}
                shown = merged.get("show", True) if own is not None else bool(labels) and labels.get("show", True)
                if not shown or merged.get("position") != "center":
                    continue
                text = merged.get("text")
                if text is None:
                    text = label_text(float(value), merged.get("number_format") or s.get("number_format") or el.get("number_format"))
                if text is None:
                    unmeasured.append({"chart": el["id"], "part": f"series[{si}] point {pi} label", "why": f"number format {merged.get('number_format')!r} not read here"})
                    continue
                words_over(text, merged.get("role"), bar, f"series[{si}] {s.get('name')!r} point {pi} label")
    return findings, unmeasured


def title_node(spec_raw: dict) -> dict | None:
    """The page title by position: the first text element, in reading order (depth first,
    so a title inside a region counts), whose first paragraph is set in type.title. The
    title report and the title-lines reason read this; the title band holds it only when it
    is the root's first child (banded_title)."""
    def walk(node: dict) -> dict | None:
        if node.get("kind") == "text" and (node.get("paragraphs") or [{}])[0].get("role") == "type.title":
            return node
        for child in node.get("children") or []:
            found = walk(child)
            if found is not None:
                return found
        return None
    return walk(spec_raw.get("root") or {})


def banded_title(spec_raw: dict) -> dict | None:
    """title_node when it is the root's first child: the one place the title band applies."""
    node = title_node(spec_raw)
    children = (spec_raw.get("root") or {}).get("children") or []
    return node if node is not None and children and children[0] is node else None


def page_title_id(slide: dict, spec_raw: dict) -> str | None:
    """The element the page spec names as its title (`title.element`), else title_node's."""
    named = (slide.get("title") or {}).get("element")
    if named:
        return named
    node = title_node(spec_raw)
    return node.get("id") if node else None


#: Asserted, unmeasured: a page whose stated register the house uses on fewer than this
#: share of its titles is warned. No measurement says where a register becomes foreign.
RARE_REGISTER_SHARE = 0.10


def title_report(slide: dict, spec_raw: dict, elements: list[dict], entry: dict, guide: dict) -> tuple[dict, list[dict]]:
    """The page title against the house's titles (guide.titles): characters, words and the
    solver's lines against the house distribution (above the house max warns), and the
    register the page spec states (`slide.title.register`) against the house's register
    counts (a register on under RARE_REGISTER_SHARE of the house's titles warns). The
    register is never read from the words here: the spec states it, or it is reported as
    not stated. Absence of house evidence is reported as such, never as zero."""
    tid = page_title_id(slide, spec_raw)
    named = (slide.get("title") or {}).get("element")
    stated = (slide.get("title") or {}).get("register")
    vocab = json.loads((Path(__file__).resolve().parent.parent / "references" / "page_craft_vocabulary.json").read_text())["title_register"]
    if stated is not None and stated not in vocab:
        raise SystemExit(f"{slide.get('id')}: title.register {stated!r} is not one of {sorted(vocab)}")
    el = next((e for e in elements if e["id"] == tid and e["kind"] == "text"), None) if tid else None
    if named and el is None:
        kinds = sorted({e["kind"] for e in elements if e["id"] == named})
        raise SystemExit(f"{slide.get('id')}: title.element {named!r} names " + (f"a {'/'.join(kinds)} element, not a text" if kinds else "no element on the page"))
    if el is None:
        return {"element": None, "register_stated": stated,
                "verdict": "no title: the page names none (title.element) and holds no text element set in type.title"}, []
    text = paragraphs_words(el["paragraphs"])
    house = guide.get("titles")
    report: dict = {"element": tid, "text": text, "register_stated": stated}
    warnings: list[dict] = []
    measured = {"chars": len(text), "words": len(text.split()), "lines": (entry.get("text_lines") or {}).get(tid)}
    if not house or not house["distribution"]["chars"]["n"]:
        report["length"] = {k: {"value": v, "verdict": "no evidence: the guide has no titles read by position"} for k, v in measured.items()}
    else:
        report["length"] = {}
        for k, v in measured.items():
            d = house["distribution"][k]
            if v is None or not d["n"]:
                verdict = "no evidence" if v is not None else "not measured"
            else:
                verdict = "above house max" if v > d["max"] else "above house p90" if v > d["p90"] else "within house p90"
            report["length"][k] = {"value": v, "house": {q: d[q] for q in ("median", "p90", "max", "n")}, "verdict": verdict}
            if verdict == "above house max":
                warnings.append({"kind": "title longer than the house", "severity": "warning",
                                 "detail": f"{tid}: {v} {k} against the house max of {d['max']} (median {d['median']}, {d['n']} titles)"})
    reg = (house or {}).get("register")
    if stated is None:
        report["register"] = {"verdict": "not stated: the page spec names no title.register"}
    elif not reg:
        report["register"] = {"verdict": "no evidence: the guide's /titles/register is not completed"}
    else:
        share = reg["counts"].get(stated, 0) / reg["n"] if reg["n"] else None
        report["register"] = {"house_counts": reg["counts"], "share": None if share is None else round(share, 3), "threshold": RARE_REGISTER_SHARE,
                              "threshold_basis": "unmeasured", "verdict": "rare in the house" if share is not None and share < RARE_REGISTER_SHARE else "house register"}
        if share is not None and share < RARE_REGISTER_SHARE:
            warnings.append({"kind": "title register rare in the house", "severity": "warning",
                             "detail": f"{tid}: a {stated} title, which the house writes on {reg['counts'].get(stated, 0)} of {reg['n']} titles "
                                       f"({json.dumps(reg['counts'])}); the {RARE_REGISTER_SHARE:.0%} line is unmeasured"})
    return report, warnings


def prepare_page(spec_raw: dict, guide: dict, chrome_mode: str = "auto") -> None:
    """The page as the build enforces it: the guide's page size, the chrome zones, the
    indent progression for a bullet-less reference, and the title band. `layout.py
    capacity` calls this too, so the budget it prints is the budget the build solves."""
    page = spec_raw.setdefault("page", {})
    page.setdefault("width_emu", guide["reference"]["page"]["width_emu"])
    page.setdefault("height_emu", guide["reference"]["page"]["height_emu"])
    if "reserved_zones" not in page:
        page["reserved_zones"] = chrome_zones(guide, chrome_mode)
    if "bullet_indent_roles" not in spec_raw and not guide.get("typography", {}).get("bullets"):
        # a reference with no bullets (a PDF, a deck of prose) gets the indent progression
        # of the spacing scale: sm, md, lg (deckgen 4b row 1: continue the indent progression)
        spec_raw["bullet_indent_roles"] = {"0": "space.sm", "1": "space.md", "2": "space.lg", "3": "space.xl"}
    band = title_band_emu(guide, spec_raw)
    root_children = spec_raw.get("root", {}).get("children", [])
    if band and banded_title(spec_raw) is not None:
        # the reference keeps its titles above the top rule: the title's box is the band
        # from the root's content top down to the rule, so whatever follows it starts
        # below the rule; a title that needs more lines than the band holds is refused
        # as overflow, never pushed under the rule
        root_children[0]["size"] = {"width_emu": None, "height_emu": band}
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


def flatten(slide: dict, resolved: dict, spec_raw: dict, guide: dict) -> list[dict]:
    """The solver's boxes and measured lines, joined with the slide's styling, charts,
    images and rules, into the emitter's flat element list."""
    styling = slide.get("styling", {})
    charts = slide.get("charts", {})
    images_ = slide.get("images", {})
    rules = slide.get("rules", {})
    rects = slide.get("rects", {})
    out = []

    def visit(node: dict) -> None:
        if node.get("type") == "region":
            st = styling.get(node["id"])
            check_presentation(node["id"], "region", st or {})
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
        check_presentation(nid, kind, {**rects.get(nid, {}), **extra})
        para_style = extra.pop("paragraphs", {})
        if kind == "text":
            measured = resolved["elements"][nid]["paragraphs"]
            paragraphs = []
            for i, (p_spec, p_meas) in enumerate(zip(node["paragraphs"], measured)):
                ps = para_style.get(str(i), {})
                para = {"role": p_spec["role"], "bullet_level": p_spec.get("bullet_level"), "lines": p_meas["lines"], "indent_emu": p_meas.get("marL", 0),
                        "fit": {k: p_meas[k] for k in FIT_KEYS},
                        "runs": ps.get("runs") or [{"text": p_spec["text"]}], "ink_role": ps.get("ink_role") or p_spec.get("ink_role"), "align": ps.get("align") or p_spec.get("align")}
                paragraphs.append(para)
            out.append({"id": nid, "kind": "text", "box": b, "paragraphs": paragraphs, **extra})
        elif kind == "table":
            t = node["table"]
            r = resolved["elements"][nid]
            # the roles the solver measured, from its own resolution, so the file sets the
            # cells in the type the fit was decided on
            roles = {"header_role": (r["header"] or r["cell"])["role"], "cell_role": r["cell"]["role"]}
            out.append({"id": nid, "kind": "table", "box": b, "columns": t["columns"], "rows": t["rows"], "header_rows": t.get("header_rows", 1),
                        "column_widths_emu": r["gridCol_w"], "row_heights_emu": r["tr_h"], **roles,
                        "fit_header": {k: r["header"][k] for k in FIT_KEYS} if r.get("header") else None, "fit_cell": {k: r["cell"][k] for k in FIT_KEYS},
                        "fit_padding_emu": r["cell_margins_emu"]["marL"], **extra})
        elif kind == "chart":
            c = charts.get(nid)
            if not c:
                raise SystemExit(f"{nid}: chart element without chart data under slide.charts")
            out.append({"id": nid, "kind": "chart", "box": b, **c, **extra})
        elif kind == "image":
            if nid in images_:
                pic = slide_picture(slide, nid, guide)
                out.append({"id": nid, "kind": "image", "box": b, **pic.emit_fields(), **extra})
                if pic.defaults_taken:
                    slide.setdefault("_image_defaults", {})[nid] = pic.defaults_taken
            elif nid in rects or extra.get("fill_role"):
                out.append({"id": nid, "kind": "rect", "box": b, **rects.get(nid, {}), **extra})
            else:
                raise SystemExit(f"{nid}: image element needs slide.images[{nid!r}] ({{\"path\": ...}} or {{\"svg\": ...}}) or a fill under slide.rects")
        elif kind == "rule":
            out.append({"id": nid, "kind": "rule", "box": b, **rules.get(nid, {}), **extra})
        else:
            raise SystemExit(f"{nid}: unknown kind {kind}")

    visit(spec_raw["root"])
    return out


def solve_slide(slide: dict, guide: dict, chrome: str, lg: L.Guide, ruler, index, api: dict, scale: L.Fraction | None = None) -> tuple[dict, L.Context, L.Outcome]:
    """One page as the build solves it: presentation keys lifted, measured weights marked,
    the page prepared (guide page size, chrome zones, title band), components probed and
    expanded at their boxes, then the scale descent; or, given `scale`, one attempt at that
    scale only. The build and `layout.py capacity` both call this, so a capacity budget is
    the page the build solves. `slide` is updated as the build updates it (styling, rects,
    spacers, component notes)."""
    spec_raw = json.loads(json.dumps(slide["spec"]))
    spec_raw["root"] = normalise(spec_raw["root"], slide)
    mark_measured_weights(spec_raw["root"], slide, guide)
    prepare_page(spec_raw, guide, chrome)
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
    mark_measured_weights(tree, slide, guide)  # a component's tables too
    spec = L.parse_spec(spec_raw)
    ctx = L.Context(lg, ruler, index, spec)
    if scale is None:
        return spec_raw, ctx, L.descend(ctx)
    attempt = L._attempt(ctx, scale)
    return spec_raw, ctx, L.Outcome("fit" if attempt.fits else "unfittable", attempt.resolved, [attempt], attempt.refusal or "violations at this scale", scale)


#: Text appended to an element to find its budget: mean-advance English with figures.
FILLER = (L.REFERENCE_ALPHABET + " ") * 200
CAPACITY_MAX_CHARS = 4000


def table_budgets(ctx, outcome) -> list[dict]:
    """Every table on the page solved at full scale: its box, the height its rows need,
    and how many body rows fit. Tables are not budgeted in characters: a table's rows are
    measured cell by cell, so its budget is rows. `rows_to_fit` is the body-row count the
    page holds at full scale with everything else as written (layout.outcome_json's
    rows_to_fit_slide: the split cut); `rows_fitting_box` counts rows that fit the table's
    own box."""
    resolved = outcome.resolved
    if resolved is None:
        return []
    split = (L.outcome_json(ctx, outcome).get("unfittable") or {}).get("tables") or {}
    out = []
    for nid, fit in resolved.table_fits.items():
        box = resolved.boxes.get(nid)
        body = len(fit.row_heights) - fit.header_rows
        tallest = sorted(range(fit.header_rows, len(fit.row_heights)), key=lambda i: -fit.row_heights[i])[:3]
        lines = {i - fit.header_rows: max(len(v) for (r, _), v in fit.cell_lines.items() if r == i) for i in tallest}
        entry = {"id": nid, "body_rows": body, "header_rows": fit.header_rows,
                 "box_in": None if box is None else [round(v / EMU_PER_INCH, 2) for v in (box.left, box.top, box.width, box.height)],
                 "rows_need_in": round(fit.total_height_emu / EMU_PER_INCH, 2),
                 "rows_fitting_box": fit.fitting_row_prefix,
                 "rows_to_fit": (split.get(nid) or {}).get("rows_to_fit_slide", body if not fit.overflow else fit.fitting_row_prefix),
                 "tallest_rows": [{"row": r, "lines": n} for r, n in lines.items()],
                 "column_deficits_in": {k: round(v / EMU_PER_INCH, 2) for k, v in fit.column_deficits.items()}}
        if box is not None and fit.total_height_emu <= box.height:
            entry["height_free_in"] = round((box.height - fit.total_height_emu) / EMU_PER_INCH, 2)
        out.append(entry)
    return out


def full_scale_cause(ctx, outcome) -> list[str]:
    """Why the page does not fit at full scale, in words: each violation the full-scale
    solve found, with its element and shortfall, and for each table what it needs against
    what it has."""
    resolved = outcome.resolved
    if resolved is None:
        return [outcome.reason or "the page does not solve at full scale"]
    causes = [f"{v.code}: {v.node_id}{' and ' + v.related_node_id if v.related_node_id else ''}"
              f"{f' short by {v.shortfall_emu / EMU_PER_INCH:.3f} in ({v.shortfall_emu} EMU)' if v.shortfall_emu else ''}: {v.detail}" for v in resolved.violations]
    over = (L.outcome_json(ctx, outcome).get("unfittable") or {}).get("overshoot_emu") or 0
    for t in table_budgets(ctx, outcome):
        if t["rows_to_fit"] < t["body_rows"]:
            causes.insert(0, f"table {t['id']}: the page is {over / EMU_PER_INCH:.2f} in over at full scale, and {t['rows_to_fit']} of its "
                             f"{t['body_rows']} body rows fit with everything else as written (rows_to_fit): cut rows, shorten the cells "
                             f"that wrap, cut other text, or split the table after row {max(0, t['rows_to_fit'] - 1)} at a declared boundary")
        if t["box_in"] and t["rows_need_in"] > t["box_in"][3]:
            causes.append(f"table {t['id']}: its {t['body_rows']} body rows need {t['rows_need_in']} in, its box is {t['box_in'][3]} in; "
                          f"{t['rows_to_fit']} body rows fit the page as written; its tallest rows wrap to "
                          + ", ".join(f"{x['lines']} lines (row {x['row']})" for x in t["tallest_rows"])
                          + ": shorten those cells, widen their columns (width_share), cut rows, or split the table at a declared boundary")
        for k, v in t["column_deficits_in"].items():
            causes.append(f"table {t['id']} column {k}: {v} in narrower than its widest word or figure")
    return causes or [outcome.reason or "unfittable at full scale"]


def capacity(slide: dict, guide: dict, chrome: str = "auto") -> dict:
    """The text budget of every text element the slide's spec names, on the page the build
    solves (solve_slide): its solved box, lines and characters now, and how many characters
    more it takes before the page stops fitting at full scale, found by solving the page
    with filler text appended to the element's last paragraph (bisection on the count;
    every probe is the build's own solve, chrome zones and title band included). A page
    that does not fit at full scale has no budget: the build would descend the scale."""
    import copy
    lg = L.load_guide(guide)
    ruler, index = L.ruler_for(guide), L.default_index()
    api = component_api.make_api(guide, lg, ruler, index)
    one = L.Fraction(1)
    base_slide = copy.deepcopy(slide)
    base_raw, _, outcome = solve_slide(base_slide, guide, chrome, lg, ruler, index, api)
    out: dict = {"id": slide.get("id"), "ruler": ruler.name, "ruler_basis": ruler_basis(guide), "status": outcome.status,
                 "scale": None if outcome.resolved is None else float(outcome.resolved.scale),
                 "reserved_zones_in": {z.get("source"): [round(z[k] / EMU_PER_INCH, 2) for k in ("left", "top", "width", "height")]
                                       for z in base_raw["page"].get("reserved_zones") or []}, "elements": []}
    if outcome.resolved is None:
        out["reason"] = outcome.reason
        return out
    _, full_ctx, full = solve_slide(copy.deepcopy(slide), guide, chrome, lg, ruler, index, api, one)
    fits_full = full.status == "fit"
    texts: list[dict] = []
    out["tables"] = table_budgets(full_ctx, full)
    if not fits_full:
        out["why_not_full_scale"] = full_scale_cause(full_ctx, full)

    def walk(node: dict, path: tuple) -> None:
        if node.get("type") == "region":
            for i, c in enumerate(node.get("children", [])):
                walk(c, path + (i,))
        elif node.get("kind") == "text" and node.get("paragraphs"):
            texts.append({"node": node, "path": path})
        elif node.get("type") == "component":
            out.setdefault("components", []).append({"id": node.get("id"), "kind": node.get("kind"),
                                                     "budget": "measured by the component itself (component_api); its box is in the build report"})

    walk(slide["spec"]["root"], ())

    def with_filler(path: tuple, n: int) -> dict:
        probe = copy.deepcopy(slide)
        node = probe["spec"]["root"]
        for i in path:
            node = node["children"][i]
        last = node["paragraphs"][-1]
        last["text"] = (last.get("text") or "") + (" " + FILLER[:n] if n else "")
        return probe

    def fits(path: tuple, n: int) -> tuple[bool, L.Outcome]:
        try:
            _, _, o = solve_slide(with_filler(path, n), guide, chrome, lg, ruler, index, api, one)
        except SystemExit:
            return False, None  # type: ignore[return-value]
        return o.status == "fit", o

    for t in texts:
        node = t["node"]
        nid = node["id"]
        box = outcome.resolved.boxes.get(nid)
        meas = outcome.resolved.measurements.get(nid) or []
        entry = {"id": nid, "role": node["paragraphs"][-1].get("role"),
                 "box_in": None if box is None else [round(v / EMU_PER_INCH, 2) for v in (box.left, box.top, box.width, box.height)],
                 "lines_now": sum(len(m.lines) for m in meas), "chars_now": sum(len(p.get("text") or "") for p in node["paragraphs"])}
        if not fits_full:
            entry["chars_free"] = 0
            entry["why"] = (f"the page fits only at scale {out['scale']}: it is already over its full-scale budget; see why_not_full_scale"
                            if outcome.status == "fit" else "the page does not fit: see why_not_full_scale")
            out["elements"].append(entry)
            continue
        lo, hi, best = 0, 64, full
        while hi <= CAPACITY_MAX_CHARS:
            ok, o = fits(t["path"], hi)
            if not ok:
                break
            lo, best, hi = hi, o, hi * 2
        else:
            hi = CAPACITY_MAX_CHARS + 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            ok, o = fits(t["path"], mid)
            if ok:
                lo, best = mid, o
            else:
                hi = mid
        at = best.resolved.measurements.get(nid) or [] if best and best.resolved else []
        entry["chars_free"] = lo if lo < CAPACITY_MAX_CHARS else f">= {CAPACITY_MAX_CHARS}"
        entry["lines_at_budget"] = sum(len(m.lines) for m in at)
        entry["lines_free"] = entry["lines_at_budget"] - entry["lines_now"]
        out["elements"].append(entry)
    out["method"] = ("each element's chars_free: the most characters of mean-advance filler (English words and figures) appended to its "
                     "last paragraph with the page still fitting at full scale, every other element unchanged; budgets do not add up "
                     "across elements that share free space")
    return out


def leakage_of(out: str, reference: str | None, house_decks: list[dict], briefs: list[str], template: str, ids: list, computed: list[str] | None = None,
               furniture: list[str] | None = None) -> dict:
    """leakage.py on the written deck against the past decks this build was given: the
    reference, and each house deck's own file when it is found with its recorded sha256.
    A past deck that cannot be read is named, never taken as clean."""
    import hashlib
    import leakage
    past, unread = [], []
    if reference:
        past.append(reference)
    for g in house_decks:
        ref = g.get("reference") or {}
        path = Path(ref.get("file") or "")
        if ref.get("file") and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == ref.get("sha256"):
            past.append(str(path))
        else:
            unread.append(f"{ref.get('file')}: not found with the guide's sha256, so not compared")
    if not past:
        return {"verdict": "not checked: no past deck given (--reference, --house-deck)", "unread": unread}
    return {**leakage.leakage(out, past, briefs, template, ids, computed, furniture), **({"unread": unread} if unread else {})}


def plan_message_figures(slide: dict, elements: list[dict], plan_pages: list[dict] | None) -> list[dict]:
    """A figure the plan's message for this page states that the built page does not
    carry: the plan was written before the numbers moved, or the page dropped its claim.
    A warning, located: the plan or the page is changed, whichever is wrong."""
    import leakage
    page = next((p for p in plan_pages or [] if p.get("id") == slide.get("id")), None)
    if not page or not page.get("message"):
        return []
    drawn = " ".join(r.get("text", "") for el in elements if el.get("kind") == "text" for p in el.get("paragraphs", []) for r in p.get("runs", []))
    drawn += " " + " ".join(str(c) for el in elements if el.get("kind") == "table" for row in el.get("rows", []) for c in row)
    drawn += " " + " ".join(f"{v}" for el in elements if el.get("kind") == "chart" for s in el.get("series") or [] for v in s.get("values") or []
                            if isinstance(v, int | float) and not isinstance(v, bool))
    have = {leakage.norm(w) for w in leakage.tokens(drawn)}
    # the same figure spelt another way ($21.50 and 21.50, 1.7x and 1.7) is on the page
    values = {v for v in (leakage._figure_value(w) for w in leakage.tokens(drawn)) if v is not None}
    missing = [w for w in leakage.tokens(page["message"]) if leakage._FIGURE.search(w) and leakage.norm(w) not in have
               and leakage._figure_value(w) not in values]
    return [{"kind": "plan figure not on the page", "severity": "warning",
             "detail": f"the plan's message for {slide.get('id')!r} states {missing}, which the page does not carry; update the plan's message "
                       "to the computed figure, or put the claim on the page"}] if missing else []


def passed(report: dict) -> bool:
    """The build's verdict, the one definition: every page fit and the package is valid.
    The exit code, the brief and where the outputs land all read it."""
    return bool(report.get("slides")) and all(s.get("status") == "fit" for s in report["slides"]) and bool((report.get("validation") or {}).get("ok"))


class Outputs:
    """Where a build writes, so that only a passing build leaves files that look current.
    The deck and its renders are made at staging paths beside the asked-for ones and moved
    to them only when the build passes. A refused build's deck and renders land beside
    them as <stem>.refused.pptx and <renders>.refused; a deck and renders an earlier build
    left at the asked-for paths no longer match the spec, so they are moved aside to
    <stem>.stale.pptx and <renders>.stale. The report (<stem>.build.json) is always this
    build's, refused or not, and names every path it wrote or moved."""

    def __init__(self, out: str, renders: str | None, do_render: bool) -> None:
        self.out = Path(out)
        self.renders = (Path(renders) if renders else self.out.with_name(self.out.stem + "-renders")) if do_render else None
        self.stage_out = self.out.with_name(f".{self.out.stem}.building{self.out.suffix}")
        self.stage_renders = self.renders.with_name(f".{self.renders.name}.building") if self.renders else None
        self.report_path = self.out.with_suffix(".build.json")

    @staticmethod
    def _beside(path: Path, tag: str) -> Path:
        return path.with_name(f"{path.stem}.{tag}{path.suffix}") if path.suffix else path.with_name(f"{path.name}.{tag}")

    @staticmethod
    def _move(src: Path, dst: Path) -> None:
        import shutil
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))

    def start(self) -> None:
        import shutil
        self.out.parent.mkdir(parents=True, exist_ok=True)
        if self.stage_out.exists():
            self.stage_out.unlink()
        if self.stage_renders and self.stage_renders.exists():
            shutil.rmtree(self.stage_renders)

    def _set_aside_earlier(self) -> list[str]:
        moved = []
        for path in (self.out, self.renders):
            if path is not None and path.exists():
                stale = self._beside(path, "stale")
                self._move(path, stale)
                moved.append(f"{path} -> {stale}: an earlier build's output, which does not match this spec")
        return moved

    def finish(self, ok: bool) -> dict:
        """Move the staged files to where they belong for this verdict."""
        import shutil
        written: dict = {"verdict": "built" if ok else "refused", "moved_aside": []}
        pairs = [(self.stage_out, self.out)] + ([(self.stage_renders, self.renders)] if self.renders else [])
        if ok:
            for path in (self.out, self.renders):
                refused = self._beside(path, "refused") if path is not None else None
                if refused is not None and refused.exists():
                    shutil.rmtree(refused) if refused.is_dir() else refused.unlink()
            for src, dst in pairs:
                if src.exists():
                    self._move(src, dst)
            written["deck"], written["renders"] = str(self.out), str(self.renders) if self.renders else None
        else:
            written["moved_aside"] = self._set_aside_earlier()
            for src, dst in pairs:
                if src.exists():
                    self._move(src, self._beside(dst, "refused"))
            written["deck"] = str(self._beside(self.out, "refused")) if self._beside(self.out, "refused").exists() else None
            written["renders"] = str(self._beside(self.renders, "refused")) if self.renders and self._beside(self.renders, "refused").exists() else None
            written["note"] = ("refused: the deck and renders of this build are written as .refused beside the asked-for paths, for diagnosis; "
                               "nothing at the asked-for paths is current")
        return written

    def refuse_early(self, message: str) -> None:
        """A refusal before anything was written: the report says so, and an earlier
        build's deck and renders at these paths are moved aside."""
        import shutil
        if self.stage_out.exists():
            self.stage_out.unlink()
        if self.stage_renders and self.stage_renders.exists():
            shutil.rmtree(self.stage_renders)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        report = {"outputs": {"verdict": "refused before building", "refusal": message, "deck": None, "renders": None,
                              "moved_aside": self._set_aside_earlier()}}
        self.report_path.write_text(json.dumps(report, indent=1))

    def rewrite(self, report: dict, written: dict) -> dict:
        """The report with the staging paths replaced by where the files now are."""
        text = json.dumps(report, default=str)
        for stage, final in ((self.stage_out, written.get("deck")), (self.stage_renders, written.get("renders"))):
            if stage is not None:
                text = text.replace(json.dumps(str(stage))[1:-1], json.dumps(final or "")[1:-1] if final else "(not kept)")
        return json.loads(text)


def build(deck: dict, guide: dict, template: str, out: str, reference: str | None, others: list[str], renders: str | None, do_render: bool, chrome: str = "auto",
          plan_pages: list[dict] | None = None, house_decks: list[dict] | None = None, house_names: list[str] | None = None,
          plan_check: dict | None = None, briefs: list[str] | None = None, outputs: Outputs | None = None, computed: list[str] | None = None) -> dict:
    outputs = outputs or Outputs(out, renders, do_render)
    outputs.start()  # before the solve: a missing -o directory otherwise fails only at the save
    out = str(outputs.stage_out)
    lg = L.load_guide(guide)
    ruler = L.ruler_for(guide)
    index = L.default_index()
    api = component_api.make_api(guide, lg, ruler, index)
    emit_spec: dict = {"slides": [], **({"firm_chrome": deck["firm_chrome"]} if "firm_chrome" in deck else {})}
    report = {"out": out, "ruler": ruler.name, "ruler_basis": ruler_basis(guide), "slides": []}
    ref_slides = None
    precedent = None
    if reference:
        from ooxml import fingerprint_deck, ink_backings
        ref_slides = fingerprint_deck(reference)
        precedent = ink_backings(ref_slides)
    pages: list[tuple[int, list[dict]]] = []  # (deck page number, flattened elements) of every emitted page
    emitted: list[dict] = []  # the report entry of every emitted page, in emit order
    annotation_pages: dict[int, list[dict]] = {}  # emitted page index -> its annotations as resolved
    for number, slide in enumerate(deck["slides"], 1):
        try:
            spec_raw, ctx, outcome = solve_slide(slide, guide, chrome, lg, ruler, index, api)
            entry = {"id": slide.get("id"), "status": outcome.status, "attempts": [a.summary() for a in outcome.attempts]}
            if slide.get("component_notes"):
                entry["component_notes"] = sorted(set(slide["component_notes"]))
            # a table choice the spec left out, as the chart's are listed: the weight of an emphasis group
            taken = {tid: [f"emphasis[{i}].bold: true (left out, emphasised cells are bold)" for i, g in enumerate(st["emphasis"])
                           if isinstance(g, dict) and "bold" not in g]
                     for tid, st in (slide.get("styling") or {}).items() if isinstance(st, dict) and isinstance(st.get("emphasis"), list)}
            for tid in spanned_tables(slide["spec"]["root"]):
                st = (slide.get("styling") or {}).get(tid) or {}
                if not st.get("spanner_align") and not st.get("header_align"):
                    taken.setdefault(tid, []).append("spanner_align: each spanner takes its first column's alignment (left out)")
            if any(taken.values()):
                entry["table_defaults_taken"] = {k: v for k, v in taken.items() if v}
            if outcome.resolved is None:
                entry["reason"] = outcome.reason
                entry["unfittable"] = L.outcome_json(ctx, outcome).get("unfittable")
                report["slides"].append(entry)
                continue
            banded = banded_title(spec_raw)
            title_rows = outcome.resolved.measurements.get(banded.get("id") or "", []) if banded else []
            title_over = banded is not None and any(v.code == "overflow" and v.node_id == banded.get("id") for v in outcome.resolved.violations)
            if outcome.status != "fit" and title_over and title_rows:
                # the first cause named first: the title's box is the band above the top rule
                band = title_band_emu(guide, spec_raw) or 0
                pitch = max(1, title_rows[0].entry.pitch_emu)
                entry["reason"] = (f"title needs {sum(len(m.lines) for m in title_rows)} lines; the band above the top rule "
                                   f"({band / EMU_PER_INCH:.2f} in) holds {band // pitch} at {title_rows[0].entry.size_pt}pt. Shorten the title before anything else.")
            elif outcome.status != "fit":
                # the brief names the cause on the page's own line, not only in the JSON
                causes = full_scale_cause(ctx, outcome)
                entry["reason"] = causes[0] + (f" (and {len(causes) - 1} more under slides[].violations)" if len(causes) > 1 else "")
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
            elements = flatten(slide, resolved, spec_raw, guide)
            if slide.get("_image_defaults"):
                entry["image_defaults_taken"] = slide["_image_defaults"]
            annotation_problems: list[dict] = []
            if slide.get("annotations") is not None:
                # resolved on the solved page: anchored to the hosts' boxes, measured at the page's scale
                planned = next((p for p in plan_pages or [] if p.get("id") == slide.get("id")), None)
                elements, placed, annotation_problems = annotate.resolve(slide["annotations"], elements, ctx, outcome.resolved.scale, guide,
                                                                         spec_raw["page"].get("reserved_zones") or [],
                                                                         list(planned["exhibit_types"]) if planned else None)
                entry["annotations"] = placed
            entry["density"] = density_of(elements, resolved, guide, spec_raw)
            breaks, unread = chart_label_breaks(elements, ctx)
            if breaks or unread:
                entry["chart_label_breaks"] = {"findings": breaks, "unmeasured": unread}
            entry["problems"] = page_problems(entry, elements, resolved, guide, annotation_problems + [
                {"kind": "chart label breaks mid-word", "severity": "refusal",
                 "detail": f"{b['chart']} {b['part']}: {b['word']!r} at {b['size_pt']}pt measures {b['width_emu']} EMU, wider than the {b['limit_emu']} EMU it wraps to at most"}
                for b in breaks], chrome, precedent)
            entry["title"], title_warnings = title_report(slide, spec_raw, elements, entry, guide)
            entry["problems"][:0] = title_warnings + plan_message_figures(slide, elements, plan_pages)  # warnings first, as the tie-outs are
        except L.FaceRefused as error:
            # the guide's faces cannot measure this page as the renderer draws it: the page is
            # refused by name in the report, not solved in another face and not a traceback
            report["slides"].append({"id": slide.get("id"), "status": "unfittable", "solver_status": None, "reason": "font refused",
                                     "problems": [{"kind": "font refused", "severity": "refusal", "detail": str(error)}]})
            continue
        pages.append((number, elements))
        emit_spec["slides"].append({"layout": slide.get("layout"), "notes": slide.get("notes"), "elements": elements})
        report["slides"].append(entry)
        if "annotations" in entry:
            annotation_pages[len(emitted)] = entry["annotations"]
        emitted.append(entry)
    sourced = [(e["id"], e["source_line"]) for e in emitted if "source_line" in e]
    report["source_lines"] = {"house": source_line_habit(guide),
                              "deck": {"data_pages": sum(1 for _, s in sourced if s["data_page"]),
                                       "with_source_line": [i for i, s in sourced if s["source_line"]],
                                       "data_pages_without": [i for i, s in sourced if s["data_page"] and not s["source_line"]]}}
    report["position_drift"] = position_drift(pages, guide)
    report["repetition"] = repetition_of(pages, guide, plan_pages, house_decks, {n: deck["slides"][n - 1].get("id") for n, _ in pages},
                                         {n: realised_classes(deck["slides"][n - 1]["spec"]["root"]) for n, _ in pages}, house_names, plan_check)
    emit_report = emit_slides(emit_spec, template, guide, out, chrome)
    report["emitted_slides"] = len(emit_report["slides"])
    # the file as written, measured against the boxes it was solved for
    for entry, found in zip(emitted, emitted_fit(out, emitted, emit_spec["slides"], guide, L.Context(lg, ruler, index))):
        if not found:
            continue
        entry["problems"].extend({"kind": "emitted text overflows", "severity": "refusal", "detail": f"{f['shape']}: {f['detail']}"} for f in found)
        if entry["status"] == "fit":
            entry["status"], entry["reason"] = "unfittable", "emitted text overflows"
    report["chrome"] = {**emit_report["chrome"], "drawn": [page["chrome_drawn"] for page in emit_report["slides"]]}
    for entry, page in zip(emitted, emit_report["slides"]):
        if page.get("charts"):
            # every chart choice the spec left out, with the value written for it
            entry["chart_defaults_taken"] = {c["id"]: c["defaults_taken"] for c in page["charts"]}
    from pptx_tools import validate
    report["validation"] = validate(out, render=False)
    # the chrome the build drew is the house's furniture, as the template's own text is: on a
    # raster reference the past deck's copy of it is OCR text and never reads as chrome there
    furniture = [t for t in (chrome_text(ch) for ch in chrome_on_page(guide, chrome)) if t]
    report["leakage"] = leakage_of(out, reference, house_decks or [], briefs or [], template, [e.get("id") for e in emitted], computed, furniture)
    if do_render:
        import subprocess
        rdir = str(outputs.stage_renders)
        pdf = str(Path(rdir) / "deck.pdf")
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name("render.py")), out, "--out", rdir, "--width", "1600", "--keep-pdf", pdf],
                                   capture_output=True, text=True, timeout=900)
        try:
            report["renders"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            report["renders"] = {"error": completed.stderr[-500:]}
        unread = None
        words: list = []
        if annotation_pages:
            try:
                if not Path(pdf).exists():
                    raise annotate.RenderUnread("the render wrote no PDF")
                words = annotate.pdf_words(pdf)
                if len(words) < len(emitted):
                    raise annotate.RenderUnread(f"the PDF has {len(words)} page(s) for {len(emitted)} emitted page(s)")
            except annotate.RenderUnread as error:
                unread = str(error)
        if unread is not None:
            # asked for and not done: the words the host draws are unknown, so the page is
            # not passed as if they had been read
            for index, placed in annotation_pages.items():
                entry = emitted[index]
                for e in placed:
                    if e.get("status") == "placed":
                        e["render_check"] = f"not checked: the render's words were not read ({unread})"
                entry["problems"].append({"kind": "annotation render check failed", "severity": "refusal", "detail": f"the words the host drew were not read: {unread}"})
                if entry["status"] == "fit":
                    entry["status"], entry["reason"] = "unfittable", "annotation render check failed"
        elif annotation_pages:
            # the emitted pages are the PDF's last pages, as emitted_fit reads the file
            offset = len(words) - len(emitted)
            for index, placed in annotation_pages.items():
                found = annotate.render_check(placed, emit_spec["slides"][index]["elements"], words[offset + index])
                entry = emitted[index]
                entry["problems"].extend(found)
                if found and entry["status"] == "fit":
                    entry["status"], entry["reason"] = "unfittable", "annotation covers chart text"
    picture_pages = {i: [el for el in page["elements"] if el.get("kind") == "image" and (el.get("path") or el.get("svg_source"))]
                     for i, page in enumerate(emit_spec["slides"])}
    picture_pages = {i: els for i, els in picture_pages.items() if els}
    if picture_pages:
        pngs = (report.get("renders") or {}).get("images") or [] if do_render else []
        for index, els in picture_pages.items():
            entry = emitted[index]
            png_index = len(pngs) - len(emitted) + index
            if not do_render:
                entry["pictures"] = [{"id": el["id"], "status": "not checked: --no-render"} for el in els]
                continue
            if not 0 <= png_index < len(pngs) or not Path(pngs[png_index]).exists():
                entry["pictures"] = [{"id": el["id"], "status": "not checked: the render wrote no page image"} for el in els]
                entry["problems"].append({"kind": "picture render check failed", "severity": "refusal", "detail": "the render wrote no page image, so whether each picture was drawn is unknown"})
                if entry["status"] == "fit":
                    entry["status"], entry["reason"] = "unfittable", "picture render check failed"
                continue
            found = images.render_check(els, pngs[png_index], guide["reference"]["page"]["width_emu"], guide)
            entry["pictures"] = found
            bad = [f for f in found if f["status"] == "not drawn as written"]
            for f in bad:
                entry["problems"].append({"kind": "picture not drawn as written", "severity": "refusal",
                                          "detail": f"{f['id']}: {f['differ_share']:.1%} of its box's pixels differ from the picture as written (at most {images.RENDER_TOLERANCE:.0%})"})
            small = [f for f in found if f["status"] == "too small to check"]
            for f in small:
                w, h = f["box_px"][2], f["box_px"][3]
                entry["problems"].append({"kind": "picture too small to check", "severity": "refusal",
                                          "detail": f"{f['id']}: drawn {w} x {h} px on the render, under {images.MIN_CHECK_PX} px on a side; at its aspect it does not show in its box (give it a box it shows in)"})
            if (bad or small) and entry["status"] == "fit":
                entry["status"], entry["reason"] = "unfittable", "picture not drawn as written" if bad else "picture too small to check"
    for placed in annotation_pages.values():
        for e in placed:
            if e.get("status") == "placed" and "render_check" not in e:
                e["render_check"] = "not checked: --no-render, so the words the host draws are unknown"
            for k in [k for k in e if k.startswith("_")]:
                e.pop(k)
    if reference:
        from fingerprint import judge as judge_style
        judge = judge_style(out, reference, others, ref_slides=ref_slides)
        # the judge reads style; fit is the solver's verdict and validity the package's. A
        # page is filed under the house only when all three hold, and never when the judge
        # could not read the reference.
        all_fit = all(sl.get("status") == "fit" and not sl.get("violations") for sl in report["slides"])
        judge["filed_under_reference"] = None if "cannot_judge" in judge else (
            bool(judge["nearest_is_reference"]) and bool(judge["within_house_spread"]) and judge["layout_clean"]
            and all_fit and bool(report.get("validation", {}).get("ok")))
        report["judge"] = judge
    written = outputs.finish(passed(report))
    report = outputs.rewrite(report, written)
    report["out"] = written["deck"]
    report["outputs"] = written
    outputs.report_path.write_text(json.dumps(report, indent=1, default=str))
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
    ap.add_argument("--plan", default=None, help="the section plan (plan.py): realised compositions are compared with the planned ones")
    ap.add_argument("--house-deck", action="append", default=[], help="another guide of the same house, pooled into the house's variety")
    ap.add_argument("--brief", action="append", default=[], help="the user's brief or data as a text file; the leakage report allows its words")
    ap.add_argument("--computed", action="append", default=[], help="figures your own arithmetic produced from the user's data, as text; "
                    "a past deck's figure that matches one is listed under leakage.declared_computed instead of as distinctive")
    args = ap.parse_args(argv)
    import cli
    cli.guard_args(args, "out", "renders")
    outputs = Outputs(args.out, args.renders, not args.no_render)
    try:
        report = _run(args, outputs)
    except (SystemExit, L.LayoutContractError) as error:
        message = str(error.code if isinstance(error, SystemExit) else error)
        if isinstance(error, SystemExit) and (error.code is None or isinstance(error.code, int)):
            raise
        outputs.refuse_early(message)
        raise SystemExit(f"refused before building: {message}\nreport: {outputs.report_path}") from None
    print(brief_text(report, outputs))
    return 0 if passed(report) else 1


def _run(args, outputs: Outputs) -> dict:
    for name in ("deck", "guide", "template", "plan", "reference"):
        value = getattr(args, name, None)
        if value is not None:
            import cli
            cli.in_path(value, f"--{name}" if name != "deck" else "the deck spec")
    for name in ("brief", "computed", "house_deck"):
        for value in getattr(args, name, None) or []:
            import cli
            cli.in_path(value, f"--{name.replace('_', '-')}")
    deck = json.loads(Path(args.deck).read_text())
    guide = json.loads(Path(args.guide).read_text())
    plan_pages = None
    plan_check = None
    house_decks = [json.loads(Path(p).read_text()) for p in args.house_deck]
    house_names = [f"--guide {args.guide}", *(f"--house-deck {p}" for p in args.house_deck)]
    if args.plan:
        # the plan gate is plan.py check's, whole: a plan it refuses is not built
        plan_json = json.loads(Path(args.plan).read_text())
        plan_check = plan.check(plan_json, guide, house_decks, house_names)
        if plan_check["status"] != "pass":
            raise plan.Refused(f"--plan: plan.py check refuses {args.plan}: " + "; ".join(plan_check["refusals"]))
        plan_pages = plan.read_plan(plan_json, guide)
        planned, built = [p["id"] for p in plan_pages], [s.get("id") for s in deck["slides"]]
        # a deck may build the whole plan or one contiguous run of it (one page while you
        # work on it): adjacent built pages are then adjacent planned pages, so the
        # plan-against-build comparison reads the same pairs the plan declared
        start = next((i for i in range(len(planned) - len(built) + 1) if planned[i:i + len(built)] == built), None) if built else None
        if start is None:
            raise plan.Refused(f"--plan: the deck's slide ids {built} are not the plan's page ids {planned} or one contiguous run of them, "
                               f"in order. Build the whole section, or a deck holding only consecutive planned pages (one page: a deck of "
                               f"that one slide), with each slide's id equal to its page id")
        plan_check["subset"] = None if len(built) == len(planned) else {
            "built": built, "of": planned,
            "note": "a run of the plan: the plan check covers the whole plan, the realised variety covers only the pages built"}
    else:
        plan.house_of([guide, *house_decks], house_names)  # the house decks proven before the solve, not after it
    return build(deck, guide, args.template, args.out, args.reference, args.others, args.renders, not args.no_render, args.chrome, plan_pages, house_decks,
                 house_names, plan_check, args.brief, outputs, args.computed)


def brief_text(report: dict, outputs: Outputs) -> str:
    """The build in a few lines: the verdict, where everything is, each page's status and
    first problems, and one line per gate. The whole report is the JSON file."""
    slides = report.get("slides") or []
    ok = passed(report)
    unfit = [s for s in slides if s.get("status") != "fit"]
    written = report.get("outputs") or {}
    lines = [(f"build: {'PASS' if ok else 'REFUSED'}: {len(slides) - len(unfit)} of {len(slides)} page(s) fit; package "
              f"{'valid' if (report.get('validation') or {}).get('ok') else 'NOT valid: ' + '; '.join(map(str, (report.get('validation') or {}).get('problems') or []))[:300]}"),
             f"report: {outputs.report_path}  (read it for every figure; this is a brief)",
             f"deck: {written.get('deck')}" + (f"  renders: {written.get('renders')}" if written.get("renders") else "")]
    if written.get("note"):
        lines.append(f"note: {written['note']}")
    lines += [f"moved aside: {m}" for m in written.get("moved_aside") or []]
    lines.append(f"ruler: {report.get('ruler')} ({report.get('ruler_basis')})")
    for s in slides:
        problems = s.get("problems") or []
        refusals = [p for p in problems if p.get("severity") == "refusal"]
        warns = [p for p in problems if p.get("severity") != "refusal"]
        scale = f" scale {s['scale']:.2f}" if isinstance(s.get("scale"), float) else ""
        lines.append(f"page {s.get('id')}: {s.get('status')}{scale}" + (f" ({s['reason']})" if s.get("reason") else "")
                     + (f"; {len(refusals)} refusal(s), {len(warns)} warning(s)" if problems else ""))
        for p in (refusals + warns)[:4]:
            lines.append(f"  {p.get('severity', 'note')}: {p.get('kind')}: {str(p.get('detail', ''))[:240]}")
        if len(problems) > 4:
            lines.append(f"  ... {len(problems) - 4} more in the report (slides[].problems)")
        taken = sum(len(v) for v in (s.get("chart_defaults_taken") or {}).values())
        if taken:
            lines.append(f"  chart defaults taken: {taken} (slides[].chart_defaults_taken): write each choice you mean")
    rep = report.get("repetition") or {}
    ah = rep.get("against_house") or {}
    if isinstance(ah.get("composition_V"), dict):
        cv, kv = ah["composition_V"], ah.get("classes_V") or {}
        lines.append(f"variety: composition V {cv.get('value')} (house p10 {cv.get('house_p10_deck')}), class V {kv.get('value')} "
                     f"(house p10 {kv.get('house_p10_deck')}), longest run {(ah.get('longest_run') or {}).get('built')} "
                     f"(house {(ah.get('longest_run') or {}).get('house')})")
    lines += [f"  variety warning: {w}" for w in rep.get("warnings") or []]
    differing = ((rep.get("plan") or {}) if isinstance(rep.get("plan"), dict) else {}).get("pages_differing_from_plan") or []
    lines += [f"  differs from plan: {d.get('id')}: {d.get('detail')}" for d in differing]
    src = report.get("source_lines") or {}
    if src:
        deck_src = src["deck"]
        lines.append(f"source lines: house {src['house']['habit']}: {src['house']['evidence']}; this deck: {len(deck_src['with_source_line'])} page(s) carry one "
                     f"({', '.join(map(str, deck_src['with_source_line'])) or 'none'}), {deck_src['data_pages']} data page(s)")
    leak = report.get("leakage") or {}
    if leak:
        lines.append(f"leakage: {leak.get('verdict')}" + (f"; {leak.get('distinctive', leak.get('findings'))} distinctive, {leak.get('low', 0)} low" if "findings" in leak else "")
                     + (f", {len(leak['declared_computed'])} past figure(s) your --computed file also produces (leakage.declared_computed)" if leak.get("declared_computed") else ""))
    firm = (report.get("chrome") or {}).get("firm") or []
    for f in firm:
        lines.append(f"firm chrome: {f.get('chrome_id')} {f.get('text') or f.get('kind')!r}: {f.get('decision')}" + ("" if f.get("chosen") else " (not chosen by the deck)"))
    judge = report.get("judge") or {}
    if "total" in judge:
        hs = judge.get("house_spread") or {}
        lines.append(f"judge: total {judge['total']} (house median {hs.get('median')}, p90 {hs.get('p90')}, max {hs.get('max')}); nearest is the reference: "
                     f"{judge.get('nearest_is_reference')}; filed under the reference: {judge.get('filed_under_reference')} (necessary, not sufficient)")
    elif judge.get("cannot_judge"):
        lines.append(f"judge: cannot judge: {judge['cannot_judge']}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
