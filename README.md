# designing-presentations

designing-presentations is an Agent Skill and a Claude Code plugin. With it, Claude
designs native PowerPoint decks that you can edit. Examples are pitch books, investment
committee books, consulting pages, earnings decks and annual reports.

You can give Claude a reference: a company template, a past deck, any .pptx file, or a
vector or scanned PDF. The new pages then use the look of that reference. If you give no
reference, Claude chooses a look from the reader, the subject and the data.

Claude makes the design decisions. It chooses the storyline, the layout of each page, each
exhibit, each annotation and each colour. The scripts of the skill do the measurements.
They read the look of the reference and measure text with the installed fonts. They
calculate the page geometry and write the .pptx file with native charts and tables. Then
they render the file with LibreOffice, read the render, and refuse a page that has a
defect they can measure.

![Twelve pages from ten decks that the skill built: pitch book, LBO committee book, three pages of a board deck, strategy pre-read, initiation report, quarterly results, committee pre-read, two pages in the look of US government decks, a roadmap and an annual report](docs/showcase/range.png)

The image above shows twelve pages from ten decks in the gallery below. Each image of a new
page in this README is the LibreOffice render of the .pptx file that the build wrote.

| Row | Left | Right |
|---|---|---|
| 1 | IPO pitch book: headline figures, an annotated revenue chart, the offering terms | LBO committee book: a returns table, a value bridge, four sensitivity tables |
| 2 | Board deck: three approvals, eight target tiles with small bar charts | Strategy pre-read: a scatter of 214 stores in four zones, an action table |
| 3 | Initiation report: a margin chart and a bridge to adjusted income | Board deck: two maps of plant moves, three tables, three figure tiles |
| 4 | Quarterly results: six figure tiles with small charts, three tables | Committee pre-read: a diagram of who elects the board, share-class tables |
| 5 | Transit outlook: three small charts with ranges, in the look of an EIA deck | Wildfire plan: ranked bars and a table, in the look of a SAMHSA deck |
| 6 | Board deck: a roadmap of twelve initiatives with milestones | Parks annual report: ranked bars with a bracket callout, a table |

The IPO pitch book, the initiation report and the committee pre-read use figures from the
public Form S-1 of Anthropic, PBC. These decks are unofficial demonstrations and are not
investment advice. The organisations on the other pages are fictional, and their figures
are illustrative. The gallery gives the details.

## What the skill can do

- **Use the look of a reference, or choose a look.** The skill reads a .pptx file through
  its masters, layouts and theme. It sorts the pages of a PDF into vector pages and
  scanned pages, and it measures a scanned page from its pixels. The style guide records
  each value and the source of that value. With no reference, Claude writes a short look
  brief (reader, subject, data, brand, restraint) and chooses each value. No value has a
  default.
- **Make dense pages.** A page can hold many exhibits, and each exhibit gets the size that
  the solver calculates for it. Each page of the LBO committee book in the gallery holds five
  to nine tables and charts.
- **Write native exhibits.** Charts are PowerPoint charts, and their data is in the file.
  Tables are PowerPoint tables. The file
  `plugins/designing-presentations/skills/designing-presentations/references/chart-recipes.md`
  has worked examples for bridges, valuation ranges, a mekko chart and a price-and-volume
  chart.
- **Annotate exhibits.** The skill can put marks on a chart or on table cells. The marks
  include reference lines, bands, brackets, callouts, badges, outline boxes and rows
  aligned to categories. Any OOXML shape can also be a mark. If a mark has no words that
  explain it, the build gives a warning.
- **Use logos and icons.** The skill can use pictures from your files, pictures from the
  reference, and small SVG icons in the colours of the deck.
- **Measure text fit.** The skill measures each text box, table cell and label in the
  font that the renderer will draw. It uses HarfBuzz, or Pillow if the machine does not
  have HarfBuzz. If the machine does not have the font that a page names, and the guide names
  no stand-in font, the build refuses the page. If a page does not fit, the report tells you what
  to change.
