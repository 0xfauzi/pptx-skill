# Chart recipes

## Contents
- The spec
- How the contrast gate reads a chart
- Waterfall (bridge): an invisible first series as the running base
- Bridge with negative steps that cross zero
- Football field as a chart: a stacked bar with an invisible low series
- Mekko approximation: one 100% column per segment, widths by weight
- Labelled bars with no value axis
- Annotations: shapes at data positions
- What a default looks like in the report

A chart is a spec you write. The emitter writes it as given and decides nothing: not
the chart type, not a colour, not whether an axis shows, not which ink a label takes.
The guide is the style (its colour roles, its type roles, `charts.series_color_roles`
and `charts.per_kind` as evidence of what the reference does); you read it and write
every choice into the spec. The build then measures: contrast of every label against
the fill it sits on (below 3.0:1 refuses the page), the stroke floor (`validate
--emit`), fit, the judge. What you leave out is written as a neutral value and listed
per page under `chart_defaults_taken` in the build report. Read that list after every
build: each line is a decision you did not make.

Everything below is a recipe in that spec, not a code path. Each one has been built on
keybank (the pages named under "Proven on") and read from the render.

## The spec

```json
{
 "type": "COLUMN_STACKED",
 "categories": ["FY16", "FY17"],
 "number_format": "0",
 "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
 "series": [
  {"name": "Precedented", "values": [120, 250],
   "fill_role": "color.accent1", "line_role": "none", "line_width_pt": 0.75,
   "labels": {"show": true, "position": "center", "number_format": "0", "role": "type.data_label", "ink_role": "color.ink"},
   "points": [{"index": 1, "fill_role": "color.accent2", "line_role": "none",
               "label": {"ink_role": "color.ink_inverse", "text": "250 (record)"}}]}
 ],
 "axes": {
  "category": {"visible": true, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none",
               "reverse": false, "gridlines": "none",
               "labels": {"show": true, "position": "low", "role": "type.axis_label", "ink_role": "color.ink_muted"}},
  "value": {"visible": false}
 },
 "gap_width": 50,
 "overlap": 100,
 "legend": {"position": "b", "hide_entries": [], "role": "type.axis_label", "ink_role": "color.ink_muted"},
 "plot_fill_role": "none",
 "title": "none"
}
```

- `type`: any `XL_CHART_TYPE` member name python-pptx 1.0.2 can write: `COLUMN_CLUSTERED`,
  `COLUMN_STACKED`, `COLUMN_STACKED_100`, `BAR_CLUSTERED`, `BAR_STACKED`,
  `BAR_STACKED_100`, `LINE`, `LINE_MARKERS`, `LINE_STACKED` (and the 100 and markers
  variants), `PIE`, `PIE_EXPLODED`, `DOUGHNUT`, `DOUGHNUT_EXPLODED`, `AREA`,
  `AREA_STACKED`, `AREA_STACKED_100`, `XY_SCATTER` and its line variants, `BUBBLE`,
  `RADAR`, `RADAR_FILLED`, `RADAR_MARKERS`. A 3-D, cone, stock or surface member is
  refused with python-pptx's own reason.
- XY and bubble series take `values` as `[[x, y], ...]` or `[[x, y, size], ...]` and no
  `categories`.
- Colours are roles from the guide or `"none"`. A literal hex anywhere in a chart spec is
  refused; so is an unknown key (a typo never silently becomes a default).
- `fill_role` applies to bars, slices, areas and bubbles; a line, scatter or radar
  series draws its `line_role` and `line_width_pt` (markers take `marker`:
  `{"style": "circle", "size": 6, "fill_role": ..., "line_role": ...}`).
- `labels.position` must be one PowerPoint offers for the type: clustered bar and column
  `center`, `inside_end`, `inside_base`, `outside_end`; stacked bar and column the same
  without `outside_end`; line, scatter and bubble `center`, `left`, `right`, `above`,
  `below`; pie `center`, `inside_end`, `outside_end`, `best_fit`; area, doughnut and
  radar take none. Anything else is refused.
- A point's `label` overrides the series labels for that point, merged key by key:
  `{"show": false}` hides one label; `"text"` writes your own words in place of the
  value.
