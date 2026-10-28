---
name: designing-presentations
description: Designs native, editable PowerPoint (.pptx) decks in the look of a .pptx or PDF reference the user supplies, or with none. Use to create, extend or edit slides, a pitch book or a board deck.
license: MIT (LICENSE.txt)
compatibility: Needs Python 3.11+ with lxml, Pillow, python-pptx and pdfplumber, plus LibreOffice, poppler and fontconfig for renders (uharfbuzz optional). scripts/preflight.py reports what is missing and how to install it; the skill installs nothing.
---

# Designing presentations, from a reference or from none

You design; the scripts measure and refuse. You decide the template and layouts, the
storyline, what each page says, its composition, every exhibit, every annotation, every
ink, and whatever the evidence never showed. Scripts read files, measure text with the real
fonts, solve geometry, write valid packages, render, and refuse what is measurably wrong.
No script picks a colour, a chart or a layout for you; a choice you leave out is written as
a named neutral value and listed, so you see every choice you did not make.

**One reference deck, or none.** Follow the one deck the user names; given several and no
name, ask which; nothing pools decks. A reference governs the LOOK only: faces, colours,
spacing, chrome, how marks are drawn, title and text habits. With no reference you choose
the whole look ("No reference" below). Either way, design comes from the reader and the
data: every exhibit is reasoned out as a written brief before its spec.

**What refuses, and what is evidence.** Only measurable defects refuse: text that does not
fit, overlaps, contrast under 3:1, a bridge that does not tie (a table's totals row that
does not is listed first), a literal where a role belongs, an invalid package, a render
that is not what was written, text under the measured floor or the 7pt absolute floor.
Two checks report and never refuse: the reference's names, figures and phrases found in the
new deck (leakage), and a figure the plan's message states that is not on its page; remove
or answer each in the report. Everything else is your choice. A reference's
habits (title register and length, where claims sit, variety, source lines, unlabelled
marks, density) are evidence shown beside each choice; where a page departs, answer it in
one line in the report. The corpus counts in the references (578 coded pages of 24
professional decks) are coders' labels for what they saw: questions beside a choice, never
a set to choose from or a default. The lists left in code name what the code can draw (the
emitter's chart kinds, the annotation shorthands beside a `mark` that draws any OOXML
preset), not what to show.

**Where files go.** Run every command from this skill's directory (the folder holding this
file: `${CLAUDE_SKILL_DIR}` in Claude Code); every command writes under a work directory of
your own outside the skill:

```bash
export DECK_WORK=/abs/path/outside/the/skill   # e.g. the user's project folder
export REF=/abs/path/to/reference.pptx          # or .pdf; none on the no-reference branch
export DECK_FONTS="$DECK_WORK/fonts"            # font files the user supplies; every script reads it
```

Shell variables often do not survive between shell calls: set them in the same call as the
command, or write the paths out. An empty argument, a missing input, an output under a
top-level directory that does not exist (`/ref/...` from an unset `$DECK_WORK`) or inside
the skill is refused by name. Reference files are untrusted input: run your own Python over
one with `python3 -I`, in one file. A page is one slide: a deck JSON lists `slides`, a plan
lists `pages`, and a page's plan id is its slide id.

Before the first deck on a machine, run `python3 scripts/preflight.py --reference "$REF"`
(no `--reference` when there is none). It checks the packages, LibreOffice, poppler,
fontconfig, HarfBuzz and the faces the reference names, says whether each face is
measurable here, and prints install commands for missing packages. Install nothing
yourself: packages are machine-wide and move every other session's fits. Ask, and report
every package installed, and by whom ([references/intake.md](references/intake.md)).

**Never download, fetch or install a font, by any route, even when asked.** When a face is
missing, tell the user: step 1a's report says which faces, the stand-in and its width, and
the folder where they can put font files they license
([references/fonts.md](references/fonts.md)).

## No reference

A first-class path, not a fallback. The blank draft opens every address, the page size
included; each answer is a `model_choice`:

