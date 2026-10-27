#!/usr/bin/env python3
"""Build the upload zip of the shipped skill, for claude.ai or the Skills API.

    python3 dev/tools/package_skill.py [-o dist/designing-presentations.zip]

The zip holds the skill directory itself as its one top-level entry
(designing-presentations/SKILL.md, ...), as claude.ai and the API ask, and only the files
git tracks there, as committed: a file in the skill that git does not track, or ignores, is
refused by name, as is a tracked file changed since the last commit, and every byte it
writes is read from the commit (git's blobs at HEAD), never from the working tree, so
nothing that is not in the repository reaches an upload. The one exception is the judge's
panel the user fetches (refs/files, refs/library: third-party decks, git-ignored, never shipped), which is
left out. It refuses, by name, a skill whose frontmatter claude.ai or the API would reject,
or that this reader cannot read as written: a frontmatter line that is not a one-line plain
`key: value` (a block, quoted or continued value is not read, so it is not checked); a key outside the six the Agent Skills specification defines; a name that is not the
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
import time
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


def committed() -> dict[str, tuple[str, str]]:
    """The skill's files as the last commit holds them: path relative to the skill, with its
    git mode and blob id. What ships is read from here, never from the working tree, so an
    index flag (assume-unchanged, skip-worktree) that hides an edit from git diff cannot
    carry the edit into the zip."""
    done = subprocess.run(["git", "-C", str(SKILL), "ls-tree", "-r", "-z", "HEAD", "--", "."], capture_output=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"refused: git ls-tree HEAD failed in {SKILL} ({done.stderr.decode(errors='replace').strip()}); "
                         "the packager builds from a git checkout only")
    out = {}
    for entry in done.stdout.decode("utf-8").split("\0"):
        if entry:
            meta, _, rel = entry.partition("\t")
            mode, _kind, oid = meta.split()
            out[rel] = (mode, oid)
    return out


def blob(oid: str) -> bytes:
    return subprocess.run(["git", "-C", str(SKILL), "cat-file", "blob", oid], capture_output=True, check=True).stdout


def left_out(rel: str) -> bool:
    return any(rel == d or rel.startswith(d + "/") for d in LEFT_OUT)


#: the first character of a YAML value that is not a one-line plain scalar: a block scalar
#: (| or >), a quoted or flow value, an anchor, alias, tag, comment or directive
NOT_PLAIN = tuple("|>\"'[]{}&*!#%@`")


def frontmatter(text: str) -> dict[str, str]:
    """The frontmatter as one-line plain `key: value` pairs, the only YAML form read here.
    Any other line (a block scalar, a continuation, a quoted or flow value, a repeated key, a
    value YAML would cut at ' #' or reject at ': ') is refused by name: a reader that skipped
    it would check a value claude.ai reads differently."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        raise SystemExit("refused: SKILL.md has no frontmatter between --- lines")
    out: dict[str, str] = {}
    for n, line in enumerate(m.group(1).split("\n"), 2):
        key, sep, value = line.partition(":")
        value = value.strip()
        why = ("an empty or indented line" if not line.strip() or line[0] in " \t" else
               "no 'key:'" if not sep or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key) else
               f"{key!r} is repeated" if key in out else
               f"{key!r} has no value on its line" if not value else
               f"{key!r} is not a plain scalar (it opens with {value[0]!r})" if value.startswith(NOT_PLAIN) else
               f"{key!r} holds ': ' or ' #', which YAML reads as a mapping or a comment" if ": " in value or " #" in value else None)
        if why:
            raise SystemExit(f"refused: SKILL.md frontmatter line {n}: {why}; the packager reads one-line plain `key: value` lines only")
        out[key] = value
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default=str(ROOT / "dist" / f"{SKILL.name}.zip"))
    args = ap.parse_args(argv)
    tree = committed()
    for need in ("SKILL.md", "LICENSE.txt"):
        if tree.get(need, ("",))[0] != "100644":
            raise SystemExit(f"refused: {need} is not a committed regular file of the skill")
    fm = frontmatter(blob(tree["SKILL.md"][1]).decode("utf-8"))
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
    root_license = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:LICENSE"], capture_output=True, check=False).stdout
    if blob(tree["LICENSE.txt"][1]) != root_license:
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
    for rel, (mode, oid) in sorted(tree.items()):
        if left_out(rel):
            problems.append(f"{rel} is committed inside {LEFT_OUT}, the third-party panel that is never shipped")
        elif mode == "120000":
            problems.append(f"{rel} is a symbolic link")
        elif mode not in ("100644", "100755"):
            problems.append(f"{rel} is committed as mode {mode}, not a file (a submodule)")
        else:
            files.append((rel, mode, blob(oid)))
    total = sum(len(data) for _, _, data in files)
    if total > MAX_UPLOAD_BYTES:
        problems.append(f"{total} bytes uncompressed, over the API's {MAX_UPLOAD_BYTES}")
    if problems:
        raise SystemExit("refused: " + "; ".join(problems))
    out = Path(args.out).resolve()
    if out == SKILL or SKILL in out.parents:
        raise SystemExit(f"refused: {out} is inside the skill directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        stamp = time.gmtime(int(subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct", "HEAD"], capture_output=True, check=True).stdout))
        for rel, mode, data in files:
            info = zipfile.ZipInfo(f"{SKILL.name}/{rel}", date_time=stamp[:6])
            info.external_attr = int(mode, 8) << 16  # the committed mode: scripts stay executable
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    print(f"wrote {out}: {len(files)} files, {total} bytes uncompressed, {out.stat().st_size} bytes zipped; "
          f"top-level entry {SKILL.name}/; frontmatter keys {sorted(fm)}; description {len(fm['description'])} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