- `axes.<name>.min`, `max`, `major_unit` and `number_format` belong to a value axis (and
  to both axes of a scatter). `reverse: true` writes maxMin: a horizontal bar then
  lists categories top-down in the order you gave them, and the value axis moves to the
  far edge (its tick labels then sit above the plot, where a vertical line's label
  would go). A hidden axis (`visible: false`) still writes its `min`, `max`, `reverse`
  and `cross_between`: the plot keeps the scale you gave it.
- `axes.value.cross_between`: `"between"` (categories are bands; bars and line points
  sit mid-band) or `"midpoint"` (line points on the band edges, the first and last on
  the plot's edges). Written as `c:crossBetween`; left out, each renderer picks.
- `gap_width` (0 to 500, percent of a bar's width) and `overlap` (-100 to 100) belong to
  bar and column types only. A stacked type wants `overlap: 100`; the series stack in
  every renderer only then.
- `smooth` (true or false) on a line or scatter series is written as `c:smooth`; omitted,
  the report names the value the file got.
- `plot_area: {"x", "y", "w", "h"}` fixes the inner plot rectangle (inside the axes and
  their labels) as fractions of the chart frame, written as a manual layout. Leave room
  outside it for the tick labels: they are drawn outside the rectangle, not measured.
- A line, box, band, arrow, bracket, callout or badge at a data position is an
  annotation on the slide, not a chart key (section "Annotations" below). It needs
  `plot_area` and the axis's `min`, `max` and `cross_between`.
- `bridge: {"deltas": [...], "totals": [...]}` on a stacked chart declares it a bridge
  for the build's tie-out (below); it draws nothing.
- `c:varyColors val="0"` is written on every chart and is not yours to set: PowerPoint
  and LibreOffice read its absence oppositely (measured on both renderers). It means a pie
  draws one colour unless you give every slice a `fill_role` under `points`.

## How the contrast gate reads a chart

Every label you ink is scored against what lies under it. A label at `center`,
`inside_end` or `inside_base` of a bar, slice or bubble sits on that mark's fill (the
point's `fill_role`, else the series'); at `outside_end` or on a line it sits on the
plot (`plot_fill_role`, else whatever the page draws under the chart). A label whose
position you left open is scored against both. A series with `fill_role: "none"` puts
its labels on the plot. A label on a fill you left to the renderer is listed as
`undecidable`, and a label with no `ink_role` (on itself or on `text`) as `unbound`.
Below 3.0:1 refuses the page and names the part, the ink and the backing:

    chart series[0] 'Precedented' labels (points [0, 1, 2]): color.ink_inverse over
    color.accent1 fill of series[0] 'Precedented' labels is 1.54:1, under 3.0:1

Nothing swaps an ink to rescue a page. The fix is the role you meant.

## Waterfall (bridge): an invisible first series as the running base

A stacked column whose first series is the running base with no fill and no stroke,
whose second series carries each step's height, and whose third series of zeros
carries the labels above each bar (`inside_base` of a zero-height segment sits on top
of the stack, on the plot, which a stacked type cannot do with `outside_end`). You
compute the base: a total draws from zero; a step at running total r with delta d sits
on min(r, r + d) with height |d|. Colour the steps through `points`.

Proven on: `examples/keybank-bridge.deck.json` page `b1-eps`.

```json
{
 "type": "COLUMN_STACKED",
 "categories": ["FY17E", "Cost syn.", "Revenue syn.", "Marks", "Amortisation", "Financing", "Issuance", "Pro forma"],
 "number_format": "0.00",
 "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
 "series": [
  {"name": "Base", "values": [0, 1.12, 1.33, 1.36, 1.34, 1.29, 1.24, 0],
   "fill_role": "none", "line_role": "none", "labels": {"show": false}},
  {"name": "Step", "values": [1.12, 0.21, 0.03, 0.04, 0.06, 0.05, 0.05, 1.24],
   "fill_role": "color.accent3", "line_role": "none", "labels": {"show": false},
   "points": [{"index": 0, "fill_role": "color.accent2"}, {"index": 4, "fill_role": "color.accent1"},
              {"index": 5, "fill_role": "color.accent1"}, {"index": 6, "fill_role": "color.accent1"},
              {"index": 7, "fill_role": "color.accent2"}]},
  {"name": "Label", "values": [0, 0, 0, 0, 0, 0, 0, 0], "fill_role": "none", "line_role": "none",
   "labels": {"show": true, "position": "inside_base", "number_format": "0.00", "role": "type.data_label", "ink_role": "color.ink"},
   "points": [{"index": 0, "label": {"text": "$1.12"}}, {"index": 1, "label": {"text": "+0.21"}},
              {"index": 2, "label": {"text": "+0.03"}}, {"index": 3, "label": {"text": "+0.04"}},
              {"index": 4, "label": {"text": "(0.06)"}}, {"index": 5, "label": {"text": "(0.05)"}},
              {"index": 6, "label": {"text": "(0.05)"}}, {"index": 7, "label": {"text": "$1.24"}}]}
 ],
 "axes": {"category": {"visible": true, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": false,
                       "gridlines": "none", "labels": {"show": true, "role": "type.axis_label", "ink_role": "color.ink_muted"}},
          "value": {"visible": false, "min": 0}},
 "gap_width": 40, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
 "bridge": {"deltas": [1.12, 0.21, 0.03, 0.04, -0.06, -0.05, -0.05, 1.24], "totals": [0, 7]}
}
```

`bridge` is a declaration, not a drawing instruction: nothing is drawn from it. The build
reads it and refuses the page ("bridge does not tie") when a total is not the running
sum of the steps before it, or when a category's drawn span (the filled series,
stacked as the renderers stack them) is not the span its step covers. A base computed
wrong by one cent is caught by name:

    chart: 'Revenue syn.' draws 1.3 to 1.33; the bridge step covers 1.33 to 1.36

