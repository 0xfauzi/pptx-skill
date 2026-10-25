# Typography: questions for holding the house's hierarchy

The guide's type roles, size levels, floors and description are the house's typography;
these questions are for applying them, never rules that override them.

## Questions

- How many size levels does this house actually write, and how close are their votes? If
  two or three levels carry similar weight, do your pages write at those sizes too, or
  does every run sit on `type.body`? (A generated section held at a 12pt body role, in a
  house whose histogram put its mass at 11, 16 and 18pt, was not filed by the judge with
  `size_hist` carrying the distance.)
- Does each run land exactly on one role? An intermediate, one-off size reads as an error;
  the emitter refuses literal sizes, so a new level enters only as a role the completion
  added at a size the reference shows.
- How do adjacent levels differ in this house: by size, by weight, by ink, by case? Copy
  the house's dimension rather than adding a second.
- How does this house emphasise inside running text: bold lead-ins (consulting 179 of 317
  pages, bank 26 of 231), colour, or neither? How many words does it emphasise at once?
- Are casing and alignment held per role across every page? Is body text flush where the
  house sets it flush, and is centring kept for what the house centres?
- Does any text sit below its family's floor? The solver never descends below
  `max(floor_pt, absolute_floor_pt)`; when body content cannot fit above its floor, the
  page splits or re-arranges.
- Are fonts the house's? A stand-in face is recorded under `typography.families.substitutes`
  only as fc-match's answer, so the measured face is the drawn face.

## Measured facts that bear on type

- Line pitch is 1.2 x size, font independent (7 families); single spacing is drawn at that.
- The absolute floor, 7.0pt, was measured on two screen media by one rater for Arial and
  Calibri; print was not measured.
- A strong model used exactly a guide's closed type scale (8, 9, 10, 11, 14, 24pt) where a
  weaker model invented 8.5, 9.5, 20 and 22pt (measured once): closed sets of roles are
  followed, continuous values drift.
