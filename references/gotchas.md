# OOXML and renderer facts, each measured

- LibreOffice fits more text than PowerPoint on 92 of 600 measured boxes; the ruler shrinks
  the width budget (5,933 EMU with the Pillow ruler, 20,234 with HarfBuzz) so a measured
  line never runs long in PowerPoint (600 boxes measured in both).
- Line pitch is 1.2 times the size, font independent (7 families); font tables are wrong by
  up to 20%.
- Table row heights in the file are minimums; PowerPoint realises lines x 1.2 x size plus
  the cell margins (exact to the EMU on 5 sizes and 4 families). The fitter writes exactly that.
- A deck's theme is reached through the master's relationship, never by globbing theme
  parts: notes and handout masters carry the stock palette.
- Colour maps apply before the theme lookup; a slide or layout may override the map.
- A bullet glyph needs its bullet font (Wingdings squares render as a section sign without
  it); the extractor records it and the emitter writes it.
- Hidden slides are not exported by the renderer; the gallery counts and skips them.
- A figure and its unit, a currency mark and its figure, a period prefix and its year
  (`$1.2 bn`, `EUR 40 mm`, `FY 2024`, `12.5 %`) never break across lines: the ruler treats
  that space as unbreakable and the emitter writes the measured lines.
- A master that spaces paragraphs by percent (`spcPct`) is read as points at the boundary;
  the emitter never writes a negative `spcPts`, which LibreOffice answers by drawing
  nothing.
- A shape's `p:style/a:fontRef` sets its default text colour, above the master's default
  and below the run's own; a table style's `tcTxStyle` colour does the same for cells.
- A scanned PDF's text layer is not evidence; triage decides per page, and the deck's size
  is the paper it was printed to, not the letter page around the image.
- An interrupted `soffice` leaves a lock in its profile; every render uses a fresh profile.
- LibreOffice 24.2 draws nothing for the first XY scatter series when a later series has
  more points; the emitter writes every scatter and bubble series with the group's largest
  point count, the extra points blank.
- `c:varyColors` absent is read oppositely by the two renderers; the emitter always writes
  `val=0`, so a pie whose slices differ names a fill per point.