Declare it on every bridge you draw.

Choices to make from the guide, not from this example: which role marks a total (the
house's anchor colour: keybank's first series colour is `color.accent2`), which marks an
increase and a decrease (a guide with `color.positive` and `color.negative` has them;
keybank has neither, so the steps are told apart by tone and by the sign in the label),
and whether labels sit above the bars (this recipe) or inside them (`labels` on the Step
series at `center`, with an ink per fill; check the step heights hold the label first).
Give each category room for its name: the renderer rotates tick labels that would
collide, and nothing in the build measures that. On keybank this page's first draft
(long names, chart at flex weight 1.7 beside the text) rendered at 45 degrees, short
names at 1.7 still did, and short names at weight 2.6 read level. Look at the render.

## Bridge with negative steps that cross zero

A native stack draws positive values up from zero and negative values down from zero,
each in series order. So a bridge whose running total goes below zero takes four
series: a positive base (invisible), a positive step, a negative base (invisible), a
negative step. For a step spanning [lo, hi]:

- lo >= 0: positive base lo, positive step hi - lo.
- hi <= 0: negative base hi, negative step lo - hi (both negative numbers).
- lo < 0 < hi: positive step hi, negative step lo (the bar crosses the axis).

Give each step one label on its larger segment and hide the other (`{"show": false}`),
hide the label of every zero-height segment (a "0.0" would print on the axis), and put
the category labels at the bottom of the plot (`"position": "low"`), since the category
axis crosses at zero.

Proven on: `examples/keybank-bridge.deck.json` page `b2-capital` (0.6, then -1.4 to
-0.8, -0.2 to -1.0, +1.1 back to 0.1, +0.4, ending at 0.5).

