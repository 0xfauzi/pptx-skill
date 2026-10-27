# Designing a look with no reference

With no reference deck the look is yours. This file is not a style and not a menu: it holds
no palette, no ladder and no layout to pick. It is the reasoning to walk before you answer
the blank draft, five questions in order, each with the corpus evidence that bears on it and
what nobody has measured. Write the answers down as the look brief (`/look_brief`, last
section) before any other address; the guide is then the brief made concrete.

Counts are from 578 coded content pages of professional decks (bank 231, consulting 317,
chart book 30), one coder per page, good to about plus or minus 2 to 3, as in the other
references/ files. They say what those firms did, for those readers. They are evidence of
how a kind of deck reads, never a value to copy: a count tells you what a bank reader is
used to, not what your page should do.

## Contents
- 1. Audience and occasion
- 2. The subject's own world
- 3. The content and the data
- 4. A named brand or organisation
- 5. Restraint
- The look brief
- What is unmeasured

## 1. Audience and occasion

Who reads this, where, and for how long? The answer sets density, title register and type
size before anything else does.

- A board pack read before the meeting, on paper or a laptop, is read at the reader's pace:
  it can carry more per page than a projected deck, and its titles have to work alone.
- A projected keynote is read at a distance, in seconds, by a room. How many ideas, how
  large the type and how many marks a page can carry there is not measured here: the corpus
  holds no projected keynote, and the 7pt absolute floor was measured on screens at
  reading distance, not projected. Ask what the back row must read, and how long the page
  stays up, and say your answer in the brief.
- A banker's book is read line by line, often printed, by people who check the numbers. The
  corpus bank pages carry about 80 elements a page at the median (two decks at 145 and
  119; dense tables reach 110 to 230), title by topic on 223 of 231 pages (a claim on 2, a
  question on 6), and put a claim elsewhere when they state one (a takeaway band, a lead-in
  bullet).
- A consulting deck argues: claim titles on 197 of 317 pages (median 15 words for a claim
  title against 4 for a bank topic title), with a kicker or section tag on 265 of 317 pages
  and bold or coloured lead-ins on 179 of 317.
- A chart book is exhibits and nothing else: no body text on any of its 30 pages, light
  horizontal gridlines on 47 of 47 charts, a units line on 27 of 30 exhibit titles.
- A public report is read by people who did not commission it: plain words, a defined term
  the first time, every chart readable without the speaker.

Ask: which of these is it, or what mix? If the user did not say, ask them, or say in the
brief what you assumed and why.

## 2. The subject's own world

Every subject has materials, artefacts and conventions of its own: a ferry operator has
timetables, route maps and harbour charts; a hospital has clinical charts and wristbands; a
mining company has core logs and assay tables; a bank has the term sheet and the comps
table. A look can borrow from that world, and when it does the reader recognises the subject
before reading a word.

A development run on a bus fleet case (not kept as an example) borrowed transit signage:
a dark destination band with an amber stripe carrying a mono section code, a route line with
numbered stations for anything that ran in sequence, timetable-style tables with no header
fill and a heavy rule under the header. Each borrowing had a job: the band carried the
title, the stations carried a sequence, the timetable rule separated header from data.

When does borrowing become costume?

- When the device has no job on the page. The test is the one emphasis-and-decoration.md
  puts to every mark: can you name its job in one phrase? A wave pattern on a ferry deck's
  title band has none; a route line that orders four routes by revenue has one.
- When it competes with the data. A borrowed texture behind a chart, a themed font for
  numbers that then fits fewer digits, an illustration that takes a quarter of every page.
- When the audience would find it unserious for the occasion. A board deciding a
  restructuring reads costume as distance from the decision. Icons, the most common
  decorative borrowing, appear on 32 of 578 corpus pages: 30 consulting, 2 bank, 0 in the
  native-pptx bank decks and the chart book.
- When it would date or travel badly: a pun in the palette that only the author sees.

