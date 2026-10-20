---
name: pptx
description: "Use whenever a .pptx or a PDF deck is given as the style to follow, or a dense pitch book, board deck, CIM, consulting or management presentation must be built or extended as a .pptx. Covers reading a reference deck's style (fonts, colours, spacing, chrome, composition, register) with provenance, completing what it never showed, planning dense pages, solving every page with measured text fit, emitting on the reference's own master (or a constructed one for PDF references), building net-new components that still obey the style, and judging the result from outside the generator. Also covers reading, templating, duplicating, deleting and validating .pptx files."
---

# Decks in any reference's style, dense and measured

A reference deck carries its house style in three forms and this skill uses all three:
numbers (every font, size, colour, gap and rule, read with inheritance resolved and kept
with provenance), words (a description you write after looking), and pictures (renders,
cropped components, one exemplar per composition family). You decide intent: what each
page says, how it is composed, what to complete where the reference is silent, what a
new component should look like. Scripts do what judgment cannot: resolve OOXML, measure
text, solve geometry, write a valid package, and judge adherence from outside.

Every value in a generated deck is a token role resolved through the guide. A literal
colour, size or coordinate in a slide spec is refused. That is what lets a component the
reference never showed come out in the reference's style.

All commands are relative to this skill's directory. Work in a directory of your own
(`work/`), never inside the skill.

## 1. Decide the path

| Situation | Path |
|---|---|
| A .pptx reference is given | Full path: 2 to 8 below. The deck is emitted on the reference's own master and layouts. |
| A PDF reference is given | Same path. Extraction reads less (no shape kinds, no layouts); chrome is mined from recurring lines; the template is constructed; chrome is drawn. Section 2.3. |
| The reference is a scanned PDF | The extractor flags `reference.text_layer.status: suspect`. Tokens from it are not evidence: complete the guide from the renders, say so in the report, and ask for the native deck. |
| Add pages to an existing deck in its own style | Extract from that deck, then `pptx_tools.py template --keep` to carry the pages you keep, and build the new ones (section 8). |
| Read, split, duplicate, validate a .pptx | `pptx_tools.py` (section 8). |

## 2. Intake: render, extract, gallery

```bash
python3 scripts/render.py ref.pptx --out work/ref/renders --width 1600 --grid
python3 scripts/extract_style.py ref.pptx -o work/ref/draft.json --report work/ref/draft.md
python3 scripts/gallery.py ref.pptx --out work/ref/gallery --guide work/ref/draft.json
```

Look at `work/ref/renders/grid.png` once, then read `work/ref/draft.md` in full. It is
the evidence digest: size levels with votes, the role table with provenance, colour
pools by use, spacing steps and margins, composition families, chrome, motifs, register
and density bands, floors, and the list of what is still open. Then open
`work/ref/gallery/MANIFEST.md` and look at every exemplar and the crops whose captions
name something the digest cannot (a recurring banner, a composite, a chart treatment).

Read `work/ref/renders/fonts.json`. A face rendered as a `metric_alias` (Arial as
Liberation Sans) is layout-faithful and visually not: never copy letterforms from such a
render. A face marked `substituted` makes the render useless as evidence of fit.

### 2.1 What the digest cannot see

- `type.body` is the most frequent size level. When two or three levels are close in
  votes (the levels table shows it), the house writes at several sizes and your pages
  must too: match the size histogram, not only the role.
- Density bands are the house's own range (10th to 90th percentile of words, elements
  and covered area per page). A page below the band is sparse for this house; above it
  is denser than the house ever goes. Aim at the upper half for a pitch book.
- The composition families list which pages share an arrangement. Vary across them.
- Hidden slides are walked as evidence (a hidden page still shows how the house sets
  type). The digest's notes list them; when one is an off-style leftover, delete it
  from a copy with `pptx_tools.py delete` and extract again.

### 2.2 PDF references

Most public pitch books are PDF and most of those are not vector exports: of the 19
reference PDFs this skill was measured on, 8 are page images inside a letter-size print
(an EDGAR exhibit printed from a browser, a filing with the deck bound in, a scan with an
OCR layer). Their text layer is browser chrome, searchable-text blocks or OCR output,
and mining it gives a house of 1pt Times. So the extractor triages every page first and
the digest says which class the deck is:

```bash
python3 scripts/ooxml.py triage ref.pdf          # the per-page table, before anything is mined
```

