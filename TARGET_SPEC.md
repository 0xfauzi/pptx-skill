# House-Style Deck Skill: Target Specification

Version 1, 2026-10-20. Written for an agent that will build this system from scratch. You
will not see the code of the prototype this spec describes, nor the predecessor system it
borrowed from. Everything you need is in this document: the goal, the architecture, the
contracts between parts, and every fact that was measured along the way, with the
measurement that produced it. Where a fact was not measured, it is marked as such.

Read section 0 first. Then section 1 (goal and how it is judged) and section 2 (design
principles); they decide every trade-off below.

## Contents

0. How to read this document; vocabulary
1. Goal, scope and success criteria
2. Design principles
3. Packaging the skill (Anthropic skill-authoring practice)
4. System overview: the pipeline in one page
5. Intake: reading any reference
6. The style guide: schema, provenance, completion
7. Visual context: renders, gallery, exemplars, the page library
8. Templates and chrome
9. Planning a section: storyline, page plan, variety plan
10. The page specification language
11. Text measurement and the layout solver
12. Exhibits: charts, tables, annotation, components
13. Emitting the PowerPoint file
14. Gates: validation, contrast, fit read-back, tie-outs, register, repetition
15. Rendering and the self-critique loop
16. The style judge, and its limits
17. Editing an existing deck
18. Evaluation program
19. Evidence: what was measured
20. What the prototype built, and how each part fared
21. Failures observed, and their causes
22. Target improvements over the prototype
23. Hard rules
24. Build order with exit criteria
Appendix A. Measured annotation and page-craft vocabulary
Appendix B. Reasoning questions for the designer
Appendix C. OOXML and renderer facts (each measured)
Appendix D. Reference corpus

---

## 0. How to read this document

### 0.1 Vocabulary

- **Reference**: the deck (pptx or PDF) whose style the output must match. Untrusted input.
- **House**: the visual identity a reference belongs to (one bank's or consultancy's
  template and habits). Several decks can share a house.
- **Style guide** (or **guide**): a JSON document describing the reference's style as
  named roles with values and provenance (section 6).
- **Role**: a named slot in the guide, such as `type.title`, `color.accent1`, `space.md`.
  Page specs refer only to roles, never to literal values.
- **Provenance**: for every guide value, where it came from: observed in the file,
  deterministically inferred, completed by the model, or raster-measured; plus evidence
  and confidence.
- **Open address**: a guide path the extractor could not settle from evidence. The model
  must answer exactly these and no others.
- **Page spec**: the model's description of one page as a tree of regions and elements
  using roles and weights (section 10).
- **Solver**: deterministic code that turns a page spec plus guide into exact geometry in
  EMU, using measured text widths (section 11).
- **EMU**: English Metric Unit, PowerPoint's coordinate unit. 914400 EMU = 1 inch;
  12700 EMU = 1 point.
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
  (a football field, a KPI row), checked against held-out cases before use (section 12.5).
- **Judge**: a style fingerprint distance that says which house a deck most resembles
  (section 16). It is an instrument, not the definition of quality.
- **Blind round**: the human evaluation in which a rater sees real and generated pages
  mixed and guesses which is which, and rates quality (section 18). This is the primary
  measure of success.

### 0.2 Status labels

Facts are labelled:
- **Measured**: produced by a run on real files, with the numbers given.
- **Measured once**: a single observation, real but not repeated.
- **Unmeasured**: a claim or design intent with no measurement behind it yet.
- **External**: from published sources, not measured on this system.

---

## 1. Goal, scope and success criteria

### 1.1 The goal

Given ANY reference presentation, a native .pptx or a PDF (vector export or scanned), an
agent using this skill produces new presentation pages that:

1. Are indistinguishable from the reference house's own pages to an informed human reader
   (a banker or consultant who knows decks), including pages built from exhibits the
   reference never showed.
2. Are dense, expert, pitch-book quality: the content a managing director would send,
   with the analytical craft of a senior associate (correct figures, sensible exhibit
   choice, intelligent annotation, consistent furniture, source lines).
3. Are native, editable PowerPoint: real text, real tables, real charts or drawn shapes,
   on the reference's own master when the reference is a pptx.
4. Are valid files that open without repair in PowerPoint and render the same in
   LibreOffice to within the measured renderer differences.

### 1.2 The division of labour

The model (the agent using the skill) decides everything that is a design or content
judgment: storyline, what each page says, composition, exhibit type, what to annotate and
how, emphasis, what to complete where the reference is silent, how a new component looks.

Scripts decide nothing about design. They read files, measure text, solve geometry, write
valid packages, render, and refuse what is measurably wrong (overflow, overlap, contrast
below threshold, totals that do not tie, values outside the guide). They never pick a
colour, never choose a chart, never swap an ink to fix contrast, never default a design
choice silently.

The skill's job is therefore to give the model three things:
- **Context**: the reference's style as data, the reference's own pages and exhibits as
  images, a library of excellent pages from other houses, and measured statistics about
  how human decks are designed.
- **Reasoning instructions**: questions and procedures that make the model think about a
  page the way a senior designer does (Appendix B), not rules that fix a design.
- **Instruments**: scripts that make the model's decisions executable and checkable.

### 1.3 Scope

In scope: style extraction from pptx and PDF; completion of what the reference never
showed; section and deck planning; page design; charts, tables, diagrams, annotation; novel
components; measured fit; valid emission; rendering; gates; style judging; editing and
extending existing decks; evaluation.

Out of scope: sourcing financial data (figures come from the user; never invented),
animation, speaker scripts beyond notes, non-PowerPoint output formats.

### 1.4 Success criteria (in priority order)

1. **Blind round** (section 18.2): over a set of houses, a rater cannot tell generated
   pages from real ones better than chance, and rates generated pages at least as high
   as real ones. Baseline from the prototype: rater accuracy 45 of 60 (chance 30;
   probability of 45 or more by luck 0.00007); mean quality 2.93 generated vs 3.53 real.
   Target: accuracy within the binomial chance band at p = 0.05 per house, and generated
   quality mean at or above real.
2. **Expert review**: located findings from a reviewer (human, or a model acting as an MD)
   on figures, exhibit choice, annotation, wording; zero factual errors in titles and
   takeaways (every figure computed from the data).
3. **Mechanical correctness**: every page fits at measured scale; zero overflow, overlap,
   clipped labels, contrast violations, unresolved roles; package validates; renders in
   PowerPoint and LibreOffice.
4. **Style judge** (section 16): the deck is filed under its reference. Necessary, not
   sufficient. The prototype's judge filed decks a human caught every time, and failed to
   file a deck that fooled the human 4 of 5 times (section 21.1).

---

## 2. Design principles

These were learned, mostly by violating them. Each is followed by the evidence.

### 2.1 The model designs; code measures and refuses

Any design choice made in code is a choice the model cannot see or override, and it
produces the same page for every house. The prototype's chart code once picked series
colours by cycling a palette, hid value axes when labels showed, swapped label inks below
3:1 contrast, and drew waterfalls through a dedicated path. Removing 21 such decisions and
handing them to the model (with every choice written in the spec and every omitted choice
reported by name) left the reference-adherence scores unchanged (judge 0.086 before and
after on the keybank section) while letting the model compose exhibits the code had never
anticipated (a horizontal cost bridge, a Gantt from a stacked bar, a scatter with a
regression line). Measured.

Corollary: when the model leaves a choice out, the system writes a named neutral value and
reports it (`chart_defaults_taken`), so the model sees every choice it did not make.

### 2.2 Context plus reasoning, not rules

Rules that fix a design override the house. The prototype told the model to write
assertion (claim) titles with computed figures. In 51 sampled content pages of three
native-pptx bank pitch books, 48 titles are topic phrases (median 4 to 5 words), 3 are
questions, 0 are claim sentences; the claim lives in a lead-in bullet ending in a colon
above the exhibit (measured; Appendix A). The predecessor system measured the same
mismatch: the reference's 11 titles had a median of 35 characters (longest 57); the
planner's 19 claim titles had a median of 80 (longest 103); only 4 of 19 fit within the
reference's longest; told a 56-character budget the designer shortened only 5 of 19, and
17 of 22 held pages were held because the title overran its one-line band (measured).
The blind rater caught every generated page in exactly those two houses.

So: the house's observed habits (title register and length, annotation moves, emphasis
devices, composition variety) are measured from the reference and given as context. Generic
doctrine is offered as questions the model asks itself, and "the reference wins" is
enforced by measurement, not prose.

### 2.3 A prompt sentence does not fix a visual defect

