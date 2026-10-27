"""(c) Oracle half: deckgen's HarfBuzz measure_text over the shared cases.

Run: cd "$DECKGEN" && uv run python -I <this> [oracle.json]
(default output: ruler_oracle.json in the system temporary directory)."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruler_cases import CASES, FAMILY, SIZE_PT  # noqa: E402

from deckgen_server.measure.text import advance_emu, measure_text  # noqa: E402

out = []
for text, width in CASES:
    m = measure_text([text], width, FAMILY, SIZE_PT)
    out.append({"text": text, "width": width, "lines": [l.text for l in m.lines], "widths": [l.width_emu for l in m.lines],
                "advance": advance_emu(text, FAMILY, SIZE_PT), "face": m.face_path})
dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "ruler_oracle.json"
dest.write_text(json.dumps(out, indent=1))
print("wrote", len(out), "oracle measurements to", dest, "; face", out[0]["face"])