Borrow conventions (how the subject's own documents organise information) before
ornaments (how they look). The timetable's rule is a convention; a bus clip-art is an
ornament.

## 3. The content and the data

Read the brief and the data before choosing anything. Then ask:

- How much data is there, and what shape is it? A few headline figures, a time series, a
  matrix of entities by metrics, a bridge, a distribution? charts.md and tables.md ask the
  form questions; the corpus put lookup and reference content in a table in 71 of 71 cases.
- How many exhibits per page does the content call for? In the corpus one exhibit is the
  norm (390 of 578 pages), two on 74, three on 17, four or more on 3; bank pages carry two
  or more more often (45 of 231) than consulting pages (34 of 317). Two exhibits on a page
  should be a comparison (composition.md, co-equal blocks), not a fill.
- How dense should the pages be, for this content and this reader? Median page fill is
  0.85 in every corpus deck type, so density is not about leaving space empty: it is how
  many elements, rows and words that filled area carries. Bank about 80 elements a page,
  consulting about 30, chart book about 35. Words per page: native-pptx bank median 72
  (range 2 to 221); two consulting firms 114 to 191 on average.
- What does the density ask of the system? A dense page uses the ladder's bottom rungs
  (table cells, footnotes, source lines, axis labels) a lot, so their sizes decide whether
  it fits; that much is arithmetic, and the solver measures it. The rest are questions
  nobody here has measured, so answer them for your content and say why: how wide a
  gutter does this page need to read as two columns, and what does each gutter cost in
  columns? What separates the rows of a long table (a rule, a band of fill, white space,
  nothing), and does the separator still read at the row count you expect? How many text
  colours can the page carry before the claim is lost among its elements? What can a sparse
  page spend its space on (margins, a large title, a coloured band), and does that serve
  the reader or fill the page?

Write the density target in the brief with its reason ("a lender reads every row; tables of
15 to 25 rows per page, footnotes at the floor"), not as a word ("dense").

## 4. A named brand or organisation

If the user names a company, a client or an institution, its public identity is evidence:
its colours, its typeface if installed (preflight.py lists what is; otherwise its fc-match
stand-in, reported), its tone. With no reference deck, though, nothing here is the
organisation's template, and the deck must not pass as the organisation's own publication:
use its colours as meaning (section 5), not its logo or trade dress, unless the user
supplies them and has the right to. A fictional subject (the example's Northwind Ferries)
has no brand: say so in the brief, and let sections 1 to 3 decide.

## 5. Restraint

The look is mostly what you leave out.

- Colour as meaning. Give each colour one meaning and hold it across the whole deck: the
  subject series, the comparison, the look-here mark, a signed good and bad. Write each
  meaning in the brief's `colour_meanings`, by role. In the corpus one emphasis colour or a
  single hue was the most common chart colouring; categorical colour was kept for genuinely
  categorical series (one bank group: 24 of 72 single emphasis against 15 of 72
  categorical); semantic red and green appear on 9 pages, and elsewhere red means "look
  here". A colour that means two things on two pages is a defect the reader pays for.
- The type ladder from the densest page backwards. Find the densest page the content
  will need (the largest table, the longest footnote block, the most-labelled chart), set
  its smallest text at a size that fits and stays above the floor, and step up from there to
  body, headings and title. A ladder chosen from the cover forwards puts the dense page
  under the floor and splits it. The solver measures every run in the faces you name and
  never sets text below max(floor, 7pt); a closed set of sizes was measured to be followed
  where continuous sizes drifted (typography.md).
- Legibility at the measured floors. 7pt is the absolute floor, measured on two screen
  media by one rater for Arial and Calibri; print was not measured, nor projection, nor any
  other face. A face with a small x-height at 7pt is not proven legible by that measurement.
- What to leave plain: gridlines are absent on 58 of 80 recorded bank charts and
  78 of 89 consulting ones; labels on the marks replace a legend most often where series run
  side by side over time (34 of 85). The corpus counts say nothing about gradients and
  shadows (unmeasured); the job test of section 2 applies to them. Each plain choice is a choice: say it in `rejected` or
  in the description's `not_seen`.

## The look brief

Write it as `/look_brief` in the completion, before the other answers, and paste it into
your response. The blank-guide completion refuses a brief that is missing, has a part
missing, or answers a part with a placeholder (TBD, n/a, "to be determined", "see above",
lorem ipsum, the shape's own `<...>` text); it never weighs what the brief says, and the
build refuses a guide written with `--allow-partial` while the brief is open. `complete_guide.py --shapes` gives the keys:

- `audience`, `occasion`: section 1.
- `subject_world`: section 2, including what you chose not to borrow.
- `data_character`: section 3, how much data and its shape, exhibits per page.
- `density`: `{"target", "why"}`, the target in rows, words or exhibits, and why this
  content and reader call for it.
- `look`: the look in words, one or two sentences.
- `colour_meanings`: `{"color.<role>": "<its one meaning>"}`, every colour that carries one.
- `type_ladder`: why the ladder is what it is, from the densest page.
- `rejected`: `[{"what", "why"}]`, the looks and devices you considered and turned down.

Two worked briefs: `examples/no-reference.completion.json` (a three-page board review read
on screens and projected, moderate density) and `examples/no-reference-credit.completion.json`
(a two-page credit committee book printed on letter paper, a 27-row table at 8pt, five
exhibits on one page). Each is one model's reasoning for one brief, not a look to reuse.

The brief is the argument; the guide is the decision. Where the guide departs from the
brief (a colour with no meaning in it, a ladder the densest page does not need), the brief
or the guide is wrong: fix one, so the two agree.

## What is unmeasured

- Whether a look derived this way reads better to its audience than a stock one: no rater
  has rated no-reference decks against each other.
- Legibility below 9pt on print and on projection; any face other than Arial and Calibri at
  the floor.
- Where borrowing turns into costume: section 2 gives tests, not a measurement.
- Density a reader accepts by audience: the corpus says what firms did, not what readers
  preferred.
- What a projected page can carry (ideas, type size, marks): the corpus holds no projected
  keynote.
- On a dense page: gutter width, what separates a long table's rows (rule, fill band, white
  space) and how many text colours a page carries before the claim is lost. No corpus count
  here or in tables.md or composition.md measures any of them; section 3 asks them as
  questions.
