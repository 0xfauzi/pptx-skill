# Typography: questions for holding the reference's hierarchy

The guide's type roles, size levels, floors and description are the reference's measured
typography, the strongest evidence you have: start there, and where a page departs, say why
in the report. Only measurable defects refuse (fit, floors, fonts). These are questions.

## Questions

- How many size levels does this reference actually write, and how close are their votes? If
  two or three levels carry similar weight, do your pages write at those sizes too, or
  does every run sit on `type.body`? (A generated section held at a 12pt body role, in a
  reference whose histogram put its mass at 11, 16 and 18pt, was not filed by the judge with
  `size_hist` carrying the distance.)
- Does each run land on one role? The emitter refuses literal sizes (roles, not
  literals), so a new level enters as a role the completion adds: at a size the reference
  shows, or at another size with a `why`, which is then tagged `off_ladder` and listed as a
  build warning with the judge's `size_hist` distance (complete_guide.py). The measured
  reason to prefer the reference's levels is the drift below.
- How do adjacent levels differ in this reference: by size, by weight, by ink, by case? Where
  this page adds a second dimension, what does it say that the reference's one does not?
- How does this reference emphasise inside running text: bold lead-ins (consulting 179 of 317
  pages, bank 26 of 231), colour, or neither? How many words does it emphasise at once?
- Are casing and alignment held per role across every page? Is body text flush where the
  reference sets it flush, and is centring kept for what the reference centres?
- Does any text sit below its family's floor? The solver does not descend below
  `max(floor_pt, absolute_floor_pt)`; when body content cannot fit above its floor, the
  page splits or re-arranges.
- Are fonts the reference's? A stand-in face is recorded under `typography.families.substitutes`
  only as fc-match's answer, so the measured face is the drawn face.

## Measured facts that bear on type

- Line pitch is 1.2 x size, font independent (7 families); single spacing is drawn at that.
- The absolute floor, 7.0pt, was measured on two screen media by one rater for Arial and
  Calibri; print was not measured.
- A strong model used exactly a guide's closed type scale (8, 9, 10, 11, 14, 24pt) where a
  weaker model invented 8.5, 9.5, 20 and 22pt (measured once): closed sets of roles are
  followed, continuous values drift.
