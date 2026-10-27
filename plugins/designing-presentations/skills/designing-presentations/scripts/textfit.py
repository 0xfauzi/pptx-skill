"""Measured text fit for layout.py: face resolution, two rulers, one wrap rule.

Nothing here estimates a width: every candidate line is measured as
ONE string by a ruler, and the two rulers are the two instruments scored
against PowerPoint's own PDF export (600 boxes):
HarfBuzz (uharfbuzz, optional; 541/600 exact breaks, 588/600 same line count) and
Pillow at x128 scale, BASIC layout, getlength (539/600, 585/600), the fallback a
stock sandbox always has. Each carries the width shrink that made it one-sided
against PowerPoint (zero optimistic boxes): 20,234 EMU HarfBuzz, 5,933 EMU Pillow.
Line pitch is never read from font tables (wrong by up to 20 percent, measured).

Faces: exact family from the file's own name table, then fontconfig's metric-alias
classes (Arial -> Liberation Sans, Calibri -> Carlito, Cambria -> Caladea, Times New
Roman -> Liberation Serif, Courier New -> Liberation Mono). An unknown family is
REFUSED unless the guide names a stand-in, and the stand-in must be the face fc-match
returns, the one LibreOffice draws (resolve_measured); bold is never synthesised
(measured cost of a wrong face: 52/120 break agreement, lines off by three).

Font files: the installed folders (fontconfig's defaults and the standard macOS and Windows
folders, STANDARD_FONT_ROOTS) and the work folder's fonts directory named by DECK_FONTS
(work_fonts). Work-folder files are checked by fontfiles.py first and copied to a folder of
this process; fontconfig reads that copy through a FONTCONFIG_FILE of this process only
(font_env), so fc-match, LibreOffice and the rulers see the same faces and nothing is
installed. A file whose fsType is restricted is never used. Nothing here downloads a font.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fontfiles  # noqa: E402

try:
    import uharfbuzz as hb
except ImportError:  # the stock sandbox ships Pillow; uharfbuzz is optional
    hb = None

EMU_PER_POINT = 12_700

#: Width shrink before wrapping, per ruler, so no box is optimistic against
#: PowerPoint. HarfBuzz: (13 + 20,221). Pillow x128:
#: ("shrink 5,933 EMU -> 0 optimistic boxes").
FIT_EPSILON_HARFBUZZ_EMU = 20_234
FIT_EPSILON_PILLOW_EMU = 5_933

#: Converged Pillow scale: at x1 only 306/600 boxes agree, at x128 539/600.
PILLOW_SCALE = 128

#: A 7.5 in page at 1 pt holds about 450 lines.
MAX_WRAPPED_LINES = 2_000

DEFAULT_FONT_ROOTS = ("/usr/share/fonts", "/usr/local/share/fonts")
#: Installed fonts outside fontconfig's system folders: the user's own folders on Linux
#: (fontconfig reads both), and the system and user folders of macOS and Windows. A folder
#: that does not exist on this machine is skipped.
STANDARD_FONT_ROOTS = (
    *DEFAULT_FONT_ROOTS,
    str(Path.home() / ".local/share/fonts"), str(Path.home() / ".fonts"),
    "/System/Library/Fonts", "/Library/Fonts", str(Path.home() / "Library/Fonts"),
    os.environ.get("WINDIR", "C:/Windows").replace("\\", "/") + "/Fonts",
    *((os.environ["LOCALAPPDATA"].replace("\\", "/") + "/Microsoft/Windows/Fonts",) if os.environ.get("LOCALAPPDATA") else ()),
)
FONT_SUFFIXES = fontfiles.FONT_SUFFIXES
#: The environment variable that names the work folder's fonts directory (SKILL.md).
WORK_FONTS_ENV = "DECK_FONTS"
#: fontconfig's own configuration, included by the per-process one: the variable the user
#: set, else the Linux path, else the Homebrew paths on macOS.
SYSTEM_FONTCONFIG = ("/etc/fonts/fonts.conf", "/opt/homebrew/etc/fonts/fonts.conf", "/usr/local/etc/fonts/fonts.conf")

#: fontconfig's own `binding="same"` metric aliases, normalized with normalize_family:
#: the 17 classes (84 family-to-family edges) read from the 72 binding="same"
#: alias elements of /etc/fonts/conf.d/30-metric-aliases.conf. The file's weak generic aliases (Arial to
#: Helvetica) are not binding="same", so arial and helvetica are separate classes.
#: The one table: render.py's fidelity verdict imports it.
METRIC_ALIAS_CLASSES: tuple[frozenset[str], ...] = (
    frozenset({"albany", "albanyamt", "arial", "arimo", "liberationsans"}),
    frozenset({"arialnarrow", "liberationsansnarrow"}),
    frozenset({"avantgarde", "itcavantgardegothic", "texgyreadventor", "urwgothic", "urwgothicl"}),
    frozenset({"bookman", "bookmanoldstyle", "bookmanurw", "itcbookman", "texgyrebonum", "urwbookman", "urwbookmanl"}),
    frozenset({"c059", "centuryschoolbook", "centuryschoolbookl", "centuryschoolbookurw", "newcenturyschoolbook", "texgyreschola"}),
    frozenset({"caladea", "cambria"}),
    frozenset({"calibri", "carlito"}),
    frozenset({"chanceryurw", "itczapfchancery", "texgyrechorus", "urwchanceryl", "z003", "zapfchancery"}),
    frozenset({"courier", "courierstd", "nimbusmono", "nimbusmonol", "nimbusmonops", "texgyrecursor"}),
    frozenset({"couriernew", "cousine", "cumberland", "cumberlandamt", "liberationmono"}),
    frozenset({"gelasio", "georgia"}),
    frozenset({"helvetica", "nimbussans", "nimbussansl", "texgyreheros"}),
    frozenset({"helveticanarrow", "nimbussansnarrow", "texgyreheroscn"}),
    frozenset({"liberationserif", "thorndale", "thorndaleamt", "timesnewroman", "tinos"}),
    frozenset({"nimbusroman", "nimbusromanno9l", "texgyretermes", "times"}),
    frozenset({"p052", "palatino", "palatinolinotype", "palladiourw", "texgyrepagella", "urwpalladiol"}),
    frozenset({"symbol", "symbolneu"}),
)

#: What a font's own name table may call each style.
_STYLE_SPELLINGS: dict[tuple[bool, bool], tuple[str, ...]] = {
    (False, False): ("Regular", "Book", "Roman", "Normal", "Medium"),
    (True, False): ("Bold", "Heavy", "Black"),
    (False, True): ("Italic", "Oblique"),
    (True, True): ("Bold Italic", "Bold Oblique", "BoldItalic"),
}

_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")

class UnknownFamilyError(LookupError):
    """No indexed face and no metric-vouched clone for the requested family."""

class UnknownStyleError(LookupError):
    """The family is indexed but not in the requested weight or slope."""

class UnmeasurableTextError(ValueError):
    """The text carries nothing a line could be made of."""

class WrappedTooManyLinesError(ValueError):
    """The text wraps into more lines than any slide element could hold."""

def normalize_family(name: str) -> str:
    base = _SUBSET_PREFIX.sub("", name).split("-")[0]
    return "".join(ch for ch in base.lower() if ch.isalnum())

def metric_alias(declared: str, rendered: str) -> bool:
    """fontconfig's binding="same" table puts the two families in one class."""
    a, b = normalize_family(declared), normalize_family(rendered)
    return a != b and any(a in cls and b in cls for cls in METRIC_ALIAS_CLASSES)

