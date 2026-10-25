# Intake: render, extract, gallery, PDF triage, fonts

## Contents
- What the three intake commands produce
- What the digest cannot see
- Generated slides and corner radii
- PDF references: triage, vector pages, raster pages
- Fonts the machine lacks

## What the three intake commands produce

```bash
python3 scripts/render.py "$REF" --out "$DECK_WORK/ref/renders" --width 1600 --grid
python3 scripts/extract_style.py "$REF" -o "$DECK_WORK/ref/draft.json" --report "$DECK_WORK/ref/draft.md"
python3 scripts/gallery.py "$REF" --out "$DECK_WORK/ref/gallery" --guide "$DECK_WORK/ref/draft.json"
```

- `renders/grid.png` and one PNG per page; `renders/fonts.json`, the font report.
- `draft.json`, the guide draft with provenance on every value and the `unresolved` list
  (the open addresses you answer); `draft.md`, the evidence digest: size levels with
  votes, the role table, colour pools by use, spacing steps and margins, composition
  archetypes, chrome, motifs, register and density bands, floors, titles, the house's
  variety, and what is still open.
- `gallery/MANIFEST.md`: crops of every component, one exemplar per composition family
  with its skeleton.

Read `fonts.json`. A face rendered as a `metric_alias` (Arial as Liberation Sans) is
faithful in layout and not in letterforms: never copy letterforms from such a render. A
face marked `substituted` makes the render useless as evidence of fit. For a PDF the list
is the file's own fonts: an embedded face renders `exact`, a face the file only names is
matched like a pptx face.

`extract_style.py` prints one progress line per stage on stderr (a 205-page PDF: 48 to
50 s over three runs, 32 to 34 s of it reading the PDF). `gallery.py` needs `--guide` for
a PDF (no placeholders, so footer and page number come from the chrome the draft mined),
crops only evidence pages, and refuses a deck over its component cap (1,000) with the
count; `--pages 30-70` reads a range.

## What the digest cannot see

- `type.body` is the most frequent size level. When two or three levels are close in
  votes, the house writes at several sizes and your pages must too: match the size
  histogram, not only the role.
- Density bands are the house's own range (10th to 90th percentile of words, elements and
  covered area per page). Below the band is sparse for this house; above it is denser
  than the house ever goes.
- Composition archetypes list which pages share an arrangement of content boxes; the
  draft's Variety section measures how often the house repeats one.
- Hidden slides are walked as evidence. The digest's notes list them; when one is an
  off-style leftover, delete it from a copy (`pptx_tools.py delete`) and extract again.

## Generated slides and corner radii

Slides this skill generated carry an origin tag; the extractor and the gallery skip them
and say how many (`--include-generated` keeps them, only when you mean to treat your own
output as evidence). `/shape_language/corner_radii` is observed whenever the slides declare
preset geometry and is then never completed. A PDF declares none: the draft lists the
address open and you read it off the renders
(`{"modal_radius_emu": 0, "rounded_share": 0.0, "why": "..."}`).

## PDF references: triage, vector pages, raster pages

Of 19 reference PDFs measured, 8 are page images inside a letter-size print (an EDGAR
exhibit printed from a browser, a filing with the deck bound in, a scan with an OCR
layer). Their text layer is browser chrome or OCR output; mining it gives a house of 1pt
Times. So triage first:

```bash
python3 scripts/ooxml.py triage "$REF"      # per-page class and the deck_class; a non-PDF is refused
```

- `vector` and `vector_with_image` pages carry real type and are mined like a pptx, minus
  placeholders, layouts, chart parts and table rules, which the draft lists as open. The
  reader joins glyphs into lines, lines into text blocks (one block is one element), blocks
  into paragraphs with bullets and measured indents. A glyph turned a quarter is read at
  its true size; any other angle is left out and counted in the notes. The title is the
  block at the position titles recur at (left edge, top or bottom, on at least half the
  pages). Size never picks the title: with no recurring position `type.title` stays open.
  A wrong size in the draft is a reader defect to report, never a value to patch over.
- `raster_wrapper`, `raster_ocr` and `raster_only` pages are images. When they are the
  majority (`deck_class: raster`) the draft opens every text-derived address, takes the
  page size from the image box, and names the next step:

```bash
python3 scripts/raster_style.py "$REF" --out "$DECK_WORK/ref/raster" [--dpi 100]
```

  It measures what pixels can tell: palette by painted area, text ink as the modal dark
  pixel, chrome as pixels holding one colour on half the pages (with `chrome-mask.png`),
  margins by ink extents, line pitch by autocorrelation with a body size estimate.
  `raster.patch.json` applies through `complete_guide.py` with provenance
  `raster_inference` at confidence 0.5; `raster.md` names the dpi and size band. Faces
  cannot be read from pixels: name the family yourself from the page images. The body
  estimate was within 0.3pt on a deck rendered and re-measured, and within the stated band
  on a 104 dpi scan. A raster draft has no levels table, so a type role beyond the five it
  opens is written with `"provenance": "raster_inference"`, and `/typography/bullets` takes
  glyph, face and indent per level as the pages draw them. Run it only on a raster deck:
  on a vector PDF it still measures pixels (the McKinsey board PDF reads surface 051B2D
  and no margins) and adds nothing the vector reader did not.
- `other_size` pages (a memo bound in front) are excluded; `--pages 7-60` restricts the
  extraction to a range you choose from the triage table.

## Fonts the machine lacks

`python3 scripts/preflight.py --reference "$REF"` lists every face the reference names with
what this machine draws it as, and prints the install commands for what is missing.

The solver measures with the font files it has (`fc-list`). With no metric alias for the
reference's face (Arial, Calibri, Cambria, Times New Roman and Courier New have one), the
solver refuses rather than measure another face under that name. The refusal names the
face LibreOffice draws it with (`fc-match <family>`); record exactly that face under
`/typography/families/substitutes` in the completion (`{"Verdana": "Inter"}`). A stand-in
other than fc-match's answer is refused, because the solver would then fit text in one
face while the render draws another (Verdana measured as DejaVu Sans and drawn as Inter
put a table row on one line that the build had wrapped). Every page that sets such a face
reads `status: unfittable`, `reason: font refused` until it is recorded.

`render.py` and the solver read metric aliases from one table (`textfit.py`, fontconfig's
17 binding="same" classes). Helvetica is not an alias of Liberation Sans: without Nimbus
Sans or TeX Gyre Heros installed, a Helvetica deck reports `substituted`. A face that draws
bullet glyphs only (`bullets_only`) does not set the gallery's verdict: on keybank the
verdict `metric_substituted` comes from Arial drawn as Liberation Sans and Calibri as
Carlito (same metrics, other letterforms), not from Wingdings, and the gallery's warning
names each face and what it means. `fonts.json` lists
per face `uncovered_count` and an `uncovered_sample`; the gallery refuses with
`uncoverable_characters` when any face has one, because a crop in a fallback face teaches
the wrong letterforms. Install a face that covers the script first.