- **Refuse defects that it can measure.** The build refuses a page that has one of these
  defects:
  - Text that does not fit, or text that overlaps.
  - Contrast less than 3:1.
  - A bridge that does not tie.
  - An exhibit with no written brief.
  - A render that is different from the file.

  A totals row that does not tie gives a warning. All other decisions belong to Claude.
  The report shows each decision next to the habits of the reference.

## Your reference, your look

For each pair, the reference page is on the left and the new page is on the right. The
new pages have their own subject and figures, and they use the look of the reference.

![Left: a page of three line charts from the EIA Annual Energy Outlook 2026 presentation. Right: a new page of three line charts on fares and costs of a fictional transit authority, in the same look](docs/showcase/reference-eia.png)

*Left: page 13 of the Annual Energy Outlook 2026 release presentation (a PDF) of the U.S.
Energy Information Administration. Right: a page of the transit outlook in the gallery. The
reference is a US government work, so it is in the public domain.*

![Left: a line chart and trend table from the SAMHSA 2025 NSDUH figure slides. Right: a new line chart and table on acres treated by a fictional forestry program, in the same look](docs/showcase/reference-samhsa.png)

*Left: slide 10 of the 2025 NSDUH figure slides (a .pptx file) of the Substance Abuse and
Mental Health Services Administration. Right: page 1 of the wildfire plan in the gallery,
built on the masters of that file. The reference is a US government work, so it is in the
public domain.*

The two new sections show fictional organisations. Their figures are illustrative. The
agencies did not prepare these pages and have no affiliation with them.

## Up close

These crops show three regions of gallery pages at a larger scale than the image above.

![Two risk heat maps before and after mitigation beside a risk register, a table of risks by zone and a table of early-warning indicators](docs/showcase/closeup-risk.png)

*Page 8 of the board deck. Two heat maps put nine risks on a grid of likelihood and
severity, before and after mitigation. The register, the zone table and the indicator table
use the same risk IDs and the same zone colours.*

![A table that builds sponsor equity from exit EBITDA to IRR, beside a value creation bridge with costs in red](docs/showcase/closeup-returns.png)

*Page 4 of the LBO committee book, top left. The table builds the sponsor's returns from
exit EBITDA to IRR. The bridge shows each step from equity invested to equity to holders,
with its value above the plot.*

![A bar chart of compute contracts with brackets that group floors and ceilings, above a table of the aggregates that the S-1 states](docs/showcase/closeup-commitments.png)

*Page 4 of the initiation report, left column. Two brackets put the contract floors and the
ceilings into two groups, and each bracket has a note. The table under the chart lists the
totals that the S-1 states.*

## Examples of requests

- "Here is our pitch book template, `bank_template.pptx`. Use `comps.csv` and
  `model.csv`. Build a four-page valuation section for Project Atlas. Include a summary,
  trading comps, a football field that marks the $36.50 offer, and the accretion bridge."
- "No template. Write a five-page steering committee pre-read on our store format strategy
  from `stores.csv`. The audience is the board. Every title must state the finding."
- "Use the look of `board_pack.pdf` (a scan) for two new pages on the capital plan."
- "Add a returns sensitivity page to `ic_book.pptx`, in the style of the pages of the deck."
- "Use our logo, `logo.png`, instead of the logo of the template firm. Remove the name of
  the firm from the footer."

## Install

[INSTALL.md](INSTALL.md) gives all the steps. It also gives the versions that we tested
this release on.

### Claude Code, as a plugin

Type this command in Claude Code:

```
/plugin install designing-presentations --marketplace https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
```

The command adds the marketplace and installs the plugin. Claude Code downloads only the
catalog file and the plugin folder. The skill then loads as
`/designing-presentations:designing-presentations`. Claude also uses the skill
automatically when you ask for slides.

