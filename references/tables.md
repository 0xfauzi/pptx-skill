# Tables: questions, measured habits, and the table spec

Questions to ask about a table, with what professional decks measurably do; never rules.
The guide's `tables` section and the house's `exhibit_habits` decide whenever they have
evidence. Counts are per exhibit over 192 coded tables, one coder per page, good to about
plus or minus 2 to 3.

## Contents
- Questions per table
- Table families by house type
- Moves on tables
- Number craft
- The table spec: what you write and what the build measures

## Questions per table

- Will the reader look values up (a table), compare a pattern (a chart), or match findings
  to actions (aligned rows)? Lookup and reference content was a table in 71 of 71 cases,
  sensitivity in 29 of 29.
- Can two numbers in a column be compared at a glance (numerals on one right edge, one
  decimal convention, the unit declared once)?
- Which rows does the claim rest on: the subject, the median, the totals, a scenario
  region? How does this house mark each, and does it mark several at once?
- Is this a page of argument or reference? Reference tables carry housekeeping (spanners,
  totals, footnotes) and little emphasis: in one bank coder group 54 of 224 exhibits had
  only housekeeping.
- Where does the column scan end, and does the table resolve there?
- If it will not fit: which rows split to the next page under the house's continuation
  convention? Never drop rows.

## Table families by house type

| Family | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Text or data table | 53 | 29 | 21 | 3 |
| Financial or projection table | 42 | 31 | 11 | 0 |
| Sensitivity grid | 29 | 29 | 0 | 0 |
| Framework matrix or placemat | 24 | 11 | 11 | 2 |
| Status or check matrix | 16 | 1 | 15 | 0 |
| Comps or benchmark table | 15 | 14 | 1 | 0 |
| Table with in-cell bars | 13 | 2 | 11 | 0 |

In the bank decks tables outnumber charts (117 to 109). Harvey balls: 0 in the bank decks,
0 in the chart book, 2 Harvey-style tables in 317 consulting pages; check, status and
red-amber-green matrices are the measured equivalent (16 exhibits, 41 glyph moves).

## Moves on tables

Over 192 tables: circled or boxed mark 50; column spanners 45; shaded or bold total row 47;
footnote markers 36; highlight one item 34; italic ratio rows 16; statistic or median row
15; status glyphs 16; NM, NA markers 13; sorted 10; input cells or base case 8. By family:

| Family | n | Most frequent moves |
|---|---|---|
| Financial or projection | 42 | shaded total rows 27; italic ratio rows 16; spanners 13; highlight 13; boxed rows 12 |
| Comps or benchmark | 15 | median or statistic row 12; spanners 9; subject highlighted 8; NM 5 |
| Sensitivity grid | 29 | boxed cell or region 17; spanners 7; base case marked 3 |
| Text or data | 53 | total row 14; footnotes 13; spanners 9 |
| Status or check matrix | 16 | glyphs 9; highlight 4; footnotes 4 |

Several emphases on one table are normal: comps tables emphasise the median row on 12 of
15 and the subject on 8 of 15, often both; projection tables shade several total rows on
27 of 42; sensitivity grids box a region. Shaded key rows, cells or columns appear on 52
pages; dark label cells and banners on 37.

## Number craft

Recurring bank habits (both coder groups): $ only on the first and total rows; x on
multiples; italic ratio rows under their $ row; a units column separate from the labels; NM
and NA written out, never left blank. Negatives in parentheses on 13 pages. Number-format
habits recorded on 35 pages; the house's own appear in `exhibit_habits.number_formats`.

## The table spec: what you write and what the build measures

- A column may carry `width_share` (its exact share of the table width) or
  `min_width_role` (a spacing role it never narrows below); the fitter honours both, still
  measures every cell, and reports a share below a column's widest word as a width deficit.
- `emphasis` is the table's list of emphasis groups, each marking body rows (data-row
  indices) or columns (column keys), with a `fill_role` (a colour role; `"none"`, no
  fill; `"keep"`, the banding or data fill the cells have anyway; there is no default) and
  an optional `ink_role` and `bold` (`true` or `false`: a dark label column in regular
  weight is `"bold": false`; left out, the cells are bold and the page lists it under
  `table_defaults_taken`). Cells are measured in the weight they are written in. Several
  emphases on one table are several groups: the subject row shaded and the row labels
  bold is `[{"rows": [8], "fill_role": "color.surface_alt"}, {"columns": ["label"],
  "fill_role": "keep"}]`; where two groups meet, the later one's fill and ink are drawn.
  Cell-level marks (a boxed median, a bracketed group) are annotations with a table
  anchor. (`emphasis_rows`, `emphasis_fill_role` and `emphasis_ink_role` were replaced
  by `emphasis`, and are refused with the new spelling.)
- The guide's table look is the default; each table may override it as roles:
  `header_fill_role`, `header_ink_role`, `banding_role`, `data_fill_role` (a colour role or
  `"none"`), `header_bold`, `header_align`, and `align` per column. These keys,
  `emphasis` and `totals_last_row` may sit on the element, inside its `table` spec or under
  `styling.<id>`; a key written twice with different values, or an unknown key, is refused.
- An empty cell (a section label row, a blank spacer cell) is written with no run and an
  end mark at the cell's size, so it draws at the fitted row height; before, LibreOffice
  drew it at 18pt and every row below moved, and annotations on those rows landed a row
  off.
- `header_role` and `cell_role` are the roles the solver measures and the file is written
  in, with nothing substituted; a bold header is measured bold.
- With `totals_last_row`, the build ties each numeric column's body sum to its totals cell
  and warns on a mismatch (a subtotal inside the body reads as one: compute the figure or
  take the flag off).
