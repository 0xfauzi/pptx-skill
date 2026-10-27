# Development material

Nothing under `dev/` is installed with the skill. The marketplace's one plugin has the
source `./plugins/designing-presentations`, so the plugin root, which Claude Code copies into
its cache, holds only `.claude-plugin/plugin.json` and `skills/designing-presentations/`; a
manual install and the claude.ai zip take the skill folder alone. Paths in the skill's text
that start with `dev/` name files here, in the source repository only.

| Path | What it is |
|---|---|
| `TARGET_SPEC.md` | the target specification the skill is built against |
| `PORT_AUDIT.md` | every port from the predecessor system, its assumption and its check, one row per item, round by round |
| `evals/` | ten end-to-end scenarios, the blind-round and fresh-agent protocol, and `holdout.py` (a copy of the skill with the worked examples of the decks under test held out; no `--reference` for a run with no reference) |
| `oracles/` | the scripts behind every "Checked by" in `PORT_AUDIT.md` |
| `proofs/` | the build reports and notes of the worked examples in `plugins/designing-presentations/skills/designing-presentations/examples/` (filed by `tools/file_proofs.py`: machine paths read `$WORK`, `$SKILL`, `$DECKGEN`, `$INPUTS`) |
| `showcase/` | the sources of the four gallery decks in the top-level README (figures script, plan, completion, and page specs or the script that writes them), `rebuild.sh` (one deck from its sources to a validated .pptx and renders) and `sheet.py` (the README's images from the renders) |
| `tools/file_proofs.py` | files a rebuild's build reports into `proofs/`, each machine path named by a placeholder; a report with an unmapped home or temporary path is refused |
| `tools/package_skill.py` | the claude.ai and API upload zip, checked against the upload rules |

No unit tests are kept: the proofs are end-to-end runs on real reference files, rebuilt
from a fresh extraction each round and compared report by report and render by render.

## What the review round found

Four reviewers ran the skill cold on a deck no proof had touched, attacked the judge,
fed it hostile inputs and judged the pages as a managing director would; skeptics then
tried to refute each finding. The reproduced ones are fixed in this tree and listed in
`PORT_AUDIT.md` (here): a percent paragraph spacing read as negative points that blanked every
bullet in LibreOffice, white labels read as black because a shape style's font reference
was ignored, the judge blind to overlap and overflow, a panel the agent could choose to
pass, table text with no ink on a dark reference, a football field that never drew the
offer it was about, titles false against their own exhibit. Not done, recorded: table
column levelling by added line count, paragraph rhythm per composition family.

## Adopted and rejected, on merit

Judged against the goal (any reference, dense pitch-book pages, novel components, agent
designs, instruments measure):

- Adopted from the predecessor: the inheritance-resolving reader, the token-role guide with
  provenance, the layout solver and text ruler, the gallery, the component admission
  contract, master reuse as the template. Its nine design doctrines were adopted and
  later rewritten as questions plus measured tendencies from the 578-page coded corpus:
  several of their rules (claim titles, label only what matters, one emphasis per
  table, same-sized panels are a dashboard, fills as a last resort, a source line on every
  data page) contradicted the corpus counts.
- Adopted that nobody proposed: a fingerprint judge with fitted weights (the extractor's
  own opinion is not evidence); drawn chrome for PDF references; a per-series contrast rule
  for chart labels; a render font report that names metric aliases so the agent does not
  copy letterforms from a substituted render.
- Rejected: the densification search and splitter (unbuilt in the predecessor too; here the agent
  proposes arrangements and the solver checks them), the budget ledger and ADK agents, the
  user-correction overlay, python-pptx for reading (it hides inheritance), unit tests in the
  repo (the proofs are end-to-end runs with no mocks).

