# Page specs: the grammar, the conventions, and where to look before writing

## Contents
- The tree
- Limits
- Capacity before text
- Pictures: logos, icons and the user's files
- Conventions the build enforces
- Looking before writing: the reference's gallery
- Looking before writing: the page library
- House specimen pages
- Motifs

## The tree

A page is a tree. Regions lay out children with `flex` (direction, gap role, pad role,
align, justify, weights) or `grid` (rows, cols, gutter role, areas). Elements are `text`
(paragraphs with a type role, text, bullet level), `table` (columns with a value kind,
rows, header rows), `chart`, `image`, `rule`, `rect`, or a `component`. Everything is a
role (`type.body`, `color.accent1`, `space.md`); a literal colour, size, font or coordinate
is refused by name. The full grammar with a worked example is the docstring of
`scripts/layout.py` (read it, do not run it for this); a complete four-page deck is
`examples/keybank-section.deck.json`, two bridge pages `examples/keybank-bridge.deck.json`.

A slide carries `id`, `layout` (one of the template's layout names), optional `notes`,
`spec` (`{"root": ...}`), optional `styling`, `charts`, `annotations`, and
`"title": {"register": "topic|claim|question|other", "element": "<id>"}` (the element is
optional; without it the first text whose first paragraph is `type.title` is the title).

A node in the tree carries `type`, `id`, `kind`, `weight`, `scale_class`, `size` and its
own content (`paragraphs` for text, `table` for a table) plus the styling keys the build
lifts (`fill_role`, `line_role`, `pad_role`, `anchor`, ...). A chart's own keys (`type`,
`categories`, `series`, `axes`, `plot_area`, `legend`, ...) live under `slide.charts[<the
node's id>]`, a picture's path under `slide.images`. Any other key on a node is read by
nothing and is refused by name; a chart key written on the chart's node names the move.
The deck may carry `firm_chrome` beside `slides` (templates-and-chrome.md).

## Limits

Each refused with its own message: node ids unique on the page; at most 400 nodes; at most
5 levels below the root (`root > body > col > panel > head > text` is the deepest chain).
The depth cap is a runaway bound (shape nesting observed 3 deep in three reference decks, plus 2), not a measurement of
layout trees. When a chain runs out, remove a region that wraps one child, or merge a
column into its parent; a text element takes `fill_role` and `anchor` itself.

## Capacity before text

```bash
python3 scripts/layout.py capacity "$DECK_WORK/deck/deck.json" --slide s3-synergies --guide "$DECK_WORK/ref/guide.json" \
        [--chrome draw] [-o "$DECK_WORK/deck/s3.capacity.json"]
```

`capacity` solves the page with the build's own solve (the same function: guide page size,
chrome zones for the `--chrome` mode, the title band, components probed and expanded),
then, for every text element the spec names, prints its solved box, its lines and
characters now, and `free`: how many characters more it takes before the page stops
fitting at full scale, found by solving the page again with filler text appended to that
element (every other element unchanged). One run on a keybank page:

```
s3-synergies: fit at scale 1.0 (pillow_x128)
  title              type.title         box [0.42, 0.42, 9.17, 0.4] in  lines 1  chars 38  free 21 chars (+0 lines)
  read               type.body          box [6.05, 1.02, 3.53, 5.51] in  lines 8  chars 251  free 807 chars (+19 lines)
  source             type.source_line   box [0.42, 6.73, 9.17, 0.17] in  lines 1  chars 44  free 3219 chars (+22 lines)
```

Budgets do not add up: two elements in one column share the same free space. A page that
fits only below full scale has no budget left (every `free` is 0, with the reason); cut or
re-arrange first. A component's own text is measured by the component, not here. The
filler is mean-advance English with figures, so a run of capitals or wide figures takes
fewer characters than `free` says. Write the skeleton with short placeholder text, read
the budgets, then write the words.

## Pictures: logos, icons and the user's files