@dataclass(frozen=True)
class Face:
    requested: str
    family: str
    style: str
    path: str
    provenance: str  # "exact" | "metric_alias"

class FaceIndex:
    """Every measurable face under the roots, keyed by the file's own names."""

    def __init__(self, faces: dict[tuple[str, str], Face]) -> None:
        self.by_family_style = faces

    def resolve(self, family: str, *, bold: bool = False, italic: bool = False) -> Face:
        spellings = _STYLE_SPELLINGS[(bold, italic)]
        wanted = normalize_family(family)
        for style in spellings:
            exact = self.by_family_style.get((wanted, style))
            if exact is not None:
                return Face(family, exact.family, exact.style, exact.path, "exact")
        members: frozenset[str] = frozenset()
        for cls in METRIC_ALIAS_CLASSES:
            if wanted in cls:
                members = cls - {wanted}
        for member in sorted(members):
            for style in spellings:
                found = self.by_family_style.get((member, style))
                if found is not None:
                    return Face(family, found.family, found.style, found.path, "metric_alias")
        present = {key[0] for key in self.by_family_style}
        if wanted in present or members & present:
            raise UnknownStyleError(
                f"family {family!r} is indexed but carries no {spellings[0]} face; "
                "measuring the regular face instead would under-measure"
            )
        raise UnknownFamilyError(
            f"no face for family {family!r} and no metric-compatible clone of it; "
            "measuring another typeface under this name is unbounded error"
        )

