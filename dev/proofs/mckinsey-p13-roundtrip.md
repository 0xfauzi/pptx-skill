# Round trip of the McKinsey board PDF, page 13

The reference: `mckinsey-calstrs-future-of-boards-2024.pdf` (CalSTRS, 2024; a public board
packet, 17 pages, not under `refs/`). Round 8, on a guide completed from a fresh draft with
`examples/mckinsey-pdf.completion.json` (the rebuild's `mk/guide.json`):

    python3 -I scripts/import_slide.py REF.pdf --slide 13 --guide guide.json -o rt.deck.json
    python3 -I scripts/build_deck.py rt.deck.json --guide guide.json --template tpl.pptx \
      -o b/deck.pptx --reference REF.pdf --renders b/renders --chrome draw

The build report is not kept here: it quotes the deck's text. What it said:

| | |
|---|---|
| build | PASS: page import-13 fit at scale 1.0 |
| judge total | 0.1 |
| reference's own pages (leave-one-out) | min 0.082, median 0.143, p90 0.277, max 0.355 over 17 pages |
| nearest is the reference | True |
| filed under the reference | True |

Read beside the PDF page at 60 dpi: the gradient ground is drawn; the ring diagram (three
arcs) is lost, its centre label set as a heading and its numbers falling into the text as
loose digits, and the three blocks lose their positions around it, stacking in two rows.
The judge files the page all the same: the number does not see what the render lost.
