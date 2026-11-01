# Tables: questions, measured habits, and the table spec

Questions to ask about a table, with what professional decks measurably do; never rules.
The reference's measured habits (the guide's `tables` section, its `exhibit_habits`, its
digest pages) are the strongest evidence you have. Start there; where a table departs,
say why in the report. Only measurable defects refuse. Counts are per exhibit over 192
coded tables, one coder per page, good to about plus or minus 2 to 3.

## Contents
- Questions per table
- What the corpus counted
- Number craft
- The table spec: what you write and what the build measures

## Questions per table

- Will the reader look values up (a table), compare a pattern (a chart), or match findings
  to actions (aligned rows)? Lookup and reference content was a table in 71 of 71 cases,
  sensitivity in 29 of 29.
- Can two numbers in a column be compared at a glance (numerals on one right edge, one
  decimal convention, the unit declared once)?
- Which rows does the claim rest on: the subject, the median, the totals, a scenario
  region? How does this reference mark each, and does it mark several at once?
- Is this a page of argument or reference? Reference tables carry furniture (spanners,
  totals, footnotes) and little emphasis: in one bank coder group 54 of 224 exhibits had
  only furniture.
- Where does the column scan end, and does the table resolve there?
- If it will not fit: which rows split to the next page under the reference's continuation
  convention? Never drop rows.

## What the corpus counted

