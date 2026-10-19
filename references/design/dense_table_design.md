---
name: dense_table_design
description: How to design dense, column-scannable tables - numeral alignment, header contracts, one row-tracing device, singular emphasis, concluding rows. Load when the slide carries a table.
---

# dense_table_design v1

General craft for tables that carry many rows and columns while staying
instantly readable. Concrete values - fonts, colors, sizes - belong to the
StyleGuide, never here. Where this skill and the reference's observed practice
conflict, the reference wins.

## Principles

A dense table is read down columns, not across rows. Everything serves the
column scan: numerals right-aligned on a shared edge with consistent decimal
places, one unit convention per column declared once in the header, the label
column flush left. If two numbers in a column cannot be compared at a glance,
the table has failed no matter how it looks.

Headers are the table's contract. State measure and unit in the header, never
per cell. Separate the header with a rule rather than a fill unless the
reference shows filled headers. Group related columns under spanner headings
instead of repeating a prefix in every column head.

Rows are cheap; visual noise is not. Prefer more rows at a legible floor over
fewer rows padded out. Banding, gridlines, and fills are substitutes for the
same job - guiding the eye along a row - so use at most one of them, and only
when row-tracing is genuinely hard at the width in hand.

Emphasis is singular and semantic. The row that matters - the target, the
median, the concluded range - gets the one emphasis treatment on the table.
Summary rows sit apart: a heavier rule or a spacing step above them,
emphasized labels, never just bolder text left in place.

The table ends in its reading. Medians, means, and the implied figure belong
at the bottom edge where the column scan terminates, so the table resolves
where the eye finishes.

## Worked example: trading comps

Label column flush left in type.table_cell, company names plain, the target's
row in type.emphasis over a light color.accent1 fill - the only fill on the
table. Numeric columns right-aligned with uniform decimals. Spanner headers
group the valuation multiples apart from the operating metrics, each header in
type.table_header over a color.rule hairline. Median and mean rows sit below a
second, heavier rule with labels in type.emphasis, and the implied range the
title asserts is restated beneath them in type.h2, so the scan ends on the
conclusion.

## Worked example: sensitivity grid

Row and column axis labels run type.table_header, with each axis variable
named once, units in type.caption. Interior cells are uniform type.table_cell.
The operative scenario cell carries color.accent1 with type.emphasis, and the
row and column headers it intersects shift from color.ink_muted to color.ink -
the crosshair emerges from role shifts, not drawn arrows.

## Checklist

- Numerals right-aligned with uniform decimals, units only in the header?
- At most one row-tracing device: banding, rules, or fills?
- Exactly one emphasized row or cell, and is it the one the title argues?
- Summary rows visibly set apart from the body?
- Does the column scan terminate in the concluding figures?

## Anti-patterns

- Center-aligned numeric columns.
- Units repeated in every cell.
- Banding plus gridlines plus filled headers: three devices doing one job.
- Emphasis on several rows at once, which is emphasis on none.
- A table made to fit by dropping rows instead of tightening roles or
  splitting at a legal boundary.
