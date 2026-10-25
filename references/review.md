# Reviewing the renders: the self-critique loop

## Contents
- The loop, its cap and keep-best
- What to look for, in order
- Writing a located finding
- Package checks before handing over
- What the renders cannot show

## The loop, its cap and keep-best

After each build, look at every rendered page at full size, beside the reference's nearest
pages, and write located findings as a senior banker or consultant reviewing a junior's
pages would. Then change the specs and build again. Never a score.

- Cap: at most 8 builds per 5-page section (fresh agents allowed 8 used 4 to 7, measured).
- Keep-best: keep every build's file and report. The best build is the one with the fewest
  refusals, then the fewest open findings of the first four kinds below, then the one you
  judge closest to the house side by side; not the last one, and never the one with the
  lowest judge distance alone.
- Stop when a round produces no new finding you can act on, or at the cap. Report the
  findings still open.
- A finding that a sentence in the specs cannot fix (a component defect, a renderer
  difference) goes into the report as a defect, not into another round.

## What to look for, in order

1. Mechanics: text cut at a box edge; elements sharing area; labels wrapping mid-word; a
   source line touching footer furniture; uneven gaps; a figure split from its unit;
   placeholder text; tick labels that do not sit at their values.
2. Consistency across pages: title position, chart text styling, source-line treatment,
   one element drifting between pages of one kind.
3. The message: can it be found in two seconds? Is the exhibit annotated where the claim
   lives, the way this house annotates (its `exhibit_habits`)? Does every stated figure
   compute from the page's own data?
4. The house: side by side with the house's best pages, what differs? Title register and
   length, where the claim sits, how dense, how the house marks emphasis, whether it draws
   gridlines and legends, how much it labels.
5. Generated-deck tells: card grids where the content is not a comparison, equal tiles,
   big numbers with no base or population, rounded everything, centred text, three of
   everything, uniform spacing, one composition repeated where pages are not siblings.
   Each is a tell only where this house does not do it.
6. What a managing director would circle in red, and what they would write beside it.

## Writing a located finding

Element id, what is wrong, the change:

- `takeaway: competes with the table; drop the fill, keep the rule`
- `ff axis: tick labels sit off their values and $14 is missing; the field cannot be read against its scale`
- `s3 commentary: column ends at 40% of the page height; give it the weight or add the next point`
- `s2 title: a claim sentence in a house that writes topic phrases; move the claim to the lead-in`

## Package checks before handing over

```bash
python3 scripts/pptx_tools.py validate work/out/deck.pptx --render
python3 scripts/pptx_tools.py validate work/out/deck.pptx --emit --guide work/ref/guide.json
```

The build already validated the package (relationships, one layout per slide, content
types, shapes inside the page, charts parse). `--render` reads the rendered page back and
names every paragraph that did not draw (a schema-invalid spacing value once blanked
sixteen bullets on a page that validated and judged clean). `--emit` reads what PowerPoint
and LibreOffice draw differently: a shared table edge declared differently on its two
cells, a stroke under 0.5pt the guide does not declare, any gradient, a chart without
`c:varyColors`, a run below its role's floor, a typed page number where the layout carries
the field. The emitter writes none of these; the check is for a deck edited by hand. Run
both before handing a deck over.

## What the renders cannot show

Renders are LibreOffice. Text breaks are the solver's measured breaks, so text draws as in
PowerPoint; charts and table edges can still differ slightly. A deck verified only in
LibreOffice is a known gap: open it in PowerPoint before release where one is available.
