# Showcase decks

This folder holds the sources of the seven fictional-organisation decks in the gallery of
the top-level README. The built files are in `docs/showcase/`. All organisations, persons
and figures are fictional. The `completion.json` of each deck chooses or completes its
look, and gives the reasons.

| Deck | Pages | Reference | Fonts | Sources |
|---|---|---|---|---|
| `board-transformation` | 8 | None | Inter | `figures.py` (writes `data.json` and prints each stated figure), `make_deck.py` (writes `deck/deck.json`), `plan.json`, `completion.json`, `img/` (icons, the mark and the two inset maps), `make_assets.py` |
| `transit-outlook` | 6 | EIA, PDF | Times New Roman titles, Arial | `figures.py`, `make_deck.py` (writes `deck/deck.json` and `plan.json`), `completion.json`, `digest.json`, `reference.json`, `img/lrta-mark.png` |
| `wildfire-plan` | 6 | SAMHSA, .pptx | Arial Narrow, measured and drawn as Inter | `figures.py`, `make_deck.py` (writes `deck/deck.json` and `plan.json`), `completion.json`, `digest.json`, `reference.json`, `template.sh` with `make_bg.py`, `make_bg2.py` and `clean_template.py` |
| `lbo-committee-book` | 6 | None | Calibri, with Arial for chart text | `model.py` (the LBO model), `build_spec.py` (writes `deck/deck.json` and prints each stated figure), `plan.json`, `completion.json` |
| `grocery-strategy` | 5 | None | Georgia titles, Arial | `figures.py` (writes `data.json` and prints each stated figure), `make_deck.py` (writes `deck/deck.json`), `plan.json`, `completion.json` |
| `software-earnings` | 5 | None | Arial | `figures.py` (checks and prints each stated figure), `deck.json` (the spec, written by hand), `plan.json`, `completion.json` |
| `parks-annual-report` | 5 | None | Georgia titles, Arial | `figures.py`, `deck.json`, `plan.json`, `completion.json` |

## The two reference decks

Two decks use the look of a public deck of a US government agency. A work that an officer
or employee of the US government prepares as part of official duties is in the public
domain (17 U.S.C. 105). This repository does not include the two reference files. Download
each file from its address, and keep it outside the skill folder.

| Deck | Reference | Address | sha256 | Public-domain basis |
|---|---|---|---|---|
| `transit-outlook` | U.S. Energy Information Administration (EIA), U.S. Department of Energy: "Annual Energy Outlook 2026: Release Presentation", 8 April 2026, 16 pages, PDF | https://www.eia.gov/outlooks/aeo/pdf/AEO2026_Release_Presentation.pdf | `c14c5907...815801` | EIA staff made the deck, and the PDF names EIA as its author. The EIA page "Copyrights and Reuse" (https://www.eia.gov/about/copyrights_reuse.php) says that US government publications are in the public domain. EIA asks for an acknowledgment when you use its products. |
| `wildfire-plan` | Center for Behavioral Health Statistics and Quality, Substance Abuse and Mental Health Services Administration (SAMHSA), U.S. Department of Health and Human Services: "Results from the 2025 National Survey on Drug Use and Health: Graphics from the Key Findings Report", 90 slides, .pptx | https://www.samhsa.gov/data/sites/default/files/reports/rpt57150/2025_NNR_figure_slides.pptx (report page: https://www.samhsa.gov/data/report/2025-nsduh-annual-national-report) | `16bfa702...da5ab68` | SAMHSA published the file, and its creator field names the SAMHSA center, SAMHSA and HHS. We did not find a public-domain statement on the report page. The basis is 17 U.S.C. 105 only. |

`reference.json` in each deck folder holds the full sha256. `rebuild.sh` refuses a
reference file with a different sha256.

The two new decks do not copy the text, the figures or the logos of the references:

- Each page has a footer that says the figures are illustrative and that no agency
  prepared or endorsed the page.
- The transit outlook draws its own mark, `img/lrta-mark.png`.
- For the wildfire plan, `template.sh` removes every slide of the reference. It replaces
  the SAMHSA wordmark in the master background with the fictional Ridgeline wordmark
  (`make_bg.py`, then `make_bg2.py`). It also replaces the document properties, the comment
  authors and the figure-number prompt of the layouts (`clean_template.py`).