```json
{
 "type": "COLUMN_STACKED",
 "categories": ["Standalone excess", "Cash consideration", "Intangibles deduction", "Common issuance", "Preferred issuance", "Pro forma excess"],
 "number_format": "0.0",
 "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
 "series": [
  {"name": "Base above zero", "values": [0, 0, 0, 0, 0.1, 0], "fill_role": "none", "line_role": "none", "labels": {"show": false}},
  {"name": "Step above zero", "values": [0.6, 0.6, 0, 0.1, 0.4, 0.5], "fill_role": "color.accent3", "line_role": "none",
   "labels": {"show": true, "position": "center", "number_format": "0.0", "role": "type.data_label", "ink_role": "color.ink"},
   "points": [{"index": 0, "fill_role": "color.accent2", "label": {"text": "$0.6bn", "ink_role": "color.ink_inverse"}},
              {"index": 1, "fill_role": "color.accent1", "label": {"show": false}},
              {"index": 2, "label": {"show": false}},
              {"index": 3, "fill_role": "color.accent3", "label": {"show": false}},
              {"index": 4, "fill_role": "color.accent3", "label": {"text": "+0.4", "ink_role": "color.ink"}},
              {"index": 5, "fill_role": "color.accent2", "label": {"text": "$0.5bn", "ink_role": "color.ink_inverse"}}]},
  {"name": "Base below zero", "values": [0, 0, -0.8, 0, 0, 0], "fill_role": "none", "line_role": "none", "labels": {"show": false}},
  {"name": "Step below zero", "values": [0, -0.8, -0.2, -1.0, 0, 0], "fill_role": "color.accent1", "line_role": "none",
   "labels": {"show": true, "position": "center", "number_format": "0.0", "role": "type.data_label", "ink_role": "color.ink"},
   "points": [{"index": 0, "label": {"show": false}},
              {"index": 1, "fill_role": "color.accent1", "label": {"text": "(1.4)", "ink_role": "color.ink"}},
              {"index": 2, "fill_role": "color.accent1", "label": {"text": "(0.2)", "ink_role": "color.ink"}},
              {"index": 3, "fill_role": "color.accent3", "label": {"text": "+1.1", "ink_role": "color.ink"}},
              {"index": 4, "label": {"show": false}}, {"index": 5, "label": {"show": false}}]}
 ],
 "axes": {"category": {"visible": true, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": false,
                       "gridlines": "none", "labels": {"show": true, "position": "low", "role": "type.axis_label", "ink_role": "color.ink_muted"}},
          "value": {"visible": false}},
 "gap_width": 40, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none",
 "bridge": {"deltas": [0.6, -1.4, -0.2, 1.1, 0.4, 0.5], "totals": [0, 5]}
}
```

On keybank, white on `color.accent3` (5E7C9E) reads 4.33:1, under AA at 10pt: the build
warned on the first draft of this page and the inks above are the fix (`color.ink`,
4.85:1).

## Football field as a chart: a stacked bar with an invisible low series

A horizontal stacked bar: the low end as an invisible series (its `inside_end` label
sits just left of the bar, on the plot, and prints the low), the range as a visible
series, and a third invisible series of a constant small width whose `inside_base`
label, with your own text, prints the high just right of the bar. Set the value axis
range yourself so every method starts on the plot. Reverse the category axis so the
methods read top-down in your order; the value axis then sits at the top.

Proven on keybank (scratch page `ff`, five methods, $20 to $40).

```json
{
 "type": "BAR_STACKED",
 "categories": ["52-week trading range", "Analyst price targets", "Trading comparables", "Precedent transactions", "DCF (WACC 9-11%)"],
 "number_format": "0.0",
 "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
 "series": [
  {"name": "Low", "values": [24.1, 26.0, 25.5, 29.0, 27.5], "fill_role": "none", "line_role": "none",
   "labels": {"show": true, "position": "inside_end", "number_format": "$0.0", "role": "type.data_label", "ink_role": "color.ink"}},
  {"name": "Range", "values": [7.8, 8.0, 5.0, 7.5, 7.5], "fill_role": "color.accent2", "line_role": "none", "labels": {"show": false},
   "points": [{"index": 3, "fill_role": "color.accent3"}]},
  {"name": "High label", "values": [2.5, 2.5, 2.5, 2.5, 2.5], "fill_role": "none", "line_role": "none",
   "labels": {"show": true, "position": "inside_base", "number_format": "$0.0", "role": "type.data_label", "ink_role": "color.ink"},
   "points": [{"index": 0, "label": {"text": "$31.9"}}, {"index": 1, "label": {"text": "$34.0"}}, {"index": 2, "label": {"text": "$30.5"}},
              {"index": 3, "label": {"text": "$36.5"}}, {"index": 4, "label": {"text": "$35.0"}}]}
 ],
 "axes": {"category": {"visible": true, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": true,
                       "gridlines": "none", "labels": {"show": true, "role": "type.axis_label", "ink_role": "color.ink"}},
          "value": {"visible": true, "line_role": "none", "tick_marks": "none", "reverse": false, "number_format": "$0",
                    "min": 20, "max": 40, "major_unit": 5,
                    "gridlines": {"line_role": "color.accent1", "line_width_pt": 0.5},
                    "labels": {"show": true, "role": "type.axis_label", "ink_role": "color.ink_muted"}}},
 "gap_width": 60, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none"
}
```

