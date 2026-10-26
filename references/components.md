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
EMU); fixed heights are spacing steps from the guide. Every declared variant can be asked
for by `data["variant"]`; with none asked, the component picks one by what the box holds
and says which and why. Every role and constant it would write is open through
`data["roles"]` (and `data["params"]`), and each default it leaves in place is listed under
the page's `component_notes` (the component's `report`). A shipped component is a worked
example to read and fork for this house, not the one way to draw its exhibit. `spec.json` declares the data schema, the size domain and four test boxes: three
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

`check` asks for every declared variant at all four boxes (`variant_data` in spec.json
gives what a variant needs that the test data cannot, such as a panel's fill) and admits
only a component each of whose variants draws at one box at least; the check lists where
each fits, fails, or is refused by the component. It runs each test's `expand` twice in separate interpreters under two hash seeds and
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
`fit_epsilon_emu`, `space_emu(guide, role)`, `contrast(guide, role_a, role_b)`,
`reading_role(guide, candidates, grounds)` (the first role that reads at 3:1 on every
ground: how a mark or a lead picks an ink, instead of an accent by its number) and
`choices(data, key, defaults, where)` (the component's constants, open to the slide). A text element sized to `text_width_emu + fit_epsilon_emu` stays on one
line. By hand:

```bash
python3 scripts/component_api.py "$DECK_WORK/ref/guide.json" type.caption '$12.4 to $13.9'
```

The functions raise on a role the guide lacks, as the solver would; do not catch and guess.
`football_field` refuses to expand without the API: an estimated width is not a measurement.

## The admitted components

Each admitted on a bank pptx (three shown boxes, one held-out box with other data, two hash
seeds, single-line figures, contrast, a package that validates):

- `football_field`: valuation ranges on one shared axis, the marker drawn through every
  bar; `wide` or `compact` (asked, or chosen by measured label wrap and box size, with the
  reason). The marker takes the first accent that reads 3:1 on the page ground and the
  bands the first other accent (on keybank the marker is the deep blue at 11.2:1 and the
  bands the light grey, where accent1 had put a 1.5:1 grey marker on blue bars); roles
  and the label share, line cap, minimum width, value share and marker width are open.
  Seen on two renders and not yet fixed: the tick labels sat off their values, unevenly
  spaced, and on one page the $14 tick was missing; read the axis on every render.
- `title_block`: optional kicker, the title, a closing hairline (`rule: false` leaves it
  out); the data picks the variant, and asking for `no_kicker` with a kicker in the data
  is refused (the kicker would be dropped).
- `bullet_stack`: co-equal points in the writer's order; two columns filled down then
  across when `width // 2 >= height`; item role, gaps and bullet level open.
- `kpi_row`: figures with labels; the lead (`lead`, default the first, null for co-equal
  figures) takes the first accent that reads on its ground at 3:1. Horizontal when every
  figure measures onto one line, else label-left rows; `panel` (filled tiles) only when
  asked for, with its fill role: big-number or KPI panels are on 8 of 578 coded corpus
  pages and no bank page (composition.md), so the report asks of each figure: of what,
  and for whom?
