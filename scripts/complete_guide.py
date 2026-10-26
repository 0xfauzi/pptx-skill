#!/usr/bin/env python3
"""Apply the model's completion patch to a style guide draft, deterministically.

    complete_guide.py draft.json patch.json -o guide.json [--allow-partial] [--digest work/ref/digest]
    complete_guide.py guide.json --check            # what is still open

The model (Claude, reading the evidence digest and the renders) answers the draft's
`unresolved` entries in patch.json. This script folds them in and refuses anything the
cascade forbids. The patch answers the open set and nothing else: a path is writable only
when the draft lists it under `unresolved`, or when it is always writable (ALWAYS_WRITABLE,
/notes*, /extra_roles/<new name>, or a NEW type role at a size level the reference writes).
Any path whose target carries value_provenance observed or deterministic_inference is
refused, naming the address and its provenance. A colour the patch names must be a role in
the guide (hexes are allowed ONLY under `color.roles` and `extra_roles`, which is where new
colours enter); a type size may not sit below the family's floor. Patched values carry
provenance `model_inference`. What the patch leaves open stays listed, so nothing closes
by silence; a CORE address still open after the patch refuses the guide unless
--allow-partial, which lists it: an address left out is as wrong as one invented.

Patch shape: {"<unresolved path>": <value>, ...}. Paths are JSON-pointer-like with the
draft's spelling, e.g. "/typography/roles/type.footnote", "/color/roles/color.accent3",
"/tables", "/charts", "/description", "/derivation_rules", "/continuation",
"/typography/roles/type.h1/members" (a dict of the missing members),
"/typography/roles/type.body/line_spacing", "/spacing/baseline_emu". A colour, under
/color/roles or /extra_roles, is "RRGGBB" or {"hex": "RRGGBB", "why": "..."}. null answers
line_spacing (single spacing), /typography/scale_ratio (not a geometric ladder),
/spacing/baseline_emu and /density_bands/table_rows_per_inch, and closes them. On a
raster draft (no levels table) a new type role is writable when its value carries
"provenance": "raster_inference".
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan  # noqa: E402
from emit_pptx import GUIDE_LEGEND_POSITIONS  # noqa: E402

HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
#: TARGET_SPEC Appendix A as closed sets: the title register, the title companions and the exhibit digest fields.
VOCABULARY = json.loads((Path(__file__).resolve().parent.parent / "references" / "page_craft_vocabulary.json").read_text())
# the extractor never observes these, so they are always the model's to write
ALWAYS_WRITABLE = {"/description", "/derivation_rules", "/continuation", "/typography/families/substitutes"}
SETTLED = {"observed", "deterministic_inference"}
CORE_ROLES = ("/typography/roles/type.title", "/typography/roles/type.body", "/color/roles/color.surface",
              "/color/roles/color.ink", "/color/roles/color.accent1")
# at least one of these must be closed
CORE_ANNOTATION = ("/typography/roles/type.caption", "/typography/roles/type.footnote", "/typography/roles/type.source_line")
# whole-section paths the apply step knows how to write; each is writable only when open
#: A hand-written chrome entry (a raster draft opens /chrome whole): the keys the emitter
#: and the build read (emit_pptx.draw_chrome, chrome_on_page, build_deck.chrome_zones), so
#: an entry that would draw nothing is refused here instead of drawing nothing in silence.
CHROME_KINDS = ("rule", "band", "logo", "label", "page_number", "footer", "date")
CHROME_REQUIRED = ("chrome_id", "kind", "box_in", "slides_present")
CHROME_OPTIONAL = {"text", "text_style", "fill_hex", "fill_role", "line_hex", "line_role", "line_width_pt", "rotation_deg", "anchor",
                   "layers", "image_path", "paint_order", "why"}
CHROME_ANCHORS = ("slide_top", "slide_bottom", "slide_left", "slide_right")
CHROME_SHAPE = ('a list of {"chrome_id": "chrome-1", "kind": "' + "|".join(CHROME_KINDS) + '", "box_in": [left, top, width, height] '
                '(inches on the page), "slides_present": <pages it is on, at least half the reference\'s to be drawn>, and as the kind needs: '
                '"text" (label, footer, date; "<page number>" marks the number), "text_style": {"family", "size_pt", "bold", "ink_hex"}, '
                '"fill_hex" or "fill_role" (band; a logo placeholder), "line_hex" or "line_role" with "line_width_pt" (rule), "image_path" (logo), '
                '"anchor": "' + "|".join(CHROME_ANCHORS) + '", "rotation_deg", "why"}')


SECTION_PATHS = {"/description", "/derivation_rules", "/continuation", "/tables", "/charts", "/imagery", "/shape_language/icon_style",
                 "/color/accent_stepping", "/gallery", "/exemplars", "/spacing/baseline_emu",
                 "/typography/scale_ratio", "/density_bands/table_rows_per_inch", "/typography/families/substitutes"}
TYPE_MEMBERS = {"size_pt", "weight", "italic", "family", "alignment", "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt", "case", "ink_role"}
FLOOR_FAMILY = {}
for fam, roles in {"body": ("type.body", "type.emphasis", "type.h1", "type.h2", "type.table_header", "type.table_cell"),
                   "annotation": ("type.kicker", "type.caption", "type.footnote", "type.source_line"),
                   "display": ("type.title",), "chart": ("type.axis_label", "type.data_label")}.items():
    for r in roles:
        FLOOR_FAMILY[r] = fam


class PatchError(SystemExit):
    pass


#: The value every open address takes: (address pattern, shape, what null means or None
#: when null is refused). `--check` prints the line for each open address, and
#: references/guide-completion.md carries this table as printed by `--shapes`.
TYPE_ROLE_SHAPE = ('{"size_pt", "weight", "italic", "family", "alignment", "case", "ink_role", "why"}; optional '
                   '"line_spacing", "space_before_pt", "space_after_pt", "tracking_pt"')
COLOR_SHAPE = '{"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures'
PICTURES_NOTE = '; add "evidence": "pictures" when the house sets such text only inside pasted pictures'
#: the one value of a completion's "evidence" member: the answer is read off pictures the
#: house pasted (a chart or table as an image), not off its text or shapes
PICTURES = "pictures"
VALUE_SHAPES: tuple[tuple[str, str, str | None], ...] = (
    (r"/color/roles/color\.(surface|ink|accent1)", COLOR_SHAPE, None),
    (r"/color/roles/color\.emphasis", COLOR_SHAPE,
     ('the house marks emphasis in no colour of its own (in its ink or rule colour, or not at all): recorded under absent_roles, '
      'and an annotation names the ink or rule role instead')),
    (r"/color/roles/[^/]+", COLOR_SHAPE,
     ('the house has no such colour, not even inside its pictures: the role is recorded under absent_roles, and a page that names it is '
      'refused. A colour seen only inside pasted pictures is not absent: answer it with "evidence": "pictures"')),
    (r"/extra_roles/[^/]+", COLOR_SHAPE, None),
    (r"/typography/roles/type\.(title|body)", TYPE_ROLE_SHAPE, None),
    (r"/typography/roles/[^/]+/members", ('the open members only: any of "weight", "italic", "family", "alignment", "case", "ink_role", '
     '"line_spacing", "space_before_pt", "space_after_pt", "tracking_pt", plus "why"; never "size_pt"'), None),
    (r"/typography/roles/[^/]+/line_spacing", 'a multiple of the size, e.g. 1.2 ("/typography/roles/*/line_spacing": v answers every open one not named)',
     "single spacing (drawn at 1.2 x size)"),
    (r"/typography/roles/[^/]+", TYPE_ROLE_SHAPE + PICTURES_NOTE,
     ('the house has no such text anywhere, not even inside its pictures: recorded under absent_roles; a page that names the role is '
      'refused. Text the house sets only inside pasted pictures (axis labels on a chart image) is not absent: answer the value read off '
      'the pictures with "evidence": "pictures". One of type.caption, type.footnote, type.source_line must stay answered')),
    (r"/typography/families", '{"major": "<face>", "minor": "<face>"}', None),
    (r"/typography/families/substitutes", '{"<face named in the file>": "<installed face measured in its place>"}', None),
    (r"/typography/scale_ratio", "a number, e.g. 1.25", "the levels are not a geometric ladder"),
    (r"/spacing/steps/[^/]+", "an integer EMU", None),
    (r"/spacing/steps", '{"space.xs": EMU, "space.sm": EMU, "space.md": EMU, "space.lg": EMU, "space.margin": EMU, "space.gutter": EMU} '
     '(integers; space.xs, space.sm, space.margin and space.gutter are required: the round trip and the components read them)', None),
    (r"/spacing/baseline_emu", "an integer EMU", "no baseline grid"),
    (r"/density_bands/table_rows_per_inch", '{"metric": "table_rows_per_inch", "low", "high", "median", "n"}', "no table to measure"),
    (r"/floors/[^/]+/floor_pt", "a number of points, never below absolute_floor_pt", "no run in this family: the absolute floor holds"),
    (r"/shape_language/corner_radii", '{"modal_radius_emu": int, "rounded_share": 0..1, "why": "..."}', None),
    (r"/shape_language/icon_style", 'a string, e.g. "none" or "white line icons in accent circles"', None),
    (r"/imagery/register_kind", 'a string, e.g. "photographs, wide crops" or "none"', None),
    (r"/tables", ('{"header_fill_role", "header_ink_role", "header_bold", "banding_role", "edge_rules": {"table_top", "header_bottom", '
     '"row_interior", "table_bottom", "table_left", "table_right", "column_interior": {"width_pt", "color_role"} or {"none": true}}, '
     '"cell_padding_role", "alignment_by_column_type": {"numeric", "text"}, "totals_rule", "merged_cell_convention", "why"}'), None),
    (r"/charts", ('{"series_color_roles": [roles in order], "per_kind": {"<bar|column|line|...>": {"gridlines_major": 0..1, '
     '"data_labels": 0..1, "legend_position": "' + "|".join(GUIDE_LEGEND_POSITIONS) + '"}}, "why"}'), None),
    (r"/continuation", '{"header_repeat": "full|none", "contd_mark": "<text>", "takeaway_policy": "repeat|first_only|none"}', None),
    (r"/description", '{"summary", "typography", "color", "layout", "tables", "imagery", "motifs", "never_does": [...], "tone"}', None),
    (r"/derivation_rules", "a list of sentences", None),
    (r"/titles/register", "see Titles below", None),
    (r"/variety/content_pages", "a list of page numbers", None),
    (r"/exhibit_habits", "never in the patch: answered by --digest DIR", None),
    (r"/chrome", CHROME_SHAPE, None),
    (r"/composition", '{"archetypes": [{"archetype_id": "arch-1", "slides": [page numbers], "description": "<the arrangement in words>"}], "why"}', None),
    (r"/notes/[^/]+", "a string", None),
)
#: the spacing steps the round trip (import_slide) and the components read by name
SPACING_STEPS_NEEDED = ("space.margin", "space.gutter", "space.xs", "space.sm")
TABLE_KEYS = {"header_fill_role", "header_ink_role", "header_bold", "banding_role", "edge_rules", "cell_padding_role", "cell_padding_emu",
              "alignment_by_column_type", "totals_rule", "merged_cell_convention", "why", "provenance"}
CHART_KEYS = {"series_color_roles", "per_kind", "why", "provenance"}
ABSENT_SHAPE = "absent_roles"


def value_shape(path: str) -> tuple[str, str | None] | None:
    for pattern, shape, null in VALUE_SHAPES:
        if re.fullmatch(pattern, path):
            return shape, null
    return None


def shape_error(path: str, value) -> str | None:
    """The answer's shape against the address's, before anything is applied: a null where
    null is refused names what to write instead; a /tables or /charts key nothing reads is
    refused by name, so a key cannot look like a setting it is not."""
    found = value_shape(path)
    if found is None:
        return None
    shape, null = found
    if value is None:
        if null is None:
            return f"{path}: null is not an answer here; write {shape}"
        return None
    if path in ("/tables", "/charts"):
        if not isinstance(value, dict):
            return f"{path}: expected {shape}"
        keys = TABLE_KEYS if path == "/tables" else CHART_KEYS
        stray = sorted(set(value) - keys)
        if stray:
            return (f"{path}: {stray} {'is' if len(stray) == 1 else 'are'} read by nothing; {path} takes {sorted(keys - {'provenance'})}. "
                    "A source-line habit is not a chart setting: it is measured from the digest (each page's source_line)")
        if path == "/charts":
            per_kind = value.get("per_kind") or {}
            bad = {k: v.get("legend_position") for k, v in per_kind.items() if isinstance(v, dict) and "legend_position" in v
                   and v["legend_position"] not in GUIDE_LEGEND_POSITIONS}
            if bad:
                return (f"/charts: legend_position {bad} not in {list(GUIDE_LEGEND_POSITIONS)}; a chart spec writes the same "
                        "word as legend.position, and \"none\" as legend: \"none\"")
    return None


def model_prov(note: str = "", value=None) -> dict:
    """Completion provenance. A patch value may carry provenance "raster_inference" with a
    confidence of at most 0.5: raster_style.py's measurements on page images are inference
    from pixels, never observation, and the cap keeps them below any observed value."""
    kind, confidence = "model_inference", 0.5
    if isinstance(value, dict) and value.get("provenance") == "raster_inference":
        kind = "raster_inference"
        confidence = min(0.5, float(value.get("confidence", 0.5)))
    return {"value_provenance": kind, "role_provenance": "inferred", "evidence": [note] if note else [], "frequency": 0,
            "master_membership": False, "confidence": confidence}


def floor_for(guide: dict, role: str) -> float:
    fam = FLOOR_FAMILY.get(role, "body")
    f = (guide.get("floors") or {}).get(fam) or {}
    observed = f.get("floor_pt")
    absolute = f.get("absolute_floor_pt") or 0.0
    return max(float(observed) if observed else 0.0, float(absolute))


def check_color_refs(guide: dict, value, where: str) -> None:
    roles = set((guide.get("color", {}).get("roles") or {}).keys()) | set((guide.get("extra_roles") or {}).keys())
    if isinstance(value, dict):
        for k, v in value.items():
            if k.endswith("_role") and isinstance(v, str) and v.startswith("color."):
                if v not in roles:
                    raise PatchError(f"{where}: {k} names {v!r}, not a colour role in the guide ({sorted(roles)})")
            elif k.endswith("_hex") or k == "hex":
                raise PatchError(f"{where}: literal colour under {k}; add it under /color/roles/<role> or /extra_roles/<name> and refer to the role")
            else:
                check_color_refs(guide, v, f"{where}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            check_color_refs(guide, v, f"{where}[{i}]")


def node_at(guide: dict, path: str):
    node = guide
    for key in [q for q in path.split("/") if q]:
        node = node.get(key) if isinstance(node, dict) else None
    return node


def settled_on(guide: dict, path: str) -> tuple[str, str, list] | None:
    """The deepest node on the path (the target itself included) whose provenance is
    observed or deterministic_inference: (address, value_provenance, evidence)."""
    parts = [q for q in path.split("/") if q]
    found, node = None, guide
    for depth, key in enumerate(parts, 1):
        if not isinstance(node, dict) or key not in node:
            break
        node = node[key]
        prov = node.get("provenance") if isinstance(node, dict) else None
        if isinstance(prov, dict) and prov.get("value_provenance") in SETTLED:
            found = ("/" + "/".join(parts[:depth]), prov["value_provenance"], list(prov.get("evidence") or [])[:3])
    return found


def check_writable(guide: dict, path: str, value, open_paths: dict) -> None:
    settled = settled_on(guide, path)
    if settled and settled[0] == path:
        raise PatchError(f"{path}: target carries value_provenance {settled[1]} (evidence {settled[2]}); observed and "
                         f"deterministically inferred values are never overwritten")
    if path in open_paths or path in ALWAYS_WRITABLE or path.startswith("/notes") or path.startswith("/extra_roles/"):
        return
    # a NEW text role may be added at a size the reference actually writes: the
    # levels table had 14, 16, 18 and 20pt with 270 votes and no role on one deck,
    # and "use the levels the histogram shows" could not be followed without this
    parts = [q for q in path.split("/") if q]
    levels = {float(lv.get("size_pt")) for lv in guide.get("typography", {}).get("levels", []) if lv.get("size_pt")}
    new_role = (len(parts) == 3 and parts[0] == "typography" and parts[1] == "roles" and parts[2] not in guide["typography"]["roles"]
                and isinstance(value, dict) and value.get("size_pt") is not None)
    if new_role and float(value["size_pt"]) in levels:
        return
    # a raster reference has no levels table (its text layer is not type evidence), so a
    # size can only be read off the pixels: raster_style.py's run heights. A new role there
    # is writable when it says so, and it carries raster_inference provenance at <= 0.5
    raster = (guide.get("reference", {}).get("text_layer") or {}).get("status") == "raster"
    if new_role and raster and value.get("provenance") == "raster_inference":
        return
    under = f"; it sits under {settled[0]}, value_provenance {settled[1]}" if settled else ""
    raise PatchError(f"{path}: not an open address{under}. A patch answers the draft's unresolved list and nothing else (a new "
                     f"type role needs a size the reference writes, levels {sorted(levels)}"
                     f"{'; on this raster reference, a new role with provenance raster_inference' if raster else ''}); open: {sorted(open_paths)}")


def _vocab_error(name: str, value, where: str) -> str | None:
    allowed = VOCABULARY[name]
    return None if isinstance(value, str) and value in allowed else f"{where}: {value!r}{plan.nearest(value, allowed)} is not in {name} ({'|'.join(allowed)})"


def title_register(guide: dict, value) -> dict:
    """The model's reading of every title the draft found by position, checked against that
    list: each page title classified once in the closed register vocabulary, each block the
    draft found above or below a title named in the companion vocabulary, nothing added.
    Every omission and every stray key is reported by name in one refusal. The counts are
    computed here, never written by the model."""
    records = [r for r in (guide.get("titles") or {}).get("records") or [] if r.get("placeholder") != "ctrTitle"]
    if not isinstance(value, dict) or not isinstance(value.get("per_title"), dict):
        raise PatchError('/titles/register: expected {"per_title": {"<slide>": register}, "companions": {...}, "claims_elsewhere": {...}, "why": "..."}')
    errors: list[str] = []
    stray = sorted(set(value) - {"per_title", "companions", "claims_elsewhere", "why"})
    if stray:
        errors.append(f"unknown keys {stray}")
    for key in ("companions", "claims_elsewhere"):
        if key in value and not isinstance(value[key], dict):
            errors.append(f"{key}: an object keyed by slide, not {type(value[key]).__name__}")
    given = value.get("companions") if isinstance(value.get("companions"), dict) else {}
    for slide, entry in given.items():
        if not isinstance(entry, dict):
            errors.append(f"companions/{slide}: {{\"above\": ..., \"below\": ...}}, not {type(entry).__name__}")
    given = {k: v for k, v in given.items() if isinstance(v, dict)}
    want = {str(r["slide"]): r for r in records}
    per = value["per_title"]
    errors += [f"per_title: slide {k} ({want[k]['text']!r}) is not classified" for k in want if k not in per]
    errors += [f"per_title: slide {k} has no title found by position" for k in per if k not in want]
    errors += [e for k, v in per.items() if k in want for e in [_vocab_error("title_register", v, f"per_title/{k}")] if e]
    found = {(str(r["slide"]), pos): r[pos]["text"] for r in records for pos in ("above", "below") if r.get(pos)}
    for (slide, pos), text in found.items():
        if pos not in (given.get(slide) or {}):
            errors.append(f"companions: slide {slide} {pos} ({text!r}) is not named")
    for slide, entry in given.items():
        for pos, kind in entry.items():
            if (slide, pos) not in found:
                errors.append(f"companions: slide {slide} has no block {pos} its title")
            else:
                e = _vocab_error(f"title_companion_{pos}", kind, f"companions/{slide}/{pos}")
                if e:
                    errors.append(e)
    claims = value.get("claims_elsewhere") if isinstance(value.get("claims_elsewhere"), dict) else {}
    for slide, where in claims.items():
        if per.get(slide) != "topic":
            errors.append(f"claims_elsewhere: slide {slide} is not a topic title")
        elif where is not None and not (isinstance(where, str) and where.strip()):
            errors.append(f"claims_elsewhere/{slide}: a place in words, or null when the page states no claim")
    if errors:
        raise PatchError("/titles/register: " + "; ".join(errors))
    counts = {k: sum(1 for v in per.values() if v == k) for k in VOCABULARY["title_register"]}
    return {"counts": counts, "n": len(per), "per_title": dict(sorted(per.items(), key=lambda kv: int(kv[0]))),
            "companions": given, "companion_counts": {pos: dict(Counter(e[pos] for e in given.values() if pos in e)) for pos in ("above", "below")},
            "claims_elsewhere": claims, "why": value.get("why"), "provenance": model_prov(value.get("why") or "")}


#: the moves an annotation can draw with no words of its own (outline, fill, line,
#: bracket): on these the digest answers whether the house labelled the mark
MARK_MOVE_SET = frozenset(m for moves in VOCABULARY["annotation_kind_moves"].values() for m in moves)
EXHIBIT_KEYS = {"candidate", "class", "type", "data_shape", "message", "message_kind", "annotation_moves", "emphasis_devices",
                "number_formats", "legend", "data_labels", "colour_logic", "why"}
EXHIBIT_SCALARS = (("class", "exhibit_class"), ("type", "exhibit_type"), ("data_shape", "data_shape"), ("message_kind", "message_kind"),
                   ("legend", "legend"), ("data_labels", "data_labels"), ("colour_logic", "colour_logic"))
EXHIBIT_LISTS = (("emphasis_devices", "emphasis_device"), ("number_formats", "number_format"))


def _stub_pages(stub) -> dict[int, list[str]]:
    """The pages the gallery cut, {slide: [candidate ids]}, proven once: a list of objects,
    each slide an integer named once, each candidate id a string named once."""
    pages = stub.get("pages") if isinstance(stub, dict) else None
    if not isinstance(pages, list) or not pages:
        raise PatchError("/exhibit_habits: the digest stub lists no pages; re-run gallery.py digest")
    out: dict[int, list[str]] = {}
    for i, page in enumerate(pages):
        slide = page.get("slide") if isinstance(page, dict) else None
        ids = [c.get("id") if isinstance(c, dict) else None for c in (page.get("candidates") if isinstance(page, dict) else None) or []]
        if not isinstance(slide, int) or isinstance(slide, bool) or slide in out or not all(isinstance(c, str) for c in ids) or len(set(ids)) != len(ids):
            raise PatchError(f"/exhibit_habits: the digest stub's page {i} is not one slide number with distinct candidate ids; re-run gallery.py digest")
        out[slide] = ids
    return out


def exhibit_habits(guide: dict, value, stub) -> dict:
    """The completed digest (gallery.py digest), checked against the stub the gallery cut and
    aggregated. The completed pages are exactly the stub's: a page dropped, repeated or added
    is named, as is a candidate list that differs from the stub's. Every page is answered (an
    empty list states the page holds no exhibit; a missing or null list is an omission); a
    record repeated on its page is named; every exhibit names each field in the closed
    vocabulary, every annotation move with what it anchors to. All omissions are named in
    one refusal. The counts, by type, data shape and message kind, are computed here, and
    the sample is the stub's, never the completed file's."""
    if stub is None:
        raise PatchError("/exhibit_habits: answered only through complete_guide.py --digest DIR, which reads the stub the gallery "
                         "cut (DIR/digest.stub.json) beside the completed copy (DIR/digest.json); a patch value has no stub to be checked against")
    if not isinstance(value, dict) or not isinstance(value.get("pages"), list):
        raise PatchError("/exhibit_habits: expected the completed digest, {\"reference_sha256\", \"pages\": [{\"slide\", \"candidates\", \"exhibits\": [...]}]}")
    sha = (guide.get("reference") or {}).get("sha256")
    for name, got in (("stub", stub.get("reference_sha256") if isinstance(stub, dict) else None), ("completed digest", value.get("reference_sha256"))):
        if got != sha:
            raise PatchError(f"/exhibit_habits: the {name} was cut from {got}, this guide's reference is {sha}")
    want = _stub_pages(stub)
    errors: list[str] = []
    seen: list[int] = []
    answered: list[dict] = []
    for i, page in enumerate(value["pages"]):
        slide = page.get("slide") if isinstance(page, dict) else None
        if not isinstance(slide, int) or isinstance(slide, bool):
            errors.append(f"pages[{i}]: not a page of the stub (slide {slide!r})")
        elif slide not in want:
            errors.append(f"slide {slide}: not a page the stub lists ({sorted(want)})")
        elif slide in seen:
            errors.append(f"slide {slide}: answered more than once")
        else:
            seen.append(slide)
            answered.append(page)
    errors += [f"slide {n}: dropped from the completed digest (the stub lists it)" for n in want if n not in seen]
    records: list[dict] = []
    for page in answered:
        slide = page["slide"]
        exhibits = page.get("exhibits")
        given_ids = [c.get("id") if isinstance(c, dict) else c for c in page.get("candidates") or []]
        if given_ids != want[slide]:
            errors.append(f"slide {slide}: candidates {given_ids} differ from the stub's {want[slide]}")
        if not isinstance(exhibits, list):
            errors.append(f"slide {slide}: exhibits not answered (an empty list states the page has none)")
            continue
        data_page = any(isinstance(ex, dict) and ex.get("class") in plan.DATA_CLASSES for ex in exhibits)
        line = page.get("source_line")
        if data_page and not isinstance(line, bool):
            errors.append(f"slide {slide}: source_line {line!r}; a page holding a data chart or a table answers true or false")
        elif not data_page and line is not None:
            errors.append(f"slide {slide}: source_line {line!r} on a page with no data chart or table; leave it null")
        candidates = set(want[slide])
        # one candidate may hold several exhibits (a grid and the chart beside it), but two
        # records that say the same thing about the same place are one exhibit counted twice
        same = Counter(json.dumps(ex, sort_keys=True) for ex in exhibits)
        errors += [f"slide {slide}: an exhibit is recorded {n} times ({json.loads(k).get('message')!r})" for k, n in same.items() if n > 1]
        for i, ex in enumerate(exhibits):
            where = f"slide {slide} exhibit {i}"
            if not isinstance(ex, dict):
                errors.append(f"{where}: not an object")
                continue
            missing = sorted(EXHIBIT_KEYS - {"candidate", "why"} - set(ex))
            stray = sorted(set(ex) - EXHIBIT_KEYS)
            if missing:
                errors.append(f"{where}: {missing} not answered")
            if stray:
                errors.append(f"{where}: unknown keys {stray}")
            if ex.get("candidate") is not None and not (isinstance(ex["candidate"], str) and ex["candidate"] in candidates):
                errors.append(f"{where}: candidate {ex['candidate']!r} is not one of the stub's for this page ({sorted(candidates)})")
            for key, vocab in EXHIBIT_SCALARS:
                if key in ex:
                    e = _vocab_error(vocab, ex[key], f"{where} {key}")
                    if e:
                        errors.append(e)
            for key, vocab in EXHIBIT_LISTS:
                if key in ex:
                    if not isinstance(ex[key], list):
                        errors.append(f"{where} {key}: a list (empty when there is none)")
                    else:
                        errors += [e for v in ex[key] for e in [_vocab_error(vocab, v, f"{where} {key}")] if e]
            if "message" in ex and not (isinstance(ex["message"], str) and ex["message"].strip()):
                errors.append(f"{where} message: the one message in words")
            moves = ex.get("annotation_moves")
            if "annotation_moves" in ex:
                if not isinstance(moves, list):
                    errors.append(f"{where} annotation_moves: a list of {{\"move\", \"anchor\"}} (empty when the exhibit carries none)")
                else:
                    for j, m in enumerate(moves):
                        if not isinstance(m, dict) or set(m) - {"labelled"} != {"move", "anchor"}:
                            errors.append(f"{where} annotation_moves[{j}]: exactly {{\"move\", \"anchor\"}}, plus \"labelled\" on a mark")
                            continue
                        if m.get("move") in MARK_MOVE_SET and not isinstance(m.get("labelled"), bool):
                            errors.append(f"{where} annotation_moves[{j}]: {m['move']} is a mark: answer labelled, true when words on the exhibit "
                                          "say what it marks (a label beside it, or the figure it rings), false when it stands alone")
                        elif "labelled" in m and m.get("move") not in MARK_MOVE_SET:
                            errors.append(f"{where} annotation_moves[{j}]: labelled is answered only on a mark move ({sorted(MARK_MOVE_SET)})")
                        e = _vocab_error("annotation_move", m["move"], f"{where} annotation_moves[{j}]")
                        if e:
                            errors.append(e)
                        if not (isinstance(m["anchor"], str) and m["anchor"].strip()):
                            errors.append(f"{where} annotation_moves[{j}]: anchor names what the move points at")
            records.append({"slide": slide, **ex})
    if errors:
        raise PatchError(f"/exhibit_habits: {len(errors)} problem{'s' if len(errors) > 1 else ''}: " + "; ".join(errors))

    def count(values) -> dict:
        return dict(sorted(Counter(values).items(), key=lambda kv: (-kv[1], kv[0])))

    pages = answered
    moves = [(r, m["move"]) for r in records for m in r["annotation_moves"]]
    data_pages = [p for p in pages if p.get("source_line") is not None]
    sourced = [p["slide"] for p in data_pages if p["source_line"]]
    return {
        "source_lines": {"data_pages": len(data_pages), "with_source_line": len(sourced), "pages_with": sourced,
                         "pages_without": [p["slide"] for p in data_pages if not p["source_line"]],
                         "share": round(len(sourced) / len(data_pages), 3) if data_pages else None,
                         "definition": "pages holding a data chart or a table, and how many of them carry a source or note line"},
        "sample": {"pages_read": len(pages), "pages_with_exhibits": sum(1 for p in pages if p["exhibits"]),
                   "pages_without": [p["slide"] for p in pages if not p["exhibits"]], "exhibits": len(records),
                   "policy": stub.get("sample_policy") or "every evidence page the digest cut"},
        "classes": count(r["class"] for r in records),
        "types": count(r["type"] for r in records),
        "data_shapes": count(r["data_shape"] for r in records),
        "message_kinds": count(r["message_kind"] for r in records),
        "annotation_moves": count(m for _, m in moves),
        "moves_by_data_shape": {shape: count(m for r, m in moves if r["data_shape"] == shape) for shape in sorted({r["data_shape"] for r in records})},
        "moves_by_message_kind": {kind: count(m for r, m in moves if r["message_kind"] == kind) for kind in sorted({r["message_kind"] for r in records})},
        "marks_labelled": {state: [{"slide": r["slide"], "type": r["type"], "class": r["class"], "move": m["move"], "anchor": m["anchor"]}
                                   for r in records for m in r["annotation_moves"] if m["move"] in MARK_MOVE_SET and m["labelled"] is want]
                           for state, want in (("labelled", True), ("unlabelled", False))},
        "mean_moves_per_exhibit": round(len(moves) / len(records), 2) if records else None,
        "exhibits_without_moves": [f"{r['slide']}:{r.get('candidate')}" for r in records if not r["annotation_moves"]],
        "emphasis_devices": count(d for r in records for d in r["emphasis_devices"]),
        "number_formats": count(f for r in records for f in r["number_formats"]),
        "legend": count(r["legend"] for r in records),
        "data_labels": count(r["data_labels"] for r in records),
        "colour_logic": count(r["colour_logic"] for r in records),
        "records": records,
        "provenance": model_prov(f"exhibit digest of {len(pages)} pages, {len(records)} exhibits"),
    }


def content_pages(guide: dict, value) -> dict:
    """The model's list of the reference's content pages, proven at the boundary: a list of
    slide numbers, each a page of the draft's variety sequence that is not hidden, each named
    once. The house's variety is re-measured over it (plan.house_deck)."""
    listed = {p["slide"]: p["triage"] for p in guide["variety"]["pages"]}
    if not isinstance(value, list) or not value:
        raise PatchError("/variety/content_pages: a non-empty list of slide numbers")
    bad = [v for v in value if not (isinstance(v, int) and not isinstance(v, bool) and v in listed and listed[v] != "hidden")]
    twice = sorted({v for v in value if value.count(v) > 1 and not isinstance(v, bool)})
    if bad or twice:
        raise PatchError(f"/variety/content_pages: {('not visible pages of the sequence ' + str(bad)) if bad else ''}"
                         f"{'; ' if bad and twice else ''}{('named more than once ' + str(twice)) if twice else ''}; pages {sorted(p for p, t in listed.items() if t != 'hidden')}")
    changed = sorted(set(value) ^ {p for p, t in listed.items() if t == "content"})
    return {"pages": sorted(value), "basis": "model reading" + (f"; differs from the triage proposal on {changed}" if changed else "; agrees with the triage proposal"),
            "provenance": model_prov("content pages read off the renders")}


