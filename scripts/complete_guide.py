#!/usr/bin/env python3
"""Apply the model's completion patch to a style guide draft, deterministically.

    complete_guide.py draft.json patch.json -o guide.json [--allow-partial] [--digest digest.json]
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
--allow-partial, which lists it (deckgen prompts/style_completer/v2: "An address you leave
out is as wrong as one you invent").

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
    return None if isinstance(value, str) and value in allowed else f"{where}: {value!r} is not in {name} ({'|'.join(allowed)})"


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
    want = {str(r["slide"]): r for r in records}
    per = value["per_title"]
    errors += [f"per_title: slide {k} ({want[k]['text']!r}) is not classified" for k in want if k not in per]
    errors += [f"per_title: slide {k} has no title found by position" for k in per if k not in want]
    errors += [e for k, v in per.items() if k in want for e in [_vocab_error("title_register", v, f"per_title/{k}")] if e]
    given = value.get("companions") or {}
    found = {(str(r["slide"]), pos): r[pos]["text"] for r in records for pos in ("above", "below") if r.get(pos)}
    for (slide, pos), text in found.items():
        if pos not in (given.get(slide) or {}):
            errors.append(f"companions: slide {slide} {pos} ({text!r}) is not named")
    for slide, entry in given.items():
        for pos, kind in (entry or {}).items():
            if (slide, pos) not in found:
                errors.append(f"companions: slide {slide} has no block {pos} its title")
            else:
                e = _vocab_error(f"title_companion_{pos}", kind, f"companions/{slide}/{pos}")
                if e:
                    errors.append(e)
    claims = value.get("claims_elsewhere") or {}
    for slide, where in claims.items():
        if per.get(slide) != "topic":
            errors.append(f"claims_elsewhere: slide {slide} is not a topic title")
        elif where is not None and not (isinstance(where, str) and where.strip()):
            errors.append(f"claims_elsewhere/{slide}: a place in words, or null when the page states no claim")
    if errors:
        raise PatchError("/titles/register: " + "; ".join(errors))
    counts = {k: sum(1 for v in per.values() if v == k) for k in VOCABULARY["title_register"]}
    return {"counts": counts, "n": len(per), "per_title": dict(sorted(per.items(), key=lambda kv: int(kv[0]))),
            "companions": given, "companion_counts": {pos: dict(Counter(e[pos] for e in given.values() if pos in (e or {}))) for pos in ("above", "below")},
            "claims_elsewhere": claims, "why": value.get("why"), "provenance": model_prov(value.get("why") or "")}


EXHIBIT_KEYS = {"candidate", "class", "type", "data_shape", "message", "message_kind", "annotation_moves", "emphasis_devices",
                "number_formats", "legend", "data_labels", "colour_logic", "why"}
EXHIBIT_SCALARS = (("class", "exhibit_class"), ("type", "exhibit_type"), ("data_shape", "data_shape"), ("message_kind", "message_kind"),
                   ("legend", "legend"), ("data_labels", "data_labels"), ("colour_logic", "colour_logic"))
EXHIBIT_LISTS = (("emphasis_devices", "emphasis_device"), ("number_formats", "number_format"))


def exhibit_habits(guide: dict, value) -> dict:
    """The completed digest stub (gallery.py digest), checked and aggregated. Every page the
    stub lists is answered (an empty list states the page holds no exhibit; a missing or
    null list is an omission); every exhibit names each field in the closed vocabulary,
    every annotation move with what it anchors to. All omissions are named in one refusal.
    The counts, by type, data shape and message kind, are computed here."""
    if not isinstance(value, dict) or not isinstance(value.get("pages"), list):
        raise PatchError("/exhibit_habits: expected the completed digest stub, {\"reference_sha256\", \"pages\": [{\"slide\", \"candidates\", \"exhibits\": [...]}]}")
    sha = (guide.get("reference") or {}).get("sha256")
    if value.get("reference_sha256") != sha:
        raise PatchError(f"/exhibit_habits: the digest was cut from {value.get('reference_sha256')}, this guide's reference is {sha}")
    errors: list[str] = []
    records: list[dict] = []
    for page in value["pages"]:
        slide = page.get("slide")
        exhibits = page.get("exhibits")
        if not isinstance(exhibits, list):
            errors.append(f"slide {slide}: exhibits not answered (an empty list states the page has none)")
            continue
        candidates = {c.get("id") for c in page.get("candidates") or []}
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
            if ex.get("candidate") is not None and ex["candidate"] not in candidates:
                errors.append(f"{where}: candidate {ex['candidate']!r} is not one of the page's ({sorted(c for c in candidates if c)})")
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
                        if not isinstance(m, dict) or set(m) != {"move", "anchor"}:
                            errors.append(f"{where} annotation_moves[{j}]: exactly {{\"move\", \"anchor\"}}")
                            continue
                        e = _vocab_error("annotation_move", m["move"], f"{where} annotation_moves[{j}]")
                        if e:
                            errors.append(e)
                        if not (isinstance(m["anchor"], str) and m["anchor"].strip()):
                            errors.append(f"{where} annotation_moves[{j}]: anchor names what the move points at")
            records.append({"slide": slide, **ex})
    if errors:
        raise PatchError(f"/exhibit_habits: {len(errors)} problems: " + "; ".join(errors))

    def count(values) -> dict:
        return dict(sorted(Counter(values).items(), key=lambda kv: (-kv[1], kv[0])))

    pages = value["pages"]
    moves = [(r, m["move"]) for r in records for m in r["annotation_moves"]]
    return {
        "sample": {"pages_read": len(pages), "pages_with_exhibits": sum(1 for p in pages if p["exhibits"]),
                   "pages_without": [p["slide"] for p in pages if not p["exhibits"]], "exhibits": len(records),
                   "policy": value.get("sample_policy") or "every evidence page the digest cut"},
        "classes": count(r["class"] for r in records),
        "types": count(r["type"] for r in records),
        "data_shapes": count(r["data_shape"] for r in records),
        "message_kinds": count(r["message_kind"] for r in records),
        "annotation_moves": count(m for _, m in moves),
        "moves_by_data_shape": {shape: count(m for r, m in moves if r["data_shape"] == shape) for shape in sorted({r["data_shape"] for r in records})},
        "moves_by_message_kind": {kind: count(m for r, m in moves if r["message_kind"] == kind) for kind in sorted({r["message_kind"] for r in records})},
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


def apply(guide: dict, patch: dict) -> tuple[dict, list[str]]:
    guide = copy.deepcopy(guide)
    open_paths = {u["path"]: u for u in guide.get("unresolved", [])}
    applied: list[str] = []
    # colour roles first, so later references resolve
    ordered = sorted(patch.items(), key=lambda kv: (0 if kv[0].startswith("/color/roles/") or kv[0].startswith("/extra_roles/") else 1, kv[0]))
    for path, value in ordered:
        check_writable(guide, path, value, open_paths)
        parts = [p for p in path.split("/") if p]
        if parts[0] == "color" and parts[1] == "roles":
            role = parts[2]
            if isinstance(value, str) and HEX_RE.match(value):
                guide["color"]["roles"][role] = {"hex": value.upper(), "provenance": model_prov(f"completion of {path}")}
            elif isinstance(value, dict) and HEX_RE.match(value.get("hex", "")):
                guide["color"]["roles"][role] = {"hex": value["hex"].upper(), "provenance": model_prov(value.get("why", ""), value)}
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
                    raise PatchError(f"{path}: {spec['size_pt']}pt is below the {FLOOR_FAMILY.get(role)} floor {floor_for(guide, role)}pt")
                spec.setdefault("weight", 400)
                spec["provenance"] = model_prov(value.get("why", ""), value)
                roles[role] = spec
            elif parts[3] == "members":
                if role not in roles:
                    raise PatchError(f"{path}: {role} has no derived size to complete")
                for k, v in value.items():
                    if k not in TYPE_MEMBERS or k == "size_pt":
                        raise PatchError(f"{path}: {k} is not a completable member")
                    roles[role][k] = v
                roles[role]["partial"] = False
                roles[role]["provenance"]["evidence"].append("members by completion")
            else:
                member = parts[3]
                if member == "line_spacing":
                    # null is an answer: the role keeps single spacing (1.2 x size, the
                    # renderer's measured default when no lnSpc is written)
                    roles[role]["line_spacing"] = None if value is None else float(value)
                else:
                    raise PatchError(f"{path}: member {member} is not open")
            check_color_refs(guide, value if isinstance(value, dict) else {}, path)
        elif path == "/titles/register":
            guide["titles"]["register"] = title_register(guide, value)
        elif path == "/exhibit_habits":
            guide["exhibit_habits"] = exhibit_habits(guide, value)
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
            guide["floors"][fam]["floor_pt"] = max(float(value), float(guide["floors"][fam].get("absolute_floor_pt") or 0))
        elif path.startswith("/spacing/steps/"):
            guide["spacing"]["steps"][parts[2]] = {"emu": int(value), "provenance": model_prov("completion")}
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
        applied.append(path)
        open_paths.pop(path, None)
    # a completed table must name real roles the emitter can resolve
    tables = guide.get("tables")
    if isinstance(tables, dict):
        colors = dict(guide.get("color", {}).get("roles", {}))
        colors.update(guide.get("extra_roles") or {})
        for k in ("header_fill_role", "header_ink_role", "banding_role"):
            if tables.get(k) and tables[k] not in colors:
                raise PatchError(f"/tables/{k}: {tables[k]} is not a colour role")
    guide["unresolved"] = [u for u in guide.get("unresolved", []) if u["path"] in open_paths]
    guide.setdefault("completion", {"applied": []})["applied"].extend(applied)
    return guide, applied


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("guide")
    ap.add_argument("patch", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--allow-partial", action="store_true", help="write the guide with core addresses still open, and list them")
    ap.add_argument("--digest", default=None, help="the completed exhibit digest (gallery.py digest): the answer to /exhibit_habits")
    args = ap.parse_args(argv)
    guide = json.loads(Path(args.guide).read_text())
    if args.check or not args.patch:
        for u in guide.get("unresolved", []):
            print(f"- {u['path']}: {u['reason']}")
        print(f"{len(guide.get('unresolved', []))} open; core open: {core_open(guide) or 'none'}")
        return 0
    patch = json.loads(Path(args.patch).read_text())
    if args.digest:
        if "/exhibit_habits" in patch:
            raise PatchError("/exhibit_habits: answered both in the patch and by --digest; give one")
        patch["/exhibit_habits"] = json.loads(Path(args.digest).read_text())
    guide, applied = apply(guide, patch)
    core = core_open(guide)
    if core and not args.allow_partial:
        raise PatchError(f"core addresses still open after the patch: {core}; answer them, or pass --allow-partial to write "
                         f"a guide that lists them")
    if core:
        guide["completion"]["core_open"] = core
    out = Path(args.out) if args.out else Path(args.guide).with_name(Path(args.guide).stem.replace(".style", "") + ".guide.json")
    out.write_text(json.dumps(guide, indent=1, default=str))
    print(json.dumps({"out": str(out), "applied": applied, "core_open": core,
                      "still_open": [u["path"] for u in guide["unresolved"]]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
