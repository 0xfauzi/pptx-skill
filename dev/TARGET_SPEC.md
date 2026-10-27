# Company-Style Deck Skill: Target Specification

Written for an agent that will build, from scratch, an agent skill that generates
PowerPoint decks for a company that already has its own templates (masters, layouts,
themes), usually a body of its own past decks, and possibly brand guideline documents.
Everything you need is in this document: the ambition, the goal, the architecture, the
contracts between parts, and every fact that has been measured about the problem, with the
measurement behind it. Where a claim has not been measured, it is marked as such.

Read section 0 first. Then section 1 (ambition), section 2 (goal and how it is judged) and
section 3 (design principles); they decide every trade-off below.

## Contents

0. How to read this document; vocabulary
1. Ambition
2. Goal, scope and success criteria
3. Design principles
4. Packaging the skill (Anthropic skill-authoring practice)
5. System overview: the pipeline in one page
6. Reference material: templates, past decks, brand guidelines, or none
7. Confidentiality and data handling
8. Intake: reading any file
9. The style guide: schema, provenance, extraction, completion
10. Visual context: renders, gallery, exhibit digest, the page library
11. Templates, layouts and chrome
12. Planning a section: storyline, page plan, variety plan
13. The page specification language
14. Text measurement and the layout solver
15. Exhibits: charts, tables, annotation, diagrams, components
16. Emitting the PowerPoint file
17. Gates: validation, contrast, fit read-back, tie-outs, register, repetition, leakage
18. Rendering and the self-critique loop
19. The style judge, and its limits
20. Editing an existing deck
21. Evaluation program
22. Evidence: what has been measured
23. Known failure modes to design against
24. Hard rules
25. Build order with exit criteria
Appendix A. Measured page-craft evidence
Appendix B. Reasoning questions for the designer
Appendix C. OOXML and renderer facts (each measured)
Appendix D. The development corpus

---

## 0. How to read this document

### 0.1 Vocabulary

- **Company**: the bank, consultancy or other firm the skill serves. It owns the
  templates, the past decks and the brand guidelines.
- **Template library**: the company's template files (.potx, or .pptx files kept as
  templates), each with one or more masters, their layouts and a theme.
- **Past decks**: the company's own finished decks (pptx, sometimes only PDF). They show the
  habits a template cannot show.
- **Brand guidelines**: documents in which the company states its identity rules (colours,
  type, logo use, tone). Evidence with provenance, not code.
- **Reference**: any file whose style the output must match: a template, a past deck, a
  brand guideline, or any other pptx or PDF the user supplies. Untrusted input.
- **Look**: one visual identity: what one reference deck shows (faces, colours, spacing,
  chrome, how marks are drawn, title and text habits), or, with no reference, what the
  model chose. The skill follows one reference deck at a time; given several, the user
  names the one to follow, or is asked. Nothing pools decks.
- **Style guide** (or **guide**): a JSON document describing one reference's style as named
  roles with values and provenance (section 9).
- **Role**: a named slot in the guide, such as `type.title`, `color.accent1`, `space.md`.
  Page specs refer only to roles, never to literal values.
- **Habit**: a measured tendency of the reference's pages that is not a value: title register
  and length, exhibit types and annotation moves, composition variety, density, number
  craft.
- **Provenance**: for every guide value, where it came from: observed in a file, stated in
  a guideline, deterministically inferred, completed by the model, or raster-measured; plus
  evidence and confidence.
- **Open address**: a guide path extraction could not settle from evidence. The model must
  answer exactly these and no others.
- **Page spec**: the model's description of one page as a tree of regions and elements
  using roles and weights (section 13).
- **Solver**: deterministic code that turns a page spec plus guide into exact geometry in
  EMU, using measured text widths (section 14).
- **EMU**: English Metric Unit, PowerPoint's coordinate unit. 914400 EMU = 1 inch;
  12700 EMU = 1 point.
- **Layout**: a slide layout in a master: named, with placeholders of given types and
  geometry. Each generated page is built on exactly one layout.
- **Chrome**: furniture repeated on every page (rules, bands, logos, footer labels, page
  numbers), usually on the master or layout.
- **Motif**: a recurring decorative device that is not chrome (a coloured block beside a
  heading, a rule under a section label).
- **Exhibit**: the chart, table or diagram that carries a page's evidence.
- **Annotation**: marks added to an exhibit or page that direct the eye to the message (an
  outline box around a region, a reference line, a highlighted bar, a callout).
- **Composition** (or **archetype**): the arrangement of regions on a page (full-width
  table; chart left with takeaway column; 2x2 small multiples; and so on).
- **Component**: a reusable expander that turns data into a subtree of the page spec
  (a football field, a KPI row), checked against held-out cases before use (section 15.5).
- **Page library**: a curated, tagged set of excellent real pages, drawn first from the
  company's own best pages and optionally from external public decks (section 10.4).
- **Judge**: a style fingerprint distance that says which deck of a panel a new deck most resembles
  (section 19). It is an instrument, not the definition of quality.
- **Blind round**: the human evaluation in which a rater sees real and generated pages
  mixed, guesses which is which, and rates quality (section 21.2). This is the primary
  measure of success.
- **Fresh-agent run**: an evaluation in which an agent with only the skill, and no other
  context, performs a scenario and reports friction (section 21.3).

### 0.2 Status labels

Facts are labelled:
- **Measured**: produced by a run on real files, with the numbers given.
- **Measured once**: a single observation, real but not repeated.
- **Unmeasured**: a claim or design intent with no measurement behind it yet.
- **External**: from published sources, not measured on this system.

"Known failure mode" marks a defect that has been observed in a working system of this
kind; each is followed by the requirement it implies.

---

## 1. Ambition

State this to yourself before every design decision; the rest of the document serves it.

1. **Indistinguishable, and at least as good.** A page the skill generates should be
   indistinguishable from the company's best human-made pages to the company's own senior
   bankers or consultants, and should be at least as good as those pages. The bar is the
   blind real-versus-generated test (section 21.2): raters from the company cannot pick the
   generated page better than chance and rate it at least as high.
2. **Dense, expert, analytically sharp.** Pages carry the density and judgement of a
   senior associate's work reviewed by a managing director: an exhibit reasoned out from
   what the reader must see, the data and the reference's own exhibits; figures that are
   correct and computed; text that adds what the exhibit cannot; marks where the claim
   lives.
3. **Beyond the template, still in the reference's look.** The skill produces exhibits and
   components the template never contained (a football field, a maturity profile, a
   sensitivity grid with the answer boxed) that are still unmistakably the company's.
4. **The model reasons like a senior designer and analyst.** The skill gives the model
   context (the company's style as data, its own best pages as images, measured habits)
   and reasoning prompts (Appendix B), not rules that fix a design.
5. **Every value measured, nothing estimated.** Text fit, geometry, contrast and tie-outs
   are computed from real fonts and real data. A threshold without a measurement is
   labelled unmeasured until it has one.
6. **Correct figures, intelligent annotation, deliberate variety.** Every stated figure is
   computed from the data. The claim can be found on every exhibit; how the reference treats
   such places is the evidence beside each mark (7 of 291 corpus charts are bare). Every
   repeated composition is a deliberate parallel.
7. **Native, editable output.** Real text in real placeholders, real tables, real charts,
   on the company's own masters and layouts, opening without repair.
8. **Any reference.** The company's templates and decks first, but any pptx or PDF works,
   including scanned PDFs.
9. **Continuous improvement.** Every release is measured by scenario evaluations,
   fresh-agent friction and blind rounds; friction reported by agents using the skill is
   the primary input to the next revision.

---

## 2. Goal, scope and success criteria

### 2.1 The goal

Given a company's template library, and where available its past decks and brand
guidelines (or ANY other reference presentation, native .pptx or PDF, vector or scanned),
an agent using this skill produces new presentation pages that:

1. Are indistinguishable from the company's own best pages to an informed reader from the
   company, including pages built from exhibits its templates and past decks never showed.
2. Are dense, expert, pitch-book quality: the content a managing director would send,
   with the analytical craft of a senior associate (correct figures, sensible exhibit
   choice, intelligent annotation, consistent furniture, source lines).
3. Are native, editable PowerPoint: real text, real tables, real charts or drawn shapes,
   on the right master and layout of the right company template.
4. Are valid files that open without repair in PowerPoint and render the same in
   LibreOffice to within the measured renderer differences.
5. Leak nothing: no confidential content leaves the machine through the skill, and no
   client content from a past deck appears in a new deck unless the user supplied it for
   that deck (section 7).

### 2.2 The division of labour

The model (the agent using the skill) decides everything that is a design or content
judgement: which template and layouts, storyline, what each page says, composition,
exhibit type, what to annotate and how, emphasis, what to complete where the evidence is
silent, how a new component looks.

Scripts decide nothing about design. They read files, measure text, solve geometry, write
valid packages, render, and refuse what is measurably wrong (overflow, overlap, contrast
below threshold, totals that do not tie, values outside the guide, content leaked from a
past deck). They never pick a colour, never choose a chart or a layout, never swap an ink
to fix contrast, never default a design choice silently.

The skill's job is therefore to give the model three things:
- **Context**: the reference's style as data (from the template, the past decks and the
  guidelines), the company's own pages and exhibits as images, a library of excellent
  pages (the company's best, optionally plus external ones), and measured statistics about
  how human decks are designed.
- **Reasoning instructions**: questions and procedures that make the model think about a
  page the way a senior designer does (Appendix B), not rules that fix a design.
- **Instruments**: scripts that make the model's decisions executable and checkable.

### 2.3 Scope

In scope: inventory and selection of templates and layouts; style extraction from
templates, past decks (pptx and PDF), brand guidelines and any other reference; habit
mining from past decks; completion of what the evidence never showed; section and deck
planning; page design; charts, tables, diagrams, annotation; novel components; measured
fit; valid emission; rendering; gates; style judging; editing and extending existing decks;
confidential local processing; evaluation.

Out of scope: sourcing financial data (figures come from the user; never invented),
animation, speaker scripts beyond notes, non-PowerPoint output formats, editing the
company's templates themselves.

### 2.4 Success criteria (in priority order)

1. **Blind round** (section 21.2): over the company's firms, raters from the company (or
   informed outsiders when none are available) cannot tell generated pages from the
   company's real ones better than chance, and rate generated pages at least as high as
   real ones. Target: accuracy within the binomial chance band at p = 0.05 per reference, and
   generated quality mean at or above real. A baseline measured on an earlier build over
   six public firms: rater accuracy 45 of 60 (chance 30; probability of 45 or more by luck
   0.00007); mean quality 2.93 generated vs 3.53 real (table in section 21.2).
2. **Expert review**: located findings from a reviewer (human, or a model acting as an MD)
   on figures, exhibit choice, annotation, wording; zero factual errors in titles and
   takeaways (every figure computed from the data).
3. **Mechanical correctness**: every page fits at measured scale; zero overflow, overlap,
   clipped labels, contrast violations, unresolved roles; package validates; renders in
   PowerPoint and LibreOffice.
4. **Confidentiality**: zero network calls by the skill's scripts; zero leakage findings
   (section 17.10).
5. **Style judge** (section 19): the deck is filed under its reference. Necessary, not
   sufficient. Measured: a judge filed decks a human caught every time, and failed to file
   a deck that fooled the human 4 of 5 times (section 19.4).

---

## 3. Design principles

Each principle is followed by the evidence for it.

### 3.1 The model designs; code measures and refuses

Any design choice made in code is a choice the model cannot see or override, and it
produces the same page for every reference. Known failure mode: chart code that picks series
colours by cycling a palette, hides value axes when labels show, swaps label inks below
3:1 contrast, and draws waterfalls through a dedicated path. Measured: removing 21 such
decisions from code and handing them to the model (with every choice written in the spec
and every omitted choice reported by name) left reference-adherence scores unchanged (judge
0.086 before and after on a native-pptx bank section) while letting the model compose
exhibits the code had never anticipated (a horizontal cost bridge, a Gantt from a stacked
bar, a scatter with a regression line).

Corollary: when the model leaves a choice out, the system writes a named neutral value and
reports it (`chart_defaults_taken` and the other `*_defaults_taken` lists), so the model
sees every choice it did not make. A neutral value is nothing written (the renderer's own
value), reported; or the reference's observed value, with its provenance; never a styled
constant. Where no value is neutral (a mark's shape, a label's placement), the choice is
required and refused by name when missing.

### 3.2 Context plus reasoning, not rules

Rules that fix a design override the reference. Known failure mode: telling the model to write
assertion (claim) titles with computed figures. In 51 sampled content pages of three
native-pptx bank pitch books, 48 titles are topic phrases (median 4 to 5 words), 3 are
questions, 0 are claim sentences; the claim lives in a lead-in bullet ending in a colon
above the exhibit (measured; Appendix A.3). Over the whole coded corpus (578 pages), titles
are topic phrases on 223 of 231 investment-bank pages and 30 of 30 chart-book pages, and
claim sentences on 197 of 317 strategy-consulting pages. Measured on another pair of decks:
a reference's 11 titles had a median of 35 characters (longest 57); a planner told to write
claim titles wrote 19 with a median of 80 (longest 103); only 4 of 19 fit within the
reference's longest; told a 56-character budget, the designer shortened only 5 of 19, and
17 of 22 held pages were held because the title overran its one-line band. In a blind round on an earlier
build, the rater caught every generated page in exactly the two firms where claim titles
met a topic-title reference.

So: a reference governs the LOOK only (faces, colours, spacing, chrome, how marks are
drawn, title and text habits). Design comes from the data and the reader: each exhibit's
brief starts from what the reader must see, the comparison and the data. The reference's
habits (title register and length, annotation moves, emphasis devices, composition
variety, source lines, unlabelled marks) are measured from the one reference deck and
shown beside each choice as evidence; where a page departs, the report answers it in one
line. Generic doctrine is offered as questions the model asks itself. With no reference
the model chooses the whole look (section 6.10), and corpus evidence stays questions,
never a default style or a fallback value. Only measurable defects refuse (section 24): fit,
overlap, contrast, tie-outs, roles not literals, a valid package, renderer divergence,
confidentiality, no invented numbers, measured floors with the 7pt absolute floor.

### 3.3 A prompt sentence does not fix a visual defect

