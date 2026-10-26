# House specimen as examples

Fourteen pages of one other house: a default house specimen of a predecessor system,
converted to role-only page models with their own datasets. Each file is a one-slide deck in
the shape of `examples/keybank-section.deck.json`: `slides[].id`, `layout`, `notes` (the
specimen's intent), `spec.root`, and `styling` / `charts` / `rules` where the page has
them. Every value is a token role; nothing here carries a colour, a size or a coordinate.

They are one house's answers to 14 intents: things to look at and depart from, not seeds
and not a menu of page types. Look at your own house's nearest page first (its renders,
gallery and digest), name what the specimen does differently, then build from your house.
Read a specimen for how its spec is built (regions, weights, roles, a chart's techniques)
when your page needs the same construction. They were authored for a 16:9 house page with
house type sizes; on another reference they do not fit as written (see "On keybank" below).

## The specimen house's own habits

What these 14 pages do is this one house's practice, counted here so it can be told apart
from yours:

- a kicker over the title on 13 of 14 pages (all but the section opener, 01); a kicker or
  subtitle is on 64 of 231 coded bank pages and 265 of 317 consulting pages;
- a filled takeaway band on 4 (08, 09, 10, 13);
- a source line on 12 of 14 (not 01 or 02);
- a rule element (a hairline closing a column or heading, or a decor rule) on 12 of 14;
- a table on 10 of 14 and a native chart on 5 (04, 05, 06, 07, 12), the football field on
  09 drawn as a component.

## Pages

| File | What it shows (the specimen's coverage record) | Elements |
|---|---|---|
| `01-section-opener.deck.json` | Section divider | el-section-number (kicker), el-section-title (title), el-divider-rule (rule), el-section-frame (body), five contents groups: grp-content-N-title (emphasis), -head-rule (rule), -body (caption) |
| `02-agenda.deck.json` | Agenda / tracker; takeaway band | title, el-kicker, five entries el-section-N (body; the live one h2) with el-section-summary-N (caption), the live entry in a filled band, col-live-title (h1) + rule + body, three decisions grp-decide-N (h2 + rule + body) |
| `03-company-profile.deck.json` | Company profile page; headerless table; emphasis run | title, el-kicker, el-facts (table 6x2, no header), el-story (h2 + body), el-numbers (h2 + body with emphasis runs), el-segments (table 3x3), el-numbers-rule, el-numbers-note (footnote), el-history (table 7x5), source |
| `04-headline-metrics.deck.json` | KPI figure band; column chart | title, el-kicker, five KPI groups grp-kpi-N (figure: the lead in type.title, the rest h1; label caption; closing rule), el-segment-chart (column), el-exhibit-note (h2 + body), el-segment-table (table 3x5), source |
| `05-margin-trend.deck.json` | Text-plus-chart composite; line chart | title, el-kicker, el-argument (body) + rule, el-trend-table (table 7x5), el-argument-note (caption), el-margin-chart (line, two series), source |
| `06-revenue-mix.deck.json` | Mekko (composite of natives) | title, el-kicker, three named columns el-mekko-name-N (h2) / el-mekko-size-N (caption) over el-mekko-N (`COLUMN_STACKED_100`, one category, three region series), colour key el-key-* (emphasis) + el-key-note, el-mekko-reading (emphasis), source |
| `07-ebitda-bridge.deck.json` | Waterfall | title, el-kicker, grp-adds / grp-takes (h2 + rule + body), el-bridge (`COLUMN_STACKED`: invisible base, step series with per-point fills, a zero series carrying the signed labels), el-bridge-drivers (table 7x4), source |
| `08-trading-comparables.deck.json` | Comps table; totals row; emphasis row; splittable group; takeaway band | title, el-kicker, el-comps (table 17x10; peer-median row 8 as an emphasis group, row 16 as totals_last_row), el-comps-basis (footnote), el-takeaway (emphasis, in a filled band), source; splittable group grp-comps-blocks |
| `09-football-field.deck.json` | Football field (as the `football_field` component); takeaway band | title, el-kicker, grp-overlap (h1 + rule + body), el-range-chart (component football_field, six methods from cig-football-field, axis $30 to $55), el-method-table (table 6x4), el-range-note (emphasis, in a filled band), source |
| `10-buyer-screen.deck.json` | Framework matrix; takeaway band | title, el-kicker, el-screen (table 6x8, graded dot ratings as text), five criterion notes grp-criterion-N (emphasis + rule + caption), three shortlist groups (h2 + rule + body), el-takeaway (filled band), source |
| `11-credentials.deck.json` | Tombstone / credentials grid; credential card | title, el-kicker, eight cards (filled, ruled region): el-cred-price-N (h2) + rule + el-cred-N (mixed caption, emphasis, body, footnote), el-cred-rule-1 (rule between card rows), three reading groups (h2 + rule + body), source |
| `12-league-table.deck.json` | League table; column chart against rank | title, el-kicker, el-league (table 9x5 with totals row), el-share-chart (column, seven advisers), el-league-note (footnote), three reading groups, source |
| `13-process-timeline.deck.json` | Timeline | title, el-kicker, three phases grp-phase-N (h2 + rule + caption), el-spine (rule), six milestones el-milestone-date-N (h2) + rule + el-milestone-N (caption with emphasis), el-workstreams (table 5x4), el-decisions (emphasis, filled band), source |
| `14-recommendation.deck.json` | Arithmetic chain | title, el-kicker, three steps grp-step-N (figure h1, the result in type.title; label caption; rule), el-value-bridge (table 8x3), four argument groups why / do / unless / next (h2 + rule + body), source |

Families the specimen itself declares NOT covered (bar chart, slide-level annotation,
tracker-marker, forecast divider, callout bracket, Harvey ball, imagery, continuation)
are absent here too; the specimen's coverage record says why for each.

## What the conversion changed, and why

- **Title.** The specimen opens every page (except 01) with a `band-title` region:
  kicker over title, closed by a hairline. The build gives a reference's title band
  only to a root-first `type.title` text element, so the title is lifted to the first
  child (id `title`) and the kicker becomes the first line under it. The band's own
  hairline is dropped: the reference's top rule closes the band. Nothing else moves.
- **Motifs.** `heading-rule` becomes a `rule` element of one EMU height closing its
  column (`<region>-rule`, `rules[...]` = color.rule). `takeaway-band` and
  `credential-card` become region fills in `styling` with `color.surface_alt` (the
  card also `line_role: color.rule`): the house's own `color.accent1_wash` is not a
  core role, and a reference without it would refuse the page.
- **Decor** (`el-divider-rule`, `el-spine`, ...) becomes a `rule` with a one-EMU extent
  across its parent's main axis.
- **Charts** are real charts from `datasets.json`, written in the full chart spec
  (`references/chart-recipes.md`) with every choice explicit: column (04, 12:
  labelled bars, value axis hidden, `color.accent1` with `color.ink` labels outside the
  bars), line (05: two `LINE` series in `color.accent1` and `color.accent2` at 1.75pt,
  value axis shown without gridlines, legend at the bottom), the mekko (06: one
  `COLUMN_STACKED_100` per segment, gap 0, both axes hidden, no legend since the page
  carries its own key; the three charts sit at flex weights 4.8, 3.2 and 2.0, the
  segments' shares of revenue, so the column widths are proportional), and the bridge (07: the waterfall recipe, anchors FY25A 331
  and FY26E 374 in `color.accent2`, increases `color.accent1`, decreases
  `color.accent3`, signed labels above the bars). The specimen's own colour roles
  (`color.positive` / `color.negative` on the bridge) are not core roles and a guide
  without them would refuse the page, so the bridge uses accents; on a guide that has
  them, write them in. The football field (09) is the `football_field` component with
  the six methods' lows and highs; the specimen draws no price marker, so none is
  added. Every ink on a fill is chosen for keybank's roles (`color.ink_inverse` on
  `color.accent2`, `color.ink` on `color.accent1` and `color.accent3`); on another
  guide the build's contrast gate names any pair that no longer reads.
- **Ink and emphasis.** Element ink slots other than color.ink become paragraph
  `ink_role` in `styling`; emphasis runs become `styling.<id>.paragraphs.<n>.runs`.
- **Tables.** A totals index on the last row becomes `totals_last_row`; any other totals
  index (the comps peer median, row 8) becomes an `emphasis` group,
  `{"rows": [8], "fill_role": "color.surface_alt"}`, its fill written out (the emitter has no default fill). The specimen's column
  alignment and rule overrides are not carried (this emitter reads neither).
- **Source line.** The specimen computes it from the citations behind each page;
  its output is written as
  a `type.source_line` paragraph, id `source`, last in the root.

Conversion: a one-off script over the specimen, extended as above (not committed: it
imports the predecessor system).

## On keybank (4:3, 24pt title, 12pt tables)

Built with `scripts/build_deck.py examples/house/<file> --guide keybank.guide.json
--template keybank-template.pptx --reference keybank.pptx` on 2026-10-20; rows 02 and 09
re-read on 2026-10-26 from a fresh extraction of keybank (the same result on main,
3952e74). Status is the build's; "filed" is the judge's `filed_under_reference`. A title
that needs more lines than the band holds is now the reason a page reports first; the
overflow listed beside it is still there.

| Page | Status | Scale | Title lines (band holds 1) | Filed | What does not fit |
|---|---|---|---|---|---|
| 01 | unfittable | 0.99 | (no title band) | no | el-section-title and grp-content-0-body cross the reference's top-rule zone by 1,828 EMU |
| 02 | unfittable | 0.98 | 1 | no (the nearest house is keybank; judge 0.149) | the three decision bodies grp-decide-0-body to grp-decide-2-body each cross the footer zone (`chrome-5:footer`) by 87,301 EMU and the footer rule's zone (`chrome-4:rule`) by 88,215 EMU; the title fits |
| 03 | unfittable | 0.98 | 2 | no | band-history runs past the page |
| 04 | unfittable | 0.99 | 1 | no | el-segment-table's columns need 404,607 EMU more than its box; the source line crosses the footer rule zone by 44,127 EMU |
| 05 | unfittable | 0.98 | 2 | no | el-trend-table runs past the page |
| 06 | unfittable | 0.98 | 2 | no | only the two-line title, crossing the top-rule zone; the body fits |
| 07 | fit | 1.00 | 1 | yes | solver fit, but the waterfall is left 266,789 EMU tall (read from the emitted pptx): the two text columns and the 7-row table take the page, so the chart is a sliver. Not a usable page on keybank. |
| 08 | unfittable | 0.98 | 2 | no | 17-row table measures 9,854,046 EMU tall (company names wrap to 3 lines in keybank's 12pt cells); 3 rows fit; even the declared split at row 9 does not |
| 09 | refused before building | n/a | n/a | n/a | the text, 7-row table and note leave the football field component a box of 8,382,000 x 0 EMU, and the build refuses the component by name before solving (the 2026-10-20 row read unfittable at 1.00, band-body over by 495,645 EMU; which later change moved it was not traced) |
| 10 | unfittable | 0.98 | 2 | no | band-shortlist runs past the page |
| 11 | unfittable | 0.98 | 2 | no | each card row is as tall as its tallest card, which pushes band-reading 2,189,204 EMU past the page (before the 2026-10-20 fit-truth change the rows were cut to a share and the cards overflowed them unreported, with the rule between card rows rounded to zero height) |
| 12 | unfittable | 0.98 | 2 | no | the two-line title, crossing the top-rule zone, and el-league: its fitted rows need 2,727,460 EMU in a 1,436,322 EMU box (unreported before the 2026-10-20 fit-truth change) |
| 13 | unfittable | 0.98 | 2 | no | band-workstreams runs past the page |
| 14 | unfittable | 0.99 | 2 | no | band-asks runs past the page |

The specimen was composed for a 16:9 page; keybank is 4:3 with 12pt table cells and a
one-line title band, and 1 of 14 pages (07) fits as written. These are reported, not
forced: a page built from your house's own nearest page starts from its proportions
instead.