A picture is an `image` node in the tree with its source under `slide.images[<id>]`,
one of:

- `{"path": "/abs/file.png"}`: a PNG, JPEG or GIF the user supplied, or one taken from
  the reference (below). Anything else (a BMP, a damaged file, a text file named .png,
  more than 40 MP declared) is refused by name before the solve.
- `{"svg": "/abs/icon.svg"}`: an icon you write in the SVG subset: `<svg viewBox>` with
  only `path`, `rect`, `circle`, `line` and `polygon` as its direct children, every
  `fill` and `stroke` a colour role or `none` (both required), plain numbers, nothing
  else (no `g`, `text`, `style`, `transform`, `image`, units, DOCTYPE; UTF-8 only; a
  shape that draws nothing is refused). The file is
  written natively (an SVG part on the picture's svgBlip extension, which PowerPoint
  2016+ draws) with a PNG fallback rasterised from the same shapes; the roles become the
  guide's colours when the file is written. `python3 scripts/images.py check ICON.svg
  --guide guide.json --png preview.png` refuses or previews it.

and, optionally, its box in the house's measures: `height_role` (a spacing role, or a
type role's line pitch times `lines`), `width_role`, or both (a box the picture is
fitted inside, so a column of icons of different shapes lines up), plus `align`
(left, center, right) and `valign` (top, middle, bottom). Without a role the node is a
flexible box like a chart's. A picture is never stretched: it is drawn at its own aspect,
as large as its box allows, and every choice you left out is listed under the page's
`image_defaults_taken`.

After the render the build compares what LibreOffice drew in each picture's box with the
picture as written (the icon rasterised at the render's size, the file scaled to it) and
refuses a page where more than 5% of the box differs (`picture not drawn as written`),
or where the picture is drawn under 4 px on a side (`picture too small to check`: a
20000 x 1 logo in a square box);
`pictures` in the report gives every share. Measured: LibreOffice 24.2 draws the SVG
part itself (with a blank PNG fallback the icon still drew), so the check reads the SVG
path; PowerPoint's drawing is not measured.

Taking a logo from the reference (run on an untrusted file with `python3 -I`):

```bash
python3 -I scripts/images.py list "$REF"                                        # every picture with an id, its slides or page and size
python3 -I scripts/images.py extract "$REF" --id image14.png -o "$DECK_WORK/img/vertex.png"       # a .pptx picture's own bytes
python3 -I scripts/images.py extract "$REF" --id p15-Im8 -o "$DECK_WORK/img/nys.png"              # a PDF picture, rendered at 600 dpi
python3 -I scripts/images.py extract "$REF" --page 15 --bbox 40,230,100,275 -o "$DECK_WORK/img/x.png"  # a vector mark, PDF points
```

A company's logo is the user's or the reference's, never one you draw. An icon (a
person, a flag, a factory, a check) is yours to draw in the subset when the house uses
icons and the user supplied none.

Proven on: BCG New York page 15 rebuilt on its guide, an icon-led row page (a star of
life drawn in the subset, a flag and the state's outline taken from the PDF), each
picture in a box of `"height_role": "type.body", "lines": 3, "width_role": "space.xl"`:

```json
{"type": "region", "id": "epi-row",
 "layout": {"kind": "flex", "direction": "row", "gap_role": "space.md", "pad_role": null, "align": "center", "justify": "start"},
 "children": [
  {"type": "element", "id": "epi-icon", "kind": "image"},
  {"type": "element", "id": "epi-label", "kind": "text", "weight": 0.14,
   "paragraphs": [{"role": "type.body_large", "text": "Epidemic", "ink_role": "color.accent1", "align": "center"}]},
  {"type": "element", "id": "epi-rule", "kind": "rule", "size": {"width_emu": 12700, "height_emu": null}, "line_role": "color.ink_muted"},
  {"type": "element", "id": "epi-text", "kind": "text", "weight": 0.86,
   "paragraphs": [{"role": "type.body_large", "text": "Covid epidemic continues to spread ...", "bullet_level": 0}]}]}
