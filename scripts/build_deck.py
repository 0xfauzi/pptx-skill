#!/usr/bin/env python3
"""Build a deck: solve every slide with measured fit, emit on the reference package,
validate, render and judge. The one command the model runs after writing a deck spec.

    build_deck.py deck.json --guide guide.json --template tpl.pptx -o out.pptx
                  [--reference ref.pptx] [--others a.pptx b.pdf] [--renders DIR] [--no-render]
                  [--plan plan.json]

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
and to every other deck of its panel. An unfittable slide is still emitted from its last
attempt and marked, so the render shows what did not fit; nothing is dropped silently.

After the solve and before the emit, four more instruments read the resolved page:
`contrast` (WCAG 2.2 ratio of every text run, table row class and chart text, data
labels included, against the fill the page draws behind it; below 3.0:1 refuses the
page with reason "contrast", below AA warns; no ink is ever swapped to pass it), `register` (kind counts, decoration count and container ratio against the
reference's register_stats bands), `tieouts` (a totals row that is not the column sum,
a warning listed first under `problems`), the source-line check (a table or chart with
no type.source_line or type.footnote paragraph warns, quoting the reference's count, where at
least half the reference's data pages carry one or the habit is unmeasured; it never refuses,
and the deck-level `source_lines` sets the deck's count beside the reference's), and `title` (the page title's characters, words and lines against the reference's
titles, and the register the slide states against the reference's register counts; warnings only).
On a guide made with no reference (extract_style.py --blank) every hard limit runs (fit,
overlap, contrast, tie-outs, roles, the package, the render checks, the floors) and every
comparison with a reference (titles, variety, source-line and mark habits, contrast
precedent, the judge, the reference's chrome) reports "no reference" instead of a warning
or a score.
`repetition` at deck level is the section's realised variety: each page's content (the
frame left out) assigned a realised composition by the extractor's own leader clustering,
measured by plan.py (V, distinct per page, runs) against the reference's content pages, with
any run longer than the reference's longest flagged and, given --plan, every page whose
realised composition disagrees with the plan's. After the emit, each page with a
chart carries `chart_defaults_taken`: every chart choice its spec left out, with the
value the file got for it.

A slide's `annotations` (annotate.py) are resolved on the solved page, before those
instruments, into rect, rule and text elements; their collisions refuse the page, and
after the render the words LibreOffice drew are checked against what each one covers.
"""

from __future__ import annotations

import argparse
import functools
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
from emit_pptx import EMPHASIS_EXAMPLE, HEX_RE, run_style, OLD_EMPHASIS_KEYS, TABLE_STYLE_KEYS, Guide as EmitGuide, paragraph_align, chart_label_inks, chrome_hex, chrome_on_page, chrome_text, emit as emit_slides, table_defaults_taken, table_header_bold, table_roles, table_row_styles  # noqa: E402
from extract_style import ARCHETYPE_IOU_THRESHOLD, contrast as contrast_ratio, leader_clusters, slide_similarity, union_area  # noqa: E402
from ooxml import EMU_PER_INCH, paragraphs_words, visual_extent  # noqa: E402

#: WCAG 2.2 SC 1.4.3 minimums and the large-scale sizes (deckgen style/contrast.py:
#: AA_NORMAL, AA_LARGE, LARGE_REGULAR_PT, LARGE_BOLD_PT), cited there to
#: https://www.w3.org/TR/WCAG22/#contrast-minimum and #dfn-large-scale.
AA_NORMAL, AA_LARGE, LARGE_REGULAR_PT, LARGE_BOLD_PT = 4.5, 3.0, 18.0, 14.0
#: Below this a run is refused, not warned: AA_LARGE, the weakest pair WCAG accepts for
#: any text. Nothing in the emitter corrects an ink, so this gate is the only catch.
CONTRAST_REFUSAL = 3.0
def source_roles(guide: dict) -> tuple[str, ...]:
    """The role a source line is set in: type.source_line where the guide has it, so a
    note in type.footnote ("Note: ...", a "(1)" marker's note) is not counted as one (bcg's
    Note-only pages, which its digest reads as carrying no source); type.footnote where the
    guide has no source_line role (the reference sets its sources as footnotes)."""
    roles = (guide.get("typography") or {}).get("roles") or {}
    return ("type.source_line",) if roles.get("type.source_line") else ("type.footnote",)
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


