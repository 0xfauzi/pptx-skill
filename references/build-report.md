# Reading the build report

## Contents
- The command and the judge's panel
- Fit and scale
- Unfittable pages: what moves a page
- Refusals and warnings (`problems`)
- What the file is written at
- Contrast
- Titles, register and density
- Repetition (the section's variety)
- Leakage
- Firm chrome
- Position drift, tie-outs, chart defaults, label breaks
- The judge
- Density is a loop

## The command and the judge's panel

```bash
python3 scripts/build_deck.py "$DECK_WORK/deck/deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
  -o "$DECK_WORK/out/deck.pptx" --reference "$REF" --renders "$DECK_WORK/out/renders" --plan "$DECK_WORK/plan.json" \
  [--chrome draw] [--brief "$DECK_WORK/brief.txt" ...] \
  [--computed "$DECK_WORK/figures.txt" ...]
```

Give each build its own output folder (`out/b1/deck.pptx`, `out/b2/deck.pptx`, ...): a
refused build moves an earlier build's files at the same paths aside to `.stale`, so with
one folder the best build has to be rebuilt to be handed over.

With `--plan`, the deck holds the whole plan or one run of consecutive planned pages, each
slide's id its page id: to build one page while you work on it, give a deck of that one
slide. Any other set is refused, naming the plan's ids. The plan check covers the whole
plan; the realised variety covers only the pages built (`repetition.plan.check.subset`).

One command solves every page with measured fit, emits on the template, reads the file
back, validates, renders, and judges. It prints a brief (the verdict, the report's path,
the deck and renders paths, each page's status with its first problems, one line each for
variety, leakage, firm chrome and the judge) and writes the whole report as
`deck.build.json` beside the deck; exit 0 means every page fit and the package is valid.

`outputs` says where the files are. Only a passing build writes the deck and renders at
the paths given (they are made at staging paths and moved there). A refused build writes
`<stem>.refused.pptx` and `<renders>.refused`, and moves an earlier build's deck and
renders at the asked-for paths to `<stem>.stale.pptx` and `<renders>.stale`
(`outputs.moved_aside`), so a file at the asked-for path is never older than the spec. A
refusal before solving (a malformed spec) writes a report holding only `outputs.verdict:
"refused before building"` and the refusal; the next passing build removes the `.refused`
files. Leave `--others` alone: the
judge's panel is every deck under `refs/files` (fetch once with `refs/fetch.sh`), the
reference's twin removed by hash, scans skipped, decks inside the reference's own spread
reported as the same style (`same_style_on_panel`). The panel is not yours to choose.

With no reference (a guide from `extract_style.py --blank`, built without `--reference`),
every hard limit below runs as written, and every comparison with a reference reads
"no reference": `title.length` and `title.register`, `repetition.against_reference` and
`runs_over_reference`, `source_lines.reference`, `contrast.precedent_source`,
`chrome.reference`, `leakage` (no past deck) and `judge`. Nothing is warned or scored in
their place, and no corpus figure stands in for a reference.

## Fit and scale

`status: fit` with `scale` and `violations: []` fits at that type scale. Below 1.0 the
solver stepped the whole ladder down toward the floor; say so in the report below 0.9.
When no scale clears the floors, the message names each role and the floor it would
cross. Each page's `tables` carries the same keys whether or not it fit: `rows`,
`height_emu`, `column_widths_emu`, `fitting_row_prefix` (every body row on a page that fit
clean), `width_deficit_emu` and `column_deficits_emu`.

The brief's `ruler:` line names what measured the text: `harfbuzz` or `pillow`, pinned by
the guide (`measurement.ruler`, written by the extractor) or, for a guide that predates
the pin, this machine's default, which changes when `uharfbuzz` is installed or removed
and moves every fit budget with it. A pinned ruler that is not installed is refused, never
replaced. Report the ruler with any fit result you compare across builds.

## Unfittable pages: what moves a page

`status: unfittable` names the smallest admitted scale, every violation, and for each
table `rows_to_fit_slide`, the body-row count at which to split (`layout.py capacity`
prints the same count as `rows_to_fit`, and the causes in words, before you build). A
title that needs more lines than the band above the top rule holds does not fit, and is
named first, with the lines the band holds, because every other violation on that page
follows from it: shorten it, or move a clause to where the reference states claims (the reason
names the places, from the guide's `claims_elsewhere`). Nothing is dropped. Moves, for
instance, in no order: re-arrange (two columns instead of one, a table beside the chart
instead of below, a compact component variant), cut words, split at a declared boundary
(the fitting rows become page one, the rest page two under the reference's continuation, as
its pages show it). Then build again.

## Refusals and warnings (`problems`)

Listed per page before the figures. A refusal turns a fit page `unfittable` with the
refusal as `reason`; `solver_status` keeps the geometry verdict. Refusals: `contrast`;
`bridge does not tie` (a chart declaring `bridge` whose totals or spans do not tie to its
deltas; `slides[].bridge_ties` names every declared bridge with "ties: ..." or its failures,
or says no chart on the page declares one; a zero step that draws no bar ties, and is
a warning, `bridge zero step unlabelled`, only when no series labels it); `chart label breaks mid-word`; `emitted text overflows`;
`renderer divergence: text wrapped`; `renderer divergence: table cell`; `renderer divergence: chart text`;
`chart labels taller than their band`; `chart label covered`; `annotation refused`,
`annotation explanation not found` (what a mark's `explained_by` names is not there:
chart-recipes.md, "A mark says what it means"), `annotation collides`,
`annotation covers chart text`, `annotation render check failed`;
`picture not drawn as written`, `picture too small to check`, `picture render check failed`;
`font refused`; `exhibit without a brief` (with `--plan`: the written page holds a chart, a table, a
picture or a structure built from shapes, and its plan page briefs none; `slides[].briefs`
gives both counts). Warnings never refuse: `annotation unexplained` (a ring, box, band,
line, bracket or mark with no label and no `explained_by`, with the reference's own count of
such marks with and without words: answer it in the report); `briefs differ from the file's exhibits` (the
plan's brief count and the written page's exhibit count differ; say which brief covers
which exhibit), `tieout` (a totals cell that does not equal its column), `no
source line` (below), `renderer divergence: category interval` (a `label_interval` or
`tick_interval` above 1, which LibreOffice ignores: chart-recipes.md), `renderer-unmeasured preset` (a shape in a preset no render here has
shown: look at it, and open the deck in PowerPoint before release), `type size off the
reference's ladder` (a role the completion wrote off the reference's levels, with the levels, the
reason given and the judge's `size_hist` distance), and `plan figure not on the page` (a
figure the plan's message for the page states that the page does not carry: the plan was
written before the numbers moved, or the page lost its claim). Answer every warning in the
report: what you kept and why, or what you changed.

A warning you mean is answered once, in the deck JSON, so it stops reading as open on every
build: `"answered": [{"kind": "annotation unexplained", "why": "the trigger line is named
in the commentary beside the chart"}]` on the slide (add `"detail": "<words of its
detail>"` when the page has two warnings of one kind). The warning stays in `problems` with
`answered` set to your reason, and the brief lists it as answered, not open; carry the
reason into the final report. A refusal is never answered (`answer to a refusal`
refuses), and an answer that matches no warning on the page warns `answer names no
warning`: the page changed and the answer is stale.

The reference's source-line habit is the digest's count of data pages that carry a source
or note line (`exhibit_habits.source_lines`), over three or more data pages: `most` where
at least half do, `few` below (the half is a definition of the reference's majority, not a
measured line). `no source line` is a data page (a table or chart) with no
`type.source_line` or `type.footnote` paragraph, warned with the reference's count ("the reference
sources 41 of 44 data pages; this page has none") where the habit is `most`; where it is
`few`, a page without one does what most of the reference's pages do and nothing is said. A
page WITH one is never a problem: citing a source is never wrong. A guide whose digest
answered no `source_line`, or fewer than three data pages, is `unmeasured`: a data page
without one warns, never read as "the reference carries none". Nothing about source lines
refuses: the count is evidence beside the choice, answered in the report. The deck-level
`source_lines` sets the reference's count beside the deck's pages with one, and the brief
prints both. In round 2 the old rule (warn on every data page without one, whatever the
reference did) told agents on keybank and netflix, references with 1 of 5 and 1 of 8, to add
source lines to every page.

## What the file is written at

The file is written at the solved sizes: at scale 0.89 a 12pt cell is written at 10.5pt
with the scaled pitch, spacing, tracking and inset. After the emit the build reads the file
back and measures every text element and table against its solved box; any shape that
outgrows it refuses the page as `emitted text overflows`. Line breaks are written as the
solver measured them, so PowerPoint cannot re-break the text.

The render is then read for the lines each solved text box was drawn in (`slides[].drawn_lines`:
per box `{"written", "drawn"}`, or why it was not found: its words are not one run in the
render, or are drawn more than once). A box drawn in more lines than written refuses the
page as `renderer divergence: text wrapped`, naming the lines as drawn: the renderer set a
measured line wider than the ruler did, and the box runs below its measured height. Shorten
the text or widen the box so the line that wrapped has room. A table is read cell by
cell (`drawn_lines.<table>`: cells, drawn as written, not found), from the render's words
in each column between the table's top and bottom: a cell drawn in more lines than the
fitter measured is `renderer divergence: text wrapped`, and a cell whose characters are
not there in order refuses the page as `renderer divergence: table cell`. Without a render
(`--no-render`) nothing is checked, and `drawn_lines` says why.

Each chart's text is read the same way (`slides[].chart_text_drawn`: per chart, how many of
its category and data labels the render draws as written). The words the file writes are
found in the render's lines inside the chart's frame, and a turned label (rotation_deg, or
one LibreOffice turns to fit) among the render's turned runs, read whole; a label the render does not hold
refuses the page as `renderer divergence: chart text` (LibreOffice drops category labels
that do not fit their band, a dated axis included: say which are drawn with
`label_interval`, and breaks a label it squeezes), and so does a data label of
several words set on its bar's fill and drawn on more than one line (LibreOffice wrapped
it in its bar). A label that wraps in open space (beside a scatter or line point, or a
bar's `outside_end`) is a design: it is counted as wrapped and held to the crossing checks. Each says
what to change. Before the render, a horizontal bar chart whose category band is shorter
than one line of its labels is refused as `chart labels taller than their band`, with the
plot height that holds every name, and a centred column label wider than its bar is warned
as `chart label wider than its bar`. A data label the render draws under a line of the
chart, or over another data label, refuses the page as `chart label covered`; before the
render, an `above` or `below` label on a line drawn without markers is placed where
LibreOffice sets it (3pt off its point, measured) and warned under the same kind when a
line would cross it.

## Contrast

Every text run, table row class, chart text and chrome text line is scored (WCAG 2.2)
against the fill drawn behind it. Below 3.0:1 refuses; below AA (4.5:1, or 3.0:1 at 18pt
or 14pt bold) warns. Reference precedent first: a pair the reference itself draws (same ink
over same backing, read from `--reference`) at that size or smaller is filed under
`reference_precedent`, neither refused nor warned (a consulting reference sets its titles in a
green at 2.51:1 on white on 23 pages; its decks keep the green). On a PDF reference a
pair counts only where the page's render draws it so: a PDF keeps no draw order, so the
backing is inferred, and a gradient or a picture under the words is missed (bcg-nycha's
white words on a green gradient read as white on white). A pair the render does not
confirm, and words drawn in their backing's own colour, are no precedent; the finding
names why under `no_precedent`. A run is scored where its measured lines draw (their
height, width and alignment), not across its whole box. With no `--reference` nothing
claims precedent; with no reference, `precedent_source` reads "no reference". `undecidable` lists text over images; `unbound` lists runs with
no ink role. A column's label taller than its segment is scored against the plot too and
carries `overflows_bar_at_points` (chart-recipes.md). The fix is a role change; nothing in
the emitter corrects an ink.

## Titles, register and density

- `title`: characters, words and solved lines against the reference's median, p90 and max
  (above the max warns: a departure to answer in one line), and the register the slide states (`title.register`, in words,
  as the plan states it). A register naming a term the reference's titles are coded in (by
  slug or label: "Claim sentences" reads as claim) is set against the reference's counts (one
  on under 10% of the reference's titles warns; that line is unmeasured); any other words are
  reported as "no count", with the counts beside them. Only a register that is not
  words (a number, empty, "TBD") is refused.