Measured once: an axis rule stated in the prompt did not stop the model drawing a diagonal;
that class of defect needs the render loop, not another sentence. Visual defects are caught
by looking at renders (the model's own critique pass) or by a validator, never by adding
instructions.

### 3.4 Never offer the model a field the pipeline cannot honour

Measured: annotation anchors offered in a page spec before any placement pass existed were
refused when used; the model then attached callouts to tables and side rails (7 refusals),
and the whole annotation field had to be removed. Every field in the page spec must be fully
implemented, validated and rendered, or absent.

### 3.5 Closed sets are followed; continuous values drift

On the same briefs, a strong model used exactly the guide's type scale (8/9/10/11/14/24pt)
while a weaker model invented 8.5, 9.5, 20 and 22pt; both were exact on a palette of named
roles (measured once, two models). Expose style as closed sets of named roles; refuse any
literal value. The same holds for layouts: offer the template's named layouts as a closed
set (unmeasured for layouts).

### 3.6 More instructions help strong models and can hurt weak ones

A longer rule set (fill the whole canvas, anchor callouts) improved a strong model's
self-graded pages and caused the first collisions and larger dead margins on a weaker
model (measured once; self-graded, not independent). Test every instruction change on
every model tier the skill supports (section 21.4).

### 3.7 Measure, never estimate

Text fit is measured with the real font's shaping (section 14), never estimated from
character counts (measured once: "0.6 em per character" wrapped "$8.2 to $12.4" onto two
lines in a component). Pixels never decide fit. Whole runs are measured, never the sum of
fragments (kerning). All thresholds come from measurement on this system and carry the
measurement; an unmeasured threshold is labelled as such.

### 3.8 Absence is not zero

`set`, `dict`, `.get()` with a default, `continue` and `return {}` over untrusted
structure turn "I cannot tell" into a confident answer. Known failure modes: a judge that
fingerprinted a scanned reference from its OCR layer and confidently called the reference "88%
Times New Roman at 1pt" (so nothing could ever be filed under it); density bands of [0, 0]
words for PDF references, so every page read "above"; register bands of 0 tables and 0
charts for firms that paste exhibits as pictures, so every native table read "above".
Each such instrument must report "no evidence" distinctly from "zero". Likewise duplicate
is not one: several versions of the same past deck must not count as several decks
(section 6.6).

### 3.9 A test that passes against unfixed code is not a test

Break the fix, watch the check fail, restore. When the producer and the consumer of a
value are both yours, drive the real producer rather than spelling the expected value.
Proofs are end-to-end runs whose output is recorded beside the claim (section 21).

### 3.10 One definition per concept

A second definition of an existing concept is a bug in waiting. Known failure modes: an
emitter and a solver that read different type roles for table cells (the solver measured
the spec's `cell_role`, the emitter wrote `type.table_cell`), so a table measured at 8pt
was written at 12pt; and a ruler that measured text in DejaVu Sans while LibreOffice drew
Inter for the same font name. Both are the same bug: two sources of one truth.

### 3.11 Degrees of freedom match fragility

Anthropic's skill guidance (section 4): low freedom (exact scripts) where operations are
fragile (OOXML, fit, validation, confidentiality); high freedom (context and heuristics)
where many designs are valid (template and layout choice, composition, exhibits,
annotation, wording).

---

## 4. Packaging the skill (Anthropic skill-authoring practice)

Source: Anthropic, "Skill authoring best practices"
(platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) and
"Equipping agents for the real world with Agent Skills" (anthropic.com/engineering).
Apply all of the following.

### 4.1 Structure and progressive disclosure

- A skill is a directory with `SKILL.md` (YAML frontmatter `name`, `description`, then
  the body), plus bundled reference files and scripts.
- Level 1 (always loaded): name and description. Level 2 (loaded when relevant): the
  SKILL.md body. Level 3+: bundled files, read only when needed. Scripts are executed,
  not loaded; only their output costs context.
- Keep the SKILL.md body under 500 lines. Known failure mode: a body that grows past the
  limit (592 lines measured once) as each fix adds a paragraph.
- References one level deep from SKILL.md (no file that sends the model to a third file).
- Any reference file over 100 lines starts with a table of contents.
- Organise reference files by domain so the model reads only what the task needs
  (for example `reference/templates.md`, `reference/charts.md`, `reference/tables.md`,
  `reference/pdf-intake.md`).
- Say explicitly whether a script is to be executed or read.
- The company's own material (guides, page library, digests) lives outside the skill
  directory, in the company's working area (section 7); the skill ships no company data.

### 4.2 Metadata

- `name`: at most 64 characters, lowercase letters, digits, hyphens; no reserved words
  ("anthropic", "claude"). Prefer gerund form. Do not reuse the name of another skill the
  agent may have; a generic name such as `pptx` is likely to collide. A suitable name:
  `building-company-style-decks`.
- `description`: at most 200 characters (claude.ai's limit, the strictest; the API and the specification allow 1,024), third person, says what the skill does and when
  to use it, with the key terms a user would say (pitch book, board deck, CIM, consulting
  deck, company template, reference style, no reference, brand guidelines, past decks, reference deck,
  .pptx, PDF reference).

### 4.3 Content

- Assume the model is capable; add only what it does not already know. Every paragraph
  must justify its tokens.
- Match degrees of freedom to fragility (section 3.11).
- Provide a workflow checklist the model copies into its response and ticks off.
- Provide feedback loops: run validator, fix, repeat; build, look at the render, critique,
  fix, rebuild.
- Use examples to teach style (here: real pages from the company's decks and from the page
  library), not long descriptions.
- Consistent terminology throughout (one word per concept).
- No time-sensitive statements.
- Scripts solve problems instead of deferring them to the model; error messages name the
  element, the measured value, the limit, and the available alternatives.
- No unexplained constants; every threshold names the measurement behind it.

### 4.4 Evaluation-driven development

- Build evaluations before writing documentation: at least three scenarios that exercise
  real gaps; baseline without the skill; minimal instructions to close the gaps; iterate.
- Develop with two instances: one that writes the skill (A) and fresh instances that use
  it on real tasks with no other context (B). Observe B's behaviour (files read, order,
  what it ignored, where it struggled) and bring that back to A. Measured on an earlier
  build: fresh agents over six firms reported 71 friction items, most of them real
  (section 21.3).
- Test with every model tier the skill will run on (the guidance names a fast, a
  balanced and a strongest model). Known failure mode: testing on one tier only.

---

## 5. System overview

```
company template library   past decks   brand guidelines   (any other reference)   user brief + data
        |                      |               |                    |                     |
   [6] inventory: templates, masters, layouts; past decks matched to templates; guidelines read
        |                                                                                 |
   [8] intake: triage, render (local only, section 7)                                     |
        |                                                                                 |
   [9] extract -> guide draft per reference (template values + past-deck habits + stated values,
        |          provenance, open addresses)                                            |
   [10] visual context: renders, gallery crops, exemplars, exhibit digest, page library   |
        |                                                                                 |
   [9.6] model completes open addresses -> guide (validated)                              |
        |                                                                                 |
   [11] model picks template; template or constructed blank + chrome                      |
        |                                                                                 |
   [11.7] round trip: re-build one past-deck page, judge + look                           |
        |                                                                                 |
   [12] model plans the section: storyline, page plan, layout per page, variety plan  <---+
        |                                                                    |
   [13] model writes page specs (layout, roles, weights, exhibits, annotations)
        |                                                                    |
   [14] solver: measured fit, geometry, refusals with located reasons -------+
        |
   [16] emit pptx -> [17] gates (read-back, contrast, tie-outs, register, repetition,
        |                       leakage, validation)
   [18] render -> model critique on images (located findings) -> fix -> rebuild (capped)
        |
   [19] judge (style distance) -> report to user
```

Every arrow that returns to the model carries located information (element id, measured
value, limit), never a bare score.

---

## 6. Reference material: templates, past decks, brand guidelines, or none

The primary reference is the company's own template library and past decks, not a single
deck. A template shows values; past decks show habits; brand guidelines state intent. All
three are needed, and each is evidence with provenance.

### 6.1 What the company provides

- **Template library**: one or more template files. Each contains one or more masters,
  each master its layouts, and a theme (colour scheme, font scheme, effect scheme).
- **Past decks**: finished decks built on those templates, in pptx and sometimes only as
  PDF exports or scans. Usually many, of mixed quality and age.
- **Brand guidelines** (often): PDF or document files stating colours, type, logo rules,
  minimum sizes, tone.
- **Exemplars** (optional): decks or pages the company marks as its best work.
- **Any other reference**: a client's deck, a public deck, a competitor's public deck the
  user wants matched. The skill supports any pptx or PDF as a general capability; such a
  reference is treated as a reference of its own.

### 6.2 What each source can and cannot show

| Source | Shows | Cannot show |
|---|---|---|
| Template | Masters, layouts, placeholder geometry and text styles, theme colours and fonts, chrome on master and layouts | Title register and length, exhibit types, annotation moves, emphasis devices, composition variety, density, number craft, which layouts are actually used |
| Past decks | All habits above; layout usage; slide-layer chrome; real exhibits; real density | Values the decks never exercised; rules nobody followed |
| Brand guidelines | Stated colours, fonts, logo clear space and minimum sizes, tone | How pages are actually built; anything not written down |

Measured evidence that a template alone does not show habits: title register varies by
deck type and even by deck within one firm (Appendix A.3: topic titles on 223 of 231
investment-bank pages; claim titles on 197 of 317 strategy-consulting pages, with one deck
at 23 of 30 claims and a memo at 0 of 12); annotation moves and composition conventions
differ by deck type and by deck (section 22.3 items 3 and 4; Appendix A.2). None of this
is recorded in a master or layout.

### 6.3 Template library inventory

For every template, list: file, hash, page size, masters, and per master its layouts. Per
layout: name, type, placeholders (type, `idx`, geometry in EMU, text styles, whether
prompt text is present), layout-level chrome, and whether the layout is hidden or marked
unused. Per template: theme colour and font schemes, effect scheme, and which masters carry
which chrome.

From past decks, add usage: for each layout, how many past-deck slides use it, on which
deck types, with which compositions; layouts never used; layouts that past decks override
heavily (placeholders deleted, moved or covered); slides that use a blank layout and draw
everything by hand. Match a past deck to its template by its masters, layouts and theme,
not by file name. A past deck on an older version of a template (master or theme differs)
is recorded as such: its habits are evidence for the reference, its values are not evidence for
the current template.

### 6.4 Template selection

When the library holds several templates, the model chooses one per deck from: the brief
(deck type, audience, whether internal or client-facing), template names and descriptions,
the layout inventory, and which deck types past decks built on each template. When two
templates fit equally, the model asks the user rather than guessing (unmeasured as a
policy; it costs one question). The choice and its reason are reported.

Each template is a separate reference with its own guide. Habits may be shared across templates
of one company when the past decks show they are (for example the same number craft on
pitch books and board decks), recorded with the evidence; never assumed.

### 6.5 Layout selection per page

For each page the model picks the layout that holds the planned composition, using the
inventory and usage statistics: prefer a layout the company's past decks use for that kind
of page; write title, body and other content into the layout's placeholders where past
decks do, so the master's styles and later template changes propagate; use the reference's
title-only or blank layout and build in the content area where past decks do that. A page
spec names its layout; the solver reads that layout's placeholder geometry as fixed boxes
and its chrome as reserved zones. A layout name the template does not contain is refused
with the list of available layouts.

### 6.6 Habits from past decks

Mine habits from past decks with the same instruments used on any reference (sections 9
and 10.3): title register and length, where claims live, exhibit types and annotation
moves by data shape, emphasis devices, colour logic, composition clusters and variety,
density bands, number craft (units lines, $ placement, x suffixes, parentheses, NM),
continuation conventions, status tags, source and footnote style.

Which decks to mine:
- The user may mark exemplars; exemplars are weighted first in the page library and the
  digest (the weighting rule is unmeasured).
- Drafts, working versions and duplicates are detected and counted once: versions of one
  deck share most pages, and counting each version would inflate every habit's frequency
  (section 3.8). Near-duplicate detection by page text and arrangement; the threshold is
  unmeasured.
- Generated slides (carrying the skill's origin tag, section 16.5) are skipped by default,
  so the skill never learns from its own output.
- Recency matters where templates changed; the policy for weighting older decks is
  unmeasured.

Past decks also contain defects humans made (Appendix A.9 lists measured ones, recorded on
106 of 578 corpus pages: pictures past the margin, colliding data labels, misregistered
overlay boxes, mixed fonts, mismatched scales on sibling charts). A habit
is something the company's best pages do repeatedly, not something any page did once.

### 6.7 Brand guideline documents

Read guideline documents as evidence. Each stated value (hex, font family, logo clear
space, minimum size, tone rule) is recorded with provenance `stated`: document, page, and
the quoted sentence. Guidelines are untrusted input like any other file and are read
locally (section 7).

Conflicts: when a stated value disagrees with the template or with past decks (a stated
hex that the theme does not contain; a stated minimum size the past decks go below), both
values are recorded and the conflict is reported to the user. The skill does not resolve
it silently. Until the user decides, the template's observed value is used, because
generated pages sit on the template and past decks match it (unmeasured as a policy).
Stated rules that are habits rather than values (for example "one message per page") are
offered to the model as context, like any habit.

### 6.8 When no past decks exist

A template alone gives values but no habits. Then:
- Complete habits from the template plus the page library, with the measured deck-type
  tendencies as questions (Appendix A), at low confidence, with provenance `model_inference` and a
  `why` naming the library pages or tendencies used.
- Flag every such habit in the guide and in the report to the user: "habit not observed in
  company decks".
- Ask the user for even a few past decks or exemplar pages, and say what they would settle.
- The bar does not change; the report says that habits are unverified against the
  company's own work.

### 6.9 Other references

Any pptx or PDF reference is supported: a client's deck to match, a public deck, a single
exemplar. The same intake, extraction, completion and gates apply; the reference is its own
look. When the reference is a pptx, its masters serve as the template (section 11.2). The
skill takes one reference deck: when the user gives several, the model uses the one they
name, or asks which to follow; decks are never pooled.

### 6.10 When no reference exists

No reference is a first-class path, not a fallback. `extract_style.py --blank` writes a
draft in which every address of the look is open, the page size included, with the open
set as data (`BLANK_OPEN`); every answer carries provenance `model_choice`, and an address
left open refuses the guide (on this path nothing has a default). Before choosing, the model
reasons the look out from the audience and occasion, the subject's own world, the content
and its data, a named brand, and restraint (`references/no-reference-design.md`: reasoning
with corpus counts, never a default style or a menu), and writes that reasoning as
`/look_brief`; the completion refuses the brief only when it is missing or a placeholder,
and never weighs it. The model then chooses the page size, the faces (installed ones, so fit is measured), a type ladder with nothing
under the 7pt absolute floor, the palette, the spacing scale and margins, the chrome or
none, how tables and charts are drawn, and the look in words. The template is a blank
package at the chosen page size, built with `--chrome draw`. The build runs every hard
limit and skips every comparison with a reference (titles, variety, source-line and mark
habits, contrast precedent, the judge, leakage, the reference's chrome), each reporting
"no reference" rather than warning or scoring. Corpus evidence stays available as questions
in the references, never as a default style or a fallback value. `plan.has_reference` is
the one test of which path a guide is on, proven at the boundary.

---

## 7. Confidentiality and data handling

Company decks are confidential and contain client data. These are requirements, not
preferences.

### 7.1 Local processing

- Every script runs locally. No script makes a network call: no upload, no web fetch with
  content, no external OCR, rendering, font or conversion service. A check that the
  scripts open no sockets during a full scenario run is part of the evaluation program
  (section 21.1).
- Content reaches a model only through the model channel the company has approved for the
  agent. The skill adds no other channel.
- Fonts are installed locally; a missing face is reported, never fetched (section 14.1).

### 7.2 Derived artefacts are confidential too

Renders, crops, contact sheets, guides, digests, page library entries and reports derived
from company decks carry the confidentiality of their sources. They are written only under
the company's designated working directory, listed in a manifest with their source hash,
and deletable as a set. Nothing derived from company material is written into the skill
directory.

### 7.3 The page library and client data

- The page library is built from the company's own best pages (section 10.4). An entry
  that would copy a past page containing client data (names, figures, logos) needs the
  company's permission. Without it, the entry stores tags, structure and the reasoning
  note, and either a redacted render or no image (the redaction method is unmeasured).
- External public pages may be added; they carry their source and licence basis.
- One company's library is never visible to another company's work.

### 7.4 No carry-over into new decks

- A new deck contains only content from the user's brief and data for that deck, plus the
  company's own furniture (its logo, its disclaimers, its standard wording where past decks
  repeat it as chrome).
- Client names, figures, logos and text from past decks are never written into a new deck
  unless the user supplied them for it. The leakage gate (section 17.10) checks this.
- Reports, friction lists and critique findings quote confidential content only as far as
  needed to locate a defect.

---

## 8. Intake: reading any file

### 8.1 Formats and classes

- **pptx and potx**: the richest evidence. Read the OOXML directly (python-pptx is fine for
  writing but its reading API hides inheritance). Resolve inheritance fully: run properties
  come from the run, then the paragraph, then the shape's list style, then the
  placeholder's layout and master equivalents, then the master's text styles, then the
  theme; shape style references (`p:style/a:fontRef`) set a default text colour above the
  master default and below the run; table style `tcTxStyle` sets cell text colour. Colour
  maps (`p:clrMap`, overridable per slide and layout) apply before theme lookup. Reach the
  theme through the master's relationship, never by globbing theme parts (notes and
  handout masters carry the stock palette). All measured on real decks; see Appendix C.
- **PDF**: classify every page before mining (measured on 19 corpus PDFs: 8 are page images
  inside a letter-size print, not vector exports):
  - `vector`, `vector_with_image`: real type; mine it (a slide-shaped page with a pasted
    chart picture is still a vector page).
  - `raster_wrapper`, `raster_ocr`, `raster_only`: images; nothing on them is type
    evidence; the OCR or browser text layer gives a "reference" of 1pt Times.
  - `other_size`: memo or filing text bound in front of the deck; exclude.
  The deck class is the majority class. Page size for raster decks comes from the image
  box (letter-ratio image = deck printed to letter 11 x 8.5 in; 4:3 = 10 x 7.5 in).
  Measured: triage classified all 19 corpus PDFs with no deck misfiled against a reading of
  its renders.
- **Brand guideline documents**: read text, colour swatches and stated values with page
  locations (section 6.7). Raster-only guideline pages are read by the model from images.
- **Rotated text** in PDFs (copyright lines set vertically) must be detected and either
  read with its rotation or excluded. Known failure mode (measured once): a rotated line
  read one glyph per run produced 2 to 4pt size levels with up to 764 votes and a body size
  of 4pt, and was mined as four horizontal chrome items drawn reversed ("thgirypoC").

### 8.2 Rendering

- Render with LibreOffice in a pinned container, locally, one conversion at a time per
  process, an isolated profile per worker (`-env:UserInstallation`), `--nolockcheck
  --norestore`. An interrupted soffice leaves a lock in its profile; use a fresh profile per
  render.
- Render at 1600 px width for reading; produce a contact sheet (grid) of all pages.
- Report fonts: for every face the deck uses, what the renderer drew (via `fc-match`) and
  whether it is the face itself, a metric alias (layout-faithful, visually different:
  Arial as Liberation Sans), or a substitution (render is not evidence of fit). Report
  characters the drawn font cannot cover (tofu), and refuse to use crops whose faces
  cannot draw the deck's characters. Companies often use licensed faces; install the
  company's font files in the container rather than accept a substitution.
- Hidden slides are not exported by the renderer; count and report them.
- Long decks and large libraries: measured once, extraction took 18.6 minutes on a
  205-page PDF with no progress output. Print progress, measure where time goes, and cache
  per-file results by hash so a library is not re-read on every run.

### 8.3 Scanned references (raster)

Pixels still tell: palette by painted area; text ink as the modal dark colour; chrome as
pixels holding one colour on at least half the pages (rules, bands, logo block, page
number area); margins from ink extents; line pitch by autocorrelation and a body size
from it. Measured on a native-pptx bank deck rendered to images at 100 dpi and re-measured:
surface and accent exact, ink within 1 unit, left margin within 0.01 in, other sides within
0.09 in, body 11.7pt from a modal 14pt pitch against 12pt in the file
(dev/proofs/keybank-raster-oracle.md). On real scans, line
pitch held on 3 of 11 pages (measured), so treat it as weak evidence. Faces cannot be read
from pixels: the model looks at page images beside candidate fonts and names the family.
Raster measurements carry provenance `raster_inference` and confidence 0.5. Report
effective dpi honestly (known failure mode, measured once: 69 px per inch reported where
the image carried 104 dpi).

The judge must not fingerprint a raster reference from its text layer (section 19.4).

---

## 9. The style guide

### 9.1 Purpose

The guide is the single source of style truth for one reference (or for the look the model chose with none). Page specs refer to its
roles and layouts; the solver measures with its values; the emitter writes its values; the
gates check against it. One definition per concept (section 3.10).

### 9.2 Schema (top level)

Every value node carries `provenance`: `value_provenance` (observed | stated |
deterministic | model_inference | raster_inference), `evidence` (file hash, slide numbers,
shape ids, guideline page and quote, counts), `frequency`, `master_membership`,
`confidence`, and a `why` for anything the model wrote.

- `reference`: the reference's sources: template file and hash; past decks used (file, hash,
  slide count, format, template match, version group, exemplar flag); guideline documents
  (file, hash); for PDFs, text-layer triage (status, deck class, per-class counts, raster
  pages, slide box, size basis, print scale, effective dpi); page width and height in EMU
  and inches.
- `layouts`: the inventory of section 6.3 for this template: per layout its name,
  placeholders with geometry and styles, chrome, and past-deck usage (counts, deck types,
  compositions built on it).
- `typography`:
  - `families`: major, minor, fallbacks, and `substitutes` (a stand-in face name that MUST
    equal what `fc-match` returns in the renderer; known failure mode, measured: measuring
    with DejaVu Sans while LibreOffice drew Inter, so renders were not evidence).
  - `levels`: every observed size with votes (run count, character count), weights,
    families, and which roles use it. This is the size histogram.
  - `roles`: `type.title`, `type.h1`, `type.h2`, `type.body`, `type.body_small`,
    `type.caption`, `type.footnote`, `type.source_line`, `type.table_header`,
    `type.table_cell`, `type.data_label`, `type.axis_label`, `type.emphasis`,
    `type.kicker`, plus any the reference shows; each with size, family, weight, italic,
    caps, tracking, colour role, line spacing, space before and after, alignment, and
    bullet definition by level (glyph, font, indent, hanging).
  - `scale_ratio` (if the ladder is geometric; null when it is not, which is legal).
  - `bullets`: per level glyph, bullet font (a Wingdings square renders as a section sign
    without its font; measured), indent, hanging indent.
- `color`:
  - `theme`: the twelve theme slots resolved.
  - `roles`: `color.surface`, `color.surface_alt`, `color.ink`, `color.ink_muted`,
    `color.ink_inverse`, `color.rule`, `color.accent1..n`, `color.positive`,
    `color.negative`, `color.highlight`, each with hex and usage evidence.
  - `usage`: colour pools by use (text, fill, line, chart series) with counts.
  - Role names are assigned by usage, not by theme-slot convention: measured on one
    native-pptx bank deck, `color.accent1` by usage is the observed light grey and the deep
    blue is the second accent.
  - `off_template`: colours past decks use repeatedly that the theme does not contain,
    with counts; reported, and usable only as roles the guide declares.
- `spacing`: steps `space.xs..xl`, `space.gutter`, `space.margin`, from measured gaps
  (cluster the observed gaps); margins per side; baseline grid if any; gap levels.
- `composition`: archetypes (clusters of pages by arrangement, with member pages and the
  layout each uses), bands (title band, body band, footer band with EMU extents), column
  grids, alignment edges, and `consecutive_max` (the longest run of one archetype in the
  reference's decks).
- `titles`: register per title (topic phrase, question, claim sentence) with counts;
  length distribution in characters and words (median, max); line count distribution;
  where claims live when titles are topics (lead-in bullet ending in a colon, numbered
  takeaway row labels, a takeaway box, a subtitle). Mined from past decks; a template's
  prompt text is not evidence of register.
- `register_stats`: per page counts by element kind (text, image, shape, table, chart,
  line), decoration count, container ratio, as 10th to 90th percentile bands, AND how
  exhibits are realised (native chart, native table, pasted picture, drawn shapes) so a
  reference that pastes pictures does not make native exhibits read as "above".
- `density_bands`: words, elements, covered area per page as 10th to 90th percentiles,
  each with an evidence flag (no evidence is not zero).
- `exhibit_habits`: measured from the reference's own exhibits, by looking at them (section
  10.3): exhibit types used, annotation moves and their frequency by data shape, emphasis
  devices (outline box colour and weight, shaded rows, subject colour), number formats
  (units line, $ placement, x suffix, parentheses, NM), legend and label habits, colour
  logic, each recorded in the coder's words (for example single hue tints plus one "look
  here" colour, or categorical); nothing is chosen from a list.
- `chrome`: list of items (rule, band, logo, label, page number, confidentiality marking)
  with geometry, z-order, rotation, fill and ink roles, anchor (master, layout, slide
  layer), and whether drawn per slide.
- `motifs`: recurring non-chrome devices with roles, preset shape, size and anchor
  (`region_edge`, `element_adjacent`).
- `tables`: header fill and ink roles, header bold, banding role, edge rules by class
  (table top, header bottom, row interior, table bottom, left, right, column interior)
  with width and colour role, cell padding role, alignment by column type, totals rule.
- `charts`: series colour roles in order, per chart kind (bar, column, line, pie): data
  labels, gridlines, legend, axis visibility, gap width, as observed.
- `shape_language`: corner radii (modal roundRect radius, share of rounded shapes, read
  from the file, never from renders), outline habits, shadow use.
- `imagery`: the company's logo assets and their placement rules (stated and observed),
  photography, icons.
- `floors`: per family of roles (body, annotation, display, chart) the smallest size the
  reference uses (`floor_pt`; null with no reference) and the absolute floor (section 14.5); a guideline-stated minimum
  is recorded beside it.
- `continuation`: how a page that splits continues (header repeat, "(cont'd)" mark,
  takeaway policy).
- `conflicts`: every disagreement between template, past decks and guidelines (section
  6.7), with both values, evidence and the user's decision once given.
- `extra_roles`: model-added roles with hex and why.
- `derivation_rules`: how the palette and type ladder extend to roles never shown.
- `description`: the model's written description (summary, typography, colour, layout,
  tables, imagery, motifs, `not_seen`, tone). Written after looking; read back while
  designing. `not_seen` lists what the reference was not seen doing, stored with the pages
  read, as evidence of a tendency and never a rule; the old key `never_does` is refused by
  name.
