# Evaluations

End-to-end scenarios, a fresh-agent protocol and the blind round. None of this is a unit
test: every result is a real run on real reference files, recorded beside the claim it
supports. Company decks are confidential, so development runs these scenarios on the public
corpus (`refs/fetch.sh`, and the consulting PDFs named in each file); a deployment re-runs
the same scenarios on the company's own templates and past decks.

## Contents
- Scenario files
- Holding out the worked examples
- Running a scenario with a fresh agent
- Scoring a scenario
- The blind round (the primary success measure)
- Model matrix
- Recording results

## Scenario files

Each `NN-*.json` holds:

| key | what it is |
|---|---|
| `skills` | the skill under test |
| `target_spec_scenario` | the TARGET_SPEC 21.1 scenario it instantiates |
| `reference` | the reference type, the files (template, past decks, house decks), and what is known about the house |
| `brief` | what the user asks for, as the user would say it |
| `data` | every figure the pages may state; nothing else may be stated |
| `expected_behavior` | checkable statements, each with the `check` that decides it |

| File | Reference | What it exercises |
|---|---|---|
| 01-bank-pitchbook-valuation | native pptx pitch books on one master | topic titles, computed claims, football field, comps emphasis, bridge tie-out, pooled house variety |
| 02-bank-financing | the same house, financing deck type | variety a reader can see: exhibit structure read from the file, honest composition names, exhibit briefs |
| 03-consulting-working-draft-pdf | a 520-page mixed consulting PDF, vector pages 160 to 226 | triage and a page range, drawn chrome, part-counter titles, declared sibling runs, round-trip losses |
| 04-house-contrast-precedent | native pptx whose house sets white on its steel blue at 4.33:1 | contrast precedent from --reference, sensitivity region, measured source-line habit |
| 05-vector-pdf-title-band | a 20-page vector PDF pitch book, no template | blank template, drawn chrome, metric-alias faces, runs over the house's longest, bridge tie-out |
| 06-scanned-board-book | scanned PDF | raster intake, faces by eye, no variety evidence, judge cannot judge, logos |
| 07-extend-existing-deck | an existing deck | slides kept byte-identical, origin tags, new pages in its layouts |
| 08-confidentiality | scenario 01 with a seeded page library | the leakage report (chrome excluded), no network, library hygiene |
| 09-template-without-past-decks | a template file with several masters | template choice, habits with no evidence flagged |

## Holding out the worked examples

The skill ships worked examples made from public reference decks: a completion, a digest,
deck specs, plans and build proofs for keybank (`mi_keybank_first_niagara_fig_ma.pptx`),
the McKinsey board PDF (`mckinsey-calstrs-future-of-boards-2024.pdf`) and the Goldman
Airvana raster proof. An evaluation run on one of those decks grades the examples, not the
skill: in blind round 2 a generator on keybank found `examples/keybank.completion.json`
and the keybank digest, and step 2 could be copied instead of read off the renders.

`examples/PROVENANCE.json` ties every file under `examples/` to the reference it was made
from, by sha256 (or lists it as independent). Before any run on a reference, make the
skill copy the agent will see with that deck's examples held out:

```bash
python3 evals/holdout.py --reference refs/files/mi_keybank_first_niagara_fig_ma.pptx \
        [--reference OTHER ...] [--alias WORD ...] --out /abs/path/skill-under-test
```

It matches references by hash, not name; leaves out `evals/` (the expected behaviours);
refuses when an example file is not in `PROVENANCE.json` (a new example must say which
deck it came from before any evaluation runs); and prints every line of the copied tree
that still names a tested deck by an alias (the references cite measurements taken on
keybank, the McKinsey PDF and others). Read that list and record in the run's notes which
of those lines the agent could have used. Give the agent the `--out` tree as the skill,
never this checkout. A run on a deck with no worked examples (netflix, the BCG PDF) still
goes through it, with `--alias`, to get the naming list.

## Running a scenario with a fresh agent

1. Start an agent with only the held-out skill copy (above) and the scenario's reference
   files in a new empty working directory. Give it the `brief` and the `data` as the user
   would, and nothing else: not this README, not the expected behaviours, not earlier
   transcripts.
2. Let it run the skill's workflow to a delivered deck and final report. Build cap: 8 builds
   per 5 pages.
3. Ask it to return what it did, what it could not do, and a friction list: each item with
   what happened, a reproduction, and a severity. Every step it did by hand that a script
   should have done is a friction item.
4. Keep the transcript: which files it read and in what order, what it ignored, where it
   struggled. That is the input to the next revision of the skill (the skill author is a
   different agent from the one under test).

## Scoring a scenario

Check every `expected_behavior` statement with its `check`, against the files the run
produced (`deck.build.json`, `plan.check.json`, the deck, the renders, the report). Record
each as met, not met (with the evidence), or not checkable (with why). A statement is never
scored by reading the agent's own claim that it was met. A statement passes or fails only
on its measurable half: a claim computes, the subject can be found, totals tie, a page
fits, a warning is answered in the report. What a check calls a diagnostic (a title's
register, a variety measure, which device marks a place, how close a mark sits to the
house's) is recorded beside the score and never fails a run: the blind round below is the
judge of taste. Reproduce every friction item
before acting on it; measured on an earlier build, the large majority of 71 friction items
from six runs reproduced.

## The blind round (the primary success measure)

Per house: 5 real pages from the company's best decks (or the reference) and 5 generated
pages from the scenario runs.

1. Render all ten to the same pixel size, format and encoding (re-encode every image to one
   format; real scanned pages were otherwise twice the file size of generated ones). Hash
   file names and ids; mix the order within the house.
2. Remove visible non-design tells where possible (a gradient at the page edges, scan
   texture) and record those that remain.
3. Raters are, by preference, the company's own senior bankers or consultants; record each
   rater's background, and use more than one where possible. Real pages shown to raters are
   the company's own and stay inside the company.
4. For each page the rater guesses real or generated and rates quality 1 to 5 (1 would not
   send, 3 usable with edits, 5 client-ready), with an optional note.
5. Score per house and overall: accuracy with its binomial tail probability against chance;
   mean quality real against generated; which generated pages fooled the rater; the notes.

Target: accuracy within the chance band at p = 0.05 per house, and generated quality at or
above real. Baseline on an earlier build (one rater, 6 public houses, 60 pages): 45 of 60
correct (chance 30, P(X >= 45) = 0.00007); quality real 3.53, generated 2.93. The rater
caught every generated page in the two houses where claim titles met a topic-title
reference, and noted low chart and layout variety and missing logos. The style judge filed
five of those six houses; it does not track the rater.

## Model matrix

Run the scenarios on each model tier the skill is used with (a fast, a balanced and the
strongest model). Record per tier: gate failures, builds used, open findings at hand-over,
friction items, blind-round results. An instruction that helps one tier can hurt another
(measured once: a longer rule set improved a strong model's pages and caused a weaker
model's first collisions).

## Recording results

For each run keep, beside the scenario: the transcript, the delivered deck and its
`deck.build.json`, the renders, `plan.check.json`, the final report, the scored expected
behaviours and the friction list. Every number later quoted in `SKILL.md` or a reference
file must point at such a record, and is re-run before each release.