def core_open(guide: dict) -> list[str]:
    """Core addresses still open: absent, partial, or listed in `unresolved` (the address
    itself or its /members). A member refinement that carries a measured default, such as
    line_spacing, does not hold a role open."""
    listed = {u["path"] for u in guide.get("unresolved", [])}

    def is_open(addr: str) -> bool:
        node = node_at(guide, addr)
        return not isinstance(node, dict) or bool(node.get("partial")) or addr in listed or f"{addr}/members" in listed

    out = [a for a in CORE_ROLES if is_open(a)]
    if all(is_open(a) for a in CORE_ANNOTATION):
        out.append(" | ".join(CORE_ANNOTATION))
    return out


def apply(guide: dict, patch: dict, digest_stub: dict | None = None) -> tuple[dict, list[str], list[str]]:
    """Fold the patch in, every address, and return each refusal rather than stopping at
    the first: (guide, applied, refusals). `digest_stub` is the gallery's digest.stub.json,
    read by --digest beside the completed digest: /exhibit_habits is checked against it, and
    refused without it."""
    guide = copy.deepcopy(guide)
    open_paths = {u["path"]: u for u in guide.get("unresolved", [])}
    patch, bulk_notes = expand_bulk(patch, open_paths)
    applied: list[str] = []
    # colour roles first, so later references resolve
    ordered = sorted(patch.items(), key=lambda kv: (0 if kv[0].startswith("/color/roles/") or kv[0].startswith("/extra_roles/") else 1, kv[0]))
    refusals: list[str] = []
    for path, value in ordered:
        try:
            apply_one(guide, path, value, open_paths, digest_stub)
        except PatchError as error:
            refusals.append(str(error))
            continue
        applied.append(path)
        open_paths.pop(path, None)
    if not refusals:
        refusals += table_role_errors(guide)
    guide["unresolved"] = [u for u in guide.get("unresolved", []) if u["path"] in open_paths]
    if (guide.get("variety") or {}).get("pages"):
        # re-measured on every completion: the content pages or the exhibit types may have just been answered
        guide["variety"]["measure"] = plan.house_deck(guide)
    guide.setdefault("completion", {"applied": []})["applied"].extend(applied)
    if bulk_notes:
        guide["completion"].setdefault("bulk", []).extend(bulk_notes)
    return guide, applied, refusals


