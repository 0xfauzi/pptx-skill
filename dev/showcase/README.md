# Showcase decks

The sources of the four decks shown in the top-level README (`docs/showcase/`). Each was
built with no reference: the look was chosen in the deck's `completion.json` (its
`/look_brief` says why), and every company, person and figure is fictional.

| Deck | Pages | Sources |
|---|---|---|
| `lbo-committee-book` | 6 | `model.py` (the LBO model), `build_spec.py` (writes `deck/deck.json` and prints every stated figure), `plan.json`, `completion.json` |
| `grocery-strategy` | 5 | `figures.py` (writes `data.json` and prints every stated figure), `make_deck.py` (writes `deck/deck.json`), `plan.json`, `completion.json` |
| `software-earnings` | 5 | `figures.py` (asserts and prints every stated figure), `deck.json` (the spec, written by hand), `plan.json`, `completion.json` |
| `parks-annual-report` | 5 | `figures.py`, `deck.json`, `plan.json`, `completion.json` |

## Rebuild a deck

From the repository root, with the skill's requirements installed (`INSTALL.md`):

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
python3 dev/showcase/sheet.py docs/showcase/hero.png 1320 1 \
  LBO/out/renders/slide-01.png GROCERY/out/renders/slide-04.png \
  EARNINGS/out/renders/slide-01.png PARKS/out/renders/slide-02.png
python3 dev/showcase/sheet.py docs/showcase/grocery-strategy.png 1600 2 GROCERY/out/renders/slide-*.png
```

where `LBO`, `GROCERY`, `EARNINGS` and `PARKS` are the work directories of the four
rebuilds. Copy `WORK/out/deck.pptx` to `docs/showcase/<deck>.pptx`.

The committed images and decks were made this way from four rebuilds on the skill at the
commit that added them. Each rebuild passed (every page fit, package valid, no open
warning; the one warning, on the committee book's first page, is answered in its spec) and both validations reported no problems; the renders of the rebuilds were
identical, pixel for pixel, to the builds that were reviewed page by page before them.
