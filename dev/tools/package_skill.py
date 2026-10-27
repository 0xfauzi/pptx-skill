#!/usr/bin/env python3
"""Build the upload zip of the shipped skill, for claude.ai or the Skills API.

    python3 dev/tools/package_skill.py [-o dist/designing-presentations.zip]

The zip holds the skill directory itself as its one top-level entry
(designing-presentations/SKILL.md, ...), as claude.ai and the API ask. Left out: the
judge's panel the user fetches (refs/files, refs/library: third-party decks, never shipped)
and bytecode caches. It refuses, by name, a skill whose frontmatter claude.ai or the API
would reject (a key outside the six the Agent Skills specification defines, a name that is
not the directory's or breaks the spec's name rule, a description past 1,024 characters
or a compatibility past 500), any other symbolic link, a
LICENSE.txt that differs from the repository's LICENSE, and a total past the API's 30 MB
uncompressed. It prints what it wrote, the file count and both sizes.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins" / "designing-presentations" / "skills" / "designing-presentations"
#: the frontmatter keys the Agent Skills specification defines, the only ones a claude.ai or
#: API upload accepts (code.claude.com/docs/en/skills, Frontmatter reference)
UPLOAD_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
MAX_DESCRIPTION = 1024  # agentskills.io/specification; platform.claude.com Agent Skills overview
MAX_COMPATIBILITY = 500  # agentskills.io/specification
#: a name: lowercase letters, digits and single hyphens, not at either end, at most 64
NAME = re.compile(r"^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$")
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # platform.claude.com skills guide: under 30 MB uncompressed
LEFT_OUT = {"refs/files", "refs/library"}
SKIP_PARTS = {"__pycache__", ".DS_Store"}


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        raise SystemExit("refused: SKILL.md has no frontmatter between --- lines")
    out = {}
    for line in m.group(1).splitlines():
        if line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default=str(ROOT / "dist" / f"{SKILL.name}.zip"))
    args = ap.parse_args(argv)
    fm = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    problems = []
    if set(fm) - UPLOAD_KEYS:
        problems.append(f"frontmatter keys {sorted(set(fm) - UPLOAD_KEYS)} are not among the six an upload accepts {sorted(UPLOAD_KEYS)}")
    if not NAME.match(fm.get("name", "")):
        problems.append(f"name {fm.get('name')!r} is not 1 to 64 lowercase letters, digits and single hyphens")
    if len(fm.get("compatibility", "")) > MAX_COMPATIBILITY:
        problems.append(f"compatibility is {len(fm['compatibility'])} characters, over {MAX_COMPATIBILITY}")
    if fm.get("name") != SKILL.name:
        problems.append(f"name {fm.get('name')!r} is not the directory's name {SKILL.name!r}")
    if not 1 <= len(fm.get("description", "")) <= MAX_DESCRIPTION:
        problems.append(f"description is {len(fm.get('description', ''))} characters (1 to {MAX_DESCRIPTION})")
    if (SKILL / "LICENSE.txt").read_bytes() != (ROOT / "LICENSE").read_bytes():
        problems.append("LICENSE.txt differs from the repository's LICENSE")
    files = []
    for p in sorted(SKILL.rglob("*")):
        rel = p.relative_to(SKILL).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in LEFT_OUT) or SKIP_PARTS & set(p.relative_to(SKILL).parts):
            continue
        if p.is_symlink():
            problems.append(f"{rel} is a symbolic link")
        elif p.is_file():
            files.append((p, rel))
    total = sum(p.stat().st_size for p, _ in files)
    if total > MAX_UPLOAD_BYTES:
        problems.append(f"{total} bytes uncompressed, over the API's {MAX_UPLOAD_BYTES}")
    if problems:
        raise SystemExit("refused: " + "; ".join(problems))
    out = Path(args.out).resolve()
    if out == SKILL or SKILL in out.parents:
        raise SystemExit(f"refused: {out} is inside the skill directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in files:
            z.write(p, f"{SKILL.name}/{rel}")
    print(f"wrote {out}: {len(files)} files, {total} bytes uncompressed, {out.stat().st_size} bytes zipped; "
          f"top-level entry {SKILL.name}/; frontmatter keys {sorted(fm)}; description {len(fm['description'])} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