class WorkFontsError(LookupError):
    """DECK_FONTS names something that is not a usable fonts folder; the message says what."""


@dataclass(frozen=True)
class WorkFonts:
    folder: Path                         # the user's folder, as DECK_FONTS names it
    copies: dict[str, str]               # this process's copy -> the user's file
    faces: tuple[fontfiles.FaceInfo, ...]  # every face accepted, with the user's path
    rejected: tuple[tuple[str, str], ...]  # (the user's file, why it is not used)
    config: str | None                   # the FONTCONFIG_FILE of this process, None with no file accepted


#: the record fonts.py extract keeps in the fonts folder; not a font, never read as one
LICENCE_RECORD = "licence-confirmations.json"


def _system_fontconfig() -> str:
    for candidate in (os.environ.get("FONTCONFIG_FILE"), *SYSTEM_FONTCONFIG):
        if candidate and Path(candidate).is_file():
            return candidate
    raise WorkFontsError(f"no fontconfig configuration found (FONTCONFIG_FILE, {', '.join(SYSTEM_FONTCONFIG)}): "
                         "the renderer cannot be shown the work folder's fonts")


@lru_cache(maxsize=1)
def work_fonts() -> WorkFonts | None:
    """The fonts the user supplied (or fonts.py extract wrote) in the folder DECK_FONTS
    names, each read by fontfiles.py first; None when DECK_FONTS is unset. Accepted files
    are copied to a folder of this process (removed at exit), and a fonts.conf there adds
    that folder to fontconfig's own configuration, with its cache in the same folder: the
    user's folder is never scanned by fontconfig, and nothing outside this process
    changes."""
    value = os.environ.get(WORK_FONTS_ENV)
    if not value:
        return None
    folder = Path(value).expanduser()
    if not folder.is_absolute():
        raise WorkFontsError(f"{WORK_FONTS_ENV}={value!r} is not an absolute path: export {WORK_FONTS_ENV}=\"$DECK_WORK/fonts\"")
    if not folder.is_dir():
        raise WorkFontsError(f"{WORK_FONTS_ENV}={value} is not a folder: create it (mkdir -p \"{value}\") or unset {WORK_FONTS_ENV}")
    accepted: list[tuple[Path, list[fontfiles.FaceInfo]]] = []
    rejected: list[tuple[str, str]] = []
    for path in sorted(folder.rglob("*")):
        if path.name == LICENCE_RECORD or path.name.startswith(".") or (path.is_dir() and not path.is_symlink()):
            continue
        if path.suffix.lower() not in FONT_SUFFIXES:
            rejected.append((str(path), "not a .ttf, .otf or .ttc file"))
            continue
        try:
            faces = fontfiles.read_faces(path)
        except fontfiles.FontFileError as error:
            rejected.append((str(path), str(error)))
            continue
        locked = [f.family for f in faces if not f.permits("measure")]
        if locked:
            rejected.append((str(path), f"fsType {faces[0].fs_type} ({faces[0].embedding}): the font's licence bits forbid its use here"))
            continue
        accepted.append((path, faces))
    if not accepted:
        return WorkFonts(folder, {}, (), tuple(rejected), None)
    runtime = Path(tempfile.mkdtemp(prefix="deck-fonts-"))
    atexit.register(shutil.rmtree, runtime, True)
    (runtime / "fonts").mkdir()
    copies: dict[str, str] = {}
    for n, (path, _) in enumerate(accepted):
        copy = runtime / "fonts" / f"{n:03d}{path.suffix.lower()}"
        shutil.copyfile(path, copy)
        copies[str(copy)] = str(path)
    from xml.sax.saxutils import escape
    config = runtime / "fonts.conf"
    config.write_text('<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n<fontconfig>\n'
                      f'  <cachedir>{escape(str(runtime / "cache"))}</cachedir>\n'
                      f'  <include ignore_missing="no">{escape(_system_fontconfig())}</include>\n'
                      f'  <dir>{escape(str(runtime / "fonts"))}</dir>\n</fontconfig>\n', encoding="utf-8")
    faces = tuple(face for _, found in accepted for face in found)
    return WorkFonts(folder, copies, faces, tuple(rejected), str(config))