- `vector` and `vector_with_image` pages carry real type: the extractor mines them as it
  mines a pptx, minus placeholders, bullets, layouts, chart parts and table rules, which
  it lists as open. A slide-shaped page with a pasted chart image is still a vector page.
- `raster_wrapper`, `raster_ocr` and `raster_only` pages are images: nothing on them is
  type evidence. When they are the majority (`deck_class: raster`) the draft opens every
  text-derived address, sets the page size from the image box (a letter-ratio image is a
  deck printed to letter, 11 x 8.5 in; a 4:3 one is 10 x 7.5) and names the next step:

```bash
python3 scripts/raster_style.py ref.pdf --out work/ref/raster [--dpi 100]
```

  which renders the raster pages, crops each to its slide box and measures what pixels
  can still tell: the palette by painted area, the text ink as the modal dark pixel
  colour, chrome as the pixels that hold one colour on half the pages (rules, bands,
  logo block, page-number area, with a `chrome-mask.png` to look at), margins by ink
  extents, and the line pitch by autocorrelation, with a body size estimate from it.
  `raster.patch.json` applies through `complete_guide.py` with provenance
  `raster_inference` at confidence 0.5; `raster.md` names the dpi and the size band a
  pixel measurement carries. Faces cannot be read from pixels: look at the page images
  next to fc-match candidates and name the family yourself. Sizes come from the run
  heights table and your eyes; the raster body estimate was within 0.3pt of the truth on
  a deck rendered and re-measured, and within the stated band on a 104 dpi scan.
- `other_size` pages (a memo or filing text bound in front of the deck) are excluded;
  `--pages 7-60` restricts the extraction to a range you choose from the triage table.

### 2.3 Fonts the sandbox lacks

The solver measures with the font files it has (`fc-list`). If the reference's face has
no metric alias here (Arial, Calibri, Cambria, Times New Roman and Courier New have one),
the solver refuses rather than measure another face under that name. Record a stand-in
under `typography.families.substitutes` in the completion (`{"Georgia": "DejaVu Serif"}`):
the file names the real face for PowerPoint, measurement uses the stand-in, and the
report says so.

## 3. Complete the guide

The draft's `unresolved` list is exactly what you answer. Write `work/ref/completion.json`
as `{"<open path>": value, ...}` and fold it in:

```bash
python3 scripts/complete_guide.py work/ref/draft.json --check          # what is open
python3 scripts/complete_guide.py work/ref/draft.json work/ref/completion.json -o work/ref/guide.json
```

Rules the finalizer enforces, and the ones only you can keep:

- Answer open paths only. An observed or inferred value is never overwritten; if you
  think one is wrong, say so in the report and fix it upstream (the reference, or the
  extractor), never by patching over it.
- Every value comes from THIS reference. Low confidence beats convention: a chartless
  deck gets a chart language derived from its palette and register, not a stock one.
- Colours enter only under `/color/roles/<role>` or `/extra_roles/<name>` as hex, with a
  `why`. Everything else refers to roles. A new size may not sit below the family floor.
- Renders are a camera for colour, proportion and position. They are not evidence for
  text fit, line spacing, padding or rule weight: those are measured or they are open.
- Write `/description` (summary, typography, color, layout, tables, imagery, motifs,
  `never_does`, tone) and `/derivation_rules` (how the palette and the type ladder
  extend to roles the reference never showed). These are what you read back while
  designing; write them for yourself.
- Floors: `floor_pt` is the smallest size the reference uses per family and the solver
  never descends below it. For a reference whose body floor equals its body size (it
  never wrote smaller body text) there is no headroom: density then comes from
  arrangement and content, not from shrinking. You may lower a floor deliberately in the
  completion (`/floors/body/floor_pt`) when the reference's own captions show a smaller
  size in use; never below `absolute_floor_pt` (7.0pt, measured).

Example completion: `examples/keybank.completion.json` (a pptx reference with no tables
or charts) and `examples/mckinsey-pdf.completion.json` (a PDF reference).

## 4. Make the template

```bash
python3 scripts/pptx_tools.py template ref.pptx -o work/tpl.pptx            # pptx reference
python3 scripts/pptx_tools.py blank -o work/tpl.pptx --width-emu W --height-emu H   # PDF reference, W and H from guide.reference.page
```