The predecessor stated an axis rule in the prompt and the model drew a diagonal anyway;
the note recorded was "this class needs the render loop, not another sentence" (measured
once). Visual defects are caught by looking at renders (the model's own critique pass) or
by a validator, never by adding instructions.

### 2.4 Never offer the model a field the pipeline cannot honour

The predecessor offered annotation anchors before any placement pass existed; anchored
annotations were refused, the model then attached callouts to tables and side rails (7
refusals), and the whole annotation field was removed (measured). Every field in the page
spec must be fully implemented, validated and rendered, or absent.

### 2.5 Closed sets are followed; continuous values drift

On the same briefs, a strong model used exactly the guide's type scale (8/9/10/11/14/24pt)
while a weaker model invented 8.5, 9.5, 20 and 22pt; both were exact on a palette of named
roles (measured once, two models). Expose style as closed sets of named roles; refuse any
literal value.

### 2.6 More instructions help strong models and can hurt weak ones

A longer rule set (fill the whole canvas, anchor callouts) improved a strong model's
self-graded pages and caused the first collisions and larger dead margins on a weaker
model (measured once; self-graded, not independent). Test every instruction change on
every model tier the skill supports (section 18.4).

### 2.7 Measure, never estimate

Text fit is measured with the real font's shaping (section 11), never estimated from
character counts ("0.6 em per character" wrapped "$8.2 to $12.4" onto two lines in a
component; measured once). Pixels never decide fit. Whole runs are measured, never the sum
of fragments (kerning). All thresholds come from measurement on this system and carry the
measurement; an unmeasured threshold is labelled as such.

### 2.8 Absence is not zero

`set`, `dict`, `.get()` with a default, `continue` and `return {}` over untrusted
structure turn "I cannot tell" into a confident answer. Examples from the prototype: a
judge that fingerprinted a scanned reference from its OCR layer and confidently called the
house "88% Times New Roman at 1pt" (so nothing could ever be filed under it); density bands
of [0, 0] words for PDF references, so every page read "above"; register bands of 0 tables
and 0 charts for houses that paste exhibits as pictures, so every native table read
"above". Each such instrument must report "no evidence" distinctly from "zero".

### 2.9 A test that passes against unfixed code is not a test

Break the fix, watch the check fail, restore. When the producer and the consumer of a
value are both yours, drive the real producer rather than spelling the expected value.
Unit tests are not checked in to this skill by the owner's choice; proofs are end-to-end
runs whose output is recorded (section 18).

### 2.10 One definition per concept

A second definition of an existing concept is a bug in waiting. The prototype had the
emitter and the solver read different type roles for table cells (the solver measured the
spec's `cell_role`, the emitter wrote `type.table_cell`), so a table measured at 8pt was
written at 12pt; and it measured text in DejaVu Sans while LibreOffice drew Inter for the
same font name. Both are the same bug: two sources of one truth.

### 2.11 Degrees of freedom match fragility

Anthropic's skill guidance (section 3): low freedom (exact scripts) where operations are
fragile (OOXML, fit, validation); high freedom (context and heuristics) where many designs
are valid (composition, exhibits, annotation, wording).

---

## 3. Packaging the skill (Anthropic skill-authoring practice)

Source: Anthropic, "Skill authoring best practices"
(platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) and
"Equipping agents for the real world with Agent Skills" (anthropic.com/engineering).
Apply all of the following; the prototype violated most of them.

### 3.1 Structure and progressive disclosure

- A skill is a directory with `SKILL.md` (YAML frontmatter `name`, `description`, then
  the body), plus bundled reference files and scripts.
- Level 1 (always loaded): name and description. Level 2 (loaded when relevant): the
  SKILL.md body. Level 3+: bundled files, read only when needed. Scripts are executed,
  not loaded; only their output costs context.
- Keep the SKILL.md body under 500 lines. The prototype's was 592.
- References one level deep from SKILL.md (no file that sends the model to a third file).
- Any reference file over 100 lines starts with a table of contents.
- Organise reference files by domain so the model reads only what the task needs
  (for example `reference/charts.md`, `reference/tables.md`, `reference/pdf-intake.md`).
- Say explicitly whether a script is to be executed or read.

### 3.2 Metadata

- `name`: at most 64 characters, lowercase letters, digits, hyphens; no reserved words
  ("anthropic", "claude"). Prefer gerund form. Do not reuse the name of another skill the
  agent may have (the prototype was named `pptx`, colliding with the stock skill). A
  suitable name: `building-house-style-decks`.
- `description`: at most 1024 characters, third person, says what the skill does and when
  to use it, with the key terms a user would say (pitch book, board deck, CIM, consulting
  deck, house style, reference deck, .pptx, PDF reference).

### 3.3 Content

- Assume the model is capable; add only what it does not already know. Every paragraph
  must justify its tokens.
- Match degrees of freedom to fragility (section 2.11).
- Provide a workflow checklist the model copies into its response and ticks off.
- Provide feedback loops: run validator, fix, repeat; build, look at the render, critique,
  fix, rebuild.
- Use examples to teach style (here: real pages from the reference and from the page
  library), not long descriptions.
- Consistent terminology throughout (one word per concept).
- No time-sensitive statements.
- Scripts solve problems instead of deferring them to the model; error messages name the
  element, the measured value, the limit, and the available alternatives.
- No unexplained constants; every threshold names the measurement behind it.

### 3.4 Evaluation-driven development

- Build evaluations before writing documentation: at least three scenarios that exercise
  real gaps; baseline without the skill; minimal instructions to close the gaps; iterate.
- Develop with two instances: one that writes the skill (A) and fresh instances that use
  it cold on real tasks (B). Observe B's behaviour (files read, order, what it ignored,
  where it struggled) and bring that back to A. The prototype did this informally: cold
  generator agents reported 71 friction items over six houses, most real (section 21.3).
- Test with every model tier the skill will run on (the guidance names a fast, a
  balanced and a strongest model). The prototype tested only one.

---

## 4. System overview

```
reference (pptx | pdf)                       user brief + data
        |                                            |
   [5] intake: triage, render                        |
        |                                            |
   [6] extract -> guide draft (values + provenance + open addresses)
        |                                            |
   [7] visual context: renders, gallery crops, exemplars, page library, house exhibit digest
        |                                            |
   [6.4] model completes open addresses -> guide (validated)
        |                                            |
   [8] template (reference master) or constructed blank + chrome
        |                                            |
   [8.4] round trip: re-build one reference page, judge + look
        |                                            |
   [9] model plans the section: storyline, page plan, variety plan  <-----+
        |                                                                 |
   [10] model writes page specs (roles, weights, exhibits, annotations)   |
        |                                                                 |
   [11] solver: measured fit, geometry, refusals with located reasons ----+
        |
   [13] emit pptx  ->  [14] gates (read-back, contrast, tie-outs, register, repetition, validation)
        |
   [15] render -> model critique on images (located findings) -> fix -> rebuild (capped)
        |
   [16] judge (style distance)  ->  report to user
```

Every arrow that returns to the model carries located information (element id, measured
value, limit), never a bare score.

---

## 5. Intake: reading any reference

### 5.1 Formats and classes

- **pptx**: the richest evidence. Read the OOXML directly (python-pptx is fine for writing
  but its reading API hides inheritance). Resolve inheritance fully: run properties come
  from the run, then the paragraph, then the shape's list style, then the placeholder's
  layout and master equivalents, then the master's text styles, then the theme; shape
  style references (`p:style/a:fontRef`) set a default text colour above the master
  default and below the run; table style `tcTxStyle` sets cell text colour. Colour maps
  (`p:clrMap`, overridable per slide and layout) apply before theme lookup. Reach the
  theme through the master's relationship, never by globbing theme parts (notes and
  handout masters carry the stock palette). All measured on real decks; see Appendix C.
- **PDF**: classify every page before mining (measured on 19 corpus PDFs: 8 are page images
  inside a letter-size print, not vector exports):
  - `vector`, `vector_with_image`: real type; mine it (a slide-shaped page with a pasted
    chart picture is still a vector page).
  - `raster_wrapper`, `raster_ocr`, `raster_only`: images; nothing on them is type
    evidence; the OCR or browser text layer gives a "house" of 1pt Times.
  - `other_size`: memo or filing text bound in front of the deck; exclude.
  The deck class is the majority class. Page size for raster decks comes from the image
  box (letter-ratio image = deck printed to letter 11 x 8.5 in; 4:3 = 10 x 7.5 in).
  Triage classified all 19 corpus PDFs with no deck misfiled against a reading of its
  renders (measured).
- **Rotated text** in PDFs (copyright lines set vertically) must be detected and either
  read with its rotation or excluded. The prototype counted a rotated line one glyph per
  run, producing 2 to 4pt size levels with up to 764 votes and a body size of 4pt, and
  mined it as four horizontal chrome items drawn reversed ("thgirypoC") (measured once).

### 5.2 Rendering

- Render with LibreOffice in a pinned container, one conversion at a time per process, an
  isolated profile per worker (`-env:UserInstallation`), `--nolockcheck --norestore`. An
  interrupted soffice leaves a lock in its profile; use a fresh profile per render.
- Render at 1600 px width for reading; produce a contact sheet (grid) of all pages.
- Report fonts: for every face the deck uses, what the renderer drew (via `fc-match`) and
  whether it is the face itself, a metric alias (layout-faithful, visually different:
  Arial as Liberation Sans), or a substitution (render is not evidence of fit). Report
  characters the drawn font cannot cover (tofu), and refuse to use crops whose faces
  cannot draw the deck's characters.
- Hidden slides are not exported by the renderer; count and report them.
- Long decks: the prototype's extractor took 18.6 minutes on a 205-page PDF with no
  progress output (measured once). Print progress and measure where time goes.

### 5.3 Scanned references (raster)

Pixels still tell: palette by painted area; text ink as the modal dark colour; chrome as
pixels holding one colour on at least half the pages (rules, bands, logo block, page
number area); margins from ink extents; line pitch by autocorrelation and a body size
from it. Measured on keybank rendered at 100 dpi and re-measured: surface and accent
exact, ink within 1 unit, left margin within 0.01 in, other sides within 0.08 in, body
11.7pt from a 14.4pt pitch against 12pt in the file. On real scans, line pitch held on 3
of 11 pages (measured), so treat it as weak evidence. Faces cannot be read from pixels:
the model looks at page images beside candidate fonts and names the family. Raster
measurements carry provenance `raster_inference` and confidence 0.5. Report effective dpi
honestly (the prototype once reported 69 px per inch where the image carried 104 dpi;
measured once).

The judge must not fingerprint a raster reference from its text layer (section 16.4).

---

## 6. The style guide

### 6.1 Purpose

The guide is the single source of style truth. Page specs refer to its roles; the solver
measures with its values; the emitter writes its values; the gates check against it. One
definition per concept (section 2.10).

### 6.2 Schema (top level)

Every value node carries `provenance`: `value_provenance` (observed | deterministic |
model_inference | raster_inference), `evidence` (slide numbers, shape ids, counts),
`frequency`, `master_membership`, `confidence`, and a `why` for anything the model wrote.

- `reference`: file, sha256, slide count, format; PDF text-layer triage (status, deck
  class, per-class counts, raster pages, slide box, size basis, print scale, effective
  dpi); page width and height in EMU and inches; layouts used.
- `typography`:
  - `families`: major, minor, fallbacks, and `substitutes` (a stand-in face name that MUST
    equal what `fc-match` returns in the renderer; the prototype measured with DejaVu Sans
    while LibreOffice drew Inter, so renders were not evidence; measured).
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
  - Role names are assigned by usage, not by convention: on keybank `color.accent1` is the
    observed light grey and the deep blue is the second accent (measured).
- `spacing`: steps `space.xs..xl`, `space.gutter`, `space.margin`, from measured gaps
  (cluster the observed gaps); margins per side; baseline grid if any; gap levels.
- `composition`: archetypes (clusters of pages by arrangement, with member pages), bands
  (title band, body band, footer band with EMU extents), column grids, alignment edges,
  and `consecutive_max` (the longest run of one archetype in the reference).
- `titles` (NEW; the prototype lacked it): register per title (topic phrase, question,
  claim sentence) with counts; length distribution in characters and words (median,
  max); line count distribution; where claims live when titles are topics (lead-in
  bullet ending in a colon, numbered takeaway row labels, a takeaway box, a subtitle).
- `register_stats`: per page counts by element kind (text, image, shape, table, chart,
  line), decoration count, container ratio, as 10th to 90th percentile bands, AND how
  exhibits are realised (native chart, native table, pasted picture, drawn shapes) so a
  house that pastes pictures does not make native exhibits read as "above".
