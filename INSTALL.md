# Installing designing-presentations

The skill is the folder `plugins/designing-presentations/skills/designing-presentations/`
(`SKILL_DIR` below). It runs Python scripts and LibreOffice on the machine where Claude
works, so that machine needs the requirements below. The skill installs nothing itself:
`scripts/preflight.py` checks every requirement and prints the install command for whatever
is missing, for you to run.

## Requirements

What the skill needs, and the versions this release was built and measured on (Linux,
round 8; `python3 scripts/preflight.py` printed the Python packages and LibreOffice, and
`pdftoppm -v`, `fc-match --version` and pdfminer's `__version__` the rest:
[dev/proofs/environment.txt](dev/proofs/environment.txt)):

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
python3 plugins/designing-presentations/skills/designing-presentations/scripts/preflight.py \
  --reference /path/to/reference.pptx
```

## Claude Code

As a plugin, from this repository's marketplace, added by the URL of its catalog file:

```
/plugin marketplace add https://raw.githubusercontent.com/0xfauzi/pptx-skill/main/.claude-plugin/marketplace.json
/plugin install designing-presentations@pptx-skill
```

or from a shell, `claude plugin marketplace add <that URL>` and
`claude plugin install designing-presentations@pptx-skill` (add `--scope project` to share it
through the project's settings). One command does both: in a session
`/plugin install designing-presentations --marketplace <that URL>` (Claude Code 2.1.275 or
later), and from a shell `claude plugin install designing-presentations --marketplace <that
URL>` (2.1.292 or later), per code.claude.com/docs/en/discover-plugins.md ("Add a
marketplace and install in one command"). The skill loads as
`/designing-presentations:designing-presentations` and is used on its own when a request
matches its description.

What lands on disk. Added by URL, the marketplace is the one catalog file, and its one entry
is a `git-subdir` source (`plugins/designing-presentations` of this repository), which
Claude Code fetches with a sparse checkout of that folder alone (code.claude.com/docs/en/
plugins/marketplace-reference.md, "git-subdir plugin source"; host-marketplace.md, "Host
your marketplace": a hosted marketplace.json URL). Measured on Claude Code 2.1.311, from a
git server on 127.0.0.1 into a scratch config: the marketplaces folder held one file, the
plugin cache the plugin folder's committed files byte for byte, and nothing of `dev/` and no
`.git` anywhere. The marketplace can also be added as `0xfauzi/pptx-skill` (the shorter form
above works in place of the URL): that clones the whole repository into
`~/.claude/plugins/marketplaces/pptx-skill/`, `dev/` included (66 files there on the same
test), while the install still fetches the plugin folder alone; `--sparse .claude-plugin` on
that add keeps the checkout to the catalog and the files at the repository's root (5 files,
nothing of `dev/`). A marketplace added from a local folder of this repository installs from
GitHub too, since the entry names the repository by URL; to try a local change, load the
plugin folder with `claude --plugin-dir plugins/designing-presentations`.

Claude Code keeps the plugin in its cache,
`~/.claude/plugins/cache/pptx-skill/designing-presentations/<version>/` (the plugins root is
`~/.claude/plugins` unless `CLAUDE_CODE_PLUGIN_CACHE_DIR` names another, per
code.claude.com/docs/en/plugins/loading.md, "Find plugins on disk"; with `CLAUDE_CONFIG_DIR`
set it was `$CLAUDE_CONFIG_DIR/plugins` on Claude Code 2.1.311), so the skill sits at
`~/.claude/plugins/cache/pptx-skill/designing-presentations/0.9.0/skills/designing-presentations/`
for this release. `claude plugin list` shows what is installed. An update installs the new
version into a new directory and removes the old one 14 days later (loading.md, "Cleanup of
previous versions").

By hand: copy or symlink `plugins/designing-presentations/skills/designing-presentations/` to
`~/.claude/skills/designing-presentations/` (every project) or to a project's
`.claude/skills/designing-presentations/`.

## claude.ai

```bash
python3 dev/tools/package_skill.py     # writes dist/designing-presentations.zip
```

The packager zips the files git tracks in the skill, as committed, and refuses by name an
untracked or ignored file there, a tracked file changed since the last commit, and a skill
an upload would reject: a frontmatter key outside the six the Agent Skills specification
defines; a name that is not the folder's, holds "anthropic" or "claude" or an XML tag; a
description that is empty, over 200 characters (support.claude.com article 12512198) or
holds an XML tag; a frontmatter line that is not a one-line plain `key: value`; a
compatibility over 500 characters; a symbolic link; a `LICENSE.txt` that differs from the
repository's `LICENSE`; a total over 30 MB (platform.claude.com skills guide, "Limits and
constraints"). The reference decks (`refs/files`, git-ignored) are left out. Upload the zip
in claude.ai under Customize > Skills and turn the skill on; code execution must be enabled.
Whether the sandbox there has LibreOffice and the packages above depends on the
environment: ask Claude to run `scripts/preflight.py` first.

## Claude API

Upload the folder with the Skills API, every file named under `designing-presentations/`:
the files the packager put in the zip, unpacked, so nothing outside git reaches the upload
(a bash snippet):

```bash
python3 dev/tools/package_skill.py
rm -rf dist/upload && mkdir -p dist/upload && cd dist/upload && unzip -q ../designing-presentations.zip
args=(); while IFS= read -r f; do args+=(-F "files[]=@$f;filename=$f"); done \
  < <(find designing-presentations -type f | sort)
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
shipped; fetch them once, into the skill's git-ignored `refs/files/`. `fetch.sh` is POSIX
sh (run under dash, bash and bash --posix), needs curl and `sha256sum` or `shasum`, and
checks every file against the sha256 in `refs/MANIFEST.md`:

```sh
sh plugins/designing-presentations/skills/designing-presentations/refs/fetch.sh
```

Without them the build still runs and says the panel is empty. In a plugin install the
skill is the cache copy above, so the panel goes there, and an update starts a new version
directory without it. Fetch it again after every update, in the new version's folder:

```sh
sh ~/.claude/plugins/cache/pptx-skill/designing-presentations/<version>/skills/designing-presentations/refs/fetch.sh
```

(`claude plugin list` names the installed version; the panel in the old directory goes when
Claude Code removes that directory, 14 days after the update.)

## Where outputs go

No command writes inside the skill folder: every output path goes under a work directory
of your own (`DECK_WORK` in SKILL.md), and a path inside the skill is refused by name. Your
own components, and the admission records `component.py admit` writes, go in a components
directory of yours, passed as `--components DIR` (`references/components.md`).
