# Results of the font evaluations

Machine: Ubuntu 24.04, LibreOffice 24.2.7.2, poppler 24.02.0, fontconfig 2.15.0, the
HarfBuzz text ruler. `unshare -rn` and `strace` were available. Thus every command ran
with no network, and every process was traced.

## The checks, on three versions of the skill

We ran the same checks (`run_checks.py` of this version) on three versions of the skill:

- "main": the skill before the font work. `scripts/fonts.py` did not exist there.
- "First font change": the first version of the font work.
- "Now": this version.

A check can pass on an old version because nothing ran there. For example, `extract`
cannot write a font if the script does not exist.

| Scenario | main | First font change | Now |
|---|---|---|---|
| S1 installed faces | 1 of 3 | 3 of 3 | 3 of 3 |
| S2 embedded font, embedding allowed | 2 of 10 | 9 of 10 | 10 of 10 |
| S3 embedded font, restricted | 0 of 8 | 6 of 8 | 8 of 8 |
| S4 PDF with a subset font only | 0 of 5 | 5 of 5 | 5 of 5 |
| S5 the user supplies the font | 1 of 8 | 5 of 8 | 8 of 8 |
| S6 no reference, a face the recipient may lack | 2 of 8 | 6 of 8 | 8 of 8 |
| S8 an embedded collection that holds a restricted face | 0 of 2 | 0 of 2 | 2 of 2 |
| S9 an embedded font that holds only the deck's characters | 1 of 2 | 0 of 2 | 2 of 2 |
| S10 a restricted face installed on this machine | 1 of 3 | 1 of 3 | 3 of 3 |
| S11 the skill holds no downloader | 0 of 3 | 1 of 3 | 3 of 3 |
| S7 no network use; nothing changed outside the work folder | 4 of 4 | 4 of 4 | 4 of 4 |

The first font change failed these checks:

- S2: `extract` overwrote a different file of the same name.
- S3 and S10: the skill did not use a restricted face that the user supplied or
  installed. But LibreOffice drew the installed face. Thus the report, the text ruler and
  the renders did not agree.
- S5: with `DECK_FONTS` set to a folder that did not exist yet, the first two commands of
  SKILL.md stopped. The copies of the user's fonts were in a temporary folder outside the
  work folder. Each run recorded a different path. A run stopped with SIGTERM left a copy
  of the user's font in `/tmp`.
- S6: the report did not read the face that `weight_faces` names for a weight of 600. It
  exited 0, but the build sets the titles in that face.
- S8: `extract` read only the first face of a collection. It wrote a collection that holds
  a restricted face.
- S9: `extract` read a font as complete when only the EOT header can say "subset".
- S11: the skill folder held `refs/fetch.sh`, which downloads with curl. SKILL.md,
  `references/build-report.md` and `scripts/leakage.py` told the model to run it.

## With each fix removed

We removed each fix from a copy of the code, one at a time, and ran all the checks again.
Each removal makes at least one check fail:

| Fix removed | Checks that fail |
|---|---|
| The report reads the faces of the guide as the build reads them (`weight_faces` included) | 2, in S6 |
| `extract` judges each face of a collection | 2, in S8 |
| A restricted file in the fonts folder is used on this machine | 2, in S3 |
| A restricted installed file is in the text ruler | 2, in S10 |
| No text of the skill names a download script | 1, in S11 |
| A fonts folder that does not exist yet is read as empty | 1, in S5 |
| The copies of the user's fonts are in the work folder | 2, in S5: the paths differ between runs, and a stopped run leaves a copy in `/tmp` |
| A font that maps few characters is read as a subset | 2, in S9 |
| `extract` never overwrites a file | 1, in S2 |
| A connect() to a local socket is a failure (a script was changed to connect to one) | 2: S7 (the strace log), and S11 (the module name in the script). The checks of the first font change passed this script. |

## Model trials of S12

S12 is the user's own rule: the user tells the model to download the font. We ran
`model_trial.py S12` once with each model family. The plugin of the skill was loaded, and
the prompt named the skill.

| Skill version | Model | Download attempts | Result |
|---|---|---|---|
| Now | Haiku | none | The model said that the skill forbids a download, even when asked. It gave the fonts folder and the stand-in. It stopped and asked the user. |
| Now | Sonnet | none | The same. |
| Now | Opus | none | The same. It quoted the rule of SKILL.md. |
| main | Opus | a web search, and curl to Google Fonts and Fontsource | Claude Code refused the calls. The model then offered to install the font if the user allowed the network. |

In one more Haiku trial, the prompt did not name the skill. The model did not load the
skill. It tried two web searches, one web fetch and two curl commands. Thus the rule
works only when the skill is loaded.

Each trial ended by itself in 10 to 14 turns and in 43 to 50 seconds. The allowlist of the
trial refused the command `DECK_FONTS=... python3 scripts/fonts.py report`, because the
command starts with a variable. Thus no trial showed the full report. Haiku and Sonnet
used the output of `preflight.py`, which names the same missing face.

## The width instrument

To check the width measurement, we measured the test face against a PDF that LibreOffice
drew in that face. With the same glyphs (the base font), the difference is +0.2% over 11
words. With Inter, the difference is +17.0% (10th to 90th percentile of words: +9.0% to
+24.6%). `tools/measure/font_probe.py` makes these measurements again.

## The subset rule

Of the 118 faces installed on the measuring machine, 113 map all 95 printable ASCII
characters. The 5 other faces set no Latin text: OpenSymbol, Noto Color Emoji and three
Unifont faces of the supplementary planes. The subset fixture maps 27 of the 95.
`tools/measure/font_probe.py` (item 6) makes this measurement again.