def font_env() -> dict[str, str]:
    """What a fontconfig or LibreOffice subprocess needs in its environment to see the work
    folder's fonts: FONTCONFIG_FILE of this process, or nothing."""
    work = work_fonts()
    return {"FONTCONFIG_FILE": work.config} if work and work.config else {}


def _usable(path: Path) -> bool:
    """An installed file whose every face fontfiles reads as restricted is never measured;
    a file fontfiles cannot read is left to Pillow, as before (a system file is not
    untrusted input, and an unread table is no evidence of a restriction)."""
    try:
        return any(f.permits("measure") for f in fontfiles.read_faces(path))
    except fontfiles.FontFileError:
        return True


def build_index(roots: tuple[str, ...] | None = None) -> FaceIndex:
    """Every measurable face: the work folder's (first, so a face the user supplied is the
    one measured) and the installed folders' (STANDARD_FONT_ROOTS, or LAYOUT_FONT_ROOTS)."""
    if roots is None:
        override = os.environ.get("LAYOUT_FONT_ROOTS")
        roots = tuple(p for p in override.split(os.pathsep) if p) if override else STANDARD_FONT_ROOTS
    work = work_fonts()
    files: list[Path] = [Path(copy) for copy in (work.copies if work else {})]
    for root in roots:
        base = Path(root)
        if base.is_dir():
            files += [p for p in sorted(base.rglob("*")) if p.suffix.lower() in FONT_SUFFIXES and p.is_file() and _usable(p)]
    faces: dict[tuple[str, str], Face] = {}
    for path in files:
        try:
            family, style = ImageFont.truetype(str(path), 16).getname()
        except (OSError, ValueError):
            continue
        if not family:
            continue
        key = (normalize_family(family), style or "Regular")
        faces.setdefault(key, Face(family, family, style or "Regular", str(path), "exact"))
    return FaceIndex(faces)

@lru_cache(maxsize=1)
def default_index() -> FaceIndex:
    return build_index()

# --- the renderer's substitute: the one place a stand-in face is chosen ----------------

class SubstituteMismatchError(LookupError):
    """The guide names a stand-in the renderer does not draw: the solver would measure
    one face while the render shows another, so neither is evidence of fit."""