- `unresolved`: the open addresses with the reason each is open.
- `notes`.

### 9.3 Extraction from the template

- Theme colours, fonts and effects; master and layout text styles per level; placeholder
  geometry and styles per layout; master and layout chrome. All `observed`.
- Template prompt text ("Click to add title") is not content and not evidence of register.
- Values the template defines but no past deck uses are recorded with frequency 0 in past
  decks; they are legal but carry no habit evidence.

### 9.4 Extraction from past decks and other references (deterministic)

- Walk every slide (hidden slides too, as evidence; mark them). Skip slides carrying the
  skill's origin tag (section 16.5) unless asked. Group versions of one deck (section 6.6).
- Collect every run with resolved properties; histogram sizes; assign roles by position,
  placeholder type, frequency and context. The title role must come from title position
  evidence (the title placeholder or the top band), never from size votes alone. Known
  failure mode (measured once): on a vector-PDF consulting deck, `type.title` was bound to
  44pt cyan numerals (20 votes) while the real page titles were 25pt white Georgia. When
  evidence conflicts, leave the role open for completion rather than binding the larger
  vote.
- Spacing from measured gaps between adjacent elements, clustered.
- Composition by clustering page arrangements (element boxes, normalised), with the
  layout each page uses.
- Chrome by recurrence across pages and master or layout membership; for PDFs, by
  recurring lines and boxes across pages.
- Every value that cannot be proven goes to `unresolved`.
- Measured: two independent extractors agreed on title, body, emphasis and caption sizes,
  surface and ink on four decks, and differed on 47 of 160 compared values (h1 and h2 sizes
  on two decks, rule and muted ink by deliberate change, spacing steps on two). Treat
  heading sizes and spacing steps as the least stable values; open them when evidence
  conflicts.

### 9.5 Combining the sources

- Template values are `observed`; guideline values are `stated`; past-deck values and
  habits are `observed` with evidence naming deck and slide.
- Where template and past decks agree, one value with both evidence lists.
- Where they disagree, record both and add to `conflicts` (section 6.7).
- Habits come from past decks only; if none exist, see section 6.8.

### 9.6 Completion by the model

- The model answers exactly the open addresses; a key outside `unresolved` is refused,
  except always-writable keys: `/description`, `/derivation_rules`, `/continuation`,
  `/typography/families/substitutes`, `/notes/*`, new `/extra_roles/<name>`, and new type
  roles at sizes the levels table shows. For raster references, whose levels table is
  empty, the model must be able to add levels it measured from images (known failure mode,
  measured: without this, table and label roles were blocked on a scanned reference).
- Observed and stated values cannot be overwritten. If the model believes one is wrong, it
  reports it; the fix belongs in the extractor or with the user.
- The core must close: `type.title`, `type.body`, `color.surface`, `color.ink`,
  `color.accent1`, and one of caption, footnote or source line.
- `null` is a legal answer where the honest answer is "none" (no baseline grid, no
  geometric ratio). Known failure mode (measured once): a completion step that crashed on
  null.
- Accept every documented form (for example an extra role as `{hex, why}` as well as a
  bare hex). Known failure mode (measured once): one form documented, another accepted.
- Completion groups: when there are many open addresses, complete them in groups derived
  from the draft (not a hand-written list), the groups partitioning the open set; a group
  that names a role runs after the group that defines it. Measured: a single completion call
  handled 52 and 70 open addresses with 0 to 1 retries, so groups are for ordering
  dependencies, not because focused calls reason better (unmeasured).
- Every value comes from this reference's evidence. Low confidence beats convention: a reference
  whose decks have no charts gets a chart language derived from its palette and register,
  not a stock one.
- Renders are evidence for colour, proportion and position; not for fit, line spacing,
  padding or rule weight.
- The draft's open list and the documented example completions must agree. Known failure
  mode (measured once): a shipped example completion left 9 addresses the draft opened.

---

## 10. Visual context

The model sees. Give it pictures, chosen well.

### 10.1 Renders

All pages at 1600 px and a contact sheet. The model looks at the contact sheet once and at
full pages as needed. For small type use crops: measured for one model family, a model that
downscales a 1920 px render to 1456 px leaves 6.5pt text at 1.1 to 1.8 times its
legibility ceiling. For a large past-deck library, render on demand and cache by hash.

### 10.2 Gallery: crops and exemplars

- Segment each page into components (title block, table, chart, panel, banner, takeaway
  box), crop them, cluster by appearance and structure, pick exemplars: one full page per
  composition family, plus crops.
- Pick crops by greedy set cover of the style tokens they show, not by recurrence
  (measured: recurrence ordering lost 10 tokens on one deck). Use an area floor of
  200 x 200 px, not a short-side floor (measured: a short-side rule deleted each deck's most
  repeated banner).
- Measured: 28 to 43 values per deck are drawn by the master and need full-page exemplars
  to be seen.
- Each crop gets a caption and a skeleton line (the structure in words).
- The gallery must work for PDFs as well as pptx (known failure mode, measured: a gallery
  that refused PDFs while the instructions told every user to run it).
- A `pick --intent "<text>"` command returns the nearest exemplars and crops from the
  company's decks for a page intent. Measured: ranking by word overlap is weak; "overlap 0
  everywhere" means the reference has nothing for that intent, and the model must design from
  the guide and the library. Rank instead by structured tags (composition, exhibit type,
  data shape, layout) produced when the model reads the decks (section 10.3). Unmeasured.

### 10.3 Exhibit digest

During intake the model looks at every exhibit page of the company's past decks (crops at
readable size) and records, per exhibit: type, data shape, the one message, annotation
moves (with what they anchor to), emphasis devices, number formats, legend and label
handling, colour logic. Aggregated, this fills `exhibit_habits` and `titles` in the guide.
This is model reading, structured; it turns "look at the company's decks" into data the
model can consult while designing. A large library is sampled by deck type and recency
with the sample recorded (sampling policy unmeasured). Digest records are confidential
artefacts (section 7.2).

### 10.4 The page library

