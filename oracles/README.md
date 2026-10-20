# Oracles

The scripts PORT_AUDIT.md cites as the "Checked by" evidence. Each compares the skill
against something it did not write: deckgen's own code, deckgen's recorded fixtures, a
brute force, or a deck a rater calls wrong. None is a unit test and none runs in CI; they
are re-run by hand when the ported code changes, and the numbers below are what each
printed on the date given, against the skill at the commit that ships this file.

Every script needs a deckgen checkout (read-only) at /home/user/deckgen and, unless noted,
runs from it with deckgen's environment:

    cd /home/user/deckgen && uv run python -I /path/to/pptx-skill/oracles/<script>

Environment variables (all optional):

- `PPTX_SKILL`: the skill under test. Default: the repo this directory sits in.
- `DECKGEN`: the deckgen checkout. Default: the working directory.
- `ORACLE_OUT`: where intermediate files go. Default: a fresh temporary directory.
  Nothing is written into either repo.

## diff_oracle.py: the extractor against deckgen's compile_draft

    uv run python -I oracles/diff_oracle.py jazz keybank netflix exhibits

For each named deck under `$DECKGEN/fixtures/corpus/`, runs deckgen's
`deckgen_server.style.compiler.extract` in process and the skill's
`python3 -I scripts/extract_style.py` as a subprocess, then prints one row per type role,
colour role, spacing step, floor, density band, motif list, archetype count and
unresolved count, flagged `<-- differs` where the JSON is not identical (float bands that
differ only in rounding are flagged too).

Last run 2026-10-20: 160 rows over the four decks, 47 flagged. Substantive differences:

- type sizes: jazz h1 18 against 14 and h2 14 against 13; netflix h1 18 against 19 and
  h2 14.5 against 15; exhibits axis_label and data_label 18 against null (and the chart
  floor 18 against null). title, body, emphasis and caption sizes agree on all four
  (exhibits has no emphasis or caption on either side); netflix body and emphasis
  differ on a member other than size (body space_before_pt 2.88 against 2.4). The other floors and space.margin agree.
- colour roles: ink_muted null against 113D63 on keybank and netflix (the port requires
  two runs, deckgen accepts one: a recorded deviation); color.rule 113D63 against
  000000 / FF0000 / C0504D on jazz, keybank and netflix, and jazz accent1..3 shifted one
  place (113D63 is now assigned to rule). surface and ink agree on all four.
- spacing: jazz space.md and space.lg, keybank space.xs and space.sm differ.
- density: words_per_slide differs on all four; content_area_fraction agrees to
  rounding on jazz, keybank and netflix, and differs on exhibits (low 0.2412 against
  0.144).
- archetypes: the port mines 13 / 8 / 6 / 2 where deckgen's draft carries 0;
  unresolved 24 / 33 / 30 / 33 against 58 / 51 / 69 / 85.

The same script run against the skill at 11f84c8 (the commit whose audit row first cited
it) also flags 47 rows; the type-size and content-area differences above were already
there. The colour-role rows changed since: at 11f84c8 jazz rule and accents agreed and
keybank / netflix accent1 differed.

## oracle_compare.py: the layout solver against deckgen's solver

    uv run python -I oracles/oracle_compare.py

Converts each default-house specimen SlideModel
(`$DECKGEN/fixtures/default_house_style/specimen/slides/*.json`) to the port's spec, solves
it with deckgen's `layout.solver.solve` and the port's `layout.solve_tree` at scales 1.0,
0.85 and 0.73, and compares every box; then compares the shared validation codes at 1.0.

Last run 2026-10-20 (tail):

    ignored annotation/chrome elements: 0
    TOTAL boxes compared: 383 max diff over all slides and scales: 0 validation agreement: 14 / 14

14 specimen slides.

## ruler_oracle.py, ruler_compare.py, ruler_cases.py, ruler_agreement.txt: the text ruler

    uv run python -I oracles/ruler_oracle.py  $ORACLE_OUT/ruler_oracle.json   # deckgen's HarfBuzz measure_text
    uv run python -I oracles/ruler_compare.py $ORACLE_OUT/ruler_oracle.json   # the port's rulers on the same cases

