# Install designing-presentations

The skill is the folder `plugins/designing-presentations/skills/designing-presentations/`.
This document calls it the skill folder.

The skill runs Python scripts and LibreOffice on the machine where Claude works. So that
machine must have the requirements below. The skill installs nothing. The script `scripts/preflight.py` checks each requirement and
prints the install command for each missing item. You run the commands.

## Contents

- Requirements
- Fonts
- Claude Code
- claude.ai
- Claude API
- The judge's panel (optional)
- Where outputs go

## Requirements

The table shows the versions that we tested this release on (Ubuntu 24.04).

| Requirement | What it does | Tested version |
|---|---|---|
| Python 3.11 or later | Runs all scripts. | 3.13.16 |
| lxml | Reads and writes OOXML. | 6.1.3 |
| Pillow | Reads and writes images and crops. Gives the fallback text ruler. | 12.3.0 |
| python-pptx | Writes the deck. | 1.0.2 |
| pdfplumber | Reads PDF references. | 0.11.10 (pdfminer.six 20260107) |
| uharfbuzz (optional) | Gives the better text ruler. Without it, the Pillow ruler measures, and the build report tells you. | 0.57.0 |
| LibreOffice (`soffice`) | Renders .pptx to PDF. All render checks read this render. | 24.2.7.2 |
| poppler (`pdftoppm`, `pdftotext`, `pdffonts`) | Rasterises pages. Reads the words that a render drew. | 24.02.0 |
| fontconfig (`fc-match`, `fc-query`) | Finds the installed font for each font name. | 2.15.0 |

The references of the skill give renderer measurements from LibreOffice 24.2.7.
Another version can draw differently. If it does, the render checks of the build show
where.

To get the versions on your machine, run these commands:

```bash
python3 plugins/designing-presentations/skills/designing-presentations/scripts/preflight.py
pdftoppm -v
fc-match --version
```

Preflight prints only the commands for the items that are missing. These are the
commands for all items:

```bash
python3 -m pip install lxml Pillow python-pptx pdfplumber uharfbuzz
sudo apt-get install -y libreoffice-impress poppler-utils fontconfig      # Debian, Ubuntu
brew install poppler fontconfig && brew install --cask libreoffice         # macOS
```

To check a machine and the fonts of a reference, run this command:

```bash
python3 plugins/designing-presentations/skills/designing-presentations/scripts/preflight.py \
  --reference /path/to/reference.pptx
```

## Fonts

The skill measures text with the fonts that the deck names. The skill never downloads or
installs a font. Do these steps for each font that the font report or preflight shows as
missing (`needs face ...`):

1. Get the font files from a source that gives you a licence for them.
2. Put the files (.ttf, .otf or .ttc) in the fonts folder of your work folder. The path
   of this folder is in `DECK_FONTS`, for example `$DECK_WORK/fonts`.
3. Run `scripts/fonts.py report` again.

The skill uses the files in the fonts folder only in its own processes. It keeps checked
copies in the `.run` folder of the fonts folder. It does not install the files, and it
does not change the fonts of your computer.

These fonts are metric-compatible stand-ins for the Microsoft core fonts:

- Liberation: Arial, Times New Roman, Courier New.
- Carlito: Calibri.
- Caladea: Cambria.

You can put their files in the fonts folder. You can also install them on your computer
with the font tool of your system. That is your own action. Do not ask Claude to install a
font: the skill never downloads or installs a font.

## Claude Code

### Install the plugin

Type these two commands in Claude Code:

```
/plugin marketplace add https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
/plugin install designing-presentations@pptx-skill
```

From a shell, use these commands:

```bash
claude plugin marketplace add https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
claude plugin install designing-presentations@pptx-skill
```

To share the plugin through the settings of a project, add `--scope project` to the
install command.

One command can also add the marketplace and install the plugin. In Claude Code 2.1.275
or later, type this command:

```
/plugin install designing-presentations --marketplace https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
```

From a shell (Claude Code 2.1.292 or later), run
`claude plugin install designing-presentations --marketplace <URL>`. The source of these
version numbers is the Claude Code documentation, "Add a marketplace and install in one
command" (code.claude.com/docs/en/discover-plugins).

The skill loads as `/designing-presentations:designing-presentations`. Claude also uses
it automatically when a request matches its description.

### What the install writes to disk

The marketplace entry for the plugin is a `git-subdir` source. Claude Code fetches only
the folder `plugins/designing-presentations` of this repository. Claude Code keeps the
plugin in its cache:

```
~/.claude/plugins/cache/pptx-skill/designing-presentations/<version>/
```

