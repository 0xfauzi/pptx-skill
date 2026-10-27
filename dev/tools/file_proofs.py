#!/usr/bin/env python3
"""File a rebuild's build reports as dev/proofs, with every machine path named by a placeholder.

    python3 dev/tools/file_proofs.py --map /abs/skill='$SKILL' --map /abs/out='$WORK' \\
        --map /abs/deckgen='$DECKGEN' OUT/kb/section/deck.build.json:keybank-section.build.json ...

Each report is JSON. Every string in it that holds a mapped prefix has the prefix replaced
(the longest first), so a proof reads `$WORK/kb/section/deck.pptx` where the rebuild wrote
an absolute path in its own scratch directory. A report that still holds an absolute
path under /tmp, /home, /Users, /root, /private or /var after the mapping is refused by
name and nothing is written: a proof is read by anyone who clones the repository, and an
unmapped prefix names the machine and the session that made it. The JSON is written back
as the build writes it (json.dumps, indent 1), so a filed proof differs from its report only
in the mapped prefixes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROOFS = Path(__file__).resolve().parents[1] / "proofs"
#: an absolute path a proof must not carry: a home, a temporary or a system-private folder
MACHINE_PATH = re.compile(r"(?<![\w$])/(tmp|home|Users|root|private|var)/[^\s\"'),;]*")


def remap(value, prefixes: list[tuple[str, str]]):
    if isinstance(value, dict):
        return {remap(k, prefixes): remap(v, prefixes) for k, v in value.items()}
    if isinstance(value, list):
        return [remap(v, prefixes) for v in value]
    if isinstance(value, str):
        for prefix, name in prefixes:
            value = value.replace(prefix, name)
    return value


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--map", action="append", default=[], metavar="PREFIX=NAME", help="an absolute prefix and its placeholder")
    ap.add_argument("pairs", nargs="+", metavar="REPORT:PROOF", help="a build report and the file name it is filed under in dev/proofs")
    args = ap.parse_args(argv)
    prefixes = []
    for m in args.map:
        prefix, sep, name = m.partition("=")
        if not sep or not prefix.startswith("/") or not name:
            raise SystemExit(f"refused: --map {m!r} is not /absolute/prefix=NAME")
        prefixes.append((prefix.rstrip("/"), name))
    prefixes.sort(key=lambda p: -len(p[0]))
    out, problems = {}, []
    for pair in args.pairs:
        src, sep, name = pair.rpartition(":")
        if not sep or "/" in name or not name.endswith(".json"):
            raise SystemExit(f"refused: {pair!r} is not REPORT:NAME.json")
        text = json.dumps(remap(json.loads(Path(src).read_text(encoding="utf-8")), prefixes), indent=1)
        hits = sorted({h.group(0)[:80] for h in MACHINE_PATH.finditer(text)})
        if hits:
            problems.append(f"{src}: {len(hits)} unmapped machine path(s), e.g. {hits[:3]}")
        out[name] = text
    if problems:
        raise SystemExit("refused, nothing written: " + "; ".join(problems))
    for name, text in out.items():
        (PROOFS / name).write_text(text, encoding="utf-8")
        print(f"filed dev/proofs/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