The pptx template is the reference with every slide removed: masters, layouts, theme and
chrome intact (deckgen E18 measured that PowerPoint opens and re-saves such packages
without repair and draws chrome exactly once per slide). Page numbers and footers that the
reference carried on its slides are copied from the layout onto each new slide.

For a PDF reference the template is blank at the reference's page size, and
`build_deck.py --chrome draw` paints the guide's chrome (rules, bands, footer labels, a
page-number field) and the surface colour on every slide.

## 4.1 Prove the chain on the house's own page

Before writing a page of your own, round-trip one of the reference's: import a slide
into a spec of roles and weights (no coordinates survive), build it on the template,
and read the judge.

```bash
python3 scripts/import_slide.py ref.pptx --slide 3 --guide work/ref/guide.json -o work/ref/rt3.deck.json
python3 scripts/build_deck.py work/ref/rt3.deck.json --guide work/ref/guide.json --template work/ref/template.pptx \
        -o work/ref/rt3.pptx --reference ref.pptx --others <two other decks> --renders work/ref/rt3-renders
```

The distance must sit inside the house's own spread (the leave-one-out distance of
each reference slide to the rest; `fingerprint.py calibrate` prints it, keybank's is
0.08 to 0.13). Then LOOK at the render next to the reference slide: on keybank the
judge said 0.083 while the labels were still black and left-aligned, because the
reader had missed the shape-style text colour on both sides. The render caught it; the
number did not. The imported spec is also your seed: a page that starts from the
exemplar of its composition family begins inside the house's bands and columns.

## 5. Plan the deck

