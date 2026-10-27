# OOXML and renderer facts, each measured

- LibreOffice fits more text than PowerPoint on 92 of 600 measured boxes; the ruler shrinks
  the width budget (5,933 EMU with the Pillow ruler, 20,234 with HarfBuzz) so a measured
  line never runs long in PowerPoint (600 boxes measured in both).
- LibreOffice 24.2.7 is not always the looser: a 7.5pt Liberation Sans line measured
  3,769,677 EMU in a 3,793,787 EMU box (24,110 EMU of slack, more than the HarfBuzz shrink)
  was wrapped, its box drawn in 3 lines where 2 were written. How often, at which sizes
  and faces, is unmeasured; the build reads the render's lines per box and refuses the
  page (`renderer divergence: text wrapped`, build-report.md).
- LibreOffice 24.2.7 drops category labels on a horizontal bar chart whose band is
  shorter than one line of the label: 14 names at 8pt drew 7 at a band 0.99 of a line and
  all 14 at 1.11, over six heights. It wraps a centred column label at its
  spaces or runs it past the bar's sides, unpredictably ('First-lien / TLB 3.75x' wrapped,
  'Senior notes 1.25x' beside it ran over). A category label turned -90 degrees draws on
  one line in a slot narrower than its word. The build reads each chart's words off the
  render (`renderer divergence: chart text`, build-report.md); a written break (`\n` in a
  point label's text) is two lines in both renderers.
- LibreOffice sets a line chart's `above` and `below` labels (no markers) a gap from their
  point that depends on the face and the size and does not grow with the size: 24,800 to
  41,900 EMU above and -18,900 to 43,100 EMU below over Liberation Sans, Carlito, Gelasio
  and Inter at 6 to 14pt (`tools/measure/label_probe.py` in the source repository; Gelasio's tall word box overlaps its
  point). On a steep line the neighbouring segment then runs through the label. The build
  predicts that with the gap measured for the face and size (`LINE_LABEL_GAP_EMU`) and reads
  it off the render, holding the line to each face's measured ink band
  (`chart label covered`).
- LibreOffice sets an `inside_base` label on a horizontal bar 35,801 EMU past the bar's base,
  at every face and size measured, and never wraps or moves it: a label longer than the bar
  less that runs past the bar's end onto the plot. The build measures it and scores its ink
  there (`contrast`); an `inside_end` label ends 29,303 to 47,136 EMU short of the bar's end
  (`tools/measure/label_probe.py` in the source repository).
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