The offer price as a line across every method, the unaffected price as a second line
and the committee's range as a shaded zone are annotations on this chart (section
"Annotations", the football field recipe). Give the chart a `plot_area` and the value
axis `min`, `max` and `cross_between`.

The `football_field` component (`components/football_field`) draws the same exhibit
from rects with measured label widths; pick the chart when the page wants native,
editable data, the component when it wants the label column the component lays out.

## Mekko approximation: one 100% column per segment, widths by weight

A native chart cannot vary category widths, which is the point of a mekko. Approximate
it with one single-category `COLUMN_STACKED_100` chart per segment, side by side in a
flex row whose `weight`s are the segments' sizes (the solver turns weights into widths),
gap 0 so each column fills its box, both axes hidden, and the segment's name and size
as text above it. The colour key is text you set once on the page, since three legends
would repeat it.

Proven on: `examples/house/06-revenue-mix.deck.json` (three segments at weights 4.8,
3.2 and 2.0, their shares of revenue; on keybank the render reads as a mekko with Flow
Control more than twice as wide as Aftermarket, though that page is refused for its
two-line title).

```json
{"type": "region", "id": "band-mekko", "layout": {"kind": "flex", "direction": "row", "gap_role": "space.sm", "pad_role": null, "align": "stretch", "justify": "start"},
 "children": [
  {"type": "element", "id": "el-mekko-0", "kind": "chart", "weight": 4.8},
  {"type": "element", "id": "el-mekko-1", "kind": "chart", "weight": 3.2},
  {"type": "element", "id": "el-mekko-2", "kind": "chart", "weight": 2.0}]}
```

```json
"el-mekko-0": {
 "type": "COLUMN_STACKED_100", "categories": ["Flow Control"], "number_format": "#,##0",
 "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
 "series": [
  {"name": "Europe (%)", "values": [45.5], "fill_role": "color.accent1", "line_role": "color.surface", "line_width_pt": 0.75,
   "labels": {"show": true, "position": "center", "number_format": "#,##0", "role": "type.data_label", "ink_role": "color.ink"}},
  {"name": "Americas (%)", "values": [36.0], "fill_role": "color.accent2", "line_role": "color.surface", "line_width_pt": 0.75,
   "labels": {"show": true, "position": "center", "number_format": "#,##0", "role": "type.data_label", "ink_role": "color.ink_inverse"}},
  {"name": "Asia Pacific (%)", "values": [18.6], "fill_role": "color.accent3", "line_role": "color.surface", "line_width_pt": 0.75,
   "labels": {"show": true, "position": "center", "number_format": "#,##0", "role": "type.data_label", "ink_role": "color.ink"}}],
 "axes": {"category": {"visible": false}, "value": {"visible": false}},
 "gap_width": 0, "overlap": 100, "legend": "none", "plot_fill_role": "none", "title": "none"}
```

The surface-coloured stroke between segments is a choice (a white hairline separates
the stacks on a white page); drop it if the house draws flush blocks.

## Labelled bars with no value axis

When every bar carries its value, the value axis repeats it: hide it, keep the category
axis as the baseline, and put the labels `outside_end`. Pick out the bar the title is
about with a point fill.

Proven on: `examples/keybank-section.deck.json` page `s2-comps` (horizontal, First
Niagara in `color.accent2` among peers in `color.accent1`, its label in type.emphasis)
and scratch page `cols` (vertical).