- `register`: element kind counts, decoration count and container ratio against the
  reference's bands; a native table or chart against a band of 0 to 0 reads `no evidence`
  (a reference that pastes exhibits as pictures).
- `density`: words, elements and covered area against the reference's bands (`below`,
  `in band`, `above`, or `no evidence`). Covered area is ink: each measured text line at
  its width and pitch, each table at its fitted rows, charts, pictures and fills at their
  boxes, unioned. A text box stretched past its last line does not count. The reference's band
  unions its shape boxes, so it is the more generous of the two. `text_boxes_mostly_empty`
  lists every text element whose lines fill under 60% of its box, with where the text ends
  and where the box ends (a reading aid, unmeasured; never a gate). A keybank page whose
  commentary column ended at 2.72 in of a box running to 6.53 in read 0.72 covered by
  boxes and 0.48 by ink, and is listed there: re-weight the column, or add a point.

## Repetition (the section's variety)

Each solved page's content (the page frame left out: `frame_left_out`) gets a realised
composition by the extractor's own clustering and an exhibit structure read back from the
written file by the reader that read the reference's pages (`ooxml.exhibit_facts`: native
charts by plot type, bar direction, grouping and series count, tables, pictures, drawn
shapes, panels 1, 2 or 3+; the drawn chrome left out; under `realised[].structure`), and
`measure` is plan.py's: composition V, structure V, kinds V (the structure with any chart
a chart, under `realised[].kinds`), distinct per page, runs. Nobody names a structure, so
renaming an exhibit cannot move it. `against_reference`
sets each beside the reference's own figure (`reference_V`; the distinct-per-page window at
its 10th percentile), `runs_over_reference` lists runs longer than the reference's longest,
and `warnings` lists every figure below the reference's, each a departure to answer in one
line; a composition V warning names each repeat the plan declared a deliberate
parallel, with its reason, and V over the other pairs. With `--plan`, `plan.check` repeats
the plan check, `realised_by_page` sets each page's planned composition beside its
realised one (realised names, b1, b2, ..., are this build's own clusters: two pages share
one when they share an arrangement), and `pages_differing_from_plan` flags each page where
plan and build disagree on whether neighbours repeat. Whether a page realises the
archetype it names is not measured (`pages_against_their_archetype` says so): an empty
`pages_differing_from_plan` does not mean each page is the archetype the plan named, so
compare the render with that archetype's slides and correct `plan.json`. A plan the check
refuses is not built. A pair whose similarity lies within 0.1 of the 0.5 line (unmeasured)
is marked `borderline` under `pairs`, and a flag or a composition V warning that rests on
one says so: one lead-in wrapping to a second line once moved a keybank pair from 0.434 to
0.543. Change the arrangement, not the words, when two pages must read as different.