```

```json
"images": {
 "epi-icon": {"svg": "/abs/work/img/star.svg", "height_role": "type.body", "lines": 3, "width_role": "space.xl", "align": "center", "valign": "middle"},
 "us-icon": {"path": "/abs/work/img/flag.png", "height_role": "type.body", "lines": 3, "width_role": "space.xl", "align": "center", "valign": "middle"}}
```

The star, `examples/icons/star-of-life.svg` (the union of three bars as one outline,
its points computed, not traced):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <polygon points="6.02,65.83 14.30,80.17 41.72,64.34 41.72,96.00 58.28,96.00 58.28,64.34 85.70,80.17 93.98,65.83 66.56,50.00 93.98,34.17 85.70,19.83 58.28,35.66 58.28,4.00 41.72,4.00 41.72,35.66 14.30,19.83 6.02,34.17 33.44,50.00" fill="color.accent1" stroke="color.ink" stroke-width="2.5" stroke-linejoin="miter"/>
</svg>
```

Logos and icons placed along a chart's categories are a `category_row` annotation
(chart-recipes.md, "Rows aligned to categories").

## Conventions the build enforces

- The page title is held to the band above the reference's top rule when it has one: the
  build gives the title element the band's height (from the root's top padding down to
  the rule), so the content below starts under the rule's zone with no gap to tune. A
  two-line title the house never wrote is refused; shorten it or move the second clause
  where the house states claims. A house that sets a subtitle above its rule (jazz) is
  written as a second paragraph of the title element in the subtitle's role, with the
  root's `pad_roles` top set to the step that starts the band where the house's title
  starts (jazz: `space.md`, 0.11 in, as its title sits 0.10 in down); the title's length
  is judged on its `type.title` paragraphs only. A tag beside the title (a lever tag) is
  a row holding the title and the tag; the tag's width comes out of the title's.
- `size` on a text element is refused: its height is its measured lines, or its share of
  a column by weight. Space above or below is a `gap_role` or a region's `pad_roles`.
- An empty cell that keeps a row or grid in step (a spacer) is a region with no
  children, with a weight in its row or column; blank text is refused.
- Chrome zones are reserved automatically; content never runs under the footer rule.
  `page.reserved_zones` overrides. Under `--chrome none` only chrome the template inherits
  is reserved. A band carrying content on at least half the pages it appears on is a
  surface (a title band, a body band) and reserves nothing; text on it is scored against
  its fill, so text straddling a band edge is refused there.
- A region may carry `fill_role` (and `prst`, a preset drawn under its children: `rect`,
  `roundRect`, `ellipse`, `homePlate`, `chevron`, `rightArrow`, `leftArrow`, `downArrow`,
  `upArrow`, `diamond`, `triangle`, and the brackets and braces, which carry no text) and
  an outline (`line_role`, `line_width_emu`, `dash`)
  and padding in its layout: `pad_role` on every side, or `pad_roles` naming each of
  `left`, `top`, `right`, `bottom` (a spacing role or null; a side left out is refused,
  not read as zero). Text inside takes `ink_role` on its paragraph. A house's arrow or
  chevron label is such a region: the contrast gate reads the text against the shape's
  solid body (a homePlate's body ends half the shape's height before its point; a
  chevron's runs between its notch and its point; an arrow's is its shaft), so give the
  pointed side the padding that keeps the words on the body (a homePlate label with
  `pad_roles` right `space.md` and the rest `space.sm` on keybank).
- A text element takes `fill_role`, `line_role` and `anchor` (`t`, `m` or `b`) itself;
  any other anchor is refused (it fell back to top in silence before). `prst` and
  `pad_role` on a text element are refused: a text box is a rectangle measured at its
  full width; put the words in a region that carries them.