```json
{
 "type": "COLUMN_CLUSTERED",
 "categories": ["FY14", "FY15", "FY16E", "FY17E"],
 "number_format": "0.0",
 "text": {"role": "type.axis_label", "ink_role": "color.ink_muted"},
 "series": [{"name": "Net income ($bn)", "values": [0.92, 0.92, 0.84, 1.31], "fill_role": "color.accent1", "line_role": "none",
             "labels": {"show": true, "position": "outside_end", "number_format": "$0.00", "role": "type.data_label", "ink_role": "color.ink"},
             "points": [{"index": 3, "fill_role": "color.accent2"}]}],
 "axes": {"category": {"visible": true, "line_role": "color.rule", "line_width_pt": 0.75, "tick_marks": "none", "reverse": false,
                       "gridlines": "none", "labels": {"show": true, "role": "type.axis_label", "ink_role": "color.ink_muted"}},
          "value": {"visible": false}},
 "gap_width": 60, "overlap": 0, "legend": "none", "plot_fill_role": "none", "title": "none"
}
```

For a horizontal bar write `BAR_CLUSTERED` and `"reverse": true` on the category axis,
or the first category prints at the bottom.

## Annotations: shapes at data positions

Humans annotate almost every data exhibit (7 of 291 charts in the coded corpus
carry none); most moves are a shape placed at a data position. They are a list
under the slide, beside `charts` and `styling`:

```json
"annotations": [
 {"id": "offer", "host": "ff", "kind": "reference_line", "anchor": {"value": 36.5},
  "line_role": "color.negative", "line_width_pt": 1.5, "dash": "dash",
  "label": {"text": "Offer $36.50", "role": "type.data_label", "ink_role": "color.negative", "position": "end_outside"}}
]
```

`host` is a chart or table element on the page. Nothing annotates by itself: you decide
whether and what, from the house's habits and the message (the guide's `exhibit_habits.moves_by_data_shape`
and `moves_by_message_kind`).

Anchors, in the host's own data:

| host | anchor | what it names |
|---|---|---|
| chart | `{"point": {"series": s, "category": c}}` (XY: `{"series": s, "index": i}`) | one bar, or one point's marker box |
| chart | `{"categories": [i, j]}` | the category bands i..j across the plot; brackets and arrows use the marks in them |
| chart | `{"category": c}` | a line at the category's centre (an event marker) |
| chart | `{"value": v}`, `{"value": v, "axis": "category"}` (XY x) | a line across the plot |
| chart | `{"values": [a, b]}` | a band across the plot |
| chart | `{"region": {"categories": [i, j], "values": [a, b]}}` (XY: `{"x": [..], "y": [..]}`) | a rectangle |
| table | `{"cell": [r, c]}`, `{"cells": [[r0, c0], [r1, c1]]}` | cells; body rows count from 0 as `rows` lists them |
| table | `{"row": r}`, `{"rows": [r0, r1]}`, `{"column": c}`, `{"columns": [c0, c1]}` | whole rows (all columns) or columns (header included); a column may be named by key |
| table | `{"header_group": {"row": 0, "columns": [c0, c1]}}` | header cells (a spanner group) |

A chart anchor needs the chart's `plot_area` and, for the axis it names, `min`, `max`
and `cross_between`; without them the annotation is refused by name (an auto-scaled
axis has no computable position). Bar, column, line and XY charts only; a pie, area,
radar, bubble or stacked line is refused. A table anchor uses the fitted column widths
and row heights.

