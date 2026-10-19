#!/usr/bin/env python3
"""Check and admit a component against the contract in components/README.md.

    component.py check <kind> --guide guide.json --template tpl.pptx --out DIR [--reference ref.pptx]
    component.py admit <kind> --out DIR        # records the passing check in components/<kind>/admitted.json
    component.py list

`check` runs expand at every test box in spec.json (three shown, one held out with other
data), solves each with the guide, refuses any violation, emits each onto the template,
renders them into one contact sheet, and judges the rendered slides against the
reference. The author reads the sheet; nothing here judges taste.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L  # noqa: E402
from build_deck import build  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent / "components"


def check(kind: str, guide_path: str, template: str, out: str, reference: str | None) -> dict:
    spec = json.loads((ROOT / kind / "spec.json").read_text())
    guide = json.loads(Path(guide_path).read_text())
    tests = [dict(t, held_out=False) for t in spec["tests"]["shown"]] + [dict(spec["tests"]["held_out"], held_out=True)]
    margin = (guide.get("spacing", {}).get("steps", {}).get("space.margin") or {}).get("emu", 457200)
    deck = {"slides": []}
    for t in tests:
        data = json.loads((ROOT / kind / t["data"]).read_text())
        w, h = t["box"]["width_emu"], t["box"]["height_emu"]
        deck["slides"].append({
            "id": t["name"],
            "layout": None,
            "spec": {"page": {"width_emu": w + 2 * margin, "height_emu": h + 2 * margin, "reserved_zones": []},
                     "root": {"type": "region", "id": "root",
                              "layout": {"kind": "flex", "direction": "column", "gap_role": "space.xs", "pad_role": "space.margin", "align": "stretch", "justify": "start"},
                              "children": [{"type": "component", "id": "c", "kind": kind, "data": data}]}},
        })
    Path(out).mkdir(parents=True, exist_ok=True)
    deck_path = Path(out) / f"{kind}.check.deck.json"
    deck_path.write_text(json.dumps(deck, indent=1))
    pptx = str(Path(out) / f"{kind}.check.pptx")
    report = build(deck, guide, template, pptx, reference, [], str(Path(out) / "renders"), True)
    verdict = []
    for t, s in zip(tests, report["slides"]):
        ok = s["status"] == "fit" and not s.get("violations")
        verdict.append({"test": t["name"], "held_out": t["held_out"], "box": t["box"], "pass": ok, "scale": s.get("scale"),
                        "violations": s.get("violations", []), "reason": s.get("reason")})
    sheet = None
    images = (report.get("renders") or {}).get("images") or []
    if images:
        from render import grid
        sheet = str(grid([Path(p) for p in images], Path(out) / f"{kind}.sheet.png", cols=2, cell_w=700))
    result = {"kind": kind, "all_pass": all(v["pass"] for v in verdict), "tests": verdict, "pptx": pptx, "sheet": sheet,
              "judge": report.get("judge"), "validation_ok": report.get("validation", {}).get("ok")}
    (Path(out) / f"{kind}.check.json").write_text(json.dumps(result, indent=1, default=str))
    return result


def admit(kind: str, out: str) -> dict:
    result = json.loads((Path(out) / f"{kind}.check.json").read_text())
    if not result["all_pass"]:
        raise SystemExit(f"{kind}: the last check did not pass every box; fix and re-check before admitting")
    record = {"kind": kind, "checked_boxes": [t["box"] for t in result["tests"]], "held_out_passed": True, "sheet": result["sheet"], "judge_total": (result.get("judge") or {}).get("total")}
    (ROOT / kind / "admitted.json").write_text(json.dumps(record, indent=1))
    return record


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("kind"); c.add_argument("--guide", required=True); c.add_argument("--template", required=True); c.add_argument("--out", required=True); c.add_argument("--reference", default=None)
    a = sub.add_parser("admit"); a.add_argument("kind"); a.add_argument("--out", required=True)
    sub.add_parser("list")
    args = ap.parse_args(argv)
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
    sys.exit(main(sys.argv[1:]))
