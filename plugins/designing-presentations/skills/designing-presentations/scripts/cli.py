"""What every command shares: where it may write, and how it exits.

A command writes only outside this skill. Company files, guides, digests, renders and
builds belong to the user's work directory (SKILL.md: `DECK_WORK`), never to the skill,
so every output path a command takes passes `out_path`, which refuses one inside the
skill by name. `component.py admit` writes its record to the user's components directory
(`--components`), never beside a shipped component. One maintenance command writes skill
content and is the only exception: `library.py import` builds the
git-ignored external library of public decks in `refs/library` (Library.guard_location
refuses any other owner there). The user fills the git-ignored `refs/files`.

`run` calls a command's main and turns a closed stdout (`... | head`) into a quiet exit
instead of a BrokenPipeError traceback.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path


class Refused(ValueError):
    """A named refusal raised below a command's main (an unreadable or over-cap reference,
    say): `run` prints it as "refused: ..." and exits non-zero, never a traceback."""


SKILL_DIR = Path(__file__).resolve().parent.parent
WORK_ENV = "DECK_WORK"


def _skill_roots() -> set[Path]:
    """The skill directory, and the folders its own symlinks point at (refs/files may be a
    symlink to a folder elsewhere): writing there is writing into the skill, by whichever
    path. Symlinks are looked for two levels down, where the skill keeps them."""
    roots = {SKILL_DIR, Path(os.path.abspath(Path(__file__).parent.parent))}
    for top in (SKILL_DIR, *(p for p in SKILL_DIR.iterdir() if p.is_dir() and not p.is_symlink())):
        try:
            entries = list(top.iterdir())
        except OSError:
            continue
        roots.update(e.resolve() for e in entries if e.is_symlink())
    return roots


def inside_skill(path: str | Path) -> bool:
    """Inside the skill as written or as resolved, or inside a folder one of the skill's own
    symlinks points at (refs/files): a path into that folder is a path into the skill
    whether it is written through the symlink or to the folder itself."""
    skill = _skill_roots()
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


#: flags that were removed or renamed: refused by name, with the new spelling, by every command
RENAMED_FLAGS = {
    "--house-deck": ("--house-deck was removed: the skill takes one reference deck (the guide made from it, and --reference). When the "
                     "user gives several, use the one they name, or ask which to follow; nothing is pooled"),
    "--houses-file": "--houses-file is now --firms-file",
}


def run(main: Callable[[list[str]], int | None]) -> None:
    argv = sys.argv[1:]
    renamed = [RENAMED_FLAGS[a.split("=", 1)[0]] for a in argv if a.split("=", 1)[0] in RENAMED_FLAGS]
    if renamed:
        raise SystemExit("refused: " + "; ".join(dict.fromkeys(renamed)))
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
        from textfit import RulerUnavailableError, WorkFontsError
        if isinstance(error, Refused):
            raise SystemExit(f"refused: {error}") from None
        if isinstance(error, (RulerUnavailableError, WorkFontsError)):
            raise SystemExit(f"refused: {error}") from None  # the guide's pinned ruler, or DECK_FONTS, named
        raise
    sys.exit(code)


def guard_args(args: object, *names: str) -> None:
    """out_path on each named argument that is set."""
    for name in names:
        value = getattr(args, name, None)
        if value:
            out_path(value, f"--{name.replace('_', '-')} path")


def parse_args(ap, argv: list[str], repeated: str):
    """ap.parse_args, except that a word left over is named with the form of `repeated`,
    a flag that takes one file and is given once per file: a flag that took several would
    also take the positional argument written after it."""
    args, extra = ap.parse_known_args(argv)
    if extra:
        ap.error(f"unrecognized arguments: {' '.join(extra)} ({repeated} takes one file: give each file its own flag, "
                 f"{repeated} a.txt {repeated} b.txt)")
    return args


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
