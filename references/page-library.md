# Building a company page library

## Contents
- Commands
- Triage and what to override
- Tagging
- Confidentiality and the manifest

## Commands

```bash
python3 scripts/library.py permit DECK --lib LIB --owner OWNER --source-type company \
  --images yes|no --by WHO --basis "what allows it"
python3 scripts/library.py build --lib LIB DECK [--skip ID:PAGES] [--keep ID:PAGES] [--exclude ID[:PAGES]]
python3 scripts/library.py tag --lib LIB tags.json            # {entry_id: {tag fields}}
python3 scripts/library.py check --lib LIB [--seal]
python3 scripts/library.py forget --lib LIB --deck ID
```

`LIB` lives in the company's working area, outside the skill directory: a company library
inside the skill directory is refused, and an external one there must sit in a directory
git ignores as a whole. One pick never mixes two companies' libraries.

## Triage and what to override

`build` refuses a deck with no `permit` record. It renders each page that is not excluded
and proposes a triage: cover (a declared title layout, or page 1), divider (a declared
section layout, or no exhibit and under a fifth of the deck's median words), disclaimer (a
legal phrase and no table or chart). Pictures in the same place on half the pages do not
count as exhibits. These rules are definitions, not measurements. A PDF states no tables or
charts, so on a PDF neither the divider nor the disclaimer rule fires: those pages are
proposed as content with their word count, and you skip them after looking (`--skip
deck-id:1,2,16`). On one bank pptx the triage matched 12 of 12 pages. Look at
`work/<id>/triage.png` and override with `--skip` and `--keep`; a page outside the deck, a
deck not in this build, or a page named by both is refused.

## Tagging

Each kept page gets a stub whose tag fields are null (`house_type`, `composition_family`,
`composition_as_recorded`, `title`, `title_register`, `exhibits` with `type`, `family`,
`data_shape`, `message`, `annotation_moves`, `annotations_as_recorded`, then
`emphasis_devices`, `craft`, `why_instructive`, `designer_questions`). Fill them after
looking at `look_at`. `[]` means you looked and found none. A designer question opens with a
sentence ending in `?`. Families and moves are the vocabulary's slugs. `check` exits 1 while
any kept page is untagged and names each; `pick` ranks only tagged entries and says how many
were left out.

## Confidentiality and the manifest

`--images no` keeps no page image: entries carry tags only, and `check --seal` deletes the
renders. Permitting a deck again with `--images no` deletes its kept images at once.
`--exclude` deletes every file that shows or lists the page, and an excluded pptx slide is
emptied in a temporary copy before rendering, so it is never drawn. Every file is listed in
`manifest.json` with the source hash and the pages it derives from; `check` refuses
unlisted files, files derived from an excluded page, and kept images on a deck whose
permission keeps none. Library entries are context for the designer: never copy a past
deck's client names or figures into a new deck.
