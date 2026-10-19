---
name: decoration_and_motifs
description: When marks earn their place - the separator hierarchy, accent budgets, motifs that recur identically, connectors that visibly connect. Load when rules, fills, markers, or motifs are in play.
---

# decoration_and_motifs v1

General craft for rules, fills, markers, and recurring motifs. Which motifs
exist and how they look is the StyleGuide's property, never this skill's.
Where this skill and the reference's observed practice conflict, the reference
wins.

## Principles

Every mark carries information. A rule separates, a fill selects, a marker
locates, a leader connects. Before drawing anything, name its job in one
phrase; a mark with no nameable job is decoration, and decoration is what
gives a generated deck away.

The hierarchy of separators runs: spacing, then hairline rule, then heavier
rule, then fill. Reach for the next device only when the previous one is
insufficient at the density in hand. Fills are the last resort and the
strongest signal - one fill on a slide says "this is the answer"; five fills
say nothing.

Accents are a budget, not a palette. Accent roles mark the exceptional: the
selected row, the concluded range, the live phase. Spend the budget once, at
the point of the argument. Everything structural runs in ink and rule roles.

Motifs are the reference's vocabulary. Reuse the guide's observed devices -
its marker shapes, its callout construction, its header treatment - at every
recurrence, identically. A device that appears once is noise; a device that
recurs in varying forms is worse, because it teaches the reader a grammar and
then breaks it.

Connectors must connect. A leader line, bracket, or arrow that does not
visibly join the two things it relates is floating geometry. Anchor both ends
to edges the composition already has.

## Worked example: callout on a table

A bracket in color.rule spans the two rows being compared, anchored to the
table's right edge. Its leader carries the delta in type.emphasis with a
one-line qualifier in type.caption, both flush to a shared left edge in the
margin column. Nothing is filled and nothing floats: the bracket borrows the
table's own row geometry, and the accent budget stays spent on the table's
selected row rather than on the callout.

## Worked example: section header motif

The guide observes a header treatment: a kicker over a hairline. Applied as a
motif, every section opener repeats it identically - type.kicker in
color.ink_muted, the color.rule hairline at the same indent, the section
number in type.caption at the same offset. The repetition is the information:
the reader learns that this construction means a new section because it never
varies.

## Checklist

- Can you name each mark's job in one phrase?
- Did spacing and rules prove insufficient before any fill was used?
- Is the accent budget spent once, at the argument's point?
- Does every recurring device recur identically?
- Are both ends of every connector anchored to existing edges?

## Anti-patterns

- Icons as filler beside list items.
- Gradients, shadows, or corner styling the reference never shows.
- Watermark-scale background shapes behind content.
- The same job done two ways on one slide: a rule here, a box there.
- An accent role used as a general color scheme instead of a marker of the
  exceptional.
