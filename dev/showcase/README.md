# Showcase decks

The sources of the four decks shown in the top-level README (`docs/showcase/`). Each was
built with no reference: the look was chosen in the deck's `completion.json` (its
`/look_brief` says why), and every company, person and figure is fictional.

| Deck | Pages | Faces | Sources |
|---|---|---|---|
| `lbo-committee-book` | 6 | Calibri; Arial for chart text | `model.py` (the LBO model), `build_spec.py` (writes `deck/deck.json` and prints every stated figure), `plan.json`, `completion.json` |
| `grocery-strategy` | 5 | Georgia titles, Arial | `figures.py` (writes `data.json` and prints every stated figure), `make_deck.py` (writes `deck/deck.json`), `plan.json`, `completion.json` |
| `software-earnings` | 5 | Arial | `figures.py` (asserts and prints every stated figure), `deck.json` (the spec, written by hand), `plan.json`, `completion.json` |
| `parks-annual-report` | 5 | Georgia titles, Arial | `figures.py`, `deck.json`, `plan.json`, `completion.json` |

The decks name only faces that Windows and macOS PowerPoint carry, so the .pptx files open
as built. The build measures each face with the installed face or its metric-compatible
stand-in (`scripts/textfit.py`, `METRIC_ALIAS_CLASSES`): Liberation Sans for Arial and
Carlito for Calibri, both in INSTALL.md's font list, and Gelasio for Georgia, which is not.
The LBO deck sets chart text in Arial because LibreOffice drew its 7pt Carlito chart labels
with lost and split word spaces ("Water andwastewater", "Downsi de case") on a render of
this deck, and draws Arial at that size as written.

## Rebuild a deck

From the repository root, with the skill's requirements installed (`INSTALL.md`). The
grocery and parks decks also need Gelasio (SIL Open Font License; github.com/SorkinType/Gelasio, as its own name table says) installed
and seen by fontconfig (`fc-match Georgia` names it): with fontconfig set to hide Gelasio,
the renderer drew Georgia as DejaVu Serif and the grocery rebuild was refused on all five
pages.

```sh
sh dev/showcase/rebuild.sh grocery-strategy /abs/path/to/an/empty/work/dir
```

`rebuild.sh` copies the deck's sources into the work directory, runs its figures script,
completes a blank guide with `completion.json`, makes a blank template at the page size the
completion chose, checks the plan, builds with `--plan`, `--chrome draw` and
`--computed figures.txt`, and validates the package twice (`validate --render` and
`validate --emit --guide`). It stops at the first step that fails. The deck lands at
`WORK/out/deck.pptx`, its page renders in `WORK/out/renders/`, the build report at
`WORK/out/deck.build.json`.

## Rebuild the images

```sh
python3 dev/showcase/sheet.py docs/showcase/hero.png 1632 1 LBO/out/renders/slide-01.png
python3 dev/showcase/sheet.py docs/showcase/strip.png 1632 3 GROCERY/out/renders/slide-04.png \
  EARNINGS/out/renders/slide-04.png PARKS/out/renders/slide-01.png
python3 dev/showcase/sheet.py docs/showcase/grocery-strategy.png 1632 1 GROCERY/out/renders/slide-*.png
```

where `LBO`, `GROCERY`, `EARNINGS` and `PARKS` are the work directories of the four
rebuilds; the last line, with each deck's name and work directory, makes each deck's
one-column image of all its pages at the render's own width. Copy `WORK/out/deck.pptx` to
`docs/showcase/<deck>.pptx`.

The committed images and decks were made this way from four rebuilds on the skill at the
commit that added them. Each rebuild passed (every page fit, package valid, no warning),
and both validations reported no problems. Two rebuilds of each deck gave renders
identical byte for byte.
