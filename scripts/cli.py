"""What every command shares: where it may write, and how it exits.

A command writes only outside this skill. Company files, guides, digests, renders and
builds belong to the user's work directory (SKILL.md: `DECK_WORK`), never to the skill,
so every output path a command takes passes `out_path`, which refuses one inside the
skill by name. Two maintenance commands write skill content and are the only exceptions:
`component.py admit` records an admission beside the component it admits (a component
shipped in `components/` is part of the skill), and `library.py import` builds the
git-ignored external library of public decks in `refs/library` (Library.guard_location
refuses any other owner there). `refs/fetch.sh` fills the git-ignored `refs/files`.

`run` calls a command's main and turns a closed stdout (`... | head`) into a quiet exit
instead of a BrokenPipeError traceback.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
WORK_ENV = "DECK_WORK"


def inside_skill(path: str | Path) -> bool:
    """Inside the skill as written or as resolved: refs/files may be a symlink to a
    folder elsewhere, and a path through it is still a path into the skill."""
    skill = {SKILL_DIR, Path(os.path.abspath(Path(__file__).parent.parent))}
    as_written = Path(os.path.abspath(Path(path).expanduser()))
    return any(p == s or s in p.parents for p in (as_written, as_written.resolve()) for s in skill)


def out_path(path: str | Path, what: str = "output") -> Path:
    """The output path, refused when it lies inside the skill directory."""
    if inside_skill(path):
        work = os.environ.get(WORK_ENV)
        hint = (f"{WORK_ENV} is {work}" + (", which is itself inside the skill" if inside_skill(work) else "")
                if work else f"{WORK_ENV} is not set")
        raise SystemExit(f"refused: the {what} {path} is inside the skill directory {SKILL_DIR}. Commands never write there; "
                         f"write under a work directory outside the skill: export {WORK_ENV}=/path/outside/the/skill and pass "
                         f"\"${WORK_ENV}/...\" ({hint})")
    return Path(path)


def run(main: Callable[[list[str]], int | None]) -> None:
    try:
        code = main(sys.argv[1:])
        sys.stdout.flush()
    except BrokenPipeError:
        # the reader stopped reading (head, a closed pager): not an error of this command
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    sys.exit(code)


def guard_args(args: object, *names: str) -> None:
    """out_path on each named argument that is set."""
    for name in names:
        value = getattr(args, name, None)
        if value:
            out_path(value, f"--{name.replace('_', '-')} path")