The SAMHSA file names Arial Narrow, Segoe UI and Segoe UI Semibold for its text. The
machine that built the wildfire plan does not have these fonts. The font report
(`scripts/fonts.py report`) gives these results for the reference file:

- Arial Narrow, Segoe UI and Segoe UI Semibold are missing. The stand-in for each is
  Inter, the font that fontconfig draws. Inter is not metric-compatible with them.
- The width difference cannot be measured. A .pptx file does not hold glyph widths, and
  the machine has no file of these fonts.
- The SAMHSA file names Calibri Light and two HelveticaNeueLT faces, but sets no text in
  them. The report lists them and does not stop for them.

The completion of the wildfire plan names Inter as the stand-in for the three fonts. With
this guide, the report exits 0, and the build measures and draws the text in Inter. The
built deck names Arial Narrow, Segoe UI and Segoe UI Semibold, and it embeds no font. In
PowerPoint, the text shows in these fonts if the computer has them. Arial Narrow is a
condensed font, so the text can take less space than in the renders. Examine the deck in
PowerPoint before you use it.

The EIA file sets a few words in Jost, a font that the machine does not have. The PDF
holds only a subset of Jost, and the skill never sets new text with a subset. The report
measures the stand-in Inter as 13.1% wider than Jost over the 4 words that the PDF sets in
Jost. The guide of the transit outlook does not use Jost, so the report exits 0.

The board deck names Inter (SIL Open Font License). The report finds Inter on the machine
that built the deck. The deck embeds no font. Install Inter on each computer that opens
the deck. If the computer does not have Inter, PowerPoint draws the text in a different
font.

## Fonts of the five decks with no reference

The board deck uses Inter. The other four decks name only fonts that PowerPoint has on
Windows and macOS. So these .pptx files open as built. For each of the four decks, the
font report finds a metric-compatible font for each font of the guide and exits 0. The build measures each font with
the installed font or with its metric-compatible stand-in (`METRIC_ALIAS_CLASSES` in
`scripts/textfit.py`):

- Liberation Sans for Arial.
- Carlito for Calibri.
- Gelasio for Georgia.

The font list in INSTALL.md includes Liberation Sans and Carlito. It does not include
Gelasio.

The LBO deck sets its chart text in Arial. At the small sizes that the deck uses,
LibreOffice draws Carlito chart labels with incorrect word spaces. LibreOffice also draws
Arial chart figures in Liberation Sans, the stand-in for Arial, with uneven gaps between
glyphs. For this reason, the bridge of the committee book
shows its figures as a row of text above the plot.

## Build a deck again

1. Install the requirements of the skill (see `INSTALL.md`).
2. The grocery and parks decks need the Gelasio font (SIL Open Font License). Put your
   copy of the Gelasio files in `WORK/fonts`. If Gelasio is installed on your computer,
   `fc-match Georgia` must name Gelasio. If the skill does not find Gelasio, the font
   report stops the build. The script does not download or install fonts.
3. The board deck and the wildfire plan need the Inter font (SIL Open Font License). Put
   your copy of the Inter files in `WORK/fonts`. The wildfire plan also needs a fontconfig
   that names Inter for "Arial Narrow" and "Segoe UI", as on the machine that built it.
   Run `fc-match "Arial Narrow"` and `fc-match "Segoe UI"` to examine this. The fonts
   folder does not change the font that fontconfig picks for a missing font. If
   fontconfig picks a different font, the text measures differently. Then the build can
   refuse pages. Installing a font is your own action. Do not ask Claude to do it.