@lru_cache(maxsize=256)
def fc_match(family: str, bold: bool = False, italic: bool = False) -> tuple[str, str, int]:
    """(family, file, face index) fontconfig picks for `family`: what LibreOffice draws a
    face the sandbox lacks with. render.py reports it; resolve_measured measures with it."""
    pattern = family + (":bold" if bold else "") + (":italic" if italic else "")
    try:
        out = subprocess.run(["fc-match", "-f", "%{family}\t%{file}\t%{index}", pattern], capture_output=True, text=True, timeout=20,
                             env={**os.environ, **font_env()}).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    name, _, rest = out.partition("\t")
    path, _, index = rest.partition("\t")
    return name.split(",")[0].strip(), path, int(index) if index.isdigit() else 0

def resolve_measured(index: FaceIndex, family: str, *, bold: bool = False, italic: bool = False,
                     substitute: str | None = None, renderer_ok: bool = False) -> Face:
    """The face a run in `family` is measured with: the family itself or a metric alias
    (FaceIndex.resolve); else the face fontconfig draws it with, which a guide must name
    under typography.families.substitutes (`substitute`) and which must be fc-match's
    answer, so measurement and render are one face. `renderer_ok` takes fc-match's face
    unnamed: the judge reads decks no guide describes."""
    try:
        return index.resolve(family, bold=bold, italic=italic)
    except UnknownFamilyError:
        drawn = fc_match(family)[0]
        if substitute is None and not renderer_ok:
            raise UnknownFamilyError(f"no face for family {family!r} here and no metric-compatible clone; the renderer draws it as {drawn!r} (fc-match): "
                                     f"name {drawn!r} under typography.families.substitutes to measure what the render shows, or have the user "
                                     f"put a licensed file of {family!r} in the fonts folder ({WORK_FONTS_ENV}"
                                     + (f"={os.environ[WORK_FONTS_ENV]}" if os.environ.get(WORK_FONTS_ENV) else " is not set in this shell")
                                     + "; scripts/fonts.py report)") from None
        if substitute is not None and normalize_family(substitute) != normalize_family(drawn):
            raise SubstituteMismatchError(f"the guide substitutes {substitute!r} for {family!r}, but the renderer draws {family!r} as {drawn!r} (fc-match); "
                                          f"measuring {substitute!r} would fit text the render does not show: name {drawn!r}") from None
        found = index.resolve(drawn, bold=bold, italic=italic)
        return Face(family, found.family, found.style, found.path, "renderer_substitute")

# --- the decided wrap rule ------------------

class Advance(Protocol):
    """Whole-run advance of one string, in the ruler's own units."""

    def __call__(self, text: str) -> float: ...

@dataclass(frozen=True)
class WrappedLine:
    text: str
    start: int
    advance_units: float

_UNIT_TOKENS = frozenset({"bn", "mm", "m", "k", "b", "x", "%", "bps", "pp", "pts", "p.a.", "yrs", "mn", "bp", "ppt", "pct"})
_CURRENCY_TOKENS = frozenset({"$", "us$", "c$", "a$", "eur", "gbp", "usd", "cad", "chf", "jpy", "sek", "nok", "dkk", "aud"})
_PERIOD_PREFIXES = frozenset({"fy", "cy", "q1", "q2", "q3", "q4", "h1", "h2", "ltm", "ntm", "fye", "ye"})


def _numeric(token: str) -> bool:
    core = token.strip("()[]$%,.:;x-\u2013+")
    return any(ch.isdigit() for ch in core) and all(ch.isdigit() or ch in ".,%$()-x+/" for ch in core)


def _glued(before: str, after: str) -> bool:
    """A figure and its unit, a currency mark and its figure, a period prefix and its
    year stay on one line: '$1.2 bn', 'EUR 40 mm', 'FY 2024', '12.5 %'. A pitch-book page
    that breaks inside one of these reads as generated, and PowerPoint would break there."""
    b, a = before.lower(), after.lower()
    if _numeric(b) and (a in _UNIT_TOKENS or a.rstrip(".,;:)") in _UNIT_TOKENS):
        return True
    if b in _CURRENCY_TOKENS and _numeric(a):
        return True
    if b in _PERIOD_PREFIXES and _numeric(a):
        return True
    return False