def table_role_errors(guide: dict) -> list[str]:
    """A completed table must name real roles the emitter can resolve."""
    tables = guide.get("tables")
    if not isinstance(tables, dict):
        return []
    colors = dict(guide.get("color", {}).get("roles", {}))
    colors.update(guide.get("extra_roles") or {})
    return [f"/tables/{k}: {tables[k]} is not a colour role" for k in ("header_fill_role", "header_ink_role", "banding_role")
            if tables.get(k) and tables[k] not in colors]


def record_absent(guide: dict, path: str, role: str, why: str) -> None:
    guide.setdefault(ABSENT_SHAPE, {})[role] = {"address": path, "why": why, "provenance": model_prov(why)}


#: chart text roles, and the digest records that show the house draws such text: an
#: axis on every exhibit of these types, a data label wherever the record says marks are
#: labelled
AXIS_TYPES = {"line", "column", "stacked", "horizontal_bar", "combo", "football_field_or_range_bars", "waterfall_or_bridge",
              "scatter_or_bubble", "histogram"}


def chart_text_in_digest(guide: dict, role: str) -> str | None:
    """Where the completed digest records the house drawing a chart text role, or None."""
    records = (guide.get("exhibit_habits") or {}).get("records") or []
    if role == "type.axis_label":
        hits = [r for r in records if r.get("type") in AXIS_TYPES]
        what = "exhibits with axes"
    elif role == "type.data_label":
        hits = [r for r in records if r.get("data_labels") in ("all", "selective")]
        what = "exhibits with labelled marks"
    else:
        return None
    return f"{len(hits)} {what} (slides {sorted({r['slide'] for r in hits})})" if hits else None


