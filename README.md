# pptx-skill: building-pptx-decks

A skill (`name: building-pptx-decks`) for generating dense, expert-grade presentation
pages in the look of ANY reference deck the user drops in (a company template, a past
deck, pptx or PDF), including exhibits and components the reference never showed, or,
with no reference at all, in a look the model designs itself. One reference deck at a
time: given several, the model follows the one the user names, or asks. The agent does the design. Instruments do the measuring: an OOXML and PDF reader
with full inheritance, a style extractor that emits token roles with provenance, a section
plan checked against the reference's measured variety, a layout solver with measured text fit,
an emitter that writes the reference values on every run, gates that refuse what is measurably
wrong, and an outside judge that says which deck of a panel a new deck most resembles.

`SKILL.md` is the skill: a checklist workflow under 500 lines that sends the agent to one
reference file per task. Everything else supports it.

## Why this exists

The stock pptx skill treats a deck as a template to fill or as HTML to convert. It has no
notion of a reference style as data, no way to measure whether a new page matches, and no
contract for a component the template never contained. This skill carries the style as a
guide with provenance for every value, solves layout in exact arithmetic with measured
wrap, and judges the output against the reference with a calibrated distance before anyone
looks at it.

No code or text from the stock skill is included. That skill is under a proprietary
licence that forbids copying and derivative works, so everything here was written fresh.
What was carried over is from a predecessor system of the same author, with the assumption
behind each port recorded in `PORT_AUDIT.md`.

## The path, in one paragraph

