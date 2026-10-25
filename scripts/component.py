#!/usr/bin/env python3
"""Check and admit a component against the contract in components/README.md.

    component.py check <kind> --guide guide.json --template tpl.pptx --out DIR [--reference ref.pptx]
    component.py admit <kind> --out DIR        # records the passing check in components/<kind>/admitted.json
    component.py list

`check` runs expand at every test box in spec.json (three shown, one held out with other
data), solves each with the guide, refuses any violation, emits each onto the template,
renders them into one contact sheet, and judges the rendered slides against the
reference. The author reads the sheet; nothing here judges taste.

Before any of that, `check` runs each test's expand twice in separate interpreters under
PYTHONHASHSEED=0 and PYTHONHASHSEED=1 and compares the returned trees (JSON with sorted
keys, so a dict whose insertion order moved is not a difference, but a list whose order
moved is: that is where a set iteration shows). Any difference fails the check and names
the first differing path.
`expand-once` is the driver those interpreters run; it prints the canonical tree.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # the skill directory is never written, not even a bytecode cache
sys.path.insert(0, str(Path(__file__).resolve().parent))
import component_api  # noqa: E402
import layout as L  # noqa: E402
from build_deck import EMU_PER_INCH, build, chrome_zones, component_root, load_component, top_rules  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent / "components"
#: deckgen expansion_checks.py HASH_SEEDS: two seeds are enough, since one differing
#: iteration order between them is the whole finding.
HASH_SEEDS = ("0", "1")


def canonical_expansion(kind: str, data_path: str, width_emu: int, height_emu: int, guide_path: str) -> str:
    """One expansion as the bytes the determinism comparison is over, with the same
    inputs the build hands the component: the test data under instance id "c", the test
    box, and the guide carrying the measurement API."""
    guide = json.loads(Path(guide_path).read_text())
    data = json.loads(Path(data_path).read_text())
    data["_id"] = "c"
    tree = load_component(kind)(data, {"width_emu": int(width_emu), "height_emu": int(height_emu)}, component_api.with_api(guide, component_api.make_api(guide)))
    return json.dumps(tree, sort_keys=True, separators=(",", ":"), default=str)


def first_difference(a, b, path: str = "$") -> str | None:
    """The first path where two canonical trees differ, list order included."""
    if type(a) is not type(b):
        return f"{path}: {type(a).__name__} against {type(b).__name__}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}: present in one run only"
            found = first_difference(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items against {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, f"{path}[{i}]")
            if found:
                return found
        return None
    return None if a == b else f"{path}: {a!r} against {b!r}"


def determinism(kind: str, tests: list[dict], guide_path: str) -> list[dict]:
    """Each test's expand run under two hash seeds in two interpreters. The child runs
    without -I or -E: both imply ignoring PYTHON* variables, which would silence the
    seed (checked: under -I, PYTHONHASHSEED=1 and =0 hash alike)."""
    out = []
    for t in tests:
        runs = []
        for seed in HASH_SEEDS:
            args = [sys.executable, str(Path(__file__).resolve()), "expand-once", kind, str(component_root(kind) / t["data"]), str(t["box"]["width_emu"]), str(t["box"]["height_emu"]), "--guide", guide_path]
            completed = subprocess.run(args, capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": seed}, timeout=300)
            if completed.returncode != 0:
                out.append({"test": t["name"], "deterministic": False, "first_difference": None, "error": f"PYTHONHASHSEED={seed}: {completed.stderr.strip()[-400:]}"})
                break
            runs.append(completed.stdout.strip())
        else:
            diff = None if runs[0] == runs[1] else (first_difference(json.loads(runs[0]), json.loads(runs[1])) or "$: the canonical dumps differ")
            out.append({"test": t["name"], "deterministic": diff is None, "first_difference": diff, "seeds": list(HASH_SEEDS)})
    return out


def check(kind: str, guide_path: str, template: str, out: str, reference: str | None) -> dict:
    name = component_root(kind).name  # `kind` may be a path to a component under development
    spec = json.loads((component_root(kind) / "spec.json").read_text())
    guide = json.loads(Path(guide_path).read_text())
    guide_ref = {"guide_reference": guide.get("reference", {}).get("file"), "guide_reference_sha256": guide.get("reference", {}).get("sha256")}
    tests = [dict(t, held_out=False) for t in spec["tests"]["shown"]] + [dict(spec["tests"]["held_out"], held_out=True)]
    stable = determinism(kind, tests, guide_path)
    margin = (guide.get("spacing", {}).get("steps", {}).get("space.margin") or {}).get("emu", 457200)
    # the harness page is emitted on the template, so the master's and layout's furniture
    # is drawn over it: the page reserves the build's chrome zones, and everything above
    # the top rule (the harness has no title to set there), so a component that crosses a
    # rule or a band is a reserved_zone violation, not a pass the sheet contradicts
    zones = chrome_zones(guide)
    page_w = guide["reference"]["page"]["width_emu"]
    top = max([margin] + [int((r["box_in"][1] + r["box_in"][3]) * EMU_PER_INCH) for r in top_rules(guide)])
    if top > margin:
        zones = zones + [{"left": 0, "top": 0, "width": page_w, "height": top, "source": "title band (above the top rule; the harness sets no title)"}]
    floor = min([z["top"] for z in zones if z["top"] > top] + [guide["reference"]["page"]["height_emu"]])
    deck = {"slides": []}
    unplaceable = {}
    for t in tests:
        data = json.loads((component_root(kind) / t["data"]).read_text())
        w, h = t["box"]["width_emu"], t["box"]["height_emu"]
        if top + h > floor:
            # the box cannot stand on this template between the top rule and the footer zone
            unplaceable[t["name"]] = f"test box {h / EMU_PER_INCH:.2f} in tall; this template leaves {(floor - top) / EMU_PER_INCH:.2f} in between its top furniture and its bottom zone"
        deck["slides"].append({
            "id": t["name"],
            "layout": None,
            "spec": {"page": {"width_emu": w + 2 * margin, "height_emu": top + h + margin, "reserved_zones": zones},
                     "root": {"type": "region", "id": "root",
                              "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": "space.margin", "align": "stretch", "justify": "start"},
                              "children": [{"type": "component", "id": "c", "kind": kind, "data": data}]}},
        })
    Path(out).mkdir(parents=True, exist_ok=True)
    deck_path = Path(out) / f"{name}.check.deck.json"
    deck_path.write_text(json.dumps(deck, indent=1))
    pptx = str(Path(out) / f"{name}.check.pptx")
    report = build(deck, guide, template, pptx, reference, [], str(Path(out) / "renders"), True)
    verdict = []
    single = tuple(spec.get("single_line_ids") or ())
    for t, s, d in zip(tests, report["slides"], stable):
        # the harness page is the component alone, so the page rule "a table or chart needs a
        # source line" is not the component's to pass; contrast is (its own inks on its own fills)
        refusals = {p["kind"] for p in s.get("problems", []) if p["severity"] == "refusal"}
        ok = (s.get("solver_status", s["status"]) == "fit" and not s.get("violations") and refusals <= {"no source line"} and d["deterministic"]
              and t["name"] not in unplaceable)
        # a figure, a tick or a marker label that wrapped is not fit, whatever the solver says:
        # '$1' over '4' is the defect the first admission let through
        wrapped = sorted(k for k, lines in (s.get("text_lines") or {}).items() if lines > 1 and any(tag in k for tag in single))
        if wrapped:
            ok = False
        verdict.append({"test": t["name"], "held_out": t["held_out"], "box": t["box"], "pass": ok, "scale": s.get("scale"),
                        "violations": s.get("violations", []), "reason": unplaceable.get(t["name"]) or s.get("reason"), "wrapped_single_line": wrapped,
                        "deterministic": d["deterministic"], "first_difference": d.get("first_difference") or d.get("error"),
                        "contrast_violations": (s.get("contrast") or {}).get("violations", [])})
    sheet = None
    images = (report.get("renders") or {}).get("images") or []
    if images:
        from render import grid
        sheet = str(grid([Path(p) for p in images], Path(out) / f"{name}.sheet.png", cols=2, cell_w=700))
    # a package that fails validation (a shape past the slide) is not admitted, whatever the boxes say
    result = {"kind": kind, "all_pass": all(v["pass"] for v in verdict) and bool(report.get("validation", {}).get("ok")), "tests": verdict, "pptx": pptx, "sheet": sheet, **guide_ref,
              "determinism": stable, "judge": report.get("judge"), "validation_ok": report.get("validation", {}).get("ok")}
    (Path(out) / f"{name}.check.json").write_text(json.dumps(result, indent=1, default=str))
    return result


def admit(kind: str, out: str) -> dict:
    name = component_root(kind).name
    result = json.loads((Path(out) / f"{name}.check.json").read_text())
    if not result["all_pass"]:
        raise SystemExit(f"{kind}: the last check did not pass every box; fix and re-check before admitting")
    record = {"kind": kind, "checked_boxes": [t["box"] for t in result["tests"]], "held_out_passed": True, "sheet": result["sheet"], "judge_total": (result.get("judge") or {}).get("total"),
              # admission is bound to the guide it passed under; build_deck says so when the guide differs
              "guide_reference": result.get("guide_reference"), "guide_reference_sha256": result.get("guide_reference_sha256")}
    (component_root(kind) / "admitted.json").write_text(json.dumps(record, indent=1))
    return record


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("kind"); c.add_argument("--guide", required=True); c.add_argument("--template", required=True); c.add_argument("--out", required=True); c.add_argument("--reference", default=None)
    a = sub.add_parser("admit"); a.add_argument("kind"); a.add_argument("--out", required=True)
    e = sub.add_parser("expand-once", help="print one canonical expansion (the determinism driver)"); e.add_argument("kind"); e.add_argument("data"); e.add_argument("width_emu", type=int); e.add_argument("height_emu", type=int); e.add_argument("--guide", required=True)
    sub.add_parser("list")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        import cli
        cli.guard_args(args, "out")
    if args.cmd == "expand-once":
        print(canonical_expansion(args.kind, args.data, args.width_emu, args.height_emu, args.guide))
        return 0
    if args.cmd == "list":
        for d in sorted(ROOT.iterdir()):
            if (d / "spec.json").exists():
                spec = json.loads((d / "spec.json").read_text())
                print(f"{d.name}: {spec.get('description', '')[:100]} {'[admitted]' if (d / 'admitted.json').exists() else '[not admitted]'}")
        return 0
    if args.cmd == "check":
        result = check(args.kind, args.guide, args.template, args.out, args.reference)
        print(json.dumps({k: v for k, v in result.items() if k != "judge"}, indent=1, default=str))
        return 0 if result["all_pass"] else 1
    if args.cmd == "admit":
        print(json.dumps(admit(args.kind, args.out), indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cli
    cli.run(main)
