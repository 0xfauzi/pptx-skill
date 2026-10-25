# Reading the build report

## Contents
- The command and the judge's panel
- Fit and scale
- Unfittable pages: your moves, in order
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
  [--chrome draw] [--house-deck other.guide.json ...] [--brief "$DECK_WORK/brief.txt" ...]
```

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
reported as the same house. The panel is not yours to choose.

## Fit and scale

`status: fit` with `scale` and `violations: []` fits at that type scale. Below 1.0 the
solver stepped the whole ladder down toward the floor; say so in the report below 0.9.

## Unfittable pages: your moves, in order

`status: unfittable` names the smallest admitted scale, every violation, and for each
table `rows_to_fit_slide`, the body-row count at which to split (`layout.py capacity`
prints the same count as `rows_to_fit`, and the causes in words, before you build). A title that needs two
lines is named first, because every other violation on that page follows from it. Nothing
is dropped. Your moves: re-arrange (two columns instead of one, a table beside the chart
instead of below, a compact component variant), cut words, split at a declared boundary
(the fitting rows become page one, the rest page two under the guide's continuation
convention). Then build again.

## Refusals and warnings (`problems`)

Listed per page before the figures. A refusal turns a fit page `unfittable` with the
refusal as `reason`; `solver_status` keeps the geometry verdict. Refusals: `contrast`;
`bridge does not tie` (a chart declaring `bridge` whose totals or spans do not tie to its
deltas); `chart label breaks mid-word`; `emitted text overflows`; `annotation refused`,
`annotation collides`, `annotation covers chart text`, `annotation render check failed`;
`font refused`; `no source line` where the house carries source lines as a rule (below).
Warnings never refuse: `tieout` (a totals cell that does not equal its column), `no
source line` elsewhere, and `plan figure not on the page` (a figure the plan's message
for the page states that the page does not carry: the plan was written before the
numbers moved, or the page lost its claim).

`no source line` is a page with a table or chart and no `type.source_line` or
`type.footnote` paragraph. The house's habit is the digest's count of data pages that
carry one (`exhibit_habits.source_lines`). Where at least 80% of three or more house data
pages carry one, the page is refused; otherwise it warns, with the house's count in the
detail (keybank: 1 of 5, so it warns). A guide whose digest answered no `source_line`
warns and says the habit is not measured. The 80% line is unmeasured.

## What the file is written at

The file is written at the solved sizes: at scale 0.89 a 12pt cell is written at 10.5pt
with the scaled pitch, spacing, tracking and inset. After the emit the build reads the file
back and measures every text element and table against its solved box; any shape that
outgrows it refuses the page as `emitted text overflows`. Line breaks are written as the
solver measured them, so PowerPoint cannot re-break the text.

## Contrast

Every text run, table row class, chart text and chrome text line is scored (WCAG 2.2)
against the fill drawn behind it. Below 3.0:1 refuses; below AA (4.5:1, or 3.0:1 at 18pt
or 14pt bold) warns. House precedent first: a pair the reference itself draws (same ink
over same backing, read from `--reference`) at that size or smaller is filed under
`house_precedent`, neither refused nor warned (a consulting house sets its titles in a
green at 2.51:1 on white on 23 pages; its decks keep the green). With no `--reference`
nothing claims precedent. `undecidable` lists text over images; `unbound` lists runs with
no ink role. The fix is a role change; nothing in the emitter corrects an ink.

## Titles, register and density

- `title`: characters, words and solved lines against the house's median, p90 and max
  (above the max warns), and the register the slide states against the house's counts (a
  register on under 10% of the house's titles warns; that line is unmeasured).
- `register`: element kind counts, decoration count and container ratio against the
  reference's bands; a native table or chart against a band of 0 to 0 reads `no evidence`
  (a house that pastes exhibits as pictures).
- `density`: words, elements and covered area against the reference's bands (`below`,
  `in band`, `above`, or `no evidence`). Covered area is ink: each measured text line at
  its width and pitch, each table at its fitted rows, charts, pictures and fills at their
  boxes, unioned. A text box stretched past its last line does not count. The house's band
  unions its shape boxes, so it is the more generous of the two. `text_boxes_mostly_empty`
  lists every text element whose lines fill under 60% of its box, with where the text ends
  and where the box ends (a reading aid, unmeasured; never a gate). A keybank page whose
  commentary column ended at 2.72 in of a box running to 6.53 in read 0.72 covered by
  boxes and 0.48 by ink, and is listed there: re-weight the column, or add a point.

## Repetition (the section's variety)

Each solved page's content (the page frame left out: `frame_left_out`) gets a realised
composition by the extractor's own clustering, and `measure` is plan.py's: composition V,
class V (the exhibit classes the page realises), distinct per page, runs. `against_house`
sets each against the house (pooled with `--house-deck`), `runs_over_reference` lists runs
longer than the house's longest, and `warnings` lists every figure below the house's 10th
percentile; a composition V warning names each repeat the plan declared a deliberate
parallel, with its reason, and V over the other pairs. With `--plan`, `plan.check` repeats
the plan check, `realised_by_page` sets each page's planned composition beside its
realised one (realised names, b1, b2, ..., are this build's own clusters: two pages share
one when they share an arrangement), and `pages_differing_from_plan` flags each page where
plan and build disagree. A plan the check
refuses is not built.

## Leakage

`leakage` lists, per page, every name (two or more capitalised words), figure (a currency
figure, a percent of two or more digits, a decimal, or three or more digits) and five-word phrase of the new deck that a past deck also
carries, with the past page it is on. The past decks are `--reference` and each
`--house-deck`'s own file (found by its recorded sha256; one not found is named under
`unread`, never taken as clean). Left out: the house's chrome (text a past deck repeats on
half its pages or more, and the template's own text), and every word of a `--brief` file
(the user's brief and data, as text). Pictures are compared by hash, the template's own
excepted.

Each finding is ranked by rarity against the public decks of other houses in
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
- `tieouts`: for each table with `totals_last_row`, each numeric column's body sum against
  its totals cell at the cell's decimals; median, average and mean rows are skipped.
- `chart_defaults_taken`: every chart choice the spec left out, with the value the file
  got. None of these is the house's style: write each into the spec until the list holds
  only what you meant.
- `chart_label_breaks`: words a renderer must break between characters at the chart
  text's size (category labels against their slot, centred data labels against the bar).
- `component_notes`: a component admitted against another guide; re-run its check.

## The judge

`judge.filed_under_reference` is four gates: nearest the reference among the panel's
houses, inside the reference's own spread (`house_spread.p90`), layout clean (`overlap`
and `overflow` each below 0.2 of their span; `overflow_where` names each shape), and every
page fit with a valid package. `judge.components` names what is off (`size_hist`,
`fills`, `text_colors`, `margins`, `kinds`). `judge.cannot_judge` replaces the distances
when the reference has no type evidence (a scan): the verdict is yours, from the renders.
The judge does not track a reader's eye: in a blind round, decks filed at 0.068 and 0.085
were caught on every page, and one the judge could not file fooled the rater 4 of 5
times. A filed deck is necessary, not sufficient.

## Density is a loop

Add content, build, read the report. When a page fits with room at the upper density
band, add the next item. When it does not fit at the floor, split or re-arrange.