4. For the transit outlook and the wildfire plan, download the reference file (see "The
   two reference decks"). Use an absolute path outside the skill folder.
5. Make an empty work folder. Use an absolute path outside the skill folder.
6. From the root of the repository, run the build script with the name of the deck and
   the work folder. For a reference deck, also give the path of the reference file:

   ```sh
   sh showcase/rebuild.sh grocery-strategy /abs/path/to/an/empty/work/dir
   sh showcase/rebuild.sh transit-outlook /abs/path/to/an/empty/work/dir /abs/path/to/AEO2026_Release_Presentation.pdf
   sh showcase/rebuild.sh wildfire-plan /abs/path/to/an/empty/work/dir /abs/path/to/2025_NNR_figure_slides.pptx
   ```

`rebuild.sh` does these steps:

1. It copies the sources of the deck into the work folder. In `completion.json`, it
   changes `@WORK@` to the path of the work folder.
2. It sets `DECK_FONTS` to `WORK/fonts` if `DECK_FONTS` is not set, and makes the
   folder. Then it makes the guide:
   - With no reference, it completes a blank draft with `completion.json`.
   - With a reference, it checks the sha256 of the file against `reference.json`. It
     extracts the draft from the file and cuts the digest stub. It copies `digest.json`
     (the digest, answered after a look at each crop) next to the stub. Then it completes
     the draft with `completion.json` and the digest.
3. It runs the font report (`WORK/ref/fonts.md`) on the guide, and on the reference if
   there is one. If the guide sets a font that the skill cannot measure, the script
   stops. Then it makes the template. If the deck has `template.sh`, the script makes it (the
   wildfire plan). If not, it makes a blank template at the page size of the guide.
4. It runs the figures script and the deck script.
5. It checks the plan.
6. It builds with `--plan` and `--computed figures.txt`. With no reference, it uses
   `--chrome draw`. With a reference, it also uses `--reference` and the chrome mode of
   `reference.json`.
7. It validates the package two times (`validate --render` and
   `validate --emit --guide`).

The script stops at the first step that fails. The deck goes to `WORK/out/deck.pptx`. The
page renders go to `WORK/out/renders/`. The build report goes to
`WORK/out/deck.build.json`.

The renders of the three newest decks (board, transit and wildfire), built again with
this script, are the same pixel for pixel as the renders of the reviewed builds.

`make_assets.py` of the board deck drew the icons, the mark and the two inset maps in
`img/`. It reads the Natural Earth land outlines (public domain, naturalearthdata.com) from
`dl/ne_110m_land.geojson`. `rebuild.sh` does not run it, and uses the files in `img/`.

## Make the images again

### The gallery images and files

Run this command from the root of the repository for each deck, with the name and work
folder of that deck:

```sh
python3 showcase/sheet.py docs/showcase/grocery-strategy.png 1632 1 GROCERY/out/renders/slide-*.png
```

`GROCERY` is the work folder of the grocery build. The command makes an image of all pages
of the deck in one column. Then copy `WORK/out/deck.pptx` to `docs/showcase/<deck>.pptx`.
To make the PDF, convert the deck with LibreOffice:

```sh
python3 plugins/designing-presentations/skills/designing-presentations/scripts/render.py \
  docs/showcase/grocery-strategy.pptx --out /abs/path/to/a/render/dir --keep-pdf docs/showcase/grocery-strategy.pdf
```

### The README images

`readme_images.py` makes the six images at the top of the top-level README:
`range.png`, `reference-eia.png`, `reference-samhsa.png` and the three `closeup-*.png`
files. The script lists the pages and the crop boxes that it uses. It reads renders at
2400 px wide, one folder for each deck:

```sh
R=/abs/path/to/renders
SKILL=plugins/designing-presentations/skills/designing-presentations
for d in board-transformation transit-outlook wildfire-plan lbo-committee-book grocery-strategy software-earnings parks-annual-report; do
  python3 $SKILL/scripts/render.py docs/showcase/$d.pptx --out $R/$d --width 2400
done
for d in s1-ipo-pitch-book s1-initiation-report s1-committee-pre-read; do
  python3 $SKILL/scripts/render.py docs/showcase/$d.pdf --out $R/$d --width 2400
done
python3 $SKILL/scripts/render.py /abs/path/to/AEO2026_Release_Presentation.pdf --out $R/eia --width 2400 --slides 13
python3 $SKILL/scripts/render.py /abs/path/to/2025_NNR_figure_slides.pptx --out $R/samhsa --width 2400 --slides 10
python3 showcase/readme_images.py $R docs/showcase
```

The renders of the S-1 decks come from their PDF files, because their build sources are
not in this repository. LibreOffice draws the SAMHSA file with Inter in place of Arial
Narrow, as `fonts.json` of that render reports.
