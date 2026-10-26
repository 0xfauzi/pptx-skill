"""Measured text fit for layout.py: face resolution, two rulers, one wrap rule.

A ported text ruler (PORT_AUDIT.md). Nothing here estimates a width: every candidate line is measured as
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
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from PIL import ImageFont

try:
    import uharfbuzz as hb
except ImportError:  # the stock sandbox ships Pillow; uharfbuzz is optional
    hb = None

EMU_PER_POINT = 12_700

#: Width shrink before wrapping, per ruler, so no box is optimistic against
#: PowerPoint. HarfBuzz: deckgen measure/tolerance.py:133 (13 + 20,221;
#: docs/measurements/1D-2-tolerance.md). Pillow x128: docs/measurements/
#: E16-decision.md ("shrink 5,933 EMU -> 0 optimistic boxes").
FIT_EPSILON_HARFBUZZ_EMU = 20_234
FIT_EPSILON_PILLOW_EMU = 5_933

#: E16's converged Pillow scale: at x1 only 306/600 boxes agree, at x128 539/600
#: (deckgen measure/decided.py:38, docs/measurements/E16-decision.md).
PILLOW_SCALE = 128

#: deckgen measure/text.py:51 - a 7.5 in page at 1 pt holds about 450 lines.
MAX_WRAPPED_LINES = 2_000

DEFAULT_FONT_ROOTS = ("/usr/share/fonts", "/usr/local/share/fonts")
FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc"})

#: fontconfig's own `binding="same"` metric aliases, normalized with normalize_family:
#: the 17 classes (84 family-to-family edges) deckgen read from the 72 binding="same"
#: alias elements of /etc/fonts/conf.d/30-metric-aliases.conf (deckgen render/tuning.py:170,
#: docs/measurements/S1B3-decision.md part 1). The file's weak generic aliases (Arial to
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

#: What a font's own name table may call each style (deckgen measure/faces.py:93).
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

def build_index(roots: tuple[str, ...] | None = None) -> FaceIndex:
    if roots is None:
        override = os.environ.get("LAYOUT_FONT_ROOTS")
        roots = tuple(p for p in override.split(os.pathsep) if p) if override else DEFAULT_FONT_ROOTS
    faces: dict[tuple[str, str], Face] = {}
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in FONT_SUFFIXES or not path.is_file():
                continue
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
        out = subprocess.run(["fc-match", "-f", "%{family}\t%{file}\t%{index}", pattern], capture_output=True, text=True, timeout=20).stdout
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
                                     f"name {drawn!r} under typography.families.substitutes to measure what the render shows") from None
        if substitute is not None and normalize_family(substitute) != normalize_family(drawn):
            raise SubstituteMismatchError(f"the guide substitutes {substitute!r} for {family!r}, but the renderer draws {family!r} as {drawn!r} (fc-match); "
                                          f"measuring {substitute!r} would fit text the render does not show: name {drawn!r}") from None
        found = index.resolve(drawn, bold=bold, italic=italic)
        return Face(family, found.family, found.style, found.path, "renderer_substitute")

# --- the decided wrap rule (docs/measurements/E16-decision.md) ------------------

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
    """Greedy wrap under E16's rules: break after space or hyphen, trailing
    spaces free, a token wider than the line breaks between characters, every
    candidate line measured as one string. Port of deckgen measure/text.py:203."""
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
        # is ever shaped (deckgen measured 9.55 s per call without this).
        end_of_text = stops[-1]
        span = 16
        upper = min(position + span, end_of_text)
        while upper < end_of_text and advance(text[position:upper]) <= budget_units:
            span *= 2
            upper = min(position + span, end_of_text)
        low, high = position, upper
        while low < high:
            mid = (low + high + 1) // 2
            if advance(text[position:mid]) <= budget_units:
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
            measured = advance(candidate)
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
            chosen, chosen_advance = lower, advance(text[position:lower])
            low, high = lower, first
            while low < high:
                mid = (low + high + 1) // 2
                measured = advance(text[position:mid])
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
    MAX_CACHED_STRINGS = 4_096  # deckgen measure/text.py:136

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
    """E16's decided Pillow configuration: x128 scale, BASIC layout, getlength.

    BASIC is pinned explicitly because a RAQM-enabled Pillow would otherwise
    shape through a different engine than the one E16 scored. Pillow's BASIC
    engine applies legacy kern pairs at 1/64 magnitude and ignores GPOS
    (docs/measurements/1D-2-who-is-wrong.md); its 5,933 EMU shrink is what
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
    mid-session (a second agent's pip install of uharfbuzz moved every fit budget of a
    session that had planned on Pillow) never changes the instrument under a deck."""
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

def advance_emu(ruler: Ruler, text: str, path: str, size_pt: float) -> int:
    """The whole-run advance of ONE string in EMU. One string by signature: a
    list would invite the caller to sum fragments, which kerning forbids."""
    return ruler.to_emu(path, size_pt, ruler.advance(path, size_pt)(text))