def seen_in(path: str, value: dict) -> dict:
    """{"seen_in": "pictures"} for an answer read off pasted pictures, {} otherwise; any
    other evidence value is refused."""
    if "evidence" not in value:
        return {}
    if value["evidence"] != PICTURES:
        raise PatchError(f"{path}: evidence {value['evidence']!r}; the one value is \"{PICTURES}\" (read off pictures the house pasted)")
    return {"seen_in": PICTURES}


def expand_bulk(patch: dict, open_paths) -> tuple[dict, list[str]]:
    """A bulk answer for every open line_spacing address: "/typography/roles/*/line_spacing"
    answers each one the patch does not answer by name. It closes only open addresses, so
    it can never overwrite an observed value."""
    out = dict(patch)
    notes: list[str] = []
    if BULK_LINE_SPACING in out:
        value = out.pop(BULK_LINE_SPACING)
        covered = [p for p in open_paths if re.fullmatch(r"/typography/roles/[^/]+/line_spacing", p) and p not in patch]
        for p in covered:
            out[p] = value
        notes.append(f"{BULK_LINE_SPACING} answered {len(covered)} open line_spacing address(es)"
                     + (f"; named ones kept their own answer: {sorted(p for p in patch if p.endswith('/line_spacing') and p != BULK_LINE_SPACING)}"
                        if any(p.endswith("/line_spacing") and p != BULK_LINE_SPACING for p in patch) else ""))
    return out, notes


