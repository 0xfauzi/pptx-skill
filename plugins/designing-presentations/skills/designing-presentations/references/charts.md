# Charts and other visuals: questions, and the evidence that changes the answer

There is no menu of chart types here, and nothing in this skill asks you to choose from
one: the counts below and in the other references are coders' labels for what firms did,
evidence beside your choice, and the chart kinds the spec names are what the emitter can
write, not what to show. Every exhibit is
reasoned out from three things: what the reader must see, the data, and how this reference
draws its own exhibits. Write that reasoning down before the spec, as the plan's exhibit
brief (planning-and-variety.md): what the reader must see, what is compared against what,
the data's shape in your words, at least two forms weighed with why not or why, the form
chosen and why, the reference's nearest exhibit, and what will be marked.

The reference's measured habits are the strongest evidence you have: start there, and where
this exhibit departs, say why in the report. Only measurable defects refuse. The evidence is
its digest records (`exhibit_habits`: what each
exhibit is, how it is drawn, what it marks, in words), what its files state
(`variety.pages[].exhibit_facts`: native charts and their plot groups, tables, pictures,
marks), and its `charts` section. The counts below are per exhibit over 601 coded exhibits
(291 charts) in 24 professional decks, one coder per page, good to about plus or minus 2 to
3. They are evidence for thinking, not a ranking to pick from. How to write a chart and its
marks in the spec: chart-recipes.md.

## Contents
- Questions for every exhibit
- Table or chart: what the corpus did
- How often exhibits are annotated
- Marks sit where the claim lives
- Text adds what the exhibit cannot
- Labels, legends, gridlines, colour
- Lapses humans made

## Questions for every exhibit

- What must the reader see when they look at it for three seconds? Say it in one sentence.
  If you cannot, the exhibit has no job yet.
- What is compared against what? A value against a benchmark, a subject against peers, a
  period against the last, parts against a whole, a range against a decision value? Is the
  thing compared against drawn, or does the reader have to hold it in their head?
- What is the data, in its own terms: how many things, measured how many ways, over what?
  Which of those does the claim need, and which only support it?
- Which forms could show that comparison? Weigh at least two. For each: what does the
  reader do with their eyes to get the claim (read a length, find a position against a
  line, follow a slope, look a value up, subtract two numbers)? Which form makes that act
  shortest and surest, and why do the others lose?
- What will the reader do with this content, and what does that ask of the form? (In the
  corpus, lookup and reference content was a table in 71 of 71 cases.)
- Which of the reference's own exhibits is nearest? Open it (the digest crop, the gallery, the
  render). What does the reference do there that this exhibit should take: its order, its
  emphasis, its labelling, its density? Where must this one depart, and why?
- If the reference never drew anything like this, how would its designers draw it with the
  roles, inks and devices they do use?
- Where on the exhibit does the claim live: a point, a gap, a region, a subset, a trend, an
  absence? That is where the mark goes (below).
- What is estimate and what is fact? What explains the shape, and should the exhibit say so?
- Do sibling exhibits share one scale and one order? Does a bar start at zero?
- Is the form unfamiliar enough to need a reading key?

## Table or chart: what the corpus did

Lookup and reference content was a table in 71 of 71 cases. Change over time was a chart 93
times and a table 24 times; the 24 tables were projections where every number is read. In
three native-pptx bank pitch books, 27 of 33 data exhibits were pasted pictures, with marks
laid over them as separate shapes. The question is not which form is allowed; it is
whether the reader reads numbers or reads shape.

## How often exhibits are annotated

7 of 291 charts carry no annotation (bank 0 of 109, consulting 4 of 135, chart book 3 of
47); a chart averages about two marks (bank 2.25, consulting 2.09, chart book 2.02). About
one chart in four marks nothing that points at the message (only labels, sorting,
footnotes, totals or spanners): the reader is left to find the claim. If this exhibit is
to be bare, where does this reference leave such an exhibit bare, and can the reader still find
the claim?

## Marks sit where the claim lives

The coders found the mark where the claim was: a line at the decision value on every
valuation range in one group (4 of 4), the subject highlighted and the rest muted on peer
rankings, a divider at the forecast boundary on projections, an event marker where a shape
changes because of something that happened, a total over a stack when the claim is the
total, a box round the one answer on a recommendation. Ask where your claim lives, then
ask how this reference marks such a place (its digest says, in its own words, what it marks and
how). A mark elsewhere is decoration; a mark that says nothing about what it marks reads
as a model's attempt to annotate (a rater, on an unlabelled red circle). The build
draws a mark with no label and no `explained_by` and warns, with the reference's own count of
such marks beside it; the report answers the warning. An `explained_by` that names something
not on the page is refused (`annotation explanation not found`, annotate.py).

## Text adds what the exhibit cannot

The lead-in, sidebar or takeaway states the claim and what the exhibit cannot show: the
cause, the consequence, the caveat, the number that is not on it. A sentence that restates
what the bars already say is spent twice. Read the exhibit and its text together: is
anything said twice, and is anything the reader needs said nowhere?

## Labels, legends, gridlines, colour

- Labelling every mark was the most frequent chart move in every deck type: 120 of 291
  charts (bank 65 of 109, consulting 43 of 135, chart book 12 of 47), usually beside one
  highlighted item; selective labels 22.
- Legend absent where recorded: bank 32 of 81, consulting 30 of 85, chart book 18 of 47.
  Labels on the marks themselves replace the legend most often where series run side by
  side over time (34 of 85).
- Gridlines absent where recorded: bank 58 of 80, consulting 78 of 89; the chart book draws
  light horizontal gridlines on 47 of 47. Gridlines are a reference habit.
- Colour: one emphasis colour or a single hue was the most common; categorical colour was
  kept for genuinely categorical series (one bank group: 24 of 72 single emphasis against 15 of 72
  categorical). Semantic red and green appear on 9 pages; elsewhere red means "look here".
  Heat and status colour were defined against a named benchmark or decision.

## Lapses humans made

Measurable defects the coders recorded: mismatched y-scales on sibling charts, truncated
axes, colliding labels, comma decimals in a borrowed chart. These are what a generator
should be better than, not what it should copy. One coder's judgement, recorded beside
them: a missed subject highlight, a claim with no bracket summing it; weigh these as
opinion against the reference's own pages.