def break_opportunities(text: str) -> tuple[int, ...]:
    """Offsets one past each character a line may end on: every space or hyphen
    (the hyphen stays on the line it ends), plus the end of the string. A space
    between a figure and its unit (see _glued) and a non-breaking space are not
    opportunities."""
    stops: list[int] = []
    for i, ch in enumerate(text):
        if ch == "-":
            stops.append(i + 1)
        elif ch == " ":
            before = text[:i].split(" ")[-1]
            after = text[i + 1:].split(" ")[0]
            if before and after and _glued(before, after):
                continue
            stops.append(i + 1)
    if not stops or stops[-1] != len(text):
        stops.append(len(text))
    return tuple(stops)

def wrap_text(text: str, budget_units: float, advance: Advance) -> tuple[WrappedLine, ...]:
    """Greedy wrap: break after space or hyphen, trailing
    spaces free, a token wider than the line breaks between characters, every
    candidate line measured as one string."""
    return wrap_spans(text, budget_units, lambda a, b: advance(text[a:b]))


def wrap_spans(text: str, budget_units: float, span: Callable[[int, int], float]) -> tuple[WrappedLine, ...]:
    """wrap_text with the advance of text[a:b] given by offsets, so a line whose runs are
    set in different faces is measured run by run (measure_runs); every candidate line is
    one call, from the line's start."""
    if not text.strip(" "):
        raise UnmeasurableTextError("whitespace alone wraps to no line")
    stops = break_opportunities(text)
    lines: list[WrappedLine] = []
    position = 0
    guard, limit = 0, 4 * len(text) + 8
    while position < len(text):
        if len(lines) >= MAX_WRAPPED_LINES:
            raise WrappedTooManyLinesError(f"wraps past {MAX_WRAPPED_LINES} lines")
        guard += 1
        if guard > limit:
            raise RuntimeError("wrap failed to advance")
        chosen: int | None = None
        chosen_advance = 0.0
        # Advance is monotone in prefix length: exponential probe then binary
        # search bound the longest prefix that could fit, so no stop past it
        # is ever shaped (9.55 s per call without this).
        end_of_text = stops[-1]
        width = 16
        upper = min(position + width, end_of_text)
        while upper < end_of_text and span(position, upper) <= budget_units:
            width *= 2
            upper = min(position + width, end_of_text)
        low, high = position, upper
        while low < high:
            mid = (low + high + 1) // 2
            if span(position, mid) <= budget_units:
                low = mid
            else:
                high = mid - 1
        reachable = [stop for stop in stops if position < stop <= low]
        beyond = next((stop for stop in stops if stop > low), None)
        if beyond is not None:
            tail = beyond
            while tail > position and text[tail - 1] == " ":
                tail -= 1
            if tail <= low:
                reachable.append(beyond)
        for stop in reachable:
            candidate = text[position:stop].rstrip(" ")
            if not candidate:
                continue
            measured = span(position, position + len(candidate))
            if measured <= budget_units:
                chosen, chosen_advance = stop, measured
            else:
                break
        if chosen is None:
            first = next(s for s in stops if s > position and text[position:s].strip(" "))
            lower = position
            while lower < len(text) and text[lower] == " ":
                lower += 1
            lower += 1
            chosen, chosen_advance = lower, span(position, lower)
            low, high = lower, first
            while low < high:
                mid = (low + high + 1) // 2
                measured = span(position, mid)
                if measured <= budget_units:
                    low = mid
                    chosen, chosen_advance = mid, measured
                else:
                    high = mid - 1
        lines.append(WrappedLine(text[position:chosen].rstrip(" "), position, chosen_advance))
        position = chosen
        while position < len(text) and text[position] == " ":
            position += 1
    return tuple(lines)

# --- the two rulers ----------------------------------------------------------------