Kinds (required keys first; every other choice left out is written neutral and listed
under the page's `annotations[].defaults_taken`):

| kind | required | optional | draws |
|---|---|---|---|
| `outline_box` | `line_role`, `line_width_pt` | `pad_role` (outward), `dash`, `shape` (`rect`, `ellipse`, `rounded`) | an unfilled box on the anchor |
| `band` | `fill_role` | `pad_role`, `label` (`inside_top_left` ...) | a fill UNDER the host (zone shading); a table row with its own fill hides it and is refused |
| `reference_line` | `line_role`, `line_width_pt` | `dash`, `label` (`end_outside`, `end_above`, `end_below`, `start_above`, `start_below`; vertical: `end_outside`, `end_right`, `end_left`, `start_right`, `start_left`), `gap_role` | a line across the plot at a value or category |
| `arrow` | `line_role`, `line_width_pt`, `label`, `position`, `gap_role` | `dash` | the label beside the anchor at `gap_role`, an arrow from it to the anchor |
| `callout` | `line_role`, `line_width_pt`, `fill_role`, `label`, `position`, `gap_role` | `pad_role` (inside the box), `head` (`none`, `arrow`) | a filled box with a leader to the anchor |
| `bracket` | `line_role`, `line_width_pt`, `side`, `gap_role`, `depth_role` | `style` (`square`, `brace`), `label` | a bracket opening toward the span, beyond its marks, label beyond it |
| `badge` | `fill_role`, `label`, `position` | `gap_role`, `pad_role` | a filled circle holding one line (a number keyed to text) |

`position` is one of `above`, `below`, `left`, `right`, `above_left`, `above_right`,
`below_left`, `below_right`. Labels are `{"text", "role", "ink_role"}` plus optional
`position`, `align` and `max_width_share` (a fraction of the host's width to wrap at,
for every kind; left out, the label is one line). Every label is measured with the
solver's ruler at the page's scale and written with its measured lines; a label whose
word is wider than its line (it would break between characters) is refused, and a band's
label must fit inside the band.

What the build refuses, by name, under `problems`:

- `annotation refused`: a key, anchor or role it cannot honour (`axes.value needs
  numeric min < max`, `cross_between ... is required`, `value 45 is outside axes.value
  20..44`, `value '36.5' on axes.value is not a number`, `'Committee' ... breaks between
  characters`, a band label wider than its band, `body row 10 (emphasis) is filled with
  color.accent1, which hides a band drawn under it`).
- `annotation collides`: the annotation covers another page element, another
  annotation, the page edge, a reserved chrome zone, or a mark of its host it does not
  anchor to (`covers mark 'Range' 'Dividend discount model'`). A reference line crosses
  the marks by design; its label may not. A band's fill is ground and collides with
  nothing; its label lies under the host, so it may cover no mark at all, and another
  annotation may not cover it.
- `annotation covers chart text`: after the render, the words LibreOffice drew in the
  host (tick labels, data labels, legend, cell text, read with `pdftotext -bbox`) that a
  stroke crosses or a box covers (`'mean' (reference_line) covers 4 word(s) its host
  drew: ['1.62x', '1.59x', '1.55x', '1.48x']`). An outline's interior is not a cover, so
  a box around a cell's text passes; a band's label counts as a box. With `--no-render`
  the report says `not checked: --no-render`; a render that was asked for and wrote no
  readable PDF refuses the page (`annotation render check failed`).
- `contrast`: every label is scored like any text, against its own box's fill, a
  band, a filled plot (`plot_fill_role` with `plot_area`) or the page.

Positions are computed in EMU from `plot_area`, the axis scale, `gap_width`, `overlap`
and the series count (`scripts/chart_geometry.py`), and were measured against
LibreOffice 24.2 renders of 13 chart configurations and a table (408 features, worst
1.07 px, mean 0.24 px at 1600 px: `oracles/chart_geometry_probe.py`). Whether
PowerPoint places the inner plot rectangle the same way is not measured.

Proven on: `examples/keybank-annotations.deck.json`, four pages rebuilt from corpus
exhibits on keybank (all four fit, the judge files the deck under keybank).

### Comps table: the median multiples and the subject row boxed

keybank p5 (red boxes around the median multiples and the subject row; in the coded
corpus, comps tables emphasise the median row on 12 of 15 and the subject on 8 of 15). The median
row is shaded with `emphasis_rows`; the boxes are annotations.

```json
"styling": {"comps": {"emphasis_rows": [10], "emphasis_fill_role": "color.accent1"}},
"annotations": [
 {"id": "median-box", "host": "comps", "kind": "outline_box", "anchor": {"cells": [[10, 1], [10, 2]]},
  "line_role": "color.negative", "line_width_pt": 1.5},
 {"id": "subject-box", "host": "comps", "kind": "outline_box", "anchor": {"row": 13},
  "line_role": "color.negative", "line_width_pt": 1.5}]
```

### Sensitivity grid: the scenario region boxed, a header group bracketed, the base case keyed

keybank p7 (a red box around the realistic region; corpus: a boxed cell or
region on 17 of 29 sensitivity grids). The bracket needs room above the header: the table sits in a
region with `pad_role`, and the collision check refuses it if the lead text is in the
way.

```json
"annotations": [
 {"id": "scenario", "host": "grid", "kind": "outline_box", "anchor": {"cells": [[1, 3], [5, 5]]},
  "line_role": "color.negative", "line_width_pt": 1.5},
 {"id": "syn-range", "host": "grid", "kind": "bracket", "anchor": {"header_group": {"columns": [3, 5]}},
  "side": "above", "gap_role": "space.xs", "depth_role": "space.xs", "line_role": "color.rule", "line_width_pt": 1.0,
  "label": {"text": "Realistic synergies", "role": "type.caption", "ink_role": "color.ink"}},
 {"id": "base-key", "host": "grid", "kind": "badge", "anchor": {"row": 3}, "position": "left", "gap_role": "space.xs",
  "fill_role": "color.accent2", "label": {"text": "1", "role": "type.caption", "ink_role": "color.ink_inverse"}}]
```

### Football field: the offer and unaffected prices as lines, the selected range as a zone

bmo p125 (the current offer as a labelled dashed line; corpus: a reference line at
the offer on 4 of 4 football fields). On a horizontal bar with the categories reversed the
value axis and its tick labels move above the plot, exactly where an `end_outside`
label goes: the render check caught `Unaffected $27.80` over the `$24` tick, and the
fix was to hide the value axis (the data labels carry the values). It also caught the
offer line through the `$35.0` label: move the line's label, or the data, never the
check.

```json
"annotations": [
 {"id": "selected", "host": "ff", "kind": "band", "anchor": {"values": [29, 35]}, "fill_role": "color.accent1"},
 {"id": "selected-note", "host": "ff", "kind": "callout", "anchor": {"values": [29, 35]}, "position": "below", "gap_role": "space.xs",
  "pad_role": "space.xs", "fill_role": "color.surface", "line_role": "color.rule", "line_width_pt": 0.75,
  "label": {"text": "Committee range $29-35", "role": "type.data_label", "ink_role": "color.ink"}},
 {"id": "offer", "host": "ff", "kind": "reference_line", "anchor": {"value": 36.5}, "line_role": "color.negative", "line_width_pt": 1.5, "dash": "dash",
  "label": {"text": "Offer $36.50", "role": "type.data_label", "ink_role": "color.negative", "position": "end_outside"}}]
```

### Ranking: the subject highlighted, the mean as a line, an arrow carrying the subject's figure

bcg-dallas p15 and bmo p33 (sorted, labelled, subject highlighted, a dashed mean line;
corpus: all three on 5 of 5 horizontal-bar rankings in one consulting group). The subject
bar's own label is hidden (`points[...].label.show: false`) and the arrow's label
carries its figure; data labels sit at `inside_base`, because at `outside_end` the mean
line crossed four of them and the render check refused the page.

```json
"annotations": [
 {"id": "mean", "host": "rank", "kind": "reference_line", "anchor": {"value": 1.66}, "line_role": "color.ink_muted", "line_width_pt": 1.0, "dash": "dash",
  "label": {"text": "Mean 1.66x", "role": "type.data_label", "ink_role": "color.ink_muted", "position": "end_outside"}},
 {"id": "subject", "host": "rank", "kind": "arrow", "anchor": {"point": {"series": 0, "category": 3}}, "position": "right", "gap_role": "space.md",
  "line_role": "color.accent2", "line_width_pt": 1.0,
  "label": {"text": "1.71x, +0.05x", "role": "type.data_label", "ink_role": "color.accent2"}}]
```

Prefer native where a move can be native: a median row is `emphasis_rows`, a highlighted
bar is a point `fill_role`, a total is a series label. An annotation is a shape over the
chart: it does not move when someone edits the chart's data.

## What a default looks like in the report

A bare `{"type": "COLUMN_CLUSTERED", "categories": [...], "series": [{"name", "values"}]}`
builds, and its page lists 26 lines under `chart_defaults_taken`, among them:

    series[0].fill_role: no fill written: the renderer's automatic colour by series index
    series[0].labels: no data labels
    axes.category.line_role: no stroke written: each renderer reads the theme's line style, and they differ (measured)
    axes.value.tick_marks: out (python-pptx's chart part)
    gap_width: 150 (python-pptx's chart part)
    legend: none (OOXML absence)
    text: chart text inherits the theme's face, size and colour

None of those is the house's style; each is a choice to write.