- `density_bands`: words, elements, covered area per page as 10th to 90th percentiles,
  each with an evidence flag (no evidence is not zero).
- `exhibit_habits` (NEW): measured from the reference's own exhibits, by looking at
  them (section 7.3): exhibit types used, annotation moves and their frequency, emphasis
  devices (outline box colour and weight, shaded rows, subject colour), number formats
  (units line, $ placement, x suffix, parentheses, NM), legend and label habits, colour
  logic (single hue tints plus one "look here" colour, or categorical).
- `chrome`: list of items (rule, band, logo, label, page number) with geometry, z-order,
  rotation, fill and ink roles, anchor (master, layout, slide layer), and whether drawn
  per slide.
- `motifs`: recurring non-chrome devices with roles, preset shape, size and anchor
  (`region_edge`, `element_adjacent`).
- `tables`: header fill and ink roles, header bold, banding role, edge rules by class
  (table top, header bottom, row interior, table bottom, left, right, column interior)
  with width and colour role, cell padding role, alignment by column type, totals rule.
- `charts`: series colour roles in order, per chart kind (bar, column, line, pie): data
  labels, gridlines, legend, axis visibility, gap width, as observed.
- `shape_language`: corner radii (modal roundRect radius, share of rounded shapes, read
  from the file, never from renders), outline habits, shadow use (normally none).
- `imagery`: logo use, photography, icons.
- `floors`: per family of roles (body, annotation, display, chart) the smallest size the
  reference uses (`floor_pt`) and the absolute floor (section 11.5).
- `continuation`: how a page that splits continues (header repeat, "(cont'd)" mark,
  takeaway policy).
- `extra_roles`: model-added roles with hex and why.
- `derivation_rules`: how the palette and type ladder extend to roles never shown.
- `description`: the model's written description (summary, typography, colour, layout,
  tables, imagery, motifs, `never_does`, tone). Written after looking; read back while
  designing.
- `unresolved`: the open addresses with the reason each is open.
- `notes`.

### 6.3 Extraction method (deterministic)

- Walk every slide (hidden slides too, as evidence; mark them). Skip slides carrying this
  skill's origin tag (section 13.5) unless asked.
- Collect every run with resolved properties; histogram sizes; assign roles by position,
  placeholder type, frequency and context. The title role must come from title position
  evidence (the title placeholder or the top band), never from size votes alone: on a
  McKinsey PDF the prototype bound `type.title` to 44pt cyan numerals (20 votes) while the
  real page titles were 25pt white Georgia (measured once). When evidence conflicts, leave
  the role open for completion rather than binding the larger vote.
- Spacing from measured gaps between adjacent elements, clustered.
- Composition by clustering page arrangements (element boxes, normalised).
- Chrome by recurrence across pages and master or layout membership; for PDFs, by
  recurring lines and boxes across pages.
- Every value that cannot be proven goes to `unresolved`. The prototype's extractor
  matched the predecessor's on title, body, emphasis and caption sizes, surface and ink on
  four decks, and differed on 47 of 160 compared values (h1 and h2 sizes on two decks,
  rule and muted ink by deliberate change, spacing steps on two) (measured).

### 6.4 Completion by the model

- The model answers exactly the open addresses; a key outside `unresolved` is refused,
  except always-writable keys: `/description`, `/derivation_rules`, `/continuation`,
  `/typography/families/substitutes`, `/notes/*`, new `/extra_roles/<name>`, and new type
  roles at sizes the levels table shows (for raster references, whose levels table is
  empty, the model must be able to add levels it measured from images; the prototype
  could not, which blocked table and label roles on a scanned house; measured).
- Observed and deterministic values cannot be overwritten. If the model believes one is
  wrong, it reports it; the fix belongs in the extractor.
- The core must close: `type.title`, `type.body`, `color.surface`, `color.ink`,
  `color.accent1`, and one of caption, footnote or source line.
- `null` is a legal answer where the honest answer is "none" (no baseline grid, no
  geometric ratio). The prototype crashed on null (measured once).
- Accept the documented forms (for example an extra role as `{hex, why}` as well as a bare
  hex). The prototype documented one form and accepted another (measured once).
- Completion groups: when there are many open addresses, complete them in groups derived
  from the draft (not a hand-written list), the groups partitioning the open set; a group
  that names a role runs after the group that defines it. A single call handled 52 and 70
  open addresses with 0 to 1 retries in the predecessor (measured), so groups are for
  ordering dependencies, not because focused calls reason better (unmeasured).
- Every value comes from this reference. Low confidence beats convention: a chartless deck
  gets a chart language derived from its palette and register, not a stock one.
- Renders are evidence for colour, proportion and position; not for fit, line spacing,
  padding or rule weight.
- The draft's open list and the documented example completions must agree; the prototype's
  shipped example left 9 addresses the draft opened (measured once).

---

## 7. Visual context

The model sees. Give it pictures, chosen well.

### 7.1 Renders

All pages at 1600 px and a contact sheet. The model looks at the contact sheet once and at
full pages as needed. For small type use crops; a model that downscales a 1920 px render to
1456 px leaves 6.5pt text at 1.1 to 1.8 times its legibility ceiling (measured in the
predecessor for one model family).

### 7.2 Gallery: crops and exemplars

- Segment each page into components (title block, table, chart, panel, banner, takeaway
  box), crop them, cluster by appearance and structure, pick exemplars: one full page per
  composition family, plus crops.
- Pick crops by greedy set cover of the style tokens they show, not by recurrence
  (recurrence ordering lost 10 tokens on one deck; measured). Use an area floor of
  200 x 200 px, not a short-side floor (a short-side rule deleted each deck's most repeated
  banner; measured).
- 28 to 43 values per deck are drawn by the master and need full-page exemplars to be
  seen (measured).
- Each crop gets a caption and a skeleton line (the structure in words).
- The gallery must work for PDFs (the prototype's refused PDFs while the instructions told
  every user to run it; measured).
- A `pick --intent "<text>"` command returns the nearest exemplars and crops for a page
  intent. The prototype ranked by word overlap; "overlap 0 everywhere" means the reference
  has nothing for that intent, and the model must design from the guide and the library.
  Better: rank by structured tags (composition, exhibit type, data shape) produced when the
  model reads the reference (section 7.3). Unmeasured.

### 7.3 House exhibit digest (NEW)

During intake the model looks at every exhibit page of the reference (crops at readable
size) and records, per exhibit: type, data shape, the one message, annotation moves (with
what they anchor to), emphasis devices, number formats, legend and label handling, colour
logic. Aggregated, this fills `exhibit_habits` and `titles` in the guide. This is model
reading, structured; it turns "look at the reference" into data the model can consult
while designing.

### 7.4 The page library (NEW)

A curated set of about 40 to 60 excellent real pages from many houses (investment banks,
consultancies, research publishers), each tagged: house type, composition, exhibits,
annotation moves, emphasis devices, and one line on why it is instructive plus the
question a designer asked to produce it. Shown as examples (not templates) when the model
plans a page whose intent matches. The evidence pass that builds the first version is
described in section 19.4 and Appendix A.

Rules for the library:
- Real pages only. Hand-authored specimen pages scored 3 of 10 by the predecessor's owner,
  and judging output few-shot conditioned on those same pages is circular (measured).
- 3 to 5 diverse examples per intent (external guidance; unmeasured here).
- The reference's own pages always outrank library pages; library pages teach reasoning
  and craft, the reference teaches style.

---

## 8. Templates and chrome

### 8.1 pptx reference

The template is the reference with every slide removed; masters, layouts, theme and chrome
intact. PowerPoint opens and re-saves such packages without repair and draws chrome once
per slide (measured in the predecessor). Page numbers and footers the reference carried on
its slides are copied from the layout to each new slide.

### 8.2 PDF reference

A blank package at the reference's page size, with chrome drawn per slide from the guide:
rules, bands, logos, footer labels, page number fields, surface colour. Requirements the
prototype failed:
- Draw in the reference's z-order. The prototype drew a full-page white band last, burying
  the title band, the rule and the page number (measured once).
- Reserve only the zones chrome actually occupies. Bands anchored to the full page
  reserved the whole page, leaving no content area (measured once, a blocker).
- Chrome text carries the reference's observed ink and is scored by the contrast gate.
  The prototype drew "McKinsey & Company" and the page number in default black on navy
  pages, invisible and unscored (measured on two houses).
- Rotated chrome keeps its rotation, or is refused.
- A logo the reference shows must be carried: extract the logo image from the reference
  (crop from the PDF or the pptx media) and place it. The prototype drew an empty
  outlined placeholder; the blind rater named missing logos as a tell (measured once).
- No inherited theme effects: rules drawn on a blank template picked up a grey drop shadow
  from the theme's effect style in LibreOffice (measured on two houses). Write effect-free
  shapes explicitly.

### 8.3 Slide-layer chrome in pptx references

Logos, rules or labels the reference pastes on every slide (not on the layout) are drawn
on every generated page; chrome the layout carries is inherited, never redrawn.

### 8.4 Round trip (prove the chain)

Before designing, import one reference page into a page spec (roles and weights; no
coordinates survive), build it on the template, judge it and look at it beside the
original. The prototype's keybank round trip scored 0.057 to 0.056, inside the house's own
spread (measured). The look matters more than the number: once the judge said 0.083 while
labels were black and left-aligned because the reader had missed a shape-style text colour
on both sides (measured once). The import must work for PDFs (the prototype's produced
empty paragraphs for PDF pages; measured on three houses).

---

## 9. Planning a section

### 9.1 Storyline and page plan

The model writes a plan before any page: for each page, the one message, the evidence that
proves it, the exhibit, supporting text, data needed, the composition intent (which element
dominates, or how co-equal blocks divide the page), split boundaries if it will not fit, and
the title in the HOUSE's register and length (from `guide.titles`).

### 9.2 Figures

Use the user's figures byte for byte. Never invent a number; a missing figure is a named
placeholder. Every figure stated in a title, lead-in or callout is computed from the
exhibit's own data before writing (midpoints, medians, counts above a line). The prototype
once wrote "$11.40 sits above every method's midpoint" where two midpoints were above it
(measured once). A generator script that computes and asserts every stated figure worked
well in the cold runs (all six houses used one).

### 9.3 Variety plan

Before building, the model lists the planned composition and exhibit type per page and
compares against the reference's measured variety: in three bank pitch books, consecutive
content pages differ in composition 83% to 90% of the time, and no composition runs longer
than 2 pages; the repeats are deliberate parallels (two scenario pages, matching summary and
conclusion) (measured; Appendix A). The plan states which repeats are deliberate and why.
The predecessor gave its designer a composition-history digest and an instruction to vary;
one arrangement still held 6 of 19 designs where the register allowed 1, so a prompt alone
did not produce variety (measured). Variety must be planned at section level and checked by
the repetition gate (section 14.7), which compares content regions, not page furniture.