Read `references/design/storyline_logic.md` and `title_and_message_writing.md` first.
Then write the plan as a list of pages, each with: an assertion title (one line in the
reference's title band; the solver refuses a title the band cannot hold), the one
message, the exhibit that proves it, the supporting text, the data it needs, the
composition intent (which element dominates), and the boundaries where the page may
split if it will not fit. Vary composition across pages unless content demands
repetition; the reference's families tell you its own range.

Numbers: use the user's figures byte for byte. Never invent a number; a figure you do
not have is a placeholder the user must fill, named as such in the report.

## 6. Write the page specs

A page is a tree. Regions lay out children with `flex` (direction, gap role, pad role,
align, justify, weights) or `grid` (rows, cols, gutter role, areas). Elements are `text`
(paragraphs with a type role, text and bullet level), `table` (columns with a value
kind, rows, header rows), `chart`, `image`, `rule`, `rect`, or a `component`. Everything
is a role: `type.body`, `color.accent1`, `space.md`. The full grammar with one worked
example is the docstring of `scripts/layout.py`; a complete four-page deck spec is
`examples/keybank-section.deck.json`.

Before writing text, ask the solver what fits:

```bash
python3 scripts/layout.py capacity work/deck/s03.spec.json --guide work/ref/guide.json
```

It prints lines and characters per region per role from the measured ruler. Write to
that budget. Read `references/design/deliberate_composition.md` (every page),
`ib_slide_composition.md` or `consulting_slide_composition.md` (by genre),
`dense_table_design.md` (tables), `chart_design.md` (charts), `typography_hierarchy.md`
and `decoration_and_motifs.md`. Where a doctrine and the reference disagree, the
reference wins.

Conventions the build enforces:

- The first element of a page whose role is `type.title` is held to the band above the
  reference's top rule when it has one. A two-line title the house never wrote is refused;
  shorten it or move the second clause into a lead sentence.
- Chrome zones from the guide are reserved automatically; content never runs under the
  footer rule. Pass `page.reserved_zones` yourself only to override.
- A region may carry `fill_role` and `pad_role`: it becomes a filled box with padded
  children (a takeaway panel). Text inside takes `ink_role` on its paragraph.
- Emphasis runs (`styling.<id>.paragraphs.<n>.runs` with `emphasis: true`) are measured
  at the paragraph's regular weight; keep them short or give the box slack.
- Bullet indents come from the reference's own bullets; a reference without bullets gets
  the spacing scale's progression (sm, md, lg).

## 7. Build, read, add, build again

```bash
python3 scripts/build_deck.py work/deck/deck.json --guide work/ref/guide.json --template work/tpl.pptx \
  -o work/out/deck.pptx --reference ref.pptx --others <two or three other decks or PDFs>
```

One command solves every page with measured fit, emits on the template, validates the
package, renders every page, and judges the deck against the reference and the other
houses. Read `work/out/deck.build.json`:

- `status: fit` with `scale` and `violations: []` is a page that fits at that type scale.
  Scale below 1.0 means the solver stepped the whole type ladder down toward the floor;
  say so in the report if it went below 0.9.
- `status: unfittable` names the smallest admitted scale, every violation, and for each
  table the row prefix that would fit. Nothing is dropped silently. Your moves, in this
  order: re-arrange (two columns instead of one, a table beside the chart instead of
  below it, a compact component variant), cut words, split the page at a declared
  boundary (the table's fitting rows become page one, the rest page two with the
  continuation convention from the guide). Then build again.
- `judge.total` is the fingerprint distance to the reference; `judge.others` the same
  distance to the other houses. `nearest_is_reference: false` is a failed page set.
  `judge.components` names what is off: `size_hist` and `size_ladder` (sizes off the
  reference's histogram), `fills` and `text_colors` (palette), `margins`, `kinds`.

Density is a loop, not a setting. Add content to a page, build again, read the report.
When a page fits with room at the reference's upper density band, add the next item.
When it does not fit at the floor, split or re-arrange. Keep going until every page sits
inside the band and every page fits.

## 8. Components the reference never showed

When nothing in `components/` draws what a page needs (a football field, a bridge, a
league table with tombstones, a tracker), write one. Read `components/README.md`; the
contract in brief: `components/<kind>/expand.py` exposes `expand(data, box, guide)` and
returns a region tree in the page grammar with roles only; proportions are flex weights
from the data (a bar's length is a weight, never an EMU); heights that must be fixed are
spacing steps read from the guide; the variant is chosen by what the box can hold.
`spec.json` declares the data schema, the size domain and four test boxes: three shown
and one held out with different data.

```bash
python3 scripts/component.py check football_field --guide work/ref/guide.json --template work/tpl.pptx --out work/components --reference ref.pptx
python3 scripts/component.py admit football_field --out work/components
```

Look at the contact sheet before admitting. A component is admitted only when all four
boxes solve with no violation; the held-out case is what stops one tuned to its examples.
Use it in a page as `{"type": "component", "id": "ff", "kind": "football_field", "data": {...}}`.

## 9. QA: what to look at and what each failure means

The build already ran `pptx_tools.py validate` (package integrity, relationship targets,
content types, slide ids, shapes inside the page, charts parse). Then:

1. Look at every render at full size. The defects to look for, in order: text cut at a
   box edge; two elements sharing area; a source line touching the footer rule; uneven
   gaps; a title that drifts between pages of one kind; chart labels styled differently
   from chart to chart; a figure split from its unit; placeholder text left over. The
   solver prevents the first two on measured elements; charts and images are the places
   they still appear.
2. Review each page against the description you wrote and the exemplars, as located
   findings: name the element and the change (`takeaway: the box competes with the
   table; drop the fill, keep the rule`), never a score. Then the generated-deck tells in
   `references/design/deliberate_composition.md`: card grids, equal tiles, KPI tiles,
   rounded everything, centred text, three of everything, uniform spacing. Fix, rebuild.
3. Read `judge` in the build report. A deck nearer another house than its reference is
   not done; the component list says where. Real case: the McKinsey PDF pages scored
   0.360 against 0.378 for the nearest other house, with `size_hist` 0.718 and `fills`
   0.977 carrying the distance. The reference writes at 11, 16 and 18pt while the
   pages sat on the 12pt body role, and it paints navy bands the specs never asked
   for. The fix is in the specs (use the levels the histogram shows, add the band),
   not in the guide.
4. Compare pages with each other, not only each with itself: same title position, same
   chart text, same source line treatment.

Renders come from LibreOffice. Line breaks in the file are the solver's measured breaks
(written as literal breaks), so what you see is what PowerPoint draws for text; charts
and tables can still differ slightly between the two renderers.

## 10. Working on an existing deck

```bash
python3 scripts/pptx_tools.py text deck.pptx            # text per slide, tables as rows
python3 scripts/pptx_tools.py layouts deck.pptx         # masters, layouts, placeholders with boxes
python3 scripts/pptx_tools.py template deck.pptx -o work/tpl.pptx --keep 1,4,7   # reuse pages
python3 scripts/pptx_tools.py duplicate deck.pptx --slide 3 -o out.pptx --after 5
python3 scripts/pptx_tools.py delete deck.pptx --slides 2,5 -o out.pptx
python3 scripts/pptx_tools.py clean deck.pptx -o out.pptx
python3 scripts/pptx_tools.py validate out.pptx --render
```

Slides the deck already had are not re-solved or restyled: they are the reference. New
pages are built on the template that keeps them and appended. To replace one page,
delete it, build the new one, and splice with `duplicate`/`delete` order kept: structure
first, content second.

## 11. Hard rules

- No literal colour, size, font or coordinate in a spec; roles only. The emitter refuses.
- Nothing is dropped to make a page fit. Unfittable is a report and a choice, never a cut.
- Never generate below `max(floor_pt, absolute_floor_pt)`; the solver cannot, and the
  completion may not set a floor below the absolute one.
- Observed values are never overwritten by completion.
- Numbers come from the user's data. Source lines are written from the sources used.
- The reference wins over any doctrine in `references/`.
- A deck nearer another house than its reference is not finished.
- Report what was measured, what was completed from judgment, what was substituted (fonts),
  and what the user must supply.

## 12. Gotchas, each measured once

- LibreOffice fits more text than PowerPoint on 92 of 600 measured boxes; the solver's
  ruler shrinks the width budget (5,933 EMU with the Pillow ruler, 20,234 with HarfBuzz)
  so that a measured line never runs long in PowerPoint (deckgen E16).
- Line pitch is 1.2 times the size, font independent (measured on 7 families); font
  tables are wrong by up to 20%.
- Table row heights in the file are minimums; PowerPoint realises lines times 1.2 times
  the size plus the cell margins (E38). The fitter writes exactly that.
- A deck's theme is reached through the master's relationship, never by globbing theme
  parts: notes and handout masters carry the stock palette.
- Colour maps apply before the theme lookup; a slide or layout may override the map.
- A bullet glyph needs its bullet font (Wingdings squares render as a section sign
  without it); the extractor records it and the emitter writes it.
- Hidden slides are not exported by the renderer; the gallery counts and skips them.
- A figure and its unit, a currency mark and its figure, and a period prefix and its
  year (`$1.2 bn`, `EUR 40 mm`, `FY 2024`, `12.5 %`) never break across lines: the ruler
  treats that space as unbreakable and the emitter writes the measured lines, so the file
  cannot re-break there.
- A scanned PDF's text layer is not evidence; the triage (2.2) decides per page, and the
  size of the deck is the size of the paper it was printed to, not the letter page around
  the image.
- An interrupted `soffice` leaves a lock in its profile; every render uses a fresh profile.

## 13. Files

| Path | What it is |
|---|---|
| `scripts/ooxml.py` | the OOXML and PDF reader with inheritance resolved; `triage` for PDFs |
| `scripts/extract_style.py` | reference to guide draft with provenance and the open list |
| `scripts/gallery.py` | component crops, exemplars, skeletons, manifest |
| `scripts/complete_guide.py` | folds your completion into the draft under the rules |
| `scripts/render.py` | LibreOffice to PNG, font substitution report, contact sheet |
| `scripts/raster_style.py` | what a scanned reference can still tell: palette, ink, chrome, margins, line pitch |
| `scripts/layout.py`, `scripts/textfit.py` | solver, measured text, table fitter, scale descent, capacity |
| `scripts/emit_pptx.py` | resolved pages to slides on the template |
| `scripts/build_deck.py` | solve, emit, validate, render, judge, in one command |
| `scripts/component.py` | component contract check and admission |
| `scripts/import_slide.py` | a reference slide into a spec of roles, for the round trip and as a seed |
| `scripts/fingerprint.py` | the style judge: distance to a house, calibration |
| `scripts/pptx_tools.py` | text, layouts, template, blank, duplicate, delete, clean, validate |
| `components/` | the contract and admitted components |
| `references/design/` | nine doctrines, reference-agnostic (the reference always wins) |
| `examples/` | a four-page deck spec, two completions, a PDF deck spec, a round-trip spec, and `proofs/` with the build reports and raster reports behind the numbers in this file |
| `refs/MANIFEST.md`, `refs/fetch.sh` | eleven public bank and consulting decks for calibration |
| `PORT_AUDIT.md` | every piece ported from deckgen, its assumption, and how it was checked |
