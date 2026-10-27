# Font evaluations

These evaluations test how the skill handles fonts. The skill must never download a font.
When a font is missing, the skill must tell the user.

We wrote the scenarios before we wrote the code that they test. Anthropic's skill-authoring
guide tells skill authors to do this ("Build evaluations first",
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).

## Contents of this folder

| File | What it does |
|---|---|
| `scenarios.json` | The seven scenarios. Each scenario has a query, the files, and the expected behavior of the model. |
| `make_fixtures.py` | Makes the test files. It downloads nothing and installs nothing. |
| `run_checks.py` | Runs the scripts of the skill for each scenario and checks the results. |
| `audit_run.py` | Runs one Python script and logs each network event of that script. |
| `RESULTS.md` | The results before and after the change, and the results with each fix removed. |

## The test fonts

The scenarios need fonts that the machine does not have. `make_fixtures.py` makes these
fonts from a font that the machine has (Liberation Serif, or DejaVu Serif). It copies the
file and gives the copy a new family name, "Evalprobe Serif". For one copy, it also sets
the embedding permission (OS/2 fsType) to "restricted". The licences of Liberation Serif
(SIL Open Font License 1.1) and DejaVu Serif (Bitstream Vera licence) let you make a
changed copy under a new name. The copies stay in the work folder. The script never
installs them.

The script also makes:

- Decks (.pptx) that name the test fonts.
- Decks that embed a test font. The format follows ECMA-376 Part 1 (19.2.1.9 and
  19.2.1.10) and the W3C submission for Embedded OpenType. PowerPoint did not make these
  decks, because no PowerPoint is available here.
- A PDF that LibreOffice drew with the test font. The PDF holds a subset of the font.

## The scenarios

| Scenario | Input | Expected result |
|---|---|---|
| S1 | A deck whose fonts the machine has | The report exits 0. It proposes no stand-in. |
| S2 | A deck that embeds a font that allows embedding | The report asks for a licence confirmation. `extract` refuses without the confirmation. With the confirmation, it writes the font into the fonts folder and records the words of the user. Then the report exits 0, and LibreOffice draws the font. |
| S3 | A deck that embeds a restricted font | The report reads the font as missing. `extract` writes nothing. A restricted font file in the fonts folder is not used. |
| S4 | A PDF that holds only a subset of a font | The report reads the font as missing. It proposes a stand-in and measures its width against the text of the PDF. With a guide that does not use the font, the report exits 0. |
| S5 | The user puts the font file in the fonts folder | The report finds the file. The text ruler and LibreOffice use the file. With `DECK_FONTS` unset, the report stops and names the variable. |
| S6 | No reference; the guide names a font that the recipient can lack | Without the files, the report exits 3. With the regular file only, it asks for the bold file. With both files, it exits 0 and says that the recipient needs the font. |
| S7 | All the commands of S1 to S6 | No command uses the network. No fontconfig cache file changes outside the work folder. |

## How the checks block and find network use

`run_checks.py` runs each command of the skill in three layers:

1. `unshare -rn` puts the command in a new network namespace with no network. Then no
   process can reach the network.
2. `strace` logs each `connect()` and `sendto()` call of each process, LibreOffice
   included. A call with `AF_INET` or `AF_INET6` is a failure.
3. `audit_run.py` logs each Python network event (`socket.connect`,
   `socket.getaddrinfo` and others). An event is a failure, also when the script catches
   the error.

If `unshare` or `strace` is not available, the report of S7 says so.

## Run the checks

You need the requirements of the skill (see `INSTALL.md`) and Liberation Serif or DejaVu
Serif. `unshare` and `strace` are optional.

From the root of the repository, run this command. Use an empty folder outside the skill
folder:

```sh
python3 -I tools/evals/fonts/run_checks.py /abs/path/to/an/empty/folder --json /abs/path/to/results.json
```

The script prints PASS or FAIL for each scenario and each check. The exit code is 0 only
if all scenarios pass. The logs of each command are in the `logs` folder of the work
folder.

## The model rubric

`expected_behavior` in `scenarios.json` is for a run of the model with the skill. A script
cannot grade it. To use it, give the query and the files to the model, and compare what the
model does with each line.
