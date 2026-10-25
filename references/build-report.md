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
- Position drift, tie-outs, chart defaults, label breaks
- The judge
- Density is a loop

## The command and the judge's panel

```bash
python3 scripts/build_deck.py work/deck/deck.json --guide work/ref/guide.json --template work/tpl.pptx \
  -o work/out/deck.pptx --reference REF --renders work/out/renders --plan work/plan.json \
  [--chrome draw] [--house-deck other.guide.json ...]
```

One command solves every page with measured fit, emits on the template, reads the file
back, validates, renders, and judges. It prints a brief and writes `deck.build.json` beside
the deck; exit 0 means every page fit and the package is valid. Leave `--others` alone: the
judge's panel is every deck under `refs/files` (fetch once with `refs/fetch.sh`), the
reference's twin removed by hash, scans skipped, decks inside the reference's own spread
reported as the same house. The panel is not yours to choose.

## Fit and scale

`status: fit` with `scale` and `violations: []` fits at that type scale. Below 1.0 the
solver stepped the whole ladder down toward the floor; say so in the report below 0.9.

## Unfittable pages: your moves, in order

`status: unfittable` names the smallest admitted scale, every violation, and for each
table `rows_to_fit_slide`, the body-row count at which to split. A title that needs two
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
`font refused`. Warnings never refuse: `tieout` (a totals cell that does not equal its
column), and `no source line` (a page with a table or chart and no `type.source_line` or
`type.footnote` paragraph: the house's source-line habit is not measured, so look at its
data pages and add one where the house does).

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
  `in band`, `above`, or `no evidence`). A fit page `below` on covered area ends half-way
  down: give the body region a weight in its column, or add content.

## Repetition (the section's variety)

Each solved page's content (the page frame left out: `frame_left_out`) gets a realised
composition by the extractor's own clustering, and `measure` is plan.py's: composition V,
class V (the exhibit classes the page realises), distinct per page, runs. `against_house`
sets each against the house (pooled with `--house-deck`), `runs_over_reference` lists runs
longer than the house's longest, and `warnings` lists every figure below the house's 10th
percentile. With `--plan`, `plan.check` repeats the plan check and
`pages_differing_from_plan` flags each page where plan and build disagree. A plan the check
refuses is not built.

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
