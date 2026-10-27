# Installing designing-presentations

The skill is the folder `plugins/designing-presentations/skills/designing-presentations/`. It runs Python scripts and
LibreOffice on the machine where Claude works, so that machine needs the requirements
below. The skill installs nothing itself: `scripts/preflight.py` checks every requirement
and prints the install command for whatever is missing, for you to run.

## Requirements

What the skill needs, and the versions this release was built and measured on (Linux,
round 8; `python3 scripts/preflight.py` printed them):

| Requirement | Needed for | Measured on |
|---|---|---|
| Python 3.11 or later | every script | 3.13.16 |
| lxml | reading and writing OOXML | 6.1.3 |
| Pillow | images, crops, the fallback text ruler | 12.3.0 |
| python-pptx | writing the deck | 1.0.2 |
| pdfplumber | reading PDF references | 0.11.10 (pdfminer.six 20260107) |
| uharfbuzz (optional) | the better text ruler; without it the Pillow ruler measures and the build report says so | 0.57.0 |
| LibreOffice (`soffice`) | rendering .pptx to PDF; every render check reads it | 24.2.7.2 |
| poppler (`pdftoppm`, `pdftotext`, `pdffonts`) | rasterising pages, reading the words a render drew | 24.02.0 |
| fontconfig (`fc-match`, `fc-query`) | finding the installed face for each named face | 2.15.0 |

Every renderer measurement in the skill's references (where LibreOffice puts a label, how
it rounds a value, when it drops a category) was taken on LibreOffice 24.2.7; another
version may draw differently, and the build's render checks then say where.

Fonts: the build measures text with the faces the deck names. A face the machine lacks is
reported by preflight (`needs face ...`); install your own licensed copy, or its
metric-compatible stand-in, and run `fc-cache -f`. The stand-ins for the Microsoft core
faces are Liberation (Arial, Times New Roman, Courier New), Carlito (Calibri) and Caladea
(Cambria): `fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea` on Debian and
Ubuntu, `brew install --cask font-liberation font-carlito font-caladea` on macOS.

Install commands preflight prints (shown here for reference; it prints only what is missing):

```bash
python3 -m pip install lxml Pillow python-pptx pdfplumber uharfbuzz
sudo apt-get install -y libreoffice-impress poppler-utils fontconfig      # Debian, Ubuntu
brew install poppler fontconfig && brew install --cask libreoffice         # macOS
```

Check a machine, and a reference's faces:

```bash
python3 plugins/designing-presentations/skills/designing-presentations/scripts/preflight.py --reference /path/to/reference.pptx
```

## Claude Code

As a plugin, from this repository's marketplace:

```
/plugin marketplace add 0xfauzi/pptx-skill
/plugin install designing-presentations@pptx-skill
```

or from a shell, `claude plugin marketplace add 0xfauzi/pptx-skill` and
`claude plugin install designing-presentations@pptx-skill` (add `--scope project` to share it
through the project's settings). Claude Code copies the plugin into its plugin cache; the
skill loads as `/designing-presentations:designing-presentations` and is used on its own
when a request matches its description.

By hand: copy or symlink `plugins/designing-presentations/skills/designing-presentations/` to
`~/.claude/skills/designing-presentations/` (every project) or to a project's
`.claude/skills/designing-presentations/`.

## claude.ai

```bash
python3 dev/tools/package_skill.py     # writes dist/designing-presentations.zip
```

The packager refuses a skill an upload would reject (a frontmatter key outside the six the
Agent Skills specification defines, a name that is not the folder's, a description over
1,024 characters, a total over 30 MB) and leaves out the reference decks. Upload the zip in
claude.ai under Customize > Skills and turn the skill on; code execution must be enabled.
Whether the sandbox there has LibreOffice and the packages above depends on the
environment: ask Claude to run `scripts/preflight.py` first.

## Claude API

Upload the folder with the Skills API, every file named under `designing-presentations/`
(the files the packager puts in the zip):

```bash
python3 dev/tools/package_skill.py && cd skills
args=(); while IFS= read -r f; do args+=(-F "files[]=@$f;filename=$f"); done \
  < <(unzip -Z1 ../dist/designing-presentations.zip | grep -v '/$')
curl -X POST https://api.anthropic.com/v1/skills \
  -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" "${args[@]}"
```

Then pass the returned `skill_id` in a Messages request's `container.skills`
(`{"type": "custom", "skill_id": "...", "version": "latest"}`) with the code execution
tool. The API's container has no network access and installs no packages at run time, so
the skill runs there only as far as the pre-installed packages reach; preflight says how far.

## The judge's panel (optional)

The build compares a new deck against a panel of public decks of other firms (the judge's
rarity basis and the leakage check's background). They are third-party files and are never
shipped; fetch them once, into the skill's git-ignored `refs/files/`:

```bash
sh plugins/designing-presentations/skills/designing-presentations/refs/fetch.sh     # checks every sha256 in refs/MANIFEST.md
```

Without them the build still runs and says the panel is empty. In a plugin install the
skill folder sits in Claude Code's plugin cache and is replaced on update; fetch again after
an update.

## Where outputs go

No command writes inside the skill folder: every output path goes under a work directory
of your own (`DECK_WORK` in SKILL.md), and a path inside the skill is refused by name.
