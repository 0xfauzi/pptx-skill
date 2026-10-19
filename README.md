# pptx-skill

A skill for generating dense, expert-grade presentation pages in the style of ANY
reference deck, pptx or PDF, including components the reference never showed. The agent
does the design. Instruments do the measuring: an OOXML reader with full inheritance, a
style extractor that emits token roles with provenance, a layout solver with measured text
fit, an emitter that writes the house values on every run, and an outside judge that says
whether the result would be filed under the same house.

`SKILL.md` is the skill. Everything else supports it.

## Why this exists

The stock pptx skill treats a deck as a template to fill or as HTML to convert. It has no
notion of a house style as data, no way to measure whether a new page matches, and no
contract for a component the template never contained. This skill carries the style as a
guide with provenance for every value, solves layout in exact arithmetic with measured
wrap, and judges the output against the reference with a calibrated distance before anyone
looks at it.

No code or text from the stock skill is included. That skill is under a proprietary
licence that forbids copying and derivative works, so everything here was written fresh.
What was carried over is from deckgen, with the assumption behind each port recorded in
`PORT_AUDIT.md`.

## The path, in one paragraph

Render the reference and look at it. Extract a guide (`extract_style.py`): typography
levels and the role ladder, colour roles by usage and contrast, spacing steps from measured
gaps, composition families, register and density bands, legibility floors, chrome and
motifs. Complete what the extractor could not prove (`complete_guide.py --check`). Make a
template from the reference with its slides removed, or a blank page-sized template for a
PDF (`pptx_tools.py`). Write page specs that name roles and weights, never sizes or
coordinates. Build (`build_deck.py`): solve, emit, validate, render, judge. Read the render,
add content, build again until the page is as dense as the house allows. For a component
the reference never showed, write an expander and admit it on held-out data in a held-out
box (`component.py`).

## What was measured

Every number below was produced on this corpus by a script in the scratchpad of the
session that built the skill. None is estimated.

| Claim | Measurement |
|---|---|
| The judge tells houses apart | 147 of 161 held-out slides over 8 houses filed correctly (chance bound 28); 128 of 161 with the whole deck held out over 19 decks (chance bound 14) |
| The judge is not fooled by copying the master | deckgen's master-reuse deck (E18), which inherits the reference master verbatim, is flagged as off-style |
| The layout port is deckgen's solver | 383 boxes over 13 specimen slides at three scales: maximum difference 0 EMU; validation findings agree on 14 of 14 |
| The text ruler is the measured one | 90 of 90 recorded wrap cases agree with HarfBuzz; 89 of 90 with the Pillow fallback the sandbox has |
| The gallery port is deckgen's gallery | Component, candidate, cluster, crop and exemplar counts equal deckgen's recorded manifests on three decks; every exemplar skeleton byte-identical |
| The extractor reproduces deckgen's draft | Role sizes, surfaces, inks, floors, margins and content bands equal on jazz, keybank, netflix and exhibits; deviations listed in `PORT_AUDIT.md` |
| New pages read as the house | keybank: 4 generated pages with a novel football-field component, judge distance 0.191 against 0.353 to 0.677 for five other houses. McKinsey PDF: 2 generated pages, 0.360 against 0.378 for the nearest other house |

The McKinsey result is marginal and the gap is diagnosed in `SKILL.md` section 9: the
reference's size histogram puts its mass at 11, 16 and 18pt while the generated pages sit
on the 12pt body role, and its pages use navy fills that the specs did not ask for.

## Adopted and rejected, on merit

Judged against the goal (any reference, dense pitch-book pages, novel components, agent
designs, instruments measure):

- Adopted from deckgen: the inheritance-resolving reader, the token-role guide with
  provenance, the layout solver and text ruler, the gallery, the component admission
  contract, master reuse as the template, the nine design doctrines.
- Adopted that nobody proposed: a fingerprint judge with fitted weights (the extractor's
  own opinion is not evidence); drawn chrome for PDF references; a per-series contrast rule
  for chart labels; a render font report that names metric aliases so the agent does not
  copy letterforms from a substituted render.
- Rejected: the densification search and splitter (unbuilt in deckgen too; here the agent
  proposes arrangements and the solver checks them), the budget ledger and ADK agents, the
  user-correction overlay, python-pptx for reading (it hides inheritance), unit tests in the
  repo (the proofs are end-to-end runs with no mocks).

## Layout

```
SKILL.md                 the skill
PORT_AUDIT.md            every port, its assumption and its check
scripts/
  ooxml.py               package reader, inheritance chains, colour transforms, PDF reader
  extract_style.py       guide extraction with provenance; markdown report
  complete_guide.py      apply and check a completion patch
  fingerprint.py         style fingerprint and distance; calibrate; compare
  render.py              render to PDF and PNG; font substitution report; contact sheet
  gallery.py             component crops and exemplar skeletons
  layout.py, textfit.py  flex/grid solver, measured wrap, table fitter, scale descent
  emit_pptx.py           write a solved page into a template with house values on every run
  build_deck.py          spec -> solve -> emit -> validate -> render -> judge
  component.py           check and admit a component on held-out data
  pptx_tools.py          template surgery, delete, duplicate, clean, validate, blank
components/              admitted components (expand.py, spec.json, data, admitted.json)
references/design/       the nine design doctrines
examples/                worked completions and page specs for a pptx and a PDF reference
refs/                    manifest and fetch script for the public reference decks (files git-ignored)
```

## Requirements

Python 3.11 or later with lxml and Pillow; pdfplumber for PDF references; LibreOffice and
poppler for rendering; uharfbuzz if available (the Pillow ruler is the fallback and the
build report names which one ran).

## Known gaps

- No arrangement search: when a page does not fit, the solver reports the splittable
  groups and the row prefix that fits, and the agent decides.
- Hidden slides are read as evidence unless the agent excludes them.
- PDF references with no usable text layer (scans) are flagged and need an OCR step this
  skill does not provide.
- The judge was calibrated on 19 public decks from 8 houses; a house unlike all of them
  needs its own calibration run before the distance means anything.
