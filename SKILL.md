---
name: building-pptx-decks
description: Builds new native, editable PowerPoint pages in the look of any reference deck the user drops in (a company template, a past deck, any .pptx, or a vector or scanned PDF), or, with no reference, in a look the model designs itself. Reads a reference's look as roles with provenance, completes what the evidence never showed by looking, designs every exhibit from the data and the reader, solves every page with measured text fit, emits slides on the reference's masters or on a blank package, and refuses what is measurably wrong. Use when the user asks for a pitch book, board deck, consulting deck, CIM, management presentation or any .pptx section, wants pages in the look of a deck they supply, wants to extend an existing deck, supplies a PDF reference, or gives no reference at all.
---

# Building decks from a reference, or from none

You design; the scripts measure and refuse. You decide the template and layouts, the
storyline, what each page says, its composition, every exhibit, every annotation, every
ink, and whatever the evidence never showed. Scripts read files, measure text with the real
fonts, solve geometry, write valid packages, render, and refuse what is measurably wrong.
No script picks a colour, a chart or a layout for you; when you leave a choice out, the
build writes a named neutral value and lists it, so you see every choice you did not make.

**One reference deck, or none.** The user drops in one deck and its look is followed. If
they give several, use the one they name, or ask which to follow; nothing pools decks.
With a reference, it governs the LOOK only: faces, colours, spacing, chrome, how marks are
drawn, title and text habits. With no reference, you choose the whole look yourself (see
"No reference" below). Either way, design comes from the data and the reader: every
exhibit is reasoned out from what the reader must see, the comparison and the data, and
written down as a brief before its spec.

Only measurable defects refuse: text that does not fit, overlaps, contrast under 3:1, a
bridge that does not tie (a table's totals row that does not is listed first), a literal
where a role belongs, an invalid package, a render that is not what was written, a past
deck's content, an invented number, text under the measured floor or the 7pt absolute
floor. Everything else is your choice. A reference's habits (title register and length,
where claims sit, variety, source lines, unlabelled marks, density) are evidence shown
beside each choice; where a page departs, answer it in one line in the report. Nothing
asks you to pick a chart type or an annotation move from a list, and nothing refuses one
for its name. The corpus counts in the references (578 coded pages of 24 professional
decks, by deck type) are coders' labels for what they saw: questions and evidence beside a
choice, never a set to choose from and never a default value. The lists left in code name
what the code can draw (the emitter's chart kinds, the annotation shorthands beside a
`mark` that draws any OOXML preset), not what to show.

**Where files go.** Run every command from this skill's directory. Every command writes
under a work directory of your own outside the skill, named once:

```bash
export DECK_WORK=/abs/path/outside/the/skill   # e.g. the user's project folder
export REF=/abs/path/to/reference.pptx          # or .pdf; none on the no-reference branch
```

