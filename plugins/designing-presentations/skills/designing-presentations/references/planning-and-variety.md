# Planning a section and its variety

## Contents
- The page plan
- The exhibit brief
- Figures: computed, never invented
- The reference's variety (guide.variety)
- plan.json
- plan.py check: what it refuses and what it warns
- What the build reports against the plan
- Where the measure is weak
- Measured tendencies across firms

## The page plan

Before any page spec, write for each page: its message (on a reference page, which states
no claim, what the reader looks it up for), the evidence that proves it,
the exhibit, the supporting text, the data it needs, the composition intent (which element
dominates, or how co-equal blocks divide the page), the layout, the split boundaries if it
will not fit, and the title, with its register and length read against the reference's
(`guide.titles`: the plan check and the build report them, and a departure is answered
in one line; with no reference there is nothing to read them against).

## The exhibit brief

Every exhibit on a planned page carries a brief, written before its spec. Design starts
from the reader and the data: what the reader must see, what is compared against what, and
the data's shape. A reference governs the look only, and the brief says how that look
applies to the form chosen (`in_reference_look`, optional; the digest's crops, the gallery
and the renders show the look). Nothing in it is chosen from a list, and nothing checks a
form by its name. It is where the visual is thought through:

```json
{"reader_must_see": "where 1.33x tangible book falls in the ranking of precedents",
 "comparison": "the offer's multiple against each precedent's multiple, ranked",
 "data": "one value for each of nine deals, one of them the subject",
 "forms_considered": [
   {"form": "sorted horizontal bars with the subject in the emphasis colour", "reason": "chosen: rank and the subject's place read at a glance"},
   {"form": "dot plot on one axis", "reason": "names would collide where multiples cluster near 1.6x"}],
 "chosen_form": "sorted horizontal bars with the subject in the emphasis colour",
 "why": "the claim is a rank; sorted bars show the rank, and one dark bar shows where the offer sits",
 "marks": "the subject bar in the dark fill with its value bold; the rest muted",
 "in_reference_look": "the reference's deep blue for the subject and light grey for the rest, values at the bar ends"}
```

`in_reference_look` is optional, a phrase, and only on a guide made from a reference (on
a guide with no reference it is refused: there is no reference look to apply). The key it
replaced, `nearest_house_exhibit`, is refused by name: a reference page is evidence of how
a look draws a form, never the source of the form. A form you cannot argue for against
another is not chosen yet; a brief whose reader cannot see `reader_must_see` on the render
is a review finding (review.md). `plan.py check` reads a brief for completeness only:
every field there; each a phrase of at least three distinct words (a form's name at least
one), where a repeated word, a lone letter and a placeholder (TBD, n/a, TODO, ...) do not
count; at least two distinct forms, telling forms apart after case, punctuation,
fullwidth letters, a leading article and a plural s, and refusing a form spelt in two
scripts; a `chosen_form` that is one of the forms considered; `in_reference_look`, when
given, a phrase; and no brief given twice in the plan
(identical after the same folding). It never reads what the brief says.

## Figures: computed, never invented

Use the user's figures byte for byte. A missing figure is a named placeholder the user must
fill. Every figure in a title, lead-in or callout is computed from the exhibit's own data
before it is written: midpoints, medians, counts above or below a line. Write a short script
that computes and asserts each stated figure; fresh agents in six scenario runs all did, and
it worked. Measured failures: "$11.40 sits above every method's midpoint" over a field where
two midpoints were above it; a re-engagement band "above every standalone midpoint" whose
floor sat below one of them. The build cannot catch a false sentence.

## The reference's variety (guide.variety)

Per content page: its composition archetype (leader clustering of content boxes at box
IoU 0.5), and its exhibit facts as the file states them (`exhibit_facts`, read by the
extractor: each native chart by the plot groups its chart XML declares, with their bar
direction, grouping and series count; tables; pictures; drawn shapes, a structure the page
builds from three or more fills, outlines or brackets where it holds no native exhibit;
the panel count, 1, 2 or 3+; and every mark drawn on content, with its geometry, what it
sits on, whether it carries text, and whether it sits on a shape-built structure). Over adjacent pairs of content pages the reader sees in a row:

