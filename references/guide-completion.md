# Completing the guide

## Contents
- What you answer, and what the finalizer refuses
- Value shapes
- Description and derivation rules
- Floors
- Titles: /titles/register
- Exhibit habits: the digest
- Content pages: /variety/content_pages
- Worked completions

## What you answer, and what the finalizer refuses

The draft's `unresolved` list is exactly what you answer: every address in it, no other.
An address left out is as wrong as one invented. Write `{"<open path>": value, ...}`:

```bash
python3 scripts/complete_guide.py work/ref/draft.json --check     # what is open, which core addresses
python3 scripts/complete_guide.py work/ref/draft.json work/ref/completion.json -o work/ref/guide.json --digest work/ref/digest
```

- A key outside `unresolved` is refused. Always writable: `/description`,
  `/derivation_rules`, `/continuation`, `/typography/families/substitutes`, `/notes/*`, a
  new `/extra_roles/<name>`, and a new type role at a size the levels table shows (on a
  raster reference, one whose value carries `"provenance": "raster_inference"`).
- A key whose target is observed or deterministically inferred is refused with its
  provenance and evidence. If you think an observed value is wrong, say so in the report;
  never patch over it.
- The core must close: type.title, type.body, color.surface, color.ink, color.accent1, and
  one of type.caption, type.footnote, type.source_line. `--allow-partial` writes a guide
  with the open core listed under `completion.core_open`, for inspection only.
- Role names are the extractor's: on one bank deck `color.accent1` is the observed light
  grey and the deep blue is the second accent. Bind fills and inks by what the draft
  observed; the build's contrast gate confirms it.
- Every value comes from THIS reference. Low confidence beats convention: a chartless deck
  gets a chart language derived from its palette and register, not a stock one.
- Colours enter only under `/color/roles/<role>` or `/extra_roles/<name>` as hex with a
  `why`. Everything else refers to roles. No size below the family floor.
- Renders are a camera for colour, proportion and position, not for text fit, line
  spacing, padding or rule weight: those are measured or they stay open.

## Value shapes

`null` is an answer where shown, and closes the address; a left-out key never does.

| address | value |
|---|---|
| `/color/roles/<role>`, `/extra_roles/<name>` | `{"hex": "RRGGBB", "why": "..."}` (a bare `"RRGGBB"` also applies) |
| `/typography/roles/<role>` | `{"size_pt", "weight", "italic", "family", "alignment", "case", "ink_role", "why"}` |
| `/typography/roles/<role>/members` | the members the ladder left open, same keys without `size_pt` |
| `/typography/roles/<role>/line_spacing` | a multiple of the size, or `null`: single spacing (drawn at 1.2 x size) |
| `/typography/scale_ratio` | a number, or `null` when the levels are not a geometric ladder |
| `/spacing/baseline_emu` | an integer, or `null`: no baseline grid |
| `/density_bands/table_rows_per_inch` | `{"metric", "low", "high", "median", "n"}`, or `null` with no table |
| `/shape_language/corner_radii` | `{"modal_radius_emu", "rounded_share", "why"}` |
| `/floors/<family>/floor_pt` | a number, never below `absolute_floor_pt` |

## Description and derivation rules

Write `/description` (summary, typography, color, layout, tables, imagery, motifs,
`never_does`, tone) and `/derivation_rules` (how the palette and the type ladder extend to
roles the reference never showed). You read these back while designing; write them for
yourself, from what you saw.

## Floors

`floor_pt` is the smallest size the reference uses per family; the solver never descends
below it. A size set on two or more pages counts even when the Tukey fence would trim it
(source lines that are 10 of 44 annotation runs set the floor at 8.0, not the fence's
9.0); a size on one page under the fence is trimmed, and turned text is never a sample.
When the body floor equals the body size there is no headroom: density comes from
arrangement and content. You may lower a floor in the completion when the reference's
captions show a smaller size in use, never below `absolute_floor_pt` (7.0pt, measured on
two screen media by one rater for Arial and Calibri; print was not measured, so for a deck
that will be printed keep the reference's own floor).

## Titles: /titles/register

The draft lists every page title found by position (text, characters, words, lines, and
the block directly above or below it) with median, p90 and max. Read each one on the
render and answer:

```json
{"/titles/register": {
  "per_title": {"<slide>": "topic|claim|question"},
  "companions": {"<slide>": {"above": "kicker|section_tag|exhibit_label|status_tag|other",
                             "below": "subtitle|units_line|lead_in|other"}},
  "claims_elsewhere": {"<slide of a topic title>": "where the page states its claim, or null"},
  "why": "..."}}
```

Every listed title and every listed companion is named; a block the reader found below a
title that is really the first cell of a table is `other`. The finalizer counts the
registers; the plan check and the build hold your titles to those counts and lengths.

## Exhibit habits: the digest

```bash
python3 scripts/gallery.py digest REF --out work/ref/digest --guide work/ref/draft.json
```

Look at every page, content crop and candidate crop (a title or chrome leaf inside a
content crop is still drawn; the stub names it under `also_draws`). Copy
`digest.stub.json` to `digest.json` in the same directory, leave the stub as cut, and in
the copy replace each page's `exhibits: null` with records in the stub's
`record_template` (an empty list states the page has none; one candidate may hold several
exhibits). Every value comes from `references/page_craft_vocabulary.json`; every
annotation move names its anchor. Answer with `--digest work/ref/digest`: a page dropped,
repeated or added, a candidate added and a record repeated are each refused by name, and a
patch value for `/exhibit_habits` is refused. The finalizer computes every count (types,
data shapes, moves by data shape and by message, emphasis, number formats, legend, labels,
colour logic) and re-measures the house's exhibit-type and exhibit-class variety.

## Content pages: /variety/content_pages

The draft proposes which pages are content (library.py's triage: cover, divider,
disclaimer, hidden and generated pages are not). On a PDF no divider or disclaimer is
proposed, so a contents page or a letter counts as content until you answer. Look at the
renders and answer with the list of content pages, e.g. `[3, 4, 5, 17]`. A page not in the
sequence, a hidden page, a duplicate, an empty list or a non-list is refused by name. The
house's variety is re-measured over your list on every completion.

## Worked completions

`examples/keybank.completion.json` (a pptx reference with no native tables or charts) and
`examples/mckinsey-pdf.completion.json` (a vector PDF), each with its digest under
`examples/digests/`. Both apply cleanly to the current extractor's drafts with nothing left
open.