## Leakage

`leakage` lists, per page, every name (two or more capitalised words), figure (a currency
figure, a percent of two or more digits, a decimal, or three or more digits) and five-word phrase of the new deck that a past deck also
carries, with the past page it is on. The past deck is `--reference`; with no reference
there is none, and `leakage.verdict` says so. Left out: the reference's chrome (text a past deck repeats on
half its pages or more, and the template's own text), and every word of a `--brief` file
(the user's brief and data, as text), and the text of the chrome the build drew (on a
raster reference the past deck's copy of a footer is OCR text that never reads as chrome
there). Pictures are compared by hash, the template's own excepted.

`--computed FILE` takes the figures your own arithmetic produced from the user's data, as
text (the output of the script that computes and asserts every stated figure). A past
deck's figure that also appears there is listed once under `declared_computed`, with the
past page it coincides with, instead of as distinctive: a computed 1.6% that a reference
also prints is a coincidence you can name. A figure matches on its value and its unit
(thousands commas and trailing zeros aside): write each figure with the unit the page shows,
`36%` and not a bare `36`, since a count of 36 in the file does not excuse a 36% on the page.
Only figures: a name or a phrase in that file is still reported. Never put a figure you did
not compute in it.

Each finding is ranked by rarity against the public decks of other firms in
`refs/files` (`rarity_basis`; the past decks and their twins left out). Low: a name or
phrase whose words run in that order in such a deck, a name every word of which they use
(senior notes, debt / EBITDA: products and ratios), a round figure (two significant
digits at most, the second 0 or 5: 10%, $1,000, 4.0x) and a year. These are listed once
each under `low_findings`, with why: keep every one your own data or brief produces, and
check any figure among them you did not compute. Everything else is distinctive and
listed per page under `pages`, rarest first (most words no public deck uses): remove each,
or confirm the user supplied it for this deck, in the final report. `what_to_do` says the
same in the report. `verdict` is `clean`, `no distinctive carry-over` (low findings only)
or `possible carry-over`. The thresholds are unmeasured. The
same report runs on any deck: `python3 scripts/leakage.py DECK.pptx --past PAST.pptx
[--brief brief.txt] [--template tpl.pptx]`.

