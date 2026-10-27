"""(c) Port half: the port's ruler(s) over the shared cases vs deckgen's HarfBuzz oracle."""

import json
import os
import sys
import tempfile
from pathlib import Path

# argv[1]: the oracle file ruler_oracle.py wrote (default: ruler_oracle.json in the system
# temporary directory); PPTX_SKILL: the skill under test (default: the repo this file sits in)
SKILL = Path(os.environ.get("PPTX_SKILL", Path(__file__).resolve().parents[2] / "skills" / "designing-presentations"))
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import textfit  # noqa: E402
from ruler_cases import CASES, FAMILY, SIZE_PT  # noqa: E402

src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "ruler_oracle.json"
oracle = {(o["text"], o["width"]): o for o in json.loads(src.read_text())}
index = textfit.default_index()
face = index.resolve(FAMILY)
rulers = [textfit.PillowRuler()]
if textfit.hb is not None:
    rulers.append(textfit.HarfBuzzRuler())
for ruler in rulers:
    exact = same_count = 0
    max_line_diff = max_adv_diff = 0
    disagreements = []
    diffs = []
    worst = None
    for text, width in CASES:
        o = oracle[(text, width)]
        lines = textfit.measure_text(ruler, text, width, face.path, SIZE_PT)
        mine = [l.text for l in lines]
        exact += mine == o["lines"]
        same_count += len(mine) == len(o["lines"])
        if mine == o["lines"]:
            for a, b in zip([l.width_emu for l in lines], o["widths"]):
                diffs.append(abs(a - b))
                if abs(a - b) > max_line_diff:
                    max_line_diff, worst = abs(a - b), text[:50]
        else:
            disagreements.append((text[:40], width, len(mine), len(o["lines"])))
        max_adv_diff = max(max_adv_diff, abs(textfit.advance_emu(ruler, text, face.path, SIZE_PT) - o["advance"]))
    print(f"[{ruler.name}] face {face.path} (same as oracle: {face.path == o['face']})")
    print(f"  exact-break agreement {exact}/{len(CASES)}; same line count {same_count}/{len(CASES)}")
    diffs.sort()
    print(f"  per-line width difference on agreeing cases ({len(diffs)} lines): p50 {diffs[len(diffs)//2]} EMU, p95 {diffs[int(len(diffs)*0.95)]} EMU, max {max_line_diff} EMU on {worst!r}; max whole-sentence advance difference: {max_adv_diff} EMU")
    for d in disagreements:
        print("  differs:", d)
