# Composition: questions, and what decks measurably do

Questions to ask about a page's arrangement, with what professional decks measurably do.
None of it is a rule. The reference's measured habits (`guide.composition`, `guide.variety`, its
own pages) are the strongest evidence you have: start there, and where this page departs,
say why in the report. Only measurable defects refuse. Counts are from 578 coded content pages (bank 231, consulting 317, chart book
30), one coder per page, good to about plus or minus 2 to 3.

## Contents
- Questions per page
- Composition families by deck type
- Exhibits per page, and co-equal blocks
- Sidebars and takeaway boxes
- Density
- Conventions that belong to one reference
- What a blind rater noticed on generated pages

## Questions per page

- Which layout do the reference's past decks use for a page like this, and which placeholders
  do they fill?
- Did the content's own structure pick the arrangement (how many entities, how many
  measures per entity, what is compared, what is concluded), or was a layout picked and
  the content poured in?
- Which element proves the message most directly, and does its size reflect that? Where
  does the eye finish? (The resolution tends to sit at the end of the reading path: the
  last row boxed and shaded, a bottom band, a down arrow to one bottom-line number.)
- If several blocks are co-equal, are they a comparison (equal panels on a shared scale,
  one order) or a list of unrelated facts? Does each block's size say how much it matters
  to the message?
- Is every edge on an axis the page already has? Is empty space a decision you can name?
- With a reference, which of its pages is nearest to this intent in look, and what does it do that this page does not?

## What coders counted, by deck type

The rows are the corpus coders' composition families with counts: evidence of how firms
arrange pages, never a set to choose from. (`library.py pick --composition` takes words:
words that name one of these families match the library pages filed under it, any other
words are matched against what each page records of its composition. It is a search over
coded examples, and a page none of the families names is filed as `other` in words.)

| Family | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Single chart, full width | 113 | 53 | 45 | 15 |
| Single table, full width | 91 | 45 | 46 | 0 |
| Exhibit plus side text or takeaway column | 80 | 22 | 58 | 0 |
| Two or more exhibits (panels, small multiples, chart plus table) | 77 | 38 | 24 | 15 |
| Structured text (label rows, numbered rows, columns, cards) | 76 | 16 | 60 | 0 |
| Diagram, process or timeline | 58 | 8 | 50 | 0 |
| Text only | 40 | 23 | 17 | 0 |
| Image, logo or evidence wall | 19 | 11 | 8 | 0 |
| Exhibit plus text above or below | 16 | 15 | 1 | 0 |
| Big numbers or KPI panel | 8 | 0 | 8 | 0 |

Page design is mainly composition, text and tables: 346 of 578 pages carry no data chart.

## Exhibits per page, and co-equal blocks

| Exhibits on the page | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| 0 | 94 | 25 | 69 | 0 |
| 1 | 390 | 161 | 214 | 15 |
| 2 | 74 | 34 | 31 | 9 |
| 3 | 17 | 9 | 3 | 5 |
| 4 or more | 3 | 2 | 0 | 1 |

Equal panels are not themselves a defect: 77 of 578 pages carry two or more exhibits, 6 of
30 chart-book pages are two equal panels, and equal small multiples on a shared scale are
how the corpus makes a comparison honest. Measured once on two model tiers: "one element
dominates", with no guidance for co-equal blocks, produced dashboard-like grids of unrelated
panels. The question is whether the blocks are a comparison.

## Sidebars and takeaway boxes

Recorded sidebar or takeaway box: bank 18 of 231, consulting 55 of 317, chart book 0 of 30.
Takeaway band, box or sidebar as an emphasis device: 46 pages.

## Density

Median page fill is 0.85 in every deck type. Median elements per page: bank about 80 (two
decks at 145 and 119), consulting about 30, chart book about 35; dense tables reach 110 to
230 elements. The guide's density bands are this reference's own range: the build reports
where the page sits in them, as evidence, and a page outside them says why in the report.

## Conventions that belong to one reference

Each was found in one deck or one firm's decks; they show what mining a company's decks finds, not
what to copy elsewhere: a bottom takeaway band on 20 of 30 pages; a chart of 62 to 70% of
the width beside a grey full-height sidebar on 11 of 29 pages; a title panel on the left
third of the page; rows of number badge, arrow label and finding box on 6 of 51 pages of
three pitch books on one master; exhibit-only pages with no body text on 30 of 30; a
row-label template for 7 appendix pages; one template across 6 recap pages and another
across 5 segment tables.

## What a blind rater noticed on generated pages

The rater's recorded notes, the evidence here: "Chart variety and layout variety in
generated slides are low. Generally the same patterns with different colours"; "Logos.
Generated slides have none". Claim titles on every page of a deck whose reference titles by topic were caught in the
blind round too (dev/evals/README.md).

Questions to put to a page, with counts where the corpus has them:

- A card grid: is the content a comparison, or a list that a grid makes look like one?
- Number and label tiles: big numbers or KPI panels are 8 of 578 coded pages, all
  consulting; icons are on 32 (2 bank, 30 consulting). Does this reference draw them?
- Corners: what do `guide.shape_language.corner_radii` (`rounded_share`) and the reference's
  pages show?
- Centred body text, three of everything, uniform spacing: does the reference do this, and does
  this content have three parts or equal weight?
- One composition on pages that are not siblings: is the repeat saying they are parallel?
- Extra text or exhibits added to look full: would a split serve the reader better?

Where the reference does one of these (a consulting deck pairing big numbers with icons; a
deck whose panels are equal small multiples), it is the reference's habit. With no
reference, each is a question for the look you chose.