- V (composition): pairs whose composition differs / pairs;
- V (structures): pairs whose exhibit structure differs / pairs (a page with no exhibit
  is "text only"; a page whose facts were not read is left out, never counted as a
  change). Nobody names a structure, so renaming an exhibit in a plan or a digest cannot
  move it;
- V (kinds): the same over exhibit kinds: the distinct kinds of exhibit with no count,
  each chart by its form (plot type, bar direction, grouping; not its series count). A
  table beside a column chart and two tables beside a column chart are one kind of page; a
  table beside a scatter and a table beside a stacked-column bridge are two. Three or more
  charts of one form drawn at one size (a column sparkline per tile) are one small multiple: one panel, one
  brief;
- distinct compositions per page; the longest run; every run of two or more.

A deck with no stretch of 3 content pages in a row is `no evidence`, and so is a raster
reference (its pages have no shapes); a guide made with no reference reads `no reference`.
The measure is the one reference deck's own: nothing pools decks (given several, the user
names the one to follow, or you ask), and anything that is not a guide is refused.

```bash
python3 scripts/plan.py reference --guide "$DECK_WORK/ref/guide.json"
```

## plan.json

Every key on every page:

```json
{"schema": "pptx-skill section plan v2", "reference_sha256": "<guide.reference.sha256, or null with no reference>",
 "pages": [{"id": "<the page's slide id in the deck JSON>", "intent": "...", "message": "...",
            "composition": "arch-4 | new:<lowercase-name>",
            "title_register": "<the title's register in words>", "deliberate_parallel": null,
            "exhibits": [<one exhibit brief per exhibit; [] on a page with none>]}]}
```