def chrome_zones(guide: dict, mode: str = "auto", page: dict | None = None) -> list[dict]:
    """Reserved zones from the chrome a page carries in this --chrome mode
    (emit_pptx.chrome_on_page). Furniture anchored to the bottom edge reserves everything
    below it (the reference's content never runs under its footer rule); a top-anchored
    rule stays a thin boundary, because the title band sits above it and the solver must
    be free to place the title there. A surface band reserves nothing (is_surface)."""
    zones = []
    page_h = guide["reference"]["page"]["height_emu"]
    page_w = guide["reference"]["page"]["width_emu"]
    for ch in chrome_on_page(guide, mode, page):
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
    from emit_pptx import recurring_chrome
    page = guide.get("reference", {}).get("page") or {}
    page_w, page_h = page.get("width_emu"), page.get("height_emu")
    if not page_w or not page_h:
        return []
    return [ch for ch in recurring_chrome(guide) if ch["kind"] == "rule"
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
            if ps.get("runs"):
                # each run measured whole in the face the emitter writes it in (run_style)
                runs = [(r["text"], *run_style(r, f"text {node.get('id')!r} paragraph {i} run {ri}")) for ri, r in enumerate(ps["runs"])]
                joined, text = "".join(r[0] for r in runs), str(p.get("text", ""))
                if joined != text:
                    # exact, spaces included: the emitter writes the runs, so a space left out
                    # of a run is a space left out of the page ("from$142.0m")
                    at = next((k for k, (x, y) in enumerate(zip(joined, text)) if x != y), min(len(joined), len(text)))
                    raise SystemExit(f"text {node.get('id')!r} paragraph {i}: its runs spell {joined!r} and the paragraph's text is {text!r}; they part at "
                                     f"character {at} (runs ...{joined[max(0, at - 12):at + 12]!r}, text ...{text[max(0, at - 12):at + 12]!r}). The runs, "
                                     "joined, are the paragraph's text exactly, spaces included, cut where the setting changes: "
                                     "[{\"text\": \"Revenue rose from \"}, {\"text\": \"$142.0m\", \"emphasis\": true}, {\"text\": \" in 2021\"}]")
                p["runs"] = [list(r) for r in runs]
    elif node.get("kind") == "table":
        table = node.setdefault("table", {})
        table["totals_last_row"] = bool(st.get("totals_last_row"))
        # every cell in the setting the emitter writes it in (emit_pptx.table_row_styles, the
        # one reader of cell styles): (grid row, column, bold, italic, indent role)
        rows = table_row_styles(table_element(node, st), EmitGuide(guide))
        table["cell_styles"] = [[ri, ci, c["bold"], c["italic"], c["indent_role"]] for ri, row in enumerate(rows) for ci, c in enumerate(row["cells"])]
        table["header_bold"] = table_header_bold(st, EmitGuide(guide))


def table_element(node: dict, st: dict) -> dict:
    """A table node as the emitter's readers take it (emit_pptx.table_row_styles,
    table_defaults_taken) before the solve: its spec, the roles the solver will measure
    (layout's own defaults when the spec names none) and its drawing keys."""
    t = node.get("table") or {}
    return {"id": node.get("id"), "columns": t.get("columns") or [], "rows": t.get("rows") or [], "header_rows": t.get("header_rows", 1),
            "header_role": t.get("header_role", "type.table_header"), "cell_role": t.get("cell_role", "type.table_cell"),
            **({"cell_padding_role": t["cell_padding_role"]} if t.get("cell_padding_role") else {}), **st}


def table_nodes(node: dict) -> list[dict]:
    if node.get("type") == "region":
        return [t for c in node.get("children", []) for t in table_nodes(c)]
    return [node] if node.get("kind") == "table" else []


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
#: a run: its words, and optionally its ink (a colour role), bold and italic (true or
#: false; left out, the role's own), and `emphasis: true`, shorthand for bold, the inline
#: emphasis the emitter has drawn since runs existed
RUN_KEYS = {"text", "emphasis", "ink_role", "bold", "italic"}



def check_presentation(nid: str, kind: str, st: dict) -> None:
    """A presentation value nothing would draw is refused by name, never dropped: an
    anchor outside t, m, b fell back to top in silence (round 5: "middle" on three
    reference decks), and a prst on a text element drew a plain box."""
    from emit_pptx import SpecError, preset_shape
    if "anchor" in st and st["anchor"] not in TEXT_ANCHORS:
        raise SystemExit(f"{kind} {nid!r}: anchor {st['anchor']!r} is not one of {list(TEXT_ANCHORS)} (t top, m middle, b bottom)")
    if kind == "text" and st.get("pad_role") is not None:
        raise SystemExit(f"text {nid!r}: pad_role insets nothing on a text element (the solver measures its words at the box's full width). "
                         "Put the text in a region whose layout carries pad_role (or pad_roles, per side) and whose styling carries the fill")
    if "prst" in st:
        if kind == "text":
            raise SystemExit(f"text {nid!r}: prst draws nothing on a text element (a text box is a rectangle). Put the text in a region whose "
                             "styling carries fill_role, prst and a pad_role deep enough to keep the words inside the shape's body; the region's fill is drawn under them")
        try:
            preset_shape(st["prst"], f"{kind} {nid!r}")
        except SpecError as error:
            raise SystemExit(str(error.code)) from None
    for pi, ps in (st.get("paragraphs") or {}).items():
        for ri, run in enumerate((ps or {}).get("runs") or []):
            stray = sorted(set(run) - RUN_KEYS) if isinstance(run, dict) else ["(not an object)"]
            if stray:
                raise SystemExit(f"{kind} {nid!r} paragraph {pi} run {ri}: {stray} not read on a run; a run is {{\"text\"}} plus {sorted(RUN_KEYS - {'text'})}")
            run_style(run, f"{kind} {nid!r} paragraph {pi} run {ri}")


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
        if refusal := L.sized_text_refusal(node.get("id"), node.get("size") or {}):
            raise SystemExit(refusal)
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
    (10th to 90th percentile): below the band is sparse for this reference, above it denser
    than the reference ever goes. The build reports it because a page that fits can still end
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
                            "and fill at its box, unioned; a text box stretched past its lines is not covered. The reference band "
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


def _corner(ss: float) -> float:
    return ss * 16667 / 100000  # roundRect's default adj


#: The solid body of each filled preset text may stand on, at the preset's default
#: adjustments (the emitter writes none), taken conservatively, as rectangles of which any
#: one must hold the words: a homePlate's body before its point, a chevron's between its
#: notch and its point, an arrow's shaft (half its breadth; the head half the shorter side
#: long), a rounded rectangle without its corners. An ellipse is held by its inscribed
#: curve (preset_holds). Any other preset (a bracket, a brace, a diamond, a triangle, a
#: callout, a cloud) has no body bounded here, so no text may stand on it: the contrast
#: gate could not say what lies under the words (check_text_preset).
PRESET_BODIES = {
    "rect": lambda x, y, w, h, ss: [[x, y, w, h]],
    "roundRect": lambda x, y, w, h, ss: [[x, y + _corner(ss), w, h - 2 * _corner(ss)], [x + _corner(ss), y, w - 2 * _corner(ss), h]],
    "homePlate": lambda x, y, w, h, ss: [[x, y, w - ss * 0.5, h]],
    "chevron": lambda x, y, w, h, ss: [[x + ss * 0.5, y, w - ss, h]],
    "rightArrow": lambda x, y, w, h, ss: [[x, y + h * 0.25, w - ss * 0.5, h * 0.5]],
    "leftArrow": lambda x, y, w, h, ss: [[x + ss * 0.5, y + h * 0.25, w - ss * 0.5, h * 0.5]],
    "downArrow": lambda x, y, w, h, ss: [[x + w * 0.25, y, w * 0.5, h - ss * 0.5]],
    "upArrow": lambda x, y, w, h, ss: [[x + w * 0.25, y + ss * 0.5, w * 0.5, h - ss * 0.5]],
}
TEXT_BEARING_PRESETS = ("ellipse", *PRESET_BODIES)


def preset_holds(prst: str, outer: list, inner: list) -> bool:
    """Whether a filled preset drawn in `outer` lies under every point of `inner`
    (PRESET_BODIES; an ellipse by its inscribed curve). False for any other preset."""
    if prst == "ellipse":
        return _ellipse_contains(outer, inner)
    body = PRESET_BODIES.get(prst)
    return body is not None and any(_contains(b, inner) for b in body(*outer, min(outer[2], outer[3])))


def carries_text(node: dict) -> bool:
    """Whether a spec node draws words: a text, a table or a chart anywhere under it."""
    if node.get("type") == "region":
        return any(carries_text(c) for c in node.get("children") or [])
    return node.get("kind") in ("text", "table", "chart")


def check_text_preset(node: dict, st: dict) -> None:
    """A region whose fill is drawn in a preset under words must use a preset whose body
    the contrast gate can bound (TEXT_BEARING_PRESETS); any preset may be drawn with
    nothing on it."""
    prst = st.get("prst") or "rect"
    if (st.get("fill_role") or st.get("line_role")) and prst not in TEXT_BEARING_PRESETS and carries_text(node):
        raise SystemExit(f"region {node['id']!r}: prst {prst!r} is drawn under words, and its body is not bounded here, so the contrast gate "
                         f"cannot say what lies under them. Under text use one of {list(TEXT_BEARING_PRESETS)}; any preset is drawn on a region "
                         "or rect with no words in it (a shape beside the text, the text in its own region)")


def unmeasured_presets(elements: list[dict]) -> list[dict]:
    """A rect drawn in a preset no earlier render has shown (emit_pptx.PRESETS_DRAWN_BEFORE):
    a warning, since the renderers may draw it differently and nothing here measured how."""
    from emit_pptx import PRESETS_DRAWN_BEFORE
    seen = sorted({(el.get("prst") or "rect", el["id"]) for el in elements if el["kind"] == "rect" and (el.get("prst") or "rect") not in PRESETS_DRAWN_BEFORE})
    return [{"kind": "renderer-unmeasured preset", "severity": "warning",
             "detail": f"{nid}: prst {prst!r} has not been drawn in either renderer by this skill's proofs: check its render, and open the deck in "
                       "PowerPoint before release (references/review.md), since the two renderers may draw it differently"} for prst, nid in seen]


def label_interval_divergence(elements: list[dict]) -> list[dict]:
    """A category axis labelled or ticked every n-th category (label_interval, tick_interval
    above 1): a warning. Measured, round 7, LibreOffice 24.2.7: c:tickLblSkip and
    c:tickMarkSkip are not honoured on a line or column chart at any rotation; LibreOffice
    thins the labels by its own fit (120 categories at an interval of 20 drew every 6th) and
    PowerPoint draws every n-th, so the render reviewed may show other labels than the page."""
    out = []
    for el in elements:
        for name, ax in ((el.get("axes") or {}).items() if el["kind"] == "chart" else []):
            for k in ("label_interval", "tick_interval"):
                if isinstance(ax, dict) and isinstance(ax.get(k), int) and ax[k] > 1:
                    out.append({"kind": "renderer divergence: category interval", "severity": "warning",
                                "detail": f"{el['id']} axes.{name}.{k} {ax[k]}: LibreOffice ignores it and draws its own selection of "
                                          f"{'labels' if k == 'label_interval' else 'ticks'} (measured), PowerPoint draws every {ax[k]}th; the render "
                                          "is not the page here. To draw the same labels in both, hide the axis labels and draw a category_row "
                                          "with a cell per category, null where none is drawn"})
    return out


def chrome_layers(guide: dict, mode: str, page: dict | None = None) -> list[dict]:
    """The page's chrome as the contrast gate reads it, in paint order: bands (a fill
    under whatever lands on them) and text lines (a run to score), each with its EMU page
    box. Drawn chrome lies under every content element."""
    eg = EmitGuide(guide)
    page_w, page_h = guide["reference"]["page"]["width_emu"], guide["reference"]["page"]["height_emu"]
    out = []
    ground = (guide.get("ground") or {}).get("image_path")
    if mode == "draw" and ground and Path(ground).is_file():
        # the reference's ground picture lies under everything (emit_pptx._picture_background)
        out.append({"kind": "ground", "id": "ground", "box": [0, 0, page_w, page_h], "path": ground})
    for ch in chrome_on_page(guide, mode, page):
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


@functools.lru_cache(maxsize=4)
def _ground_pixels(path: str):
    from PIL import Image
    with Image.open(path) as im:
        return im.convert("RGB").copy()


def ground_extremes(path: str, page: list[int], box: list[int]) -> list[str]:
    """The darkest and the lightest colour of the ground picture (stretched over `page`)
    under `box`, as hex: the two backings a run on a gradient ground has at its worst."""
    im = _ground_pixels(path)
    sx, sy = im.width / max(1, page[2]), im.height / max(1, page[3])
    x0, y0 = max(0, int(box[0] * sx)), max(0, int(box[1] * sy))
    x1, y1 = min(im.width, max(x0 + 1, int((box[0] + box[2]) * sx))), min(im.height, max(y0 + 1, int((box[1] + box[3]) * sy)))
    crop = im.crop((x0, y0, x1, y1))
    raw = crop.tobytes()
    px = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)] or [im.getpixel((min(x0, im.width - 1), min(y0, im.height - 1)))]
    luma = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in px]
    lo, hi = px[luma.index(min(luma))], px[luma.index(max(luma))]
    return list(dict.fromkeys("{:02X}{:02X}{:02X}".format(*c) for c in (lo, hi)))


