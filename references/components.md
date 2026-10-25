# Components the reference never showed

## Contents
- The contract
- Checking and admitting
- The measurement API
- The admitted components

## The contract

When nothing in `components/` draws what a page needs (a football field, a bridge, a
league table with tombstones, a tracker), write one: `components/<kind>/expand.py`
exposes `expand(data, box, guide)` and returns a region tree in the page grammar with roles
only. Proportions are flex weights from the data (a bar's length is a weight, never an
EMU); fixed heights are spacing steps from the guide; the variant is chosen by what the box
can hold. `spec.json` declares the data schema, the size domain and four test boxes: three
shown and one held out with different data. `spec.json` may name `single_line_ids`, id
fragments of figures, ticks and marker labels that must never wrap. A component's ids
carry `data["_id"]` as prefix; paragraph `ink_role` and `align` reach the file. A component
the page leaves no room for is refused by name. Use one in a page as
`{"type": "component", "id": "ff", "kind": "football_field", "data": {...}}`.

## Checking and admitting

```bash
python3 scripts/component.py check KIND_OR_DIR --guide "$DECK_WORK/ref/guide.json" --template "$DECK_WORK/tpl.pptx" \
  --out "$DECK_WORK/components" --reference "$REF"
python3 scripts/component.py admit KIND_OR_DIR --out "$DECK_WORK/components"
```

`check` runs each test's `expand` twice in separate interpreters under two hash seeds and
compares the trees (a set iterated into children is the usual difference), solves each box
on a harness page emitted on the template (so it reserves the build's chrome zones), fails
a box with a contrast violation or a wrapped single-line id, and validates the package.
Look at the contact sheet before admitting. Admission requires all four boxes to solve with
no violation, and is bound to the guide it was checked with (`guide_reference_sha256`): a
football field admitted on one bank deck overflowed on a sister deck whose 12pt floor left
no headroom. Re-run `check` with every new guide; the build says so when the guide differs.
`KIND_OR_DIR` may be a path to a component under development.

## The measurement API

Never estimate a text width in a component ("0.6 em per character" wrapped "$8.2 to $12.4"
onto two lines). `expand` receives the guide with `guide["_api"]`, the solver's own
instruments: `text_width_emu(guide, role, text)` (the whole string at scale 1.00, cased,
tracked, bold when the role is), `line_pitch_emu(guide, role)`, `paragraph_spacing_emu`,
`fit_epsilon_emu`. A text element sized to `text_width_emu + fit_epsilon_emu` stays on one
line. By hand:

```bash
python3 scripts/component_api.py "$DECK_WORK/ref/guide.json" type.caption '$12.4 to $13.9'
```

The functions raise on a role the guide lacks, as the solver would; do not catch and guess.

## The admitted components

Each admitted on a bank pptx (three shown boxes, one held-out box with other data, two hash
seeds, single-line figures, contrast, a package that validates):

- `football_field`: valuation ranges on one shared axis, the marker drawn through every
  bar; wide or compact by measured label wrap. Seen on two renders and not yet fixed: the
  tick labels sat off their values, unevenly spaced, and on one page the $14 tick was
  missing; read the axis on every render.
- `title_block`: optional kicker, the title, a closing hairline; the data picks the variant.
- `bullet_stack`: co-equal points in the writer's order; two columns filled down then
  across when `width // 2 >= height`.
- `kpi_row`: ranked figures, never tiles; the lead takes the first accent that reads on the
  surface at 3:1. Horizontal when every figure measures onto one line, else label-left
  rows.