## Firm chrome

`chrome.firm` lists every chrome entry a generated page carries that can name the
reference's firm (on-page text with words in it, page numbers excluded, and pictures),
with the `decision` taken (`keep`, `drop`, `replace with ...`) and `chosen`: false when
the deck's `firm_chrome` did not name it and the default, keep, was taken. A deck for
another firm or a fictional one chooses for each (SKILL.md step 3). Inherited chrome is
changed in this deck's own copy of the master; an entry the template does not draw where
the guide says is refused by name.

## Position drift, tie-outs, chart defaults, label breaks

- `position_drift`: one element (same id and kind, left edge and width within a spacing
  step) on several pages whose top moves by more than that step.
- `tieouts`: for each table with `totals_last_row`, each numeric column's body against
  its totals cell at the cell's decimals, by the column's `total` (`sum`, the default and
  reported as such, or `mean`; `none` is skipped and says so); a totals row headed median,
  average or mean is skipped.
- `table_defaults_taken`: every table choice neither the spec nor the guide states (an
  emphasis group's weight, a totals row's bold, the banding phase, the header's weight,
  the cell padding, a column's alignment), with the value written (tables.md).
- `chart_defaults_taken`: every chart choice the spec left out, with the value the file
  got.
- `layout_defaults_taken`: every layout choice a region left out (a flex region's align,
  stretch, and justify, start; no padding; children with no weight, weight 1 in the split
  of free space), and the bullet indents a page gets when the reference shows no bullets
  (with the question whether the text needs bullets at all).
- `emit_defaults_taken`: every other value the file got that neither the spec nor the
  guide states, per element: a bullet glyph or indent the guide names none for, an outline
  or rule width (0.75pt), a rule's colour, a chrome entry's face or size.
- None of the defaults-taken lists is the reference's style: write each choice into the spec
  until the lists hold only what you meant, or name what is left in the report as
  intended. The brief prints each page's counts.
- With no reference, a default that is a look (a face, size, weight, alignment, colour,
  fill, stroke or bar geometry falling to the blank template's stock Office theme, a
  renderer's own style or a constant in the emitter) is refused before building, by
  element and choice: "with no reference nothing is drawn in a look nobody chose". The
  lists then hold only what draws nothing or is placed from the data (no axis title, an
  automatic plot area, no padding, OOXML's own cell inset).
- `layout_depth`: the page tree's deepest chain of ids and its depth (the runaway bound,
  12, is a guard against a looping generator, never a design limit).
- `chart_label_breaks`: words a renderer must break between characters at the chart
  text's size (category labels against their slot, centred data labels against a column's
  width), and under `spills` each horizontal bar's label wider than its bar, warned as
  "chart label wider than its bar".
- `component_notes`: what each component chose and why (its variant), each role or
  constant it left at its default, each role it computed from the guide (a lead's or a
  marker's ink by contrast), and a component admitted against another guide (re-run its
  check). The defaults are choices like any other: set them through the component's
  `data["roles"]` or `data["params"]` where the reference does otherwise.
- `pictures`: per picture on the page (a `slide.images` entry or a `category_row` cell),
  the box it was drawn in on the render (`box_px`), `differ_share` (the share of that
  box's pixels with no pixel of the picture as written within one pixel and 64 levels of
  it) and `status`; above 5% refuses the page as `picture not drawn as written`, and a
  picture drawn under 4 px on a side as `picture too small to check`. With
  `--no-render` it says not checked.
- `image_defaults_taken`: per picture, every choice left out (align, valign, an icon's
  stroke caps and joins, fill rule) with the value written.

## The judge

`judge.filed_under_reference` is four gates: nearest the reference among the panel's
firms, inside the reference's own spread (`reference_spread.p90`), layout clean (`overlap`
and `overflow` each below 0.2 of their span; `overflow_where` names each shape), and every
page fit with a valid package. `judge.components` names what is off (`size_hist`,
`fills`, `text_colors`, `margins`, `kinds`). `judge.cannot_judge` replaces the distances
when the reference has no type evidence (a scan): the verdict is yours, from the renders.
The judge does not track a reader's eye: in a blind round, decks filed at 0.068 and 0.085
were caught on every page, and one the judge could not file fooled the rater 4 of 5
times. A filed deck is necessary, not sufficient.

## Density is a loop

Add content, build, read the report. `density` says where the page sits in the reference's
own band (words, elements, covered area: its 10th to 90th percentile), as evidence, not a
target. A page below the band with room left is one to ask about: is something the
reader needs missing? Measured on hand-built specimen pages against 96 corpus pages (median
ink coverage 0.21 to 0.25 against 0.576, TARGET_SPEC.md 14.3), what closed the gap was
adding the exhibits a page lacked, not enlarging the ones it had. When a page does not fit
at the floor, split or re-arrange.
