"""Compare the port's guide with deckgen's draft on the same deck: core roles, spacing, floors, density.

Run: cd /home/user/deckgen && uv run python -I <this file> jazz keybank netflix exhibits

Each name is a deck under $DECKGEN/fixtures/corpus/<name>.pptx (DECKGEN defaults to the
working directory). deckgen's draft comes from deckgen_server.style.compiler.extract in
this process; the port's comes from `python3 -I scripts/extract_style.py` of the skill at
$PPTX_SKILL (default: the repo this file sits in), run as a subprocess so the port is
measured with the interpreter it ships for. Both drafts land in $ORACLE_OUT (default: a
fresh temporary directory), never in either repo.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from deckgen_server.style.compiler import extract

SKILL = Path(os.environ.get("PPTX_SKILL", Path(__file__).resolve().parents[2] / "skills" / "designing-presentations"))
DECKGEN = Path(os.environ.get("DECKGEN", Path.cwd()))
S = Path(os.environ.get("ORACLE_OUT") or tempfile.mkdtemp(prefix="diff_oracle_"))
S.mkdir(parents=True, exist_ok=True)
print(f"skill {SKILL}; deckgen {DECKGEN}; drafts in {S}")
for name in sys.argv[1:]:
    deck = DECKGEN / "fixtures" / "corpus" / f"{name}.pptx"
    draft = extract(deck.read_bytes(), reference_identity=name).model_dump(mode="json")
    (S / f"deckgen_draft_{name}.json").write_text(json.dumps(draft, indent=1))
    subprocess.run(["python3", "-I", str(SKILL / "scripts" / "extract_style.py"), str(deck), "-o", str(S / f"{name}.style.json")],
                   check=True, stdout=subprocess.DEVNULL)
    d = draft["values"]
    g = json.load(open(S / f"{name}.style.json"))
    print(f"==== {name}")
    def dv(path):
        v = d.get(path)
        if isinstance(v, dict) and "value" in v: return v["value"]
        return v
    rows = []
    # typography roles
    for role in ("type.title","type.h1","type.h2","type.body","type.emphasis","type.caption","type.footnote","type.kicker","type.table_header","type.table_cell","type.axis_label","type.data_label"):
        mine = g["typography"]["roles"].get(role)
        theirs = {}
        for member in ("size_pt","weight","alignment","case","space_before_pt","space_after_pt"):
            v = dv(f"/typography/roles/{role}/value/{member}")
            if v is None:
                whole = dv(f"/typography/roles/{role}")
                if isinstance(whole, dict): v = whole.get(member)
            theirs[member] = v
        rows.append((role, {k: (mine or {}).get(k) for k in theirs}, theirs))
    for role in ("color.surface","color.surface_alt","color.ink","color.ink_muted","color.ink_inverse","color.rule","color.accent1","color.accent2","color.accent3","color.positive","color.negative"):
        mine = (g["color"]["roles"].get(role) or {}).get("hex")
        t = dv(f"/color/roles/{role}")
        rows.append((role, mine, (t or {}).get("hex","").lstrip("#") if isinstance(t, dict) else t))
    for step in ("space.xs","space.sm","space.md","space.lg","space.xl","space.gutter","space.margin"):
        rows.append((step, (g["spacing"]["steps"].get(step) or {}).get("emu"), dv(f"/spacing/steps/{step}")))
    for fam in ("body","annotation","display","chart"):
        t = dv(f"/floors/{fam}")
        rows.append((f"floor.{fam}", (g["floors"].get(fam) or {}).get("floor_pt"), (t or {}).get("floor_pt") if isinstance(t, dict) else dv(f"/floors/{fam}/floor_pt")))
    for m in ("elements_per_slide","content_area_fraction","words_per_slide"):
        t = dv(f"/density_bands/{m}")
        mine = g["density_bands"].get(m, {})
        rows.append((f"density.{m}", (mine.get("low"), mine.get("high")), ((t or {}).get("low"), (t or {}).get("high")) if isinstance(t, dict) else t))
    rows.append(("motifs", [m["name"] for m in g.get("motifs", [])], [m.get("name") for m in (dv("/motifs") or [])]))
    rows.append(("archetypes", len(g["composition"]["archetypes"]), len(dv("/composition/archetypes") or [])))
    rows.append(("unresolved", len(g["unresolved"]), len(draft["unresolved"])))
    for k, mine, theirs in rows:
        flag = "" if json.dumps(mine, default=str) == json.dumps(theirs, default=str) else "  <-- differs"
        print(f"  {k:28s} port={json.dumps(mine, default=str)[:70]:72s} deckgen={json.dumps(theirs, default=str)[:70]}{flag}")
