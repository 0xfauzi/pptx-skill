# Components: net-new visual elements that still obey the guide

A component is a function from data to a layout subtree. It never writes a colour, a
size or a coordinate: it writes token roles (`type.*`, `color.*`, `space.*`) and
proportions (flex weights, grid tracks), and the layout solver turns those into
measured boxes inside whatever box the slide gives it. That is what makes a component
the reference never showed come out in the reference's style: every value it draws is
resolved through the guide, and the same code renders a football field on a dark
consulting deck and on a white banking deck.

## Layout of a component

The components here ship with the skill and are read-only. A new component, or a fork of
one of these under a new name, lives in your components directory, a work directory
outside the skill passed as `--components DIR` to `build_deck.py`, `layout.py capacity`
and `component.py`; `component.py admit` writes every admission record there.

    <kind>/
      spec.json      what it needs: data schema, size domain, variants, tests
      expand.py      def expand(data: dict, box: dict, guide: dict) -> dict

`box` is `{"width_emu", "height_emu"}`, the box the slide offers (the solver's probe
box). A component is a worked example to read and fork per reference (or per look you chose), not the one way to
draw its exhibit. It returns a region tree in the layout spec grammar (see
`scripts/layout.py`): regions with `flex`/`grid` layouts, elements of kind `text`,
`rule`, `rect` (a filled box: `{"kind": "rect", "fill_role": ..., "line_role": ...}`),
`table`, `image`. Element ids must be prefixed with the component instance id the slide
gives (`data["_id"]`) so two instances never collide.

What the slide can say, and what the component says back:

- `data["variant"]` asks for any variant spec.json declares; with none asked, `expand`
  picks one by what the box holds. A variant the data cannot carry is refused by name
  (a ValueError the build reports), never swapped for another.
- `data["roles"]` and, where a component has them, `data["params"]` open every role and
  constant it would otherwise write (component_api `choices`: a name the component does
  not have is refused).
- The returned root region carries `report`: sentences naming the variant and why, each
  default left in place, and each role computed from the guide. The build lists them under
  the page's `component_notes`.

## The contract tests, and why there are four

`spec.json` lists three SHOWN boxes (the sizes the author designed for) and one HELD-OUT
box with a different data instance. `scripts/component.py check <kind>` runs all four:
expand, solve with the guide, refuse any overlap, containment or floor violation, emit
each onto the reference template, render a contact sheet, and judge the rendered slides
against the reference. It then asks for every declared variant by name at all four boxes
(with `variant_data`, what a variant needs that the test data cannot give, such as a
panel's fill role) and records where each fits. The author looks at the sheet. A
component is admitted to the library only when all four pass and every declared variant
draws at one box at least: the held-out case is what stops a component that was tuned
to its three examples, and the variant matrix is what keeps a declared variant from
being a name nothing can reach.

## What the author writes, in order

1. The data schema and three or four real data instances (not lorem).
2. The composition in words: which parts lead and which support, or whether they are
   co-equal, and how it reads (references/composition.md).
3. `expand`: proportions from the data (a bar's length is a weight, never an EMU),
   roles from the guide, nothing else; every constant open through `data` and reported
   when left in place.
4. `component.py check`, look, fix, repeat; then `component.py admit --components DIR`.

The `admitted.json` files shipped here were written by `component.py admit` into a work
directory (keybank guide) and copied in by the maintainer; they name the sheet and
the reference by file name only.

## Merit case

A server-side generator runs model-written component code in a sandbox because a server executes code a
model wrote for strangers. Here the model writes and runs the code in its own session,
which is already the sandbox, so the contract tests, the held-out case and the render
review are kept and the container is not.