Name the composition honestly: a reference archetype when the page is built like one (look at
the archetype's anchor page), else a named new one, and the SAME name whenever two pages
share an arrangement, mirrored or re-weighted. A page that repeats the previous page's
composition carries the reason in `deliberate_parallel` (for instance a sibling page meant
to be compared: such pages share one scale and one category order; whether they share one
frame is your call, said in the reason). Worked plans: `examples/keybank-section.plan.json`,
`examples/mckinsey-pdf.plan.json`, and with no reference `examples/no-reference.plan.json`.

`title_register` is your words for the title's register. When they name a term the reference's
titles are coded in (topic, claim, question, other: `references/page_craft_vocabulary.json`,
by its slug or its label, case and plurals aside), the check sets the reference's count of that
term beside it (`title_registers.pages`); otherwise it reports "no count", with the
reference's counts beside it. A hybrid ("topic: claim", a label and a figure) is stated as it
is, never bent to a term.

## plan.py check: what it refuses and what it warns

```bash
python3 scripts/plan.py check "$DECK_WORK/plan.json" --guide "$DECK_WORK/ref/guide.json" -o "$DECK_WORK/plan.check.json"
```

It prints a short verdict (status, each refusal and warning, each measure beside the
reference's) and writes the whole report as JSON with `-o` (`--json` prints it). V is held
beside the reference deck's own V; distinct compositions per page beside the 10th
percentile of the reference's windows of the same length. A plan declares no exhibit
structure (its exhibits are briefs), so the check reports the reference's structure V for
reference and leaves the measure to the build.

Refused (exit 1), each by name: a guide made before the current readings (its pages' exhibit
facts read under another definition, or none, or a digest still in the closed lists:
`plan.old_guide_error`; the build refuses it the same way); a plan not of this shape (a
`reference_sha256` left out included: null says there is no reference); an incomplete
exhibit brief (a field missing, a phrase under three distinct words, fewer than two
distinct forms, a chosen form none of those considered, `in_reference_look` on a guide with
no reference, the removed `nearest_house_exhibit`, one brief pasted for two exhibits); a
title register that is not words (a number, an empty string, a placeholder);
an archetype the guide does not hold, or a `new:` name that is not lowercase letters,
digits, `-` and `_`; a reason on a page that repeats nothing; a plan for another
reference.

Warned, each a departure from the reference's habit to answer in one line in the report:
V below the reference's; distinct compositions per page below the reference's 10th
percentile window of the same number of pages (an A B A B A plan); a run longer than the
reference's longest, declared or not; a coded title register the reference never writes.
Also warned, with or without a reference: a repeat with no `deliberate_parallel` reason
(was it meant?). Where the reference has no run evidence (no stretch of 3 content pages, a
raster reference), no run is judged and the report says so; nothing from the corpus stands
in. With no reference every comparison reads `no reference`. These lines are choices, not
measurements: nobody has measured where V reads as samey.

## What the build reports against the plan

`build_deck.py --plan $DECK_WORK/plan.json` runs the same check first and refuses to build a plan
it refuses. The deck holds the whole plan or one run of consecutive planned pages (one page
while you work on it), each slide's id its page id. After solving it reports, under `repetition`: each page's realised composition
(the same clustering over the solved content boxes, the page frame left out), V and runs
against the reference, each page's exhibit structure read back from the file the build wrote
(the one reader that read the reference's pages, `ooxml.exhibit_facts`, the drawn chrome left
out), structure V and kinds V against the reference's, and every page where plan and build
disagree. Neither can be renamed: a section of table-beside-chart pages reads as the repeat
it is however the plan describes them (measured: the netflix section builds at structure V 1.0, since each of its charts plots something else,
and kinds V 0.25 against 0.494, the 10th percentile of the three decks it was then pooled with, warned; its
revision builds at kinds V 0.75, not warned). Decoration cannot move it
either: a fill, outline or bracket beside a native chart, table or picture (a banner over
a chart's title, a frame round a panel) is no panel and no kind, and on a page with no
native exhibit fewer than three of them are a band or a callout, not a structure
(`ooxml.DRAWN_STRUCTURE_MIN`, a definition). Each page's `drawn` entry says how many it
drew and what they were read as.

Each built page's briefs are also held to its file (`slides[].briefs`): a page whose file
holds an exhibit (a chart, a table, a picture, a structure built from shapes) while its
plan page briefs none (`exhibits: []`) is refused, `exhibit without a brief`; another
difference in count is warned with both counts, since one brief may cover a chart and the
table under it, and a logo wall is many pictures under one brief.

## Where the measure is weak

- Boxes only: a full-width table and a full-width bullet block of the same extent are one
  archetype.
- Box IoU sees arrangement, not kind: a table beside a chart, mirrored, reads as different;
  kinds V is where that sameness shows, and it changes when the chart form changes (a
  scatter, then a bridge) even beside the same tables.
- Leader clustering is order-dependent and not transitive.
- The reference's title is content to the extractor; the build leaves the frame out, so the
  reference is held to the more lenient count.
- On a PDF, text blocks stand in for shapes; a page set as many small blocks rarely matches
  another, so a consulting PDF can read every page as its own archetype.
- A picture carries no structure: a reference that pastes its charts and tables reads every
  such page as "picture", so its structure V is low and the build is held to a lenient
  line. What a picture shows is the digest's reading, never measured.
- A PDF states rectangles, paths and text, never a chart or a table: a PDF reference's
  structure reads pictures, drawn shapes and text only, coarser than a native build's.
- Decoration is read by position, not meaning: fills beside a native exhibit are never a
  structure, so a page that sets a drawn diagram beside a native chart reads as the chart
  alone (the stricter count: pages read more alike, never less); on a page without one,
  two boxes read as decoration and three as a structure.
- Structure is kind and count, not form: two column charts of three series are one
  structure whatever they compare.
- V counts adjacent pairs only: A B A C A reads 1.0; distinct compositions per page shows it.

## Measured tendencies across firms

Over the 23 of the 24 coded decks that carry a variety row, on 10 composition families: the median composition change between
consecutive pages is 0.69 (investment bank 0.645, consulting 0.765, chart book 0.55 at a
two-page stride); exhibit sets change more often (median 0.77 bank, 0.85 consulting, 0.97
chart book). Three native-pptx bank pitch books on one master change composition 83% to
90% of the time with no run longer than 2. Every longer run in the corpus (up to 7 pages)
is a deliberate sibling template: recap pages, segment tables, an appendix of row-label
pages, two matching scenario pages; no coder found an accidental run of sameness. A
designer told to vary, with a composition-history digest, still used one arrangement for 6
of 19 designs where the register allowed 1: variety has to be planned and checked, not
asked for. These are questions to put to a plan, never a line it is held to: with no
reference, the plan's runs and V are reported as they are and the reasons are yours.
