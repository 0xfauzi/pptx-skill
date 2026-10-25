# Charts: questions, and what decks measurably do

Questions to ask about a chart, with what professional decks measurably do; never rules.
The house's `exhibit_habits` (moves by data shape and by message, labels, legend, colour
logic) and its `charts` section decide whenever they have evidence. Counts are per exhibit
over 601 coded exhibits (291 charts), one coder per page, good to about plus or minus 2 to
3. How to write a chart and its annotations in the spec is in the chart recipes.

## Contents
- Questions per chart
- Chart families by house type
- Annotation is the norm
- Moves by data shape
- Moves by message
- Labels, legends, gridlines, colour
- Lapses humans made

## Questions per chart

- What is the data's shape (time series, ranking, part-to-whole, bridge, distribution,
  range, relation)? Which chart types fit it, and which does the house use? Would a table
  say it better? (Lookup and reference content was a table in 71 of 71 cases; change over
  time was a chart 93 times and a table 24 times, the tables being projections where every
  number is read.)
- If the house never showed this chart, how would its designers have drawn it with the
  roles, rules and devices they do use?
- What comparison is the reader making, and against what value? Is that value drawn?
- Where on this chart does the claim live: a point, a region, a subset, an absence? How
  does the house mark such a place?
- How much to annotate, and what to leave out? How will the reader find the subject
  (colour, position, order held across panels)?
- What is estimate and what is fact? What explains the shape?
- Do comparable charts share one scale? Do bars start at zero? (The two non-zero
  baselines in the chart book were recorded as lapses.)
- Is the form unfamiliar enough to need a reading key?

## Chart families by house type

| Family | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Line (incl. indexed, price, dual-axis) | 85 | 20 | 46 | 19 |
| Column | 58 | 33 | 20 | 5 |
| Stacked bar, column or area | 47 | 13 | 25 | 9 |
| Horizontal bar | 21 | 7 | 12 | 2 |
| Combo (bar plus line or dot) | 14 | 9 | 1 | 4 |
| Football field or range bars | 14 | 11 | 1 | 2 |
| Pie or donut | 13 | 10 | 3 | 0 |
| Waterfall or bridge | 12 | 3 | 8 | 1 |
| Map | 10 | 1 | 9 | 0 |
| Scatter or bubble | 8 | 1 | 3 | 4 |
| Histogram | 5 | 1 | 4 | 0 |

Construction (native-pptx bank decks only): 27 of 33 data exhibits in three pitch books
were pasted pictures, with annotations laid over them as separate shapes.

## Annotation is the norm

7 of 291 charts carry no annotation (bank 0 of 109, consulting 4 of 135, chart book 3 of
47). Mean moves per exhibit: bank 2.25, consulting 2.09, chart book 2.02. Charts with no
move that points at the message (labels, sorting, footnotes, totals or spanners only): bank
36 of 109, consulting 27 of 135, chart book 12 of 47, about one in four.

Moves on charts (n = 291): data labels on all marks 120; reference, benchmark or average
line 61; callout, arrow or leader 56; end or direct labels 56; highlight one, mute the rest
45; footnote markers 42; circled or boxed mark 39; sorted order 35; forecast demarcation
31; totals above stacks 29; data rows aligned under the chart 29; event markers 27; delta
or growth label 26; inset stats table 24; selective labels 22. CAGR arrows: 0 in the bank
decks, 1 in consulting; growth is shown in a column, an inset table or an oval instead.

## Moves by data shape

| Data shape | n | Most frequent moves |
|---|---|---|
| Line or time series | 85 | end or direct labels 34; reference line 22; event markers 21; callout 17; inset stats table 15; forecast demarcation 13 |
| Column | 58 | all labels 38; highlight one 17; sorted 14; reference line 14; footnotes 10; delta label 9 |
| Horizontal bar (ranking) | 21 | all labels 20; sorted 15; highlight one 13 |
| Stacked or 100% | 47 | all labels 23; totals or "100% =" bases 20; callout 13; rows aligned under the axis 9 |
| Waterfall | 12 | labels 7; totals 6; connectors 6; footnotes 6 |
| Football field or ranges | 14 | labels 10; reference line at the offer or price 8; end labels 6; method spanners 5 |
| Scatter or bubble | 8 | callout 5; highlight the current point 4; reference line 3; regression and R-squared 3 |
| Histogram | 5 | labels 4; reference lines 3; rows under the axis 2 |

## Moves by message

- Subject against peers: label, highlight the subject, a median line or row (bank); a
  highlight, a mean line, a delta pill, sorted (consulting peer benchmarks).
- Ranking: sorted, labelled and the subject highlighted.
- Change over time: end labels; event markers when the message is what caused the shape; a
  forecast divider for projections.
- Valuation range: a reference line at the decision value on 4 of 4 football fields in one
  group, plus brackets and data rows under the axis.
- Composition: totals above stacks, "100% =" bases, row-aligned labels in place of a legend.
- Estimate or scenario: dashed forecast with period shading, a baseline line, the headline
  value circled.
- Relationship: regression line, today's point highlighted, an R-squared box.
- Choice or recommendation: a pointer or callout plus a box on the answer.

## Labels, legends, gridlines, colour

- Labelling every mark is the most frequent chart move in every house type: 120 of 291
  charts (bank 65 of 109, consulting 43 of 135, chart book 12 of 47), usually beside one
  highlighted item. Selective labels: 22.
- Legend absent where recorded: bank 32 of 81, consulting 30 of 85, chart book 18 of 47.
  Direct labels replace the legend mostly on lines and indexed series (34 of 85 lines).
- Gridlines absent where recorded: bank 58 of 80, consulting 78 of 89; the chart book draws
  light horizontal gridlines on 47 of 47. Gridlines are a house habit.
- Colour: one emphasis colour or a single hue is the norm; categorical colour is kept for
  genuinely categorical series (one bank group: 24 of 72 single emphasis against 15 of 72
  categorical). Semantic red and green appear on 9 pages; elsewhere red means "look here".
  Heat and status colour were defined against a named benchmark or decision.

## Lapses humans made

Mismatched y-scales on sibling charts, truncated axes, colliding labels, a missed subject
highlight, a claim with no bracket summing it, comma decimals in a borrowed chart. These are
what a generator should be better than, not what it should copy.
