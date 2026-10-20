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

Slides this skill generated carry a pptx-skill origin tag; `extract_style.py` and
`gallery.py` skip them by default and say how many (`--include-generated` keeps them,
only when you mean to treat your own output as evidence). `/shape_language/corner_radii`
is observed from the file (the modal roundRect radius and the share of rounded shapes):
never complete it from renders.

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

`render.py` and the solver read metric aliases from one table (`textfit.py`, fontconfig's
17 binding="same" classes). Helvetica is not an alias of Liberation Sans: without Nimbus
Sans or TeX Gyre Heros installed, a Helvetica deck reports `substituted`, and its renders
are not evidence of fit. `fonts.json` lists per face `uncovered_count` and up to ten
`uncovered_sample` codepoints, characters the deck sets in that face which the rendered
font file cannot draw; the gallery refuses with `uncoverable_characters` when any face
has one, even if LibreOffice drew the glyph from a fallback face, because a crop in
another face teaches the wrong letterforms. Install a face that covers the script first.

## 3. Complete the guide

The draft's `unresolved` list is exactly what you answer: every address in it, and no
other. An address you leave out is as wrong as one you invent. Write
`work/ref/completion.json` as `{"<open path>": value, ...}` and fold it in:

```bash
python3 scripts/complete_guide.py work/ref/draft.json --check          # what is open, and which core addresses
python3 scripts/complete_guide.py work/ref/draft.json work/ref/completion.json -o work/ref/guide.json
```

Rules the finalizer enforces, and the ones only you can keep:

- Answer open paths only. A key outside `unresolved` is refused. The only exceptions,
  always writable, are `/description`, `/derivation_rules`, `/continuation`,
  `/typography/families/substitutes`, `/notes/*`, a new `/extra_roles/<name>`, and a new
  type role at a size the levels table shows. A key whose target is observed or
  deterministically inferred is refused with its provenance and evidence; a whole
  section such as `/tables` is no exception when the deck has one. If you think an
  observed value is wrong, say so in the report and fix it upstream, never by patching
  over it.
- The core must close: type.title, type.body, color.surface, color.ink, color.accent1,
  and at least one of type.caption / type.footnote / type.source_line. If any is still
  open after the patch the guide is refused; `--allow-partial` writes it and lists the
  open core under `completion.core_open`, for inspection only.
- Role names are the extractor's, not yours: on keybank `color.accent1` is the observed
  light grey and the deep blue is the second accent. Bind fills and inks by what the
  draft observed, then let the build's contrast gate confirm it (white on accent1 there
  reads 1.54:1 and is refused).
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
  size in use; never below `absolute_floor_pt` (7.0pt, measured on two screen media by
  one rater for Arial and Calibri at regular and bold; print was excluded from that
  measurement, so for a deck that will be printed never go below the reference's own
  `floor_pt` either).

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
judge said 0.083 (0.056 at HEAD) while the labels were still black and left-aligned, because the
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

### 5.1 Every figure in a title is computed

Before writing a title or a bullet that states a figure, compute it from the exhibit's
own data: midpoints, medians, counts above or below a line. Write the computed figure.
The shipped example once said "$11.40 sits above every method's midpoint" over a field
where two midpoints were above it, and "the offer is at the top of the range" over a
table where its multiple was below the median; the build cannot catch a false sentence,
only you can, and a managing director will.

### 5.2 Seed a page from the house specimen

`examples/house/` holds deckgen's 14 house specimen pages as deck specs (comps, football
field, waterfall, Mekko, KPI band, timeline, credentials, league table, agenda, profile,
framework matrix, arithmetic chain, section divider, text plus chart); `COVERAGE.md`
names each page's family and elements. Copy the page of the family you need, replace the
content, and write a title that fits the reference's band. They were composed for a 16:9
page: on keybank's 4:3 page at 12pt only 2 of 14 fit as written (the bridge fits with its
chart crushed to 0.29 in, which is not a pass you should accept), so cut an exhibit or
split before you build, and read the unfittable report rather than forcing the scale.

## 6. Write the page specs

A page is a tree. Regions lay out children with `flex` (direction, gap role, pad role,
align, justify, weights) or `grid` (rows, cols, gutter role, areas). Elements are `text`
(paragraphs with a type role, text and bullet level), `table` (columns with a value
kind, rows, header rows), `chart`, `image`, `rule`, `rect`, or a `component`. Everything
is a role: `type.body`, `color.accent1`, `space.md`. The full grammar with one worked
example is the docstring of `scripts/layout.py`; a complete four-page deck spec is
`examples/keybank-section.deck.json`, and two bridge pages written from the chart
recipes are `examples/keybank-bridge.deck.json`.

