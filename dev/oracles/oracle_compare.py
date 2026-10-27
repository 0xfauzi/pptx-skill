"""(a) Oracle comparison: deckgen's own pure solver vs the port, specimen by specimen.

Run: cd /home/user/deckgen && uv run python -I <this file>
Converts each specimen SlideModel mechanically to the port's spec (regions and
layouts pass through; text runs become paragraphs with dataset refs resolved;
table_ref becomes a table with the dataset's real cells; chart/decor/image become
flexible boxes; annotations, chrome and components are ignored - none occur in the
specimens). Reserved zones are the guide's master zones, exactly as
solver.master_zones lists them.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

# PPTX_SKILL: the skill under test (default: the repo this file sits in); DECKGEN: the
# deckgen checkout (default: the working directory, since uv run needs it); ORACLE_OUT:
# where the converted specimen specs are written (default: a fresh temporary directory)
SKILL = Path(os.environ.get("PPTX_SKILL", Path(__file__).resolve().parents[2] / "skills" / "designing-presentations"))
DECKGEN = Path(os.environ.get("DECKGEN", Path.cwd()))
sys.path.insert(0, str(SKILL / "scripts"))
import layout as port  # noqa: E402
from deckgen_contracts import DatasetRowRange, Element, SlideModel, StyleGuide, walk  # noqa: E402
from deckgen_server.layout.solver import master_zones, solve  # noqa: E402
from deckgen_server.layout.validation import validate_geometry  # noqa: E402
from deckgen_server.lineage.datasets import load_dataset_bundle, resolve_table_cells  # noqa: E402
from deckgen_server.lineage.text import paragraph_texts  # noqa: E402

FIX = DECKGEN / "fixtures" / "default_house_style"
OUT = Path(os.environ.get("ORACLE_OUT") or tempfile.mkdtemp(prefix="oracle_compare_")) / "specimen_specs"
print(f"skill {SKILL}; deckgen {DECKGEN}; specs in {OUT}")
OUT.mkdir(parents=True, exist_ok=True)

raw_guide = json.loads((FIX / "guide.json").read_text())
guide = StyleGuide.model_validate(raw_guide)
pguide = port.load_guide(raw_guide)
data = load_dataset_bundle(FIX / "specimen/datasets.json")
zones = [{**z.box.model_dump(), "source": z.source} for z in master_zones(guide)]


def convert(raw: dict, nodes: dict[str, Element]) -> dict:
    if raw["node_type"] == "region":
        return {"type": "region", "id": raw["id"], "weight": raw.get("weight"), "layout": raw["layout"],
                "children": [convert(c, nodes) for c in raw["children"]]}
    content = raw["content"]
    out = {"type": "element", "id": raw["id"], "weight": raw.get("weight"), "scale_class": raw["scale_class"]}
    if content["payload_type"] == "text_runs":
        element = nodes[raw["id"]]
        texts = paragraph_texts(data, element, guide)
        groups: dict[int, list[dict]] = {}
        for run in content["runs"]:
            groups.setdefault(run["paragraph"], []).append(run)
        out["kind"] = "text"
        # The port applies the role's case itself, so the raw (uncased) text goes
        # in; refs are resolved here because the port carries no datasets.
        out["paragraphs"] = [{"role": runs[0]["type_role"], "text": "".join(r["text"] for r in runs) if "{ref:" not in "".join(r["text"] for r in runs) else texts[i], "bullet_level": runs[0]["bullet_level"]} for i, runs in sorted(groups.items())]
    elif content["payload_type"] == "table_ref":
        dataset, cells = resolve_table_cells(data, node_id=raw["id"], dataset_id=content["dataset_id"], row_range=DatasetRowRange(**content["row_range"]), column_keys=content["column_keys"])
        by_key = {c.key: c for c in dataset.columns}
        out["kind"] = "table"
        out["table"] = {"columns": [{"key": k, "label": by_key[k].label, "value_kind": by_key[k].value_kind} for k in content["column_keys"]], "rows": cells, "header_rows": content["header_row_count"]}
    elif content["payload_type"] == "series_ref":
        out["kind"] = "chart"
    elif content["payload_type"] == "decor":
        out["kind"] = "rule"
    else:
        out["kind"] = "image"
    return out


def boxes_of(resolved) -> dict[str, tuple[int, int, int, int]]:
    return {k: (b.left, b.top, b.width, b.height) for k, b in resolved.boxes.items() if "#" not in k}


ignored = 0
summary = []
for path in sorted((FIX / "specimen/slides").glob("*.json")):
    raw = json.loads(path.read_text())
    model = SlideModel.model_validate(raw)
    nodes = {n.id: n for n, _ in walk(model.root) if isinstance(n, Element)}
    ignored += sum(1 for n in nodes.values() if n.annotation is not None or n.chrome_id is not None)
    spec_raw = {"page": {**{k: raw["page_geometry"][k] for k in ("width_emu", "height_emu")}, "reserved_zones": zones},
                "root": convert(raw["root"], nodes), "splittable_groups": raw["splittable_groups"]}
    (OUT / path.name).write_text(json.dumps(spec_raw, indent=1))
    spec = port.parse_spec(spec_raw)
    row = {"slide": path.stem}
    for scale in (1.0, 0.85, 0.73):
        expected = boxes_of(solve(model, guide, scale))
        actual = {k: (b.left, b.top, b.width, b.height) for k, b in port.solve_tree(spec, pguide, scale).items()}
        shared = sorted(set(expected) & set(actual))
        diff = max((abs(e - a) for k in shared for e, a in zip(expected[k], actual[k])), default=0)
        row[f"s={scale}"] = {"boxes": len(shared), "max_diff_emu": diff, "missing": sorted(set(expected) ^ set(actual))}
    # extra: the five shared validation codes at 1.0 on the pure solve
    codes = ("containment", "overlap", "exceeds_page", "overcommit", "zero_dimension", "reserved_zone")
    theirs = sorted((v.code, v.node_id) for v in validate_geometry(solve(model, guide, 1.0), guide).violations if v.code in codes)
    mine = sorted((v.code, v.node_id) for v in port.validate(spec, pguide, Fraction(1), port.solve_tree(spec, pguide, 1.0), {}) if v.code in codes)
    row["validation_1.0"] = {"deckgen": theirs, "port": mine, "agree": theirs == mine}
    summary.append(row)
    print(json.dumps(row))

print("ignored annotation/chrome elements:", ignored)
print("TOTAL boxes compared:", sum(r["s=1.0"]["boxes"] for r in summary), "max diff over all slides and scales:",
      max(r[f"s={s}"]["max_diff_emu"] for r in summary for s in (1.0, 0.85, 0.73)),
      "validation agreement:", sum(r["validation_1.0"]["agree"] for r in summary), "/", len(summary))