BULK_LINE_SPACING = "/typography/roles/*/line_spacing"

def chrome_entries(guide: dict, value) -> list[dict]:
    """A hand-written /chrome list, proven at the boundary: each entry names its id once,
    a kind the emitter draws, a box, the pages it is on (an entry on under half of them
    is never drawn, so it is refused), and what its kind draws with (a rule a stroke, a
    band a fill, a text kind its text, a logo a picture or a placeholder fill). Stray keys
    are named. Every problem is listed in one refusal."""
    if not isinstance(value, list) or not value:
        raise PatchError(f"/chrome: expected {CHROME_SHAPE}")
    n = max(1, int((guide.get("reference") or {}).get("slides") or 1))
    errors: list[str] = []
    ids: list[str] = []
    for i, ch in enumerate(value):
        where = f"/chrome[{i}]"
        if not isinstance(ch, dict):
            errors.append(f"{where}: not an object")
            continue
        missing = [k for k in CHROME_REQUIRED if k not in ch]
        stray = sorted(set(ch) - set(CHROME_REQUIRED) - CHROME_OPTIONAL)
        if missing:
            errors.append(f"{where}: {missing} not answered")
        if stray:
            errors.append(f"{where}: {stray} read by nothing")
        cid, kind = ch.get("chrome_id"), ch.get("kind")
        if not isinstance(cid, str) or not cid or cid in ids:
            errors.append(f"{where}: chrome_id {cid!r} must be a name given once")
        ids.append(cid)
        if kind not in CHROME_KINDS:
            errors.append(f"{where}: kind {kind!r}{plan.nearest(kind, CHROME_KINDS)} not in {list(CHROME_KINDS)}")
        box = ch.get("box_in")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int | float) and not isinstance(v, bool) for v in box) and box[2] > 0 and box[3] > 0):
            errors.append(f"{where}: box_in is [left, top, width, height] in inches, width and height above 0")
        sp = ch.get("slides_present")
        if not isinstance(sp, int) or isinstance(sp, bool) or not 0 < sp <= n:
            errors.append(f"{where}: slides_present is the number of the reference's {n} pages it is on")
        elif sp < 0.5 * n:
            errors.append(f"{where}: on {sp} of {n} pages, under half: the build draws only furniture on half the pages or more, so this entry would draw nothing")
        if kind in ("label", "footer", "date") and not (isinstance(ch.get("text"), str) and ch["text"].strip()):
            errors.append(f"{where}: a {kind} draws its text: answer text")
        if kind == "rule" and not (ch.get("line_hex") or ch.get("line_role") or ch.get("fill_hex") or ch.get("fill_role")):
            errors.append(f"{where}: a rule needs line_hex or line_role (and line_width_pt)")
        if kind == "band" and not (ch.get("fill_hex") or ch.get("fill_role")):
            errors.append(f"{where}: a band needs fill_hex or fill_role, or it draws nothing")
        if kind == "logo" and not (ch.get("image_path") or ch.get("fill_hex") or ch.get("fill_role") or ch.get("line_hex") or ch.get("line_role")):
            errors.append(f"{where}: a logo needs image_path (a file you cut from the reference) or a placeholder fill or line, or it draws nothing")
        for key in ("fill_hex", "line_hex"):
            if ch.get(key) is not None and not (isinstance(ch[key], str) and HEX_RE.match(ch[key])):
                errors.append(f"{where}: {key} is a hex colour")
        if ch.get("anchor") is not None and ch["anchor"] not in CHROME_ANCHORS:
            errors.append(f"{where}: anchor {ch['anchor']!r} not in {list(CHROME_ANCHORS)}")
        style = ch.get("text_style")
        if style is not None and (not isinstance(style, dict) or set(style) - {"family", "size_pt", "bold", "ink_hex"}):
            errors.append(f"{where}: text_style is {{\"family\", \"size_pt\", \"bold\", \"ink_hex\"}}")
    if errors:
        raise PatchError(f"/chrome: {len(errors)} problem{'s' if len(errors) > 1 else ''}: " + "; ".join(errors))
    out = []
    for order, ch in enumerate(value):
        entry = {**ch, "layers": ch.get("layers") or ["slide"], "of_slides": n, "paint_order": ch.get("paint_order", order),
                 "provenance": model_prov(ch.get("why") or "completion of /chrome")}
        box = entry["box_in"]
        entry.setdefault("exclusion_zone_in", list(box))
        out.append(entry)
    return out


