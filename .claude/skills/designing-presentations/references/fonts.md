# Fonts: the report, the fonts folder, what the user supplies

## Contents
- The rule: no font is ever downloaded
- The loop
- The fonts folder
- Reading the report
- Faces a .pptx reference embeds
- Faces in a PDF reference
- What fsType allows
- Embedding in the built deck
- With no reference
- What is unmeasured

## The rule: no font is ever downloaded

Never download, fetch or install a font, and never run a command that would: no package
manager (apt, brew, pip, npm), no curl or wget, no web font service, no copy from a
website, even when the user asks for it. No script in this skill does any of these. When a
face is missing, tell the user: the font report says which faces, what the build would set
them in, and where the user can put font files they license. Installing a font on the
machine is the user's own act, outside this skill, and changes every other session's fits.

## The loop

```bash
export DECK_FONTS="$DECK_WORK/fonts"      # in the same shell call as each command, like DECK_WORK
python3 scripts/fonts.py report "$REF" -o "$DECK_WORK/ref/fonts.json"            # with a reference
python3 scripts/fonts.py report --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/ref/fonts.json"   # no reference, after step 2
```

1. Run the report. Exit 0: every face that sets text resolves; go on.
2. Exit 3: paste `fonts.md` (written beside `fonts.json`) into your response and ask the
   user, for each face it lists under "What the user can do", to either put licensed font
   files in the fonts folder it names, confirm a licence for a font the reference embeds,
   or approve the stand-in at the width shown.
3. Wait for the answer. Do not choose for the user, and do not build in the meantime.
4. Act on the answer: files supplied, run the report again; a licence confirmed, run
   `fonts.py extract` (below), then the report again; a stand-in approved, name it under
   `/typography/families/substitutes` in the completion, then run the report with
   `--guide` again.
5. Repeat until the report exits 0. Say in the final report every stand-in the user
   approved, every file they supplied, and every font extracted with their confirmation.

The report keeps the build's rule: a face with no metric-compatible stand-in is measured
only in fc-match's answer, the face the renderer draws, and only once that face is named
under `/typography/families/substitutes`; until then the build refuses each page that sets
it (`font refused`).

## The fonts folder

`DECK_FONTS` names one folder, the work folder's `fonts` directory; `fonts.py` creates it,
and until then every other script reads it as empty. Every script reads it: `fonts.py` and
the build's text ruler measure with its files, and LibreOffice draws with them, through a
fontconfig configuration that only the skill's own subprocesses get (a copy of the
accepted files in the folder's `.run` directory, with its own cache). Nothing is installed
and nothing outside the work folder changes. With `DECK_FONTS` unset, `fonts.py` refuses
by name, and the build refuses a face that only that folder holds, naming the variable.

The folder takes `.ttf`, `.otf` and `.ttc` files. Each file is read before use (size cap,
every offset checked, never run); the report lists each file it did not use and why (not
a font, a WOFF web font, a symbolic link, a file it cannot read).

## Reading the report

One row per face. `Sets` is `text` (a run or chart text is set in it), `bullets` (bullet
glyphs only) or `declared` (named, setting no text: never blocks). `Where it resolves`:

- `fonts folder`: a file the user supplied, or one `extract` wrote.
- `installed`: a file in fontconfig's folders, the user's font folders, or the standard
  macOS and Windows folders.
- `metric-compatible face`: an installed face with the same advance widths (fontconfig's
  binding="same" table: Liberation Sans for Arial, Carlito for Calibri, Gelasio for
  Georgia). Layout is faithful; letterforms are not.
- `embedded in the reference; extractable after the user confirms a licence`.
- `MISSING`, with why (a PDF subset, a restricted embedded copy, no file at all).

`styles missing` names a weight or slope the reference or the guide sets that no file
supplies (bold is never synthesised). For a missing face, `Stand-in` is fc-match's answer
and whether it is metric-compatible; `Width of the stand-in` is how much wider (+) or
narrower (-) the stand-in sets the reference's own words than the reference face, over
every upright regular-weight word, with the 10th to 90th percentile of words. It is
measured only against a PDF, whose glyph widths are in the file (the same face read back
from a PDF measures +0.2%); a .pptx stores no widths, so there it reads `cannot be
measured`. A WARNING line means the ruler found a file that fontconfig does not draw:
put a copy in the fonts folder.

## Faces a .pptx reference embeds

A .pptx lists embedded fonts in `p:embeddedFontLst` (ECMA-376 Part 1, 19.2.1.9 and
19.2.1.10); each style's font part is the font itself or an Embedded OpenType (EOT)
wrapper. `fontfiles.py` reads both, XOR-masked or not. It refuses by name a payload
compressed with MicroType Express, and a subset (only the characters the deck set: new text
would lack glyphs). A font that maps fewer than the 95 printable ASCII characters is read as a
subset too. A collection is judged by its most restrictive face. A copy the fsType allows
(below) is extracted only after the user confirms a licence:

```bash
python3 scripts/fonts.py extract "$REF"                                      # lists what it would write; exit 2
python3 scripts/fonts.py extract "$REF" --licence-confirmed "<the user's words>"
```

The second form writes each allowed font into the fonts folder and appends the user's
words, the file's sha256 and the reference's to `licence-confirmations.json` there. It
never overwrites a file: one with other bytes under the same name is refused by name;
ask the user which file to keep. Pass
the user's own confirmation, never your guess that they hold one.

## Faces in a PDF reference

`pdffonts` names every face, a subset by its tag (`ABCDEF+Jost-Regular`, read as Jost). A
PDF's embedded copy is never used to set new text: a subset holds only the glyphs the PDF
sets, and the skill does not take fonts out of a PDF. Such a face is missing until the user
supplies it, and its stand-in's width is measured against the PDF's own text.

## What fsType allows

The OS/2 table's fsType (OpenType 1.9.1) states embedding rights: whether a font may go
into a document, or come out of one. It does not limit a face installed on the machine or
supplied by the user, which is measured and rendered whatever its fsType:

| fsType | Measure and render | Embed or extract |
|---|---|---|
| 0 installable, 8 editable | yes | yes |
| 4 preview and print | yes | no |
| 2 restricted, or no OS/2 table | yes | no |

A file whose only outlines may not be embedded (bitmap-only, bit 9) is never extracted.

## Embedding in the built deck

The built deck embeds no font. LibreOffice 24.2, the one renderer here, drew none of three
test decks in their embedded font (the font itself, EOT, EOT with XOR), so a written
font could not be checked, and PowerPoint was not measured. So every face the deck names
must be on the recipient's machine: the report's "For the recipient" list says which.
Tell the user each face a recipient may lack, and say it again in the final report.

## With no reference

Run the report with `--guide` once the guide is complete: it checks every face the guide
names (families, each role's face and its bold or italic, and the face
`weight_faces` names for a weight other than 400 or 700; fallbacks set no text). The faces are your
choice; references/no-reference-design.md asks which faces the recipient has.

## What is unmeasured

- Whether PowerPoint shows a deck's embedded font: no PowerPoint runs here.
- Whether LibreOffice on macOS or Windows reads the per-process fontconfig configuration;
  it was measured on Linux only.
- How a stand-in's width difference turns into lines and page fit: the build measures
  that page by page once the stand-in is named.