Render the reference and look at it; triage a PDF first. With no reference, make a blank
draft (`extract_style.py --blank`), reason the look out and write it as a look brief
(`references/no-reference-design.md`), choose the whole look, and skip the round trip; the
build then runs every hard limit and reports "no reference" wherever it would compare. Extract a guide draft
(`extract_style.py`) and answer its open addresses by looking (`complete_guide.py`),
including the reference's title register, its exhibit digest (`gallery.py digest`: every
exhibit described in the model's own words) and which pages are content. Make a template from the reference with its slides removed, or a blank
page-sized one for a PDF (`pptx_tools.py`). Round-trip one of the reference's pages
(`import_slide.py`). Plan the section, with a brief for every exhibit written from
the reader and the data (what the reader must see, what is compared, at least two forms
weighed, the form chosen and why, the marks, and with a reference how its look applies),
and check the plan (`plan.py check`: briefs complete, variety against the reference's). Nothing asks the
model to pick a chart type or an annotation from a list; the corpus counts in the
references are evidence, and the lists left in code name what the emitter and the
annotation solver can draw. Write page specs that name roles and weights, never sizes or
coordinates, after looking at the reference's nearest pages and the page library. Build
(`build_deck.py --plan`): solve, emit, read back, validate, render, judge, and report the
realised variety, measured from the written file (composition, and exhibit structure read
from the chart XML, tables, pictures and drawn shapes, against the same reading of the
reference's own pages). Look at every render, write located findings, fix, rebuild within a cap,
keep the best build. For a component the reference never showed, write an expander and
admit it on held-out data in a held-out box (`component.py`).

## What was measured

Every number below was produced on this corpus by a script in the scratchpad of the
session that built the skill. None is estimated.

| Claim | Measurement |
|---|---|
| The judge tells firms apart | 152 of 165 held-out slides over 8 firms filed correctly with the shipped weights, 151 with weights re-fitted in the same run, 132 with equal weights (chance bound 29; weights fitted on the other half of the same corpus, judged leave-one-slide-out, single-slide decks split by deck, raster pages not scored; firms in `oracles/calibration-firms.txt`). The three Mergers and Inquisitions books are one firm (one fictional bank, one master) and the judge cannot tell them apart; it reports them as the same style, not as rivals |
| The judge is not fooled by copying the master | a master-reuse deck, which inherits the reference master verbatim, is flagged as off-style |
| The judge is not fooled by a wreck in the reference's clothes | Five decks a rater calls wrong (keybank's shapes at random positions, all stacked at one point, nine random boxes a page, a wall of text, every box overflowing) once filed under keybank at 0.013 to 0.192; they now carry `overlap` or `overflow` at 1.0 and fail the layout gate |
| The layout port is the predecessor's solver | 383 boxes over 14 specimen slides at three scales: maximum difference 0 EMU; validation findings agree on 14 of 14 |
| The text ruler is the measured one | 90 of 90 recorded wrap cases agree with HarfBuzz; 89 of 90 with the Pillow fallback the sandbox has |
| The gallery port is the predecessor's gallery | Component, candidate, cluster, crop and exemplar counts equal the predecessor's recorded manifests on three decks; crop rows match 12/12, 14/14 and 22/24; every exemplar skeleton byte-identical |
| The extractor tracks the predecessor's draft | Title, body, emphasis and caption sizes, surface and ink equal the predecessor's on jazz, keybank, netflix and exhibits; 47 of 160 compared values differ (h1/h2 sizes on two decks, rule and muted ink by deliberate change, spacing steps on two), listed in `PORT_AUDIT.md` and re-runnable with `oracles/diff_oracle.py` |
| New pages read as the reference (judge only) | keybank: 4 generated pages with a novel football-field component, 0.090 against the reference with the reference's own pages at 0.055 to 0.372, every page fit, filed (`examples/proofs/keybank-section.build.json`). A 17-page McKinsey board PDF (CalSTRS, 2024; a public board packet, not under `refs/`): 2 generated pages at 0.313 against a reference spread of 0.082 to 0.355: every page fit, not filed (`examples/proofs/mckinsey-pdf.build.json`). In a blind round on an earlier build the rater caught every generated page in two firms the judge had filed, so a filed deck is necessary, not sufficient (`evals/README.md`) |
| The chain reproduces the reference's own page | keybank slide 3 imported as roles and weights, re-solved and emitted on the keybank master: 0.056, inside the reference's own spread; the render matches the original to the eye. McKinsey PDF page 13: 0.097, filed, while the render lost the ring diagram, the gradient ground and the block positions: the number does not see it |
| PDF triage tells scans from vector exports | 19 reference PDFs classified per page; the 8 page-image decks (EDGAR prints, a bound filing, OCR scans, a stamped scan) come out `raster`, the 11 vector exports `vector`, with no deck misfiled against a reading of its renders |
| The raster instrument reads a render back | keybank rendered at 100 dpi and re-measured from pixels: surface and accent exact, ink within 1 unit, left margin within 0.01 in, the other sides within 0.08 in, the top and bottom rules at the walk's positions, body 11.7pt from a 14.4pt pitch against 12pt in the file |

The McKinsey pages are not filed; the judge's components carry the gap (sizes off the
reference's histogram, fills), and the renders show a flat navy where the reference draws a
gradient.

## What the review round found

Four reviewers ran the skill cold on a deck no proof had touched, attacked the judge,
fed it hostile inputs and judged the pages as a managing director would; skeptics then
tried to refute each finding. The reproduced ones are fixed in this tree and listed in
`PORT_AUDIT.md`: a percent paragraph spacing read as negative points that blanked every
bullet in LibreOffice, white labels read as black because a shape style's font reference
was ignored, the judge blind to overlap and overflow, a panel the agent could choose to
pass, table text with no ink on a dark reference, a football field that never drew the
offer it was about, titles false against their own exhibit. Not done, recorded: table
column levelling by added line count, paragraph rhythm per composition family.

## Adopted and rejected, on merit

Judged against the goal (any reference, dense pitch-book pages, novel components, agent
designs, instruments measure):

- Adopted from the predecessor: the inheritance-resolving reader, the token-role guide with
  provenance, the layout solver and text ruler, the gallery, the component admission
  contract, master reuse as the template. Its nine design doctrines were adopted and
  later rewritten as questions plus measured tendencies from the 578-page coded corpus:
  several of their rules (claim titles, label only what matters, one emphasis per
  table, same-sized panels are a dashboard, fills as a last resort, a source line on every
  data page) contradicted the corpus counts.
- Adopted that nobody proposed: a fingerprint judge with fitted weights (the extractor's
  own opinion is not evidence); drawn chrome for PDF references; a per-series contrast rule
  for chart labels; a render font report that names metric aliases so the agent does not
  copy letterforms from a substituted render.
- Rejected: the densification search and splitter (unbuilt in the predecessor too; here the agent
  proposes arrangements and the solver checks them), the budget ledger and ADK agents, the
  user-correction overlay, python-pptx for reading (it hides inheritance), unit tests in the
  repo (the proofs are end-to-end runs with no mocks).

## Layout

```
SKILL.md                 the skill: workflow checklist, commands, design questions, hard rules
PORT_AUDIT.md            every port, its assumption and its check
TARGET_SPEC.md           the target specification the skill is built against
scripts/
  preflight.py           packages, LibreOffice, poppler, fontconfig, HarfBuzz, a reference's faces
  cli.py                 where commands may write (never inside the skill); quiet exit on a closed pipe
  ooxml.py               package reader, inheritance chains, colour transforms, PDF reader and triage
  extract_style.py       guide extraction with provenance; markdown report; the reference's variety
  complete_guide.py      apply and check a completion patch (titles, exhibit digest, content pages)
  plan.py                the one variety measure (reference, plan, build); `check` a section plan
  fingerprint.py         style fingerprint and distance; calibrate; compare
  render.py              render to PDF and PNG; font substitution report; contact sheet
  raster_style.py        palette, ink, chrome, margins and line pitch from page images
  gallery.py             component crops, exemplar skeletons, the exhibit digest stub, pick
  library.py             the page library: permit, build, tag, check, pick, vocab, forget
  layout.py, textfit.py  flex/grid solver, measured wrap, table fitter, scale descent, capacity
  emit_pptx.py           write a solved page into a template with the guide's values on every run
  chart_geometry.py, annotate.py   data positions on charts and tables; annotations placed and checked
  build_deck.py          spec -> solve -> emit -> read back -> validate -> render -> judge -> variety -> leakage
  leakage.py             past decks' names, figures and phrases found in a new deck, chrome excluded
  component.py, component_api.py   check and admit a component; the solver's measures for components
  import_slide.py        a reference slide into a spec of roles: the round trip, and a seed
  pptx_tools.py          template, blank, layouts, text, duplicate, delete, clean, validate
references/              one level deep from SKILL.md, by domain:
  intake, no-reference-design, guide-completion, templates-and-chrome, planning-and-variety, page-specs,
  page-library, chart-recipes, build-report, components, review, editing, gotchas
  (procedures); storyline, titles-and-text, composition, charts, tables, typography,
  emphasis-and-decoration (design questions with measured tendencies);
  page_craft_vocabulary.json (the title vocabulary; no exhibit is read in a list)
evals/                   ten end-to-end scenarios and the blind-round and fresh-agent protocol
components/              four admitted components: football field, title block, bullet stack, KPI row
examples/                deck specs, section plans, completions and digests for a pptx and a PDF
                         reference, and for a deck with no reference; proofs/ build reports
oracles/                 the scripts behind every 'Checked by' in PORT_AUDIT.md
refs/                    manifest and fetch script for the public reference decks (files git-ignored)
```

## Requirements

Python 3.11 or later with lxml, Pillow and python-pptx; pdfplumber for PDF references; LibreOffice,
poppler and fontconfig; uharfbuzz if available (the Pillow ruler is the fallback and the
build report names which one ran). `python3 scripts/preflight.py` checks them and prints
the install commands. Commands write only under a work directory outside the skill
(`DECK_WORK` in SKILL.md).

## Known gaps

- No arrangement search: when a page does not fit, the solver reports the splittable
  groups and the row prefix that fits, and the agent decides.
- The reference's source-line habit is counted from the digest; the share above which a missing
  source line warns (half of three or more data pages) is unmeasured.
- The leakage report's matching rules and thresholds are unmeasured; its false positives
  have not been recorded across the scenarios.
- The football-field component's tick labels sat off their values on two renders; read the
  axis on every render until it is fixed.
- Hidden slides are read as evidence (the predecessor's rule); the digest lists them and the agent
  excludes them by deleting them from a copy.
- A scanned PDF yields palette, ink, chrome, margins and line pitch from pixels (confidence
  capped at 0.5) and nothing about faces; the agent names the family by eye.
- The judge was calibrated on 19 public decks from 8 firms and does not track a human
  rater; the blind round in `evals/README.md` is the success measure.
- The scenarios in `evals/` have not yet been run with fresh agents on every model tier.
