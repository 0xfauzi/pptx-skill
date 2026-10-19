---
name: ib_slide_composition
description: How to compose an investment-banking slide - functional anatomy, exhibit dominance, reading gravity, shared-edge alignment, and density with hierarchy. Load for every whole-slide design call.
---

# ib_slide_composition v1

General craft for composing an investment-banking slide. Concrete values -
fonts, colors, sizes, motifs - belong to the StyleGuide, never here. Where
this skill and the reference's observed practice conflict, the reference wins.

## Principles

An IB slide is an argument, not a poster. Its anatomy is fixed by function: a
kicker locates the slide in the deck's storyline; the title asserts the
conclusion; the exhibit proves it; support qualifies it; the source line makes
it auditable. Every element on the slide must be assignable to one of those
jobs - anything that is not is decoration and must justify itself.

The exhibit dominates. Give the proving element the majority of the canvas and
let support read visibly as support: subordinate roles, muted ink, marginal
position. The eye should land on the exhibit's key figure within a second and
find the title's claim confirmed there.

Reading gravity runs top-left to bottom-right. Place the claim early on that
path and the resolution - the concluded number, the recommended range - late
on it. A slide that resolves in its top-left corner and trails off below is
inverted.

Structure with alignment, not enclosure. A small number of shared edges
carries the whole composition: one left edge for text blocks, one right edge
for numerals, shared baselines across regions. Separate regions with spacing
steps and hairline rules; reserve fills for the exceptional.

Density is credibility in this genre, but density without hierarchy is noise:
compress inside groups, open up between groups, and keep every floored text
role legible. When content cannot fit legibly, it splits - it is never diluted
into filler.

## Worked example: trading comps page

The kicker runs type.kicker in color.ink_muted above a type.title assertion
stating the discount. The comps table dominates roughly three quarters of the
width: type.table_header over a color.rule hairline, type.table_cell numerals
right-aligned, the target's row marked with color.accent1 and type.emphasis -
the single fill on the slide. A narrow right-hand column of type.body
observations aligns to the table's top baseline, each observation keyed to the
row it comments on. The type.source_line sits at the bottom margin in
color.ink_muted.

## Worked example: process update

A horizontal spine in color.rule crosses the canvas. Completed phases carry
color.ink markers and type.h2 labels; the live phase carries the only
color.accent1 marker plus a type.emphasis annotation of the near-term date;
future phases fade to color.ink_muted. Below the spine, workstream detail in
type.body sits at space.sm intervals, tight under its own phase and open at
space.lg between phases. The title asserts the timing claim that the accented
marker proves.

## Checklist

- Can every element be named as kicker, title, exhibit, support, or source?
- Does one element visibly dominate, and does it prove the title?
- Do numerals share one right edge and text blocks one left edge?
- Is spacing tight within groups and open between them?
- Does the reading path end on the resolution?

## Anti-patterns

- The gallery slide: several exhibits of equal weight, none proving the title.
- Support styled as loudly as the exhibit it qualifies.
- A missing source line on a slide built from data.
- Enclosure instead of alignment: boxes drawn around what shared edges
  already group.
- Filler added to reach a fuller-looking canvas instead of splitting.
