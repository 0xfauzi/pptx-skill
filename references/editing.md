# Working on an existing deck

## Contents
- Commands
- Rules

## Commands

```bash
python3 scripts/pptx_tools.py text deck.pptx                                   # text per slide, tables as rows, layout named
python3 scripts/pptx_tools.py layouts deck.pptx                                # masters, layouts, placeholders with boxes
python3 scripts/pptx_tools.py template deck.pptx -o work/tpl.pptx --keep 1,4,7  # a template that keeps chosen pages
python3 scripts/pptx_tools.py duplicate deck.pptx --slide 3 -o out.pptx --after 5
python3 scripts/pptx_tools.py delete deck.pptx --slides 2,5 -o out.pptx
python3 scripts/pptx_tools.py clean deck.pptx -o out.pptx                      # drop unreferenced parts
python3 scripts/pptx_tools.py validate out.pptx --render
```

`duplicate` copies a slide's charts with their own workbooks, so editing the copy's data in
PowerPoint leaves the original alone.

## Rules

- The deck's existing slides are the reference. They are not re-solved or restyled.
- Extract the style from the deck itself (tagged generated slides are skipped), and
  combine it with the company's guide for its template when that template is in the library.
- Build new pages on a template that keeps the pages you keep (`template --keep`), using
  its layouts; append them. To replace a page: delete it, build the new one, and restore
  the order with `duplicate` and `delete`: structure first, content second.
- Every generated slide carries an origin tag (`p:tags` with `pptx-skill` = `generated`,
  which survives a PowerPoint save), so a deck you extended can be its own reference again
  without learning from your pages; `--include-generated` overrides.
- Nothing from another past deck enters unless the user supplied it for this deck.