### Claude Code, manual install

1. Copy the folder `plugins/designing-presentations/skills/designing-presentations/`.
2. Put the copy in `~/.claude/skills/` for all projects, or in `.claude/skills/` of one
   project.
3. Keep the folder name `designing-presentations`. This name must be the same as the
   `name` of the skill.

### claude.ai

1. Build the upload zip from the root of this repository:

   ```bash
   python3 tools/package_skill.py          # writes dist/designing-presentations.zip
   ```

   If the packager refuses a `__pycache__` folder, delete that folder and run the
   command again.
2. In claude.ai, go to Customize > Skills and upload the zip.
3. Turn on the skill. Code execution must be on.
4. Ask Claude to run `scripts/preflight.py`. This script shows if the sandbox has
   LibreOffice and the necessary packages.

The zip holds one top-level folder, `designing-presentations/`. The zip holds only the
files that git tracks in that folder, as committed. The packager refuses a file that git
does not track and any content that an upload would reject. INSTALL.md lists the rules.

### Claude API

Upload the same folder through the Skills API. INSTALL.md gives the commands. The
container of the API has no network access and cannot install packages. So the skill
can run there only if the container already has the packages that the skill needs.
`scripts/preflight.py` shows which packages are missing.

## Requirements

- Python 3.11 or later, with lxml, Pillow, python-pptx and pdfplumber.
- uharfbuzz (optional). It gives a better text ruler.
- LibreOffice, poppler and fontconfig.
- The fonts that your reference names, or their metric-compatible stand-ins.

The skill installs nothing. Run `scripts/preflight.py` in the skill folder. The script
lists what is missing and prints the install command for your platform. Install the
fonts before you build, because the skill measures text with the installed fonts.

## How the skill works

1. **Intake.** The skill renders the reference, extracts its look into a draft guide, and
   cuts its exhibits into a gallery. The draft records the source of each value. With no
   reference, the draft is blank.
2. **Guide.** Claude gives a value for each open item in the draft. With no reference,
   all items are open.
3. **Plan.** Claude writes the storyline and a brief for each exhibit. The brief says what
   the reader must see, which forms Claude compared, and why it chose one. A script
   calculates and checks each figure that a title states.
4. **Page specs.** Each page is a tree of regions and elements. The spec uses roles (a
   type role, a colour role, a spacing step). It never uses a literal size, colour or
   coordinate.
5. **Build.** The solver puts each box on the page, and the text ruler measures each line.
   The emitter writes the .pptx file on the masters of the reference, or on a blank
   master. LibreOffice renders the file, and the build reads the render. The build refuses
   a page with a defect that it can measure, and it tells you what to change.
6. **Review.** Claude examines each render at full size against the brief of each
   exhibit. Claude then makes corrections, builds again and validates the package.

The file
[SKILL.md](plugins/designing-presentations/skills/designing-presentations/SKILL.md)
gives the full workflow, step by step.

## Gallery

### Three decks from a public S-1

The skill built these three decks from the public Form S-1 of Anthropic, PBC, filed on
26 October 2026. It used no reference deck. Claude chose the look of each deck.

- The bank, the broker and the fund are fictional: Halden & Rowe, Keswick Research and
  Marlow Street Capital.
- Each page has this footer: "Unofficial demonstration built from Anthropic, PBC's public
  Form S-1 (filed 26 October 2026). Not prepared by or affiliated with Anthropic. Not
  investment advice."
- Valuations, forecasts, probabilities, sizes and price limits are illustrative
  assumptions of the fictional firm. The decks label them as assumptions.
- Each page names the section of the S-1 that its figures come from. You can check
  each figure against the filing. If a figure on a page is different from the S-1, the S-1
  is correct.

The build sources of these three decks are not in this repository.

