---
name: chart_design
description: How to choose and discipline chart forms - the data relationship picks the form, one message per chart, direct labels, honest axes, annotated takeaways, and the consulting grammar (Mekko, Gantt, benchmark dots). Load when the slide carries a chart.
---

# chart_design v1

General craft for charts in dense advisory decks. Concrete values - fonts,
colors, sizes - belong to the StyleGuide, never here. Where this skill and the
reference's observed practice conflict, the reference wins.

## Principles

The data relationship picks the form. A ranked comparison wants ordered bars;
a build-up over stages wants a bridge; ranges around a point want bands on
one shared axis; a trend wants a line. Choosing the form before reading the
data produces charts that decorate instead of argue.

One message per chart: a single comparison made unmissable. Secondary series
are context and read as context, in muted roles. A chart supporting two
claims is two charts, or one too many.

Label directly, sort deliberately. Series names go at the series, value
labels at the marks that matter - endpoints, extremes, the concluded figure -
not in a legend. Sort categorical axes by value unless an inherent order
exists.

Axes are honest and quiet. Bars start at zero; a truncated scale is
announced, never silent. Gridlines, ticks, and axis lines are scaffolding in
muted roles: if removing one loses nothing, remove it. Comparable charts
share one scale; an unshared scale is visibly declared.

The takeaway is annotated on the chart: the delta, the crossing point, the
concluded range marked where it happens, anchored to the marks it measures.

## Consulting grammar

A Mekko earns its second dimension only when width carries meaning: segment
width is share of the total, stack composition within each segment, so both
axes read as parts of one whole. Near-uniform widths, or a second dimension
nobody needs, mean a plain stacked bar.

A Gantt or swimlane runs time one way and owners in lanes - bars activities,
markers milestones, a now-line anchoring the reader - and argues only when
its takeaway is marked: the critical path, the slipped milestone, the
dependency between lanes.

A benchmark dot plot puts entities on one axis, the metric on the other, one
dot each: subject accented, peers muted, median or range marked. Choose it
over bars when the message is position in a field, not magnitude.

## Worked example: valuation football field

Horizontal bands, one per methodology, on a single shared axis labelled in
type.axis_label. Band labels sit flush left in type.body; each range's
endpoints carry type.data_label. Methodology bands stay in muted color.ink;
the concluded range crosses them as a vertical band in color.accent1, its
span restated in type.emphasis at the top - the one accent, the figure the
title asserts. The current price is a color.rule vertical marker with a
type.caption label.

## Worked example: EBITDA bridge

Start and end columns anchor in color.ink; increments carry color.positive,
decrements color.negative; connectors are color.rule hairlines. Each step
shows its signed delta in type.data_label. Only the start, the end, and the
one step the slide argues about get type.emphasis; that step alone shifts to
color.accent1 with a type.caption note anchored to it. The value axis is
suppressed: the labelled values carry the scale. How to write this, and the football
field, mekko and labelled-bar exhibits, in the chart spec: `chart_recipes.md`.

## Checklist

- Can the data relationship behind the form be stated in one sentence?
- Is the single message annotated on the chart itself?
- Direct labels at the marks that matter, a legend only if unavoidable?
- Zero-based or explicitly declared axes; shared scales across comparables?
- Are secondary series and scaffolding in muted roles?

## Anti-patterns

- Legend-only identification that forces eye travel.
- A silently truncated value axis.
- Every mark labelled, so no label reads.
- Accent roles distributed for variety rather than meaning.
- A Mekko with near-uniform widths: a stacked bar in costume.