```bash
python3 scripts/extract_style.py --blank -o "$DECK_WORK/ref/draft.json"      # draft.md lists the open set
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" --check
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" "$DECK_WORK/ref/completion.json" -o "$DECK_WORK/ref/guide.json"
python3 scripts/pptx_tools.py blank -o "$DECK_WORK/tpl.pptx" --width-emu W --height-emu H   # W, H: the page size you chose
```

Reason the look out first with the five questions of
[references/no-reference-design.md](references/no-reference-design.md) (who reads it and
where; the subject's own world, and when borrowing is costume; the data and the density it
calls for; a named brand; restraint). Write the answers as `/look_brief`, paste it into
your response, and only then answer every other address (page size, installed faces, a
ladder with nothing under 7pt, palette, spacing, chrome or `[]`, tables, charts,
`/description`). Nothing has a default; the brief is refused only when missing or a
placeholder, never weighed. Then step 1a with `--guide` alone, and steps 5 to 11 with no `--reference`, `--chrome draw`, a
null `reference_sha256` and no `in_reference_look`: every hard limit runs, a look left to
the stock theme or a constant is refused, and every comparison reports "no reference".
Worked: `examples/no-reference.*` (a board review) and `examples/no-reference-credit.*` (a
dense credit book).

## Workflow

Copy this checklist into your response and tick it off. Steps 1a, 5, 7, 8 and 9 are loops: run
the check, fix what it names, run it again.

```
Deck progress:
- [ ] 1. Intake: render, extract, gallery (triage a PDF first); no reference: the blank draft
- [ ] 1a. Fonts: fonts.py report; show the user; wait for their files, licence or approval
         of each stand-in; run it again until it exits 0
- [ ] 2. Guide: answer every open address, including /titles/register,
         /exhibit_habits (from the digest) and /variety/content_pages; --check until nothing is open
- [ ] 3. Template: the reference's template with its slides removed, or a blank page
- [ ] 4. Round trip: rebuild one of the reference's own pages and compare renders
         (nothing to round-trip with no reference)
- [ ] 5. Section plan: plan.json with an exhibit brief per exhibit; plan.py check until it passes
- [ ] 6. Page specs: context first, then capacity, then the spec
- [ ] 7. Build with --plan; read the report; fix refusals; rebuild
- [ ] 8. Review every render at full size against each exhibit's brief; located findings;
         fix; rebuild (cap 8 builds per 5-page section; keep the best build)
- [ ] 9. Annotation: can each exhibit's claim be found on it? Mark, or say why not; rebuild
- [ ] 10. Variety report: realised variety against the plan, with the reference's beside it
- [ ] 11. Validate the package; final report
```

### 1. Intake

```bash
python3 scripts/ooxml.py triage "$REF"                              # PDF only: per-page vector or raster
python3 scripts/render.py "$REF" --out "$DECK_WORK/ref/renders" --width 1600 --grid
python3 scripts/extract_style.py "$REF" -o "$DECK_WORK/ref/draft.json" --report "$DECK_WORK/ref/draft.md"
python3 scripts/gallery.py "$REF" --out "$DECK_WORK/ref/gallery" --guide "$DECK_WORK/ref/draft.json"
python3 scripts/raster_style.py "$REF" --out "$DECK_WORK/ref/raster"  # only when triage says deck_class raster
```

Look at `renders/grid.png`, then read `draft.md` in full, `renders/fonts.json`, and
`gallery/MANIFEST.md` with its exemplars. PDF triage, scans and missing fonts:
[references/intake.md](references/intake.md).

### 1a. Fonts

```bash
python3 scripts/fonts.py report "$REF" -o "$DECK_WORK/ref/fonts.json"    # no reference: --guide "$DECK_WORK/ref/guide.json" after step 2
```

Exit 0: every face that sets text resolves (fonts folder, installed, metric-compatible, or
a stand-in the guide names). Exit 3: paste `fonts.md` into your response and wait for the
user: font files they license in `$DECK_FONTS`, a licence confirmed for a font the
reference embeds (`fonts.py extract`), or approval of each stand-in at the width shown.
Then run it again. Build nothing until it exits 0. The built deck embeds no font: tell the
user which faces a recipient must have. The loop, the report and fsType:
[references/fonts.md](references/fonts.md).