| Deck | Pages | All pages | Files |
|---|---|---|---|
| IPO pitch book of a fictional bank: situation overview, business model, revenue growth, customers, margins, compute commitments, balance sheet, public comparables, illustrative valuation, offering structure and governance, timetable (US letter) | 11 | [image](docs/showcase/s1-ipo-pitch-book.png) | [.pptx](docs/showcase/s1-ipo-pitch-book.pptx), [PDF](docs/showcase/s1-ipo-pitch-book.pdf) |
| Initiation of coverage by a fictional broker: thesis and key data, revenue drivers, unit economics, compute commitments, path to profit, key risks, forecast, valuation scenarios (16:9) | 8 | [image](docs/showcase/s1-initiation-report.png) | [.pptx](docs/showcase/s1-initiation-report.pptx), [PDF](docs/showcase/s1-initiation-report.pdf) |
| Investment committee pre-read of a fictional fund: recommendation and size, growth and margins, ten risks, governance, scenarios, sizing rules and conditions (16:9) | 6 | [image](docs/showcase/s1-committee-pre-read.png) | [.pptx](docs/showcase/s1-committee-pre-read.pptx), [PDF](docs/showcase/s1-committee-pre-read.pdf) |

### Seven decks about fictional organisations

The skill built these seven decks. All organisations and figures are fictional. Each deck
has a figures script, a plan, a completion and page specs. Each build passed all checks
and both package validations. The folder [showcase/](showcase/README.md) holds the sources
and the commands that build each deck and image again.

Five decks have no reference. Two decks use the look of a public US government deck:

- The transit outlook uses the look of the Annual Energy Outlook 2026 release
  presentation, a PDF of the U.S. Energy Information Administration (EIA).
- The wildfire plan uses the look and the masters of the 2025 NSDUH figure slides, a .pptx
  file of the Substance Abuse and Mental Health Services Administration (SAMHSA).

These two references are US government works, so they are in the public domain.
[showcase/README.md](showcase/README.md) gives the address of each. This repository does
not include them.

| Deck | Reference | Pages | All pages | Files |
|---|---|---|---|---|
| Board deck of a medical device maker on an operating transformation: decision, order to cash, plant footprint, prioritisation, EBITDA bridge and cash, roadmap, operating model, delivery risks (16:9) | None | 8 | [image](docs/showcase/board-transformation.png) | [.pptx](docs/showcase/board-transformation.pptx), [PDF](docs/showcase/board-transformation.pdf) |
| Section of a transit authority's ten-year outlook: ridership, fare revenue, capital plan, funding gap, cost per boarding, project timeline (16:9) | EIA, PDF | 6 | [image](docs/showcase/transit-outlook.png) | [.pptx](docs/showcase/transit-outlook.pptx), [PDF](docs/showcase/transit-outlook.pdf) |
| Section of a state forestry program's wildfire plan: acres treated, hazard by county, cost per acre, crews and equipment, schedule, hazard reduction (16:9) | SAMHSA, .pptx | 6 | [image](docs/showcase/wildfire-plan.png) | [.pptx](docs/showcase/wildfire-plan.pptx), [PDF](docs/showcase/wildfire-plan.pdf) |
| LBO investment committee book: company overview, sources and uses, operating model, returns and sensitivities, debt capacity, exit (US letter) | None | 6 | [image](docs/showcase/lbo-committee-book.png) | [.pptx](docs/showcase/lbo-committee-book.pptx), [PDF](docs/showcase/lbo-committee-book.pdf) |
| Grocery store format strategy: market shift, format economics, customer segments, network rationalisation, three-year plan (16:9) | None | 5 | [image](docs/showcase/grocery-strategy.png) | [.pptx](docs/showcase/grocery-strategy.pptx), [PDF](docs/showcase/grocery-strategy.pdf) |
| Software company quarterly results: highlights, revenue and ARR, unit economics, margin, guidance (16:9) | None | 5 | [image](docs/showcase/software-earnings.png) | [.pptx](docs/showcase/software-earnings.pptx), [PDF](docs/showcase/software-earnings.pdf) |
| National parks annual report: visitors, conservation, budget, volunteers, priorities (16:9) | None | 5 | [image](docs/showcase/parks-annual-report.png) | [.pptx](docs/showcase/parks-annual-report.pptx), [PDF](docs/showcase/parks-annual-report.pdf) |

