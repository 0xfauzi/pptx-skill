# Titles and text: questions, and what decks measurably do

Questions to ask, with what professional decks measurably do. None of it is a rule. The
house's measured `guide.titles` (register counts, lengths, companions, where its claims
sit) is the strongest evidence you have: start there, and where this page departs, say why
in the report. Only measurable defects refuse. Counts are from 578 coded content pages (bank 231,
consulting 317, chart book 30), one coder per page, good to about plus or minus 2 to 3.

## Contents
- Questions per page
- Title register: what houses did
- Where the claim lives when the title is a topic
- Length
- Kickers, units lines, continuations
- Text beside an exhibit
- Words on the page

## Questions per page

- What should the reader leave with: the page's message, or, on a reference page, what
  they look up? Which slot of THIS house carries it (`guide.titles.claims_elsewhere` names
  where it states claims; the corpus found titles, lead-ins, sidebars, takeaway bands,
  kickers, units lines and row labels), or does this page need somewhere else?
- Does this house argue in titles, or name the topic and argue elsewhere? How long are its
  titles, and does any run to two lines?
- Is this a page of argument or a page of reference (263 of 372 topic-title pages state
  no claim)? What do this house's own reference pages carry: complete tables, spanners,
  totals, footnotes, how much emphasis?
- What does the text add that the exhibit cannot: assumptions, caveats, causes, history,
  the implication, the derived number? Is anything said twice?
- Can the reader check the claim on the page? Is every figure in the claim computed from
  what is printed?
- Is there a measured figure behind each adjective: what is the number behind "strong"?

## Title register: what houses did

| Register | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Topic phrase | 372 | 223 | 119 | 30 |
| Claim sentence | 199 | 2 | 197 | 0 |
| Question | 7 | 6 | 1 | 0 |

- Bank decks title with a claim on 2 of 231 pages; the chart book on 0 of 30; consulting
  on 197 of 317.
- Register varies by deck within one house (one consulting deck 23 of 30 claim titles; a
  memo 0 of 12), and the same exhibit can take both registers in one deck.
- Measured on generated sections: a planner told to write claim titles wrote 19 with a
  median of 80 characters against a reference median of 35; only 4 fit within the
  reference's longest, and 17 of 22 held pages were held because the title overran its
  band. In a blind round the rater caught every generated page in exactly the two houses
  where claim titles met a topic-title reference.

## Where the claim lives when the title is a topic

On 109 of 372 topic-title pages a claim sentence sits elsewhere (bank 71 of 223,
consulting 36 of 119, chart book 2 of 30):
- bank: a takeaway band (one deck, 21 of 30 pages); a lead-in bullet ending in a colon
  before its exhibit; the labels of numbered rows; kickers and sidebars;
- chart book: a full claim sentence in the exhibit's units line;
- consulting: a sidebar or subtitle, or memo prose.
On the remaining topic-title pages no claim is stated: the page is reference material.

## Length

Median title length in words: bank topic titles 4; chart book 4; consulting topic titles
7; consulting claim titles 15 (8 to 22 words, usually two lines). The build reports each
title against the house's own median, p90 and max from `guide.titles` and warns above the
max; the report answers the warning. What it refuses is fit: a title that needs more lines
than the band above the reference's top rule holds does not fit (build_deck.py, the title
band check), and the message names both fixes: shorten it, or move a clause to where the
house states claims.

## Kickers, units lines, continuations

- Kicker, subtitle or section tag: consulting 265 of 317 pages; bank 64 of 231. The bank
  anatomy is usually title, exhibit, footnotes, source and furniture.
- Units line on exhibit titles: bank 64 pages; chart book 27 of 30. In the native-pptx bank
  decks, 18 of 24 numeric pages and every page that shows currency.
- Continuations appear in four consulting decks.

## Text beside an exhibit

When text and exhibit share a page, the text usually adds what the exhibit cannot show:
assumptions and caveats, causes and history, the so-what, the derived number (all six coder
groups). Text restating the title: bank 40 of 264 exhibits, consulting 61 of 180 recorded,
chart book 8 of 52; in consulting, restating usually means one panel proves one clause of a
two-part title.

## Words on the page

- Body hierarchy levels: bank pages mostly 0 or 1 level (118 and 75 of 231); consulting
  mostly 1 or 2 (108 and 171 of 317); the chart book has no body text.
- Bold or coloured lead-ins: bank 26 of 231, consulting 179 of 317, chart book 0 of 30.
- Words per page: native-pptx bank decks median 72 (range 2 to 221); two consulting houses
  114 to 191 per page on average; the guide's density band is this house's own range.
- Coders recorded parallel findings set as numbered or label rows rather than bullets,
  ordered options as a spectrum, and qualitative text ranked on an axis (not counted). What
  form would carry this text best for this reader?
