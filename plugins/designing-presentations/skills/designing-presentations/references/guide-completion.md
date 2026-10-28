# Completing the guide

## Contents
- What you answer, and what the finalizer refuses
- No reference
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
  new `/extra_roles/<name>`, with no reference a further colour role
  (`/color/roles/color.accent4`) beside the core ones, and a new type role at a size the levels table shows, or at
  another size with a `why` of three words or more (then tagged `off_ladder` and listed
  under `completion.off_ladder`: a weaker model given continuous sizes drifted to 8.5,
  9.5, 20 and 22pt, so the reference's levels are the first evidence, and a departure is
  answered in the report); on a raster reference, one whose value carries
  `"provenance": "raster_inference"`. Every role you add states its `weight`. A text the
  reference's roles do not set well is a role you add, never a borrowed one: a one-line
  panel header in a bar (`/typography/roles/type.panel_header` with the body's size,
  `space_before_pt` and `space_after_pt` 0, its weight and ink, and a why), so the bar is
  as tall as its line and its padding and not the body's paragraph spacing.
- A key whose target is observed or deterministically inferred is refused with its
  provenance and evidence. If you think an observed value is wrong, say so in the report;
  never patch over it.
- The core must close: type.title, type.body, color.surface, color.ink, color.accent1, and
  one of type.caption, type.footnote, type.source_line. `--allow-partial` writes a guide
  with the open core listed under `completion.core_open`, for inspection only: build_deck.py
  refuses a guide with core still open.
- Role names are the extractor's: on one bank deck `color.accent1` is the observed light
  grey and the deep blue is the second accent. Bind fills and inks by what the draft
  observed; the build's contrast gate confirms it.
- Every value comes from THIS reference. Low confidence beats convention: a chartless deck
  gets a chart language derived from its palette and register, not a stock one.
- Colours enter only under `/color/roles/<role>` or `/extra_roles/<name>` as hex with a
  `why`. Everything else refers to roles. No size below the family floor.
- Renders are a camera for colour, proportion and position, not for text fit, line
  spacing, padding or rule weight: those are measured or they stay open.

## No reference

A blank draft (`extract_style.py --blank`) opens every address of the look, the page size
included; every answer is the model's choice and is stored with provenance `model_choice`.
Every open address must be answered (a left-open one refuses the guide: on this path
nothing has a default), `null` included where the table below allows it. The floors carry
only the 7pt absolute floor (nothing was measured), so no role may sit under 7pt. `/chrome`
takes `[]` for pages with no furniture, and its entries leave out `slides_present` (every
entry is drawn on every page). `/reference/page` takes the page size you choose. The corpus
counts in the design references are questions beside each choice, never a value to write.