`ruler_cases.py` holds the 90 shared (text, width) cases. The oracle writes deckgen's line
breaks, line widths and advances; the compare runs the port's Pillow x128 ruler and, when
uharfbuzz is importable (it is in deckgen's environment), its HarfBuzz ruler.
`ruler_agreement.txt` is the recorded output; the run of 2026-10-20 printed it again
line for line: Pillow 89/90 exact breaks (90/90 same line count, max line width
difference 140155 EMU on the kerning case), HarfBuzz 90/90 with 0 EMU difference.

## gallery_judge.py: the gallery against deckgen's recorded manifests

    uv run python -I oracles/gallery_judge.py

Checks `extract_style.hungarian_max` against brute force on 300 random matrices up to
5x5, then drives `gallery.py`'s geometry pipeline (no render) on jazz, keybank and netflix
and diffs components, candidates, clusters, crops, exemplars and skeletons against
`$DECKGEN/fixtures/gallery/<deck>/`.

Last run 2026-10-20: Hungarian 300 of 300; component, candidate, cluster, crop and
exemplar counts equal on all three; crop rows matching exactly: jazz 22 of 24 (missing
crop-23, the slide 19 table block; an extra slide 17 text block in its place), keybank
12 of 12, netflix 14 of 14; every committed skeleton identical. The jazz mismatch is the
same at cdaa54e, the commit whose audit row first cited this script.

## triage_probe.py: per-page facts behind the PDF triage thresholds

    uv run python -I oracles/triage_probe.py ref1.pdf ref2.pdf ...

Prints, for the first 12 pages of each PDF, page size, char count, image count, image
coverage, chars inside images, the size histogram and fonts of the text layer. The
thresholds in `ooxml.pdf_triage` were read off its output over 19 PDFs: deckgen's 11
under `fixtures/corpus/consulting/` and the 8 bank decks `refs/fetch.sh` downloads.
Needs pdfplumber (deckgen's environment has it).

## build_gaming.py: five decks the judge must fail

Plain python3, from the skill repo (needs python-pptx and lxml):

    python3 -I oracles/build_gaming.py OUT_DIR keybank.pptx honest.pptx template.pptx

`honest.pptx` is a generated section on keybank (for example `scripts/build_deck.py
examples/keybank-section.deck.json ...`), `template.pptx` is
`scripts/pptx_tools.py template keybank.pptx`. Writes g1_scramble (shapes moved at
random), g2_stack (every shape at 0,0), g3_overflow (the honest section with every run
repeated 12 times), g4_giant (one page-sized text box per slide) and g5_random (nine
random boxes in keybank's values). Judge each with
`python3 -I scripts/fingerprint.py compare OUT_DIR/gN.pptx --reference keybank.pptx`.

Last run 2026-10-20, honest section built from examples/keybank-section.deck.json on a
guide completed from a fresh keybank draft:

| deck | overlap | overflow | layout_clean |
|---|---|---|---|
| g1_scramble | 1.0 | 0.0 | false |
| g2_stack | 1.0 | 0.0 | false |
| g3_overflow | 0.0 | 1.0 | false |
| g4_giant | 0.0 | 1.0 | false |
| g5_random | 1.0 | 0.6 | false |
| honest section | 0.0 | 0.0 | true (total 0.086) |

## raster_keybank.sh: the raster instrument on a deck whose values are known

Plain sh and python3, from the skill repo:

    sh oracles/raster_keybank.sh [keybank.pptx] [out_dir]

Renders keybank at 100 dpi with `scripts/render.py`, then measures the renders with
`scripts/raster_style.py --page-emu 9144000x6858000` as if they were a scan; compare
`out_dir/raster/raster.md` with the OOXML draft.

Last run 2026-10-20: surface FFFFFF; accent1 113D63; ink 010101 (OOXML 000000); top rule
at 0.90 in and bottom rule at 6.92 in, both 113D63; margins left 388620, right 502920,
top 434340, bottom 617220 EMU (0.425, 0.55, 0.475, 0.675 in); modal pitch 14pt over 11
pages, with 14.4pt on 3 of the 11; modal ink-run height 9pt (44 runs).