A curated set of excellent real pages, shown as examples (not templates) when the model
plans a page whose intent matches. Each entry is tagged with the fields below; the external
starter set (section 22.4) uses exactly these, and the company's own entries use the same
fields so that one retrieval serves both:
- **Source**: the page image; the source deck and page as an internal reference (kept in
  the library's manifest, never written into generated pages); the coder who tagged it;
  the source type (company deck or external public deck).
- **Deck type and page size** (examples do not transfer across aspect ratios; see the
  rules below).
- **Composition**: the family from the measured taxonomy (Appendix A.2) plus the coder's
  own description of the arrangement. The coder's description is the better one where
  several panels were recorded as one exhibit.
- **Layout** (for company pages): the layout the page was built on.
- **Title** and its register (topic, claim, question).
- **Exhibits**: per exhibit, its type, family, data shape and one message, and its
  annotation moves as the coder recorded them, all in words (Appendix A.6 counts the
  corpus's moves as evidence; it is not a list tags are chosen from).
- **Emphasis devices** and **craft details**.
- **Why instructive**: one line on what the page does well.
- **Designer questions**: what the designer evidently had to know or ask to produce it,
  phrased as questions, never as rules (Appendix B).

Built from, in order:
1. The company's own best pages: exemplars the user marks, then pages the model selects
   from past decks during the digest, confirmed by the user where possible. Subject to
   section 7.3.
2. Optionally, external public pages. The development corpus provides a starter set of
   about 40 pages: 15 from investment-bank decks, 21 from strategy-consulting decks and 4
   from a dense market chart book, drawn from each coder group's most instructive pages
   and balanced across deck type and composition rather than chart pages first. 15 of the
   40 have a table, matrix, diagram or structured text, not a chart, as their main exhibit.
   What such entries teach, for example: ranking panels re-sorted each period with the
   subject marked in every panel; a football field judged against the offer line; numbered
   method-to-finding rows instead of bullets; ordered options as a spectrum with a pointer
   to the recommendation; the absence of a mark as evidence; the answer as the last row and
   the only one boxed; each panel proving one clause of a two-part title; the non-focus
   layers of a diagram faded; the headline number derived on the page; a table and a chart
   held in one row order.

Rules for the library:
- Real pages only. Measured: hand-authored specimen pages were scored 3 of 10 by a
  reviewer, and judging output few-shot conditioned on those same pages is circular.
- 3 to 5 diverse examples per intent (external guidance; unmeasured here).
- The company's own pages always outrank external pages; external pages teach reasoning
  and craft, the company's pages teach its style.
- The library's mix follows the page mix, not the chart mix: 346 of 578 corpus pages carry
  no data chart (Appendix A.1), so a library of chart pages would teach the wrong
  proportion (inferred).
- Page examples composed for one aspect ratio do not transfer to another (measured: of 14
  specimen families composed for 16:9, 2 fit as written on a 4:3 reference on 2026-10-20 and 1
  on 2026-10-26; those 14 specimen pages have since been removed). Tag each entry
  with its page size.

---

## 11. Templates, layouts and chrome

### 11.1 Choosing the template

Section 6.4. The chosen template, its guide, and the reason are recorded in the build
report.

### 11.2 Company template (pptx or potx)

Build on the company's template file itself: masters, layouts, theme and chrome intact.
For a .potx, the main part's content type differs from a .pptx's and must be switched when
writing a presentation (external: OOXML specification; verify on the company's files). For
a past deck or any pptx used as a template, remove every slide and keep masters, layouts,
theme and chrome. Measured: PowerPoint opens and re-saves such packages without repair and
draws chrome once per slide. Page numbers and footers the reference carries on its slides are
copied from the layout to each new slide.

When the template carries masters or layouts that no past deck uses, keep them in the
package (the company expects its full template) and offer every layout with its usage
count ("used on 0 of 140 past slides"): the count is evidence beside the choice, and a
page on an unused layout says why in the report.

### 11.3 Layouts and placeholders

- Each page spec names a layout (section 6.5). The solver treats that layout's placeholders
  as fixed boxes with their inherited styles and its chrome as reserved zones.
- Content written into a placeholder inherits the placeholder's formatting; the emitter
  writes only what differs from the inherited value, and the read-back (section 14.4)
  measures the resolved result.
- A placeholder the page does not use is removed from the slide, never left showing prompt
  text (unmeasured as a hazard on renderers; verify).
- Placeholder geometry is the layout's unless the spec declares an override; a declared
  override is reported beside how past decks on that layout use it (whether any override
  it, and to what). Chrome collision, off-page and overflow still refuse.

### 11.4 PDF reference (no template file)

A blank package at the reference's page size, with chrome drawn per slide from the guide:
rules, bands, logos, footer labels, page number fields, surface colour. Requirements, each
from a known failure mode:
- Draw in the reference's z-order (measured once: a full-page white band drawn last buried
  the title band, the rule and the page number).
- Reserve only the zones chrome actually occupies (measured once, a blocker: bands
  anchored to the full page reserved the whole page, leaving no content area).
- Chrome text carries the reference's observed ink and is scored by the contrast gate
  (measured on two firms: the reference name and the page number drawn in default black on
  navy pages, invisible and unscored).
- Rotated chrome keeps its rotation, or is refused.
- A logo the reference shows is carried (the firm's own chrome, decided for the deck): extract the logo image from the reference
  (crop from the PDF or the pptx media; for a company, prefer the company's own logo file)
  and place it. Measured once: an empty outlined placeholder in place of the logo; the
  blind rater named missing logos as a tell.
- No inherited theme effects (measured on two firms: rules drawn on a blank template
  picked up a grey drop shadow from the theme's effect style in LibreOffice). Write
  effect-free shapes explicitly.

When a company has a template, never build on a constructed blank instead; the blank is
for references that arrive only as PDF.

### 11.5 Slide-layer chrome

Logos, rules, labels or confidentiality markings the reference pastes on every slide (not on
the layout) are where each generated page starts: drawn by default, shown with their
counts ("on 31 of 33 reference pages"). A page may omit or replace a non-firm entry with a
`why`, reported; the firm's own chrome, legal and confidentiality marks are never omitted
page by page. Zones, contrast and position drift read the same per-page list. Chrome the
layout carries is inherited, never redrawn.

### 11.6 Logos

The company's logo comes from the company's asset files or the template media, placed by
the stated and observed rules. Client and counterparty logos come only from the user for
this deck (section 7.4); where the reference uses logos as category labels or in logo walls,
the page names the logos it needs and the user supplies them.

### 11.7 Round trip (prove the chain)

Before designing, import one past-deck page into a page spec (layout, roles and weights;
no coordinates survive), build it on the template, judge it and look at it beside the
original. Measured: on a native-pptx bank deck the round trip scored 0.057 to 0.056, inside
the reference's own spread. The look matters more than the number: measured once, the judge
said 0.083 while labels were black and left-aligned because the reader had missed a
shape-style text colour on both sides. The import must work for PDFs (known failure mode,
measured on three firms: import produced empty paragraphs for PDF pages).

---

## 12. Planning a section

### 12.1 Storyline and page plan

The model writes a plan before any page: for each page, its message (or, on a reference
page, what the reader looks up: 263 of 372 topic-title corpus pages state no claim), the
evidence that proves it, the exhibit, supporting text, data needed, the composition intent
(which element dominates, or how co-equal blocks divide the page), the layout, split
boundaries if it will not fit, and the title, whose register and length are reported
against the reference's (`guide.titles`).

### 12.2 Figures

Use the user's figures byte for byte. Never invent a number; a missing figure is a named
placeholder. Every figure stated in a title, lead-in or callout is computed from the
exhibit's own data before writing (midpoints, medians, counts above a line). Known failure
mode (measured once): "$11.40 sits above every method's midpoint" written where two
midpoints were above it. Measured: every fresh agent in six scenario runs wrote a generator
script that computed and asserted every stated figure, and it worked well; encourage it.

### 12.3 Variety plan

Before building, the model lists the planned composition, layout and exhibit type per page
and compares against the reference's measured variety. Measured over 23 corpus decks (Appendix
A.10): the median composition change between consecutive pages is 0.69 on a coarse
10-family taxonomy (investment-bank 0.645, strategy-consulting 0.765), and exhibit types
change more often than compositions (median exhibit-set change 0.77 and 0.85). On a finer
taxonomy, three native-pptx bank pitch books change composition 83% to 90% of the time with
no run longer than 2 pages. Every longer run (up to 7 pages) is a deliberate sibling
template: recap pages, segment tables, an appendix of row-label pages, two matching
scenario pages. The plan states which repeats are deliberate and why. Sibling pages meant
to be compared share one scale and one category order (mismatched sibling scales were
recorded as human defects); whether they also share one layout is the plan's question.
Measured: a designer given a composition-history digest and an instruction to vary still
used one arrangement for 6 of 19 designs where the register allowed 1, so a prompt alone
did not produce variety. Variety is therefore planned at section level: the plan check asks
the plan to declare or vary each repeat (a question the plan must answer, not a cap: a
reason in words clears it), and the build's repetition report (section 17.7), which
compares content regions, not page furniture, is evidence read in the variety report.

### 12.4 Co-equal content

Measured once on two model tiers: "one element dominates" without guidance for co-equal
blocks produced dashboard-like panel grids on multi-block content. Ask the model whether
each block's size says how much it matters to the message. Equal panels are not
themselves the defect: 77 of 578 corpus pages carry two or more exhibits, and equal small
multiples on a shared scale are how the corpus makes a comparison honest (Appendix A.2).
The question is whether the blocks are a comparison (panels meant to be compared share one
scale and one order) or unrelated facts.

---

## 13. The page specification language

### 13.1 Shape

A page names its `layout` and is a tree. A region lays out children with:
- `flex`: direction (row | column), `gap_role`, `pad_role`, `align` (start | center |
  end | stretch), `justify`, child `weight`s.
- `grid`: rows, cols, gutter role, named areas.
A region may carry `fill_role`, `line_role` and `pad_role` (a filled, padded box such as a
takeaway panel). A region or element may be bound to a layout placeholder (`placeholder`:
type and idx), in which case its box is the placeholder's.

Elements:
- `text`: paragraphs, each with type role, text, bullet level, `ink_role`, `align`,
  emphasis runs.
- `table`: columns (value kind: text | number | currency | percent | multiple | date;
  `width_share` or `min_width_role`; alignment override), header rows with spanners, body
  rows, row classes (totals, subtotal, emphasis, statistic, subject), per-table overrides of
  banding, alignment and fills as roles.
- `chart`: the full chart spec (section 15.1).
- `image`: an asset reference (logo, picture) with fit mode.
- `rule`, `rect` (with preset shape), `connector`/`arrow`.
- `annotation`: shapes anchored to another element's data coordinates (section 15.3).
- `component`: a kind and its data (section 15.5).

Every size, colour, gap and font is a role. A literal value is refused with the list of
available roles. An unknown key is refused by name (known failure mode, measured once:
emphasis-row keys written on the wrong node were silently dropped). Keys that have an
obvious alternative spelling (for example OOXML's `nextTo` for `next_to`) are accepted or
refused with the correct spelling named. An unknown layout or placeholder is refused with
the available list.

### 13.2 Limits

Any structural limit (tree depth, node count) is documented and each violation has its own
message (known failure mode, measured on two firms: "duplicate id", "over 400 nodes" and
"depth over 5" merged into one message, costing builds). The bounds are runaway guards,
not design limits: depth 5 measured shape nesting, not layout trees, and refused a
component placed three regions down, so the depth bound is 12 and each page's deepest
chain is reported.

### 13.3 Conventions enforced

- A title is given the reference's title band or title placeholder; a title needing more
  lines than the band holds does not fit, and that is reported first, before other
  violations (they follow from it), with both fixes (shorten it, or move a clause to where
  the reference states claims). Its register and length are reported against the reference's, as
  warnings to answer.
- Chrome zones are reserved automatically; content never runs under footer furniture.
- A page with a table or chart and no source or footnote paragraph is checked against the
  reference's observed source-line rate (section 17.9).
- Ids are unique per page; elements that are the same thing across pages (title, source
  line) share ids so position drift can be checked; different things never share ids
  (known failure mode, measured once: drift reported between unrelated elements that
  happened to share an id).

### 13.4 Capacity query

Before writing text, the model asks the solver how many lines and characters each region
and placeholder holds per role, from the measured ruler, and writes to that budget.

---

## 14. Text measurement and the layout solver

### 14.1 The ruler

- Measure with HarfBuzz shaping on the actual font files (fall back to Pillow only if
  HarfBuzz is unavailable; measured: they agreed on 89 of 90 recorded wrap cases, HarfBuzz
  on 90 of 90). The company's licensed font files are installed locally for this; never
  fetched.
- Measure whole runs, never sums of fragments.
- Measured: PowerPoint fits less text than LibreOffice on 92 of 600 boxes. Shrink the width
  budget by a measured epsilon (5,933 EMU with the Pillow ruler, 20,234 EMU with HarfBuzz)
  so a measured line never runs long in PowerPoint.
- Line pitch is 1.2 times the font size, font-independent (measured on 7 families); font
  metric tables are wrong by up to 20% for this purpose.
- Wrap at spaces and break opportunities; never inside a word. A word wider than its line
  refuses the page by name (`word_split`) rather than breaking mid-word (known failure
  mode, measured once: "Consideratio" / "n" written and reported as fit).
- Non-breaking pairs: a figure and its unit, a currency mark and its figure, a period
  prefix and its year (`$1.2 bn`, `EUR 40 mm`, `FY 2024`, `12.5 %`).
- Write the measured line breaks into the file as literal breaks so PowerPoint cannot
  re-break differently.
- Metric aliases: one table, fontconfig's 17 binding="same" classes (Arial = Liberation
  Sans, Calibri = Carlito, and so on). Helvetica is not an alias of Liberation Sans. A face
  with no alias and no installed file is refused until the guide names a stand-in that
  equals the renderer's `fc-match` result, and the report tells the user which font file
  to install.
- Italic roles need an italic face; a stand-in without italics (DejaVu Sans, measured
  once) silently drops italic capacity.

### 14.2 The solver

- Exact integer EMU arithmetic. Allocate flexible shares in whole EMU (a 1-EMU rule must
  stay 1 EMU; known failure mode, measured: rounding produced 0 or 2 EMU on 6 of 12 tested
  heights).
- Placeholder boxes from the page's layout are fixed; the solver lays out content inside
  them and in the free content area.
- Region height is its content height unless it holds an element with no intrinsic height
  (chart, image, rule) or carries a weight inside a column. `align: stretch` does not make
  a row flexible. A flexible region never gets less than its content. (Measured: these
  rules replaced ones that gave a row of fixed figures half the spare height and starved a
  table.)
- Every element is held to its own box: text taller than its box and table rows taller
  than the table's box are violations, wherever the element sits (known failure mode,
  measured: a table that was a direct child of a stretch row was never checked against its
  fitted height).
- Tables: fit column widths by measured content, honouring `width_share` and
  `min_width_role`; report per-column width deficits; row heights are lines x 1.2 x size
  plus cell margins, which is what PowerPoint realises (measured); report
  `rows_to_fit_slide` for splitting.
- Type scale descent: if the page does not fit at scale 1.0, step the whole type ladder
  down uniformly toward the floor, re-solving each step.
- The emitter writes the solver's resolved sizes (size, line pitch, spacing, tracking,
  cell insets) for exactly the scale chosen. Known failure mode (measured once, a
  blocker): solving at scale 0.89 but emitting 12pt table cells and a 25pt title at full
  size; text then overlaps while every gate passes. Requirement: one resolved entry per
  element, produced by the solver and consumed by the emitter; the emitter refuses an
  element that arrives without it.
- Output on failure: `status: unfittable`, the smallest admitted scale, every violation
  located (element id, needed EMU, budget EMU), and for each table the body-row count at
  which to split. Nothing is ever dropped to make a page fit.

### 14.3 Density as a search

Density is a loop the model runs: build, read where the page sits in the reference's density
band (reported as evidence), and decide what the page needs. Moves, in no order and for
instance: add an exhibit the argument is missing, re-arrange (two columns, table beside
chart, a compact component variant, another layout), cut words, split at a declared
boundary with the reference's continuation convention. Measured: hand-built specimen pages had
median ink coverage 0.21 to 0.25 against 0.576 for 96 corpus pages; what closed the gap was
adding missing exhibits, not enlarging existing ones.

### 14.4 Fit read-back

After emitting, read the written file back, resolve inheritance (including placeholder
styles), and re-measure every text element and table against its solved box. A shape that
outgrows its box refuses the page as "emitted text overflows", naming the shape. Measured,
non-tautological: restoring an emitter with the scale defect of 14.2 made the read-back
refuse six shapes.

### 14.5 Legibility floors

- `floor_pt` per role family is the smallest size the reference uses; never generate below
  `max(floor_pt, absolute_floor_pt)`. A guideline-stated minimum above that is honoured.
- `absolute_floor_pt` = 7.0pt. Measured on two screen media with one rater: legible down to
  6.0pt Arial; 6.5pt Calibri regular, 7.0pt bold. Print was not measured; for a printed
  deck, never go below the reference's own floor. The model may lower a floor in completion
  only when the reference's own captions show the smaller size.

---

## 15. Exhibits

### 15.1 Charts

Native charts written from a complete spec the model writes:
- `type`: any PowerPoint chart type the emitter can write (its capability table: column and
  bar clustered, stacked, 100% stacked; line, with markers; pie, doughnut; area; XY
  scatter, with lines; bubble; radar; combo with secondary axis). The table says what can
  be written, not what to show: the form is reasoned out per exhibit, in the plan's
  exhibit brief, from the questions of Appendix B.
- Series: name, values (XY as [x, y] pairs), `fill_role` or `"none"` per series and per
  point, `line_role` and width, smooth, marker; data labels per series and per point
  (show, position, number format, type role, `ink_role`, custom text); secondary axis.
- Axes: visible, line role and width, gridlines, number format, reverse, min, max, major
  unit, tick marks, tick label position, crossing.
- `gap_width`, `overlap`, legend (position, hidden entries) or `"none"`, chart text role
  and ink, plot fill, title.
- Plot area written as a MANUAL layout (fixed inner plot rectangle) so that data
  coordinates are computable in EMU (section 15.3).
- Colours are roles only; literal hex refused; unknown keys refused.
- `c:varyColors val=0` is always written (file safety: the renderers read its absence
  oppositely; measured: PowerPoint paints one series in five theme colours).
- Every choice left out is written as a named neutral value (section 3.1: nothing
  written, or the reference's observed value with provenance; never a styled constant) and
  reported per page.
- No special chart kinds (no "waterfall" or "football field" type): they are recipes over
  the general spec (invisible base series with fill none; a zero-height carrier for
  labels; an invisible low series for ranges). Recipes are documentation named by
  mechanism (invisible series, zero-height carriers, error bars), each pointing at the
  reference's pages for how its look draws them; the model adapts them.
  An optional `bridge` declaration on a chart (deltas and totals) is tied out by the build:
  each total against the running sum and each drawn span against its step.
- Known renderer and writer hazards (measured): an XY scatter series that does not set
  `smooth` crashed one chart writer; LibreOffice 24.2 draws nothing for the first XY
  scatter series when a later series declares a larger ptCount (writing every series with
  the group's largest ptCount, extra points blank, draws all; measured); LibreOffice wraps
  category labels and in-bar data labels mid-word in narrow slots. The build must measure
  category and data labels against their slot (upper bound of the category width; bar
  thickness for centred labels) and refuse a label that will break mid-word, naming it.
- Where the company's past decks paste chart pictures, the generated chart is still native
  (editable), styled to match the pictures' look as read in the digest.
- Features the measured moves need (Appendix A.6, A.7), each found missing from the chart
  spec of an earlier build of this kind: combo plots sharing one set of axes (real
  reference lines and dot overlays on bar and column charts; reference lines appear on 77
  exhibits); series `dash` and pattern or hatch fills (forecast demarcation on 39
  exhibits, dashed reference lines); per-point marker overrides; error bars or high-low
  lines (ranges); a trendline (regression on 3 scatters); series lines between stacks
  (connectors on 22 exhibits); axis titles; manual data-label positions; and the manual
  plot layout of section 15.3. An axis break (14 exhibits, with inversion and rebasing) has
  no native form; it is drawn by the overlay layer or not at all (unmeasured).

### 15.2 Tables

- Header fill and ink, rules by edge class, banding, padding, alignment by value kind, from
  the guide; per-table overrides as roles.
- Shared edges written identically on both adjacent cells (measured: PowerPoint keeps the
  first declared side and writes it back; LibreOffice draws the heavier).
- Strokes below 0.5pt only when the guide declares them (measured: 0.48 px in PowerPoint vs
  1.27 px in LibreOffice).
- Row classes: totals (tie-out checked), subtotal, statistic (median, mean: skipped by
  tie-out), subject (set apart), emphasis (requires an explicit fill role or `none`).
- Number craft: what does this reference write (its observed habits first, Appendix A.9 as
  corpus evidence)? The corpus recorded units lines or units columns, $ only on first and
  total rows, x suffixes on multiples, parentheses for negatives, NM and n.a. written out,
  footnote markers resolving in the footer zone, sorted order where the message is a
  ranking. Figures stay byte for byte; a format never rounds away precision.
- Cell-level styling, because the measured table moves need it (Appendix A.6, A.7) and a
  table spec with per-row styling and one emphasis fill per table could not express them
  (known failure mode, measured on an earlier build: 99 of 192 tables carried at least one
  such move):
  - merged header cells (`gridSpan`) for true column spanners and partial underlines
    (spanners on 57 exhibits, 45 of them tables);
  - per-cell fill, border, ink, weight and italic (boxed cells on 50 tables, input cells
    and base cases on 8, semantic cell colour on 15);
  - per-row italic (italic ratio rows on 16 projection tables);
  - more than one emphasis style per table, each a role (comps tables emphasise the median
    row on 12 of 15 and the subject on 8 of 15, often both; projection tables shade several
    total rows, 27 of 42);
  - a table with in-cell bars (13 exhibits) as a component from rects sized by weight.
- Tables carry most of the corpus's pages (192 tables against 291 charts, and in bank decks
  117 tables against 109 charts; Appendix A.5), so table craft deserves at least the effort
  given to charts.

### 15.3 Annotation layer

Humans annotate almost every data exhibit, and much of what they do is a shape placed on
the exhibit at a data position. Measured over 601 exhibits on 578 corpus pages (Appendix
A.6, A.7): 7 of 291 charts carry no annotation; the commonest moves are data labels on all
marks (131 exhibits), a circled or boxed mark (105, 50 of them on tables), highlight one
item and mute the rest (90), footnote markers (90), a callout box, arrow or leader (77), a
reference or benchmark line (77), direct labels instead of a legend (59), column spanners
(57), shaded or bold total rows (51), brackets or braces (24), event markers (29), an inset
stats table inside the plot (24), data rows aligned under the chart (29) and connectors or
zoom lines between marks (22). In the native-pptx bank decks, 27 of 33 data exhibits were
pasted pictures with annotation shapes laid over them at absolute offsets: humans solve
the problem by overlay.

Measured against the chart, table and page-grammar spec of an earlier build of this kind
(native chart features, recipes over them, and a grammar of non-overlapping elements): 150
of 291 charts (52%) carry at least one move that needs a shape over the chart at data
coordinates; 99 of 192 tables (52%) carry at least one cell-level move the table spec could
not express (merged spanners, italic rows, input cells, semantic cell colour, a cell box or
callout, two emphasis styles); 227 of 578 pages (39%) carry at least one such move. Known
failure mode: a system that draws native charts but cannot place a shape at a data
coordinate leaves the model unable to annotate; generated exhibits then lack the reference's
moves, and a blind rater notices (section 23.1).

Known failure mode (found in the code of that earlier build; three independent causes, any
one of which is enough to block placement on a native chart):
1. The solver refused any two element boxes that shared area, and the judge gated overlap,
   so no element could ever sit on a chart or a table.
2. No manual plot layout was written, so each renderer placed the inner plot rectangle
   itself after axis labels and legend, and the EMU position of a value was unknown even
   with a fixed axis range (auto-scaled axes made it worse).
3. The shape vocabulary had no arrowheads, braces, callout shapes, elbow connectors or
   rotated lines, so the marks could not be drawn.

Requirements:

- **Anchors.** An `annotation` element is anchored to a host element and to positions in
  the host's own data:
  - charts: a point `{category, series}`; a category span; a value on the value axis (a
    horizontal or vertical line); a region (categories x value range); a date or category
    on a time axis (event marker); an XY coordinate;
  - tables: a cell, a cell range, a row, a column, a header group;
  - text: a paragraph.
- **Kinds**: named shorthands for measured moves (outline box or ellipse around a mark,
  cell or region; filled band or zone shading; reference line with label, solid or dashed;
  event marker; arrow or pointer with arrowheads from a label to an anchor; elbow
  connector; bracket or brace over a span with a label; callout box with leader line;
  number or letter badge keyed to text, holding as many lines as its measured block; inset
  table or stats box; logo or image at a category position; connector or zoom lines),
  beside one primitive `mark`: any OOXML preset by name, or a line with any OOXML line
  ends, with optional words beside it (inside it only on presets whose body the contrast
  gate can bound). A mark's shape may be taken from a mark the reference's own file draws
  (`reference_mark`). The shorthands are conveniences, not the set of marks allowed. Roles
  only, like everything else.
- **Hosts.** Any element of the page can host a mark: data positions on charts and tables
  as below, or fractions of the element's solved box (`{"box": [x0, y0, x1, y1]}`) on any
  other element. A footnote marker is any 1 to 3 character token that stands as its own
  token and starts the note's paragraph.
- **Fixed plot rectangle.** Every chart that hosts an annotation, or that has data rows or
  a table aligned under its categories, is written with
  `c:plotArea/c:layout/c:manualLayout`, `c:layoutTarget val="inner"`, `c:xMode` and
  `c:yMode` set to `edge`, and x, y, w, h as fractions of the chart frame. The spec takes a
  `plot_box` (fractions, or an inset in spacing roles). Every axis an annotation refers to
  must declare `min`, `max` and `crossBetween`; an annotation on an auto-scaled axis is
  refused by name.
- **Coordinates computed, never estimated.** With chart frame (X, Y, W, H) in EMU and inner
  plot fractions (px, py, pw, ph):
  - value v on a vertical value axis: `y = Y + H * (py + ph * (max - v) / (max - min))`;
    the mirror form for horizontal bars or a reversed axis;
  - category i of n with `crossBetween="between"` (bars): centre at
    `X + W * (px + pw * (i + 0.5) / n)`; with `midCat` (lines):
    `X + W * (px + pw * i / (n - 1))`;
  - bar width for k clustered series with gap width g and overlap o (percent):
    `slot = pw * W / n`, `bar = slot / (k - (k - 1) * o / 100 + g / 100)`; a stacked or
    single series: `bar = slot / (1 + g / 100)`;
  - XY scatter: both axes linear on the same rectangle;
  - table cells: from the solver's fitted column widths and row heights, which PowerPoint
    realises as written (section 14.2).
  These formulas are derived from the OOXML layout model and are unmeasured until the
  verification below passes.
- **Overlay layer in the page grammar.** Annotations are resolved after the host's box is
  solved. They are exempt from the overlap check against their own host only, and still
  checked against every other element, every data and axis label, other annotations and the
  page edge. The solver reserves room for labels placed outside the plot.
- **Native gaps beside the overlay** (sections 15.1, 15.2): combo plots, so reference lines
  and dot overlays can be real series on a bar chart's axes; series dash and hatch for
  forecasts; series lines for stack connectors; a trendline for regressions; per-cell table
  styling. Where a move can be native, prefer native (it stays editable and moves with the
  data).
- **Verification before reliance** (unmeasured; the first experiment to run):
  1. Build one test page per chart family (column, clustered column, stacked column,
     horizontal bar with reversed axis, line, XY scatter) with a known manual layout, fixed
     axes and one distinctively coloured marker per data point.
  2. Render at a known width and convert predicted EMU to pixels
     (`emu * width_px / page_width_emu`).
  3. Locate bar tops, bar edges and marker centres by scanning for each series' fill
     colour, and compare with the prediction. A tolerance of 1.5 px at 1600 px has been
     proposed; it is unmeasured, and the tolerance actually achieved is to be stated.
  4. Extract the rendered PDF with `pdftotext -bbox` and check that no annotation
     intersects a data label or tick label.
  5. Measure once in PowerPoint. Whether PowerPoint honours an inner manual layout the same
     way LibreOffice does is unmeasured, and the claim must not ship before it is measured.
  6. Where a renderer diverges, the fallback is to draw the whole exhibit as a component
     from shapes (as a football-field component does): exact coordinates, but the chart is
     no longer a native, data-editable chart. The build reports which exhibits took the
     fallback.
- **Collision contract.** An annotation may overlap only its anchor; it must not cover
  data labels, axis labels, other annotations or text outside the exhibit.
- Annotations are scored by the contrast gate like any text.
- The model decides whether and what to annotate. The skill supplies the corpus evidence
  (Appendix A, counts of what coders saw, not a set to choose from), the reference's own habits
  (`exhibit_habits`) and the reasoning questions (Appendix B). A mark with no label and no
  explanation is drawn and warned, with the reference's own count of such marks beside it, and
  the report answers it; an explanation that names something not on the page is refused. Nothing annotates automatically, and no field is offered to the
  model before its placement is implemented and verified (section 3.4).

### 15.4 Diagrams

Diagrams are built from the page grammar or components; nothing limits which. The corpus
recorded, for instance, process flows, timelines and Gantts, matrices (with a written
reading rule and a legend for cell states), spectra (options on a continuum with a pointer
to the recommended one), org-style trees, logo walls and tombstone grids (diagrams and
processes: 62 of 601 exhibits, Appendix A.5).
Known failure mode (measured once): a Gantt built from a grid of filled text boxes counted
every cell as an element and read "above" the density band. Element counting must
understand that a diagram is one exhibit.

### 15.5 Components

A component is a function `expand(data, box, guide) -> subtree` in the page grammar,
roles only, proportions as weights from the data, fixed heights as spacing steps. Every
declared variant is reachable through `data["variant"]`; with none asked for, expand picks
one by what the box can hold and the report says which and why. Text is measured through
an API, never estimated (`text_width`, `line_pitch`, `paragraph_spacing`, `fit_epsilon`
exposed to components from the solver's own ruler), and a component's roles and constants
are open through its data, each choice and default reported.

Components are worked examples of drawing exhibits the template never contained, in the
reference's look: a component reads only the guide's roles, so the same football field takes each
reference's roles. They are one way to draw an exhibit, not the way: read one, fork it per
reference, or draw the exhibit from the page grammar.

Contract and admission:
- A schema for its data, a size domain, and four test boxes: three shown and one held out
  with different data.
- Check: determinism (expand twice in separate interpreters under different hash seeds;
  any difference in list order fails and names the path); all four boxes solve with no
  violation; ids that must stay on one line never wrap (`single_line_ids`); contrast
  passes; the package validates; and geometry tested against the master's and layout's
  own shapes (known failure mode, measured: a check passed while the master's top rule
  struck through a football-field bar).
- Admission is bound to the guide it was checked with (hash). Measured once: a component
  admitted on one reference overflowed on another whose 12pt floor left no headroom.
- The model writes new components when nothing draws what a page needs; the build reports
  a component admitted against a different guide.
- Feasibility shown (measured): football field, title block, bullet stack and KPI row were
  each built and admitted under this contract.

---

## 16. Emitting the PowerPoint file

### 16.1 Rules

- Write on the chosen company template, the reference's masters, or (PDF only) the
  constructed blank.
- Every value resolved from the guide through the solver's resolved entries; nothing
  inferred in the emitter; no ink swaps, no colour picks.
- Content bound to a placeholder is written into that placeholder on the named layout.
- `word_wrap` set explicitly true (measured: python-pptx's default centres text in
  LibreOffice).
- Body properties written fully (insets, anchor, autofit off).
- Never write negative `spcPts` (measured: LibreOffice then draws nothing); a master that
  spaces by percent (`spcPct`) is converted to points at the boundary.
- Measured once: a schema-invalid spacing value blanked sixteen bullets on a page that
  validated and judged clean. Validate against the schema, and read the render back.
- Effect-free shapes (no inherited shadow).
- Bullet glyph with its bullet font.
- Page number as a field where the layout carries the field; never a typed number.

### 16.2 Package hygiene

Unique slide ids; relationship targets present; one layout per slide and one master per
layout; content types complete (including the potx-to-pptx switch, section 11.2); shapes
inside the page; charts parse. Template parts carried over intact.

### 16.3 Speaker notes

State that figures are illustrative when they are; carry sources.

### 16.4 Determinism

Same inputs produce byte-identical packages apart from timestamps.

### 16.5 Origin tag

Every generated slide carries a tag (`p:custDataLst` tags part, name the skill's name,
value `generated`). Measured: such tags survive a PowerPoint save. Extraction, digest and
gallery skip tagged slides by default, so an extended deck, or a past deck that contains
generated pages, never teaches the skill its own output.

---

## 17. Gates

All gates report per page, located, before figures. A refusal makes the page unfittable
with a reason; a warning never refuses.

### 17.1 Package validation

Section 16.2, plus `--render` mode: render, extract text with pdftotext, and name every
paragraph that did not draw. Known false positive (measured once): wrapped names reported
as not drawn when visible; match normalised text.

### 17.2 Renderer-divergence check

On the saved package: shared table edges declared differently on two cells; strokes under
0.5pt not declared by the guide; gradients; a chart without `c:varyColors`; a run below its
role's floor; a typed page number where the layout has the field (all measured hazards).

### 17.3 Fit read-back (section 14.4)

### 17.4 Contrast

- Every text run, every table row class, every chart text (data labels per series and per
  point, axis labels, legend), every annotation label and every chrome text, scored WCAG
  2.2 against the fill actually behind it: the element's own fill, else the nearest
  enclosing filled region, else `color.surface`; for a chart label inside a mark, the mark's
  fill; outside it, the plot fill or the page; both when the position is open.
- Below 3.0:1 refuses; below AA (4.5:1, or 3.0:1 at 18pt or 14pt bold) warns.
- Reference precedent: a colour pair the reference itself uses at that size or smaller is allowed
  and reported as precedent. Without it, a reference can never use its own signature colour:
  measured once, one consulting reference's title green on white reads 2.51:1.
- Undecidable cases (text over images; fills left to the renderer) are listed, not passed.
- The fix is always a role change by the model, never an automatic ink swap.

### 17.5 Tie-outs

Totals rows: each numeric column's body sum against the totals cell at the cell's own
decimals ($ , % x stripped; parentheses negative); statistic rows skipped; n.a. cells skip
the column and are named. Chart bridges: as in 15.1.

### 17.6 Register and density

Per page counts by kind, decoration count and container ratio against the reference's bands;
words, elements and covered area against density bands. Each verdict is below, in band,
above, or NO EVIDENCE (section 3.8). A diagram counts as one exhibit.

### 17.7 Repetition

Arrangement similarity of consecutive pages over CONTENT regions only (exclude chrome and
elements identical on every page). Known failure mode (measured on two firms): a metric
dominated by the frame scored any two pages about 0.5 before their content was compared.
Flag runs longer than the reference's `consecutive_max`.

### 17.8 Position drift

An element present on several pages (by shared id) whose position moves by more than one
spacing step is reported.

### 17.9 Source line

A page with a table or chart and no source or footnote paragraph is reported, located,
with the reference's count beside it (for instance "the reference sources 41 of 44 data pages;
this page has none"), as a warning answered in the report. It never refuses: citing a source is never
wrong, and the line between "as a rule" and "sometimes" was never measured. Measured: source lines are common but not universal on real data pages (two
strategy-consulting coder groups recorded them on 23 of 111 and 27 of 121 pages; the
native-pptx bank decks on 2 of 33 data exhibits; a market chart book on 30 of 30), so a
universal refusal is stricter than many firms (section 23.5). Any source line written
names the sources actually used (section 24).

### 17.10 Leakage

Every text run of the generated deck is compared against the text of the past decks used
as evidence. A name, figure or phrase that appears in a past deck and not in the user's
brief, data or the reference's chrome and standard wording is reported, located, as possible
carry-over of client content (section 7.4); the model removes it or the user confirms it.
Image assets are checked the same way by hash. The matching rule and its thresholds are
unmeasured; build them against the evaluation scenarios and record their false positives.

### 17.11 Layout conformance

Each slide uses the layout its spec named; no placeholder shows prompt text; no
placeholder geometry differs from its layout unless the spec declared the override, which
is reported beside the reference's past use of that layout.

---

## 18. Rendering and the self-critique loop

### 18.1 What the loop is

After each build the model looks at every rendered page at full size and writes located
findings as a reviewer would: element id, what is wrong, the change (for example
"takeaway: competes with the table; drop the fill, keep the rule"). Never a score. Then it
fixes the spec and rebuilds.

### 18.2 What it looks for (in order)

Text cut at a box edge; elements sharing area; labels wrapping mid-word; source line
touching footer furniture; uneven gaps; a title that drifts between pages of one kind;
inconsistent chart text styling across charts; a figure split from its unit; placeholder
text; and then design: Is the message findable in two seconds? Is the exhibit annotated
where the claim lives? Would a managing director mark this up, and what would they write?
Does it look like the company's best pages, side by side? What did a blind rater notice on
generated pages (low chart and layout variety, missing logos, claim titles where the
reference titles by topic, an unlabelled red circle)? The other usual suspicions are questions put against the
reference's own pages and counts, not a checklist: a card grid for content that is not a
comparison, big numbers with no base or population (8 of 578 corpus pages carry big
numbers or a KPI panel), corners (the reference's measured `shape_language` radii), centred
text, three of everything, uniform spacing, one composition repeated where the pages are
not siblings.

### 18.3 Caps and keep-best

The loop is capped. Measured on an earlier build: fresh agents allowed 8 builds per 5-page
section used 4 to 7. Keep the best build by gate status and critique, not the last.
Score-chasing loops are forbidden.

### 18.4 A second reviewer

Optionally, a separate reviewer call on a different model family than the designer
reviews renders against the company's pages and returns located patches (never rules on
measurable geometry; validators own that). Measured: 10 of 10 findings located on real
element ids at about 9 to 11 seconds per review; whether findings steer the next revision
was not measured, and the reviewer's agreement with humans was never calibrated. Treat as
unmeasured until calibrated against blind-round ratings.

### 18.5 Renderer fidelity

Renders are LibreOffice. Measured differences: text (solved by writing measured breaks),
table edges and thin strokes (section 17.2), chart label wrapping. Open the final deck in
PowerPoint at least once per release; a release verified only in LibreOffice is a known
gap. Where a Windows or macOS runner with PowerPoint is available, render there too.

---

## 19. The style judge, and its limits

### 19.1 What it is

A fingerprint per page of style distributions, compared with a distance:
families, size histogram, size ladder, title size, bold ratio, text colours, fills,
alignments, element kinds, background, margins, coverage, element count, plus two layout
gates: overlap (pairwise intersection of content shapes over their area) and overflow
(paragraphs re-wrapped with the solver's ruler against their boxes). Component weights are
fitted from each component's 1-nearest-neighbour accuracy above chance on held-out pages.

### 19.2 Verdict

Filed under the reference when: nearest to the reference among a panel of other firms; inside the
reference's own spread (90th percentile of leave-one-out distances of the reference's own pages);
layout clean (overlap and overflow below 0.2 of their span); every page fit and the
package valid. Decks inside the reference's own spread are reported as the same style, not as
rivals. The panel is fixed (not chosen by the model). For a company, the panel includes the
company's other templates as separate firms, so a pitch book is not filed under the board
template.

### 19.3 Calibration (measured)

157 of 171 held-out slides over 8 firms filed correctly with fitted weights, 132 with
equal weights (binomial chance bound 30). Copying a master verbatim is flagged off-style.
Five deliberately wrecked decks in a reference's clothes once filed at 0.013 to 0.192; adding
the overlap and overflow gates made all five fail. On an earlier build, the best generated
sections scored 0.059 to 0.175 and were filed in five of six firms.

### 19.4 Limits (measured)

- The judge does not track human perception of real versus generated. In a blind round on
  an earlier build, Reference A (0.085) and Reference B (0.068) were filed close to their
  references, yet the rater caught every generated page in both; Reference F (0.584, not filed,
  because the judge read a scan's OCR layer) fooled the rater 4 of 5 times; Reference E (0.059)
  fooled 3 of 5. Six firms and one rater are too few for a correlation, but "filed"
  clearly does not mean "passes as real". Do not present judge scores as quality.
- It cannot see content craft: title register, annotation, exhibit choice, variety,
  figures. These need the critique loop and the blind round.
- Raster references must be fingerprinted from raster measurements, or the judge must say
  it cannot judge (never a confident wrong number).
- Overflow measured on the file must use the same line pitch and spacing rules as the
  solver. Known failure mode (measured once): judge and solver disagreed and the judge's
  overflow named no shape; the judge was right.

---

## 20. Editing an existing deck

- Commands: text per slide (tables as rows, cells joined with spaces; known failure mode:
  a text dump that ran cell text together), layouts and placeholders with boxes, template
  with kept slides, duplicate, delete, clean, validate.
- Existing slides are the reference; they are not re-solved or restyled. New pages are built
  on the template that keeps them, using its layouts. Structure first (order), content
  second.
- Extract the style from the deck itself (skipping tagged generated slides), combined with
  the company's guide for its template when the deck's template is in the library.
- The leakage gate applies to added pages as to new decks.

---

## 21. Evaluation program

Every proof is an end-to-end run with its output recorded beside the claim it supports.
Evaluations are scenario files plus a human round. Company decks are confidential, so
development uses a public corpus that stands in for a company's library (Appendix D); a
deployment re-runs the same scenarios on the company's own material.

### 21.1 Scenario evaluations (build these first)

At least these, each a template library and past decks (or another reference) plus a brief
plus data plus expected behaviours:
1. The company's standard pitch book template with past pitch books: a valuation section
   with comps, football field, precedents, pro forma bridge, process timeline.
2. The same company's financing deck type: alternatives comparison, credit impact,
   dilution, maturity profile.
3. A consulting firm's template whose past decks use navy pages and serif titles: a
   governance diagnostic with benchmarks, skills gap, operating model, roadmap.
4. A consulting firm whose signature colour reads below 3:1 on white: budget impact with
   scenarios, sensitivity, recovery path.
5. A company whose older past decks exist only as vector PDF with a title band and heavy
   rule: cost baseline, spans and layers, procurement, implementation plan, savings bridge.
6. A company whose only past board book is a scanned PDF (raster only, logos, DRAFT
   stamp): credentials, league table, deal list, team, buyer universe.
7. A template library with several templates (for example pitch book, board deck,
   internal): the brief implies one; the agent must pick it and the right layout per page.
8. A template with no past decks: expected low-confidence habit completion, flagged.
9. A template plus brand guidelines that conflict with it on at least one value: expected
   conflict reported, not resolved silently.
10. Extend an existing company deck with three pages in its own style.
11. Confidentiality: any scenario above run with network access monitored; and a past-deck
    library seeded with distinctive client names and figures absent from the brief.
12. No reference at all: the model chooses the whole look; every hard limit holds and every
    comparison with a reference reads "no reference".

Expected behaviours are checkable statements, and pass or fail only on the measurable
half: zero gate failures; every warning answered in the report; every stated claim
computes from the data; figures tie; the subject can be found; template and layouts
stated with reasons; logos present where the reference shows them; conflicts and
low-confidence habits reported; zero network calls by scripts; zero seeded client strings
in the output. Title register and length against the reference's distribution, where the
reference annotates, and composition variety against the reference's are diagnostics reported
beside the result; the blind round (section 21.2) is the judge of taste.

### 21.2 The blind round (primary success metric)

- Per reference, 5 real pages from the reference deck (or the company's best decks) and 5
  generated pages, normalised to the same pixel size, format and encoding (re-encode all to
  one format; measured: real scanned pages were otherwise twice the file size of generated
  ones), file names and ids hashed, order mixed within each reference.
- Remove visible non-design tells where possible and record those that remain (measured:
  real pages of one consulting deck carried a gradient at the edges; real pages of a
  scanned bank deck carried scan texture).
- Raters are, by preference, the company's own senior bankers or consultants. Real pages
  shown to raters are the company's own and stay inside the company (section 7).
- The rater guesses real or generated and rates quality 1 to 5 (1 would not send, 3 usable
  with edits, 5 client-ready), with an optional note.
- Score: accuracy per reference and overall with the binomial tail probability; quality means
  real vs generated; which generated pages fooled the rater; notes.
- Baseline measured on an earlier build (one rater familiar with the work; 6 public firms;
  60 pages):

| Reference | Type | Correct of 10 | Generated called real | Real quality | Generated quality |
|---|---|---|---|---|---|
| A | native-pptx bank pitch book | 8 | 0 of 5 | 3.6 | 2.4 |
| B | native-pptx bank pitch book (same master as A) | 9 | 0 of 5 | 3.8 | 2.2 |
| C | vector-PDF strategy consulting | 8 | 1 of 5 | 2.6 | 2.6 |
| D | vector-PDF strategy consulting | 8 | 0 of 5 | 4.0 | 3.2 |
| E | vector-PDF strategy consulting | 6 | 3 of 5 | 3.0 | 3.4 |
| F | scanned-PDF bank board deck | 6 | 4 of 5 | 4.2 | 3.8 |

  Overall 45 of 60 (chance 30, P(X >= 45) = 0.00007); quality real 3.53, generated 2.93;
  pages guessed real were rated 3.77, guessed generated 2.66. Rater notes: "Chart variety
  and layout variety in generated slides are low. Generally the same patterns with
  different colours"; "The choice of charts here actually match the data being represented
  and is well laid out" (on a real Reference D page rated 5); "Logos. Generated slides have
  none". Judge scores of the same generated sections: A 0.085 filed; B 0.068 filed
  (repetition flagged); C 0.131 filed; D 0.175 filed; E 0.059 filed; F 0.584 not filed
  (judge read the scan's OCR layer).
- Use more than one rater when possible; record rater background.

### 21.3 Fresh-agent runs

For each scenario, a fresh agent with only the skill builds the section, with a build cap,
and returns: what it did, what it could not do, and a friction list (what, repro,
severity). Friction is the primary input for the next skill revision; every work-around an
agent performs by hand is a friction item. Measured on an earlier build: six such runs plus
an assembler and a regression run produced 71 friction items (fit truth 8, chrome 6, PDF
intake 10, judge and gates 8, spec and emit 10, plus minor documentation and ergonomics
items); on reproduction the large majority were real (all 8 items in the first scope taken
up reproduced).

### 21.4 Model matrix

Run the scenarios on each model tier the skill supports. Record per tier: gate failures,
builds used, critique findings, blind-round results.

### 21.5 Regression evidence

Keep re-runnable scripts for every measured claim (judge calibration, ruler agreement,
round trip, raster read-back, triage, template inventory, leakage gate) and re-run them
before every release. Documents must cite the run that produced each number. Known failure
mode (measured): documentation figures go stale; one re-run found the same calibration
quoted as 147 of 161 and as 157 of 171, and one section's judge score quoted as 0.085,
0.086 and 0.079. Re-measurement scripts also caught four wrong documented claims.

---

## 22. Evidence: what has been measured

### 22.1 About the instruments

Collected in sections 8, 10, 14 to 19 and Appendix C, each with its measurement.

### 22.2 About the model's behaviour

- With chart and table design handed to the model, fresh agents composed exhibits code
  never anticipated: a horizontal bridge, a Gantt from a stacked bar with an invisible
  offset series, a regression scatter, a football field as a stacked bar; all six firms
  produced 5-page sections; five of six were filed by the judge (measured).
- Fresh agents spent 4 to 7 builds per section of 5 pages; each read every render after
  every build (measured).
- Every fresh agent wrote a generator script that computed every stated figure and asserted
  the arithmetic (measured; emergent, not instructed in detail). Keep and encourage it.
- Agents worked around skill defects by hand (drawing the title band as page content
  because chrome buried it; measuring sizes from a 220 dpi render because the raster tool
  reported the wrong dpi) and reported them (measured). Work-arounds are friction items.
- Measured: single-attempt acceptance of a design model's page specs rose from 0.021 to
  0.274 on one reference and from 0.253 to 0.432 on another, against a 0.80 target, as schema
  and guide gaps were fixed; most refusals were schema and guide gaps, not model craft. Fix
  the pipeline before blaming the model.
- A "reasoning" field in the structured output had no measured win on correctness across
  three models (20 tasks x 5 repetitions); design quality was not measured. Do not add one
  without a design-quality measurement.

### 22.3 About human pages (corpus evidence)

Six coder groups looked at sampled content pages across the development corpus (Appendix
D) and coded all of them: investment-bank decks (11 decks, 231 pages), strategy-consulting
decks from three firms (12 decks, 317 pages) and a dense market chart book (30 pages); 578
pages and 601 exhibits in all. Each page record holds composition, title register and
length, text hierarchy, exhibits with type, data shape, message, every annotation move and
its anchor, emphasis devices, craft details, density, and the page-order sequences. The
full measured evidence, with its caveats (one coder per group, a keyword taxonomy,
counts good to about plus or minus 2 to 3, 8 of 24 decks sampled at a stride), is Appendix
A. The same coding applied to a company's past decks produces that company's habits
(section 6.6). The headline findings:

1. **Most pages are not charts.** 346 of 578 pages (60%) carry no data chart (bank 135 of
   231, consulting 210 of 317, chart book 1 of 30). Tables (192), diagrams and processes
   (62), structured text, image walls and big numbers make up 310 of 601 exhibits; in bank
   decks tables outnumber charts 117 to 109. Page design is mainly composition, text and
   tables. The skill's craft (exhibit choice, annotation, emphasis, density, variety) must
   cover tables, diagrams and structured text as fully as charts.
2. **Titles are deck-specific, and banks use topics.** Topic phrases on 223 of 231 bank
   pages (2 claims) and 30 of 30 chart-book pages, with a median of 4 words; claim
   sentences on 197 of 317 consulting pages (62%, median 15 words, 8 to 22, usually two
   lines), with topic titles on that deck type's executive summaries, appendices,
   trackers and reference pages. When the title is a topic, the claim lives elsewhere on
   109 of 372 pages: a takeaway band, a lead-in bullet ending in a colon, a kicker, a
   sidebar, the labels of numbered rows, a units line, or memo prose; on the rest no claim
   is stated, because the page is reference.
3. **Annotation is near-universal on data exhibits, and its moves are deck-specific.**
   7 of 291 charts carry no annotation (bank 0 of 109, consulting 4 of 135, chart book 3 of
   47). Bank decks annotate at least as much as consulting decks and annotate tables more:
   61 against 41 exhibits carry a circled or boxed mark, and 50 of the 105 boxes overall sit
   on tables. Commonest moves overall: data labels on all marks 131, circled or boxed mark
   105, highlight one item and mute the rest 90, footnote markers 90, callout with arrow or
   leader 77, reference or benchmark line 77. CAGR arrows: 0 in bank decks, 1 in consulting
   (growth goes in a CAGR column, inset table or oval). About one chart in four relies on
   labels alone, with no move that points at the message.
4. **Moves often go with the data's shape, as tendencies.** For instance, rankings were
   sorted on 15 of 21 horizontal bars; comps tables emphasised the median row on 12 of 15;
   projection tables shaded total rows on 27 of 42; sensitivity grids boxed a cell or
   region on 17 of 29; football fields drew a reference line at the decision value on 8
   of 14 (A.7). These are evidence for the question "what must the reader see here?", and
   the reference's own pages come first.
5. **The annotation sits where the claim lives.** Examples: a box around only the scenario
   region of a sensitivity grid that the argument depends on; boxes on shortfall years,
   with no box on the one scenario that is the exception the claim names; the subject in one
   colour and peers in another, with one company order held across four panels so the
   reader can find the subject; a single current-price line through a football field, with
   the judgement the chart cannot show put in a bullet; the bars that sum to the claim
   coloured.
6. **Colour is restrained.** One emphasis colour or a single hue is the norm; categorical
   colour is kept for categorical series; semantic red and green appear on only 9 pages. In
   the native-pptx bank decks series were two tints of one navy, red meant only "look
   here", and there were no icons, check marks or big numbers.
7. **Variety is high, and repeats are deliberate.** Median composition change between
   consecutive pages is 0.69 over 23 decks on a coarse 10-family taxonomy (bank 0.645,
   consulting 0.765); coders' finer taxonomies give 0.83 to 0.90 on the native-pptx bank
   decks and up to 0.93 to 1.00 on one consulting group. Exhibit types change more often
   than compositions (median exhibit-set change 0.77 bank, 0.85 consulting, 0.97 chart
   book). Every long run (up to 7 pages) is a deliberate sibling template for comparison;
   no coder found an accidental run of sameness.
8. **Text adds what the exhibit cannot.** Assumptions, caveats, causes, history, the
   so-what, the derived number (for example a percentage fall turned into the implied
   effect on the population actually reached); it rarely repeats the exhibit (restating the
   title: 40 of 264 bank exhibits, 8 of 52 chart-book exhibits).
9. **Craft details are many and small.** Units lines (123 pages; on every chart-book page),
   footnotes (195), status or caveat tags (122), $ on first and total rows only, x on
   multiples, parentheses for negatives, NM and NA written out, the subject row set apart,
   continuation marks, logos as category labels. Source lines are common but not universal:
   two consulting coder groups recorded them on only 23 of 111 and 27 of 121 pages.
10. **Exhibits in real bank decks are often pictures.** 27 of 33 data exhibits in the
    native-pptx bank decks were pasted pictures of spreadsheet output with annotation shapes
    laid on top at absolute offsets. Generating native charts is still right (editable), but
    annotation must be placeable over them precisely.
11. **Many of the recorded moves are a shape at a data position.** Measured against the chart,
    table and page-grammar spec of an earlier build of this kind: 150 of 291 charts (52%)
    carry at least one move that needs a shape over the chart at data coordinates, 99 of 192
    tables (52%) carry at least one cell-level move the table spec could not express, and
    227 of 578 pages (39%) carry at least one such move (section 15.3).
12. **Several generic design instructions contradict the evidence** (claim titles always,
    no labels on every mark, no equal panels, one emphasised row, one fill, a universal
    source-line refusal, and others); each is a known failure mode in section 23.5.

### 22.4 The external page library

The evidence pass also curated about 40 of the coded pages (15 bank, 21 consulting, 4 chart
book; 15 of them with a table, matrix, diagram or structured text as the main exhibit),
tagged as section 10.4 describes, each with why it is instructive and the questions a
designer evidently asked to produce it. This is the external starter set of the page
library, ranked below any company's own pages.

---

## 23. Known failure modes to design against

Each item has been observed in a working system of this kind. Treat every one as a
requirement.

### 23.1 Why a human caught generated pages

From a blind round on an earlier build, the rater's notes and the corpus evidence (inferred
causes, each consistent with the measurements; not individually tested):

| Cause | Requirement |
|---|---|
| Title register: computed claim titles in firms whose titles are short topic phrases (section 22.3 item 1), because a doctrine required claims | Titles reported against the reference's measured register and length, as warnings to answer; a title that needs more lines than its band holds does not fit (sections 3.2, 9.2 `titles`, 12.1, 13.3) |
| Low variety: "same patterns with different colours"; no section variety plan; a repetition metric dominated by page furniture | Variety plan whose repeats are declared or varied, and a content-only repetition report (sections 12.3, 17.7) |
| Thin annotation: the reference's moves (outline boxes on the claim region, subject highlight, reference lines, median rows) rarely present, because shapes could not be placed on charts and the reference's habits were never given | Data-anchored annotation layer and `exhibit_habits` from past decks (sections 15.3, 10.3) |
| Exhibit-to-data fit: nothing asked the model to justify the chart by the data's shape and message; the rater praised real pages whose chart matched the data | Reasoning questions per exhibit (Appendix B) and the page plan (section 12.1) |
| Missing furniture: no logos; placeholder logo boxes | Logos carried and placed (sections 11.4, 11.6) |
| Renderer and font tells: all generated pages were LibreOffice renders; some used stand-in fonts | Company fonts installed; PowerPoint render where available; normalised blind-round images (sections 8.2, 18.5, 21.2) |

Firms that fooled the rater (E and F) had dense, table-heavy, conservative pages where the
generated content matched the reference's restrained annotation.

### 23.2 Mechanical failure modes

Blockers:
- Solving at a reduced scale but emitting at full size; text then overlaps while every gate
  passes. Requirement: one resolved entry per element, consumed by the emitter; fit
  read-back (sections 14.2, 14.4).
- Chrome bands anchored to the full page reserving the whole page. Requirement: reserve
  only occupied zones (section 11.4).
- A judge fingerprinting scans from their OCR layer. Requirement: raster fingerprints or
  "cannot judge" (section 19.4).

Majors, each with its section: mid-word wraps reported as fit (14.1); a table in a stretch
row never checked against its height (14.2); measurement font differing from render font
(9.2, 14.1); chrome drawn in the wrong z-order (11.4); chrome text black on navy and
unscored (11.4, 17.4); rotated text misread (8.1); title role bound to large numerals by
vote (9.4); PDF density bands of zero (3.8); PDF import producing empty paragraphs (11.7);
a gallery refusing PDFs (10.2); contrast refusing the reference's own colours (17.4); emphasis
keys dropped silently (13.1); header and cell roles ignored by the emitter (3.10); XY
scatter crash and first scatter series not drawn (15.1); undocumented depth limit (13.2);
raster completion unable to add roles (9.6); no reference line possible on bar charts and
no per-table overrides (15.1, 15.2, 15.3); no shape placeable at a data coordinate on a
native chart, because overlap was refused, no manual plot layout was written and the shape
vocabulary had no arrowheads or braces (15.3); one emphasis style per table and no
per-cell or per-row styling, so comps tables could not mark both median and subject
(15.2).

### 23.3 Requirements and failure modes by part

What has been shown feasible, and the failure modes each part must be designed against:

| Part | Requirement | Feasibility and known failure modes |
|---|---|---|
| OOXML and PDF reader | Inheritance-resolved runs, shapes, tables, charts; PDF page triage; origin tags; corner radii from the file | Shown on all corpus decks (measured). Failure modes: rotated PDF text, title binding by vote (8.1, 9.4) |
| Template inventory | Masters, layouts, placeholders, usage from past decks, version matching (6.3) | Unmeasured; build and verify first on the development corpus's shared-master decks (Appendix D) |
| Style extractor | Draft guide with provenance and open list; levels, roles, colours, spacing, composition, chrome, motifs, register and density bands, floors, titles, habits | Core values agreed across two independent extractors (9.4). Failure modes: zero density bands for PDFs, rotated text, title binding, 18.6 minutes on 205 pages with no progress |
| Completion | Applies the model's answers; refuses answers to non-open, observed or stated addresses; core closure; partial mode | Failure modes: crash on null; a documented form rejected (9.6) |
| Raster instrument | Palette, ink, chrome mask, margins, line pitch from scans | Read-back within stated tolerances on a rendered deck (8.3). Failure modes: weak line pitch on real scans; dpi misreport |
| Renderer wrapper | LibreOffice to PNG, contact sheet, font report with alias and tofu coverage | Failure mode: no font report for PDF references |
| Gallery | Crops, clustering, exemplars, skeletons, manifest, `pick --intent` | Crop counts agreed across two independent implementations on three decks (measured). Failure modes: refusing PDFs; weak word-overlap ranking |
| Solver and ruler | Flex and grid layout, placeholders as fixed boxes, measured wrap, table fitter, scale descent, capacity | Two independent implementations agreed exactly on 383 boxes (measured). Failure modes: the height rules of 14.2 |
| Emitter | Slides on the template's layouts; text, tables, native charts from a full spec; chrome; origin tags; varyColors | Failure modes: unfitted sizes at scale below 1; chrome z-order, ink and reserved zones; theme shadows; header and cell roles ignored |
| Build orchestrator and gates | Solve, emit, validate, render, judge; contrast, register, repetition, tie-outs, source line, density, drift, chart defaults, leakage, layout conformance | End to end shown (measured). Failure modes: blind spots for chrome text, frame-dominated repetition, zero bands |
| Component system | Contract, determinism check, held-out admission, measurement API | Four components admitted (15.5). Failure mode: check blind to master shapes |
| Page importer | Past-deck page to layout, roles and weights for the round trip | 0.057 on a native-pptx deck (11.7). Failure mode: empty paragraphs on PDFs |
| Style judge | Fingerprint components, fitted weights, reference spread, panel, layout gates | Calibrated 157 of 171 (19.3). Failure modes: does not track human perception; reads OCR on scans |
| Package tools | text, layouts, template, blank, duplicate, delete, clean, validate (with render and renderer-divergence modes) | Failure mode: text dump joining cell text without spaces (20) |
| Design doctrine | Questions plus measured tendencies, with the reference's measured habits shown as the strongest evidence and departures answered in the report; chart recipes | Failure mode: doctrine (claim titles) contradicting the firms (3.2). Chart recipes were useful (measured) |
| Examples | Real pages from the company and the library, tagged with page size | Failure mode: specimens composed for 16:9; on a 4:3 reference only 1 of 14 fit as written (the specimens, since removed) |
| Re-measurement scripts | Re-run every documented number before release (21.5) | Caught four wrong documented claims (measured) |

### 23.4 Capabilities that close the observed gap

1. **Context-first architecture**: the company's template inventory, past-deck habits,
   exhibit digest, title statistics and page library, all as data the model reads (sections
   6, 9.2, 10.3, 10.4).
2. **Reasoning instructions** (Appendix B) instead of doctrine rules; doctrine written as
   questions plus measured tendencies, with the reference's measured statistics shown beside
   every choice and departures answered in the report.
3. **Annotation layer** with data-anchored placement on native charts and tables: a fixed
   inner plot rectangle, coordinates computed from the axis scale, an overlay layer exempt
   from the overlap check only against its host, marks in any OOXML preset or line end on
   any host, and cell-level
   table styling; verified against renders in both renderers (section 15.3).
4. **Template and layout choice** by the model from the inventory and past-deck usage
   (sections 6.4, 6.5).
5. **Section planning with an explicit variety plan** whose repeats are declared or
   varied, and a content-only repetition report (sections 12.3, 17.7).
6. **Self-critique loop** on renders with located findings and keep-best (section 18),
   optionally a calibrated second reviewer.
7. **Chrome done properly**: z-order, rotation, inks, contrast, logos extracted and placed,
   reserved zones only where chrome is (section 11).
8. **PDF parity**: rotated text, title binding by position, density from words that exist,
   import and gallery for PDFs, raster roles addable (sections 8, 9, 10, 11.7).
9. **One source of truth** for every resolved value from guide to solver to emitter to
   gates to judge (section 3.10).
10. **Instruments that say "no evidence"** distinctly from zero.
11. **Confidential by construction**: local processing, no carry-over, a leakage gate
    (sections 7, 17.10).
12. **Skill packaging per Anthropic practice**: under 500 lines, one-level references with
    tables of contents, checklist workflow, evaluations first, model matrix (section 4).
13. **Evaluation program** with scenario files, fresh-agent friction loop, blind rounds as
    the success metric (section 21).
14. **Logo and image handling**: extract, place, and treat logos as category labels where
    the reference does.
15. **Optional**: PowerPoint-side verification of renders when a Windows or macOS runner is
    available.

### 23.5 Design instructions that contradict the evidence

Each line below is a generic design instruction that was written into a working system of
this kind as a general rule. Each contradicts the corpus counts (Appendix A) in at least
one deck type. "The reference wins" was stated beside every one of them, but a model
applies a general rule wherever the reference is silent or thin, so the rule itself is the
failure mode. Requirement in every case: replace the rule with the question in Appendix B
plus the reference's measured habit, and keep hard gates only for what is measurable.

| Instruction (known failure mode) | Evidence | Requirement |
|---|---|---|
| Every title is a claim (assertion); topic titles fail | Topic titles on 223 of 231 bank pages and 30 of 30 chart-book pages; claims on 197 of 317 consulting pages, with topics on their reference and appendix pages; the claim sits in another slot on 109 topic-title pages | Title register and length reported against the reference's (sections 3.2, 12.1; already in 23.1) |
| Labelling every mark is an anti-pattern; label only the marks that matter | Labels on all marks are the most frequent chart move in every deck type: 120 of 291 charts (bank 65 of 109, consulting 43 of 135, chart book 12 of 47), usually beside one highlighted item | Label density from the reference's `exhibit_habits` |
| Same-sized panels are a dashboard, not a page | 77 of 578 pages carry two or more exhibits; 6 of 30 chart-book pages are two equal panels; several of the most instructive pages are equal small multiples on a shared scale | Ask whether the blocks are a comparison (section 12.4) |
| Exactly one emphasised row or cell per table; several emphasised rows is emphasis on none | Comps tables emphasise the median row on 12 of 15 and the subject on 8 of 15, often both; projection tables shade several total rows on 27 of 42; sensitivity grids box a region | Several emphasis styles per table, as roles (section 15.2) |
| Fills are a last resort; one fill on a page says "this is the answer" | Fills are role-coded and multiple: shaded key rows on 52 pages, dark label cells and banners on 37, takeaway bands on 46, grey sidebars on 11 of 29 pages of one deck. *Inferred*: the evidence supports one emphasis colour on one item (88 pages), not one fill | Fill roles from the reference; the emphasis colour, not every fill, is the scarce device |
| Banking pages let the numerals speak while consulting pages argue beside the exhibit | Bank charts are never bare (0 of 109); bank decks box or circle more marks than consulting (61 against 41 exhibits) and annotate tables more (50 of 105 boxes sit on tables, mostly in bank decks) | Annotation from the reference's `exhibit_habits`, not from deck type folklore |
| Harvey balls offered as a standard framework exhibit | 0 in bank decks, 0 in the chart book, 2 Harvey-style tables in 317 consulting pages; check, status and red-amber-green matrices are the measured equivalent (16 exhibits, 41 glyph moves) | Offer no exhibit types: ask what the reader must see, with the reference's own use and the corpus counts as evidence |
| Legends are always replaced by direct labels | Legends present on 49 of 81 bank, 55 of 85 consulting and 29 of 47 chart-book charts where recorded; direct labels replace the legend mostly on lines and indexed series (34 of 85 lines) | Ask how the reader will tell the series apart, with the reference's own charts and these counts as evidence |
| Remove every gridline that can be removed | Matches bank (58 of 80 without) and consulting (78 of 89 without); contradicts the chart book, which draws light horizontal gridlines on 47 of 47 | Gridlines from the reference's `charts` habits |
| A page with a table or chart and no source line is refused | Source lines recorded on only 23 of 111 and 27 of 121 pages in two consulting groups, and on 2 of 33 data exhibits in the native-pptx bank decks | Warn with the reference's count, answered in the report; never refuse (section 17.9) |
| A kicker is fixed anatomy of a bank page | Kickers or subtitles on 64 of 231 bank pages against 265 of 317 consulting pages; the bank anatomy is title, exhibit, footnotes, source and furniture | Kicker use from the reference's titles habits |
| Big-number tiles are a tell of generated pages and are never used | Mostly right: no bank or chart-book big numbers and only 7 consulting pages; but consulting pages do pair big numbers with icons or rings, and the craft is pairing each number with its base and population | Ask "of what, and for whom?" (Appendix B) rather than banning the form |

Instructions consistent with the evidence, worth keeping: the declare-or-vary check
measured against the reference's own longest run (sections 12.3, 17.7); vary composition unless
the content demands repetition; comparable charts share one scale; bars start at zero (the
two non-zero baselines in the chart book were recorded as lapses); ask what the data
relationship and the reader's task ask of the form; source and footnote craft in general;
nothing is dropped; the contrast and tie-out gates.

---

## 24. Hard rules

- No literal colour, size, font or coordinate in a page spec; roles only; refused by name.
- Every page names a layout of the chosen template; unknown layouts and placeholders are
  refused by name.
- The model designs every exhibit and every annotation and chooses template and layouts;
  scripts measure and refuse; no script decides or corrects a design choice; omitted
  choices are reported.
- Nothing is dropped to make a page fit; unfittable is a report.
- Never below `max(floor_pt, absolute_floor_pt)`.
- Observed and stated guide values are never overwritten by completion; conflicts between
  template, past decks and guidelines are reported to the user, never resolved silently.
- Numbers come from the user; never invented; every stated figure computed from data.
- Source lines from the sources used.
- Habits not observed in the reference are flagged as low confidence; with no reference,
  every value is the model's choice (`model_choice`), and no corpus value stands in.
- One reference deck at a time; decks are never pooled. A reference's habits are evidence
  beside a choice, never a refusal; a departure is answered in one line in the report.
- Reference files are untrusted: XML entity resolution disabled; zip-bomb caps enforced;
  run readers in isolated interpreters (`python3 -I`) in their own directories.
- Confidentiality: no network calls from any script; derived artefacts stay in the
  company's working directory; no client content from past decks in a new deck unless the
  user supplied it; no client data copied into the page library without permission.
- Generated code (new components written by the model) runs sandboxed: no network, no
  filesystem beyond its inputs, resource caps; no unsandboxed fallback.
- Feedback loops are capped and keep the best result.
- Report what was measured, what was completed by judgement, what was substituted (fonts),
  which conflicts and low-confidence habits remain, and what the user must supply.
- No em dashes, en dashes or emoji in shipped text.

---

## 25. Build order with exit criteria

Each milestone ends with an end-to-end proof recorded beside the claim.

1. **Evaluations and corpus.** Scenario files (21.1); development corpus fetched with
   hashes (Appendix D), including a stand-in company library; blind-round tooling (assembly
   with normalisation and leak checks, rating page, scoring). Exit: a baseline blind round
   on a naive approach, scored.
2. **Reader and triage.** pptx and potx inheritance, PDF triage, rotated text, raster
   instrument, guideline reader. Exit: triage matches renders on all corpus PDFs; raster
   read-back within the stated tolerances (8.3) on a rendered deck.
3. **Template inventory.** Masters, layouts, placeholders, past-deck matching and usage,
   version groups and duplicate detection. Exit: the layout usage table matches a hand
   count on every past deck of the stand-in library; versions of one deck are grouped.
4. **Ruler and solver.** HarfBuzz ruler with measured epsilon; aliases; solver with the
   height rules of 14.2 and placeholders as fixed boxes; table fitter; scale descent;
   capacity. Exit: wrap agreement on a recorded case set; solver round trip on the reference's
   own pages inside its spread.
5. **Guide, extraction, completion.** Full schema including `layouts`, `titles`,
   `exhibit_habits` and `conflicts`; provenance including `stated`; open list; completion
   with groups and null; no-past-decks mode. Exit: guides for all scenario firms with zero
   open core; title statistics match a hand count on 3 decks; a seeded guideline conflict
   is reported.
6. **Emitter and gates.** One resolved entry per element; placeholder writing; read-back;
   contrast with precedent; tie-outs; register and density with no-evidence; content-only
   repetition; renderer-divergence check; layout conformance; leakage; validation with
   render read-back. Exit: a deck built at scale 0.9 has every emitted size equal to the
   solved size; breaking the emitter makes the read-back refuse; seeded client strings are
   all reported by the leakage gate.
7. **Chrome and templates.** Template selection; z-order, rotation, ink, logos, reserved
   zones, no theme effects for PDF references. Exit: PDF-reference pages show chrome
   identical in position and colour to the reference in a side-by-side render; chrome text
   scored; generated pages on a company template open and re-save in PowerPoint without
   repair.
8. **Visual context.** Renders, gallery for pptx and PDF (set cover, area floor), the
   exhibit digest from past decks, page library from the company's best pages plus the
   external starter set. Exit: the model can retrieve the reference's nearest pages for any of
   10 intents; the external starter set has 40+ tagged pages.
9. **Charts and annotation.** Full chart spec with manual plot layout; annotation anchors
   and kinds; placement verified in LibreOffice (and PowerPoint where available) by marker
   renders; collision contract. Exit: on 10 chart types, computed anchor positions match
   rendered marks within a measured tolerance (state it).
10. **Components.** Contract, API, determinism, held-out admission, master-shape collision.
    Exit: four components admitted on two firms each.
11. **Confidentiality.** Network monitoring in the scenario harness; artefact manifest and
    deletion; page library permission handling. Exit: every scenario runs with zero
    network calls from scripts; deleting the artefact set leaves nothing derived from
    company files outside it.
12. **Skill text.** SKILL.md under 500 lines with checklist workflow; references by domain
    with tables of contents; reasoning questions (Appendix B); examples drawn from the
    company's decks and the library. Exit: a fresh agent on each model tier completes
    scenario 1 with zero unfixed friction blockers.
13. **Critique loop.** Render review with located findings, keep-best, caps; optional
    cross-family reviewer calibrated against blind ratings. Exit: findings located on real
    element ids in 10 of 10 reviews; measured effect on the next build.
14. **Blind round 2.** All scenarios, two raters if possible, raters from the company where
    deployed. Exit: success criteria of section 2.4.

---

## Appendix A. Measured page-craft evidence

These counts describe how professional decks design whole content pages. They are
tendencies by deck type: context for a company with no past decks (section 6.8), a check
on habits mined from a company's own decks (section 6.6), and the evidence behind the
reasoning questions of Appendix B. They are evidence, not rules and not a vocabulary to
choose from: the row labels are the coders' keyword categories for what they saw, and a
page may do something no row names. The reference's own measured practice is the strongest
evidence; where a page departs from it, the report says why.

### A.0 Corpus, coding and caveats

Six coder groups each wrote one record per content page: composition, title register and
length, text hierarchy, exhibits (type, data shape, message, every annotation move and its
anchor), emphasis devices, craft details, density and page order. All totals below were
recomputed from those records with one taxonomy across all groups.

| Deck type | Coder groups | Decks | Pages | Exhibits | Charts | Tables |
|---|---|---|---|---|---|---|
| Investment-bank decks (native pptx pitch books and a talk; PDF pitch books, board decks, a restructuring update) | 2 | 11 | 231 | 264 | 109 | 117 |
| Strategy-consulting decks (three firms) | 3 | 12 | 317 | 285 | 135 | 70 |
| A dense market chart book | 1 | 1 | 30 | 52 | 47 | 5 |
| Total | 6 | 24 | 578 | 601 | 291 | 192 |

Caveats that apply to every number in this appendix:
- **One coder per group.** Each page was coded by one person looking at it; there was no
  second coder, and inter-coder agreement is unmeasured.
- **Keyword taxonomy.** Each category is a keyword rule over the coders' free-text notes;
  the rules are the definitions. The taxonomy is coarser than some coders' own (10
  composition families where one coder used 51 types).
- **Approximate counts.** Cells are good to about plus or minus 2 to 3. They can differ
  from a coder's own figure because of the coarser taxonomy and because coders recorded
  some fields unevenly (one group recorded source lines only when they were notable).
  Where a coder's own count is sharper it is quoted and marked "coder count".
- **Strided samples.** 8 of the 24 decks were sampled at a stride rather than as
  consecutive pages; this matters for the variety measures (A.10).
- **Construction is visible only in pptx.** All decks except four native-pptx bank decks
  are PDFs, so how exhibits were built (native chart, pasted picture, drawn shapes) is
  measured only on those four. One bank deck is a scan with no text layer; one run of
  pages in one consulting deck had no text layer and was not inspected.
- **Duplicates.** Exact duplicate pages were dropped (four pages from a second version of
  one deck, and one repeated page).
- Anything marked *inferred* is a reading of the evidence, not a count.

### A.1 Headline: most pages are not charts

346 of 578 pages (60%) carry no data chart: investment-bank 135 of 231, consulting 210 of
317, chart book 1 of 30. Tables (192), diagrams and processes (62), structured text, image
walls and big numbers make up 310 of the 601 exhibits. In the bank decks tables outnumber
charts (117 to 109).

Implication: page design is mainly a question of composition, text and tables. Charts are
one exhibit family among several. A skill whose craft, recipes and annotation are built
around charts serves a minority of the pages a company actually makes.

### A.2 Compositions

Families are derived from each page's exhibit classes, the sidebar flag and the coder's
composition text (n = 578 pages).

| Composition family | Total | Bank (231) | Consulting (317) | Chart book (30) |
|---|---|---|---|---|
| Single chart, full width | 113 | 53 | 45 | 15 |
| Single table, full width | 91 | 45 | 46 | 0 |
| Exhibit plus side text or takeaway column | 80 | 22 | 58 | 0 |
| Two or more exhibits (panels, small multiples, chart plus table) | 77 | 38 | 24 | 15 |
| Structured text (label rows, numbered rows, columns, cards) | 76 | 16 | 60 | 0 |
| Diagram, process or timeline | 58 | 8 | 50 | 0 |
| Text only (bullets or paragraphs) | 40 | 23 | 17 | 0 |
| Image, logo or evidence wall | 19 | 11 | 8 | 0 |
| Exhibit plus text above or below | 16 | 15 | 1 | 0 |
| Big numbers or KPI panel | 8 | 0 | 8 | 0 |

Exhibits per page:

| Exhibits on the page | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| 0 | 94 | 25 | 69 | 0 |
| 1 | 390 | 161 | 214 | 15 |
| 2 | 74 | 34 | 31 | 9 |
| 3 | 17 | 9 | 3 | 5 |
| 4 or more | 3 | 2 | 0 | 1 |

Sidebar or takeaway box (recorded flag): bank 18 of 231, consulting 55 of 317, chart book
0 of 30.

Deck-specific conventions. Each comes from one deck or one firm's decks; they are examples of
what mining a company's past decks finds, not tendencies to copy:
- one bank deck used a bottom takeaway band on 20 of 30 pages (coder count);
- one consulting deck paired a chart of 62 to 70% of the page width with a grey
  full-height sidebar on 11 of 29 pages;
- one consulting deck put a title panel on the left third of the page (6 pages);
- three native-pptx bank pitch books on one master used rows of number badge, arrow label
  and finding box on 6 of 51 pages;
- the chart book's pages are exhibit-only, with no body text, on 30 of 30;
- one consulting appendix ran a row-label template for 7 pages;
- one bank board deck shared one template across 6 recap pages and another across 5
  segment tables.

### A.3 Titles

| Register | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Topic phrase | 372 | 223 | 119 | 30 |
| Claim sentence | 199 | 2 | 197 | 0 |
| Question | 7 | 6 | 1 | 0 |

Median title length in words: bank topic titles 4; chart book topic titles 4; consulting
topic titles 7; consulting claim titles 15. Consulting claim titles run 8 to 22 words and
usually take two lines (coder count).

Register is a reference choice:
- Bank decks almost never use claim titles (2 of 231); the chart book never does (0 of
  30); consulting mostly does, but not always (197 of 317, 62%).
- Consulting topic titles cluster on executive summaries, appendices, trackers and
  reference pages, often prefixed "For reference:" or "Illustrative:", or carrying a
  counter such as "(8/11)".
- Register varies by deck within one firm (coder counts: one consulting deck 23 of 30
  claim titles; a memo 0 of 12).
- The same exhibit can take both registers in one deck: one consulting fact pack titled
  the same lever tree as a topic on one page and as a claim on two later pages.

Where the claim lives when the title is a topic. On 109 of 372 topic-title pages a claim
sentence sits elsewhere (bank 71 of 223, consulting 36 of 119, chart book 2 of 30):
- bank: a takeaway band (one deck, 21 of 30 pages); a lead-in bullet that ends in a colon
  before its exhibit (9 pages over two native-pptx pitch books); the labels of numbered
  rows; kickers and sidebars (one scanned deck, 8 of 21 pages);
- chart book: a full claim sentence in the exhibit's units line;
- consulting: a sidebar or subtitle, or memo prose.
On the remaining topic-title pages no claim is stated at all: the page is reference
material.

Units, kickers and continuations:
- Units line on exhibit titles: bank 64 pages; chart book 27 of 30 (44 of 56 exhibit
  titles). Coder count for the native-pptx bank decks: 18 of 24 numeric pages, and every
  page that shows currency.
- Kicker, subtitle or section tag: consulting 265 of 317 (including "Exhibit n:" labels,
  trackers and status tags); bank 64 of 231. Kickers are mainly a consulting convention.
- Continuations ("(1/2)", "(I/III)", or a title beginning with an ellipsis that continues
  the previous page) appear in four consulting decks.

### A.4 Text hierarchy and lead-ins

Hierarchy levels of body text (pages):

| Levels | Bank | Consulting | Chart book |
|---|---|---|---|
| 0 | 118 | 0 | 30 |
| 1 | 75 | 108 | 0 |
| 2 | 31 | 171 | 0 |
| 3 | 7 | 37 | 0 |
| 4 | 0 | 1 | 0 |

- Bold or coloured lead-ins: bank 26 of 231, consulting 179 of 317, chart book 0 of 30.
- Words per page: two consulting firms averaged 114 to 191 words per deck (coder count);
  the native-pptx bank decks had a median of 72 words counted from slide XML (range 2 to
  221); the chart book has no body text.
- How text and exhibit divide the work: when both are present, the text usually adds what
  the exhibit cannot show: assumptions and caveats, causes and history, the so-what, the
  derived number. All six coder groups report this. Text that restates the title was
  recorded per exhibit: bank 40 of 264, consulting 61 of 180 recorded, chart book 8 of 52.
  In consulting, restating usually means one panel proves one clause of a two-part title.

### A.5 Exhibit types

By class (n = 601):

| Class | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Data chart | 291 | 109 | 135 | 47 |
| Table | 192 | 117 | 70 | 5 |
| Diagram or process | 62 | 11 | 51 | 0 |
| Image wall | 23 | 13 | 10 | 0 |
| Shape-built text structure | 23 | 14 | 9 | 0 |
| Big numbers | 10 | 0 | 10 | 0 |

By family (rows alphabetical: the coders' keyword categories, evidence of what firms drew,
not a set of forms to choose from):

| Family | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Big numbers or KPI | 10 | 0 | 10 | 0 |
| Column | 58 | 33 | 20 | 5 |
| Combo (bar plus line or dot) | 14 | 9 | 1 | 4 |
| Comps or benchmark table | 15 | 14 | 1 | 0 |
| Diagram or framework | 29 | 3 | 26 | 0 |
| Financial or projection table | 42 | 31 | 11 | 0 |
| Football field or range bars | 14 | 11 | 1 | 2 |
| Framework matrix or placemat | 24 | 11 | 11 | 2 |
| Funnel | 2 | 0 | 2 | 0 |
| Heatmap | 2 | 0 | 1 | 1 |
| Histogram | 5 | 1 | 4 | 0 |
| Horizontal bar | 21 | 7 | 12 | 2 |
| Image, logo or evidence wall | 23 | 13 | 10 | 0 |
| Line (incl. indexed, price, dual-axis, area to baseline) | 85 | 20 | 46 | 19 |
| Map | 10 | 1 | 9 | 0 |
| Pie or donut | 13 | 10 | 3 | 0 |
| Process, timeline or plan | 33 | 8 | 25 | 0 |
| Scatter or bubble | 8 | 1 | 3 | 4 |
| Sensitivity grid | 29 | 29 | 0 | 0 |
| Stacked bar, column or area (incl. 100%, diverging) | 47 | 13 | 25 | 9 |
| Status or check matrix | 16 | 1 | 15 | 0 |
| Structured text (rows, cards, quotes) | 23 | 14 | 9 | 0 |
| Table with in-cell bars | 13 | 2 | 11 | 0 |
| Text or data table | 53 | 29 | 21 | 3 |
| Waterfall or bridge | 12 | 3 | 8 | 1 |

Families specific to a reference type: bank decks use sensitivity grids, comps tables, football
fields, projection tables with italic ratio rows, and tombstone and logo walls; consulting
decks use check and status (red, amber, green) matrices, tables with in-cell bars, lever
trees, maps and big numbers; the chart book uses scatters with a regression line and an
R-squared box, and range bars against an item's own history.

Construction (native-pptx bank decks only): 27 of 33 data exhibits in the three pitch books
are pasted pictures; not one pitch-book chart is a native PowerPoint chart. Annotations are
separate shapes laid over the pictures at absolute offsets.

### A.6 Annotation moves

Counted per exhibit (n = 601). "On charts" and "on tables" split the same moves by host.
Rows are alphabetical: the coders' keyword categories for what they saw, evidence and not a
set of moves to choose from; a mark no row names is as open as any.

| Move | Total | Bank (264) | Consulting (285) | Chart book (52) | On charts (291) | On tables (192) |
|---|---|---|---|---|---|---|
| Axis break, inversion or rebasing | 14 | 0 | 11 | 3 | 13 | 1 |
| Bracket or brace (often with a sum) | 24 | 10 | 12 | 2 | 16 | 4 |
| Callout box, arrow or leader to the insight | 77 | 27 | 42 | 8 | 56 | 10 |
| Circled or boxed mark | 105 | 61 | 41 | 3 | 39 | 50 |
| Column spanners or grouped headers | 57 | 44 | 11 | 2 | 9 | 45 |
| Connectors or zoom lines between marks | 22 | 4 | 18 | 0 | 15 | 2 |
| Data labels on all marks | 131 | 68 | 51 | 12 | 120 | 10 |
| Data rows or a table aligned under the chart | 29 | 22 | 7 | 0 | 29 | 0 |
| Delta, growth or CAGR label | 46 | 15 | 29 | 2 | 26 | 16 |
| Derivation shown on the exhibit | 7 | 2 | 5 | 0 | 2 | 4 |
| End or direct labels instead of a legend | 59 | 22 | 26 | 11 | 56 | 1 |
| Event markers on a time axis | 29 | 7 | 18 | 4 | 27 | 0 |
| Footnote markers | 90 | 28 | 56 | 6 | 42 | 36 |
| Forecast or period demarcation | 39 | 13 | 16 | 10 | 31 | 4 |
| Highlight one item, mute the rest | 90 | 51 | 34 | 5 | 45 | 34 |
| Input cells or base case marked | 8 | 7 | 1 | 0 | 0 | 8 |
| Inset stats table inside the plot | 24 | 13 | 2 | 9 | 24 | 0 |
| Italic ratio rows | 16 | 16 | 0 | 0 | 0 | 16 |
| Logos as labels | 20 | 16 | 4 | 0 | 10 | 4 |
| Median or statistic row or block emphasised | 16 | 16 | 0 | 0 | 1 | 15 |
| NM, NA or n.q. markers | 25 | 18 | 7 | 0 | 11 | 13 |
| Numbered or lettered keys tied to text | 50 | 20 | 29 | 1 | 15 | 12 |
| Percent-of-total labels | 12 | 3 | 6 | 3 | 9 | 1 |
| Reference, benchmark or average line | 77 | 21 | 49 | 7 | 61 | 7 |
| Regression line and R-squared | 3 | 0 | 0 | 3 | 3 | 0 |
| Selective data labels | 23 | 7 | 13 | 3 | 22 | 1 |
| Semantic colour (sign, status, sentiment, heat) | 15 | 3 | 11 | 1 | 7 | 8 |
| Shaded or bold total row | 51 | 37 | 13 | 1 | 4 | 47 |
| Sorted order | 50 | 23 | 23 | 4 | 35 | 10 |
| Status glyphs (check, cross, dots) | 41 | 4 | 36 | 1 | 12 | 16 |
| Totals above stacks or "100% =" bases | 34 | 13 | 17 | 4 | 29 | 3 |
| Uncertainty (ranges, scenario lines, stamps) | 6 | 1 | 5 | 0 | 4 | 2 |
| Zone or quadrant shading | 3 | 0 | 3 | 0 | 2 | 1 |

Mean moves per exhibit: bank 2.25, consulting 2.09, chart book 2.02. Finer coder coding
gives 2.46 for the chart book and 5.0 for one consulting deck.

CAGR arrows: 0 in the bank decks (both coder groups) and 1 in consulting. Growth is shown
in a CAGR column, an inset table or an oval instead.

Zero-annotation rates:

| | Bank | Consulting | Chart book |
|---|---|---|---|
| Charts with no annotation | 0 of 109 | 4 of 135 | 3 of 47 |
| All exhibits with no annotation | 13 of 264 | 8 of 285 | 4 of 52 |

Over all firms, 7 of 291 charts carry no annotation. The bare consulting charts are line
charts whose sidebar explains the method; the bare exhibits that are not charts are mostly
tables, logo grids and icon rows.

Charts with no move that points at the message (nothing beyond labels, sorting, footnotes,
totals or spanners): bank 36 of 109, consulting 27 of 135, chart book 12 of 47. About one
chart in four relies on labels alone.

Chart scaffolding (where recorded):
- Legend absent: bank 32 of 81, consulting 30 of 85, chart book 18 of 47 (the chart book's
  legends, about 22, are swatches with text in the series colour).
- Gridlines absent: bank 58 of 80, consulting 78 of 89, chart book 0 of 47 (light
  horizontal gridlines on every chart are that reference's style).
- Colour: one emphasis colour or a single hue was the most common; categorical colour was
  kept for genuinely categorical series (one bank coder group: 24 of 72 single emphasis against 15
  of 72 categorical; the same pattern in two other groups). In the native-pptx bank decks,
  series were two tints of one navy and red meant only "look here".

### A.7 Moves by data shape and by message

What coders recorded on exhibits of one family, as evidence for the question "what must the
reader see here?", not as a lookup from shape to moves (the per-family table that stood
here read as one, and was removed; it is in this file's history at 3952e74). The counts
other sections cite: line or time series (85): end or direct labels 34, event markers 21,
forecast demarcation 13; horizontal bars (21): sorted 15, highlight one 13; stacked or 100%
(47): totals or "100% =" bases 20; football fields or ranges (14): a reference line at the
offer or current price 8; financial or projection tables (42): shaded total rows 27, italic
ratio rows 16; comps or benchmark tables (15): a median or statistic row 12, the subject
highlighted 8; sensitivity grids (29): a boxed cell or region 17. For a page, the reference's own
digest pages (`exhibit_habits.records[].marks`) and the marks its files draw come first.

By message (coders' message-level coding):
- Subject against peers (one bank coder group, n = 41 exhibits): labelled, the subject
  highlighted, a median line or median row. (One consulting coder group, n = 5 peer
  benchmarks): highlight 4, mean line 4, delta pill 3, sorted 3.
- Ranking (one bank group, n = 4; one consulting group, n = 5 horizontal bars): sorted,
  labelled and the subject highlighted on all of them.
- Change over time (all six coder groups, uncounted at message level): end labels; event
  markers when the message is what caused the shape; a forecast divider for projections.
- Valuation range (one bank group, n = 4 football fields): a reference line at the
  decision value on 4, plus brackets and data rows under the axis.
- Composition (one consulting group, n = 2 100% stacks): totals above the stacks, "100% ="
  bases, and the legend replaced by row-aligned labels on both.
- Estimate or scenario (one consulting group, n = 10): dashed forecast with period shading
  6, baseline line 6, circled headline value 4.
- Relationship (the chart book, n = 3 scatters): regression line, today's point
  highlighted and an R-squared box on all three.
- Choice or recommendation (the native-pptx bank group, uncounted): a pointer or callout
  plus a box on the answer.

### A.8 Emphasis devices

Pages carrying each device (rows alphabetical: coders' categories, evidence, not a set to
choose from):

| Device | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Arrows, chevrons or wedges as connectors | 34 | 7 | 27 | 0 |
| Big numbers | 7 | 0 | 7 | 0 |
| Bold or coloured lead-in or key phrase | 92 | 17 | 75 | 0 |
| Boxed or circled figure | 102 | 30 | 68 | 4 |
| Icons | 32 | 2 | 30 | 0 |
| Navy or dark label cells or banners | 37 | 20 | 17 | 0 |
| Numbered or lettered markers | 31 | 9 | 22 | 0 |
| Photos or logos | 12 | 0 | 12 | 0 |
| Red or green semantic text | 9 | 4 | 3 | 2 |
| Shaded key rows, cells or columns | 52 | 13 | 38 | 1 |
| Single emphasis colour on one item | 88 | 38 | 50 | 0 |
| Status glyphs, checks or red-amber-green | 25 | 5 | 20 | 0 |
| Status stamps (draft, preliminary, illustrative) | 10 | 0 | 10 | 0 |
| Takeaway band, box or sidebar | 46 | 22 | 23 | 1 |

Coder counts are higher where coders coded by hand: one bank group found shaded key rows on
64 of 184 pages and boxed or circled figures on 55 of 184; one consulting group found status
tags on 31 of 85.

Not seen: Harvey balls (0 in the bank decks, 0 in the chart book, 2 "Harvey-style" tables
in 317 consulting pages); icons (0 in the native-pptx bank decks, 0 in the chart book).

### A.9 Craft details, density and human defects

Pages carrying each detail:

| Detail | Total | Bank | Consulting | Chart book |
|---|---|---|---|---|
| Source line | 227 | 106 | 91 | 30 |
| Page furniture (number, footer, logo, codename) | 223 | 106 | 87 | 30 |
| Footnotes or notes | 195 | 93 | 95 | 7 |
| Units line or units in a header | 123 | 50 | 43 | 30 |
| Status or caveat tag | 122 | 71 | 51 | 0 |
| Deliberate repetition or cross-page consistency | 82 | 27 | 51 | 4 |
| Rounding, method or definitions disclosed | 61 | 17 | 43 | 1 |
| Number-format habits (x suffix, $ on first and total rows only, ~, K/M) | 35 | 12 | 21 | 2 |
| As-of date | 22 | 5 | 17 | 0 |
| Continuation marker or ellipsis title | 19 | 4 | 15 | 0 |
| Negatives in parentheses | 13 | 6 | 6 | 1 |

Source lines on pages that carry a chart or table, as recorded in craft notes, by coder
group: bank PDF 84 of 150; bank native pptx 2 of 23; consulting groups 20 of 51, 14 of 63
and 14 of 60; chart book 30 of 30. Recording was uneven, but the coders' own counts agree
that a large share of real data pages carry no source line (two consulting groups: source
lines on 23 of 111 and 27 of 121 pages).

Recurring table habits (bank decks, both coder groups): $ only on the first and total rows;
x on multiples; italic ratio rows under their $ row; a units column separate from the
labels; NM and NA written out, never left blank.

Density: median page fill is 0.85 in every deck type. Median elements per page: bank about
80 (two decks at 145 and 119), consulting about 30, chart book about 35. Dense tables reach
110 to 230 elements (one at 170).

Defects humans made: recorded on 106 pages (bank 39, consulting 64, chart book 3).
Measurable defects (do not imitate; each is checkable on the file or the data): title
typos; mismatched y-scales on sibling charts; truncated axes; colliding labels; a
disclaimer box overrunning the title on four pages of one deck; template residue; numbers
inconsistent across pages; in the native-pptx bank decks also pictures past the margin,
misregistered overlay boxes, comma decimals in a borrowed chart, repeated titles, and
mixed fonts between pasted exhibits and slide text; two chart-book charts on non-zero
baselines. These are what a generator should be better than, not what it should copy.
Recorded beside them as one coder's judgement, to weigh as opinion against the reference's own
pages: a missed subject highlight; a title claim with no bracket summing it.

### A.10 Variety over consecutive pages

Measures, over adjacent pairs of sampled pages within one deck, using the 10 composition
families of A.2 (coarser than some coders' taxonomies, so change rates come out lower than
theirs):
- **Composition change rate** = adjacent pairs whose composition family differs / (n - 1).
- **Exhibit-set change rate** = adjacent pairs whose set of exhibit families differs /
  (n - 1); a page with no exhibit counts as the set {text only}.
- **V** = mean over adjacent pairs of [0.5 x (1 if the composition family changed, else 0)
  + 0.5 x (1 - Jaccard similarity of the two pages' exhibit-family sets)].
- **Repeat rate** = 1 - composition change rate.
- **Longest run** = the longest sequence of consecutive pages in one composition family.
- **Entropy** = Shannon entropy, in bits, of the deck's composition-family distribution.

| Deck | n | Strided | Composition change | Exhibit-set change | V | Longest run | Distinct families | Entropy (bits) |
|---|---|---|---|---|---|---|---|---|
| Bank 1 | 26 | yes | 0.64 | 0.84 | 0.73 | 4 | 5 | 2.22 |
| Bank 2 | 21 | no | 0.65 | 0.80 | 0.70 | 5 | 5 | 2.06 |
| Bank 3 | 14 | no | 0.85 | 0.85 | 0.85 | 2 | 7 | 2.70 |
| Bank 4 | 42 | no | 0.51 | 0.56 | 0.53 | 7 | 5 | 1.83 |
| Bank 5 | 28 | no | 0.63 | 0.67 | 0.62 | 4 | 8 | 2.64 |
| Bank 6 | 30 | no | 0.62 | 0.76 | 0.66 | 5 | 5 | 2.06 |
| Bank 7 (native pptx) | 19 | no | 0.67 | 0.72 | 0.69 | 3 | 9 | 2.78 |
| Bank 8 (native pptx) | 11 | no | 0.90 | 1.00 | 0.93 | 2 | 5 | 2.12 |
| Bank 9 (native pptx) | 14 | no | 0.69 | 0.77 | 0.73 | 2 | 5 | 2.07 |
| Bank 10 (talk, contrast case) | 7 | no | 0.50 | 0.50 | 0.50 | 4 | 3 | 1.15 |
| Consulting 1 | 30 | yes | 0.86 | 0.90 | 0.88 | 2 | 8 | 2.61 |
| Consulting 2 | 30 | yes | 0.69 | 1.00 | 0.84 | 4 | 8 | 2.43 |
| Consulting 3 | 30 | yes | 0.69 | 0.69 | 0.69 | 7 | 8 | 2.56 |
| Consulting 4 | 31 | no | 0.60 | 0.53 | 0.53 | 4 | 6 | 2.35 |
| Consulting 5 | 14 | no | 0.77 | 0.92 | 0.85 | 3 | 5 | 1.92 |
| Consulting 6 | 30 | yes | 0.79 | 0.83 | 0.78 | 3 | 7 | 2.33 |
| Consulting 7 | 29 | no | 0.86 | 0.82 | 0.84 | 5 | 6 | 2.16 |
| Consulting 8 (memo) | 12 | no | 0.55 | 0.91 | 0.73 | 5 | 5 | 1.78 |
| Consulting 9 | 22 | no | 0.86 | 0.86 | 0.86 | 2 | 6 | 2.53 |
| Consulting 10 | 30 | no | 0.76 | 0.79 | 0.78 | 3 | 7 | 2.13 |
| Consulting 11 | 29 | yes | 0.82 | 0.93 | 0.88 | 3 | 6 | 2.43 |
| Consulting 12 | 30 | yes | 0.76 | 0.72 | 0.74 | 4 | 8 | 2.65 |
| Chart book | 30 | yes | 0.55 | 0.97 | 0.71 | 6 | 2 | 1.00 |

Summary:
- Median composition change rate: bank 0.645 (range 0.50 to 0.90; 9 of 10 decks
  consecutive), consulting 0.765 (range 0.55 to 0.86), chart book 0.55 at a two-page
  stride, all 23 decks 0.69. Consecutive pages repeat their composition family about 35%
  of the time in bank decks, 24% in consulting and 45% in the chart book.
- Exhibit types change more often than compositions: median exhibit-set change rate bank
  0.77, consulting 0.85, chart book 0.97. The chart book keeps two composition families
  (full width, or panels) and varies the chart type on nearly every page.
- Coders' finer taxonomies give higher change rates: one bank group 0.59 to 0.90
  (composition change); the native-pptx bank group 0.83 to 0.90 (with no run longer than 2
  by its own types); consulting groups 0.93 to 1.00 (exact layout tag), 0.64 to 0.85 and
  0.55 to 0.83.
- Every long run is a deliberate template for comparison: a bank board deck's 7 (6 recap
  pages, then 5 segment tables), a consulting appendix's 7, the chart book's 6, and a
  consulting deck's industry template and executive-summary title panels (6 each). No coder
  found an accidental run of sameness.

*Inferred*: variety in these decks comes from the content's shape changing, and repetition
comes from content that is meant to be compared. A generator should vary composition unless
pages are siblings; siblings meant to be compared share one scale and one order, and
whether they share one frame is the plan's question.

### A.11 The page library drawn from this corpus

About 40 of the coded pages form the external starter set of the page library (section
10.4): 15 bank, 21 consulting and 4 chart-book pages, chosen from each coder group's most
instructive pages and balanced across deck type and composition rather than chart pages
first. 15 of the 40 have a table, matrix, diagram or structured text, not a chart, as their
main exhibit.

---

## Appendix B. Reasoning questions for the designer

Offer these as the way to think, tied to evidence, not as rules. Each question that cites
counts is *inferred* from what the corpus pages show (Appendix A); the counts say how often
the corresponding move appears. The reference's own measured practice is the strongest
evidence; where a page departs, the report says why.

Per deck:
- Which of the company's templates fits this deck's type and audience, and which past decks
  of this type were built on it? If two fit, what would the user say?
- What do the company's best decks of this type look like, and which of their pages are
  nearest to what this deck needs?

Per section:
- What is the storyline, page by page, in one sentence each? Where does the reader need
  evidence, and where only a statement?
- Which compositions and layouts will each page use, and how does that compare with the
  reference's own variety? Which repeats are deliberate parallels, and why? (Every long run in
  the corpus was a sibling template held on purpose; median composition change 0.69 over
  23 decks; A.10.)
- Which pages are one of a set, meant to be compared by flipping? They share one scale and
  one category order; do they also read better on one frame? (Sibling runs of 5 to 12 pages
  in the corpus; missed shared scales on sibling charts were recorded as defects.)

Per page:
- What should the reader leave with: the page's message, or, on a reference page, what
  they look up? Which slot of this reference carries it (`guide.titles.claims_elsewhere`; the
  corpus found titles, lead-in bullets ending in a colon, sidebars, takeaway bands,
  kickers, units lines, the labels of numbered rows), or does this page need somewhere
  else? Does this reference argue in titles, or name the
  topic and argue elsewhere? How long are its titles? (Claim titles on 197 of 317
  consulting pages, 2 of 231 bank pages, 0 of 30 chart-book pages; on 109 topic-title pages
  the claim sits in another slot; A.3.)
- Is this a page of argument or a page of reference? (Topic titles, appendix counters and
  "For reference:" prefixes mark reference pages; they carry complete tables with
  furniture such as spanners, totals and footnotes and little emphasis: in one bank coder
  group 54 of 224 exhibits had only furniture.)
- Which layout do the company's past decks use for a page like this, and which
  placeholders do they fill?
- Which element proves the message most directly, and does its size reflect that? Where
  does the eye finish? (One exhibit per page on 390 of 578 pages; the resolution tends to
  sit at the end of the reading path: the last row boxed and shaded, a bottom band, a down
  arrow to one bottom-line number.)
- If several blocks are co-equal, are they a comparison (then equal panels on a shared scale
  are honest: 77 of 578 pages carry two or more exhibits) or a list of unrelated facts (then
  equal tiles read as a dashboard)?
- What will the reader do with this content, and what form serves that? (Lookup and
  reference content was a table in 71 of 71 cases, sensitivity in 29 of 29; change over
  time was a chart 93 times and a table 24 times, the tables being projections where every
  number is read; 346 of 578 pages carry no chart. Coders also recorded parallel findings
  set as numbered or label rows, ordered options as a spectrum and qualitative text ranked
  on an axis, uncounted.)
- What does the text add that the exhibit cannot (assumptions, caveats, causes, history,
  the implication, the derived number)? Is anything said twice? (Restating the title was
  the minority: 40 of 264 bank exhibits, 8 of 52 chart-book exhibits.)
- Can the reader check the claim on the page? Is the title's number derivable from what is
  printed (a share shown as the sum of its parts, the equation that produces a total, raw
  numerators beside the shares)? (Derivation is rare as a move, 7 exhibits, but frequent
  among the most instructive pages.)
- Which company page is nearest to this intent, and what does it do that this page does
  not?
- Is anything on this page carried over from a past deck that the user did not supply?

Per exhibit:
- What is the data, in its own terms: how many things, measured how many ways, over what?
  What must the reader see in it? Which forms could show that, and which does the reference
  use? Would a table say it better?
- If the reference has never shown this exhibit, how would its designers have drawn it with
  the roles, rules and devices they do use?
- What comparison is the reader making, and against what? (Subject against peers:
  highlight the subject on 22 of 46 such exhibits, emphasise a median or statistic row on
  12 of 46, sort on 13 of 46. Against a decision value: a reference line, used on 77
  exhibits, at the offer, the current price, the median or a policy cap. When peers are not
  one population, benchmark the subject against each cluster's median.)
- Where on this exhibit does the claim live? How does the reference mark such a place (its
  digest records and the marks its files draw)? (Circled or boxed marks on 105 exhibits, 50 of them tables; a box on the
  scenario region of a sensitivity grid; the bars that sum to the claim coloured; one panel
  left unboxed to prove "except this one".)
- Can the absence of a mark carry meaning?
- What must the reader see on this exhibit that it does not yet show? (What coders
  counted, as evidence and not as a lookup: time series carried end labels on 34 of 85;
  rankings were sorted on 15 of 21; stacks carried totals on 20 of 47; projection tables
  shaded totals on 27 of 42; comps tables emphasised a median row on 12 of 15; A.7.)
- How much to annotate, and what to leave out? (Only 7 of 291 charts are bare. Selective
  emphasis is the norm: one judgement on a whole mechanical page; three row groups boxed in
  a full table; only the first and last bars bracketed. Labelling every mark is common, 131
  exhibits, and coexists with one emphasised item. Scaffolding is left out: gridlines absent
  on 136 of 169 bank and consulting charts where recorded, legends replaced by direct labels
  on 80 of 213 charts; but one firm draws light gridlines on 47 of 47. Non-focus parts are
  faded rather than deleted.)
- How will the reader find the subject (colour, position, order held across panels)?
- What value is the decision made against (current price, offer, median, target)? Is it
  drawn?
- What is estimate and what is fact, and how certain is it? (Forecast demarcation on 39
  exhibits: a dashed line, hatching, two-tone bars or a "Forecast" divider; ranges in place
  of points; status stamps such as PRELIMINARY or ILLUSTRATIVE on 10 consulting pages; a
  broken series shown broken.)
- What explains the shape? (Event markers on 29 exhibits, all on time axes, where the
  message is what caused it.)
- Is the form unfamiliar enough to need a reading key ("How to read this chart", a written
  reading rule, the key placed in an empty grid cell)?
- Colour means relative to what? (Heat and status colour were defined against a named
  benchmark or a decision; semantic red and green appear on 9 pages; elsewhere red means
  "look here".)
- For a big number: of what, and for whom? Is its base and population on the page? (Big
  numbers are rare: 0 bank and chart-book pages, 7 consulting pages; where used, the craft
  was pairing each number with its base.)
- What does the chart not say that the reader needs, and where does that go?
- How much does the reader need to read off the marks, and how will they tell series
  apart? What number formats, units and negatives does the reference write?
- What would a managing director circle in red on this page?

Per build (on the renders):
- Can the message be found in two seconds?
- Side by side with the company's best pages, what differs?
- What would make one of the company's senior bankers or consultants suspect this page
  was generated?

---

## Appendix C. OOXML and renderer facts (each measured)

- 914400 EMU per inch; 12700 per point.
- Line pitch 1.2 x size, font-independent (7 families).
- PowerPoint fits less text than LibreOffice on 92 of 600 boxes; width epsilon 5,933 EMU
  (Pillow) or 20,234 EMU (HarfBuzz).
- Table row heights in the file are minimums; PowerPoint realises lines x 1.2 x size plus
  cell margins.
- Shared table edge declared differently on two cells: PowerPoint keeps the first-declared
  side and writes it back; LibreOffice draws the heavier.
- Strokes below 0.5pt: 0.48 px in PowerPoint, 1.27 px in LibreOffice.
- `c:varyColors` absent: PowerPoint paints one series in five theme colours; LibreOffice
  does not.
- Negative `spcPts`: LibreOffice draws nothing.
- python-pptx's default `word_wrap` centres text in LibreOffice; set it true.
- A Wingdings bullet glyph renders as a section sign without its bullet font.
- Shape style `fontRef` and table style `tcTxStyle` set default text colours; white labels
  read as black without them.
- Theme reached through the master's relationship; colour maps apply before theme lookup
  and may be overridden per slide and layout.
- Hidden slides are not exported by the renderer.
- An interrupted soffice leaves a profile lock; use a fresh profile per render.
- Origin tags in `p:custDataLst` survive a PowerPoint save.
- Template = a deck with slides removed: opens and re-saves without repair; chrome drawn
  once per slide.
- LibreOffice wraps chart category labels and centred data labels mid-word in narrow slots;
  an `inside_base` label was observed not to wrap.
- Rules on a blank template can inherit a theme drop shadow in LibreOffice.

---

## Appendix D. The development corpus

A company's decks are confidential, so the skill is developed and evaluated on public
decks that stand in for a company's library, then re-evaluated on the company's own
material at deployment. Every file is fetched once, type-checked, hashed and treated as
untrusted; a manifest records source, licence basis and hash.

What the corpus measured above contained (all public; described here by type only):
- **Investment-bank decks** (11 decks; 231 coded content pages):
  - four native pptx decks: three training pitch books built on one fictional bank's
    master (a sell-side book with a PDF twin, an M&A book and a financing book), plus a
    conference talk kept as a contrast case. Because the three share one master, they are
    the closest public stand-in for a company with one template and several past decks;
    use them for template inventory, layout usage and habit mining (scenarios 1, 2, 7, 10);
  - seven PDF decks released through regulatory filings or litigation: pitch books, board
    decks (including a go-private board deck and a fairness opinion bound with filing
    text), a scanned restructuring update with no text layer, and a credentials deck.
- **Strategy-consulting decks** (12 decks from three firms; 317 coded content pages),
  released through public-records requests: public-sector reviews, fact packs, operational
  diagnostics, governance and financial reviews, and a memo. Several run to hundreds of
  pages and were coded at a stride.
- **A dense market chart book** (30 coded pages, sampled at a stride), as a craft
  reference for annotated charts.
- A theme test file.

Known gaps: native pptx working decks from real banks are almost unobtainable publicly
(searches found only PDFs and template-store products); public web archives were
unreachable from the build environment; regulatory exhibits are mostly HTML. Expand the
corpus where possible, especially native pptx, multi-template libraries and brand
guideline documents, and keep the manifest complete.
