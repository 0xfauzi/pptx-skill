# Templates, chrome and the round trip

## Contents
- Making the template
- The reference firm's own chrome
- How chrome is drawn
- The round trip: prove the chain on the reference's own page

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
template's layouts; an unknown layout is refused by name. Which layout did the reference use
for pages like this, and does this page need the same frame? `pptx_tools.py text` on a
past deck prints each slide's layout, and `pptx_tools.py layouts` lists every layout of
the template with how many of the reference's slides use it ("on 0 of 12 slides" for one
the reference never used, which is still yours to choose; say why in the report).

For a PDF reference the template is blank at the reference's page size, and
`build_deck.py --chrome draw` paints the guide's chrome (rules, bands, footer labels, a
page-number field) and the surface colour on every slide. Its layouts are the default
eleven and say nothing about the reference: use one layout throughout (Title Only), since the
page's arrangement is the spec's, not the layout's.

What a PDF's chrome is drawn from, so it matches the reference:
- Geometry: a band's or rule's box is refined against a 300 dpi render of the first page
  that carries it (`box_basis` in the guide says so): the rows where the ink spans at
  least half the width, so a title band is as inset as the reference's and a rule as thick
  and as high as it is drawn (bain's band inset 8 px each side, BCG's title rule 2 px
  higher; both match the reference's rows).
- Logos and wordmarks: a recurring picture is cut out of the render into `<draft
  dir>/chrome/` and its entry takes that `image_path`; a wordmark drawn as vector curves
  (BCG's) is a chrome candidate from the PDF's path clusters and cut the same way. A
  footer line of any length is chrome text (a file name in 7pt included).
- Ground: a picture under every page (McKinsey's navy-to-blue gradient) becomes the
  guide's `ground`, its pixels saved beside the draft; `--chrome draw` paints it under
  everything, and the contrast gate scores text on it against its darkest and lightest
  pixels under the text, so a bright accent on the blue ground is refused as it reads.

## The reference firm's own chrome

The template carries the reference reference's name and logo on its master. For a deck of that
firm, keep them. For a deck of another firm, or of a made-up one, they would put the wrong
name on every page: ask the user whether to keep, replace or drop each, and write the
answer in the deck JSON by chrome id (the ids are in the build report's `chrome.firm`,
and in `draft.md`'s chrome list):

```json
"firm_chrome": {"chrome-13": {"text": "Harbour & Co."}, "chrome-9": "drop"}
```

`"keep"`, `"drop"`, `{"text": "..."}` for a text entry, `{"image_path": "..."}` (a PNG,
JPEG or GIF of the same format as the template's picture, read as a picture, not by its
name) for a logo. An id that is not firm chrome on these pages is refused, listing
the ones that are. The build reports every entry's decision, and marks each one the deck
left to the default.

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
  redrawn. The report's `chrome` section lists the reference's chrome with its counts
  (`chrome.reference`: "on 12 of 12 reference pages"), what each page drew and what could not
  be drawn as observed.
- The reference's chrome is where a page starts, not a rule over it. A page may leave an
  entry off, or set other words in a text entry's place, with a reason:
  `"chrome": {"chrome-7": {"omit": true, "why": "a full-bleed divider page, as the reference's
  own section openers carry no number"}}` or `{"chrome-4": {"text": "Appendix", "why":
  "..."}}`. The zones, the contrast gate and the emitter read the same per-page list, so
  an entry left off frees its zone and a replaced line is scored in its new words. Never
  page by page: the firm's own chrome (decided for the whole deck in `firm_chrome`), a
  legal or confidentiality mark, or, under `--chrome auto`, an entry the page inherits
  from its layout (choose a layout without it). The build reports each page's choices
  under `chrome_choices`.
- A value a drawn entry does not record (a rule's width, a text entry's face or size) is
  written from the guide (its minor face, `type.caption`'s size, `color.rule`) or 0.75pt,
  and listed under the page's `emit_defaults_taken`; an entry whose text has no face at
  all is refused.

## The round trip: prove the chain on the reference's own page

Before a page of your own, import one of the reference's into a spec of roles and weights
(no coordinates survive), build it on the template and compare. Choose the page with the
survey: it imports every page and says what each holds, what the import loses (a chart
becomes a placeholder line, a PDF table too, turned text is left out, merged cells are
unmerged) and whether it fits at full scale, and marks the candidates (content, title,
text and an exhibit, nothing lost, fitting, on the reference's most used layout first). A
pptx picture travels with its own bytes and a native table as a table spec (a column or
row bold throughout becomes an `emphasis` group), so a reference that pastes its exhibits as
pictures still has candidates.

```bash
python3 scripts/import_slide.py "$REF" --survey --guide "$DECK_WORK/ref/guide.json"
```

Then import and build the one you chose:

```bash
python3 scripts/import_slide.py "$REF" --slide 3 --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/rt/rt3.deck.json"
python3 scripts/build_deck.py "$DECK_WORK/rt/rt3.deck.json" --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
        -o "$DECK_WORK/rt/rt3.pptx" --reference "$REF" --renders "$DECK_WORK/rt/renders" [--chrome draw]
```

A PDF page imports the same way (`--slide` is the page number) and builds with `--chrome
draw`: text blocks become elements, the filled rectangle under a block becomes its
`fill_role`, text at a chrome position is left to the chrome, turned text is left out; the
notes name each.

Read `judge.total` against `judge.reference_spread` (the leave-one-out distance of each
reference page to the rest). Then LOOK at the render beside the reference page: the number
does not see what was lost. Measured: a bank page round-tripped at 0.056 (reference spread
0.055 to 0.372) and matched the original to the eye; a consulting PDF page round-tripped at
0.097, filed, while its render had lost the ring diagram, the gradient ground and the
block positions. The imported spec is also your seed: a page that starts from the reference's
own page begins inside its bands and columns.