The `examples/` folder of the skill holds worked inputs:

- With a bank pitch book (pptx) as the reference: a four-page section, four annotated
  pages, two bridge pages and a round trip.
- With a McKinsey board PDF as the reference: two pages.
- With no reference: a three-page board review and a two-page credit paper.

The reference examples come from public decks. The bank pitch book is a Mergers and
Inquisitions training deck, and the PDF is from a public board packet. The new pages have
their own text. The round trip builds page 3 of the bank deck again. It keeps the roles,
weights and figures of that page, but it uses new words for each text run.

## Limits

- **No arrangement search.** If a page does not fit, the solver reports the groups that
  can split and the rows of each table that fit (`scripts/layout.py`). Claude then
  changes the arrangement, removes words or splits the page.
- **One renderer.** All render checks read the drawing of LibreOffice 24.2.7. The skill
  measured PowerPoint only for text-box fit and table row heights
  (`references/gotchas.md`). The skill measured the positions of chart labels and
  annotations in LibreOffice only. No measurement shows the order of the legend of a
  horizontal bar chart in PowerPoint. LibreOffice lists the last series first.
- **Half-point sizes.** At some half-point sizes, LibreOffice draws a line wider than the
  text ruler measures it. The build refuses a table cell or text line that the renderer
  wraps (`renderer divergence`). The build cannot predict this before the render.
- **Chart text spacing.** At small sizes, LibreOffice draws Carlito (the stand-in for
  Calibri) chart labels with incorrect word spaces. It also draws Liberation Sans (the
  stand-in for Arial) chart figures with uneven gaps between glyphs. For this reason, the
  committee book in the gallery sets its chart text in Arial. Its bridge shows its figures
  as a row of text above the plot (`category_row`).
- **Leakage and stated figures give reports, not refusals.** The build lists each name,
  figure and phrase of the reference that it finds in the new deck. It also warns if a
  figure that the plan states is not on the page. Claude removes or explains each item in
  the final report. No measurement supports the matching rules and thresholds of the
  leakage report.
- **Source lines.** The build warns about a data page with no source line in two cases:
  - At least half of the data pages of the reference have a source line.
  - The data does not show the habit of the reference.
  The limits (`SOURCE_LINE_MAJORITY`, `SOURCE_LINE_MIN_PAGES` in `scripts/build_deck.py`)
  are definitions, not measurements.
- **Football-field ticks.** The football-field component starts each axis tick label at
  its value. The last label aligns right at the end of the track. The component removes a
  tick if its label does not fit its interval (`components/football_field/expand.py`).
  Read the axis on each render.
- **Hidden slides.** The skill reads hidden slides as evidence. The draft lists them. To
  exclude a hidden slide, Claude deletes it from a copy of the reference.
- **Scanned PDFs.** From the pixels of a scan, the skill gets the palette, ink, chrome,
  margins and line pitch. The confidence of these values is at most 0.5
  (`scripts/raster_style.py`). The skill gets no font data from a scan. Claude names the
  font family from the image.
- **The judge.** The judge compares a deck with its reference and with a panel of public
  decks. `DEFAULT_WEIGHTS` in `scripts/fingerprint.py` gives its weights and the method
  that fitted them. A deck that the judge files under its
  reference is not necessarily a good deck. Claude must examine each render.

## Evidence that you can run again

Each row gives a result and the command that makes it again. Run the commands from the
root of this repository. Some rows need the public reference decks. To download them, run
`sh plugins/designing-presentations/skills/designing-presentations/refs/fetch.sh`. These
results come from Ubuntu 24.04 with LibreOffice 24.2.7.2 and the versions in INSTALL.md.