`/look_brief` is open on a blank draft and only there: the reasoning behind the look,
written first from [no-reference-design.md](no-reference-design.md) (audience, occasion,
subject world, data character, density with its why, the look, a meaning per colour, the
ladder's rationale, what was rejected). It is refused when missing, when a part is missing,
or when a part is a placeholder (TBD, n/a, "to be determined", lorem ipsum, a repeated word, the shape's own `<...>` text);
what it argues is never judged. The guide stores it as `look_brief`, provenance
`model_choice`.

## Value shapes

Every open address takes the value below; `--check` prints the line for each address it
lists, and `complete_guide.py --shapes` prints this table. `null` is an answer where the
last column says what it means, and closes the address; where it says "refused", write the
value instead. A left-out key never closes anything.

| address | value | null means |
|---|---|---|
| `/color/roles/color.(surface\|ink\|accent1)` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | refused |
| `/color/roles/color.emphasis` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | the reference marks emphasis in no colour of its own (in its ink or rule colour, or not at all): recorded under absent_roles, and an annotation names the ink or rule role instead |
| `/color/roles/<name>` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | the reference has no such colour, not even inside its pictures: the role is recorded under absent_roles, and a page that names it is refused. A colour seen only inside pasted pictures is not absent: answer it with "evidence": "pictures" |
| `/extra_roles/<name>` | {"hex": "RRGGBB", "why": "..."} (a bare "RRGGBB" also applies); add "evidence": "pictures" when it is seen only inside pasted pictures | refused |
| `/typography/roles/type.(title\|body)` | {"size_pt", "weight", "italic", "family", "alignment", "case", "ink_role", "why"}; optional "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt" | refused |
| `/typography/roles/<name>/members` | the open members only: any of "weight", "italic", "family", "alignment", "case", "ink_role", "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt", plus "why"; never "size_pt" | refused |
| `/typography/roles/<name>/line_spacing` | a multiple of the size, e.g. 1.2 ("/typography/roles/*/line_spacing": v answers every open one not named) | single spacing (drawn at 1.2 x size) |
| `/typography/roles/<name>` | {"size_pt", "weight", "italic", "family", "alignment", "case", "ink_role", "why"}; optional "line_spacing", "space_before_pt", "space_after_pt", "tracking_pt"; add "evidence": "pictures" when the reference sets such text only inside pasted pictures | the reference has no such text anywhere, not even inside its pictures: recorded under absent_roles; a page that names the role is refused. Text the reference sets only inside pasted pictures (axis labels on a chart image) is not absent: answer the value read off the pictures with "evidence": "pictures". One of type.caption, type.footnote, type.source_line must stay answered |
| `/typography/families` | {"major": "<face>", "minor": "<face>"} | refused |
| `/typography/families/substitutes` | {"<face named in the file>": "<installed face measured in its place>"} | refused |
| `/typography/scale_ratio` | a number, e.g. 1.25 | the levels are not a geometric ladder |
| `/spacing/steps/<name>` | an integer EMU, 12700 (one point) or more | refused |
| `/spacing/steps` | {"space.xs": EMU, "space.sm": EMU, "space.md": EMU, "space.lg": EMU, "space.margin": EMU, "space.gutter": EMU} (integers of 12700 EMU, one point, or more; space.xs, space.sm, space.margin and space.gutter are required: the round trip and the build read them) | refused |
| `/spacing/baseline_emu` | an integer EMU | no baseline grid |
| `/density_bands/table_rows_per_inch` | {"metric": "table_rows_per_inch", "low", "high", "median", "n"} | no table to measure |
| `/floors/<name>/floor_pt` | a number of points, never below absolute_floor_pt | no run in this family: the absolute floor holds |
| `/shape_language/corner_radii` | {"modal_radius_emu": int, "rounded_share": 0..1, "why": "..."} | refused |
| `/shape_language/icon_style` | a string, e.g. "none" or "white line icons in accent circles" | refused |
| `/imagery/register_kind` | a string, e.g. "photographs, wide crops" or "none" | refused |
| `/tables` | {"header_fill_role", "header_ink_role", "banding_role" (each a colour role, or null when the reference has none: never left out), "header_bold", "edge_rules": {"table_top", "header_bottom", "row_interior", "table_bottom", "table_left", "table_right", "column_interior": {"width_pt", "color_role"} or {"none": true}}, "cell_padding_role" (a spacing step) or, when no step is near the reference's inset, "cell_padding_role": null with "cell_padding_emu": <EMU> (a role wins over EMU), "alignment_by_column_type": {"numeric", "text"}, "totals_rule", "totals_bold" (true or false; left out, the build lists the bold it writes), "banding_phase" (0: the first body row banded, 1: the second; left out, the build lists 0), "merged_cell_convention", "why"} | refused |
| `/charts` | {"series_color_roles": [roles in order], "per_kind": {"<bar\|column\|line\|...>": {"gridlines_major": 0..1, "data_labels": 0..1, "legend_position": "b\|t\|r\|l\|tr\|none"}}, "why"} | refused |
| `/continuation` | what the reference does when a page continues onto the next, read off its pages: in words ("none seen" is an answer), or {"contd_mark": "<the mark as the reference writes it>" or null, "why": "where it is seen, or that none is"} | refused |
| `/description` | {"summary", "typography", "color", "layout", "tables", "imagery", "motifs", "not_seen": ["<what the reference was not seen doing>", ...], "tone"}; not_seen is stored with the pages it was read over, as evidence of a starting tendency, never a prohibition | refused |
| `/look_brief` | {"audience": "<who reads it>", "occasion": "<where and how it is read>", "subject_world": "<the subject's own materials and conventions, and what you borrow or leave>", "data_character": "<how much data, its shape, exhibits per page>", "density": {"target": "<how dense>", "why": "<why this content and reader call for it>"}, "look": "<the look in words>", "colour_meanings": {"<color role>": "<the one thing it means across the deck>", ...}, "type_ladder": "<why the ladder is what it is, from the densest page>", "rejected": [{"what": "<a look or device considered>", "why": "<why not>"}, ...]}; each answer a phrase of your own, never a placeholder | refused |
| `/derivation_rules` | a list of sentences | refused |
| `/titles/register` | see Titles below | refused |
| `/variety/content_pages` | a list of page numbers | refused |
| `/exhibit_habits` | never in the patch: answered by --digest DIR | refused |
| `/chrome` | a list of {"chrome_id": "chrome-1", "kind": "rule\|band\|logo\|label\|page_number\|footer\|date", "box_in": [left, top, width, height] (inches on the page), "slides_present": <pages it is on, at least half the reference's to be drawn>, and as the kind needs: "text" (label, footer, date; "<page number>" marks the number), "text_style": {"family", "size_pt", "bold", "ink_hex"} (every text kind, page_number included, all four), "fill_hex" or "fill_role" (band; a logo placeholder), "line_hex" or "line_role" with "line_width_pt" (rule; a logo placeholder drawn as a line), "image_path" (logo), "anchor": "slide_top\|slide_bottom\|slide_left\|slide_right", "rotation_deg", "carries_content" (a band the page sets content on: a title band), "why"}. Nothing is filled in for you: the width, colour and text style the emitter would otherwise fall back on are refused by name when left out | refused |
| `/composition` | {"archetypes": [{"archetype_id": "arch-1", "slides": [page numbers], "description": "<the arrangement in words>"}], "why"} | refused |
| `/notes/<name>` | a string | refused |
| `/reference/page` | {"width_emu": int, "height_emu": int, "why": "..."} (a guide made with no reference: the page size you choose) | refused |
| `/spacing/margins` | {"left": {"emu": int}, "right": {"emu": int}, "top": {"emu": int}, "bottom": {"emu": int}} (EMU, 0 or more) | refused |
| `/typography/bullets` | {"<level>": {"glyph": "<glyph>", "font": "<face>", "indent_role": "space.<step>", "hanging_indent_role": "space.<step>"}}, or {} for text set without bullets | refused |

Where the honest answer is that the reference has none (no green for `color.positive`, no
kicker), answer `null`: the guide records the role under `absent_roles`, and a page that
names it is refused with that reason. Do not borrow another role's colour to fill the
slot.

`null` means none anywhere, pictures included. A reference that pastes its exhibits as
pictures still sets axis labels, data labels and emphasis marks in them: answer those
with the value read off the pictures and `"evidence": "pictures"` (recorded as `seen_in:
pictures`, so the report can say the value was read at camera precision). A `null` for
`type.axis_label` or `type.data_label` is refused when a digest record answers
`axis_labels` or `value_labels` true, since native charts would then have no role to set
them in.

`color.emphasis` is the reference's look-here colour: the outline box round a figure, the
circle, the highlighted bar. It is always open (no hue band decides it) and is not
`color.negative`, which colours a bad value; annotations take it. `null` there says the
reference marks emphasis in its ink or rule colour, or not at all.

Many open `line_spacing` addresses (one per role) usually share one answer:
`"/typography/roles/*/line_spacing": 1.2` answers every open one the patch does not name,
and a named one keeps its own answer. It closes only open addresses. The number is a
multiple of the size, and 1.0 is NOT single spacing: single spacing draws at 1.2 x the
size, so a reference set single-spaced is answered `null` (or 1.2), and 1.0 sets every role
tighter than the reference (jazz: answered 1.0, every role drew tighter).

The table lists the value each address takes when it is open; `--check` lists which are
open. A `/tables` or `/charts` the draft observed is not open, and a patch for it is
refused with its evidence. `why` is accepted everywhere a value is an object, `/members` included, and is kept
as provenance. A run applies every address it can and reports every refusal at once,
numbered; the guide is written only when none is left.

## Description and derivation rules

Write `/description` (summary, typography, color, layout, tables, imagery, motifs,
`not_seen`, tone; `not_seen` is what you did not see the reference do, stored with the pages
it was read over, "icons: on 0 of 12 pages", a tendency to weigh and never a rule; the old
`never_does` is refused by name) and `/derivation_rules` (how the palette and the type ladder extend to
roles the reference never showed). You read these back while designing; write them for
yourself, from what you saw.

## Floors

`floor_pt` is the smallest size the reference uses per family; the solver never descends
below it. A size set on two or more pages counts even when the Tukey fence would trim it
(source lines that are 10 of 44 annotation runs set the floor at 8.0, not the fence's
9.0); a size on one page under the fence is trimmed, and turned text is never a sample.
When the body floor equals the body size there is no headroom: density comes from
arrangement and content. Table text is its own family, `table` (`type.table_header`,
`type.table_cell`): its floor is the smallest text the reference sets in native table
cells, so a dense reference's 7pt tables do not wait on its 12pt body. A reference with
no native table text takes its body floor as the table floor (`inherited_from: body`: the
smallest running text it sets is the only evidence); where its tables are pictures,
measure them (below) and the table floor drops to their size. You may lower a floor in the completion when the reference's
captions show a smaller size in use, never below `absolute_floor_pt` (7.0pt, measured on
two screen media by one rater for Arial and Calibri; print was not measured, so for a deck
that will be printed keep the reference's own floor).

`/tables/picture_text` measures the size a reference sets its own tables at where they are
not native tables: `{"pictures": [{"id": "image42.png", "slide": 13, "face": "Calibri"}],
"why": "..."}` for pictures in a .pptx (ids from `images.py list`), or `[{"page": N,
"bbox": [x0, y0, x1, y1], "face": "..."}]` in PDF points from the top-left for a PDF. You
name which pictures or regions are tables and the face you read; the size is measured
(`images.py textsize`: a PDF region's text layer when it has one, which is exact, else its
pixels). The table floor (`layout.table_floor_pt`, the build and `validate --emit` alike)
drops to the smallest, never below the absolute floor. Measured on jazz: 7.8 and 8.3pt
pictures took the table floor from 12pt to 8.0pt and the dense comps pages fit.

A role you add (`/typography/roles/<new>`) clears a floor family: name it with
`"floor_family": "body|annotation|display|chart|table"` in the role's answer (a second
table style, a grid cell, is `table`); left out, it is
the body family and the completion lists that under `completion.defaults_taken`. A core
role's family is fixed.

## Titles: /titles/register

The draft lists every page title found by position (text, characters, words, lines, and
the block directly above or below it) with median, p90 and max. Read each one on the
render and answer:

```json
{"/titles/register": {
  "per_title": {"<slide>": "topic|claim|question" or {"other": "<the register in words>"}},
  "companions": {"<slide>": {"above": "kicker|section_tag|exhibit_label|status_tag" or {"other": "<the block in words>"},
                             "below": "subtitle|units_line|lead_in" or {"other": "<the block in words>"}}},
  "claims_elsewhere": {"<slide of a topic title>": "where the page states its claim, or null"},
  "why": "..."}}
```

Every listed title and every listed companion is named; a block the reader found below a
title that is really the first cell of a table is `{"other": "first cell of the table"}`. A
title none of the registers names (a label and a figure, "Topic: claim") is
`{"other": "..."}` in your words, and so is a block none of the companion terms names; a
bare `"other"` is refused in both (and in a page library's `title_register`, the same
rule). The finalizer counts the registers and companions, `other` among them, and lists
the words under `other_in_words` and `companions_other_in_words`; the plan check and the build report your titles against
those counts and lengths.

## Exhibit habits: the digest

```bash
python3 scripts/gallery.py digest "$REF" --out "$DECK_WORK/ref/digest" --guide "$DECK_WORK/ref/draft.json"
```

Look at every page, content crop and candidate crop (a title or chrome leaf inside a
content crop is still drawn; the stub names it under `also_draws`). Copy
`digest.stub.json` to `digest.json` in the same directory, leave the stub as cut, and in
the copy replace each page's `exhibits: null` with records in the stub's
`record_template` (an empty list states the page has none; one candidate may hold several
exhibits). Each record is your own words, after looking at the crop; nothing is chosen
from a list, and the words are checked for being there (a phrase of at least three words;
`what` and `marks` at least one, since an exhibit may mark nothing: "nothing ringed"),
never for what they say:

- `what`: what the exhibit is, its form and what it is made of;
- `message`: the one thing a reader takes from it;
- `how_drawn`: what is compared against what, order, colour, labels, legend, gridlines,
  number formats, as the reference does them;
- `marks`: what the reference marks on it and how, where the claim lives, and whether words
  beside the mark say what it marks; or that it marks nothing;
- `chart_or_table`, `axis_labels`, `value_labels`: true or false, read off the page.

Each stub page also carries `file_facts`: what the file itself states (the exhibit
structure and every mark drawn on content, with its geometry, what it sits on and whether
it carries text), read by the extractor. That, not your words, is what a reference precedent
for an unlabelled mark is checked against (`explained_by: {"reference_precedent": {"slide":
N}}`: slide N's file draws a mark of the same geometry with no text of its own, on the
same kind of host: a native chart for a mark on a chart, a native table or a structure
the reference built from shapes for a mark on a table). A ring
inside a pasted picture is pixels: describe it in `marks`; it is no precedent. On every
page holding a chart or a table, answer
the page's `source_line`: `true` when it carries a source or note line naming where its
figures come from, `false` when not; leave it `null` on other pages. The finalizer counts
them (`exhibit_habits.source_lines`) and prints the count under `reference_habits`; the build
warns on a data page without a source line where at least half of the reference's data pages
carry one, or where the habit is unmeasured (fewer than three data pages), quoting the
reference's count; the report answers it. A page with a source line is never a departure, and
nothing here refuses (build_deck.py `source_line_problem`; build-report.md). Answer with `--digest $DECK_WORK/ref/digest`: a page dropped,
repeated or added, a candidate added and a record repeated are each refused by name, and a
patch value for `/exhibit_habits` is refused. The finalizer counts the source lines and
keeps the records as you wrote them; it computes nothing from your words. The reference's
exhibit structure variety is read from the file by the extractor, not from the digest.

## Content pages: /variety/content_pages

The draft proposes which pages are content (library.py's triage: cover, divider,
disclaimer, hidden and generated pages are not). On a PDF no divider or disclaimer is
proposed, so a contents page or a letter counts as content until you answer. Look at the
renders and answer with the list of content pages, e.g. `[3, 4, 5, 17]`. A page not in the
sequence, a hidden page, a duplicate, an empty list or a non-list is refused by name. The
reference's variety is re-measured over your list on every completion.

## Worked completions

`examples/keybank.completion.json` (a pptx reference with no native tables or charts) and
`examples/mckinsey-pdf.completion.json` (a vector PDF: McKinsey's 17-page board discussion
document for CalSTRS, 2024, from a public board packet; it is not under `refs/`), each with its digest under
`examples/digests/`. Both apply cleanly to the current extractor's drafts with nothing left
open. They show the shape of an answer; they are not answers for another deck, and an
evaluation on either deck holds them out.
`examples/no-reference.completion.json` answers a blank draft: a whole look chosen for a
three-page deck with no reference, every answer with its why.
`examples/no-reference-credit.completion.json` answers one for a dense two-page credit
book, its look brief written first and the guide made from it.
