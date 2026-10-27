#!/usr/bin/env python3
"""Build the upload zip of the shipped skill, for claude.ai or the Skills API.

    python3 dev/tools/package_skill.py [-o dist/designing-presentations.zip]

The zip holds the skill directory itself as its one top-level entry
(designing-presentations/SKILL.md, ...), as claude.ai and the API ask, and only the files
git tracks there, as committed: a file in the skill that git does not track, or ignores, is
refused by name, as is a tracked file changed since the last commit, so nothing that is not
in the repository reaches an upload. The one exception is the judge's panel the user
fetches (refs/files, refs/library: third-party decks, git-ignored, never shipped), which is
left out. It refuses, by name, a skill whose frontmatter claude.ai or the API would reject:
a key outside the six the Agent Skills specification defines; a name that is not the
directory's, breaks the name rule, holds a reserved word ("anthropic", "claude") or an XML
tag; a description empty, past 200 characters (claude.ai's limit, the strictest of the
documents; the API and the specification allow 1,024) or holding an XML tag; a
compatibility past 500. It refuses any symbolic link, a LICENSE.txt that differs from the
repository's LICENSE, and a total past the API's 30 MB uncompressed. It prints what it
wrote, the file count and both sizes.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins" / "designing-presentations" / "skills" / "designing-presentations"
#: the frontmatter keys the Agent Skills specification defines, the only ones a claude.ai or
#: API upload accepts (code.claude.com/docs/en/skills, Frontmatter reference)
UPLOAD_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
#: the strictest of the three: support.claude.com/en/articles/12512198 (how to create custom
#: skills: "200 characters maximum"); platform.claude.com skills guide and agentskills.io
#: specification: 1,024
MAX_DESCRIPTION = 200
#: platform.claude.com skills guide, Limits and constraints: name and description hold no XML
#: tags, and the name no reserved word
RESERVED_WORDS = ("anthropic", "claude")
XML_TAG = re.compile(r"<\s*/?\s*[A-Za-z_][^<>]*>")
MAX_COMPATIBILITY = 500  # agentskills.io/specification
#: a name: lowercase letters, digits and single hyphens, not at either end, at most 64
NAME = re.compile(r"^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$")
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # platform.claude.com skills guide: under 30 MB uncompressed
#: git-ignored folders of third-party decks the user fetches; never shipped, never refused
LEFT_OUT = ("refs/files", "refs/library")


def git(*args: str) -> list[str]:
    """NUL-separated paths from git, relative to the skill directory."""
    done = subprocess.run(["git", "-C", str(SKILL), *args, "-z", "--", "."], capture_output=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"refused: git {' '.join(args)} failed in {SKILL} ({done.stderr.decode(errors='replace').strip()}); "
                         "the packager builds from a git checkout only")
    return [p for p in done.stdout.decode("utf-8").split("\0") if p]


def left_out(rel: str) -> bool:
    return any(rel == d or rel.startswith(d + "/") for d in LEFT_OUT)


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
    for word in RESERVED_WORDS:
        if word in fm.get("name", "").lower():
            problems.append(f"name {fm.get('name')!r} holds the reserved word {word!r}")
    for key in ("name", "description"):
        if XML_TAG.search(fm.get(key, "")):
            problems.append(f"{key} holds an XML tag ({XML_TAG.search(fm[key]).group(0)!r})")
    if len(fm.get("compatibility", "")) > MAX_COMPATIBILITY:
        problems.append(f"compatibility is {len(fm['compatibility'])} characters, over {MAX_COMPATIBILITY}")
    if fm.get("name") != SKILL.name:
        problems.append(f"name {fm.get('name')!r} is not the directory's name {SKILL.name!r}")
    if not 1 <= len(fm.get("description", "")) <= MAX_DESCRIPTION:
        problems.append(f"description is {len(fm.get('description', ''))} characters (1 to {MAX_DESCRIPTION})")
    if (SKILL / "LICENSE.txt").read_bytes() != (ROOT / "LICENSE").read_bytes():
        problems.append("LICENSE.txt differs from the repository's LICENSE")
    # what git tracks is what ships; everything else in the folder is named and refused
    untracked = [r for r in git("ls-files", "--others", "--exclude-standard") if not left_out(r)]
    ignored = [r for r in git("ls-files", "--others", "--ignored", "--exclude-standard", "--directory") if not left_out(r.rstrip("/"))]
    changed = git("diff", "--name-only", "HEAD")
    if untracked:
        problems.append(f"{len(untracked)} file(s) in the skill that git does not track: {untracked[:10]}")
    if ignored:
        problems.append(f"{len(ignored)} git-ignored path(s) in the skill (only refs/files and refs/library may be): {ignored[:10]}")
    if changed:
        problems.append(f"{len(changed)} tracked file(s) changed since the last commit: {changed[:10]}; commit or restore them")
    files = []
    for rel in sorted(git("ls-files", "--cached")):
        p = SKILL / rel
        if left_out(rel):
            problems.append(f"{rel} is tracked inside {LEFT_OUT}, the third-party panel that is never shipped")
        elif p.is_symlink():
            problems.append(f"{rel} is a symbolic link")
        elif not p.is_file():
            problems.append(f"{rel} is tracked but not a file here (deleted, or a submodule)")
        else:
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