### 9.4 Co-equal content

"One element dominates" without guidance for co-equal blocks produced dashboard-like panel
grids on multi-block content on two model tiers (measured once). Ask the model to rank
blocks by how directly each proves the message and size them by that rank.

---

## 10. The page specification language

### 10.1 Shape

A page is a tree. A region lays out children with:
- `flex`: direction (row | column), `gap_role`, `pad_role`, `align` (start | center |
  end | stretch), `justify`, child `weight`s.
- `grid`: rows, cols, gutter role, named areas.
A region may carry `fill_role`, `line_role` and `pad_role` (a filled, padded box such as a
takeaway panel).

Elements:
- `text`: paragraphs, each with type role, text, bullet level, `ink_role`, `align`,
  emphasis runs.
- `table`: columns (value kind: text | number | currency | percent | multiple | date;
  `width_share` or `min_width_role`; alignment override), header rows with spanners, body
  rows, row classes (totals, subtotal, emphasis, statistic, subject), per-table overrides of
  banding, alignment and fills as roles.
- `chart`: the full chart spec (section 12.1).
- `image`: an asset reference (logo, picture) with fit mode.
- `rule`, `rect` (with preset shape), `connector`/`arrow`.
- `annotation`: shapes anchored to another element's data coordinates (section 12.3).
- `component`: a kind and its data (section 12.5).

Every size, colour, gap and font is a role. A literal value is refused with the list of
available roles. An unknown key is refused by name (the prototype silently dropped
emphasis-row keys written on the wrong node; measured once). Keys that have an obvious
alternative spelling (for example OOXML's `nextTo` for `next_to`) are accepted or refused
with the correct spelling named.

### 10.2 Limits

Any structural limit (tree depth, node count) is documented and each violation has its own
message (the prototype merged "duplicate id", "over 400 nodes" and "depth over 5" into one
message, costing builds; measured on two houses). Whether depth 5 is needed is unmeasured.

### 10.3 Conventions enforced

- A title is held to the reference's title band; a title needing more lines than the house
  ever writes is refused first, before other violations (they follow from it).
- Chrome zones are reserved automatically; content never runs under footer furniture.
- A page with a table or chart and no source or footnote paragraph is refused.
- Ids are unique per page; elements that are the same thing across pages (title, source
  line) share ids so position drift can be checked; different things never share ids
  (the prototype reported drift between unrelated elements that happened to share an id;
  measured once).

### 10.4 Capacity query

Before writing text, the model asks the solver how many lines and characters each region
holds per role, from the measured ruler, and writes to that budget.

---

## 11. Text measurement and the layout solver

### 11.1 The ruler

- Measure with HarfBuzz shaping on the actual font files (fall back to Pillow only if
  HarfBuzz is unavailable; they agreed on 89 of 90 recorded wrap cases, HarfBuzz on 90 of
  90; measured).
- Measure whole runs, never sums of fragments.
- PowerPoint fits less text than LibreOffice on 92 of 600 measured boxes; shrink the width
  budget by a measured epsilon (5,933 EMU with the Pillow ruler, 20,234 EMU with HarfBuzz)
  so a measured line never runs long in PowerPoint (measured).
- Line pitch is 1.2 times the font size, font-independent (measured on 7 families); font
  metric tables are wrong by up to 20% for this purpose.
- Wrap at spaces and break opportunities; never inside a word. A word wider than its line
  refuses the page by name (`word_split`) rather than breaking mid-word (the prototype
  wrote "Consideratio" / "n" and reported fit; measured once).
- Non-breaking pairs: a figure and its unit, a currency mark and its figure, a period
  prefix and its year (`$1.2 bn`, `EUR 40 mm`, `FY 2024`, `12.5 %`).
- Write the measured line breaks into the file as literal breaks so PowerPoint cannot
  re-break differently.
- Metric aliases: one table, fontconfig's 17 binding="same" classes (Arial = Liberation
  Sans, Calibri = Carlito, and so on). Helvetica is not an alias of Liberation Sans. A face
  with no alias and no installed file is refused until the guide names a stand-in that
  equals the renderer's `fc-match` result.
- Italic roles need an italic face; a stand-in without italics (DejaVu Sans in the
  prototype's sandbox) silently drops italic capacity (measured once).

### 11.2 The solver

- Exact integer EMU arithmetic. Allocate flexible shares in whole EMU (a 1-EMU rule must
  stay 1 EMU; the prototype's rounding produced 0 or 2 EMU on 6 of 12 tested heights;
  measured).
- Region height is its content height unless it holds an element with no intrinsic height
  (chart, image, rule) or carries a weight inside a column. `align: stretch` does not make
  a row flexible. A flexible region never gets less than its content. (These replaced
  rules that gave a row of fixed figures half the spare height and starved a table;
  measured.)
- Every element is held to its own box: text taller than its box and table rows taller
  than the table's box are violations, wherever the element sits (the prototype never
  checked a table that was a direct child of a stretch row against its fitted height;
  measured).
- Tables: fit column widths by measured content, honouring `width_share` and
  `min_width_role`; report per-column width deficits; row heights are lines x 1.2 x size
  plus cell margins, which is what PowerPoint realises (measured); report
  `rows_to_fit_slide` for splitting.
- Type scale descent: if the page does not fit at scale 1.0, step the whole type ladder
  down uniformly toward the floor, re-solving each step.
- The emitter writes the solver's resolved sizes (size, line pitch, spacing, tracking,
  cell insets) for exactly the scale chosen. The prototype solved at 0.89 and wrote 12pt
  table cells and a 25pt title, producing overlapping text that every gate passed (measured
  once, a blocker). One resolved entry per element, produced by the solver and consumed by
  the emitter; the emitter refuses an element that arrives without it.
- Output on failure: `status: unfittable`, the smallest admitted scale, every violation
  located (element id, needed EMU, budget EMU), and for each table the body-row count at
  which to split. Nothing is ever dropped to make a page fit.

### 11.3 Density as a search

Density is a loop the model runs: fill a page, build, read the report, add the next item
while it fits within the house's upper density band, re-arrange or split when it does not.
The model's moves in order: re-arrange (two columns, table beside chart, a compact
component variant), cut words, split at a declared boundary with the house's continuation
convention. The predecessor's hand-built specimen had median ink coverage 0.21 to 0.25
against 0.576 for 96 corpus pages; what closed the gap was adding missing exhibits, not
enlarging existing ones (measured).

### 11.4 Fit read-back

After emitting, read the written file back and re-measure every text element and table
against its solved box. A shape that outgrows its box refuses the page as "emitted text
overflows", naming the shape. Verified non-tautological in the prototype: restoring the
old emitter made the read-back refuse six shapes (measured).

### 11.5 Legibility floors

- `floor_pt` per role family is the smallest size the reference uses; never generate below
  `max(floor_pt, absolute_floor_pt)`.
- `absolute_floor_pt` = 7.0pt. The predecessor measured legibility on two screen media with
  one rater: 6.0pt Arial; 6.5pt Calibri regular, 7.0pt bold. Print was not measured; for a
  printed deck, never go below the reference's own floor. The model may lower a floor in
  completion only when the reference's own captions show the smaller size.

---

## 12. Exhibits

### 12.1 Charts

Native charts written from a complete spec the model writes:
- `type`: any PowerPoint chart type (column and bar clustered, stacked, 100% stacked; line,
  with markers; pie, doughnut; area; XY scatter, with lines; bubble; radar; combo with
  secondary axis).
- Series: name, values (XY as [x, y] pairs), `fill_role` or `"none"` per series and per
  point, `line_role` and width, smooth, marker; data labels per series and per point
  (show, position, number format, type role, `ink_role`, custom text); secondary axis.
- Axes: visible, line role and width, gridlines, number format, reverse, min, max, major
  unit, tick marks, tick label position, crossing.
- `gap_width`, `overlap`, legend (position, hidden entries) or `"none"`, chart text role
  and ink, plot fill, title.
- Plot area written as a MANUAL layout (fixed inner plot rectangle) so that data
  coordinates are computable in EMU (section 12.3).
- Colours are roles only; literal hex refused; unknown keys refused.
- `c:varyColors val=0` is always written (file safety: the renderers read its absence
  oppositely; PowerPoint paints one series in five theme colours; measured).
- Every choice left out is written as a named neutral value and reported per page.
- No special chart kinds (no "waterfall" or "football field" type): they are recipes over
  the general spec (invisible base series with fill none; a zero-height carrier for
  labels; an invisible low series for ranges). Recipes are documentation the model adapts.
  An optional `bridge` declaration on a chart (deltas and totals) is tied out by the build:
  each total against the running sum and each drawn span against its step.
- Known renderer hazards (measured): an XY scatter series that does not set `smooth`
  crashed the prototype's writer; LibreOffice drew nothing for the first XY scatter series
  in one case until series order changed (cause not found); LibreOffice wraps category
  labels and in-bar data labels mid-word in narrow slots. The build must measure category
  and data labels against their slot (upper bound of the category width; bar thickness for
  centred labels) and refuse a label that will break mid-word, naming it.

### 12.2 Tables

- Header fill and ink, rules by edge class, banding, padding, alignment by value kind, from
  the guide; per-table overrides as roles.
- Shared edges written identically on both adjacent cells: PowerPoint keeps the first
  declared side and writes it back; LibreOffice draws the heavier (measured).
- Strokes below 0.5pt only when the guide declares them (0.48 px in PowerPoint vs 1.27 px
  in LibreOffice; measured).
- Row classes: totals (tie-out checked), subtotal, statistic (median, mean: skipped by
  tie-out), subject (set apart), emphasis (requires an explicit fill role or `none`).
- Number craft the model applies (Appendix A): units line or units column; $ only on first
  and total rows; x suffix on multiples; parentheses for negatives; NM and n.a. written
  out; footnote markers resolving in the footer zone; sorted order where the message is a
  ranking.

### 12.3 Annotation layer (NEW; the core missing capability)

Humans annotate intelligently. In three native bank pitch books, the most common move was
an outline box around the region where the claim lives (14 of 33 data exhibits); others
were column-group spanners, shaded key rows, reference lines at a decision value, a
highlighted subject in one colour with peers in another, selective data labels, sorted
order, footnote markers, callout pointers (measured; full table in Appendix A). 27 of 33
data exhibits there were pasted pictures with annotation shapes laid over them at absolute
offsets (measured). The prototype could not place a shape at a data point inside a native
chart at all, so the model could not annotate.