If you set `CLAUDE_CODE_PLUGIN_CACHE_DIR`, the cache is in that folder. If you set
`CLAUDE_CONFIG_DIR`, the cache is in `$CLAUDE_CONFIG_DIR/plugins`. For this
release, the skill is at this path:

```
~/.claude/plugins/cache/pptx-skill/designing-presentations/0.9.0/skills/designing-presentations/
```

`claude plugin list` shows the installed plugins. An update installs the new version
into a new folder. Claude Code removes the old folder 14 days later.

You can also add the marketplace as `0xfauzi/pptx-skill`. Then Claude Code clones the
full repository into `~/.claude/plugins/marketplaces/pptx-skill/`. The install still
fetches only the plugin folder.

### Test a local change

To load the plugin from your copy of this repository, run this command:

```bash
claude --plugin-dir plugins/designing-presentations
```

### Manual install

Copy or symlink `plugins/designing-presentations/skills/designing-presentations/` to one
of these folders:

- `~/.claude/skills/designing-presentations/`, for all projects.
- `.claude/skills/designing-presentations/` in a project, for that project only.

## claude.ai

1. From the root of this repository, run this command:

   ```bash
   python3 tools/package_skill.py     # writes dist/designing-presentations.zip
   ```

   If the packager refuses a `__pycache__` folder in the skill, delete that folder and
   run the command again. Python makes these folders when you run the scripts.
2. In claude.ai, go to Customize > Skills and upload the zip.
3. Turn on the skill. Code execution must be on.
4. Ask Claude to run `scripts/preflight.py`. The sandbox of claude.ai can be different
   from your machine, and the script shows what is missing.

The packager puts in the zip the files that git tracks in the skill folder, as committed.
The packager refuses these items, and it gives the name of each item:

- A file in the skill folder that git does not track or that git ignores.
- A tracked file that changed after the last commit.
- A frontmatter key that is not one of the six keys of the Agent Skills specification.
- A frontmatter line that is not one plain `key: value` line.
- A name that is not the folder name, or that holds "anthropic", "claude" or an XML tag.
- A description that is empty, longer than 200 characters, or holds an XML tag. The
  limit of 200 characters comes from support.claude.com article 12512198.
- A compatibility value longer than 500 characters.
- A symbolic link.
- A `LICENSE.txt` that is different from the `LICENSE` of the repository.
- A total size of more than 30 MB. This limit comes from the platform.claude.com skills
  guide, "Limits and constraints".

The packager does not include the reference decks (`refs/files`, which git ignores). It
also does not include `fetch-refs.sh`, which is outside the skill folder.

## Claude API

Upload the skill folder with the Skills API. Each file must have a name under
`designing-presentations/`. Use the files from the zip of the packager, so that only
committed files go into the upload. This is a bash example:

```bash
python3 tools/package_skill.py
rm -rf dist/upload && mkdir -p dist/upload && cd dist/upload && unzip -q ../designing-presentations.zip
args=(); while IFS= read -r f; do args+=(-F "files[]=@$f;filename=$f"); done \
  < <(find designing-presentations -type f | sort)
curl -X POST https://api.anthropic.com/v1/skills \
  -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" "${args[@]}"
```

Then put the `skill_id` from the response in the `container.skills` of a Messages
request: `{"type": "custom", "skill_id": "...", "version": "latest"}`. Also add the code
execution tool to the request. The container of the API has no network access and cannot
install packages. So the skill can do only what the installed packages let it do.
Preflight shows which packages are missing.

## The judge's panel (optional)

The build compares a new deck with a panel of public decks from other firms. The judge
uses the panel to find what is rare, and the leakage check uses it as background. These
decks belong to other publishers, so the skill does not include them. The skill never
downloads them. You download them yourself. To download them into the folder
`refs/files/` of the skill, run this command:

```sh
sh plugins/designing-presentations/fetch-refs.sh
```

`fetch-refs.sh` is a POSIX sh script in the plugin folder, outside the skill folder. It
needs curl and `sha256sum` or `shasum`. It checks each file against the sha256 in
`refs/MANIFEST.md`. Git ignores `refs/files/`. Without the panel, the build still runs and
reports that the panel is empty. The PDF decks hold subsets of fonts. The skill never
uses these subsets to set text.

After a plugin install, the skill is in the cache folder. An update makes a new version
folder that does not have the panel. So, after each update, run `fetch-refs.sh` again in
the folder of the new version:

```sh
sh ~/.claude/plugins/cache/pptx-skill/designing-presentations/<version>/fetch-refs.sh
```

`claude plugin list` shows the installed version.

## Where outputs go

No command writes in the skill folder. Each output path must be in a work folder of your
own (`DECK_WORK` in SKILL.md). The scripts refuse an output path in the skill folder.
