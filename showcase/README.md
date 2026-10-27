# Showcase decks

This folder holds the sources of the four fictional-company decks in the gallery of the
top-level README. The built files
are in `docs/showcase/`. The skill built each deck with no reference. The `completion.json` of
each deck chooses its look, and its `/look_brief` gives the reasons. All companies,
persons and figures are fictional.

| Deck | Pages | Fonts | Sources |
|---|---|---|---|
| `lbo-committee-book` | 6 | Calibri; Arial for chart text | `model.py` (the LBO model), `build_spec.py` (writes `deck/deck.json` and prints each stated figure), `plan.json`, `completion.json` |
| `grocery-strategy` | 5 | Georgia titles, Arial | `figures.py` (writes `data.json` and prints each stated figure), `make_deck.py` (writes `deck/deck.json`), `plan.json`, `completion.json` |
| `software-earnings` | 5 | Arial | `figures.py` (checks and prints each stated figure), `deck.json` (the spec, written by hand), `plan.json`, `completion.json` |
| `parks-annual-report` | 5 | Georgia titles, Arial | `figures.py`, `deck.json`, `plan.json`, `completion.json` |

The decks name only fonts that PowerPoint has on Windows and macOS. Thus the .pptx files
open as built. The build measures each font with the installed font or with its
metric-compatible stand-in (`METRIC_ALIAS_CLASSES` in `scripts/textfit.py`):

- Liberation Sans for Arial.
- Carlito for Calibri.
- Gelasio for Georgia.

The font list in INSTALL.md includes Liberation Sans and Carlito. It does not include
Gelasio.

The LBO deck sets its chart text in Arial. At the small sizes that the deck uses,
LibreOffice draws Carlito chart labels with incorrect word spaces. Arial chart figures
also have uneven gaps between glyphs. For this reason, the bridge of the committee book
shows its figures as a row of text above the plot.

## Build a deck again

1. Install the requirements of the skill (see `INSTALL.md`).
2. For the grocery and parks decks, also install the Gelasio font (SIL Open Font
   License, github.com/SorkinType/Gelasio). Make sure that `fc-match Georgia` names
   Gelasio. If fontconfig does not find Gelasio, the build refuses the pages.
3. Make an empty work folder. Use an absolute path outside the skill folder.
4. From the root of the repository, run the build script with the name of the deck and
   the work folder:

   ```sh
   sh showcase/rebuild.sh grocery-strategy /abs/path/to/an/empty/work/dir
   ```

`rebuild.sh` does these steps:

1. It copies the sources of the deck into the work folder and runs the figures script.
2. It completes a blank guide with `completion.json`.
3. It makes a blank template at the page size that the completion chose.
4. It checks the plan.
5. It builds with `--plan`, `--chrome draw` and `--computed figures.txt`.
6. It validates the package two times (`validate --render` and
   `validate --emit --guide`).

The script stops at the first step that fails. The deck goes to `WORK/out/deck.pptx`. The
page renders go to `WORK/out/renders/`. The build report goes to
`WORK/out/deck.build.json`.

## Make the images again

Run these commands from the root of the repository:

```sh
python3 showcase/sheet.py docs/showcase/grocery-strategy.png 1632 1 GROCERY/out/renders/slide-*.png
```

`GROCERY` is the work folder of the grocery build. Use this command for each deck, with
the name and work folder of that deck. It makes an image of all pages of the deck in one
column. Then copy `WORK/out/deck.pptx` to `docs/showcase/<deck>.pptx`.

The top-level README images `hero.png` and `strip.png` come from the three S-1 decks. Their
build sources are not in this repository. These commands made the images from the page
renders of those builds:

```sh
python3 showcase/sheet.py docs/showcase/hero.png 1632 1 PITCHBOOK/renders/slide-01.png
python3 showcase/sheet.py docs/showcase/strip.png 1632 2 RESEARCH/renders/slide-04.png \
  COMMITTEE/renders/slide-05.png
```
