# Components: net-new visual elements that still obey the guide

A component is a function from data to a layout subtree. It never writes a colour, a
size or a coordinate: it writes token roles (`type.*`, `color.*`, `space.*`) and
proportions (flex weights, grid tracks), and the layout solver turns those into
measured boxes inside whatever box the slide gives it. That is what makes a component
the reference never showed come out in the reference's style: every value it draws is
resolved through the guide, and the same code renders a football field on a dark
consulting deck and on a white banking deck.

## Layout of a component

    components/<kind>/
      spec.json      what it needs: data schema, size domain, variants, tests
      expand.py      def expand(data: dict, box: dict, guide: dict) -> dict

`box` is `{"width_emu", "height_emu"}`, the box the slide offers (the solver's probe
box); `expand` picks a variant by it (wide, tall, narrow) and returns a region tree in
the layout spec grammar (see `scripts/layout.py`): regions with `flex`/`grid` layouts,
elements of kind `text`, `rule`, `rect` (a filled box: `{"kind": "rect", "fill_role":
..., "line_role": ...}`), `table`, `image`. Element ids must be prefixed with the
component instance id the slide gives (`data["_id"]`) so two instances never collide.

## The contract tests, and why there are four

`spec.json` lists three SHOWN boxes (the sizes the author designed for) and one HELD-OUT
box with a different data instance. `scripts/component.py check <kind>` runs all four:
expand, solve with the guide, refuse any overlap, containment or floor violation, emit
each onto the reference template, render a contact sheet, and judge the rendered slides
against the reference. The author looks at the sheet. A component is admitted to the
library only when all four pass: the held-out case is what stops a component that was
tuned to its three examples.

## What the author writes, in order

1. The data schema and three or four real data instances (not lorem).
2. The composition in words: what dominates, what is support, how it reads
   (references/design/deliberate_composition.md).
3. `expand`: proportions from the data (a bar's length is a weight, never an EMU),
   roles from the guide, nothing else.
4. `component.py check`, look, fix, repeat; then `component.py admit`.

## Merit case

deckgen runs generated component code in a sandbox because a server executes code a
model wrote for strangers. Here the model writes and runs the code in its own session,
which is already the sandbox, so the contract tests, the held-out case and the render
review are kept and the container is not.
