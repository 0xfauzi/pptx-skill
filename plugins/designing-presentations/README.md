# Designing presentations

This Claude Code plugin has one skill, `designing-presentations`. With it, Claude designs
native PowerPoint decks that you can edit. Examples are pitch books, investment committee
books, consulting pages, earnings decks and annual reports.

You can give Claude a reference: a company template, a past deck, any .pptx file, or a
vector or scanned PDF. The new pages then use the look of that reference. If you give no
reference, Claude chooses a look from the reader, the subject and the data.

Claude makes the design decisions. The scripts of the skill do the measurements. They read
the look of the reference and measure each line of text with the installed fonts. They
calculate the page geometry and write the .pptx file with native charts and tables. Then
they render the file with LibreOffice and read the render.

The scripts refuse a page that has a defect they can measure. These are examples:

- Text that does not fit, or text that overlaps.
- Contrast less than 3:1.
- A bridge that does not tie.
- A label that the renderer wrapped, dropped or covered.

![Page 1 of an LBO investment committee book built with no reference: seven headline figures over six tables and a bar chart, with a notes column](https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/docs/showcase/hero.png)

![Pages from a grocery strategy, an earnings deck and a parks annual report built with the skill](https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/docs/showcase/strip.png)

All companies and figures on these pages are fictional. Each image is the LibreOffice
render of the .pptx file that the build wrote.

## What the plugin runs, sends, fetches and writes

- **Runs on your machine:**
  - Python 3 scripts in the `scripts/` folder of the skill. They use lxml, Pillow,
    python-pptx, pdfplumber and, if it is installed, uharfbuzz.
  - LibreOffice (`soffice`, headless, with a new profile for each conversion). It changes
    a deck into a PDF.
  - poppler (`pdftoppm`, `pdftotext`, `pdffonts`, `pdfinfo`, `pdfimages`). It rasterises
    and reads pages.
  - fontconfig (`fc-match`, `fc-query`). It finds the installed fonts.
  - `git check-ignore`. It makes sure that git ignores a library of public decks that you
    build in the skill folder.

  The scripts install nothing. `scripts/preflight.py` prints the install command for each
  missing item. You run the commands.
- **Sends:** nothing. No script imports a network module. No command sends a file, a deck
  or a figure to a different location.
- **Fetches:** nothing while it works. LibreOffice renders an offline copy of each deck.
  In this copy, each link to an item outside the deck (hyperlinks also) points to no
  location. Thus LibreOffice does not download a picture that a deck links to on the web
  (`scripts/render.py`, `offline_copy`).

  Only one script downloads files: `refs/fetch.sh`.
  It runs only when you start it. It downloads the public reference decks that
  `refs/MANIFEST.md` lists, with curl, into the folder `refs/files/` of the skill. The
  sources are the sites of the publishers, Amazon S3, DocumentCloud and
  raw.githubusercontent.com. The script checks each file against its sha256. Without
  these decks, the build still runs and reports that its panel of reference decks is
  empty.
- **Writes:** in a work folder that you name. The scripts refuse an output path in the
  skill folder. There are two exceptions, both ignored by git: `refs/files/`, which
  `refs/fetch.sh` fills, and `refs/library/`, a library that you build from those decks.

## Install

Type this command in Claude Code (2.1.275 or later):

```
/plugin install designing-presentations --marketplace https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
```

Claude Code downloads the catalog file of the marketplace. The plugin entry then fetches
only this plugin folder from the repository (a `git-subdir` source). You can also add the
marketplace as `0xfauzi/pptx-skill`. Then Claude Code clones the full repository under
`~/.claude/plugins/marketplaces/`.

## Requirements

- Python 3.11 or later, with lxml, Pillow, python-pptx and pdfplumber.
- uharfbuzz (optional).
- LibreOffice, poppler and fontconfig.
- The fonts that your reference names, or their metric-compatible stand-ins.

Run `scripts/preflight.py` in the skill folder to see what is missing. The INSTALL.md file
of the repository gives all install methods: Claude Code, claude.ai and the Claude API. It
also gives the versions that we tested this release on:
https://github.com/0xfauzi/pptx-skill/blob/main/INSTALL.md

## Licence

MIT (see `skills/designing-presentations/LICENSE.txt`). `scripts/confusable_letters.json`
holds a subset of the Unicode confusables data under the Unicode License v3. The file
includes the notice of that licence. The reference decks that `refs/fetch.sh` downloads
belong to their publishers. They are not part of the plugin.
