---
name: typography_hierarchy
description: How to hold a small, strict typographic hierarchy - few levels, decisive single-dimension differences, restrained emphasis, hard legibility floors. Load when text hierarchy is in play.
---

# typography_hierarchy v1

General craft for typographic hierarchy on dense slides. Actual families,
sizes, and weights belong to the StyleGuide, never here. Where this skill and
the reference's observed practice conflict, the reference wins.

## Principles

Hierarchy is a small count of distinguishable levels, held strictly. A slide
needs few - a title level, a heading level, a body level, an annotation
level - and every run must land exactly on one of them. Intermediate, one-off
levels read as errors because they are.

Differentiate on as few dimensions as the level needs. Adjacent levels should
differ decisively in one dimension - a clear size step, a weight shift, or an
ink change - not slightly in three. Small differences on many dimensions read
as inconsistency, not hierarchy.

Emphasis is borrowed, briefly. Within running text, emphasis is one device
applied to few words: a weight shift or an ink shift, not both, and never
weight plus color plus underline stacked. When everything is emphasized, the
level collapses.

Case and alignment are level properties, not local choices. Whatever casing
convention the guide observes for a role applies to every instance of that
role. Flush-left is the default for reading text; centering is reserved for a
single dominant figure. Justified text in narrow columns opens rivers - avoid
it.

The floor is a hard boundary. Annotation roles exist so fine print has a
legitimate small level; body text never shrinks to annotation scale to force a
fit. When body content cannot fit above its floor, the content splits - the
hierarchy does not bend.

## Worked example: title block

type.kicker in color.ink_muted sits on the top margin, in whatever casing the
guide observes for it; type.title below it in color.ink, flush left, held to
the text column grid; a color.rule hairline closes the block at space.sm
below. Three runs, three levels, one alignment edge: the block reads in one
fixation, and nothing in it competes with the exhibit.

## Worked example: annotated figure

A dominant numeral in type.h1 with its unit beside it in type.caption - the
unit visibly subordinate, so the figure carries the fixation. The comparison
line beneath runs type.body in color.ink; its qualifier continues at the same
level but in color.ink_muted - an ink shift rather than a size shift, because
it is the same rank of information with less claim on attention. Nothing on
the block introduces a fourth text level.

## Checklist

- Can you count the levels on one hand and name each run's level?
- Do adjacent levels differ decisively on one dimension?
- Is emphasis a single device applied to few words?
- Are casing and alignment consistent per role across the slide?
- Does no run sit below its role's floor?

## Anti-patterns

- The many-level slide: every text run subtly unique in size or weight.
- Emphasis stacking: weight plus ink plus underline on the same words.
- Centered body paragraphs.
- Shrinking body text to annotation scale to force a fit.
- A hierarchy whose logic changes from one slide to the next.
