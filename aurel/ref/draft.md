# No reference: the look is yours to choose

No reference deck was given, so nothing below is evidence of a habit. Every address is open; answer each one as a design choice, in one completion (complete_guide.py), with a why. Hard limits still hold: text fit is measured in the faces you name, contrast is scored on every run, nothing is set below 7.0pt, and specs name roles, never literals.

Questions to ask of the look, with the corpus's counts as evidence (never as a default): references/typography.md, references/composition.md, references/charts.md, references/tables.md, references/emphasis-and-decoration.md, references/titles-and-text.md.

## Open

- `/look_brief`: no reference: the look brief, written before any other answer: who reads the deck and where, the subject's own world, the data's character, the density it calls for and why, the look in words, what each colour means, why the type ladder is what it is, and what you rejected; references/no-reference-design.md walks the reasoning, complete_guide.py --shapes gives the keys
- `/reference/page`: no reference: the page size, {"width_emu": int, "height_emu": int, "why": "..."}: 16:9 at 13.333 x 7.5 in is 12192000 x 6858000 EMU, 4:3 at 10 x 7.5 in is 9144000 x 6858000; choose for where the deck will be shown
- `/typography/families`: no reference: the faces, {"major": "<face>", "minor": "<face>"}: faces installed or supplied in $DECK_FONTS (fonts.py report --guide checks them), so every fit is measured
- `/typography/roles/type.title`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.kicker`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.h1`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.h2`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.body`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.emphasis`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.caption`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.footnote`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.source_line`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.table_header`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.table_cell`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.axis_label`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/roles/type.data_label`: no reference: a type role of the ladder you choose (size, weight, face, case, ink); null when the look has no such text; no size below the 7.0pt absolute floor
- `/typography/bullets`: no reference: the bullet per level, {"0": {"glyph": "<glyph>", "font": "<face>", "indent_role": "space.<step>", "hanging_indent_role": "space.<step>"}}, or {} for text set without bullets
- `/color/roles/color.surface`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.surface_alt`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.ink`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.ink_muted`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.accent1`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.accent2`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.accent3`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.rule`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.positive`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.negative`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/color/roles/color.emphasis`: no reference: a colour of the palette you choose; null when the look has none (surface, ink and accent1 are required)
- `/spacing/steps`: no reference: the spacing scale you choose
- `/spacing/margins`: no reference: the page margins, {"left": {"emu": int}, "right": ..., "top": ..., "bottom": ...}
- `/chrome`: no reference: the page furniture drawn on every page (a rule, a page number, a label), or [] for none
- `/tables`: no reference: how tables are drawn: header, banding, rules, padding, alignment
- `/charts`: no reference: series colours, gridlines, labels and legends
- `/description`: no reference: the look you chose, in words: summary, typography, color, layout, tables, imagery, motifs, not_seen ([]), tone
- `/continuation`: no reference: what the deck does when a page continues onto the next, in words or {contd_mark, why}
