# Templates, chrome and the round trip

## Contents
- Making the template
- How chrome is drawn
- The round trip: prove the chain on the house's own page

## Making the template

```bash
python3 scripts/pptx_tools.py template "$REF" -o "$DECK_WORK/tpl.pptx"                        # pptx reference
python3 scripts/pptx_tools.py blank -o "$DECK_WORK/tpl.pptx" --width-emu W --height-emu H          # PDF reference; W, H from guide.reference.page
python3 scripts/pptx_tools.py layouts "$DECK_WORK/tpl.pptx"                                       # layouts and placeholders with boxes
```

The pptx template is the reference with every slide removed: masters, layouts, theme and
chrome intact (PowerPoint opens and re-saves such packages without repair and draws chrome
once per slide, measured). Page numbers and footers the reference carried
on its slides are copied from the layout onto each new slide. Every page names one of the
template's layouts; an unknown layout is refused by name. Choose the layout per page the
way the house's past pages use them (`pptx_tools.py text` on a past deck prints each
slide's layout).

For a PDF reference the template is blank at the reference's page size, and
`build_deck.py --chrome draw` paints the guide's chrome (rules, bands, footer labels, a
page-number field) and the surface colour on every slide.

## How chrome is drawn

- Order: entries paint in `paint_order`, the reference's own painting sequence, all under
  the content. A hand-written entry without `paint_order` keeps its place in the list.
- Text: one line, never wrapped, in the entry's `text_style` (family, size_pt, ink_hex,
  bold, read from the reference's glyphs). An entry with `rotation_deg` is turned about the
  centre of `box_in`, the pre-rotation box as OOXML keeps it. Chrome text is scored by the
  contrast gate like any run; an entry wholly off the slide is not scored; an entry with no
  `text_style.ink_hex` is listed under `contrast.unbound`.
- Zones: an entry reserves the area it covers (a turned label: the narrow strip it draws
  in). `space.margin` is the content's inset; a band, picture or rule that runs to an edge
  bleeds and is not a vote for it.
- Logo: with `image_path`, the picture; else a placeholder painted only in what the entry
  names (`fill_hex`/`fill_role`, `line_hex`/`line_role` with `line_width_pt`). An entry
  naming neither is not drawn, and `chrome.notes` says so.
- No drawn shape keeps a theme style reference (python-pptx's default would add the
  theme's drop shadow on every rule in LibreOffice).
- In the default `--chrome auto`, slide-layer chrome the reference pastes on every page is
  drawn on every generated page; chrome the layout already carries is inherited, never
  redrawn. The report's `chrome` section lists what each page drew and what could not be
  drawn as observed.

## The round trip: prove the chain on the house's own page

Before a page of your own, import one of the reference's into a spec of roles and weights
(no coordinates survive), build it on the template and compare:

```bash
python3 scripts/import_slide.py "$REF" --slide 3 --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/rt/rt3.deck.json"
python3 scripts/build_deck.py "$DECK_WORK/rt/rt3.deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
        -o "$DECK_WORK/rt/rt3.pptx" --reference "$REF" --renders "$DECK_WORK/rt/renders" [--chrome draw]
```

A PDF page imports the same way (`--slide` is the page number) and builds with `--chrome
draw`: text blocks become elements, the filled rectangle under a block becomes its
`fill_role`, text at a chrome position is left to the chrome, turned text is left out; the
notes name each.

Read `judge.total` against `judge.house_spread` (the leave-one-out distance of each
reference page to the rest). Then LOOK at the render beside the reference page: the number
does not see what was lost. Measured: a bank page round-tripped at 0.056 (house spread
0.055 to 0.372) and matched the original to the eye; a consulting PDF page round-tripped at
0.097, filed, while its render had lost the ring diagram, the gradient ground and the
block positions. The imported spec is also your seed: a page that starts from the house's
own page begins inside its bands and columns.