### 2. Complete the guide

```bash
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" --check     # each open address with its value shape
python3 scripts/gallery.py digest "$REF" --out "$DECK_WORK/ref/digest" --guide "$DECK_WORK/ref/draft.json"   # --pages 30-70 on a long deck
# copy digest/digest.stub.json to digest/digest.json; fill every page's exhibits and source_line after looking
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" "$DECK_WORK/ref/completion.json" \
        -o "$DECK_WORK/ref/guide.json" --digest "$DECK_WORK/ref/digest"
```

Answer exactly the open addresses, no others; observed values are never overwritten. Three
answers are read by looking, and carry the reference's habits into every later step as
evidence: `/titles/register` (each title topic, claim, question or other, in your words),
`/exhibit_habits` (the digest: one record per exhibit in your own words after looking at
its crop, beside the `file_facts` the file itself states) and `/variety/content_pages`.
`null` means the reference has no such text or colour anywhere; a value seen only inside
pasted pictures is answered with `"evidence": "pictures"`. `color.emphasis` is the
reference's look-here colour, never inferred from a hue. A run reports every refusal at
once and writes nothing until all pass. Value shapes, floors, the digest and worked
completions: [references/guide-completion.md](references/guide-completion.md).

### 3. Template

```bash
python3 scripts/pptx_tools.py template "$REF" -o "$DECK_WORK/tpl.pptx"                    # pptx reference
python3 scripts/pptx_tools.py blank -o "$DECK_WORK/tpl.pptx" --width-emu W --height-emu H    # PDF or no reference: W, H from guide.reference.page
python3 scripts/pptx_tools.py layouts "$DECK_WORK/tpl.pptx" --reference "$REF"            # pptx reference: its slides counted
```

Every page names one of the template's layouts. Which layout did the reference use for
pages like this, and does this page need the same frame? `layouts` prints how many of the
reference's slides use each one, an unused layout included. A PDF reference, and a deck
with no reference, builds with `--chrome draw`.