Build:
- An `annotation` element anchored to another element's data coordinates:
  - for charts: `{category, series}` (a bar or point), a category span, a value (a
    horizontal or vertical line at a value), a region (categories x value range);
  - for tables: a cell, a cell range, a row, a column, a header group;
  - for text: a paragraph.
- Kinds: outline box (line role, width, padding role), filled band (fill role,
  transparency as a role), reference line with label, arrow or pointer from a label to an
  anchor, bracket over a span with a label (for sums or CAGR), callout box with leader
  line, number badge.
- Placement: computed deterministically from the anchor. For native charts this requires
  writing the plot area as a manual layout and computing each category's band and each
  value's position from the axis scale (min, max, reverse, gap width, overlap, series
  count). Verify against renders in BOTH LibreOffice and PowerPoint before relying on it:
  draw a 1-px marker at computed positions and measure the render (unmeasured; this is the
  first experiment to run).
- Collision contract: an annotation may overlap only its anchor; it must not cover data
  labels, axis labels, other annotations or text outside the exhibit; the solver reserves
  room for labels placed outside the plot.
- Annotations are scored by the contrast gate like any text.
- The model decides whether and what to annotate. The skill supplies the measured
  vocabulary, the house's own habits (`exhibit_habits`) and the reasoning questions
  (Appendix B). Nothing annotates automatically.

### 12.4 Diagrams

Process flows, timelines and Gantts, matrices (with a written reading rule and a legend for
cell states), spectra (options on a continuum with a pointer to the recommended one),
org-style trees, logo walls, tombstone grids. Built from the page grammar or components.
The prototype's Gantt built from a grid of filled text boxes counted every cell as an
element, reading "above" the density band; element counting must understand that a
diagram is one exhibit (measured once).

### 12.5 Components

A component is a function `expand(data, box, guide) -> subtree` in the page grammar,
roles only, proportions as weights from the data, fixed heights as spacing steps, variant
chosen by what the box can hold (measured through an API, never estimated: `text_width`,
`line_pitch`, `paragraph_spacing`, `fit_epsilon` exposed to components from the solver's
own ruler).

Contract and admission:
- A schema for its data, a size domain, and four test boxes: three shown and one held out
  with different data.
- Check: determinism (expand twice in separate interpreters under different hash seeds;
  any difference in list order fails and names the path); all four boxes solve with no
  violation; ids that must stay on one line never wrap (`single_line_ids`); contrast
  passes; the package validates; and geometry tested against the master's and layout's
  own shapes (the prototype's check passed while the master's top rule struck through a
  football-field bar; measured).
- Admission is bound to the guide it was checked with (hash). A component admitted on one
  house overflowed on another whose 12pt floor left no headroom (measured once).
- The model writes new components when nothing draws what a page needs; the build reports
  a component admitted against a different guide.

The prototype admitted four: football field, title block, bullet stack, KPI row.

---

## 13. Emitting the PowerPoint file

### 13.1 Rules

- Write on the template (reference master) or the constructed blank.
- Every value resolved from the guide through the solver's resolved entries; nothing
  inferred in the emitter; no ink swaps, no colour picks.
- `word_wrap` set explicitly true (python-pptx's default centres text in LibreOffice;
  measured).
- Body properties written fully (insets, anchor, autofit off).
- Never write negative `spcPts` (LibreOffice then draws nothing); a master that spaces by
  percent (`spcPct`) is converted to points at the boundary (measured).
- A schema-invalid spacing value once blanked sixteen bullets on a page that validated
  and judged clean (measured once); validate against the schema, and read the render back.
- Effect-free shapes (no inherited shadow).
- Bullet glyph with its bullet font.
- Page number as a field where the layout carries the field; never a typed number.

### 13.2 Package hygiene

Unique slide ids; relationship targets present; one layout per slide and one master per
layout; content types complete; shapes inside the page; charts parse.

### 13.3 Speaker notes

State that figures are illustrative when they are; carry sources.

### 13.4 Determinism

Same inputs produce byte-identical packages apart from timestamps.

### 13.5 Origin tag

Every generated slide carries a tag (`p:custDataLst` tags part, name `pptx-skill` or the
new skill's name, value `generated`), which survives a PowerPoint save (measured in the
predecessor). Extraction and gallery skip tagged slides by default, so an extended deck can
be its own reference without learning from generated pages.

---

## 14. Gates

All gates report per page, located, before figures. A refusal makes the page unfittable
with a reason; a warning never refuses.

### 14.1 Package validation

Section 13.2, plus `--render` mode: render, extract text with pdftotext, and name every
paragraph that did not draw. Wrapped names reported as not drawn when visible is a known
false positive (measured once); match normalised text.

### 14.2 Renderer-divergence check

On the saved package: shared table edges declared differently on two cells; strokes under
0.5pt not declared by the guide; gradients; a chart without `c:varyColors`; a run below its
role's floor; a typed page number where the layout has the field (all measured hazards).

### 14.3 Fit read-back (section 11.4)

### 14.4 Contrast

- Every text run, every table row class, every chart text (data labels per series and per
  point, axis labels, legend), every annotation label and every chrome text, scored WCAG
  2.2 against the fill actually behind it: the element's own fill, else the nearest
  enclosing filled region, else `color.surface`; for a chart label inside a mark, the mark's
  fill; outside it, the plot fill or the page; both when the position is open.
- Below 3.0:1 refuses; below AA (4.5:1, or 3.0:1 at 18pt or 14pt bold) warns.
- House precedent (NEW): a colour pair the reference itself uses at that size or smaller is
  allowed and reported as precedent. Without it, a house can never use its own signature
  colour: BCG's title green on white reads 2.51:1 (measured once).
- Undecidable cases (text over images; fills left to the renderer) are listed, not passed.
- The fix is always a role change by the model, never an automatic ink swap.

### 14.5 Tie-outs

Totals rows: each numeric column's body sum against the totals cell at the cell's own
decimals ($ , % x stripped; parentheses negative); statistic rows skipped; n.a. cells skip
the column and are named. Chart bridges: as in 12.1.

### 14.6 Register and density

Per page counts by kind, decoration count and container ratio against the reference's
bands; words, elements and covered area against density bands. Each verdict is below, in
band, above, or NO EVIDENCE (section 2.8). A diagram counts as one exhibit.

### 14.7 Repetition

Arrangement similarity of consecutive pages over CONTENT regions only (exclude chrome and
elements identical on every page; the prototype's metric was dominated by the frame, so any
two pages scored about 0.5 before their content was compared; measured on two houses). Flag
runs longer than the reference's `consecutive_max`.

### 14.8 Position drift

An element present on several pages (by shared id) whose position moves by more than one
spacing step is reported.

### 14.9 Source line

A page with a table or chart needs a source or footnote paragraph.

---

## 15. Rendering and the self-critique loop

### 15.1 What the loop is

After each build the model looks at every rendered page at full size and writes located
findings as a reviewer would: element id, what is wrong, the change (for example
"takeaway: competes with the table; drop the fill, keep the rule"). Never a score. Then it
fixes the spec and rebuilds.

### 15.2 What it looks for (in order)

Text cut at a box edge; elements sharing area; labels wrapping mid-word; source line
touching footer furniture; uneven gaps; a title that drifts between pages of one kind;
inconsistent chart text styling across charts; a figure split from its unit; placeholder
text; and then design: Is the message findable in two seconds? Is the exhibit annotated
where the claim lives? Would a managing director mark this up, and what would they write?
Does it look like the reference's pages, side by side? Does it look like a generated deck
(card grids, equal tiles, KPI tiles, rounded everything, centred text, three of
everything, uniform spacing, one composition repeated)?

### 15.3 Caps and keep-best