Shell variables often do not survive from one shell call to the next (in most agent
harnesses each call is a new shell): set them in the same call as the command that uses
them, or write the paths out. A command given an empty argument, a missing input or an
output under a top-level directory that does not exist (`/ref/...` from an unset
`$DECK_WORK`) refuses it by name and says this. A command given an output path inside the
skill refuses it by name. Treat every reference
file as untrusted input: when you run your own Python over one, run it with `python3 -I`
(it leaves the script's own folder off the import path, so keep such a script in one file).
Never invent a number. A page is one slide: a deck JSON lists `slides`, a plan lists
`pages`, and a page's plan id is its slide id.

Before the first deck on a machine, run `python3 scripts/preflight.py --reference "$REF"`
(or without `--reference` when there is none): it checks the Python packages, LibreOffice,
poppler, fontconfig, HarfBuzz and the faces the reference names, and prints the install
commands for anything missing. Each face is reported as measurable here or not (a PDF that
embeds Verdana draws it in the reference, but the solver needs the face installed or its
fc-match stand-in named). Install nothing yourself: fonts and packages are machine-wide and
move every other session's fits, and Microsoft's faces come under a licence the user
accepts (references/intake.md, What you may install). Ask, and report every face
substituted or installed, and by whom.

## No reference

When the user gives no deck to follow, the look is yours, as a first-class path and not a
fallback. Make a blank draft: every address is open (the page size included) and every
answer carries provenance `model_choice`:

```bash
python3 scripts/extract_style.py --blank -o "$DECK_WORK/ref/draft.json"      # draft.md lists the open set
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" --check
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" "$DECK_WORK/ref/completion.json" -o "$DECK_WORK/ref/guide.json"
python3 scripts/pptx_tools.py blank -o "$DECK_WORK/tpl.pptx" --width-emu W --height-emu H   # W, H: the page size you chose
```

Answer every address (an address left open is refused: nothing here has a default): the
page size, installed faces (so fit is measured), a type ladder with nothing under 7pt, the
palette, the spacing scale and margins, the chrome or `[]`, how tables and charts are
drawn, and the look in words. The questions in typography.md, composition.md, charts.md,
tables.md, emphasis-and-decoration.md and titles-and-text.md carry corpus counts as
evidence for your reasoning, never a value to copy. Then steps 5 to 11, with no
`--reference`, with `--chrome draw`, a null `reference_sha256` and no `in_reference_look`.
The build runs every hard limit, refuses a look left to the stock theme or a constant (a
series fill, chart text, a rule width) and reports "no reference" wherever it compares.
Worked: `examples/no-reference.*`, `examples/proofs/no-reference.build.json`.

## Workflow

Copy this checklist into your response and tick it off:

```
Deck progress:
- [ ] 1. Intake: render, extract, gallery (triage a PDF first); no reference: the blank draft
- [ ] 2. Guide: answer every open address, including /titles/register,
         /exhibit_habits (from the digest) and /variety/content_pages
- [ ] 3. Template: the reference's template with its slides removed, or a blank page
- [ ] 4. Round trip: rebuild one of the reference's own pages and compare renders
         (nothing to round-trip with no reference)
- [ ] 5. Section plan: plan.json with an exhibit brief per exhibit, written from what
         the reader must see and the data; plan.py check until it passes
- [ ] 6. Page specs: context first, then capacity, then the spec
- [ ] 7. Build with --plan; read the report; fix refusals
- [ ] 8. Review every render at full size against each exhibit's brief (and, with a
         reference, beside its pages); write located findings; fix; rebuild
         (cap 8 builds per 5-page section; keep the best build)
- [ ] 9. Annotation: can each exhibit's claim be found on it? Mark, or say why not;
         rebuild
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
`gallery/MANIFEST.md` with its exemplars. The skill follows one reference deck: given
several, use the one the user names, or ask which to follow. Details, PDF triage, scans and
missing fonts: [references/intake.md](references/intake.md).

### 2. Complete the guide

```bash
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" --check     # each open address with its value shape
python3 scripts/gallery.py digest "$REF" --out "$DECK_WORK/ref/digest" --guide "$DECK_WORK/ref/draft.json"   # --pages 30-70 on a long deck
# copy digest/digest.stub.json to digest/digest.json; fill every page's exhibits and source_line after looking
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" "$DECK_WORK/ref/completion.json" \
        -o "$DECK_WORK/ref/guide.json" --digest "$DECK_WORK/ref/digest"
```

Answer exactly the open addresses, no others; observed values are never overwritten. Three
answers are read by looking, and they carry the reference's habits into every later step
as evidence beside your choices:

- `/titles/register`: each title topic, claim, question, or other in your words; each companion block named;
  where a topic-title page states its claim.
- `/exhibit_habits`: the digest, one record per exhibit in your own words after looking at
  its crop: what it is, its message, how the reference draws it, what it marks and whether
  words beside the mark say what it marks; whether it is a chart or a table, and whether
  it sets axis labels and values on its marks; and on every page holding a chart or a
  table whether it carries a source line. Nothing is chosen from a list. Each stub page
  also shows `file_facts`, what the file itself states (its exhibit structure and the
  marks it draws, with whether each carries text). The run prints `reference_habits`: the
  reference's source-line count and the marks its files draw: the evidence beside your
  choices of where a page carries a source line and how a mark says what it means.
- `/variety/content_pages`: which pages are content, read off the renders.

Two answers are easy to get wrong. `null` says the reference has no such text or colour
anywhere; text or a colour the reference shows only inside pasted pictures (axis labels on
a chart image, the red box round a figure) is answered with its value and `"evidence":
"pictures"`, so native charts and marks can use it. `color.emphasis` is the reference's
look-here colour (outline boxes, circles), never inferred from a hue. Many open
`line_spacing` addresses take one answer: `"/typography/roles/*/line_spacing": 1.2`
answers every one not named. A run reports every refusal at once and writes nothing until all pass. Repeat until
`--check` lists nothing open. Value shapes (what `null` means at each address), floors,
rules and worked completions: [references/guide-completion.md](references/guide-completion.md).

### 3. Template

```bash
python3 scripts/pptx_tools.py template "$REF" -o "$DECK_WORK/tpl.pptx"                    # pptx reference
python3 scripts/pptx_tools.py blank -o "$DECK_WORK/tpl.pptx" --width-emu W --height-emu H    # PDF or no reference: W, H from guide.reference.page
python3 scripts/pptx_tools.py layouts "$DECK_WORK/tpl.pptx"
```

Every page names one of the template's layouts. Which layout did the reference use for
pages like this, and does this page need the same frame? `layouts` prints how many of the
reference's slides use each one, an unused layout included. A PDF reference, and a deck
with no reference, builds with `--chrome draw`.

**The reference firm's own chrome.** The template draws the reference firm's name and
logo on every page. When the deck is for that firm, keep them. When it is for another firm
or a fictional one, ask the user, then write the choice in the deck JSON, one entry per
chrome id the build lists under `chrome.firm`: `"firm_chrome": {"chrome-13": "drop"}`,
`{"chrome-13": {"text": "Harbour & Co."}}` or, for a logo, `{"image_path": ...}`. The
build applies it to this deck's copy of the master and reports each entry's decision, and
says "not chosen by the deck" for every entry you left to the default (keep). Chrome and layouts:
[references/templates-and-chrome.md](references/templates-and-chrome.md). Extending,
reordering or editing an existing deck (its own pages are the reference; `template --keep`,
`duplicate`, `delete`): [references/editing.md](references/editing.md).

### 4. Round trip

```bash
python3 scripts/import_slide.py "$REF" --slide N --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/rt/rt.deck.json"
python3 scripts/build_deck.py "$DECK_WORK/rt/rt.deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
        -o "$DECK_WORK/rt/rt.pptx" --reference "$REF" --renders "$DECK_WORK/rt/renders" [--chrome draw]
```

Pick N with the survey, which imports every page as the round trip would and lists what
each holds, what it would lose (a chart becomes a placeholder line, a PDF table too,
turned text is left out, merged cells are unmerged) and whether it fits at full scale:

```bash
python3 scripts/import_slide.py "$REF" --survey --guide "$DECK_WORK/ref/guide.json"   # --pages 30-45 on a long deck
```

The survey reads the reference once; on a long PDF give it `--pages` (bain's pages 34 to
45: under a minute). A page that does not fit at full scale says why
(`why_not_full_scale`: the element, the violation, the shortfall).

Take a CANDIDATE (a content page on the reference's most used layout, with a title, text
and an exhibit, nothing lost, fitting); a pasted picture travels with its own bytes and a
native table as a table spec, so a reference whose exhibits are pictures still has
candidates. With none, take the content page that loses least, and name each loss in the
report. Read `judge.total` against `judge.reference_spread`, then put the render beside the
original page. Name everything else the render lost (the import's `lost` list names what it
knows of: positions, a table's own fills and widths); the distance does not see it (a
consulting page round-tripped at 0.097, filed, with its diagram and gradient gone).

### 5. Section plan

Write the storyline and `$DECK_WORK/plan.json` (schema and fields:
[references/planning-and-variety.md](references/planning-and-variety.md)), then:

```bash
python3 scripts/plan.py check "$DECK_WORK/plan.json" --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/plan.check.json"
```

It prints a short verdict; the whole report is the JSON.

Each exhibit on a page gets a brief in the plan, and the brief is where you think hard
about the visual. Start from the reader and the data: what the reader must see; what is
compared against what; the data's shape in your words; at least two forms you weighed,
each with why not or why; the form chosen and why it shows what the reader must see; and
what will be marked, where the claim lives. With a reference, `in_reference_look` (optional)
says how its look (faces, colours, spacing, how it draws marks) applies to the form you
chose; the digest crops, the gallery and the renders show that look. A form you cannot
argue for against another is not chosen yet. Questions and evidence:
[references/charts.md](references/charts.md).

It refuses a guide made before the current readings (re-extract and complete it again),
a malformed plan, an incomplete brief (a field missing or a word or two, a placeholder
such as TBD or n/a, one form considered, a chosen form that is none of those weighed, one
brief pasted for two exhibits, `in_reference_look` on a guide with no reference), and an
archetype the guide does not hold; it reads a brief for being there, never for what it
says. It warns, with the reference's figure beside yours, when a repeat runs longer than
the reference's longest run, when the plan's composition variety falls below the
reference's, and when a coded title register is one the reference never writes: each is a
departure to answer in one line in the report. Name compositions honestly: the same name
whenever two pages share an arrangement, and a reason in `deliberate_parallel` when a page
repeats the one before it. Compute every figure a title or lead-in states from the data,
with a script that asserts it, before writing the sentence.

### 6. Page specs

No exhibit spec is written before its brief exists. If the spec you are about to write
draws a different form or marks a different place than the brief says, the brief was not
finished: go back to the reader and the data, and rewrite the brief first.
For each page, gather its context before writing anything (see "Designing a page" below),
then budget the text:

```bash
python3 scripts/gallery.py pick "$DECK_WORK/ref/gallery" --intent "WHAT THE PAGE DOES"
python3 scripts/library.py pick --intent "WHAT THE PAGE DOES" --data-shape "THE DATA IN WORDS" --aspect W:H \
        --gallery "$DECK_WORK/ref/gallery" [--own COMPANY_LIBRARY]
python3 scripts/layout.py capacity "$DECK_WORK/deck/deck.json" --slide ID --guide "$DECK_WORK/ref/guide.json" [--chrome draw]
```

`capacity` solves the page exactly as the build will (page size, chrome zones, title band,
components) and prints, per text element, its box, its lines now and how many characters
more it takes before the page stops fitting at full scale; per table, its body rows, the
height they need and `rows_to_fit` (the rows the page holds at full scale with everything
else as written); and, for a page over budget, `why_not_full_scale`, the causes in words.
Write the page's skeleton with short placeholder text first, read the budgets, then write
the words.

Write the deck as one JSON (`{"slides": [...]}`, each slide `id`, `layout`, `spec`,
optional `charts`, `styling`, `annotations`, `notes`, and `"title": {"register": ...}`;
optional deck-level `firm_chrome`). A node in the spec tree carries its id, kind, weight
and its text or table; a chart's own keys (type, series, axes, plot_area, legend) go in
`slide.charts[<its id>]`, and a key on a node that nothing reads is refused by name.
Per-table emphasis (the subject row shaded, the row labels bold) is the table's
`emphasis` list of roles, never a literal. Roles only; a literal colour, size, font or
coordinate is refused. Grammar, limits and
conventions: [references/page-specs.md](references/page-specs.md). How to draw the form
your brief chose, technique by technique (not a menu of forms):
[references/chart-recipes.md](references/chart-recipes.md). Table spec keys:
[references/tables.md](references/tables.md). Logos, icons and the user's pictures
(a file, a logo taken from the reference with `images.py extract`, or an icon you write
as a small SVG in colour roles), in boxes sized by roles: page-specs.md, "Pictures". A
line and columns on two axes, data rows or logos aligned under a chart's categories:
chart-recipes.md, "Two value axes" and "Rows aligned to categories". A component the template never showed:
[references/components.md](references/components.md). Building a company page library:
[references/page-library.md](references/page-library.md).

### 7. Build

```bash
python3 scripts/build_deck.py "$DECK_WORK/deck/deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
        -o "$DECK_WORK/out/deck.pptx" --reference "$REF" --renders "$DECK_WORK/out/renders" --plan "$DECK_WORK/plan.json" \
        [--chrome draw] [--brief "$DECK_WORK/brief.txt" ...] [--computed "$DECK_WORK/figures.txt"]
```

With no reference, leave `--reference` out (the build refuses one beside a blank guide).
Give each build its own folder (`out/b1/`, `out/b2/`, ...) so a refused build never moves a
good one aside. A deck built with `--plan` holds the whole plan or one run of consecutive planned pages
(while you work on one page, a deck of that one slide); each slide's id is its page id.
Exit 0 means every page fit and the package is valid. The command prints a brief (the
verdict, every path, each page's first problems, one line per gate); the whole report is
`$DECK_WORK/out/deck.build.json`. Only a passing build writes `deck.pptx` and the renders
at the paths you gave; a refused build writes `deck.refused.pptx` and `renders.refused`
beside them for diagnosis, and moves an earlier build's files there to `.stale`, so nothing
at the asked-for paths is ever older than the spec. A refusal before solving (a malformed
spec, exit 1 with one line) writes only the report and does not count against the build
cap. Read the report: refusals first, then `chart_defaults_taken` (write each choice into the spec until only
what you meant remains), `title`, `density`, `contrast`, `repetition`, `leakage`, `judge`. An
unfittable page: re-arrange, cut words, or split at a declared boundary; never drop
content. Every field: [references/build-report.md](references/build-report.md).

### 8. Review every render

Open every page image in `$DECK_WORK/out/renders/` at full size (with a reference, beside
its pages nearest in intent). Then check each exhibit against its brief: does the reader
see what `reader_must_see` says, in three seconds, without arithmetic? Is the comparison
the brief names drawn, the value compared against on the exhibit? Are the marks where the
claim lives, and does each say what it marks? Does the text add what the exhibit cannot?
A render that fails its brief is a finding even when every gate passed. Write located
findings as a senior reviewer would (element id, what is wrong, the change; never a
score), fix the specs, rebuild. Cap: 8 builds per 5-page section. Keep every build; hand
over the best one by refusals, then open findings, then likeness to the reference's look
(with none, to the look you chose), not the last one. What to look for and in what order:
[references/review.md](references/review.md).

### 9. Annotation

For each exhibit, take the `marks` line of its brief. Can the claim be found on the
exhibit? With a reference, its records of what it marks (`exhibit_habits.records[].marks`
and the marks its files draw) are evidence beside your choice (7 of 291 coded charts are
bare). The means are open: `annotations` on the slide (reference lines, outline boxes,
bands, brackets, callouts, badges, rows of figures or logos under the categories, or a
`mark` in any OOXML preset or line end, at data positions or on any element's box), or
native emphasis (a point fill, an emphasis row). Nothing annotates by itself; the build
refuses an annotation that collides or covers the host's text. Ink a mark in
`color.emphasis`, not `color.negative` (a bad value); with none, the rule or ink role.

A mark says what it means. A ring, box, band, line or bracket either carries a `label`,
or names under `explained_by` what explains it: words on the page that name what it
encloses (`{"text": id, "quote": ...}`), a labelled callout on the same anchor, a legend
entry in its ink, a footnote marker it shares with a note, or a page of the reference whose
file draws a mark of the same geometry with no text of its own (`reference_precedent`).
Otherwise the build warns `annotation unexplained`, with the reference's own count of such
marks (or "no reference"), and you answer it in the report: a red circle with no word
beside it read to a blind rater as a model's attempt to annotate. A named explanation that
is not there is refused. Kinds, anchors and four worked exhibits:
[references/chart-recipes.md](references/chart-recipes.md) ("Marks at data positions").

Source lines: with a reference, a data page without one warns where at least half of the
reference's data pages carry one (or the habit is unmeasured), quoting its count; add one
or say why not. A page with one is never a departure; with no reference it is your call.
An illustrative-figures note goes where the deck puts notes; say where in the report.

### 10. Variety report

From `repetition` in the build report: realised composition V, exhibit structure V and
exhibit kinds V, with the reference's beside them (`against_reference`; "no reference"
with none), runs over the reference's longest, `warnings`, and every page in
`plan.pages_differing_from_plan`. All are read from what was built, never from names:
structure is each page's exhibits as the written file states them (chart plot types and
series counts, tables, pictures, a structure built from shapes, panels; a banner, frame or
callout beside a native exhibit is decoration and counts as neither), kinds the same with
any chart a chart, each held against the same reading of the reference's own pages. Each
page's briefs are held to its file (`slides[].briefs`): an exhibit on a page whose plan
briefs none is refused. Explain each warning and each disagreement in one line: a
deliberate parallel, or a fix you made. Composition V cannot see a table beside a chart
mirrored; kinds V can, even when each page's chart plots something else.

### 11. Validate and report

```bash
python3 scripts/pptx_tools.py validate "$DECK_WORK/out/deck.pptx" --render
python3 scripts/pptx_tools.py validate "$DECK_WORK/out/deck.pptx" --emit --guide "$DECK_WORK/ref/guide.json"
```

Read `leakage` in the build report: every name, figure and phrase of the past deck found
in the new deck, with the reference's chrome left out, ranked by rarity. `pages` lists the
distinctive ones (on no public deck of another firm), rarest first: remove each, or
confirm the user supplied it (pass the brief and data as text with `--brief` and their
words are not listed; pass the output of your own arithmetic with `--computed` and a past
figure it also produces is listed under `declared_computed` instead). `low_findings` lists terms of the trade (senior notes, debt /
EBITDA), round figures and years once each: keep every one your own data or brief
produces, and check any figure among them you did not compute. The firm's own name in
the chrome is not leakage; it is the `firm_chrome` choice in step 3. With no reference
there is no past deck, and the report says so.

Read `judge.components` in the build report: a deck nearer another panel deck than its
reference shows which components carry the distance. Fix what it names, or say in the
report why it stands; a deck filed under its reference is not thereby finished either.
With no reference the judge reports "no reference": there is no look to measure against.

The final report states: template and layouts chosen and why; what was measured, what you
completed by judgement (with confidence) or, with no reference, chose (with why), what was
substituted (fonts), and what the user must supply (placeholder figures, logos); every
page's status and scale; open findings from the last review; the variety report; each
departure from a reference habit in one line; the leakage report; the firm chrome kept,
replaced or dropped; the judge's verdict, labelled as necessary and not sufficient; any
conflict between sources (template against brand guideline) and how you resolved it,
never silently.

## Designing a page

High freedom: many designs are valid. Give yourself the context, then reason; no rule here
fixes a design.

Context for every page:
- the guide (`description`, `derivation_rules`, roles, `titles`, `exhibit_habits`,
  `variety`, density bands) and your plan's line for the page;
- the data, with every stated figure computed;
- with a reference, its own pages nearest this intent (renders, gallery exemplars, digest
  records) for their look, and library picks with their `why` and `ask` lines.

Questions to answer before writing the spec:
- What should the reader leave with: the page's message, or what they look up on a
  reference page? Which slot carries it (the corpus found titles, lead-ins, sidebars,
  takeaway bands, kickers, units lines, row labels; with a reference,
  `guide.titles.claims_elsewhere` shows where it states claims), or does this page need
  somewhere else?
- Is this a page of argument or of reference?
- Does each block's size say how much it matters? Where does the eye finish?
- If blocks are co-equal: are they a comparison (pages and panels meant to be compared
  share one scale and one order) or unrelated facts?
- What will the reader do with this content, and what form serves that?
- What is the data's shape, in its own terms? Which forms could show the comparison the
  reader must make, and what does each ask of the reader's eye? How does the look (the
  reference's, or the one you chose) draw the form you pick, with its roles?
- Where on the exhibit does the claim live, and how will you mark such a place? How much
  does it label, does it use legends and gridlines?
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
  figure is a named placeholder.
- Nothing dropped to make a page fit; unfittable is a report.
- Never below `max(floor_pt, absolute_floor_pt)`; observed guide values are never
  overwritten by completion.
- Contrast under 3:1 refuses the page, and so does a bridge that does not tie; a table's
  totals row that does not tie out is listed first in the problems.
- No content from a past deck that the user did not supply for this deck (the build's
  `leakage` report lists every candidate); company files, guides, digests and libraries
  stay in `$DECK_WORK`, outside this skill.

## Files

| Path | Run or read |
|---|---|
| `scripts/preflight.py` | run once per machine: packages, LibreOffice, poppler, fontconfig, HarfBuzz, faces |
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
| `scripts/component.py`, `scripts/component_api.py` | run: check and admit a component; measure text by hand |
| `scripts/emit_pptx.py`, `textfit.py`, `chart_geometry.py`, `annotate.py`, `fingerprint.py`, `cli.py` | called by the build and the commands |
| [references/editing.md](references/editing.md) | read to extend, reorder or edit an existing deck |
| [references/gotchas.md](references/gotchas.md) | read when a render and PowerPoint disagree: measured OOXML and renderer facts |
| `references/page_craft_vocabulary.json` | data: the title vocabulary (register, companions); no exhibit is read in a list |
| `components/` | admitted components and the contract (`components/README.md`) |
| `examples/` | worked deck specs, plans, completions, digests (with a reference and with none), and `proofs/` build reports |
| `evals/` | end-to-end scenarios and the blind-round protocol |

Requirements: Python 3.11+, lxml, Pillow, python-pptx, pdfplumber; LibreOffice, poppler
and fontconfig; uharfbuzz when available (the report names the ruler that ran).
`scripts/preflight.py` checks them all and prints the install commands. The judge's panel
of public decks is fetched once with `refs/fetch.sh` (into the git-ignored `refs/files`).