| Result | Measurement | Command |
|---|---|---|
| The seven gallery decks about fictional organisations build and pass | Each build exits 0. `validate --render` and `validate --emit --guide` report no problems for each deck. | `sh showcase/rebuild.sh DECK /abs/work/dir`, for each of `board-transformation`, `lbo-committee-book`, `grocery-strategy`, `software-earnings`, `parks-annual-report`. Add `/abs/path/REF` for `transit-outlook` and `wildfire-plan` (showcase/README.md) |
| The judge files a section in the look of a reference under that reference | The keybank example section has a judge total of 0.083. The pages of the reference itself are at 0.055 to 0.372. The judge files the section under the reference, and the layout is clean. | `sh tools/measure/judge_keybank.sh /abs/out/dir` (the `deck.pptx` line) |
| Only the layout check separates five wrong decks from the reference | The judge totals of the five wrong decks are 0.134 to 0.308, in the spread of the reference. So the style total alone files each wrong deck under the reference. Each wrong deck has `layout_clean` false. Overlap is 1.0 for the scrambled, stacked and random decks. Overflow is 1.0 for the overflowing and giant-box decks, and 0.6 for the random deck. | `sh tools/measure/judge_keybank.sh /abs/out/dir` (the `g1` to `g5` lines) |
| The raster instrument reads a render back | The script renders keybank at 100 dpi and measures the pixels. The surface (FFFFFF) and the navy (113D63) are exact. The ink is 010101 against 000000 in the file. The left margin is within 0.01 in of the file, and the other margins are within 0.09 in. The body size estimate is 11.7pt against 12pt in the file. | `sh tools/measure/raster_keybank.sh`, then compare `raster/raster.md` with the draft of `scripts/extract_style.py` |
| Chart positions agree with LibreOffice | The script reads 474 features of 15 chart configurations and a table. The largest offset from the prediction of `scripts/chart_geometry.py` is 1.07 px, and the mean is 0.236 px, at 1600 px wide. The script did not find 7 features within 7 px of the prediction. The script reports that a later series can cover such a feature. | `python3 -I tools/measure/chart_geometry_probe.py /abs/out/dir` |

## Repository layout

```
.claude-plugin/marketplace.json   the marketplace (name pptx-skill), with one plugin
plugins/designing-presentations/  the plugin root; an install copies only this folder
  .claude-plugin/plugin.json      the plugin manifest; icon.png is the listing icon
  README.md                       what the plugin runs, sends, fetches and writes
  skills/designing-presentations/ the skill: SKILL.md, references/, scripts/,
                                  components/, examples/, refs/
showcase/                         the sources of the seven fictional-organisation decks, and the scripts
                                  that build the decks and the README images
docs/showcase/                    the gallery images, .pptx files and PDF files
tools/package_skill.py            builds the upload zip for claude.ai and the API
tools/make_icon.py                draws the plugin icon
tools/measure/                    the measurement scripts in the evidence table
```

## Contribute

1. Make your change.
2. Build the seven gallery decks again with `showcase/rebuild.sh` (see
   [showcase/README.md](showcase/README.md)). Each build must pass.
3. Run `claude plugin validate . --strict` from the root of this repository.
4. Run `python3 tools/package_skill.py` after you commit. The packager reads the
   committed files only.

## Licence

MIT, copyright 2026 0xfauzi: [LICENSE](LICENSE). The skill has the same text in its
`LICENSE.txt`.

`scripts/confusable_letters.json` holds a subset of the Unicode confusables data under the
Unicode License v3. The file includes the full notice of that licence.

The public reference decks that `refs/fetch.sh` downloads belong to their
publishers. This repository does not include them, and the plugin does not ship them.
`refs/MANIFEST.md` names the source of each deck.
