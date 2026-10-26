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


#: Shell variables do not persist between separate shell calls in most agent harnesses: a
#: command written as "$REF" or "$DECK_WORK/..." in a later call then receives "" or
#: "/...". Every refusal of a path that looks like that says so.
UNSET_HINT = ("if this path came from a shell variable ($REF, $DECK_WORK), the variable is not set in this shell: variables set "
              "with export in one call do not reach the next call. Write the path itself, or set the variables in the same call")


def in_path(path: str | Path, what: str = "input", directory: bool = False) -> Path:
    """An input path that exists and is a file (a directory when `directory`), refused by
    name otherwise: never a traceback from deep inside a reader."""
    text = str(path)
    if not text.strip():
        raise SystemExit(f"refused: the {what} is an empty path; {UNSET_HINT}")
    p = Path(text).expanduser()
    if not p.exists():
        raise SystemExit(f"refused: the {what} {text} does not exist; {UNSET_HINT}")
    if directory and not p.is_dir():
        raise SystemExit(f"refused: the {what} {text} is a file, not a directory")
    if not directory and p.is_dir():
        raise SystemExit(f"refused: the {what} {text} is a directory, not a file; {UNSET_HINT}")
    return p


def out_path(path: str | Path, what: str = "output") -> Path:
    """The output path, refused when it lies inside the skill directory, and when it hangs
    off a top-level directory that does not exist ("/ref/guide.json": "$DECK_WORK/ref/..."
    with DECK_WORK unset)."""
    absolute = Path(os.path.abspath(Path(path).expanduser()))
    if not str(path).strip() or (len(absolute.parts) > 2 and not Path(absolute.anchor, absolute.parts[1]).exists()):
        raise SystemExit(f"refused: the {what} {str(path)!r} would be created under {Path(absolute.anchor, *absolute.parts[1:2])}, "
                         f"a top-level directory that does not exist; {UNSET_HINT}")
    if inside_skill(path):
        work = os.environ.get(WORK_ENV)
        hint = (f"{WORK_ENV} is {work}" + (", which is itself inside the skill" if inside_skill(work) else "")
                if work else f"{WORK_ENV} is not set")
        raise SystemExit(f"refused: the {what} {path} is inside the skill directory {SKILL_DIR}. Commands never write there; "
                         f"write under a work directory outside the skill: export {WORK_ENV}=/path/outside/the/skill and pass "
                         f"\"${WORK_ENV}/...\" ({hint})")
    return Path(path)


def run(main: Callable[[list[str]], int | None]) -> None:
    argv = sys.argv[1:]
    empty = [i for i, a in enumerate(argv) if not a.strip()]
    if empty:
        # an empty argument is a path or value that came from an unset variable
        where = ", ".join(f"argument {i + 1}" + (f" (after {argv[i - 1]})" if i else "") for i in empty)
        raise SystemExit(f"refused: {where} is empty; {UNSET_HINT}")
    try:
        code = main(argv)
        sys.stdout.flush()
    except BrokenPipeError:
        # the reader stopped reading (head, a closed pager): not an error of this command
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError) as error:
        # a path a command was given cannot be opened: named, never a traceback
        name = error.filename if error.filename is not None else ""
        raise SystemExit(f"refused: {error.strerror or error}: {name!r}; {UNSET_HINT}") from None
    except Exception as error:
        from textfit import RulerUnavailableError
        if isinstance(error, RulerUnavailableError):
            raise SystemExit(f"refused: {error}") from None  # the guide's pinned ruler, named
        raise
    sys.exit(code)


def guard_args(args: object, *names: str) -> None:
    """out_path on each named argument that is set."""
    for name in names:
        value = getattr(args, name, None)
        if value:
            out_path(value, f"--{name.replace('_', '-')} path")


def page_range(text: str) -> tuple[int, int]:
    """`--pages A-B` (or one page `A`): a 1-based inclusive range, refused by name when it
    is not one. Every command that reads part of a long deck takes it in this one spelling."""
    first, _, last = text.strip().partition("-")
    try:
        lo, hi = int(first), int(last or first)
    except ValueError:
        raise SystemExit(f"--pages {text!r}: write a 1-based inclusive range, e.g. 14-61, or one page, e.g. 19") from None
    if lo < 1 or hi < lo:
        raise SystemExit(f"--pages {text!r}: the range must start at 1 or later and end at or after its start")
    return lo, hi