The loop is capped (the prototype's cold runs were allowed 8 builds; they used 4 to 7).
Keep the best build by gate status and critique, not the last. Score-chasing loops are
forbidden.

### 15.4 A second reviewer

Optionally, a separate reviewer call on a different model family than the designer
reviews renders against the reference pages and returns located patches (never rules on
measurable geometry; validators own that). The predecessor measured 10 of 10 findings
located on real element ids at about 9 to 11 seconds per review; whether findings steer the
next revision was not measured, and the reviewer's agreement with humans was never
calibrated. Treat as unmeasured until calibrated against blind-round ratings.

### 15.5 Renderer fidelity

Renders are LibreOffice. Measured differences: text (solved by writing measured breaks),
table edges and thin strokes (section 14.2), chart label wrapping. Open the final deck in
PowerPoint at least once per release (the prototype never did).

---

## 16. The style judge, and its limits

### 16.1 What it is

A fingerprint per page of style distributions, compared with a distance:
families, size histogram, size ladder, title size, bold ratio, text colours, fills,
alignments, element kinds, background, margins, coverage, element count, plus two layout
gates: overlap (pairwise intersection of content shapes over their area) and overflow
(paragraphs re-wrapped with the solver's ruler against their boxes). Component weights are
fitted from each component's 1-nearest-neighbour accuracy above chance on held-out pages.

### 16.2 Verdict

Filed under the reference when: nearest to the reference among a panel of other houses;
inside the reference's own spread (90th percentile of leave-one-out distances of the
reference's own pages); layout clean (overlap and overflow below 0.2 of their span); every
page fit and the package valid. Decks inside the reference's own spread are reported as the
same house, not as rivals. The panel is fixed (not chosen by the model).

### 16.3 Calibration (measured)

157 of 171 held-out slides over 8 houses filed correctly with fitted weights, 132 with
equal weights (binomial chance bound 30). Copying a master verbatim is flagged off-style.
Five deliberately wrecked decks in a house's clothes once filed at 0.013 to 0.192; adding
the overlap and overflow gates made all five fail. The skill's best sections scored 0.059
to 0.175 and were filed in five of six houses.

### 16.4 Limits (measured)

- The judge does not track human perception of real versus generated. In the blind round,
  keybank (0.085) and netflix (0.068) were filed close to their references, yet the rater
  caught every generated page in both; Goldman (0.584, not filed, because the judge read a
  scan's OCR layer) fooled the rater 4 of 5 times; Bain (0.059) fooled 3 of 5. Six houses
  and one rater are too few for a correlation, but "filed" clearly does not mean "passes as
  real". Do not present judge scores as quality.
- It cannot see content craft: title register, annotation, exhibit choice, variety,
  figures. These need the critique loop and the blind round.
- Raster references must be fingerprinted from raster measurements, or the judge must say
  it cannot judge (never a confident wrong number).
- Overflow measured on the file must use the same line pitch and spacing rules as the
  solver; the prototype's judge and solver once disagreed and the judge's overflow named no
  shape (measured once; the judge was right).

---

## 17. Editing an existing deck

- Commands: text per slide (tables as rows, joined with spaces, not run together as the
  prototype's did), layouts and placeholders with boxes, template with kept slides,
  duplicate, delete, clean, validate.
- Existing slides are the reference; they are not re-solved or restyled. New pages are built
  on the template that keeps them. Structure first (order), content second.
- Extract the style from the deck itself (skipping tagged generated slides).

---

## 18. Evaluation program

Unit tests are not checked in (owner's choice); every proof is an end-to-end run with its
output recorded beside the claim it supports. Evaluations are scenario files plus a human
round.

### 18.1 Scenario evaluations (build these first)

At least these, each a reference plus a brief plus data plus expected behaviours:
1. Native pptx bank pitch book, valuation section with comps, football field, precedents,
   pro forma bridge, process timeline.
2. Native pptx financing deck: alternatives comparison, credit impact, dilution, maturity
   profile.
3. Vector PDF consulting deck (navy pages, serif titles): governance diagnostic with
   benchmarks, skills gap, operating model, roadmap.
4. Vector PDF consulting deck with a signature colour below 3:1 on white (BCG green):
   budget impact with scenarios, sensitivity, recovery path.
5. Older vector PDF diagnostic with title band and heavy rule: cost baseline, spans and
   layers, procurement, implementation plan, savings bridge.
6. Scanned PDF bank board book (raster only, logos, DRAFT stamp): credentials, league
   table, deal list, team, buyer universe.
7. Extend an existing pptx deck with three pages in its own style.
Expected behaviours are checkable statements (title register and length within the house's
distribution; every exhibit annotated where the house annotates; composition variety at or
above the house's; zero gate failures; figures tie; logos present where the house shows
them).

### 18.2 The blind round (primary success metric)

- Per house, 5 real pages from the reference and 5 generated pages, normalised to the same
  pixel size, format and encoding (re-encode all to one format; the prototype's real scan
  pages were twice the file size of generated ones), file names and ids hashed, order mixed
  within house.
- Remove visible non-design tells where possible and record those that remain (the
  prototype's McKinsey real pages carried a gradient at the edges and its Goldman real
  pages carried scan texture).
- The rater guesses real or generated and rates quality 1 to 5 (1 would not send, 3 usable
  with edits, 5 client-ready), with an optional note.
- Score: accuracy per house and overall with the binomial tail probability; quality means
  real vs generated; which generated pages fooled the rater; notes.
- Prototype baseline (one rater who knows the project; 6 houses; 60 pages):

| House | Correct of 10 | Generated called real | Real quality | Generated quality |
|---|---|---|---|---|
| keybank (pptx) | 8 | 0 of 5 | 3.6 | 2.4 |
| netflix (pptx) | 9 | 0 of 5 | 3.8 | 2.2 |
| McKinsey (vector PDF) | 8 | 1 of 5 | 2.6 | 2.6 |
| BCG (vector PDF) | 8 | 0 of 5 | 4.0 | 3.2 |
| Bain (vector PDF) | 6 | 3 of 5 | 3.0 | 3.4 |
| Goldman (scanned PDF) | 6 | 4 of 5 | 4.2 | 3.8 |

  Overall 45 of 60 (chance 30, P(X >= 45) = 0.00007); quality real 3.53, generated 2.93;
  pages guessed real were rated 3.77, guessed generated 2.66. Rater notes: "Chart variety
  and layout variety in generated slides are low. Generally the same patterns with
  different colours"; "The choice of charts here actually match the data being represented
  and is well laid out" (on a real BCG page rated 5); "Logos. Generated slides have none".
- Use more than one rater when possible; record rater background.

### 18.3 Cold-agent runs

For each scenario, a fresh agent with only the skill builds the section, with a build cap,
and returns: what it did, what it could not do, and a friction list (what, repro,
severity). Friction is the primary input for the next skill revision. The prototype's six
cold runs produced 71 friction items; on reproduction, the large majority were real (the
fixers reproduced all 8 items in the first scope they took).

### 18.4 Model matrix

Run the scenarios on each model tier the skill supports. Record per tier: gate failures,
builds used, critique findings, blind-round results.

### 18.5 Regression evidence

Keep re-runnable scripts for every measured claim (judge calibration, ruler agreement,
round trip, raster read-back, triage) and re-run them before every release. The prototype's
re-run reproduced almost every number and found stale documentation figures (147 of 161
vs 157 of 171; 0.085 vs 0.086 vs 0.079 quoted for the same section); documents must cite
the run that produced each number.

---

## 19. Evidence: what was measured

### 19.1 About the instruments

Collected in sections 5, 7, 11 to 16 and Appendix C, each with its measurement.

### 19.2 About the model's behaviour

- With chart and table design handed to the model, cold agents composed exhibits code
  never anticipated: a horizontal bridge, a Gantt from a stacked bar with an invisible
  offset series, a regression scatter, a football field as a stacked bar; all six houses
  produced 5-page sections; five of six were filed by the judge (measured).
- Cold agents spent 4 to 7 builds per section of 5 pages; each read every render after
  every build (measured).
- Every cold agent wrote a generator script that computed every stated figure and asserted
  the arithmetic (measured; emergent, not instructed in detail). Keep and encourage it.
- Agents worked around skill defects by hand (drawing the title band as page content
  because chrome buried it; measuring sizes from a 220 dpi render because the raster tool
  reported the wrong dpi) and reported them (measured). Work-arounds are friction items.
- Single-attempt acceptance of a design model in the predecessor rose from 0.021 to 0.274
  on one house and from 0.253 to 0.432 on another against a 0.80 target; most refusals
  were schema and guide gaps, not model craft (measured). Fix the pipeline before blaming
  the model.
- A "reasoning" field in the structured output had no measured win on correctness across
  three models (20 tasks x 5 repetitions); design quality was not measured. Do not add one
  without a design-quality measurement.

### 19.3 About human pages (corpus evidence, partial at time of writing)

Readers looked at sampled content pages across the corpus (Appendix D). At the time of
writing, three of six groups had reported (320 pages): native-pptx bank pitch books (51
pages), PDF bank pitch books (184 pages), and four McKinsey decks (85 pages). Consulting
(BCG, Bain, more McKinsey) and a market-research chart book were in progress. Each page
record holds composition, title register and length, text hierarchy, exhibits with type,
data shape, message, every annotation move and its anchor, emphasis devices, craft details,
density, and the page-order sequences. Summary in Appendix A. The headline findings:

1. **Titles are house-specific, and banks use topics.** Bank decks: 48 of 51 (pptx) and 179
   of 184 (PDF) titles are topic phrases of about 4 to 6 words; 2 of 235 are claims.
   McKinsey decks: 43 topic, 41 claim, 1 question of 85, varying by deck (one deck 23 of 30
   claims, a memo 0 of 12). When the title is a topic, the claim lives elsewhere: a lead-in
   bullet ending in a colon, a takeaway band or sidebar, a kicker, numbered takeaway rows,
   or the memo prose; on many bank pages there is no explicit claim at all.
2. **Annotation is near-universal on data exhibits, and its moves are house-specific.**
   Charts with no annotation at all: 1 of 101 in bank PDFs; 4 of 57 data exhibits in
   McKinsey (all line charts); 3 of 33 in bank pptx. The commonest moves differ by house
   type: bank decks use data labels on every point, column spanners, shaded totals,
   footnote markers, subject highlighted against grey or uniform peers, brackets over
   category groups, NM markers, outline boxes or circles around the point that matters,
   median rows highlighted, reference lines at a decision value; consulting decks use
   value labels instead of axes, reference or target lines, highlight-one-grey-the-rest,
   delta or growth ovals and arrows, callout boxes with leaders, event markers. CAGR arrows:
   0 in bank decks (growth goes in a CAGR column or inset table).
3. **Moves follow data shape.** Horizontal bars (rankings) are labelled, sorted and
   highlight the subject; stacked columns show totals above the stacks; indexed lines use
   end-of-line labels instead of legends; price lines carry event markers and an inset
   returns table; football fields carry a reference line at the current or offer price;
   comps tables highlight the median row; projection tables shade totals and italicise
   ratio rows.
4. **The annotation sits where the claim lives.** Examples: a box around only the scenario
   region of a sensitivity grid that the argument depends on; boxes only on shortfall
   years, with no box on the one scenario that is the exception the claim names; the
   subject company in red, peers in blue, with one company order held across four panels so
   the reader can find the subject; a single current-price line through a football field,
   with the judgement the chart cannot show put in a bullet.
5. **Colour is restrained.** Bank pptx: series in two tints of one navy; red only as "look
   here"; categorical colour only for the subject; no icons, check marks or big-number
   callouts.
6. **Variety is high, and repeats are deliberate.** In bank pptx decks, consecutive pages
   change composition 83% to 90% of the time; no run exceeds 2; repeats are deliberate
   parallels. Bank PDFs: 51 distinct composition types over 184 pages.
7. **Text adds what the exhibit cannot.** Assumptions, caveats, history, the implication
   (for example "consistent with a ~15% impact on prescribers actually called"); it rarely
   repeats the exhibit.
8. **Craft details are many and small.** Units line on most numeric pages (18 of 24 in
   bank pptx; on every currency page); $ on first and total rows only; x on multiples;
   parentheses for negatives; NM written out; footnote numbers resolving to a bold
   "Source:"; the subject row set apart; status tags (PRELIMINARY, ILLUSTRATIVE, DRAFT);
   continuation marks; logos as category labels.
9. **Exhibits in real bank decks are often pictures.** 27 of 33 data exhibits in the bank
   pptx decks were pasted pictures of spreadsheet output with annotation shapes laid on top
   at absolute offsets. Generating native charts is still right (editable), but annotation
   must be placeable over them precisely.

### 19.4 The page library

The evidence pass also curates the 40 most instructive pages with tags and the question a
designer asked to produce each; this becomes the first page library (section 7.4).

---

## 20. What the prototype built, and how each part fared

Python 3, about 15 scripts plus documentation, one skill file. Listed so you know what has
been proven possible, what to keep in spirit, and what failed.

| Part | What it did | Status |
|---|---|---|
| OOXML and PDF reader | Inheritance-resolved runs, shapes, tables, charts; PDF reading with pdfplumber; page triage; origin tags; corner radii | Worked on all corpus decks; PDF rotated text and title binding wrong (5.1, 6.3) |
| Style extractor | Draft guide with provenance and open list; levels, roles, colours, spacing, composition, chrome, motifs, register and density bands, floors | Matched predecessor on core values; failed on PDF density bands (zeros), rotated text, title binding; 18.6 min on 205 pages |
| Completion folder | Applies the model's answers; refuses answers to non-open or observed addresses; core closure; partial mode | Worked; crashed on null; rejected a documented form |
| Raster instrument | Palette, ink, chrome mask, margins, line pitch from scans | Read-back exact on a rendered deck; weak line pitch on real scans; dpi misreport |
| Renderer wrapper | LibreOffice to PNG, contact sheet, font report with alias and tofu coverage | Worked; no fonts report for PDFs |
| Gallery | Component crops, clustering, exemplars, skeletons, manifest, `pick --intent` | Matched predecessor counts on three decks; refused PDFs; word-overlap ranking weak |
| Solver and ruler | Flex and grid layout, measured wrap, table fitter, scale descent, capacity | Exact match to predecessor on 383 boxes; several height rules wrong (11.2); fixed in a later pass |
| Emitter | Slides on template; text, tables, native charts from a full spec; chrome drawing; origin tags; varyColors | Wrote unfitted sizes when scale < 1 (fixed); chrome z-order, ink and reserved zones wrong; theme shadows; header/cell roles ignored |
| Build orchestrator | Solve, emit, validate, render, judge, and gates (contrast, register, repetition, tie-outs, source line, density, drift, chart defaults) | Worked end to end; gates had blind spots (chrome text, frame-dominated repetition, zero bands) |
| Component system | Contract, determinism check, held-out admission, measurement API | Four components admitted; check blind to master shapes |
| Slide importer | Reference page to roles-and-weights spec for the round trip | Worked on pptx (0.057); empty paragraphs on PDFs |
| Style judge | 15 components, fitted weights, house spread, panel, layout gates | Calibrated 157 of 171; does not track human perception; reads OCR on scans |
| Package tools | text, layouts, template, blank, duplicate, delete, clean, validate (+render, +emit renderer-divergence) | Worked; text dump joins lines without spaces |
| Design doctrines | Nine reference-agnostic markdown files plus chart recipes | Some doctrine (claim titles) contradicts the houses; recipes useful |
| Examples | House specimen pages as specs (14 families), completions, a 4-page keybank section, proofs | Specimens composed for 16:9; on a 4:3 house only 2 of 14 fit as written |
| Oracles | Scripts that compare the port against the predecessor's outputs and re-measure claims | Valuable; caught four wrong audit claims |

Results of the last full cold run (all 5-page sections, every page fit, package valid):
keybank 0.085 filed; netflix 0.068 filed (repetition flagged); McKinsey 0.131 filed; BCG
0.175 filed; Bain 0.059 filed; Goldman 0.584 not filed (judge read the scan's OCR layer).

---

## 21. Failures observed, and their causes

### 21.1 Why the human caught the generated pages

From the blind round, the rater's notes and the corpus evidence (inferred causes, each
consistent with the measurements; not individually tested):
1. **Title register.** Generated pages used computed claim titles in houses whose titles
   are short topic phrases (section 19.3 item 1). The prototype's doctrine required claims.
2. **Low variety.** "Same patterns with different colours." The prototype had no section
   variety plan; its repetition metric was dominated by page furniture.
3. **Thin annotation.** Generated exhibits rarely carried the house's moves (outline boxes
   on the claim region, subject highlight, reference lines, median rows), because the model
   could not place shapes on charts and was never given the house's annotation habits.
4. **Exhibit-to-data fit.** The rater praised real pages whose chart choice matched the
   data's shape; nothing in the prototype asked the model to justify the chart by the data
   shape and message.
5. **Missing furniture.** No logos; placeholder logo boxes.
6. **Renderer and font tells.** All generated pages were LibreOffice renders; some used
   stand-in fonts.
7. Houses that fooled the rater (Goldman, Bain) had dense, table-heavy, conservative
   pages where the generated content matched the house's restrained annotation.

### 21.2 Mechanical failures (fixed or to fix)

Blockers: unfitted sizes written at scale < 1; chrome reserving the whole page; judge on
scans. Majors: mid-word wraps reported as fit; table in stretch row unchecked; measurement
font differing from render font; chrome z-order; chrome text black on navy and unscored;
rotated text misread; title role bound to numerals; PDF density bands zero; PDF import
empty; gallery refusing PDFs; contrast refusing house colours; emphasis keys dropped
silently; header/cell roles ignored by emitter; XY scatter crash; first scatter series not
drawn; undocumented depth limit; raster completion unable to add roles; no reference line
on bar charts; no per-table overrides.

### 21.3 The full friction list

71 items from six cold runs, an assembler and a regression run; categories: fit truth (8),
chrome (6), PDF intake (10), judge and gates (8), spec and emit (10), plus minor
documentation and ergonomics items. The headline items are integrated throughout this
spec; treat every one as a requirement.

---

## 22. Target improvements over the prototype

1. **Context-first architecture**: house exhibit digest, title statistics, exhibit habits,
   page library, all as data the model reads (sections 6.2, 7.3, 7.4).
2. **Reasoning instructions** (Appendix B) instead of doctrine rules; doctrine files
   rewritten as questions plus measured tendencies, with "the reference wins" enforced by
   measured house statistics.
3. **Annotation layer** with data-anchored placement on native charts and tables, verified
   against renders in both renderers (section 12.3).
4. **Section planning with an explicit variety plan** and a content-only repetition gate
   (sections 9.3, 14.7).
5. **Self-critique loop** on renders with located findings and keep-best (section 15),
   optionally a calibrated second reviewer.
6. **Chrome done properly**: z-order, rotation, inks, contrast, logos extracted and placed,
   reserved zones only where chrome is (section 8.2).
7. **PDF parity**: rotated text, title binding by position, density from words that exist,
   import and gallery for PDFs, raster roles addable (sections 5, 6, 7, 8.4).
8. **One source of truth** for every resolved value from guide to solver to emitter to
   gates to judge (section 2.10).
9. **Instruments that say "no evidence"** distinctly from zero.
10. **Skill packaging per Anthropic practice**: under 500 lines, one-level references with
    tables of contents, checklist workflow, evaluations first, model matrix (section 3).
11. **Evaluation program** with scenario files, cold-agent friction loop, blind rounds as
    the success metric (section 18).
12. **Logo and image handling**: extract, place, and treat logos as category labels where
    the house does.
13. **Optional**: PowerPoint-side verification of renders (when a Windows or Mac runner is
    available), since every render so far is LibreOffice.

---

## 23. Hard rules

- No literal colour, size, font or coordinate in a page spec; roles only; refused by name.
- The model designs every exhibit and every annotation; scripts measure and refuse; no
  script decides or corrects a design choice; omitted choices are reported.
- Nothing is dropped to make a page fit; unfittable is a report.
- Never below `max(floor_pt, absolute_floor_pt)`.
- Observed guide values are never overwritten by completion.
- Numbers come from the user; never invented; every stated figure computed from data.
- Source lines from the sources used.
- The reference wins over any doctrine; enforced by measured house statistics.
- Reference files are untrusted: XML entity resolution disabled; zip-bomb caps enforced;
  run readers in isolated interpreters (`python3 -I`) in their own directories.
- Generated code (new components written by the model) runs sandboxed: no network, no
  filesystem beyond its inputs, resource caps; no unsandboxed fallback.
- Feedback loops are capped and keep the best result.
- Report what was measured, what was completed by judgment, what was substituted (fonts),
  and what the user must supply.
- Never copy code or text from Anthropic's stock pptx skill (proprietary licence).
- No em dashes and no emoji in shipped text (owner's style).

---

## 24. Build order with exit criteria

Each milestone ends with an end-to-end proof recorded beside the claim.

1. **Evaluations and corpus.** Scenario files (18.1); corpus fetched with hashes
   (Appendix D); blind-round tooling (assembly with normalisation and leak checks, rating
   page, scoring). Exit: a baseline blind round on a naive approach, scored.
2. **Reader and triage.** pptx inheritance, PDF triage, rotated text, raster instrument.
   Exit: triage matches renders on all corpus PDFs; raster read-back within the stated
   tolerances on a rendered deck.
3. **Ruler and solver.** HarfBuzz ruler with measured epsilon; aliases; solver with the
   height rules of 11.2; table fitter; scale descent; capacity. Exit: wrap agreement on a
   recorded case set; solver round trip on the reference's own pages inside its spread.
4. **Guide, extraction, completion.** Full schema including `titles` and `exhibit_habits`;
   provenance; open list; completion with groups and null. Exit: guides for all scenario
   references with zero open core; title statistics match a hand count on 3 decks.
5. **Emitter and gates.** One resolved entry per element; read-back; contrast with
   precedent; tie-outs; register and density with no-evidence; content-only repetition;
   renderer-divergence check; validation with render read-back. Exit: a deck built at
   scale 0.9 has every emitted size equal to the solved size; breaking the emitter makes
   the read-back refuse.
6. **Chrome and templates.** z-order, rotation, ink, logos, reserved zones, no theme
   effects. Exit: PDF-reference pages show chrome identical in position and colour to the
   reference in a side-by-side render; chrome text scored.
7. **Visual context.** Renders, gallery for pptx and PDF (set cover, area floor), house
   exhibit digest, page library v1 from the corpus evidence. Exit: the model can retrieve
   the reference's nearest pages for any of 10 intents; library has 40+ tagged pages.
8. **Charts and annotation.** Full chart spec with manual plot layout; annotation anchors
   and kinds; placement verified in LibreOffice (and PowerPoint where available) by marker
   renders; collision contract. Exit: on 10 chart types, computed anchor positions match
   rendered marks within a measured tolerance (state it).
9. **Components.** Contract, API, determinism, held-out admission, master-shape collision.
   Exit: four components admitted on two houses each.
10. **Skill text.** SKILL.md under 500 lines with checklist workflow; references by domain
    with tables of contents; reasoning questions (Appendix B); examples drawn from the
    reference and the library. Exit: a cold agent on each model tier completes scenario 1
    with zero unfixed friction blockers.
11. **Critique loop.** Render review with located findings, keep-best, caps; optional
    cross-family reviewer calibrated against blind ratings. Exit: findings located on real
    element ids in 10 of 10 reviews; measured effect on the next build.
12. **Blind round 2.** All scenarios, two raters if possible. Exit: success criteria of
    section 1.4.

---

## Appendix A. Measured page-craft vocabulary (partial: 3 of 6 corpus groups)

All counts are one coder's judgement per page, made by looking at the page; not checked
against a second coder.

### A.1 Bank pitch books, native pptx (3 pitch books + 1 talk; 51 content pages)

Compositions: full-width bullets 11; numbered takeaway rows (number badge, arrow label,
finding box) 6; text plus table 5; label-row grid 4; text plus stacked tables 4;
full-width table 3; full-width chart 2; framed panel chart 2; 2x2 small multiples 2;
sidebar plus exhibit 2; ten others once each. Sidebar or takeaway box on 3 of 51.

Titles: 48 topic, 3 question, 0 claim; median 4 to 5 words. Claims live in a lead-in
bullet ending in a colon before the exhibit (9 pages), numbered row labels, executive
summary bullets. Units line on 18 of 24 numeric pages.

Text: 1 hierarchy level on 35 pages, 0 on 11, 2 on 5; median 72 words (range 2 to 221).

Exhibits (45): table 17, chart 11, shape-built text structure 11, diagram 2, evidence
excerpt 2, logo wall 1, matrix 1. 27 of 33 data exhibits are pasted pictures; no native
charts in the three pitch books.

Annotation over 33 data exhibits: outline box 14; column-group spanners 6; units column 5;
shaded key row or block 5; parentheses for negatives 4; sorted order 4; selective data
labels 3; all data labels 3; reference line 3; footnote marker 3; logos as category labels
3; NM or N/A 3; callout arrow or pointer 3; base case bolded 3; summary-stats block 2;
category order held across panels 2; input-cell shading 2; section bands 2; caption naming
both axes 2; source line 2; highlight one grey the rest 1; direct labels replacing legend
1. Absent: CAGR arrows, delta labels, brackets with sums, forecast shading, totals above
stacks, event markers. No annotation on 3 of 33.

Emphasis: red or navy outline boxes 13 pages; numbered badges 6; shaded median, subject,
output or answer rows 6; panel header bars 4; no icons, check marks or big numbers.

Variety: V = adjacent pairs with different composition / (n - 1): 0.83, 0.90, 0.85 for the
three pitch books (0.50 for the talk); longest run 2.

Defects humans made (do not imitate): pictures past the margin, colliding data labels,
misregistered overlay boxes, comma decimals in a borrowed chart, repeated titles, subject
not highlighted, mixed fonts between pasted exhibits and slide text.

### A.2 Bank pitch books, PDF (7 decks; 184 content pages; 224 exhibits)

Compositions: full table 30; full chart 20; two charts 12; bullets only 9; chart plus
tables right 9; label-column rows 8; 2x2 chart grid 7; chart plus table below 5; numbered
rows 5; 51 distinct types. Takeaway column or sidebar 15 of 184; one deck uses a bottom
takeaway band on 20 of 30 pages.

Titles: 179 topic, 3 question, 2 claim; mean 3.8 to 5.6 words per deck. Units line 46 of
184; subtitle or kicker 57; a claim sentence appears somewhere on 47 of 184 pages.

Text: hierarchy 0 levels on 110 pages, 1 on 40, 2 on 27, 3 on 7; bold lead-ins 9.

Exhibits: column 29; other financial tables 29; sensitivity matrix 24; projection or DCF
table 20; framework matrix 12; stacked column 11; pie 9; comps table 9; column plus line
8; line 8; horizontal bar 7; price line with events 5; indexed multi-line 5; numbered list
5; logo table 5; football field 4; range bars 4; tombstone grid 4; waterfall 3; analysis
at various prices 3; structure diagram 3; line with peer range band 2; sum-of-parts
floating bars 2; table with inline bars 2; scatter 1; histogram 1; quote stack 1.

Annotation (per exhibit, n = 224): data labels on every point 72; column spanners 59;
shaded or bold total rows 40; footnote markers 30; data rows aligned under chart axis 29;
subject highlighted, rest grey or uniform 27; bracket or group header over categories 23;
NM, NA or dash markers 21; callout text with arrow or leader 20; end-of-line labels 20;
circle or dotted box around the point 19; italic ratio rows 18; sorted order 17; median or
stat row highlighted 15; reference, benchmark or median line 15; colour encodes series
role 14; inset stat table 12; forecast or period demarcation 11; logos as labels 11;
totals above stacks 10; conditional colour 9; event markers 7; delta label 5;
percent-of-total 4; selective data labels 3; peer range band 2. CAGR arrows 0 (growth in a
CAGR column or inset table). Charts with no annotation: 1 of 101.

By data shape: horizontal bar 7 of 7 labelled, 6 sorted, 6 highlight one item; column 25
of 29 labelled, 11 highlight the subject; stacked column 8 of 11 totals above stacks;
indexed multi-line 5 of 5 end labels instead of a legend; price line 5 of 5 event markers,
4 inset returns table; football field 4 of 4 reference line, 3 group brackets; comps 9 of
9 highlight the median row; projection 17 of 20 shade totals, 14 italic ratio rows;
sensitivity 18 of 24 rely only on boxed axis headers and spanners, 2 circle the answer.

### A.3 McKinsey decks (4 decks incl. a memo; 85 content pages; 103 exhibits)

Compositions: table 18; multiple exhibits side by side 15; diagram or framework 14;
exhibit plus takeaway sidebar 9 (one deck pairs a 62 to 70% chart with a grey full-height
sidebar carrying the so-what); parallel columns or icon rows 8; timeline 6; split panel 4;
matrix 3; big numbers 2. Sidebar or takeaway on 19 of 85.

Titles: 43 topic, 41 claim, 1 question; claim titles 8 to 22 words, usually two lines;
house-specific (one deck 23 of 30 claims; the memo 0 of 12). Kicker or tag on 60 of 85
("Exhibit n:", numbered section circles, small-caps tracker kickers, PRELIMINARY,
ILLUSTRATIVE, DRAFT, "Not exhaustive", "(1/2)"). Two-part claim titles split across two
panels, each panel proving its half with its own headline and units line.

Text: bold lead-ins 26 of 85; takeaway or callout text 18 of 85, always stating an
implication the chart does not show directly.

Exhibits: diagram or framework 22; table 16; line 15; column or bar 8; timeline 7;
horizontal bar 5; big numbers 3; press quotes 3; map 3; waterfall 3; bubble matrix 2;
donut 2; 100% stacked column 2; funnel 1.

Annotation (57 data exhibits): footnote markers 17; value labels instead of axis 14;
reference, benchmark, target or trend line 10; highlight one, mute the rest 8; delta or
growth label 7; sorted 5; direct labels replacing legend 5; callout box with leader 5;
legend swatch defining a state 4; outline box around one item 4; event marker 4; totals or
"100% =" bases 3; axis break 2; bracket with computed range 2; forecast shading 1;
percent-of-total 1. No annotation: 4 of 57 (all line charts).

### A.4 Still to come

BCG, Bain and more McKinsey decks; a market-research chart book known for dense
annotation. Treat A.1 to A.3 as the current evidence and refresh when the pass completes.

---

## Appendix B. Reasoning questions for the designer

Offer these as the way to think, tied to evidence, never as rules.

Per section:
- What is the storyline, page by page, in one sentence each? Where does the reader need
  evidence, and where only a statement?
- Which compositions will each page use, and how does that compare with the reference's
  own variety? Which repeats are deliberate parallels, and why?

Per page:
- What is the one thing the reader should leave with? Where does the house put that claim:
  the title, a lead-in bullet, a sidebar, a takeaway band, a kicker? How long are the
  house's titles?
- Which element proves it most directly, and does its size reflect that? If several blocks
  are co-equal, how do they divide the page without becoming a dashboard?
- What does the text add that the exhibit cannot (assumptions, caveats, history, the
  implication)? Is anything said twice?
- Which reference page is nearest to this intent, and what does it do that this page does
  not?

Per exhibit:
- What is the data's shape (time series, ranking, part-to-whole, bridge, distribution,
  range, relation, matrix, process)? Which exhibit types fit that shape, and which does the
  house use? Would a table say it better?
- Where on this exhibit does the claim live (a region of a grid, a few years, one company,
  a gap to a benchmark)? How does the house mark such a place (outline box, circle,
  highlight against grey, reference line, bracket)?
- Can the absence of a mark carry meaning (the one scenario with no box)?
- How will the reader find the subject (colour, position, order held across panels)?
- What value is the decision made against (current price, offer, median, target)? Is it
  drawn?
- What does the chart not say that the reader needs, and where does that go?
- Labels: every point, selected points, or none with an axis? Legend, or direct labels?
  Number formats, units, negatives, NM?
- What would a managing director circle in red on this page?

Per build (on the renders):
- Can the message be found in two seconds?
- Side by side with the reference's pages, what differs?
- What would make a reader suspect this page was generated?

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
- Template = reference with slides removed: opens and re-saves without repair; chrome drawn
  once per slide.
- LibreOffice wraps chart category labels and centred data labels mid-word in narrow slots;
  an `inside_base` label was observed not to wrap.
- Rules on a blank template can inherit a theme drop shadow in LibreOffice.

---

## Appendix D. Reference corpus

Public decks, fetched with curl, type-checked, hashed; treated as untrusted.

Bank pitch books and board decks:
- Mergers & Inquisitions / Breaking Into Wall Street training pitch books (native pptx,
  one fictional bank "Goldman Stanley" master): Jazz Pharmaceuticals sell-side
  (pptx and PDF twin), KeyBank / First Niagara FIG M&A, Netflix equity, debt and
  convertible financing. URLs under biws-support.s3.amazonaws.com/Pitch-Books/.
- Wall Street Prep hosted PDFs (SEC filing or litigation provenance): Goldman Sachs Airvana
  "Why Goldman" (2009, scanned) and go-private board deck, Deutsche Bank AmTrust, Citigroup
  Tribune restructuring update (scanned), Perella Weinberg pitch, BMO fairness opinion
  (243 pages including filing text). URLs under media.wallstreetprep.com/uploads/2011/09/.
- A 2006 conference talk pptx (contrast case) and a theme test file.

Consulting (public-records releases):
- McKinsey: CalSTRS future of boards (2024), CBP project documents (2018), MTA COVID
  financial (2020), OxyContin growth memo (2013), Purdue BDC deck (2014), Purdue market
  access appendix (2019), Virginia COVID fact pack (2020), University of Florida "Road
  Ahead" (2023, scanned, 520 pages).
- BCG: Dallas loose dogs (2016), NYCHA support functions (2012), New York State COVID
  impact (2020).
- Bain: UC Berkeley operational diagnostic (2010, 205 pages).

Craft reference: J.P. Morgan Guide to the Markets (dense annotated charts).

Known gaps: native pptx working decks from real banks are almost unobtainable publicly
(searches found only PDFs and template-store products); archive.org was unreachable from
the build environment; SEC exhibits are mostly HTML. Expand the corpus where possible,
especially native pptx and more houses, and keep a manifest with source, licence basis and
hash for every file.
