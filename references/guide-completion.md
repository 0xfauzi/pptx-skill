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
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" --check     # what is open, which core addresses
python3 scripts/complete_guide.py "$DECK_WORK/ref/draft.json" "$DECK_WORK/ref/completion.json" -o "$DECK_WORK/ref/guide.json" --digest "$DECK_WORK/ref/digest"
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

Every open address takes the value below; `--check` prints the line for each address it
lists, and `complete_guide.py --shapes` prints this table. `null` is an answer where the
last column says what it means, and closes the address; where it says "refused", write the
value instead. A left-out key never closes anything.

| address | value | null means |
|---|---|---|
| `/color/roles/color.(surface\|ink\|accent1)` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | refused |
| `/color/roles/color.emphasis` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | the house marks emphasis in no colour of its own (in its ink or rule colour, or not at all): recorded under absent_roles, and an annotation names the ink or rule role instead |
| `/color/roles/<name>` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | the house has no such colour, not even inside its pictures: the role is recorded under absent_roles, and a page that names it is refused. A colour seen only inside pasted pictures is not absent: answer it with "evidence": "pictures" |
| `/extra_roles/<name>` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | refused |
| `/typography/roles/type.(title\|body)` | {"size_pt", "weight", "italic", "family", "alignment", "case", "ink_role", "why"}; optional "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt" | refused |
| `/typography/roles/<name>/members` | the open members only: any of "weight", "italic", "family", "alignment", "case", "ink_role", "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt", plus "why"; never "size_pt" | refused |
| `/typography/roles/<name>/line_spacing` | a multiple of the size, e.g. 1.2 ("/typography/roles/*/line_spacing": v answers every open one not named) | single spacing (drawn at 1.2 x size) |
| `/typography/roles/<name>` | {"size_pt", "weight", "italic", "family", "alignment", "case", "ink_role", "why"}; optional "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt"; add "evidence": "pictures" when the house sets such text only inside pasted pictures | the house has no such text anywhere, not even inside its pictures: recorded under absent_roles; a page that names the role is refused. Text the house sets only inside pasted pictures (axis labels on a chart image) is not absent: answer the value read off the pictures with "evidence": "pictures". One of type.caption, type.footnote, type.source_line must stay answered |
| `/typography/families` | {"major": "<face>", "minor": "<face>"} | refused |
| `/typography/families/substitutes` | {"<face named in the file>": "<installed face measured in its place>"} | refused |
| `/typography/scale_ratio` | a number, e.g. 1.25 | the levels are not a geometric ladder |
| `/spacing/steps/<name>` | an integer EMU | refused |
| `/spacing/baseline_emu` | an integer EMU | no baseline grid |
| `/density_bands/table_rows_per_inch` | {"metric": "table_rows_per_inch", "low", "high", "median", "n"} | no table to measure |
| `/floors/<name>/floor_pt` | a number of points, never below absolute_floor_pt | no run in this family: the absolute floor holds |
| `/shape_language/corner_radii` | {"modal_radius_emu": int, "rounded_share": 0..1, "why": "..."} | refused |
| `/shape_language/icon_style` | a string, e.g. "none" or "white line icons in accent circles" | refused |
| `/imagery/register_kind` | a string, e.g. "photographs, wide crops" or "none" | refused |
| `/tables` | {"header_fill_role", "header_ink_role", "header_bold", "banding_role", "edge_rules": {"table_top", "header_bottom", "row_interior", "table_bottom", "table_left", "table_right", "column_interior": {"width_pt", "color_role"} or {"none": true}}, "cell_padding_role", "alignment_by_column_type": {"numeric", "text"}, "totals_rule", "merged_cell_convention", "why"} | refused |
| `/charts` | {"series_color_roles": [roles in order], "per_kind": {"<bar\|column\|line\|...>": {"gridlines_major": 0..1, "data_labels": 0..1, "legend_position": "b\|t\|r\|l\|tr\|none"}}, "why"} | refused |
| `/continuation` | {"header_repeat": "full\|none", "contd_mark": "<text>", "takeaway_policy": "repeat\|first_only\|none"} | refused |
| `/description` | {"summary", "typography", "color", "layout", "tables", "imagery", "motifs", "never_does": [...], "tone"} | refused |
| `/derivation_rules` | a list of sentences | refused |
| `/titles/register` | see Titles below | refused |
| `/variety/content_pages` | a list of page numbers | refused |
| `/exhibit_habits` | never in the patch: answered by --digest DIR | refused |
| `/notes/<name>` | a string | refused |