The template draws the reference firm's name and logo on every page. For a deck of that
firm, keep them; for another firm or a fictional one, ask the user, then write the choice
per chrome id in the deck JSON (`"firm_chrome": {"chrome-13": "drop"}`, a `{"text": ...}`
or a logo's `{"image_path": ...}`); the build reports each entry's decision. Chrome,
layouts and the round trip:
[references/templates-and-chrome.md](references/templates-and-chrome.md). Extending,
reordering or editing an existing deck (its own pages are the reference):
[references/editing.md](references/editing.md).

### 4. Round trip

```bash
python3 scripts/import_slide.py "$REF" --survey --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/rt/survey.json"   # --pages 30-45 on a long deck
python3 scripts/import_slide.py "$REF" --slide N --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/rt/rt.deck.json"
python3 scripts/build_deck.py "$DECK_WORK/rt/rt.deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
        -o "$DECK_WORK/rt/rt.pptx" --reference "$REF" --renders "$DECK_WORK/rt/renders" [--chrome draw]
```

The survey imports every page as the round trip would and lists what each holds, what it
would lose and whether it fits at full scale. Take a candidate it marks (a content page on
the reference's most used layout, with a title, text and an exhibit, nothing lost,
fitting); with none, the page that loses least, and name each loss in the report. Read
`judge.total` against `judge.reference_spread`, then put the render beside the original:
the distance does not see what was lost (a consulting page round-tripped at 0.100, filed,
with its ring diagram and block positions gone). How to choose and read it:
[references/templates-and-chrome.md](references/templates-and-chrome.md), "The round trip".

### 5. Section plan

Write the storyline and `$DECK_WORK/plan.json`, then:

```bash
python3 scripts/plan.py check "$DECK_WORK/plan.json" --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/plan.check.json"
```

Each exhibit gets a brief in the plan, and the brief is where you think hard about the
visual: what the reader must see; what is compared against what; the data's shape in your
words; at least two forms weighed, each with why not or why; the form chosen and why; what
will be marked, where the claim lives; with a reference, optionally `in_reference_look`
(how its look applies to the form chosen). A form you cannot argue for against another is
not chosen yet. The check reads a brief for being there, never for what it says; it warns,
with the reference's figure beside yours, where the plan departs from the reference's
variety or title register. Name compositions honestly, and give `deliberate_parallel` a
reason where a page repeats the one before it. Compute every figure a title or lead-in
states with a script that asserts it and prints what it asserted
(`python3 "$DECK_WORK/figures.py" > "$DECK_WORK/figures.txt"`, as
`examples/no-reference.figures.py` does); that output is what the build's `--computed`
reads. Schema, what refuses and warns, and the brief:
[references/planning-and-variety.md](references/planning-and-variety.md). Questions and
evidence for exhibits: [references/charts.md](references/charts.md).

### 6. Page specs

No exhibit spec is written before its brief. If the spec draws a different form or marks a
different place than the brief says, the brief was not finished: rewrite the brief first.
Gather each page's context ("Designing a page" below), then budget the text:

```bash
python3 scripts/gallery.py pick "$DECK_WORK/ref/gallery" --intent "WHAT THE PAGE DOES" --guide "$DECK_WORK/ref/guide.json"
python3 scripts/library.py pick --intent "WHAT THE PAGE DOES" --data-shape "THE DATA IN WORDS" --aspect W:H \
        --gallery "$DECK_WORK/ref/gallery" --guide "$DECK_WORK/ref/guide.json" [--own COMPANY_LIBRARY]
python3 scripts/layout.py capacity "$DECK_WORK/deck/deck.json" --slide ID --guide "$DECK_WORK/ref/guide.json" [--chrome draw]
```

`capacity` solves the page exactly as the build will and prints each text element's box,
lines and spare characters at full scale, each table's `rows_to_fit`, each annotation as
placed, and, for a page over budget, the causes in words. Write the skeleton with short
placeholder text, read the budgets, then write the words.

The deck is one JSON, `{"slides": [...]}`, each slide with `id`, `layout`, `spec`, and
optional `charts`, `styling`, `annotations`, `notes` and `"title": {"register": ...}`.
Roles only; a literal colour, size, font or coordinate is refused, and so is a key on a
node that nothing reads. Where to read:

| For | Read |
|---|---|
| the spec grammar, limits, pictures (logos, icons as small SVG in colour roles, the user's files) | [references/page-specs.md](references/page-specs.md) |
| drawing the form your brief chose, technique by technique (two value axes, rows aligned to categories, marks) | [references/chart-recipes.md](references/chart-recipes.md) |
| table spec keys and per-table `emphasis` roles | [references/tables.md](references/tables.md) |
| building a company page library | [references/page-library.md](references/page-library.md) |

### 7. Build

```bash
python3 scripts/build_deck.py "$DECK_WORK/deck/deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
        -o "$DECK_WORK/out/b1/deck.pptx" --reference "$REF" --renders "$DECK_WORK/out/b1/renders" --plan "$DECK_WORK/plan.json" \
        [--chrome draw] [--brief "$DECK_WORK/brief.txt" ...] [--computed "$DECK_WORK/figures.txt"]   # no reference: no --reference
```

Give each build its own folder (`out/b1/`, `out/b2/`, ...). With `--plan` the deck holds the
whole plan or one run of consecutive planned pages (one slide while you work on one page).
Exit 0 means every page fit and the package is valid; only a passing build writes the deck
and renders at the paths given. The command prints a brief; the whole report is
`deck.build.json` beside the deck. Read refusals first, then `chart_defaults_taken` (write
each choice into the spec until only what you meant remains), `title`, `density`,
`contrast`, `repetition`, `leakage`, `judge`. An unfittable page: re-arrange, cut words, or
split at a declared boundary; never drop content. Every field, refused-build files and
what counts against the cap: [references/build-report.md](references/build-report.md).

### 8. Review every render

Open every page image in the build's renders at full size (with a reference, beside its
pages nearest in intent) and hold each exhibit to its brief: does the reader see what
`reader_must_see` says, in three seconds, without arithmetic? Is the comparison the brief
names drawn? Are the marks where the claim lives, and does each say what it marks? Does the
text add what the exhibit cannot? A render that fails its brief is a finding even when
every gate passed. Write located findings as a senior reviewer would (element id, what is
wrong, the change; never a score), fix the specs, rebuild. Cap: 8 builds per 5-page
section. Hand over the best build by refusals, then open findings, then likeness to the
look, not the last one. What to look for, in order:
[references/review.md](references/review.md).

### 9. Annotation

For each exhibit, take the `marks` line of its brief: can the claim be found on the
exhibit? With a reference, its records of what it marks (`exhibit_habits.records[].marks`
and the marks its files draw) are evidence beside your choice (7 of 291 coded charts are
bare). The means are open: `annotations` on the slide (reference
lines, outline boxes, bands, brackets, callouts, badges, rows under the categories, or a
`mark` in any OOXML preset or line end, at data positions or on any element's box), or
native emphasis (a point fill, an emphasis row). Nothing annotates by itself; an annotation
that collides or covers the host's text is refused. Ink a mark in `color.emphasis`, not
`color.negative` (a bad value); with none, the rule or ink role.

A mark says what it means: a ring, box, band, line or bracket carries a `label` or names
under `explained_by` what explains it. Otherwise the build warns `annotation unexplained`
with the reference's own count, and you answer it in the report; a named explanation that
is not there is refused. A data page without a source line warns where most of the
reference's data pages carry one; add one or say why not. Kinds, anchors, explanations and
worked exhibits: [references/chart-recipes.md](references/chart-recipes.md), "Marks at data
positions"; source lines: [references/build-report.md](references/build-report.md).

### 10. Variety report

From `repetition` in the build report: realised composition V, exhibit structure V and
exhibit kinds V, with the reference's beside them ("no reference" with none), runs over
the reference's longest, `warnings`, and every page in `plan.pages_differing_from_plan`.
All are read from what was built, never from names. Explain each warning and each
disagreement in one line: a deliberate parallel, or a fix you made. What each measure
reads and cannot see: [references/planning-and-variety.md](references/planning-and-variety.md),
"What the build reports against the plan".

### 11. Validate and report

```bash
python3 scripts/pptx_tools.py validate "$DECK_WORK/out/b1/deck.pptx" --render
python3 scripts/pptx_tools.py validate "$DECK_WORK/out/b1/deck.pptx" --emit --guide "$DECK_WORK/ref/guide.json"
```

Read `leakage` (every name, figure and phrase of the past deck found in the new deck, the
reference's chrome left out): remove each distinctive one in `pages`, or confirm the user
supplied it; `--brief` and `--computed` keep the user's words and your own arithmetic off
the list. Read `judge.components`: a deck nearer another panel deck than its reference
shows which components carry the distance; fix it or say why it stands. With no reference
both read "no reference". Both: [references/build-report.md](references/build-report.md),
"Leakage" and "The judge".

The final report states:

```
- template and layouts chosen, and why
- what was measured; what you completed by judgement (with confidence) or, with no
  reference, chose (with why); fonts substituted, supplied or extracted; what the user must
  supply; the faces a recipient must have
- every page's status and scale; open findings from the last review
- the variety report; each departure from a reference habit in one line
- the leakage report; the firm chrome kept, replaced or dropped
- the judge's verdict, labelled as necessary and not sufficient
- any conflict between sources (template against brand guideline) and how you resolved it
```

## Designing a page

High freedom: many designs are valid. Give yourself the context, then reason; no rule here
fixes a design.

Context for every page: the guide (`description`, `derivation_rules`, roles, `titles`,
`exhibit_habits`, `variety`, density bands) and your plan's line for the page; the data,
with every stated figure computed; with a reference, its own pages nearest this intent
(renders, gallery exemplars, digest records) and library picks with their `why` and `ask`
lines.

Questions to answer before writing the spec:
- What should the reader leave with: the page's message, or what they look up on a
  reference page? Which slot carries it (with a reference, `guide.titles.claims_elsewhere`
  shows where it states claims), or does this page need somewhere else?
- Is this a page of argument or of reference? Does each block's size say how much it
  matters? Where does the eye finish?
- Co-equal blocks: a comparison (one scale, one order) or unrelated facts?
- What is the data's shape, in its own terms? Which forms could show the comparison the
  reader must make, and what does each ask of the eye? How does the look draw the form?
- Where on the exhibit does the claim live, and how will you mark it? How much does it
  label; does it need a legend or gridlines?
- What does the text add that the exhibit cannot? Is anything said twice?
- What would a managing director circle in red?

The full question sets with their measured tendencies:
[references/storyline.md](references/storyline.md),
[references/titles-and-text.md](references/titles-and-text.md),
[references/composition.md](references/composition.md),
[references/charts.md](references/charts.md),
[references/tables.md](references/tables.md),
[references/typography.md](references/typography.md),
[references/emphasis-and-decoration.md](references/emphasis-and-decoration.md).

Low freedom where it is fragile: OOXML, fit, validation and confidentiality are the
scripts' job. Run them as written; do not edit generated packages by hand, and do not work
around a refusal by changing the guide.

## Hard rules

- Roles only in a spec; no literal colour, size, font or coordinate.
- Every page on a named layout of the chosen template.
- Figures from the user's data, byte for byte; every stated figure computed; a missing
  figure is a named placeholder. Never invent a number.
- Nothing dropped to make a page fit; unfittable is a report.
- Never below `max(floor_pt, absolute_floor_pt)`; observed guide values are never
  overwritten by completion.
- Contrast under 3:1 refuses the page, and so does a bridge that does not tie; a table's
  totals row that does not tie out is listed first in the problems.
- No content from a past deck that the user did not supply for this deck; company files,
  guides, digests and libraries stay in `$DECK_WORK`, outside this skill.

## Files

| Path | Run or read |
|---|---|
| `scripts/preflight.py` | run once per machine: packages, LibreOffice, poppler, fontconfig, HarfBuzz, faces |
| `scripts/fonts.py` | run: `report`, the font report; `extract`, a .pptx's embedded fonts after the user confirms a licence |
| `scripts/ooxml.py` | run `triage` on a PDF; the OOXML and PDF reader behind every script |
| `scripts/render.py` | run: LibreOffice to PNG, font report, contact sheet |
| `scripts/extract_style.py` | run: reference to guide draft with provenance and the open list; `--blank` for no reference |
| `scripts/raster_style.py` | run on a raster PDF: palette, ink, chrome, margins, line pitch |
| `scripts/gallery.py` | run: crops and exemplars; `digest`, the exhibit digest stub; `pick` |
| `scripts/complete_guide.py` | run: fold your completion into the draft under the rules |
| `scripts/pptx_tools.py` | run: template, blank, layouts, text, duplicate, delete, clean, validate |
| `scripts/import_slide.py` | run: a reference page into a spec of roles, for the round trip |
| `scripts/plan.py` | run: `check` a section plan; `reference` the reference's variety |
| `scripts/library.py` | run: the page library (permit, build, tag, check, pick, vocab, forget) |
| `scripts/layout.py` | run `capacity`; read its docstring for the page grammar |
| `scripts/build_deck.py` | run: solve, emit, read back, validate, render, judge, leakage |
| `scripts/leakage.py` | run on any deck: past decks' content found in it (the build runs it too) |
| `scripts/images.py` | run: `list` and `extract` the reference's pictures; `check` an icon in the SVG subset |
| `scripts/emit_pptx.py`, `textfit.py`, `fontfiles.py`, `chart_geometry.py`, `annotate.py`, `fingerprint.py`, `cli.py` | called by the build and the commands |
| [references/gotchas.md](references/gotchas.md) | read when a render and PowerPoint disagree: measured OOXML and renderer facts |
| `references/page_craft_vocabulary.json` | data: the title vocabulary (register, companions); no exhibit is read in a list |
| `examples/` | worked deck specs, plans, completions, digests (with a reference and with none) |
| `refs/` | `MANIFEST.md`: the judge's panel of public decks, in the git-ignored `refs/files` once the user has fetched them |

Requirements (preflight.py checks them): Python 3.11+, lxml, Pillow, python-pptx, pdfplumber,
LibreOffice, poppler, fontconfig, uharfbuzz when available. The judge's panel: `refs/files`, which the user fills; never download it yourself.
