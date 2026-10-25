# Planning a section and its variety

## Contents
- The page plan
- Figures: computed, never invented
- The house's variety (guide.variety)
- plan.json
- plan.py check: what it refuses and what it warns
- What the build reports against the plan
- Where the measure is weak
- Measured tendencies across houses

## The page plan

Before any page spec, write for each page: the one message, the evidence that proves it,
the exhibit, the supporting text, the data it needs, the composition intent (which element
dominates, or how co-equal blocks divide the page), the layout, the split boundaries if it
will not fit, and the title in the HOUSE's register and length (`guide.titles`).

## Figures: computed, never invented

Use the user's figures byte for byte. A missing figure is a named placeholder the user must
fill. Every figure in a title, lead-in or callout is computed from the exhibit's own data
before it is written: midpoints, medians, counts above or below a line. Write a short script
that computes and asserts each stated figure; fresh agents in six scenario runs all did, and
it worked. Measured failures: "$11.40 sits above every method's midpoint" over a field where
two midpoints were above it; a re-engagement band "above every standalone midpoint" whose
floor sat below one of them. The build cannot catch a false sentence.

## The house's variety (guide.variety)

Per content page: its composition archetype (leader clustering of content boxes at box
IoU 0.5), and once `/exhibit_habits` is answered its exhibit-type and exhibit-class sets.
Over adjacent pairs of content pages the reader sees in a row:

- V (composition): pairs whose composition differs / pairs;
- V (exhibits), V (classes): the same over exhibit-type and exhibit-class sets (a page
  with none is {text_only}; an unread page is left out, never counted as a change);
- distinct compositions per page; the longest run; every run of two or more.

A deck with no stretch of 3 content pages in a row is `no evidence`, and so is a raster
reference (its pages have no shapes). Pool decks of one house with `--house-deck`; a deck
given twice (same sha256) is refused, and so is anything that is not a guide.

```bash
python3 scripts/plan.py house --guide "$DECK_WORK/ref/guide.json" [--house-deck other.guide.json ...]
```

## plan.json

Every key on every page:

```json
{"schema": "pptx-skill section plan v1", "reference_sha256": "<guide.reference.sha256>",
 "pages": [{"id": "<the page's slide id in the deck JSON>", "intent": "...", "message": "...",
            "composition": "arch-4 | new:<lowercase-name>",
            "exhibit_types": ["<exhibit_type>"], "data_shapes": ["<data_shape>"],
            "title_register": "topic|claim|question", "deliberate_parallel": null}]}
```

Name the composition honestly: a house archetype when the page is built like one (look at
the archetype's anchor page), else a named new one, and the SAME name whenever two pages
share an arrangement, mirrored or re-weighted. A page that repeats the previous page's
composition carries the reason in `deliberate_parallel` (a sibling template: same layout,
scale and category order, held exactly). Worked plans: `examples/keybank-section.plan.json`,
`examples/mckinsey-pdf.plan.json`.

## plan.py check: what it refuses and what it warns

```bash
python3 scripts/plan.py check "$DECK_WORK/plan.json" --guide "$DECK_WORK/ref/guide.json" [--house-deck other.guide.json ...] -o "$DECK_WORK/plan.check.json"
```

It prints a short verdict (status, each refusal and warning, each measure against the
house's 10th percentile) and writes the whole report as JSON with `-o` (`--json` prints it).
With one house deck each 10th percentile is that deck's own value, and its exhibit and class
V come from your digest reading: a different reading of the same deck moves these lines by
up to 0.3 (two readers of keybank: exhibit V 0.8 and 1.0, class V 0.6 and 0.9). The verdict
says so; pool sister decks with `--house-deck` where you have them.

Refused (exit 1), each by name: a plan not of this shape; a value outside the vocabulary
(`references/page_craft_vocabulary.json`), including a non-string register; an archetype the
guide does not hold, or a `new:` name that is not lowercase letters, digits, `-` and `_`; a
reason on a page that repeats nothing; a plan for another reference; an UNDECLARED repeat
that makes a run longer than the house's longest (with no house evidence, any undeclared
repeat).

Warned: V below the house's 10th percentile deck; distinct compositions per page below the
house's 10th percentile window of the same number of pages (an A B A B A plan); a DECLARED
run longer than the house's longest; an undeclared repeat within it; a title register the
house never writes. These thresholds are choices, not measurements: nobody has measured
where V reads as samey. Answer every warning in the plan or in your report.

## What the build reports against the plan

`build_deck.py --plan $DECK_WORK/plan.json` runs the same check first and refuses to build a plan
it refuses. The deck holds the whole plan or one run of consecutive planned pages (one page
while you work on it), each slide's id its page id. After solving it reports, under `repetition`: each page's realised composition
(the same clustering over the solved content boxes, the page frame left out), V and runs
against the house, the exhibit classes each page realises (a table is `table`, a chart
`data_chart`; a page with a component or an image is unread), class V against the house's,
and every page where plan and build disagree. Class V cannot be renamed: a section of
table-beside-chart pages reads as the repeat it is however the plan names them (measured: a
section rated samey built at composition V 1.0 and class V 0.25 against the house's 10th
percentile deck 0.643, warned; its revision built at class V 0.75, not warned).

## Where the measure is weak

- Boxes only: a full-width table and a full-width bullet block of the same extent are one
  archetype.
- Box IoU sees arrangement, not kind: a table beside a chart, mirrored, reads as different;
  class V is where that sameness shows.
- Leader clustering is order-dependent and not transitive.
- The house's title is content to the extractor; the build leaves the frame out, so the
  house is held to the more lenient count.
- On a PDF, text blocks stand in for shapes; a page set as many small blocks rarely matches
  another, so a consulting PDF can read every page as its own archetype.
- The exhibit-type vocabulary has 25 types against 10 corpus families, so exhibit V comes
  out higher than the corpus figures below.
- V counts adjacent pairs only: A B A C A reads 1.0; distinct compositions per page shows it.

## Measured tendencies across houses

Over the 23 of the 24 coded decks that carry a variety row, on 10 composition families: the median composition change between
consecutive pages is 0.69 (investment bank 0.645, consulting 0.765, chart book 0.55 at a
two-page stride); exhibit sets change more often (median 0.77 bank, 0.85 consulting, 0.97
chart book). Three native-pptx bank pitch books on one master change composition 83% to
90% of the time with no run longer than 2. Every longer run in the corpus (up to 7 pages)
is a deliberate sibling template: recap pages, segment tables, an appendix of row-label
pages, two matching scenario pages; no coder found an accidental run of sameness. A
designer told to vary, with a composition-history digest, still used one arrangement for 6
of 19 designs where the register allowed 1: variety has to be planned and checked, not
asked for.