def composition_answer(value) -> dict:
    """A hand-written /composition (a raster draft opens it whole): archetypes the plan
    names by id, each an id of the form arch-N given once, with the pages it is seen on."""
    shape = '{"archetypes": [{"archetype_id": "arch-1", "slides": [page numbers], "description": "<the arrangement in words>"}], "why"}'
    if not isinstance(value, dict) or not isinstance(value.get("archetypes"), list):
        raise PatchError(f"/composition: expected {shape}")
    errors, ids = [], []
    for i, a in enumerate(value["archetypes"]):
        aid = a.get("archetype_id") if isinstance(a, dict) else None
        if not (isinstance(aid, str) and re.fullmatch(r"arch-\d+", aid)) or aid in ids:
            errors.append(f"archetypes[{i}]: archetype_id {aid!r} must be arch-N, given once (the plan names compositions by it)")
        ids.append(aid)
        slides = a.get("slides") if isinstance(a, dict) else None
        if not (isinstance(slides, list) and slides and all(isinstance(s, int) and not isinstance(s, bool) for s in slides)):
            errors.append(f"archetypes[{i}]: slides is the list of reference pages it is seen on")
    if errors:
        raise PatchError("/composition: " + "; ".join(errors) + f"; expected {shape}")
    return {"archetypes": [{**a, "occurrence_count": len(a["slides"])} for a in value["archetypes"]],
            "bands": value.get("bands") or [], "column_grids": value.get("column_grids") or [], "alignment_edges": value.get("alignment_edges") or [],
            "provenance": model_prov(value.get("why") or "completion of /composition")}