Tree limits, each refused with its own message: node ids unique on the page; at most
400 nodes; at most 5 levels below the root (root = 0, so `root > body > col > panel >
head > text` is the deepest chain). The depth cap is deckgen's runaway bound (observed
shape nesting of 3 in its references plus 2), not a measurement of layout trees. When a
chain runs out, remove a region that only wraps one child, or merge a column into its
parent column; a filled box without padding needs no region, since a text element
takes `fill_role` and `anchor` itself.

Before writing text, ask the solver what fits:

```bash
python3 scripts/layout.py capacity work/deck/s03.spec.json --guide work/ref/guide.json
```

It prints lines and characters per region per role from the measured ruler. Write to
that budget. Read `references/design/deliberate_composition.md` (every page),
`ib_slide_composition.md` or `consulting_slide_composition.md` (by genre),
`dense_table_design.md` (tables), `chart_design.md` and `chart_recipes.md` (charts), `typography_hierarchy.md`
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

Before writing each page, look at the reference's nearest pages for that intent:

```bash
python3 scripts/gallery.py pick work/ref/gallery --intent "two column comparison table beside commentary"
```

It prints the two exemplars and three crops whose words overlap the intent most, with
their skeleton lines. Overlap 0 everywhere means the gallery has nothing for that intent
(keybank's tables are pasted images, so a table intent finds none): design from the
guide and the doctrines, not from a near miss.

A slide-layer logo, rule or label the reference pastes on every page is drawn on every
generated page in the default `--chrome auto`; chrome the layout already carries is
inherited, never redrawn.

### 6.1 You design every exhibit; the guide is the style

The guide is the reference's style as roles and evidence: colour roles, type roles,
`charts.series_color_roles` and `charts.per_kind` (what the reference's charts do:
gridlines, labels, legend), `tables` (header fill and ink, rules, banding), motifs. No
script turns that evidence into a design. You read it, look at the reference, and write
every design choice into the spec; the scripts resolve roles, write what the spec says,
measure and refuse.

- **Charts** are a full spec under `charts.<id>`: `type` (any python-pptx
  `XL_CHART_TYPE` name: `COLUMN_STACKED`, `BAR_CLUSTERED`, `LINE_MARKERS`, `PIE`,
  `XY_SCATTER`, ...), series with `fill_role` or `"none"` per series and per point,
  `line_role` and width, data labels per series and per point (show, position, number
  format, type role, `ink_role`, your own text), both axes (visible, line, gridlines,
  number format, reverse, min and max, tick marks, tick labels), `gap_width`, `overlap`,
  the legend or `"none"`, the chart text role and ink, the plot fill, the title.
  Colours are roles only; a literal hex is refused, and so is an unknown key. There is
  no waterfall kind and no football-field kind: they, the mekko, a bridge that crosses
  zero and labelled bars without a value axis are recipes over the spec in
  `references/design/chart_recipes.md`, as worked JSON to adapt. A line at a decision
  value (an offer price across a football field, a threshold across columns) is
  `reference_lines` (`axis`, `at`, `line_role`, `line_width_pt`, `dash`); it needs
  `plot_area` (the inner plot as x, y, w, h fractions of the chart frame, written as a
  manual layout) and that axis's `min` and `max`, so its position is computed, not
  guessed. An enumerated value written in another spelling (`nextTo`, `insideEnd`) is
  refused with this spec's spelling named. The one value written
  unasked is `c:varyColors val=0` (file safety: the renderers read its absence
  oppositely), so a pie whose slices differ names a fill per point.
- **Inks** are yours. Nothing picks an ink for a fill: a white label on a light bar is
  written white, and the build refuses the page by name. Set `ink_role` on every label
  that sits on a fill.
- **Tables**: a column may carry `width_share` (its exact share of the table width) or
  `min_width_role` (a spacing role it never narrows below); the fitter honours both,
  still measures every cell, and reports a share below a column's widest word as a
  width deficit. `emphasis_rows` need `emphasis_fill_role` (a role, or `"none"` for bold
  on the row's own ground) and may take `emphasis_ink_role`; there is no default fill.
  The guide's table look is the default, and each table may override it as roles:
  `header_fill_role`, `header_ink_role`, `banding_role`, `data_fill_role` (each a colour
  role or `"none"`), `header_bold`, `header_align`, and `align` (left, center, right) on
  a column. These drawing keys and `totals_last_row` may sit on the table element, inside
  its `table` spec or under `styling.<id>`; a key written twice with different values,
  or any key none of them knows, is refused by name. `header_role` and `cell_role` are
  the roles the solver measures and the file is written in, with nothing substituted;
  a bold header (`header_bold`, yours or the guide's) is measured bold.

Motifs the digest lists (a band, a rule, a block with a preset, roles and an anchor)
are applied by you: draw one as a `rule` or `rect` element with the motif's line or
fill role at the place the reference uses it (`slide_top` and `slide_bottom` marks
are chrome and already on the layout; `region_edge` and `element_adjacent` marks are
yours to place). There is no motif field in the page grammar.

## 7. Build, read, add, build again

```bash
python3 scripts/build_deck.py work/deck/deck.json --guide work/ref/guide.json --template work/tpl.pptx \
  -o work/out/deck.pptx --reference ref.pptx --renders work/out/renders
```

Leave `--others` alone: the judge's panel is every deck under `refs/files` (fetch them
once with `refs/fetch.sh`), the reference's twin removed by hash, scans with no type
skipped, and decks that sit inside the reference's own spread reported as the same
house rather than as rivals. A pass against two alien decks and a fail against the
sister decks is the same deck; the panel is not yours to choose.

One command solves every page with measured fit, emits on the template, validates the
package, renders every page, and judges the deck against the reference and the other
houses. Read `work/out/deck.build.json`:

- `status: fit` with `scale` and `violations: []` is a page that fits at that type scale.
  Scale below 1.0 means the solver stepped the whole type ladder down toward the floor;
  say so in the report if it went below 0.9.
- `status: unfittable` names the smallest admitted scale, every violation, and for each
  table `rows_to_fit_slide`, the body-row count at which to split the page (the
  `fitting_row_prefix` beside it is the probe-box figure the fitter worked from, not the
  cut). A title that needs two lines is named first, before any other violation, because
  every other violation on that page follows from it. Nothing is dropped silently. Your moves, in this
  order: re-arrange (two columns instead of one, a table beside the chart instead of
  below it, a compact component variant), cut words, split the page at a declared
  boundary (the table's fitting rows become page one, the rest page two with the
  continuation convention from the guide). Then build again.
- `judge.filed_under_reference` is the verdict, and it is four gates: nearest the
  reference among the panel's other houses, inside the reference's own spread
  (`house_spread.p90`, the leave-one-out distance of the reference's own pages), layout
  clean (no measured overlap between content shapes, no text shape whose paragraphs
  outgrow it: `overlap` and `overflow` in the components, each a gate at 0.2 of its
  span), and every page fit and the package valid. `judge.total` and `judge.others` are
  the distances; `same_house_on_panel` lists the decks the judge recognises as the
  reference's own house. `judge.components` names what is off: `size_hist` and
  `size_ladder` (sizes off the reference's histogram), `fills` and `text_colors`
  (palette), `margins`, `kinds` (text boxes where the house draws shapes, rectangles
  where it draws none).
- `density` per page: words, elements and covered area against the reference's bands,
  each marked `below`, `in band` or `above`. A page that fits and reads `below` on
  covered area ends half-way down the canvas: give the body region weight and its rows
  `align: stretch` so they share the content height, or add content.
- `position_drift`: an element id present on several pages whose top moves by more
  than one spacing step, with its positions. A source line at 5.5 in on one page and
  6.7 in on the next reads as two different pages.
- `component_notes`: a component admitted against another reference; run
  `component.py check` with this guide before trusting its fit.
- `chart_defaults_taken` per page with a chart: every chart choice the spec left out,
  with the value the file got (`series[0].labels: no data labels`, `gap_width: 150
  (python-pptx's chart part)`, `axes.value.line_role: no stroke written: each renderer
  reads the theme's line style, and they differ`). None of these is the house's style.
  Write each one into the spec and build again until the list is empty or every entry
  left is one you meant.
- `problems` per page, listed before the figures: tie-out warnings first, then refusals. A refusal turns a page that fit into `status: unfittable` with the refusal as `reason` (`contrast`, `no source line`, `bridge does not tie`: a chart that declares `bridge` whose totals or drawn spans do not tie to its deltas); `solver_status` keeps the geometry verdict beside it. A warning never refuses.
- `contrast` per page: every text run, every table row class and every chart text (data labels per series and per overriding point, axis labels, legend) scored WCAG 2.2 against the fill the page draws behind it (the element's own fill, else the nearest enclosing filled region, else `color.surface`; for a chart label inside a bar, slice or bubble, that mark's fill; outside it, the plot fill or the page under the chart; both when the spec left the position open). Below 3.0:1 is a violation and refuses the page; below AA (4.5:1, or 3.0:1 at 18pt or 14pt bold) is a warning. `undecidable` lists text over an image (pixels, not roles, decide that) and labels on a fill left to the renderer; `unbound` lists runs and chart parts with no ink role, which inherit the master's or the theme's colour; `nearest_pass` is the tightest pair that passed. The fix is a role change, never a literal: a muted source line inside an accent band reads 1.6:1 on keybank, and white labels on keybank's light grey bars read 1.54:1. Nothing in the emitter corrects an ink, so the ink scored is the ink drawn.
- `register` per page: `kind_counts` (text, image, shape, table, chart, line), `decoration_count` and `container_ratio` against the reference's `register_stats` bands, each `below`, `in band` or `above`. Counted as drawn: a takeaway in a filled region is one shape without text plus one bare text shape; a house that draws filled text shapes wants the fill on the text element itself.
- `repetition` at deck level: the arrangement similarity of each consecutive pair of pages (the extractor's own slide_similarity on the elements' boxes, similar at 0.5) and `runs_over_reference`, any run of look-alike consecutive pages longer than the reference's longest run of one archetype. A deck of six pages on one arrangement reads as generated even when every page fits.
- `tieouts` per page: for every table with `totals_last_row`, each number, currency or percent column's body sum against its totals cell at the cell's own decimals ($ , % x stripped, parentheses negative). A row headed median, average or mean is skipped as a statistic; a column with an n.a. cell is skipped and names the cell. A mismatch is a warning under `problems`: a subtotal inside the body or a non-total row styled as the totals row reads as a mismatch, so either compute the figure or take `totals_last_row` off that row.
- A page with a table or a chart and no paragraph in `type.source_line` or `type.footnote` is refused with reason `no source line`.

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

Admission is bound to the guide it was checked with (`guide_reference_sha256` in
`admitted.json`): the football field admitted on keybank overflowed its band on netflix,
whose 12pt floor and padding left no headroom, until the value column was sized to its
figures. Re-run `check` with every new guide; the build says so when the guide differs.
`spec.json` may name `single_line_ids`, id fragments of figures, ticks and marker labels
that must never wrap; the check fails a box where one of them did ("$1" over "4" is a
defect the solver's fit verdict does not see).

`check` first runs each test's `expand` twice in separate interpreters under PYTHONHASHSEED=0 and PYTHONHASHSEED=1 and compares the trees with keys sorted: a dict whose key order moved is not a difference, a list whose order moved is. Any difference fails the check and names the first differing path (`$.children[0].paragraphs[0].text: ...`); a set iterated into children is the usual cause. The check also fails a box with a contrast violation; the harness page's missing source line is not the component's fault. `kind` may be a path to a component directory under development, so a draft can be checked before it enters `components/`.

The library, each admitted on keybank (three shown boxes, one held-out box with other
data, two hash seeds, single-line figures, contrast, and a package that validates):

- `football_field`: valuation ranges on one shared axis, the marker drawn through every
  bar; wide or compact by measured label wrap.
- `title_block`: optional kicker, the claim, a closing hairline; the data picks the variant.
- `bullet_stack`: co-equal points in the writer's order; two columns filled down then
  across when `width // 2 >= height`.
- `kpi_row`: ranked figures, never tiles; the lead takes the first accent that reads on
  the surface at 3:1 (on keybank that is the second accent, the deep blue). Horizontal
  when every figure measures onto one line in its column, else label-left rows.

A component's ids carry `data["_id"]` as prefix, and paragraph `ink_role` and `align`
written in its tree reach the file. A component the page leaves no room for is refused
by name, never expanded into a zero-size box.

Never estimate a text width in a component (`0.6 em per character` wrapped "$8.2 to $12.4" onto two lines). `expand` receives the guide with `guide["_api"]`, the solver's own instruments: `api["text_width_emu"](guide, role, text)` is the width the whole string draws in that role at scale 1.00 (cased, tracked, bold when the role is), `api["line_pitch_emu"](guide, role)` the baseline advance, `api["paragraph_spacing_emu"]` the role's spcBef plus spcAft, `api["fit_epsilon_emu"]` the ruler's wrap margin. A text element sized to `text_width_emu + fit_epsilon_emu` stays on one line; add your own padding. `python3 scripts/component_api.py guide.json type.caption '$12.4 to $13.9'` prints the figures by hand. The functions raise on a role the guide lacks, as the solver would; do not catch and guess.

Look at the contact sheet before admitting. A component is admitted only when all four
boxes solve with no violation; the held-out case is what stops one tuned to its examples.
Use it in a page as `{"type": "component", "id": "ff", "kind": "football_field", "data": {...}}`.

## 9. QA: what to look at and what each failure means

The build already ran `pptx_tools.py validate` (package integrity, relationship targets,
one layout per slide and one master per layout, content types, slide ids, shapes inside
the page, charts parse). `validate --render` also reads the rendered page back with
pdftotext and names every paragraph that did not draw: a schema-invalid spacing value
once blanked sixteen bullets on a page that validated and judged clean. Then:

`validate --emit --guide guide.json` reads the saved package for what PowerPoint and
LibreOffice draw differently (deckgen E38, measured): a shared table edge declared
differently on its two cells (PowerPoint keeps the first-declared side and writes it
back, LibreOffice draws the heavier one, so a rule you saw in the render is gone in the
banker's copy), a stroke under 0.5pt that the guide does not itself declare (0.48px in
PowerPoint, 1.27px in LibreOffice), any gradient, a chart plot without `c:varyColors`
(the default paints one series in five theme colours in PowerPoint only), a run below
its role's floor, a typed page number where the layout carries the number field. The
emitter writes none of these; the check is for a deck you edited by hand or got from
elsewhere. Run it before handing a deck over.

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
   not done; the component list says where. Real case: the McKinsey PDF pages score
   0.335 against a house whose own pages sit at 0.12 to 0.30: not filed, with `size_hist`
   0.72 and `fills` 0.86 carrying the distance and the exec page `below` the band on
   covered area. The reference writes at 12, 14, 16 and 18pt (levels with 62 to 95 votes
   each) while the pages sit on the 12pt body role, and the page ends half-way down the
   canvas. The fix is in the specs (add roles at the levels the histogram shows, which
   the completion now allows, and give the body rows weight), not in the guide.
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

Every generated slide carries an origin tag (a `p:tags` part with `pptx-skill` =
`generated`, which deckgen measured surviving a PowerPoint save). The extractor and the
gallery skip tagged slides, so a deck you added pages to can serve as its own reference
again without learning from your pages; `--include-generated` overrides.

## 11. Hard rules

- No literal colour, size, font or coordinate in a spec; roles only. The emitter refuses.
- The guide is the style; you design every exhibit from it. Chart type, fills, inks,
  axes, labels, legend, gap and overlap, table emphasis fills and column shares are
  written in the spec by you, never left to a script. The build measures and refuses
  (fit, contrast, overlap, overflow, tie-outs, the judge); it never decides or corrects
  a design choice. `chart_defaults_taken` lists what you left to defaults: an exhibit
  is not finished while that list holds a choice you did not mean.
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
- A master that spaces paragraphs by percent (`spcPct`) is read as points at the
  boundary (a share of the 1.2 x size line); nothing negative reaches the guide, and the
  emitter never writes a negative `spcPts`, which LibreOffice answers by drawing nothing.
- A shape's `p:style/a:fontRef` sets its default text colour, above the master's default
  and below the run's own; a table style's `tcTxStyle` colour child does the same for
  cells. White labels on filled rectangles and white header rows read as black without
  these.
- A scanned PDF's text layer is not evidence; the triage (2.2) decides per page, and the
  size of the deck is the size of the paper it was printed to, not the letter page around
  the image.
- An interrupted `soffice` leaves a lock in its profile; every render uses a fresh profile.
- LibreOffice 24.2 draws nothing for the first XY scatter series when a later series has
  more points (10 before 12, and 2 before 12, measured); the emitter writes every
  scatter and bubble series with the group's largest point count, the extra points
  blank, and all series draw.

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
| `references/design/` | nine doctrines, reference-agnostic (the reference always wins), and `chart_recipes.md`, worked chart specs to adapt |
| `examples/` | a four-page deck spec, a two-page bridge spec, two completions, a PDF deck spec, a round-trip spec, and `proofs/` with the build reports and raster reports behind the numbers in this file |
| `refs/MANIFEST.md`, `refs/fetch.sh` | eleven public bank and consulting decks for calibration |
| `PORT_AUDIT.md` | every piece ported from deckgen, its assumption, and how it was checked |