Where the honest answer is that the house has none (no green for `color.positive`, no
kicker), answer `null`: the guide records the role under `absent_roles`, and a page that
names it is refused with that reason. Do not borrow another role's colour to fill the
slot.

`null` means none anywhere, pictures included. A house that pastes its exhibits as
pictures still sets axis labels, data labels and emphasis marks in them: answer those
with the value read off the pictures and `"evidence": "pictures"` (recorded as `seen_in:
pictures`, so the report can say the value was read at camera precision). A `null` for
`type.axis_label` or `type.data_label` is refused when the digest records exhibits with
axes or labelled marks, since native charts would then have no role to set them in.

`color.emphasis` is the house's look-here colour: the outline box round a figure, the
circle, the highlighted bar. It is always open (no hue band decides it) and is not
`color.negative`, which colours a bad value; annotations take it. `null` there says the
house marks emphasis in its ink or rule colour, or not at all.

Many open `line_spacing` addresses (one per role) usually share one answer:
`"/typography/roles/*/line_spacing": 1.2` answers every open one the patch does not name,
and a named one keeps its own answer. It closes only open addresses.

The table lists the value each address takes when it is open; `--check` lists which are
open. A `/tables` or `/charts` the draft observed is not open, and a patch for it is
refused with its evidence. `why` is accepted everywhere a value is an object, `/members` included, and is kept
as provenance. A run applies every address it can and reports every refusal at once,
numbered; the guide is written only when none is left.

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
arrangement and content. An observed floor also binds the table roles: when the house's
own tables are pictures set below its body floor (keybank's are about 10pt over a 12pt
body floor), native tables will be set at the floor and read larger than the house's; say
so in the report rather than asking for a smaller size. You may lower a floor in the completion when the reference's
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
python3 scripts/gallery.py digest "$REF" --out "$DECK_WORK/ref/digest" --guide "$DECK_WORK/ref/draft.json"
```

Look at every page, content crop and candidate crop (a title or chrome leaf inside a
content crop is still drawn; the stub names it under `also_draws`). Copy
`digest.stub.json` to `digest.json` in the same directory, leave the stub as cut, and in
the copy replace each page's `exhibits: null` with records in the stub's
`record_template` (an empty list states the page has none; one candidate may hold several
exhibits). Every value comes from `references/page_craft_vocabulary.json`; every
annotation move names its anchor. A mark move (a ring or box, a band or shading, a
reference or event line, a bracket: the moves under `annotation_kind_moves` in the
vocabulary) also answers `labelled`: `true` when words on the exhibit say what it marks (a
label beside it, or the figure or words it rings), `false` when it stands alone and only
the text around it explains it; a mark move without it is refused. `false` answers are
the house's precedent for an unlabelled mark on a new page (`explained_by:
{"house_precedent": {"slide": N}}`), and the finalizer lists both under
`exhibit_habits.marks_labelled`. On every page holding a data chart or a table, answer
the page's `source_line`: `true` when it carries a source or note line naming where its
figures come from, `false` when not; leave it `null` on other pages. The finalizer counts
them (`exhibit_habits.source_lines`) and prints the count under `house_habits`; the build
refuses a data page without a source line where the house carries one on at least 80% of
its data pages, and warns on a page WITH one where under 50% do (over three or more data
pages; both lines unmeasured: build-report.md). Answer with `--digest $DECK_WORK/ref/digest`: a page dropped,
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
`examples/mckinsey-pdf.completion.json` (a vector PDF: McKinsey's 17-page board discussion
document for CalSTRS, 2024, from a public board packet; it is not under `refs/`), each with its digest under
`examples/digests/`. Both apply cleanly to the current extractor's drafts with nothing left
open. They show the shape of an answer; they are not answers for another deck, and an
evaluation on either deck holds them out (`evals/holdout.py`).