def apply_one(guide: dict, path: str, value, open_paths: dict, digest_stub: dict | None) -> None:
    check_writable(guide, path, value, open_paths)
    err = shape_error(path, value)
    if err:
        raise PatchError(err)
    parts = [p for p in path.split("/") if p]
    if parts[0] == "color" and parts[1] == "roles" and value is None:
        guide["color"]["roles"].pop(parts[2], None)
        record_absent(guide, path, parts[2], "answered null: the house shows no such colour")
    elif parts[0] == "typography" and parts[1] == "roles" and len(parts) == 3 and value is None:
        drawn = chart_text_in_digest(guide, parts[2])
        if drawn:
            raise PatchError(f"{path}: null says the house sets no such text, but the digest records it drawn: {drawn}. Text the house "
                             f"sets only inside pasted pictures is not absent: answer the value read off those pictures with "
                             f"\"evidence\": \"pictures\", so native charts can set it")
        guide["typography"]["roles"].pop(parts[2], None)
        record_absent(guide, path, parts[2], "answered null: the house sets no such text")
    elif parts[0] == "color" and parts[1] == "roles":
        role = parts[2]
        if isinstance(value, str) and HEX_RE.match(value):
            guide["color"]["roles"][role] = {"hex": value.upper(), "provenance": model_prov(f"completion of {path}")}
        elif isinstance(value, dict) and HEX_RE.match(value.get("hex", "")):
            guide["color"]["roles"][role] = {"hex": value["hex"].upper(), "provenance": model_prov(value.get("why", ""), value),
                                             **seen_in(path, value)}
        else:
            raise PatchError(f"{path}: expected a hex colour")
    elif parts[0] == "extra_roles":
        # the same two forms a colour role takes: a bare hex, or {"hex", "why"} (SKILL.md
        # section 3 asks for the why, so the object form is the documented one)
        if isinstance(value, str) and HEX_RE.match(value):
            spec = {"hex": value.upper(), "provenance": model_prov(f"completion of {path}")}
        elif isinstance(value, dict) and isinstance(value.get("hex"), str) and HEX_RE.match(value["hex"]):
            spec = {"hex": value["hex"].upper(), "provenance": model_prov(value.get("why", ""), value)}
        else:
            raise PatchError(f"{path}: expected a hex colour, or {{\"hex\": \"RRGGBB\", \"why\": \"...\"}}")
        guide["extra_roles"] = guide.get("extra_roles") or {}
        guide["extra_roles"][parts[1]] = spec
    elif parts[0] == "typography" and parts[1] == "roles":
        role = parts[2]
        roles = guide["typography"]["roles"]
        if len(parts) == 3:
            if role in roles and not roles[role].get("partial"):
                raise PatchError(f"{path}: {role} is observed")
            if not isinstance(value, dict) or "size_pt" not in value:
                raise PatchError(f"{path}: a role needs at least size_pt")
            spec = {k: value.get(k) for k in TYPE_MEMBERS}
            if float(spec["size_pt"]) < floor_for(guide, role):
                fam = FLOOR_FAMILY.get(role, "body")
                observed = ((guide.get("floors") or {}).get(fam) or {}).get("floor_pt") is not None and "/floors/" + fam + "/floor_pt" not in open_paths
                raise PatchError(f"{path}: {spec['size_pt']}pt is below the {fam} floor {floor_for(guide, role)}pt"
                                 + (f"; that floor is the smallest {fam} text the reference sets as text, observed, so it cannot be lowered. "
                                    f"Answer {floor_for(guide, role)}pt or more; if the house's own tables are pictures set smaller, "
                                    "native tables will read larger than they do: say so in the report" if observed else ""))
            spec.setdefault("weight", 400)
            spec["provenance"] = model_prov(value.get("why", ""), value)
            spec.update(seen_in(path, value))
            roles[role] = spec
        elif parts[3] == "members":
            if role not in roles:
                raise PatchError(f"{path}: {role} has no derived size to complete")
            if not isinstance(value, dict):
                raise PatchError(f"{path}: expected {value_shape(path)[0]}")  # type: ignore[index]
            bad = sorted(k for k in value if k == "size_pt" or (k not in TYPE_MEMBERS and k != "why"))
            if bad:
                raise PatchError(f"{path}: {bad} {'is' if len(bad) == 1 else 'are'} not completable here; write {value_shape(path)[0]}")  # type: ignore[index]
            for k, v in value.items():
                if k != "why":
                    roles[role][k] = v
            roles[role]["partial"] = False
            roles[role]["provenance"]["evidence"].append("members by completion" + (f": {value['why']}" if value.get("why") else ""))
        else:
            member = parts[3]
            if member == "line_spacing":
                # null is an answer: the role keeps single spacing (1.2 x size, the
                # renderer's measured default when no lnSpc is written)
                roles[role]["line_spacing"] = None if value is None else float(value)
            else:
                raise PatchError(f"{path}: member {member} is not open")
        check_color_refs(guide, value if isinstance(value, dict) else {}, path)
    elif path == "/chrome":
        guide["chrome"] = chrome_entries(guide, value)
    elif path == "/composition":
        guide["composition"] = composition_answer(value)
    elif path == "/titles/register":
        guide["titles"]["register"] = title_register(guide, value)
    elif path == "/exhibit_habits":
        guide["exhibit_habits"] = exhibit_habits(guide, value, digest_stub)
    elif path == "/variety/content_pages":
        guide["variety"]["content_pages"] = content_pages(guide, value)
    elif path in SECTION_PATHS:
        check_color_refs(guide, value, path)
        if path == "/tables" and isinstance(value, dict):
            for k in ("header_fill_role", "header_ink_role", "banding_role"):
                value.setdefault(k, None)
            value.setdefault("provenance", model_prov("completion"))
        if path == "/typography/families/substitutes":
            # stand-in faces for measurement only: the file names the real face
            guide["typography"].setdefault("families", {})["substitutes"] = dict(value)
        elif path == "/typography/scale_ratio":
            # null is an answer: the ladder is not geometric, and nothing reads a ratio
            guide["typography"]["scale_ratio"] = None if value is None else float(value)
        elif path == "/spacing/baseline_emu":
            guide["spacing"]["baseline_emu"] = int(value) if value is not None else None
        elif path == "/density_bands/table_rows_per_inch":
            guide["density_bands"]["table_rows_per_inch"] = value
        elif path.startswith("/shape_language/") or path.startswith("/color/"):
            guide[parts[0]][parts[1]] = value
        else:
            guide[parts[0]] = value
    elif path.startswith("/floors/"):
        fam = parts[1]
        # null: no run in this family, so the absolute floor is the floor (floor_for)
        guide["floors"][fam]["floor_pt"] = None if value is None else max(float(value), float(guide["floors"][fam].get("absolute_floor_pt") or 0))
    elif path.startswith("/spacing/steps/"):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise PatchError(f"{path}: a positive integer EMU, got {value!r}")
        guide["spacing"]["steps"][parts[2]] = {"emu": value, "provenance": model_prov("completion")}
    elif path == "/spacing/steps":
        # the whole scale at once (a raster draft opens it whole): proven here, stored as the
        # vector extractor stores observed steps, so every reader takes one shape
        if not isinstance(value, dict) or any(not (isinstance(k, str) and re.fullmatch(r"space\.[a-z_]+", k)) for k in value):
            raise PatchError(f"{path}: expected {value_shape(path)[0]}")  # type: ignore[index]
        bad = sorted(k for k, v in value.items() if not isinstance(v, int) or isinstance(v, bool) or v <= 0)
        missing = sorted(set(SPACING_STEPS_NEEDED) - set(value))
        if bad or missing:
            raise PatchError(f"{path}: " + "; ".join(([f"{bad} must each be a positive integer EMU (\"space.sm\": 91440, not an object)"] if bad else [])
                                                     + ([f"{missing} not answered: the round trip and the components read them"] if missing else [])))
        guide["spacing"]["steps"] = {k: {"emu": v, "provenance": model_prov("completion")} for k, v in value.items()}
    elif path.startswith("/notes"):
        guide.setdefault("notes", []).append(str(value))
    else:
        # any other open leaf: set it where the draft addressed it
        node = guide
        for key in parts[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        node[parts[-1]] = value


def load_json(path: Path):
    """A JSON file whose objects name each key once: a repeated key is refused, not read as
    its last value."""
    def pairs(items: list) -> dict:
        keys = [k for k, _ in items]
        repeated = sorted({k for k in keys if keys.count(k) > 1})
        if repeated:
            raise PatchError(f"{path}: keys {repeated} are given more than once in one object")
        return dict(items)
    try:
        return json.loads(path.read_text(), object_pairs_hook=pairs)
    except json.JSONDecodeError as error:
        raise PatchError(f"{path}: not JSON ({error})") from None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("guide", nargs="?")
    ap.add_argument("patch", nargs="?")
    ap.add_argument("--shapes", action="store_true", help="print the value every address takes, and what null means there")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--allow-partial", action="store_true", help="write the guide with core addresses still open, and list them")
    ap.add_argument("--digest", default=None, help="the gallery.py digest directory: digest.stub.json as cut, and digest.json, the completed "
                    "copy, which answers /exhibit_habits")
    args = ap.parse_args(argv)
    if not args.shapes and not args.guide:
        ap.error("a guide draft is required (or --shapes)")
    guide = json.loads(Path(args.guide).read_text()) if args.guide else {}
    if args.shapes:
        print("| address | value | null means |\n|---|---|---|")
        def cell(text: str) -> str:
            return text.replace("|", "\\|")
        for pattern, shape, null in VALUE_SHAPES:
            address = pattern.replace("[^/]+", "<name>").replace("\\.", ".")
            print(f"| `{cell(address)}` | {cell(shape)} | {cell(null or 'refused')} |")
        return 0
    if args.check or not args.patch:
        # each value shape is printed once, under every open address it answers
        groups: dict[tuple | None, list[dict]] = {}
        for u in guide.get("unresolved", []):
            found = value_shape(u["path"])
            groups.setdefault(tuple(found) if found else None, []).append(u)
        for found, items in groups.items():
            for u in items:
                print(f"- {u['path']}: {u['reason']}")
            if found:
                print(f"    value{' (each of the ' + str(len(items)) + ' above)' if len(items) > 1 else ''}: {found[0]}; null: {found[1] or 'refused'}")
        print(f"{len(guide.get('unresolved', []))} open; core open: {core_open(guide) or 'none'}")
        return 0
    patch = load_json(Path(args.patch))
    stub = None
    if args.digest:
        if "/exhibit_habits" in patch:
            raise PatchError("/exhibit_habits: answered both in the patch and by --digest; give one")
        folder = Path(args.digest)
        for name in ("digest.stub.json", "digest.json"):
            if not (folder / name).is_file():
                raise PatchError(f"/exhibit_habits: {folder / name} does not exist; --digest names the gallery.py digest directory, "
                                 "holding the stub as cut and the completed copy beside it")
        stub = load_json(folder / "digest.stub.json")
        patch["/exhibit_habits"] = load_json(folder / "digest.json")
    guide, applied, refusals = apply(guide, patch, stub)
    core = core_open(guide)
    if core and not args.allow_partial:
        refusals.append(f"core addresses still open after the patch: {core}; answer them, or pass --allow-partial to write "
                        f"a guide that lists them")
    if refusals:
        raise PatchError(f"refused, {len(refusals)} problem{'s' if len(refusals) > 1 else ''} (nothing written; {len(applied)} other "
                         "address(es) applied cleanly):\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(refusals, 1)))
    if core:
        guide["completion"]["core_open"] = core
    import cli
    out = cli.out_path(Path(args.out) if args.out else Path(args.guide).with_name(Path(args.guide).stem.replace(".style", "") + ".guide.json"), "guide")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(guide, indent=1, default=str))
    summary: dict = {"out": str(out), "applied": applied, "core_open": core, "still_open": [u["path"] for u in guide["unresolved"]]}
    eh = guide.get("exhibit_habits")
    if isinstance(eh, dict):
        # the habits every later step reads, with their counts, where the model sees them first
        sl = eh["source_lines"]
        summary["house_habits"] = {
            "source_lines": f"{sl['with_source_line']} of {sl['data_pages']} data pages carry a source or note line"
                            + (f" (pages {sl['pages_with']})" if sl["pages_with"] else "") + ": put one where the house would",
            "marks": f"{len(eh['marks_labelled']['labelled'])} labelled, {len(eh['marks_labelled']['unlabelled'])} unlabelled "
                     f"(unlabelled on slides {sorted({m['slide'] for m in eh['marks_labelled']['unlabelled']})}): an unlabelled mark on a new page "
                     "names what explains it (annotation explained_by)",
            "annotation_moves": eh["annotation_moves"]}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