def ink_columns(el: dict, measured: dict, eg: EmitGuide) -> tuple[int, int]:
    """The leftmost and rightmost EMU a text element's measured lines draw at, from each
    line's measured width, its paragraph's indent and the alignment it is written with
    (emit_pptx.paragraph_align). A bulleted or justified paragraph is taken from the box's
    left (a bullet hangs left of the indent) or across its whole width."""
    x, _, w, _ = el["box"]
    left, right = x + w, x
    for para, meas in zip(el["paragraphs"], measured.get("paragraphs") or []):
        align = paragraph_align(para, eg.type_spec(para["role"], where=el["id"]))
        indent = int(meas.get("marL") or 0)
        alloc = int(meas.get("allowance_emu") or (w - indent))
        for width in meas.get("line_widths_emu") or []:
            if para.get("bullet_level") is not None or align == "justify":
                lo, hi = x, x + w
            else:
                start = {"center": (alloc - width) // 2, "right": alloc - width}.get(align, 0)
                lo = x + indent + max(0, start)
                hi = min(x + w, lo + width)
            left, right = min(left, lo), max(right, hi)
    return (left, right) if right > left else (x, x + w)


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
        if band["kind"] == "ground":
            # the ground picture's darkest and lightest pixels under the box: text is
            # scored against both, as against two fills a partial band leaves
            backings, undecidable = ground_extremes(band["path"], band["box"], box), False
            for hexv in backings:
                names.setdefault(hexv, "the reference's ground picture")
            continue
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


def contrast_of(elements: list[dict], resolved: dict, guide: dict, chrome_mode: str = "auto", precedent: dict | None = None,
                page_chrome_choices: dict | None = None) -> dict:
    """WCAG 2.2 contrast of every text run, every table row class, every chart text and
    every chrome text line against the fill the page draws behind it. A text run's backing: the element's own
    fill, else the chain under it. A table's: the row's own fill as the emitter writes it
    (emit_pptx.table_row_styles: header, banding, data, emphasis), else the chain. A
    chart's data labels: the series or point fill for a position on the mark, the plot
    fill or the chain under the chart for a position off it, both when the spec leaves
    the position open (emit_pptx.chart_label_inks); axis labels and the legend: the plot.
    The ink scored is the ink the spec names: nothing swaps it, so a wrong one is
    refused here by name.

    Reference precedent: a pair under AA that the reference itself draws (the same ink hex
    over the same backing hex, ooxml.ink_backings) at this size or smaller is the reference's
    own choice, not a defect of the deck. It is filed under `reference_precedent` with the
    reference's evidence, neither refused nor warned. On a PDF reference a pair counts only
    where the page's render draws it (ooxml.confirm_on_render): a misread backing or words
    in their backing's own colour are no precedent, and the finding names why under
    `no_precedent`. `precedent` None means no reference was given, and every pair is judged
    on WCAG alone; on a guide made with no reference the report says "no reference"."""
    eg = EmitGuide(guide)
    out: dict = {"checked": 0, "violations": [], "warnings": [], "reference_precedent": [], "undecidable": [], "unbound": [], "nearest_pass": None,
                 "precedent_source": ("reference" if precedent is not None else "none: no --reference, so no pair can claim the reference's precedent")
                 if plan.has_reference(guide) else plan.NO_REFERENCE}

    def file(finding: dict) -> None:
        out["checked"] += 1
        seen = (precedent or {}).get((finding["ink_hex"], finding["backing_hex"]))
        if seen and not seen["confirmed"] and finding["ratio"] < finding["threshold"]:
            # the reference's runs of this pair were read, but the render does not draw them so
            finding = {**finding, "no_precedent": seen["not_confirmed"]}
            seen = None
        if finding["ratio"] < finding["threshold"] and seen and isinstance(finding["size_pt"], (int, float)) and seen["min_size_pt"] <= finding["size_pt"]:
            out["reference_precedent"].append({**finding, "reference": {"min_size_pt": seen["min_size_pt"], "chars": seen["chars"], "pages": sorted(seen["pages"])[:12]}})
            return
        if finding["ratio"] < CONTRAST_REFUSAL:
            out["violations"].append(finding)
        elif finding["ratio"] < finding["threshold"]:
            out["warnings"].append(finding)
        elif out["nearest_pass"] is None or finding["ratio"] / finding["threshold"] < out["nearest_pass"]["ratio"] / out["nearest_pass"]["threshold"]:
            out["nearest_pass"] = finding  # the tightest pair that passed, so a near miss is visible

    chrome = chrome_layers(guide, chrome_mode, page_chrome_choices)
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
        scored = elements
        height = (resolved["elements"].get(el["id"]) or {}).get("height_emu") if el["kind"] == "text" else None
        if height is not None and height <= el["box"][3]:
            # the words lie in their measured lines, not in the whole box: a title box that
            # ends on a band's edge has no ink there (bain's title box meets the yellow rule),
            # and a centred label in a homePlate stops short of the point its box reaches
            # into (bain's phase chevrons)
            _, y, _, h = el["box"]
            top = y + {"m": (h - height) // 2, "b": h - height}.get(el.get("anchor") or "t", 0)
            left, right = ink_columns(el, resolved["elements"][el["id"]], eg)
            scored = list(elements)
            scored[i] = {**el, "box": [left, top, right - left, height]}
        lower, image_below = _lower_backings(scored, i, eg, names, chrome)
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
                    own_bold, _ = run_style(run, f"{el['id']} paragraph {pi} run {ri}")
                    bold = bool(meas.get("b") or spec.get("weight", 400) >= 700) if own_bold is None else own_bold
                    run_ink, run_ink_name = (eg.hex(run["ink_role"], where=f"{el['id']} run {ri}"), run["ink_role"]) if run.get("ink_role") else (ink, ink_name)
                    finding = {"element": el["id"], "paragraph": pi, "run": ri, "role": para["role"], "ink": run_ink_name,
                               "text": (run.get("text") or "")[:40], **_score(run_ink, [own] if own else lower, size_pt, bold, names)}
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


#: the element kinds that make a page a data page, which the source-line habit is held to
DATA_KINDS = frozenset({"table", "chart"})
BUILD_UNREAD = "the written file was not read back for this page"


def emitted_structures(path: Path, numbers: list[int], guide: dict, slides: list[dict]) -> tuple[dict[int, dict | None], str | None]:
    """Each built page's exhibit structure and kinds ({"structure", "kinds"}), read from the
    file the build wrote with the one reader that reads the reference's pages
    (ooxml.exhibit_facts), the chrome the build drew (named by its chrome_id) and the footer
    placeholders left out. A picture sized by a role (slide.images[id] with height_role or
    width_role: a logo, an icon, a wordmark) is a mark, not an exhibit, and is left out too
    (bcg's wordmark set as content read every page as holding a picture). The written
    slides are the ones carrying the origin tag, in order, one per solved page; any other
    count reads every page unread, with the reason."""
    import ooxml
    chrome_ids = {ch.get("chrome_id") for ch in guide.get("chrome") or [] if isinstance(ch, dict)}

    def role_sized(slide: dict) -> set[str]:
        return {i for i, entry in (slide.get("images") or {}).items()
                if isinstance(entry, dict) and (entry.get("height_role") or entry.get("width_role"))}

    def left_out(marks: set[str]):
        def test(sh) -> bool:
            return sh.ph_type in ooxml.CHROME_TYPES or (sh.name is not None and (sh.name in chrome_ids or (sh.kind == "picture" and sh.name in marks)))
        return test

    written = [p for p in ooxml.fingerprint_deck(str(path)) if p.generated]
    if len(written) != len(numbers):
        return {n: None for n in numbers}, f"the file holds {len(written)} generated slides for {len(numbers)} solved pages"
    facts = {n: ooxml.exhibit_facts(p, left_out(role_sized(slides[n - 1]))) for n, p in zip(numbers, written, strict=True)}
    return {n: {**{key: f[key] for _, key in plan.FACT_MEASURES}, "panels": f["panels"], "drawn": f["drawn"]} for n, f in facts.items()}, None


def briefs_against_file(pages: list[tuple[int, list[dict]]], emitted: list[dict], slide_ids: dict[int, str],
                        plan_pages: list[dict] | None, structures: dict[int, dict | None], unread_why: str | None) -> None:
    """Each built page's exhibit briefs against the exhibits its written file holds
    (emitted_structures' panels: charts, tables, pictures and a structure built from shapes;
    decoration is no panel). A page whose file holds an exhibit while its plan page briefs
    none is refused by name: the brief is how an exhibit is reasoned out before its spec,
    and an empty list states the page holds none. Other differences in count are warned
    with both counts (one brief may cover a chart and the table set under it as one
    exhibit; a logo wall is many pictures and one brief), and a page whose file was not
    read says so in entry["briefs"], never as agreement."""
    if plan_pages is None:
        return
    planned = {p["id"]: p for p in plan_pages}
    for (number, _), entry in zip(pages, emitted, strict=True):
        page = planned.get(slide_ids.get(number))
        if page is None:
            continue
        briefs = len(page["exhibits"])
        facts = structures.get(number)
        if facts is None:
            entry["briefs"] = {"plan": briefs, "file": None, "verdict": f"not compared: {unread_why or 'the written file was not read'}"}
            continue
        panels = facts["panels"]
        entry["briefs"] = {"plan": briefs, "file": panels, "file_structure": facts["structure"],
                           "verdict": "agree" if panels == briefs else "differ"}
        if panels and not briefs:
            entry["problems"].append({"kind": "exhibit without a brief", "severity": "refusal",
                                      "detail": f"the written page holds {facts['structure']} and its plan page {page['id']!r} briefs no exhibit "
                                                "(exhibits: []): write the brief for each exhibit (what the reader must see, the comparison, "
                                                "the data, the forms weighed, the chosen form and why, the marks) "
                                                "and plan.py check it before the spec"})
            if entry["status"] == "fit":
                entry["status"], entry["reason"] = "unfittable", "exhibit without a brief"
        elif panels != briefs:
            entry["problems"].append({"kind": "briefs differ from the file's exhibits", "severity": "warning",
                                      "detail": f"the plan briefs {briefs} exhibit(s) for {page['id']!r} and the written page holds {panels} "
                                                f"({facts['structure']}): say in the report which brief covers which exhibit, or brief the one left out"})


#: Unmeasured: a pair of pages whose box similarity lies this close to the archetype
#: line is marked borderline (round 5: one lead-in wrapping to two lines moved a keybank
#: pair from 0.434 to 0.543 and flipped the realised variety).
BORDERLINE_SIMILARITY = 0.1


def repetition_of(pages: list[tuple[int, list[dict]]], guide: dict, plan_pages: list[dict] | None = None,
                  slide_ids: dict[int, str] | None = None, structures: dict[int, dict | None] | None = None,
                  plan_check: dict | None = None, unread_why: str = BUILD_UNREAD) -> dict:
    """The built section's realised variety. Each solved page's content is its flattened
    elements' boxes with the page frame (frame_tracks) left out; pages get a realised
    composition by the extractor's own leader clustering (leader_clusters on
    slide_similarity, Hungarian box IoU over the larger set, at the archetype threshold),
    which is how the reference's archetypes were assigned, and are measured by plan.py's one
    measure: V, distinct compositions per page, the longest run and every run. A page that
    did not solve breaks the sequence (absence, not a change). Against the reference
    (guide.variety), a run longer than the reference's longest is flagged as a departure to
    answer in the report; with no run evidence none is judged, and with no reference every
    comparison reads "no reference". Against the plan, each
    adjacent pair where plan and build disagree (the plan repeats a composition and the
    build changes it, or the reverse) flags the later page. The exhibit structure of each
    page, read from the file the build wrote (emitted_structures), is measured the same way
    against the structure the extractor read off the reference's own pages: nobody names it, so
    a section of pages that each set a table beside a chart reads as the repeat it is
    however the plan describes them. The reference's measure keeps its
    title as content where the build leaves the frame out: the reference is held to the more
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
        facts = (structures or {}).get(number) or {}
        segments[-1].append({"slide": number, "composition": realised[number], **{key: facts.get(key) for _, key in plan.FACT_MEASURES}})
    pairs = []
    for (pa, ea), (pb, eb) in zip(pages, pages[1:]):
        if pb == pa + 1:
            sim = slide_similarity(content(pa, ea), content(pb, eb))
            pairs.append({"pages": [pa, pb], "similarity": round(sim, 3), "similar": sim >= ARCHETYPE_IOU_THRESHOLD,
                          **({"borderline": True} if abs(sim - ARCHETYPE_IOU_THRESHOLD) < BORDERLINE_SIMILARITY else {})})
    built = plan.measure_deck("built", segments, unread_why)
    ref = plan.reference_variety(guide)
    longest = ref.get("longest_run") if ref["status"] == "measured" else None
    held = (longest if longest is not None else plan.NO_REFERENCE if ref["status"] == plan.NO_REFERENCE
            else f"not judged: the reference's longest run is no evidence ({ref.get('why')})")
    runs = built.get("runs") or []
    over: list[dict] | str = ([{"pages": r["pages"], "length": len(r["pages"]), "realised": r["composition"]} for r in runs if len(r["pages"]) > longest]
                              if longest is not None else held)
    out: dict = {"threshold": ARCHETYPE_IOU_THRESHOLD, "frame_left_out": sorted(t["id"] for t in frame), "pairs": pairs,
                 "realised": [{"page": n, "composition": realised[n], **((structures or {}).get(n) or {})} for n, _ in pages], "measure": built,
                 "reference": {k: ref[k] for k in ("deck", "status", "content_pages", "composition", *(n for n, _ in plan.FACT_MEASURES),
                                                   "distinct", "longest_run", "why") if k in ref},
                 "against_reference": ({"composition_V": plan.against(built["composition"]["V"], ref, "composition"),
                                        **{f"{name}_V": plan.against(built[name].get("V"), ref, name) for name, _ in plan.FACT_MEASURES},
                                        "distinct_per_page": plan.distinct_against(built["distinct"]["per_page"], built["content_pages"], ref),
                                        "longest_run": {"built": built["longest_run"], "reference": held}}
                                       if built["status"] == "measured" else {"built": built["why"]}),
                 "reference_longest_run": held, "runs_over_reference": over}
    warnings = [f"{k} {v['value']} {v['verdict']} ({v.get('reference_V', v.get('reference_p10_window'))}): a departure (the line is unmeasured); "
                "answer it in one line in the report"
                for k, v in (out["against_reference"].items() if built["status"] == "measured" else []) if isinstance(v, dict) and v.get("verdict", "").startswith("below")]
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
                   **{f"{name}_V": {"planned": "not declared: " + plan.PLAN_UNREAD,
                                    "realised": (built.get(name) or {}).get("V", (built.get(name) or {}).get("why"))} for name, _ in plan.FACT_MEASURES},
                   "pages_differing_from_plan": flags,
                   # absence is not agreement: the list above compares neighbours only
                   "pages_against_their_archetype": "unmeasured: the guide keeps each archetype's kinds and slide numbers, not its boxes, so "
                                                    "whether a page realises the archetype it names (arch-10 built as an arch-15 list) is not "
                                                    "checked here; pages_differing_from_plan compares adjacent pages only. Compare the render "
                                                    "with the archetype's slides yourself and correct plan.json when they differ"}
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
            how = col.get("total") or "sum"
            if how == "none":
                out.append({"table": el["id"], "column": col.get("key"), "status": "skipped", "note": "total \"none\": the column says its totals cell is no simple aggregate"})
                continue
            total_text = str(el["rows"][-1][ci])
            total = parse_figure(total_text)
            rec = {"table": el["id"], "column": " ".join(t for t in L.header_labels(col, int(el.get("header_rows", 1)), "table") if t) or col.get("key"), "total": total_text,
                   "aggregate": how if "total" in col else "sum (the default: the column states no total)"}
            if total is None:
                out.append({**rec, "status": "skipped", "note": "the totals cell is blank or not a figure"})
                continue
            body = [(str(r[ci]), parse_figure(r[ci])) for r in el["rows"][:-1]]
            bad = [text for text, value in body if value is None]
            if bad:
                out.append({**rec, "status": "skipped", "note": f"cells not figures: {bad}"})
                continue
            d = _decimals(total_text)
            total_sum = sum(value for _, value in body) / (len(body) if how == "mean" else 1)
            rec.update({how: f"{total_sum:.{d}f}", "precision": d, "status": "ok" if abs(round(total_sum, d) - round(total, d)) < 10 ** -(d + 6) else "mismatch"})
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


def source_line_of(elements: list[dict], guide: dict) -> dict:
    """Whether the page holds a data exhibit (a table or a chart, DATA_KINDS) and whether it
    carries a paragraph of its own in the source-line role (source_roles; an annotation's
    label is not one)."""
    roles = source_roles(guide)
    return {"data_page": any(el["kind"] in DATA_KINDS for el in elements),
            "source_line": any(p["role"] in roles for el in elements if el["kind"] == "text" and not el.get("annotation")
                               for p in el["paragraphs"])}


#: A definition, not a measured line: a data page departs from the reference's source-line
#: habit when it lacks a source line and at least this share of the reference's data pages
#: carry one (the reference's majority), read from the completed digest over at least
#: SOURCE_LINE_MIN_PAGES data pages. Citing a source is never wrong, so a page WITH one is
#: never a departure, and nothing here refuses: the count is evidence beside the choice.
SOURCE_LINE_MAJORITY = 0.5
SOURCE_LINE_MIN_PAGES = 3
#: what each habit means for a new page, as source_line_problem reads it
SOURCE_LINE_ADVICE = {
    "most": "a data page without one is warned with this count; answer the warning in the report",
    "few": "a data page without one does what most of the reference's do; a page with one is never wrong",
    "unmeasured": "a data page without one is warned (the reference's habit is no evidence either way); answer the warning in the report",
    plan.NO_REFERENCE: "nothing is compared: say in the report where the deck's data comes from",
}


def source_line_habit(guide: dict) -> dict:
    """The reference's source-line habit from the digest, with its count: `most` (at least
    SOURCE_LINE_MAJORITY of its data pages carry one), `few` (fewer do), or `unmeasured`
    (no answers, or too few data pages to say; never read as 'the reference carries none'),
    or "no reference" on a guide made with none, where a page's source line is the model's call."""
    if not plan.has_reference(guide):
        return {"habit": plan.NO_REFERENCE, "evidence": "no reference: whether a data page carries a source line is the deck's own choice"}
    lines = (guide.get("exhibit_habits") or {}).get("source_lines")
    if not isinstance(lines, dict) or lines.get("share") is None:
        return {"habit": "unmeasured", "evidence": "not measured: the guide's digest answers no source_line (re-run gallery.py digest and answer it)"}
    n, k = lines["data_pages"], lines["with_source_line"]
    if n < SOURCE_LINE_MIN_PAGES:
        return {"habit": "unmeasured", "evidence": f"{k} of {n} data pages carry one: fewer than {SOURCE_LINE_MIN_PAGES} data pages is no evidence of a habit"}
    share = lines["share"]
    return {"habit": "most" if share >= SOURCE_LINE_MAJORITY else "few", "share": share, "pages_with": lines.get("pages_with"),
            "evidence": f"the reference sources {k} of {n} data pages ({share:.0%}"
                        + (f": pages {', '.join(str(x) for x in lines.get('pages_with') or [])}" if 0 < k <= 5 else "") + ")"}


def source_line_problem(elements: list[dict], guide: dict) -> dict | None:
    """A data page without a source line where most of the reference's data pages carry one,
    or where the habit is unmeasured: a warning quoting the reference's count, answered in the
    report (keep the page as it is and say why, or add one). Never a refusal: the reference's
    count is evidence, not a measured defect."""
    page = source_line_of(elements, guide)
    habit = source_line_habit(guide)
    role = source_roles(guide)[0]
    if page["data_page"] and not page["source_line"] and habit["habit"] not in ("few", plan.NO_REFERENCE):
        return {"kind": "no source line", "severity": "warning",
                "detail": f"the page carries a table or a chart and no paragraph in {role}; {habit['evidence']}; this page has none: "
                          "add one, or say in the report why this page carries none"}
    return None


def page_problems(entry: dict, elements: list[dict], resolved: dict, guide: dict, measured: list[dict] | None = None, chrome_mode: str = "auto",
                  precedent: dict | None = None, page_chrome_choices: dict | None = None) -> list[dict]:
    """The ordered problem list: tie-out warnings first (a totals row can be a subtotal
    the agent meant), then the refusals (contrast, bridge ties, the measured checks), then
    the source-line problem (source_line_habit). A refusal turns a fit
    page unfittable with the refusal's name as the reason; a page the solver already
    refused keeps the solver's reason, the first cause."""
    entry["contrast"] = contrast_of(elements, resolved, guide, chrome_mode, precedent, page_chrome_choices)
    entry["register"] = register_of(elements, guide)
    entry["tieouts"] = tieouts_of(elements)
    problems = [{"kind": "tieout", "severity": "warning", "detail": f"{t['table']} column {t['column']!r}: body rows' {'mean' if 'mean' in t else 'sum'} is {t.get('mean', t.get('sum'))}, the totals cell reads {t['total']}; a totals cell that is no simple aggregate takes total \"none\" on its column"} for t in entry["tieouts"] if t["status"] == "mismatch"]
    for v in entry["contrast"]["violations"]:
        if "run" in v:
            where = f"{v['element']} paragraph {v['paragraph']} run {v['run']}"
        elif "part" in v:
            where = f"{v['element']} {v['part']}" + (f" (points {v['points']})" if v.get("points") else "")
        else:
            where = f"{v['element']} {v['row_class']} rows"
        problems.append({"kind": "contrast", "severity": "refusal", "detail": f"{where}: {v['ink']} over {v['backing']} is {v['ratio']}:1, under {CONTRAST_REFUSAL}:1 (AA asks {v['threshold']}:1 at {v['size_pt']}pt{' bold' if v['bold'] else ''})"})
    failures = bridge_ties(elements)
    problems.extend({"kind": "bridge does not tie", "severity": "refusal", "detail": f"{b['chart']}: {b['detail']}"} for b in failures)
    # each declared bridge by name, with a verdict that says so: an empty list read as
    # "nothing checked" and "everything ties" alike
    declared = [el.get("id", "chart") for el in elements if el["kind"] == "chart" and el.get("bridge")]
    entry["bridge_ties"] = {c: ([b["detail"] for b in failures if b["chart"] == c] or "ties: every total equals the steps before it, every drawn span its step")
                            for c in declared} or "no chart on this page declares a bridge"
    problems.extend(measured or [])
    entry["source_line"] = source_line_of(elements, guide)
    found = source_line_problem(elements, guide)
    if found:
        problems.append(found)
    refusals = list(dict.fromkeys(p["kind"] for p in problems if p["severity"] == "refusal"))
    entry["solver_status"] = entry["status"]  # the geometry verdict alone; component.py's harness page reads it
    if refusals and entry["status"] == "fit":
        entry["status"], entry["reason"] = "unfittable", "; ".join(refusals)
    return problems


# --- measured fit of what the file carries --------------------------------------------------


def drawn_lines(out: str, emitted: list[dict], emit_pages: list[dict], words: list[list[tuple]]) -> list[dict]:
    """Each solved text box as the renderer drew it: its words found in the render's word
    list (pdftotext -bbox, in the order drawn) as one unbroken run, and the lines they sit
    on counted against the lines the file writes (each paragraph and each break the solver
    measured). More lines drawn than written means the renderer set a measured line wider
    than the ruler did and wrapped it: the box overflows below its measured height (on
    LibreOffice 24.2.7, a 7.5pt line measured 24,110 EMU inside its box was wrapped). Words
    the render does not hold as one run are reported as not found, never as a fit."""
    from pptx import Presentation
    from pptx.oxml.ns import qn as pqn
    slides = list(Presentation(out).slides)
    offset = len(slides) - len(emitted)
    out_pages = []
    for i, page in enumerate(emit_pages):
        solved = {el["id"] for el in page["elements"] if el["kind"] == "text"}
        page_words = words[i] if i < len(words) else []
        checked, wrapped = {}, []
        for shape in slides[offset + i].shapes:
            if shape.name not in solved or not shape.has_text_frame:
                continue
            paras = shape.text_frame.paragraphs
            written = sum(1 + len(p._p.findall(pqn("a:br"))) for p in paras if p.text.strip())
            tokens = " ".join(p.text for p in paras).split()
            if not tokens:
                continue
            # the render's words inside the box's column, from its top down (a wrapped box runs
            # below its height, never out of its column), in the order drawn; bullet glyphs
            # are drawn as words of their own and are not the text
            glyphs = {b.get("char") for b in shape._element.iter(pqn("a:buChar"))} - {None, ""}
            x0, x1, top = shape.left, shape.left + shape.width, shape.top
            seq = [(box, t) for box, t in page_words if x0 - annotate.EMU_PER_PT <= box[0] + box[2] / 2 <= x1 + annotate.EMU_PER_PT
                   and box[1] + box[3] / 2 >= top and not (t in glyphs or (len(t) == 1 and 0xE000 <= ord(t) <= 0xF8FF))]
            texts_in = [t for _, t in seq]
            starts = [k for k in range(len(texts_in) - len(tokens) + 1) if texts_in[k:k + len(tokens)] == tokens]
            if len(starts) != 1:
                checked[shape.name] = f"not found: its words are {'not one run' if not starts else 'drawn ' + str(len(starts)) + ' times'} in its column of the render"
                continue
            run = seq[starts[0]:starts[0] + len(tokens)]
            lines: list[tuple[float, list[str]]] = []
            for box, text in run:
                if lines and abs(box[1] - lines[-1][0]) < box[3] / 2:
                    lines[-1][1].append(text)
                else:
                    lines.append((box[1], [text]))
            checked[shape.name] = {"written": written, "drawn": len(lines)}
            if len(lines) > written:
                wrapped.append(f"{shape.name}: written in {written} line(s) the solver measured, drawn in {len(lines)} by the renderer "
                               f"({[' '.join(t) for _, t in lines]}); a measured line was set wider than the ruler measured it. "
                               "Shorten the text or widen its box, so the line that wrapped has room")
        out_pages.append({"checked": checked, "wrapped": wrapped})
    return out_pages


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
                    if cell.is_spanned:
                        continue  # covered by a spanner to its left: the origin cell draws the text
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
                    ppr = cell.text_frame.paragraphs[0]._p.pPr
                    indent = int(ppr.get("marL") or 0) if ppr is not None else 0
                    # a spanner (gridSpan) wraps at the width of every column it covers
                    span = cell.span_width if cell.is_merge_origin else 1
                    width = sum(shape.table.columns[c].width for c in range(ci, ci + span))
                    budget = max(1, width - (cell.margin_left or 0) - (cell.margin_right or 0) - indent - ctx.ruler.fit_epsilon_emu)
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


def chart_label_breaks(elements: list[dict], ctx: L.Context) -> tuple[list[dict], list[dict], list[dict]]:
    """Chart text a renderer must break between characters, measured with the solver's
    ruler and faces at the size the emitter writes (the guide role, scale 1). A bar or
    column chart's category slot is at most the chart box's extent along the category
    axis over the category count; a column chart's tick label wraps to its slot, and a
    centred data label wraps to the bar's thickness, at most the slot less the gap
    (gap_width, else none) and, clustered, shared by the series (overlap, else full).
    Both are upper bounds, since the plot is smaller than the box: a word wider than the
    bound breaks for certain, one under it may still break. A horizontal bar's centred
    label is not wrapped (LibreOffice 24.2, measured 2026-10-26 on twelve stacked bars
    0.2 in thick: "Wave 1", "Remaining" in a 0.46 in segment and a five-word label each
    drew on one line), so it is held to nothing here; a label wider than its bar's length
    spills past the bar's ends and is listed under `spills` when the chart has a
    plot_area. An inside_base label wider than its 0.47 in bar stayed on one line (bain
    page 5). Returns (findings, unmeasured, spills)."""
    findings: list[dict] = []
    unmeasured: list[dict] = []
    spills: list[dict] = []
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

        try:
            from annotate import drawn_marks
            from chart_geometry import ChartGeometry, GeometryRefused
            marks = {(j, i): m for j, i, m in drawn_marks(ChartGeometry(el, el["box"]))} if horizontal else {}
        except GeometryRefused:
            marks = {}

        def words_over(text: str, role: str | None, limit: float, part: str, mark: tuple | None = None, el: dict = el, horizontal: bool = horizontal) -> None:
            role = role or (el.get("text") or {}).get("role")
            if not role:
                unmeasured.append({"chart": el["id"], "part": part, "why": "no type role: the theme sets the size"})
                return
            entry = L.resolve_type_entry(ctx.guide, role, L.Fraction(1))
            face = ctx.face(entry)
            if horizontal:
                width = L.advance_emu(ctx.ruler, str(text), face.path, entry.size_pt)
                if mark is not None and width > mark[2]:
                    spills.append({"chart": el["id"], "part": part, "text": str(text), "width_emu": width, "bar_emu": round(mark[2]), "size_pt": entry.size_pt})
                return
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
                words_over(text, merged.get("role"), bar, f"series[{si}] {s.get('name')!r} point {pi} label", marks.get((si, pi)))
    return findings, unmeasured, spills


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


def claim_places(guide: dict) -> str:
    """Where the reference states the claims its topic titles leave out, with counts, from the
    completed /titles/register (claims_elsewhere: slide -> a place in words, or null)."""
    if not plan.has_reference(guide):
        return "no reference: a lead-in, a takeaway band or a sidebar, wherever the page's own design puts it"
    claims = (((guide.get("titles") or {}).get("register")) or {}).get("claims_elsewhere")
    if not isinstance(claims, dict) or not claims:
        return "the guide's /titles/register records no claims_elsewhere: read the reference's own pages for it"
    places = Counter(" ".join(str(v).split()).lower() for v in claims.values() if isinstance(v, str) and v.strip())
    stated = ", ".join(f"{p} ({n})" for p, n in places.most_common())
    silent = sum(1 for v in claims.values() if v is None)
    return (f"claims_elsewhere: {stated}" if stated else "claims_elsewhere names no place") + (f"; {silent} topic-titled page(s) state no claim" if silent else "")


#: Asserted, unmeasured: a page whose stated register the reference uses on fewer than this
#: share of its titles is warned. No measurement says where a register becomes foreign.
RARE_REGISTER_SHARE = 0.10


def title_report(slide: dict, spec_raw: dict, elements: list[dict], entry: dict, guide: dict) -> tuple[dict, list[dict]]:
    """The page title against the reference's titles (guide.titles): characters, words and the
    solver's lines against the reference distribution (above the reference max warns), and the
    register the page spec states (`slide.title.register`, in words, as the plan states
    it): a coded term (plan.register_term) against the reference's register counts (a term on
    under RARE_REGISTER_SHARE of the reference's titles warns), any other words reported as no
    count with the counts beside them. Only a register that is not words is refused.
    The register is never read from the title here: the spec states it, or it is reported
    as not stated. Absence of evidence is reported as such, never as zero; on a guide made
    with no reference nothing is compared and the report says "no reference"."""
    tid = page_title_id(slide, spec_raw)
    named = (slide.get("title") or {}).get("element")
    stated = (slide.get("title") or {}).get("register")
    if stated is not None and (e := plan.register_error(stated, f"{slide.get('id')}: title.register")):
        raise SystemExit(e)  # the plan's own rule (plan.register_error)
    el = next((e for e in elements if e["id"] == tid and e["kind"] == "text"), None) if tid else None
    if named and el is None:
        kinds = sorted({e["kind"] for e in elements if e["id"] == named})
        raise SystemExit(f"{slide.get('id')}: title.element {named!r} names " + (f"a {'/'.join(kinds)} element, not a text" if kinds else "no element on the page"))
    if el is None:
        return {"element": None, "register_stated": stated,
                "verdict": "no title: the page names none (title.element) and holds no text element set in type.title"}, []
    # the title's own paragraphs: a subtitle set with it in the band above the rule (the
    # reference's subtitle on jazz) is a companion, which the reference's title lengths leave out
    own = [p for p in el["paragraphs"] if p.get("role") == "type.title"] or el["paragraphs"]
    text = paragraphs_words(own)
    titles = guide.get("titles") if plan.has_reference(guide) else None
    report: dict = {"element": tid, "text": text, "register_stated": stated}
    warnings: list[dict] = []
    lines = (sum(len(p["lines"]) for p in own) if all(p.get("lines") for p in own)
             else (entry.get("text_lines") or {}).get(tid) if len(own) == len(el["paragraphs"]) else None)
    measured = {"chars": len(text), "words": len(text.split()), "lines": lines}
    if not plan.has_reference(guide):
        report["length"] = {k: {"value": v, "verdict": plan.NO_REFERENCE} for k, v in measured.items()}
    elif not titles or not titles["distribution"]["chars"]["n"]:
        report["length"] = {k: {"value": v, "verdict": "no evidence: the guide has no titles read by position"} for k, v in measured.items()}
    else:
        report["length"] = {}
        for k, v in measured.items():
            d = titles["distribution"][k]
            if v is None or not d["n"]:
                verdict = "no evidence" if v is not None else "not measured"
            else:
                verdict = "above reference max" if v > d["max"] else "above reference p90" if v > d["p90"] else "within reference p90"
            report["length"][k] = {"value": v, "reference": {q: d[q] for q in ("median", "p90", "max", "n")}, "verdict": verdict}
            if verdict == "above reference max":
                warnings.append({"kind": "title longer than the reference", "severity": "warning",
                                 "detail": f"{tid}: {v} {k} against the reference max of {d['max']} (median {d['median']}, {d['n']} titles): "
                                           "a departure; answer it in one line in the report"})
    reg = (titles or {}).get("register")
    term = plan.register_term(stated) if stated is not None else None
    if stated is None:
        report["register"] = {"verdict": "not stated: the page spec names no title.register"}
    elif not plan.has_reference(guide):
        report["register"] = {"term": term, "verdict": plan.NO_REFERENCE}
    elif not reg:
        report["register"] = {"verdict": "no evidence: the guide's /titles/register is not completed"}
    elif term is None:
        report["register"] = {"term": None, "reference_counts": reg["counts"],
                              "verdict": "no count: the register is in words, none of the terms the reference's titles are coded in"}
    else:
        report["register_term"] = term
        stated = term
        share = reg["counts"].get(stated, 0) / reg["n"] if reg["n"] else None
        report["register"] = {"reference_counts": reg["counts"], "share": None if share is None else round(share, 3), "threshold": RARE_REGISTER_SHARE,
                              "threshold_basis": "unmeasured", "verdict": "rare in the reference" if share is not None and share < RARE_REGISTER_SHARE else "a register the reference writes"}
        if share is not None and share < RARE_REGISTER_SHARE:
            warnings.append({"kind": "title register rare in the reference", "severity": "warning",
                             "detail": f"{tid}: a {stated} title, which the reference writes on {reg['counts'].get(stated, 0)} of {reg['n']} titles "
                                       f"({json.dumps(reg['counts'])}); the {RARE_REGISTER_SHARE:.0%} line is unmeasured: a departure; answer it in one line in the report"})
    return report, warnings


#: the indent per bullet level a page gets when the reference shows no bullets and the
#: spec names none: the spacing scale's progression, a default nobody chose
BULLET_INDENTS_TAKEN = {"0": "space.sm", "1": "space.md", "2": "space.lg", "3": "space.xl"}


def bullet_indents_taken(slide: dict, spec: L.Spec, guide: dict) -> list[str]:
    """The bullet indents prepare_page put on this page, listed when a paragraph sets a
    bullet (otherwise they draw nothing), with the question the default hides."""
    if "bullet_indent_roles" in (slide.get("spec") or {}) or guide.get("typography", {}).get("bullets"):
        return []
    levels = sorted({q.bullet_level for node, _ in L.walk(spec.root) if isinstance(node, L.Element) for q in node.paragraphs if q.bullet_level is not None})
    if not levels:
        return []
    whose = "the reference shows no bullets, so nothing of the reference's sets them" if plan.has_reference(guide) else "the guide sets no bullets"
    return [(f"bullet_indent_roles: levels {levels} indented {', '.join(BULLET_INDENTS_TAKEN[str(lv)] for lv in levels if str(lv) in BULLET_INDENTS_TAKEN)} "
             f"({whose}): does this text need bullets, numbered rows or prose?")]


def prepare_page(spec_raw: dict, guide: dict, chrome_mode: str = "auto", page_chrome_choices: dict | None = None) -> None:
    """The page as the build enforces it: the guide's page size, the chrome zones, the
    indent progression for a bullet-less reference, and the title band. `layout.py
    capacity` calls this too, so the budget it prints is the budget the build solves."""
    page = spec_raw.setdefault("page", {})
    page.setdefault("width_emu", guide["reference"]["page"]["width_emu"])
    page.setdefault("height_emu", guide["reference"]["page"]["height_emu"])
    if "reserved_zones" not in page:
        page["reserved_zones"] = chrome_zones(guide, chrome_mode, page_chrome_choices)
    if "bullet_indent_roles" not in spec_raw and not guide.get("typography", {}).get("bullets"):
        # a reference with no bullets (a PDF, a deck of prose) gets the indent progression
        # of the spacing scale (deckgen 4b row 1: continue the indent progression), listed
        # under layout_defaults_taken where a page sets bullets (bullet_indents_taken)
        spec_raw["bullet_indent_roles"] = dict(BULLET_INDENTS_TAKEN)
    band = title_band_emu(guide, spec_raw)
    root_children = spec_raw.get("root", {}).get("children", [])
    if band and banded_title(spec_raw) is not None:
        # the reference keeps its titles above the top rule: the title's box is the band
        # from the root's content top down to the rule, so whatever follows it starts
        # below the rule; a title that needs more lines than the band holds is refused
        # as overflow, never pushed under the rule
        root_children[0]["size"] = {"width_emu": None, "height_emu": band}
        root_children[0]["scale_class"] = "fixed"


def slide_chrome(slide: dict, guide: dict, mode: str) -> dict:
    """The page's own chrome choices (slide.chrome), proven once (emit_pptx.page_chrome):
    an entry left off this page or set in other words, each with its why."""
    from emit_pptx import SpecError, page_chrome
    try:
        return page_chrome(guide, mode, slide.get("chrome"), f"slide {slide.get('id')!r}")
    except SpecError as error:
        raise SystemExit(str(error.code)) from None


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
            try:
                sub = load_component(node["kind"])(data, {"width_emu": box["width"], "height_emu": box["height"]}, guide_for_components)
            except ValueError as error:
                # the component cannot draw what its data asks for (a variant the data cannot
                # carry, a constant out of range): refused by name, never a traceback
                raise SystemExit(f"component {node['id']!r} ({node['kind']}): {error}") from None
            # what the component chose and the defaults it left in place, said by the component
            # (component_api: its root region's `report`), into the page's component_notes
            told = sub.pop("report", None) if isinstance(sub, dict) else None
            if told is not None and (not isinstance(told, list) or not all(isinstance(t, str) for t in told)):
                raise SystemExit(f"component {node['kind']}: report is a list of sentences, got {told!r}")
            slide.setdefault("component_notes", []).extend(f"{node['kind']} {node['id']!r}: {t}" for t in told or [])
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
            check_text_preset(node, st or {})
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
                        "runs": ps.get("runs") or [{"text": p_spec["text"], **({"emphasis": True} if p_spec.get("emphasis") else {})}],
                        "ink_role": ps.get("ink_role") or p_spec.get("ink_role"), "align": ps.get("align") or p_spec.get("align")}
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
                        "fit_padding_emu": r["cell_margins_emu"]["marL"], "cell_indents_emu": r.get("cell_indents_emu") or {}, **extra})
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
    prepare_page(spec_raw, guide, chrome, slide_chrome(slide, guide, chrome))
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
            # first only when the table's own rows outgrow its box; otherwise another block
            # took the height and the table's count is a budget, not the cause
            own = bool(t["box_in"]) and t["rows_need_in"] > t["box_in"][3]
            causes.insert(0 if own else len(causes), f"table {t['id']}: the page is {over / EMU_PER_INCH:.2f} in over at full scale, and {t['rows_to_fit']} of its "
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


def leakage_of(out: str, reference: str | None, guide: dict, briefs: list[str], template: str, ids: list, computed: list[str] | None = None,
               furniture: list[str] | None = None) -> dict:
    """leakage.py on the written deck against the past deck this build was given (the
    reference). With no reference there is no past deck to find in the new one, and the
    report says so; a reference guide built without --reference says it was not checked."""
    import leakage
    if not reference:
        return {"verdict": (plan.NO_REFERENCE + ": no past deck, so no past content can be found in this deck") if not plan.has_reference(guide)
                else "not checked: no past deck given (--reference)"}
    return leakage.leakage(out, [reference], briefs, template, ids, computed, furniture)


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


def type_roles_of(obj) -> set[str]:
    """Every type role an emitted element names, wherever it names it (a paragraph, a
    table's header and cells, a chart's text, labels and axes)."""
    if isinstance(obj, dict):
        return {v for k, v in obj.items() if k.endswith("role") and isinstance(v, str) and v.startswith("type.")} | {
            r for v in obj.values() for r in type_roles_of(v)}
    if isinstance(obj, list):
        return {r for v in obj for r in type_roles_of(v)}
    return set()


def off_ladder_problems(elements: list[dict], guide: dict, judge: dict | None) -> list[dict]:
    """A type role the completion wrote off the reference's size ladder (provenance.off_ladder,
    complete_guide.check_writable: allowed with a reason) that this page sets text in: a
    warning naming the levels, the nearest one, the reason given and the judge's size_hist
    distance for the deck, answered in the report. A weaker model given continuous sizes
    drifted to 8.5, 9.5, 20 and 22pt (references/typography.md); the levels are the reference's."""
    roles = (guide.get("typography") or {}).get("roles") or {}
    d = ((judge or {}).get("components") or {}).get("size_hist")
    distance = (f"the judge's size_hist distance for this deck is {d} (0 is the reference's own mix of sizes)" if d is not None
                else "the judge's size_hist distance is not computed (no --reference, or the reference cannot be judged)")
    out = []
    for role in sorted(type_roles_of(elements)):
        tag = ((roles.get(role) or {}).get("provenance") or {}).get("off_ladder")
        if isinstance(tag, dict):
            out.append({"kind": "type size off the reference's ladder", "severity": "warning",
                        "detail": f"{role} at {tag.get('size_pt')}pt is off the reference's levels {tag.get('levels')} (nearest {tag.get('nearest_level')}pt), "
                                  f"written because: {tag.get('why')}; {distance}. Say in the report why this size and not the nearest level"})
    return out


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


def read_answers(slide: dict) -> list[dict]:
    """A page's answers to warnings it means (slide.answered), proven at the boundary: a list
    of {"kind": <a warning's kind>, "why": words} plus an optional "detail" (words the
    warning's detail holds, when the page has two warnings of one kind)."""
    raw = slide.get("answered")
    if raw is None:
        return []
    where = f"slide {slide.get('id')!r} answered"
    if not isinstance(raw, list):
        raise SystemExit(f"{where}: a list of {{\"kind\": <the warning's kind>, \"why\": ...}}, not {type(raw).__name__}")
    for i, a in enumerate(raw):
        if not isinstance(a, dict) or set(a) - {"kind", "why", "detail"} or not isinstance(a.get("kind"), str) or not a["kind"].strip():
            raise SystemExit(f"{where}[{i}]: {{\"kind\": <the warning's kind, as the report names it>, \"why\": ..., \"detail\": <optional words of its detail>}}, not {a!r}")
        if plan._words(a.get("why") or "") < 3:
            raise SystemExit(f"{where}[{i}]: why, in words: the reason the page does what the warning names")
        if "detail" in a and not (isinstance(a["detail"], str) and a["detail"].strip()):
            raise SystemExit(f"{where}[{i}]: detail is words the warning's detail holds")
    return raw


def answer_warnings(slide: dict, entry: dict) -> None:
    """Mark each warning the page answers (read_answers) as answered, with its why: it stays
    in the report and the brief, read as answered rather than open. A refusal is never
    answered (it is fixed), and an answer that names no warning on the page is itself a
    warning: the page changed and the answer is stale."""
    problems = entry.setdefault("problems", [])
    found = list(problems)  # the page's own problems: what answering adds below is never itself answerable
    for a in read_answers(slide):
        hits = [p for p in found if p.get("kind") == a["kind"] and a.get("detail", "") in str(p.get("detail", ""))]
        if any(p.get("severity") == "refusal" for p in hits):
            problems.append({"kind": "answer to a refusal", "severity": "refusal",
                             "detail": f"answered names {a['kind']!r}, a refusal on this page: a refusal is fixed, never answered"})
            continue
        if not hits:
            kinds = sorted({str(p.get("kind")) for p in found if p.get("severity") != "refusal"})
            problems.append({"kind": "answer names no warning", "severity": "warning",
                             "detail": f"answered {a['kind']!r}{' (' + repr(a['detail']) + ')' if 'detail' in a else ''} matches no warning on this page "
                                       f"(its warnings: {kinds or 'none'}): remove the answer, or name the warning as the report does"})
            continue
        for p in hits:
            p["answered"] = a["why"]


def build(deck: dict, guide: dict, template: str, out: str, reference: str | None, others: list[str], renders: str | None, do_render: bool, chrome: str = "auto",
          plan_pages: list[dict] | None = None, plan_check: dict | None = None, briefs: list[str] | None = None, outputs: Outputs | None = None, computed: list[str] | None = None) -> dict:
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
    referenced = plan.has_reference(guide, "--guide")
    from complete_guide import core_open
    if open_core := core_open(guide):
        raise SystemExit(f"--guide: core addresses still open {open_core}: a guide written with --allow-partial is for inspection, never "
                         "built; answer them with complete_guide.py and build the guide it writes")
    if reference and not referenced:
        raise SystemExit("--reference: the guide was made with no reference (extract_style.py --blank), so there is no reference deck to "
                         "compare with; build without --reference, or make the guide from this deck with extract_style.py")
    if reference:
        from ooxml import fingerprint_deck, ink_backings
        ref_slides = fingerprint_deck(reference)
        precedent = ink_backings(ref_slides, reference if str(reference).lower().endswith(".pdf") else None)
    pages: list[tuple[int, list[dict]]] = []  # (deck page number, flattened elements) of every emitted page
    emitted: list[dict] = []  # the report entry of every emitted page, in emit order
    annotation_pages: dict[int, list[dict]] = {}  # emitted page index -> its annotations as resolved
    for slide in deck["slides"]:
        read_answers(slide)  # a malformed answer refuses before anything is solved
    for number, slide in enumerate(deck["slides"], 1):
        try:
            spec_raw, ctx, outcome = solve_slide(slide, guide, chrome, lg, ruler, index, api)
            entry = {"id": slide.get("id"), "status": outcome.status, "attempts": [a.summary() for a in outcome.attempts]}
            entry["layout_depth"] = {"deepest": len(ctx.spec.deepest) - 1, "chain": " > ".join(ctx.spec.deepest), "runaway_bound": L.MAX_TREE_DEPTH}
            layout_taken = L.defaults_taken(spec_raw["root"]) + bullet_indents_taken(slide, ctx.spec, guide)
            if layout_taken:
                entry["layout_defaults_taken"] = layout_taken
            if slide.get("component_notes"):
                entry["component_notes"] = sorted(set(slide["component_notes"]))
            # every table choice neither the spec nor the guide states, as the chart's are listed
            taken = {t["id"]: table_defaults_taken(table_element(t, (slide.get("styling") or {}).get(t["id"]) or {}), EmitGuide(guide))
                     for t in table_nodes(spec_raw["root"])}
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
                held = band // pitch
                entry["reason"] = (f"title needs {sum(len(m.lines) for m in title_rows)} lines; the band above the top rule "
                                   f"({band / EMU_PER_INCH:.2f} in) holds {held} line{'' if held == 1 else 's'} at {title_rows[0].entry.size_pt}pt, "
                                   f"so it does not fit. Shorten the title, or move a clause of it to where the reference states claims "
                                   f"({claim_places(guide)})")
            elif outcome.status != "fit":
                # the brief names the cause on the page's own line, not only in the JSON. The
                # cause is the page at FULL scale first: at the smallest scale tried the page
                # is shrunk, and what crosses then (a heading over a rule) is the shrinking's
                # effect, not the cause (a sidebar 0.09 in too tall read as the headings: round 7)
                import copy
                _, full_ctx, full = solve_slide(copy.deepcopy(slide), guide, chrome, lg, ruler, index, api, L.Fraction(1))
                entry["why_not_full_scale"] = full_scale_cause(full_ctx, full)
                causes = full_scale_cause(ctx, outcome)
                first = entry["why_not_full_scale"][0]
                entry["reason"] = (f"at full scale: {first}"
                                   + ("" if causes[0] == first else f"; at the smallest scale tried ({float(outcome.resolved.scale):.2f}): {causes[0]}")
                                   + " (every cause under slides[].why_not_full_scale and slides[].violations)")
            resolved = L.resolved_json(ctx, outcome.resolved)
            entry["scale"] = resolved["scale_float"]
            entry["violations"] = resolved["violations"]
            entry["text_lines"] = {k: v["lines"] for k, v in resolved["elements"].items() if v.get("kind") == "text"}
            # the fitter's row prefix is relative to the PROBE box; after the intrinsic pass the
            # containment check is the verdict, so on a page that fit clean every body row fits.
            # One shape on every page: the keys are there whether or not the page fit
            clean = outcome.status == "fit" and not resolved["violations"]
            entry["tables"] = {k: {"rows": len(v["tr_h"]), "height_emu": v["total_height_emu"], "column_widths_emu": v["gridCol_w"],
                                   "fitting_row_prefix": len(v["tr_h"]) - v["header_rows"] if clean else v["fitting_row_prefix"],
                                   "width_deficit_emu": v["width_deficit_emu"], "column_deficits_emu": v["column_deficits_emu"]}
                               for k, v in resolved["elements"].items() if v.get("kind") == "table"}
            if outcome.status == "unfittable":
                entry["unfittable"] = L.outcome_json(ctx, outcome).get("unfittable")
            elements = flatten(slide, resolved, spec_raw, guide)
            if slide.get("_image_defaults"):
                entry["image_defaults_taken"] = slide["_image_defaults"]
            annotation_problems: list[dict] = []
            if slide.get("annotations") is not None:
                # resolved on the solved page: anchored to the hosts' boxes, measured at the page's scale
                elements, placed, annotation_problems = annotate.resolve(slide["annotations"], elements, ctx, outcome.resolved.scale, guide,
                                                                         spec_raw["page"].get("reserved_zones") or [])
                entry["annotations"] = placed
            entry["density"] = density_of(elements, resolved, guide, spec_raw)
            breaks, unread, spills = chart_label_breaks(elements, ctx)
            if breaks or unread or spills:
                entry["chart_label_breaks"] = {"findings": breaks, "unmeasured": unread, "spills": spills}
            entry["problems"] = page_problems(entry, elements, resolved, guide, unmeasured_presets(elements) + label_interval_divergence(elements) + annotation_problems + [
                {"kind": "chart label breaks mid-word", "severity": "refusal",
                 "detail": f"{b['chart']} {b['part']}: {b['word']!r} at {b['size_pt']}pt measures {b['width_emu']} EMU, wider than the {b['limit_emu']} EMU it wraps to at most"}
                for b in breaks] + [
                {"kind": "chart label wider than its bar", "severity": "warning",
                 "detail": f"{b['chart']} {b['part']}: {b['text']!r} at {b['size_pt']}pt measures {b['width_emu']} EMU on one line, past its "
                           f"{b['bar_emu']} EMU bar: it is drawn over the bar's ends and what lies beyond them"}
                for b in spills], chrome, precedent, slide_chrome(slide, guide, chrome))
            entry["title"], title_warnings = title_report(slide, spec_raw, elements, entry, guide)
            entry["problems"][:0] = title_warnings + plan_message_figures(slide, elements, plan_pages)  # warnings first, as the tie-outs are
        except L.FaceRefused as error:
            # the guide's faces cannot measure this page as the renderer draws it: the page is
            # refused by name in the report, not solved in another face and not a traceback
            report["slides"].append({"id": slide.get("id"), "status": "unfittable", "solver_status": None, "reason": "font refused",
                                     "problems": [{"kind": "font refused", "severity": "refusal", "detail": str(error)}]})
            continue
        pages.append((number, elements))
        emit_spec["slides"].append({"layout": slide.get("layout"), "notes": slide.get("notes"), "elements": elements,
                                    **({"chrome": slide["chrome"]} if slide.get("chrome") is not None else {})})
        report["slides"].append(entry)
        if "annotations" in entry:
            annotation_pages[len(emitted)] = entry["annotations"]
        emitted.append(entry)
    sourced = [(e["id"], e["source_line"]) for e in emitted if "source_line" in e]
    report["source_lines"] = {"reference": source_line_habit(guide),
                              "deck": {"data_pages": sum(1 for _, s in sourced if s["data_page"]),
                                       "with_source_line": [i for i, s in sourced if s["source_line"]],
                                       "data_pages_without": [i for i, s in sourced if s["data_page"] and not s["source_line"]]}}
    report["position_drift"] = position_drift(pages, guide)
    emit_report = emit_slides(emit_spec, template, guide, out, chrome)
    # variety after the write: each page's exhibit structure is read off the file, as the reference's was
    structures, structures_unread = emitted_structures(out, [n for n, _ in pages], guide, deck["slides"])
    report["repetition"] = repetition_of(pages, guide, plan_pages, {n: deck["slides"][n - 1].get("id") for n, _ in pages},
                                         structures, plan_check, structures_unread or BUILD_UNREAD)
    briefs_against_file(pages, emitted, {n: deck["slides"][n - 1].get("id") for n, _ in pages}, plan_pages, structures, structures_unread)
    report["emitted_slides"] = len(emit_report["slides"])
    # the file as written, measured against the boxes it was solved for
    for entry, found in zip(emitted, emitted_fit(out, emitted, emit_spec["slides"], guide, L.Context(lg, ruler, index))):
        if not found:
            continue
        entry["problems"].extend({"kind": "emitted text overflows", "severity": "refusal", "detail": f"{f['shape']}: {f['detail']}"} for f in found)
        if entry["status"] == "fit":
            entry["status"], entry["reason"] = "unfittable", "emitted text overflows"
    n_ref = (guide.get("reference") or {}).get("slides")
    report["chrome"] = {**emit_report["chrome"], "drawn": [page["chrome_drawn"] for page in emit_report["slides"]],
                        # the reference's chrome every page starts from, with its counts; a page leaves one off or sets other words with a why (slide.chrome)
                        "reference": [{"chrome_id": ch["chrome_id"], "kind": ch["kind"], "text": chrome_text(ch), "on": f"{ch.get('slides_present')} of {n_ref} reference pages"}
                                      for ch in chrome_on_page(guide, chrome)] if referenced else plan.NO_REFERENCE}
    for entry, page in zip(emitted, emit_report["slides"]):
        if page.get("charts"):
            # every chart choice the spec left out, with the value written for it
            entry["chart_defaults_taken"] = {c["id"]: c["defaults_taken"] for c in page["charts"]}
        if page.get("defaults_taken"):
            # every other value the file got that neither the spec nor the guide states
            entry["emit_defaults_taken"] = page["defaults_taken"]
        if page.get("chrome_choices"):
            entry["chrome_choices"] = page["chrome_choices"]
    from pptx_tools import validate
    report["validation"] = validate(out, render=False)
    # the chrome the build drew is the reference's furniture, as the template's own text is: on a
    # raster reference the past deck's copy of it is OCR text and never reads as chrome there
    furniture = [t for t in (chrome_text(ch) for ch in chrome_on_page(guide, chrome)) if t]
    report["leakage"] = leakage_of(out, reference, guide, briefs or [], template, [e.get("id") for e in emitted], computed, furniture)
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
        if do_render:
            try:
                if not Path(pdf).exists():
                    raise annotate.RenderUnread("the render wrote no PDF")
                words = annotate.pdf_words(pdf)
                if len(words) < len(emitted):
                    raise annotate.RenderUnread(f"the PDF has {len(words)} page(s) for {len(emitted)} emitted page(s)")
            except annotate.RenderUnread as error:
                unread = str(error)
        if unread is None:
            # every solved text box against the lines the renderer drew it in
            offset = len(words) - len(emitted)
            for entry, found in zip(emitted, drawn_lines(out, emitted, emit_spec["slides"], words[offset:]), strict=True):
                entry["drawn_lines"] = found["checked"]
                for f in found["wrapped"]:
                    entry["problems"].append({"kind": "renderer divergence: text wrapped", "severity": "refusal", "detail": f})
                if found["wrapped"] and entry["status"] == "fit":
                    entry["status"], entry["reason"] = "unfittable", "renderer divergence: text wrapped"
        else:
            for entry in emitted:
                entry["drawn_lines"] = f"not checked: the render's words were not read ({unread})"
        if unread is not None and annotation_pages:
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
        # page is filed under the reference only when all three hold, and never when the judge
        # could not read the reference.
        all_fit = all(sl.get("status") == "fit" and not sl.get("violations") for sl in report["slides"])
        judge["filed_under_reference"] = None if "cannot_judge" in judge else (
            bool(judge["nearest_is_reference"]) and bool(judge["within_reference_spread"]) and judge["layout_clean"]
            and all_fit and bool(report.get("validation", {}).get("ok")))
        report["judge"] = judge
    elif not referenced:
        report["judge"] = {"verdict": plan.NO_REFERENCE, "why": "the judge measures a deck's distance to its reference; this guide was made with none"}
    for entry, page in zip(emitted, emit_spec["slides"], strict=True):
        entry["problems"].extend(off_ladder_problems(page["elements"], guide, report.get("judge")))
    for slide, entry in zip(deck["slides"], report["slides"], strict=True):
        answer_warnings(slide, entry)
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
    for name in ("brief", "computed"):
        for value in getattr(args, name, None) or []:
            import cli
            cli.in_path(value, f"--{name.replace('_', '-')}")
    deck = json.loads(Path(args.deck).read_text())
    guide = json.loads(Path(args.guide).read_text())
    plan_pages = None
    plan_check = None
    if args.plan:
        # the plan gate is plan.py check's, whole: a plan it refuses is not built
        plan_json = json.loads(Path(args.plan).read_text())
        plan_check = plan.check(plan_json, guide)
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
        plan.reference_variety(guide)  # the guide proven before the solve, not after it
    return build(deck, guide, args.template, args.out, args.reference, args.others, args.renders, not args.no_render, args.chrome, plan_pages,
                 plan_check, args.brief, outputs, args.computed)


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
        warns = [p for p in problems if p.get("severity") != "refusal" and "answered" not in p]
        answered = [p for p in problems if p.get("severity") != "refusal" and "answered" in p]
        scale = f" scale {s['scale']:.2f}" if isinstance(s.get("scale"), float) else ""
        lines.append(f"page {s.get('id')}: {s.get('status')}{scale}" + (f" ({s['reason']})" if s.get("reason") else "")
                     + (f"; {len(refusals)} refusal(s), {len(warns)} open warning(s)" + (f", {len(answered)} answered" if answered else "") if problems else ""))
        for p in (refusals + warns)[:4]:
            lines.append(f"  {p.get('severity', 'note')}: {p.get('kind')}: {str(p.get('detail', ''))[:240]}")
        for p in answered[:max(0, 4 - len(refusals + warns))]:
            lines.append(f"  answered: {p.get('kind')}: {str(p['answered'])[:200]}")
        if len(problems) > 4:
            lines.append(f"  ... {len(problems) - 4} more in the report (slides[].problems)")
        counts = {name: sum(len(v) for v in (s.get(f"{name}_defaults_taken") or {}).values()) for name in ("chart", "table", "emit")}
        counts["layout"] = len(s.get("layout_defaults_taken") or [])
        if any(counts.values()):
            lines.append("  defaults taken: " + ", ".join(f"{n} {name}" for name, n in counts.items() if n)
                         + " (slides[].<kind>_defaults_taken): write each choice you mean, or name it in the report as intended")
    rep = report.get("repetition") or {}
    ah = rep.get("against_reference") or {}
    if isinstance(ah.get("composition_V"), dict):
        cv, sv, kv = ah["composition_V"], ah.get("structures_V") or {}, ah.get("kinds_V") or {}

        def beside(v: dict) -> str:
            return f"reference {v['reference_V']}" if "reference_V" in v else str(v.get("verdict"))
        lines.append(f"variety: composition V {cv.get('value')} ({beside(cv)}), exhibit structure V {sv.get('value')} "
                     f"({beside(sv)}), exhibit kinds V {kv.get('value')} ({beside(kv)}), "
                     f"longest run {(ah.get('longest_run') or {}).get('built')} "
                     f"(reference {(ah.get('longest_run') or {}).get('reference')})")
    lines += [f"  variety warning: {w}" for w in rep.get("warnings") or []]
    differing = ((rep.get("plan") or {}) if isinstance(rep.get("plan"), dict) else {}).get("pages_differing_from_plan") or []
    lines += [f"  differs from plan: {d.get('id')}: {d.get('detail')}" for d in differing]
    src = report.get("source_lines") or {}
    if src:
        deck_src = src["deck"]
        lines.append(f"source lines: reference {src['reference']['habit']}: {src['reference']['evidence']}; this deck: {len(deck_src['with_source_line'])} page(s) carry one "
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
        hs = judge.get("reference_spread") or {}
        lines.append(f"judge: total {judge['total']} (reference's own pages: median {hs.get('median')}, p90 {hs.get('p90')}, max {hs.get('max')}); nearest is the reference: "
                     f"{judge.get('nearest_is_reference')}; filed under the reference: {judge.get('filed_under_reference')} (necessary, not sufficient)")
    elif judge.get("cannot_judge"):
        lines.append(f"judge: cannot judge: {judge['cannot_judge']}")
    elif judge.get("verdict") == plan.NO_REFERENCE:
        lines.append(f"judge: {plan.NO_REFERENCE}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
