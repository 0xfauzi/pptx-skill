#!/usr/bin/env python3
"""A copy of the skill with the worked examples of the decks under test held out.

    python3 dev/evals/holdout.py [--reference REF.pptx ...] [--alias WORD ...] --out DIR

With no --reference the copy is for a run with no reference deck: no worked example is
held out (none is made from a deck under test).

The skill ships worked examples (a completion, a digest, deck specs, build proofs) made
from public reference decks. An evaluation that tests the skill on one of those decks
would grade the examples, not the skill. This writes the shipped skill directory
(skills/designing-presentations) to DIR (outside it, new or empty) without every example examples/PROVENANCE.json ties to a reference
given here, matched by the reference file's sha256, or by its twin's stem (the same deck in
another format: the PDF of a pptx whose examples PROVENANCE.json lists). It refuses a skill
tree holding an example file PROVENANCE.json does not name (it could not say whether that
file is made from the deck under test). It prints, as JSON, what it held out and every
line of the copied text that still names a held-out deck by an alias (reference files
cite the decks they were measured on): the evaluator reads that list and decides; nothing
here edits the skill's text.

refs/files (the judge's panel) becomes a folder of copies of its files, never
linked: the decks under test are left out by sha256 and by name (the same deck in another
format), and the copy's refs/MANIFEST.md loses their rows (their download URLs). The agent
under test must not reach the deck it is tested on through the panel (round 7: the copy linked
the whole folder, then each file, and one readlink named the folder still holding the deck).
An absolute path to the skill in the copied text is rewritten to the copy, where the held-out
files do not exist. Bytecode caches are left
out. The repository's dev/ (these scenarios' expected behaviours, the port audit) is outside
the skill directory, so the agent under test never sees it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "skills" / "designing-presentations"
SKIP_DIRS = {".git", "__pycache__", ".claude", ".ruff_cache", ".mypy_cache", ".pytest_cache"}  # caches name the skill's own paths
TEXT_SUFFIXES = {".md", ".json", ".py", ".sh", ".txt"}


class Refused(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def provenance() -> dict:
    """examples/PROVENANCE.json, proven against the examples directory: every example file
    named exactly once, every named file present."""
    prov = json.loads((SKILL / "examples" / "PROVENANCE.json").read_text())
    named: list[str] = list(prov.get("independent") or [])
    for name, entry in (prov.get("references") or {}).items():
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str) or not isinstance(entry.get("examples"), list):
            raise Refused(f"PROVENANCE.json: reference {name!r} needs sha256 and examples")
        named += entry["examples"]
    present = sorted(str(p.relative_to(SKILL / "examples")) for p in (SKILL / "examples").rglob("*")
                     if p.is_file() and not SKIP_DIRS & set(p.relative_to(SKILL).parts))
    twice = sorted({n for n in named if named.count(n) > 1})
    unnamed = sorted(set(present) - set(named))
    missing = sorted(set(named) - set(present))
    problems = ([f"named more than once: {twice}"] if twice else []) + ([f"not named (made from which deck?): {unnamed}"] if unnamed else []) \
        + ([f"named and absent: {missing}"] if missing else [])
    if problems:
        raise Refused("examples/PROVENANCE.json does not account for examples/: " + "; ".join(problems))
    return prov


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", action="append", default=[],
                    help="a reference deck the evaluation tests on (repeatable; none for a run with no reference)")
    ap.add_argument("--alias", action="append", default=[], help="another word the skill's files may use for a tested deck (repeatable)")
    ap.add_argument("--out", required=True, help="a new or empty directory outside the skill")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if out == SKILL or SKILL in out.parents:
        raise Refused(f"--out {out} is inside the skill; the held-out copy goes outside it")
    if out.exists() and any(out.iterdir()):
        raise Refused(f"--out {out} is not empty")
    prov = provenance()
    tested = {}
    for ref in args.reference:
        path = Path(ref)
        if not path.is_file():
            raise Refused(f"--reference {ref}: no such file")
        tested[sha256(path)] = path.name
    held: dict[str, list[str]] = {}
    # a tested deck's own name is always searched for, and its twin (the same stem in another
    # format: the PDF of a pptx) is the same deck, by the rule the panel below uses
    tested_stems = {Path(t).stem.lower() for t in tested.values()}
    aliases = [a.lower() for a in args.alias] + sorted(tested_stems)
    for name, entry in prov["references"].items():
        if entry["sha256"] in tested or Path(name).stem.lower() in tested_stems:
            held[name] = entry["examples"]
            aliases += [a.lower() for a in entry.get("aliases") or []] + [Path(name).stem.lower()]
    left_out = {str(Path("examples") / f) for files in held.values() for f in files}

    def ignore(folder: str, names: list[str]) -> set[str]:
        rel = Path(folder).resolve().relative_to(SKILL)
        return {n for n in names if n in SKIP_DIRS or str(rel / n) in left_out}

    shutil.copytree(SKILL, out, symlinks=True, ignore=ignore, dirs_exist_ok=True)
    panel = SKILL / "refs" / "files"
    withheld: list[str] = []
    if panel.exists():
        copied = out / "refs" / "files"
        if copied.is_symlink() or copied.is_file():
            copied.unlink()
        elif copied.is_dir():
            shutil.rmtree(copied)
        copied.mkdir(parents=True)
        for f in sorted(panel.resolve().iterdir()):
            if not f.is_file():
                continue
            # by bytes, or by name: the same deck in another format (a PDF of the pptx under test)
            if sha256(f) in tested or f.stem.lower() in tested_stems | set(aliases):
                withheld.append(f.name)
                continue
            shutil.copy2(f, copied / f.name)  # a copy: a link names the folder, or shares the panel's bytes for writing
        manifest = out / "refs" / "MANIFEST.md"
        if manifest.is_file() and withheld:
            rows = manifest.read_text().splitlines(keepends=True)
            manifest.write_text("".join(r for r in rows if not any(r.startswith(f"| {w} ") for w in withheld)))
    roots_panel = str(panel.resolve())
    roots = sorted({str(SKILL), roots_panel}, key=len, reverse=True)  # the longer first: one may hold the other
    links = [str(p.relative_to(out)) for p in out.rglob("*") if p.is_symlink()]
    if links:
        raise Refused(f"the copy holds symbolic links, each naming a place outside it: {links}")
    naming = []
    for p in sorted(out.rglob("*")):
        if p.is_symlink() or not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        text = p.read_text(errors="replace")
        # a pointer to a held-out file says so in the copy, so the agent under test is not
        # sent looking for the worked answer to its own deck (round 6, mckinsey)
        marked = text
        for root in roots:
            marked = marked.replace(root, str(out / "refs" / "files") if root == roots_panel else str(out))
        for f in sorted(left_out):
            marked = marked.replace(f"`{f}`", f"`{f}` (held out of this copy: it is made from the deck under test)")
        if marked != text:
            p.write_text(marked)
        for i, line in enumerate(marked.splitlines(), 1):
            low = line.lower()
            hit = [a for a in aliases if a and a in low]
            if hit:
                naming.append({"file": str(p.relative_to(out)), "line": i, "names": hit})
    print(json.dumps({"out": str(out), "tested": sorted(tested.values()) or "no reference: a run with no reference deck",
                      "held_out": held or "nothing: no example of examples/PROVENANCE.json is made from a deck given",
                      "untested_examples_kept": sorted(n for n in prov["references"] if n not in held),
                      "panel_withheld": withheld or "nothing: no file of refs/files is a deck given",
                      "lines_still_naming_a_tested_deck": len(naming), "naming": naming,
                      "note": "the naming lines are the skill's own references citing measurements on the tested decks; "
                              "read them and decide whether the evaluation can stand with them"}, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        sys.exit(2)