- A paragraph is `{"role", "text"}` plus `bullet_level`, `ink_role`, `align`. Bold or
  coloured words go under `styling.<id>.paragraphs.<n>.runs`, the paragraph keeping the
  whole text; `runs` on the paragraph itself is refused by name. A run is `{"text"}` plus
  `emphasis` (bold) and `ink_role` (its own colour, scored by the contrast gate against
  the run's backing); any other key on a run is refused by name.
- A region outline (`line_role` on a region) that marks something on the page is a mark
  like any annotation: say what it marks in words on the page, as "A mark says what it
  means" in chart-recipes.md asks.
- Spacing between paragraphs is the role's (`space_before_pt`, `space_after_pt`); a
  paragraph carries none of its own. A house that spaces its list items has that spacing
  in a role (answer it at completion, or add a list role there); otherwise put each item
  in its own element in a column with a `gap_role`.
- Height: a region is as tall as its content unless it is flexible (it holds a chart, image
  or rule with no height, or carries a `weight` inside a column); flexible regions share
  the spare height by weight. A text element with a `weight` inside a column is flexible
  too: it takes its share (never less than its lines) and its words sit at its `anchor`,
  so a filled sidebar or a row of label cells runs to the foot of its column. A row's `align` does not make it flexible: to fill the page,
  give the region a weight in its column.
- Every measured element is checked against its own box: `overflow` (text or table rows
  outgrow it) and `word_split` (a word wider than its line, named) are violations a
  smaller scale may fix.
- Emphasis runs (`styling.<id>.paragraphs.<n>.runs` with `emphasis: true`) are measured at
  the paragraph's regular weight; keep them short or leave slack.
- Bullet indents come from the reference's bullets; a reference without bullets gets the
  spacing scale's progression (sm, md, lg).

## Looking before writing: the reference's gallery

```bash
python3 scripts/gallery.py pick "$DECK_WORK/ref/gallery" --intent "two column comparison table beside commentary"
```

Prints the two exemplars and three crops whose words overlap the intent most, with their
skeletons. Overlap 0 everywhere means the gallery has nothing for that intent (a house that
pastes its tables as pictures has no table crop): design from the guide and the digest, not
from a near miss. Word overlap is a weak ranking (measured); the digest's records are the
stronger evidence.

## Looking before writing: the page library

```bash
python3 scripts/library.py pick --intent "each valuation method's range against the offer" \
  [--composition "words"] [--data-shape "seven low and high pairs and one offer value"] \
  [--aspect 4:3] --gallery "$DECK_WORK/ref/gallery" [--own COMPANY_LIBRARY]
python3 scripts/library.py vocab        # the tag fields, and the few tags that are slugs
```

It searches the reference's own gallery, then the company's library, then an external
library (`refs/library`, git-ignored), and says which answered. Order: composition first,
aspect next, then data-shape and intent words against the words each exhibit was tagged
in. Describe the page by what it must show, not by a chart type.
Use each entry's `why` and `ask` lines as questions for your page, never as a layout to
copy. An aspect mismatch is flagged: examples do not carry across page sizes. `no evidence`
means nothing fits. Building a company library is in the page-library reference.

## House specimen pages

`examples/house/` holds 14 specimen pages as deck specs (comps, football field, waterfall,
Mekko, KPI band, timeline, credentials, league table, agenda, profile, framework matrix,
arithmetic chain, section divider, text plus chart); `COVERAGE.md` names each page's family.
They were composed for 16:9: on a 4:3 bank page at 12pt only 2 of 14 fit as written, so cut
or split before building, and read the unfittable report rather than forcing the scale.
Their titles are specimens, not a register: write titles in the house's register.

## Motifs

Motifs the digest lists (a band, a rule, a block with a preset, roles and an anchor) are
yours to apply: draw one as a `rule` or `rect` element with the motif's role at the place
the reference uses it. `slide_top` and `slide_bottom` marks are chrome and already on the
layout; `region_edge` and `element_adjacent` marks are yours to place. There is no motif
field in the grammar.
