#!/usr/bin/env python3
"""Apply the model's completion patch to a style guide draft, deterministically.

    complete_guide.py draft.json patch.json -o guide.json [--allow-partial]
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
"/typography/roles/type.body/line_spacing", "/spacing/baseline_emu".
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
# the extractor never observes these, so they are always the model's to write
ALWAYS_WRITABLE = {"/description", "/derivation_rules", "/continuation", "/typography/families/substitutes"}
SETTLED = {"observed", "deterministic_inference"}
CORE_ROLES = ("/typography/roles/type.title", "/typography/roles/type.body", "/color/roles/color.surface",
              "/color/roles/color.ink", "/color/roles/color.accent1")
# at least one of these must be closed
CORE_ANNOTATION = ("/typography/roles/type.caption", "/typography/roles/type.footnote", "/typography/roles/type.source_line")
# whole-section paths the apply step knows how to write; each is writable only when open
SECTION_PATHS = {"/description", "/derivation_rules", "/continuation", "/tables", "/charts", "/imagery", "/shape_language/icon_style",
                 "/shape_language/corner_radii", "/color/accent_stepping", "/gallery", "/exemplars", "/spacing/baseline_emu",
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
    if (len(parts) == 3 and parts[0] == "typography" and parts[1] == "roles" and parts[2] not in guide["typography"]["roles"]
            and isinstance(value, dict) and value.get("size_pt") is not None and float(value["size_pt"]) in levels):
        return
    under = f"; it sits under {settled[0]}, value_provenance {settled[1]}" if settled else ""
    raise PatchError(f"{path}: not an open address{under}. A patch answers the draft's unresolved list and nothing else (a new "
                     f"type role needs a size the reference writes, levels {sorted(levels)}); open: {sorted(open_paths)}")


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
            if not (isinstance(value, str) and HEX_RE.match(value)):
                raise PatchError(f"{path}: expected a hex colour")
            guide["extra_roles"] = guide.get("extra_roles") or {}
            guide["extra_roles"][parts[1]] = {"hex": value.upper(), "provenance": model_prov(f"completion of {path}")}
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
                    roles[role]["line_spacing"] = float(value)
                else:
                    raise PatchError(f"{path}: member {member} is not open")
            check_color_refs(guide, value if isinstance(value, dict) else {}, path)
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
                guide["typography"]["scale_ratio"] = float(value)
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
    args = ap.parse_args(argv)
    guide = json.loads(Path(args.guide).read_text())
    if args.check or not args.patch:
        for u in guide.get("unresolved", []):
            print(f"- {u['path']}: {u['reason']}")
        print(f"{len(guide.get('unresolved', []))} open; core open: {core_open(guide) or 'none'}")
        return 0
    patch = json.loads(Path(args.patch).read_text())
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
