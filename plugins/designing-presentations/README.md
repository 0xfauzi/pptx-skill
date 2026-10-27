# Designing presentations

A Claude Code plugin with one skill, `designing-presentations`, with which Claude designs
native, editable PowerPoint decks: pitch books, investment committee books, consulting
pages, earnings decks, annual reports. Give it a reference (a company template, a past
deck, any .pptx, or a vector or scanned PDF) and the new pages take that reference's look;
give it none and Claude reasons a look out from the reader, the subject and the data.

Claude designs; the skill's scripts measure. They read the reference's look, measure every
line of text in the installed fonts, solve the page geometry, write the .pptx with native
charts and tables, render it with LibreOffice, read the render back and refuse a page whose
defect can be measured (text that does not fit or overlaps, contrast under 3:1, a bridge
that does not tie, a label the renderer wrapped, dropped or covered).

![Page 1 of an LBO investment committee book built with no reference: seven headline figures over six tables and a bar chart, with a notes column](https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/docs/showcase/hero.png)

![Pages from a grocery strategy, an earnings deck and a parks annual report built with the skill](https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/docs/showcase/strip.png)

Every company and figure in these pages is fictional; each image is LibreOffice's render of
the .pptx the build wrote.

## What it runs, sends and fetches

- **Runs, on your machine:** Python 3 scripts in the skill's `scripts/` folder (with lxml,
  Pillow, python-pptx, pdfplumber and, if installed, uharfbuzz), LibreOffice (`soffice`,
  headless, a fresh profile per conversion) to turn a deck into a PDF, poppler
  (`pdftoppm`, `pdftotext`, `pdffonts`, `pdfinfo`, `pdfimages`) to rasterise and read
  pages, fontconfig (`fc-match`, `fc-query`) to find installed fonts, and `git check-ignore`,
  to confirm that a library of public decks built inside the skill folder is ignored by git.
  The scripts install nothing: `scripts/preflight.py` prints the install command for
  whatever is missing, for you to run.
- **Sends:** nothing. No script imports a network module, and no command sends a file,
  a deck or a figure anywhere.
- **Fetches:** nothing while it works. LibreOffice renders an offline copy of each deck in
  which every link to something outside the deck, hyperlinks included, points nowhere, so a
  picture a deck links to on the web is not downloaded (`scripts/render.py`, `offline_copy`). The one script that
  downloads is `refs/fetch.sh`, and only when you run it: it fetches the public reference
  decks listed in `refs/MANIFEST.md` (from the publishers' own sites, Amazon S3,
  DocumentCloud and raw.githubusercontent.com) with curl into the skill's `refs/files/`
  folder and checks each against its sha256. Without them the build still runs and says
  its panel of reference decks is empty.
- **Writes:** under a work directory you name; an output path inside the skill folder is
  refused by name. The exceptions are the git-ignored folders for the public reference decks:
  `refs/files/`, which `refs/fetch.sh` fills, and `refs/library/`, a library built from them.

## Install

In a Claude Code session (2.1.275 or later):

```
/plugin install designing-presentations --marketplace https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
```

From a marketplace URL, Claude Code downloads the one catalog file, and the plugin entry
fetches this plugin folder alone from the repository (a `git-subdir` source). Adding the
marketplace as `0xfauzi/pptx-skill` works too, and clones the whole repository, its
development material included, under `~/.claude/plugins/marketplaces/`.

## Requirements

Python 3.11 or later with lxml, Pillow, python-pptx and pdfplumber (uharfbuzz optional);
LibreOffice, poppler and fontconfig; the fonts your reference names, or their
metric-compatible stand-ins. Run `scripts/preflight.py` in the skill to see what is
missing. Every install route (Claude Code, claude.ai, the Claude API) and the versions this
release was measured on are in the repository's INSTALL.md:
https://github.com/0xfauzi/pptx-skill/blob/main/INSTALL.md

## Licence

MIT (see `skills/designing-presentations/LICENSE.txt`). `scripts/confusable_letters.json`
holds a subset of the Unicode confusables data under the Unicode License v3, whose notice it
carries. The reference decks `refs/fetch.sh` downloads belong to their publishers and are
not part of the plugin.