Totals that answer a question, with the reference's own pages ahead of them: read the reference's
digest records (`gallery.py digest`: each table page's marks and how they are drawn) for
what THIS reference does, and these only for how common a move is elsewhere.

- Table or chart: in the bank decks tables outnumber charts, 117 to 109.
- Several emphases on one table are normal: comps tables mark the median or a statistic
  row on 12 of 15 and the subject on 8 of 15, often both; projection tables shade several
  total rows on 27 of 42; sensitivity grids box a cell or a region on 17 of 29.
- Shaded key rows, cells or columns appear on 52 pages; dark label cells and banners on 37;
  italic ratio rows on 16 of 42 financial tables.
- Harvey balls: 0 in the bank decks, 2 Harvey-style tables in 317 consulting pages; check,
  status and red-amber-green matrices are the measured equivalent (16 exhibits, 41 glyph
  moves).

## Number craft

Recurring bank habits (both coder groups): $ only on the first and total rows; x on
multiples; italic ratio rows under their $ row; a units column separate from the labels; NM
and NA written out, never left blank. Negatives in parentheses on 13 pages. Number-format
habits recorded on 35 pages; the reference's own are in its digest records (`how_drawn`).

## The table spec: what you write and what the build measures

- A column may carry `width_share` (its exact share of the table width) or
  `min_width_role` (a spacing role it never narrows below); the fitter honours both, still
  measures every cell, and reports a share below a column's widest word as a width deficit.
- `emphasis` is the table's list of emphasis groups, each marking body rows (data-row
  indices), columns (column keys), or both (only the cells where they cross: a base-case
  region of a sensitivity grid is `{"rows": [2, 3], "columns": ["y2025", "y2026"], ...}`),
  with a `fill_role` (a colour role; `"none"`, no fill; `"keep"`, the banding or data fill
  the cells have anyway; there is no default) and optionally `ink_role`, `bold` and
  `italic` (`true` or `false`; left out, the cells keep their own setting: the cell role's
  weight and a totals row's `totals_bold`, and the page lists it under
  `table_defaults_taken`), `indent_role` (a spacing step the cells' words are set in by:
  a sub-row under its parent) and `include_header` (with `columns`: the header cells above
  them take the group's fill, ink and setting too: a highlighted subject column). Cells
  are measured in the face, weight and indent they are written in. Several emphases on one
  table are several groups: the subject row shaded and the row labels bold is
  `[{"rows": [8], "fill_role": "color.surface_alt"}, {"columns": ["label"], "fill_role":
  "keep", "bold": true}]`, italic ratio rows are `{"rows": [3, 6], "fill_role": "keep",
  "italic": true}`; where two groups meet, the later one's settings are drawn. Cell-level
  marks (a boxed median, a bracketed group) are annotations with a table anchor.
  (`emphasis_rows`, `emphasis_fill_role` and `emphasis_ink_role` were replaced by
  `emphasis`, and are refused with the new spelling.)
- The guide's table look is where a table starts; each table may override it as roles:
  `header_fill_role`, `header_ink_role`, `banding_role`, `data_fill_role` (a colour role or
  `"none"`), `header_bold`, `totals_bold` (whether a totals row is bold), `banding_phase`
  (0: the first body row banded, 1: the second), `edge_rules` (the guide's own shape, for
  the classes it names: `{"header_bottom": {"color_role": "color.rule", "width_pt": 1.0},
  "row_interior": {"none": true}}`; roles only, and no stroke under 0.5pt unless the
  guide's own table rules declare that width), `header_align`, `align` per column, and
  `cell_anchor` (`t`, `m` or `b`: where every cell's words sit in its row's height; left
  out, top, OOXML's own; a row whose label wraps to two lines while its figures take one
  reads aligned at `m`).
  These keys, `emphasis` and `totals_last_row` may sit on the element, inside its `table`
  spec or under `styling.<id>`; a key written twice with different values, or an unknown
  key, is refused.
- `table_defaults_taken` lists every table value neither the table nor the guide states,
  with what the file got: an emphasis group's weight, a totals row's bold, the banding
  phase, the header's weight, the cell padding (0.05 in, OOXML's own) and a column's
  alignment (figures right, text left) where the guide's `alignment_by_column_type` says
  nothing. Write each one you mean, or name it in the report.
- An empty cell (a section label row, a blank spacer cell) is written with no run and an
  end mark at the cell's size, so it draws at the fitted row height; before, LibreOffice
  drew it at 18pt and every row below moved, and annotations on those rows landed a row
  off.
- `header_role` and `cell_role` are the roles the solver measures and the file is written
  in, with nothing substituted; a bold header is measured bold.
- With `totals_last_row`, the build ties each numeric column's body to its totals cell
  and warns on a mismatch (a subtotal inside the body reads as one: compute the figure or
  take the flag off). A column says what its totals cell is with `total`: `"sum"` (the
  default, reported as taken), `"mean"` (the plain mean of the body rows), or `"none"` (no
  simple aggregate: a weighted average span, a ratio of two totals), which skips it and
  says so under `tieouts`.
- The solver measures every cell in the setting the emitter writes it in (one reader,
  `emit_pptx.table_row_styles`): the label cell of each gap row bold and red is
  `{"rows": [1, 3], "columns": ["skill"], "fill_role": "keep", "ink_role":
  "color.negative", "bold": true}`.
- Grouped headers are native. With `header_rows` N above 1, every column's `label` is a
  list of N strings, top row first; in each row above the last, adjacent columns with the
  same text are one merged cell (a spanner), and `""` leaves a cell empty:
  `{"key": "ev_rev", "label": ["Valuation multiples", "EV / Revenue"]}` beside
  `{"key": "ev_ebitda", "label": ["Valuation multiples", "EV / EBITDA"]}`. A spanner is
  measured across the columns it spans; `spanner_align` (left, center, right) sets the
  spanner cells, else they are centred and the page lists that under
  `table_defaults_taken`. A group label over columns is a spanner, not a bracket
  annotation above the table.
- Table text has one floor, the same in the build and in `pptx_tools validate --emit`:
  the floor of the `table` family (the smallest text the reference sets in native table
  cells; with no native table text, the body floor; with no reference, the 7pt absolute floor). Where the reference's own tables are pasted
  pictures or vector text in a PDF, answer `/tables/picture_text` at completion
  (guide-completion.md): the size is measured there and the table floor drops to it,
  never below the absolute floor.
- Cell padding comes from the guide: `tables.cell_padding_role`, or, when no spacing step
  is near the reference's inset, `cell_padding_role: null` with `cell_padding_emu` (a role wins
  when both are set). A table spec may override with its own `cell_padding_role`.