@dataclass(frozen=True)
class MeasuredLine:
    text: str
    start: int
    width_emu: int

class Ruler(Protocol):
    name: str
    fit_epsilon_emu: int

    def advance(self, path: str, size_pt: float) -> Advance: ...
    def budget_units(self, path: str, size_pt: float, width_emu: int) -> float: ...
    def to_emu(self, path: str, size_pt: float, units: float) -> int: ...

class HarfBuzzRuler:
    """Whole-run advance in font design units; one rounding at the EMU conversion."""

    name = "harfbuzz"
    fit_epsilon_emu = FIT_EPSILON_HARFBUZZ_EMU
    MAX_CACHED_STRINGS = 4_096

    def __init__(self) -> None:
        if hb is None:
            raise ImportError("uharfbuzz is not importable")
        self._fonts: dict[str, tuple[object, int]] = {}
        self._cache: dict[tuple[str, str], int] = {}

    def _font(self, path: str) -> tuple[object, int]:
        entry = self._fonts.get(path)
        if entry is None:
            face = hb.Face(hb.Blob.from_file_path(path))
            font = hb.Font(face)
            font.scale = (face.upem, face.upem)
            entry = self._fonts[path] = (font, face.upem)
        return entry

    def units(self, path: str, text: str) -> int:
        key = (path, text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        font, _ = self._font(path)
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(font, buffer)
        value = int(sum(p.x_advance for p in buffer.glyph_positions))
        if len(self._cache) >= self.MAX_CACHED_STRINGS:
            self._cache.clear()
        self._cache[key] = value
        return value

    def advance(self, path: str, size_pt: float) -> Advance:
        return lambda text: float(self.units(path, text))

    def budget_units(self, path: str, size_pt: float, width_emu: int) -> float:
        return width_emu * self._font(path)[1] / (size_pt * EMU_PER_POINT)

    def to_emu(self, path: str, size_pt: float, units: float) -> int:
        return round(units / self._font(path)[1] * size_pt * EMU_PER_POINT)

class PillowRuler:
    """Decided Pillow configuration: x128 scale, BASIC layout, getlength.

    BASIC is pinned explicitly because a RAQM-enabled Pillow would otherwise
    shape through a different engine than the one scored. Pillow's BASIC
    engine applies legacy kern pairs at 1/64 magnitude and ignores GPOS; its 5,933 EMU shrink is what
    makes it one-sided despite that.
    """

    name = "pillow_x128"
    fit_epsilon_emu = FIT_EPSILON_PILLOW_EMU

    def __init__(self) -> None:
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def _font(self, path: str, size_pt: float) -> ImageFont.FreeTypeFont:
        key = (path, round(size_pt * PILLOW_SCALE))
        font = self._fonts.get(key)
        if font is None:
            font = self._fonts[key] = ImageFont.truetype(
                path, key[1], layout_engine=ImageFont.Layout.BASIC
            )
        return font

    def advance(self, path: str, size_pt: float) -> Advance:
        font = self._font(path, size_pt)
        return lambda text: float(font.getlength(text))

    def budget_units(self, path: str, size_pt: float, width_emu: int) -> float:
        return width_emu / EMU_PER_POINT * PILLOW_SCALE

    def to_emu(self, path: str, size_pt: float, units: float) -> int:
        return round(units / PILLOW_SCALE * EMU_PER_POINT)

def default_ruler() -> Ruler:
    return HarfBuzzRuler() if hb is not None else PillowRuler()


class RulerUnavailableError(LookupError):
    """The guide pins a ruler this Python cannot run."""


def ruler_named(name: str) -> Ruler:
    if name == HarfBuzzRuler.name:
        if hb is None:
            raise RulerUnavailableError("the guide pins the harfbuzz ruler and uharfbuzz is not importable here. Do not install it "
                                        "yourself: a package installed machine-wide moves every other session's fit budgets. Tell the "
                                        "user it is missing and that the command is python3 -m pip install uharfbuzz, for them to run "
                                        "or to tell you to; or build on the machine the guide was extracted on (references/intake.md, "
                                        "What you may install)")
        return HarfBuzzRuler()
    if name == PillowRuler.name:
        return PillowRuler()
    raise RulerUnavailableError(f"the guide pins ruler {name!r}; the rulers are {HarfBuzzRuler.name!r} and {PillowRuler.name!r}")


def ruler_pin() -> dict:
    """What a draft records of its measurement: the ruler this machine runs now. Every
    later command on that guide measures with it (ruler_for), so a package installed
    mid-session never changes the instrument under a deck."""
    return {"ruler": default_ruler().name,
            "basis": "pinned when the draft was extracted; every capacity, survey and build on this guide measures with this ruler"}


def ruler_for(guide: dict | None) -> Ruler:
    """The guide's pinned ruler (ruler_pin), or this machine's default for a guide that
    pins none (one extracted before the pin, or a reference read without a guide)."""
    name = ((guide or {}).get("measurement") or {}).get("ruler")
    return ruler_named(name) if name else default_ruler()

def measure_text(
    ruler: Ruler, text: str, width_emu: int, path: str, size_pt: float
) -> tuple[MeasuredLine, ...]:
    """`text` wrapped into `width_emu` (insets and epsilon already removed by
    the caller) in the face at `path`, every line measured whole."""
    if not text.strip(" "):
        raise UnmeasurableTextError("whitespace alone wraps to no line")
    if width_emu <= 0:
        raise ValueError(f"width_emu must be positive, got {width_emu}")
    advance = ruler.advance(path, size_pt)
    if advance(text) <= 0:
        raise UnmeasurableTextError("the text shapes to zero advance")
    budget = ruler.budget_units(path, size_pt, width_emu)
    return tuple(
        MeasuredLine(line.text, line.start, ruler.to_emu(path, size_pt, line.advance_units))
        for line in wrap_text(text, budget, advance)
    )

def measure_runs(ruler: Ruler, text: str, spans: Sequence[tuple[int, int, str, float]], width_emu: int) -> tuple[MeasuredLine, ...]:
    """`text` whose characters [a, b) are set in the face at `path` and `size_pt`, for each
    (a, b, path, size_pt) of `spans` (covering the text in order), wrapped into
    `width_emu`. A line's advance is the sum, over the runs it crosses, of each run's part
    shaped WHOLE in its own face: a run is what a renderer shapes as one string, so kerning
    never crosses a change of face, and no run is ever cut into fragments that are summed.
    One face throughout is measure_text, unchanged."""
    if not text.strip(" "):
        raise UnmeasurableTextError("whitespace alone wraps to no line")
    if width_emu <= 0:
        raise ValueError(f"width_emu must be positive, got {width_emu}")
    covered = 0
    for a, b, _, _ in spans:
        if a != covered or b < a:
            raise ValueError("spans must cover the text in order, end to end")
        covered = b
    if covered != len(text):
        raise ValueError("spans must cover the text in order, end to end")
    faces = {(path, size) for _, _, path, size in spans}
    if len(faces) == 1:
        path, size = faces.pop()
        return measure_text(ruler, text, width_emu, path, size)

    def span(a: int, b: int) -> float:
        total = 0
        for s0, s1, path, size in spans:
            lo, hi = max(a, s0), min(b, s1)
            if lo < hi:
                total += advance_emu(ruler, text[lo:hi], path, size)
        return float(total)

    return tuple(MeasuredLine(line.text, line.start, round(line.advance_units)) for line in wrap_spans(text, float(width_emu), span))


def advance_emu(ruler: Ruler, text: str, path: str, size_pt: float) -> int:
    """The whole-run advance of ONE string in EMU. One string by signature: a
    list would invite the caller to sum fragments, which kerning forbids."""
    return ruler.to_emu(path, size_pt, ruler.advance(path, size_pt)(text))
