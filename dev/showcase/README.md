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
The LBO deck sets chart text in Arial because LibreOffice draws Carlito chart labels with
collapsed or split word spaces at the sizes the deck could use: measured on this deck's own
labels, the narrowest word space was 0.51 of a space at 7pt ("Water andwastewater"), and gaps
inside words reached 0.35 to 0.41 of a space at 7.5 and 8pt ("Wat er"), where Arial at 7pt
drew every space at 0.69 or more and no gap inside a word over 0.15; `kern` 0 or 1200 on
the chart text changed nothing (PORT_AUDIT.md, docs round 2). Arial chart labels are not
even either: on the committee book's bridge, figures such as "(30.0)" drew with gaps and
overlaps between glyphs of up to 0.42 of a space at 7 to 9pt in half-point steps, so the
bridge sets its figures as a row of text above the plot (PORT_AUDIT.md, docs round 3).

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
and both validations reported no problems. Against the previous round's rebuild, every
render of a page no change touched was pixel-identical (dev/PORT_AUDIT.md, docs round 3).
