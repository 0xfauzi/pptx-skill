# Page specs: the grammar, the conventions, and where to look before writing

## Contents
- The tree
- Limits
- Capacity before text
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
`"title": {"register": "topic|claim|question", "element": "<id>"}` (the element is
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

## Conventions the build enforces

- The page title is held to the band above the reference's top rule when it has one. A
  two-line title the house never wrote is refused; shorten it or move the second clause
  where the house states claims.
- Chrome zones are reserved automatically; content never runs under the footer rule.
  `page.reserved_zones` overrides. Under `--chrome none` only chrome the template inherits
  is reserved. A band carrying content on at least half the pages it appears on is a
  surface (a title band, a body band) and reserves nothing; text on it is scored against
  its fill, so text straddling a band edge is refused there.
- A region may carry `fill_role` (and `prst`, a preset drawn under its children: `rect`,
  `roundRect`, `ellipse`, `homePlate`, `chevron`, `rightArrow`, `diamond`, `triangle`)
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
  whole text; `runs` on the paragraph itself is refused by name.
- Height: a region is as tall as its content unless it is flexible (it holds a chart, image
  or rule with no height, or carries a `weight` inside a column); flexible regions share
  the spare height by weight. A row's `align` does not make it flexible: to fill the page,
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
python3 scripts/library.py pick --intent "valuation football field against the offer" \
  --exhibit football_field_or_range_bars [--composition C] [--move M]... [--data-shape TEXT] \
  [--aspect 4:3] --gallery "$DECK_WORK/ref/gallery" [--own COMPANY_LIBRARY]
python3 scripts/library.py vocab        # every value the tags take
```

It searches the reference's own gallery, then the company's library, then an external
library (`refs/library`, git-ignored), and says which answered. Order: composition,
exhibit family and annotation moves first, aspect next, data-shape and intent words last.
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
