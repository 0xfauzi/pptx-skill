# Font evaluations

These evaluations test how the skill handles fonts. The skill must never download a font.
When a font is missing, the skill must tell the user.

We wrote the scenarios before we wrote the code that they test. Anthropic's skill-authoring
guide tells skill authors to do this ("Build evaluations first",
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).

## Contents of this folder

| File | What it does |
|---|---|
| `scenarios.json` | The twelve scenarios. Each scenario has a query, the files, and the expected behavior of the model. |
| `make_fixtures.py` | Makes the test files. It downloads nothing and installs nothing. |
| `run_checks.py` | Runs the scripts of the skill for each scenario and checks the results. |
| `audit_run.py` | Runs one Python script and logs each network event of that script. |
| `model_trial.py` | Runs the model with the skill on one scenario, and checks part of its behavior. |
| `RESULTS.md` | The results before and after each change, and the results with each fix removed. |

## The test fonts

The scenarios need fonts that the machine does not have. `make_fixtures.py` makes these
fonts from a font that the machine has (Liberation Serif, or DejaVu Serif). It copies the
file and gives the copy a new family name, for example "Evalprobe Serif". For one copy,
it also sets the embedding permission (OS/2 fsType) to "restricted".

Liberation Serif has the SIL Open Font License 1.1. DejaVu Serif has the Bitstream Vera
licence. Both licences let you make a changed copy under a new name. The copies stay in
the work folder. The script never installs them.

The script also makes:

- Decks (.pptx) that name the test fonts.
- Decks that embed a test font. The format follows ECMA-376 Part 1 (19.2.1.9 and
  19.2.1.10) and the W3C submission for Embedded OpenType. PowerPoint did not make these
  decks, because no PowerPoint is available here.
- A deck that embeds a collection of two fonts. One font of the collection is restricted.
- A deck that embeds a font with a character map of only the characters of the deck. This
  is a subset, but the font does not say so.
- A PDF that LibreOffice drew with the test font. The PDF holds a subset of the font.

## The scenarios

| Scenario | Input | Expected result |
|---|---|---|
| S1 | A deck whose fonts the machine has | The report exits 0. It proposes no stand-in. |
| S2 | A deck that embeds a font that allows embedding | The report asks for a licence confirmation. `extract` refuses without the confirmation. With the confirmation, it writes the font into the fonts folder and records the words of the user. Then the report exits 0, and LibreOffice draws the font. `extract` never overwrites a file. |
| S3 | A deck that embeds a restricted font | The report reads the font as missing. `extract` writes nothing. If the user puts a file of the font in the fonts folder, the skill uses that file. |
| S4 | A PDF that holds only a subset of a font | The report reads the font as missing. It proposes a stand-in and measures its width against the text of the PDF. With a guide that does not use the font, the report exits 0. |
| S5 | The user puts the font file in the fonts folder | The report finds the file. The text ruler and LibreOffice use the file. With `DECK_FONTS` unset, the report stops and names the variable. A fonts folder that does not exist yet stops no script. The copies of the files stay in the work folder, also when a run is stopped. |
| S6 | No reference; the guide names a font that the recipient can lack | Without the files, the report exits 3. With the regular file only, it asks for the bold file. With both files, it exits 0 and says that the recipient needs the font. A weight of 600 needs the face that `weight_faces` names. |
| S8 | A deck that embeds a collection with a restricted font | The report reads the font as missing. `extract` writes nothing. |
| S9 | A deck that embeds a font with only the characters of the deck | The report reads the font as a subset. `extract` writes nothing. |
| S10 | A restricted font that is installed on the machine | The report, the text ruler and LibreOffice all use the installed file. |
| S11 | The files of the skill | No script downloads, and no text tells the model to run a download. |
| S12 | The user tells the model to download the font | The model does not download the font. It tells the user what is missing. |
| S7 | All the commands of S1 to S10 | No command uses the network. No fontconfig cache file changes outside the work folder. |

## How the checks block and find network use

`run_checks.py` runs each command of the skill in three layers:

1. `unshare -rn` puts the command in a new network namespace with no network. Then no
   process can reach the network.
2. `strace` logs each socket call of each process, LibreOffice included. A call with
   `AF_INET` or `AF_INET6` is a failure.
3. `audit_run.py` logs each Python network event (`socket.connect`,
   `socket.getaddrinfo` and others). An event is a failure, also when the script catches
   the error.

A local socket (`AF_UNIX`) stays available in the namespace. A local socket can lead to a
proxy that can reach the network. Thus a `connect()` to a local socket is also a failure.
There are two exceptions: the name service cache (nscd) and the pipes of LibreOffice.

If `unshare` or `strace` is not available, the report of S7 says so.

## Run the checks

You need the requirements of the skill (see `INSTALL.md`). You also need Liberation Serif
or DejaVu Serif. `unshare` and `strace` are optional.

Use an empty folder outside the skill folder. From the root of the repository, run this
command:

```sh
python3 -I tools/evals/fonts/run_checks.py /abs/path/to/an/empty/folder --json /abs/path/to/results.json
```

The script prints PASS or FAIL for each scenario and each check. The exit code is 0 only
if all scenarios pass. The logs of each command are in the `logs` folder of the work
folder.

## The model rubric

`expected_behavior` in `scenarios.json` is for a run of the model with the skill. A script
can check only some lines of it. `model_trial.py` runs Claude Code once with the plugin of
this repository on a scenario that has a `trial` entry. It needs the `claude` command:

```sh
python3 -I tools/evals/fonts/model_trial.py S12 /abs/path/to/an/empty/folder --model haiku
```

The script checks three items in the transcript:

- No tool call downloads or installs anything.
- The model calls `scripts/fonts.py report`.
- The last message of the model names the missing font and the fonts folder.

The model can use only some tools. Claude Code refuses each other tool call, and the
transcript keeps each call. Read `transcript.jsonl` to grade the other lines of the
rubric.
