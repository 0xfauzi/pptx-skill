#!/bin/sh
# Rebuild one showcase deck from its sources with the skill in this repository.
# usage: sh showcase/rebuild.sh DECK WORK
#   DECK  lbo-committee-book | grocery-strategy | software-earnings | parks-annual-report
#   WORK  an absolute path to an empty work directory outside the skill
# Writes WORK/out/deck.pptx, WORK/out/renders/slide-NN.png, WORK/out/deck.build.json and
# the two validation reports; exits non-zero on the first step that fails.
set -eu

deck=${1:?usage: rebuild.sh DECK WORK}
work=${2:?usage: rebuild.sh DECK WORK}
case $work in /*) ;; *) echo "WORK must be an absolute path" >&2; exit 2 ;; esac

here=$(cd "$(dirname "$0")" && pwd)
src=$here/$deck
skill=$(cd "$here/../plugins/designing-presentations/skills/designing-presentations" && pwd)
[ -d "$src" ] || { echo "no showcase deck named $deck" >&2; exit 2; }

mkdir -p "$work/ref" "$work/deck" "$work/out"
cp "$src"/*.py "$src"/*.json "$work"/
mv "$work/completion.json" "$work/ref/completion.json"

# 1. The figures: every stated figure computed and asserted by the deck's own script.
cd "$work"
if [ -f build_spec.py ]; then
  python3 build_spec.py > figures.txt          # also writes deck/deck.json
elif [ -f make_deck.py ]; then
  python3 figures.py > figures.txt             # also writes data.json
  python3 make_deck.py > /dev/null             # writes deck/deck.json
else
  python3 figures.py > figures.txt
  mv deck.json deck/deck.json                  # the deck spec is written by hand
fi

# 2. The guide: the blank draft with no reference, completed by the deck's completion.
cd "$skill"
python3 scripts/extract_style.py --blank -o "$work/ref/draft.json" --report "$work/ref/draft.md" > /dev/null
python3 scripts/complete_guide.py "$work/ref/draft.json" "$work/ref/completion.json" -o "$work/ref/guide.json" > "$work/ref/complete.log"

# 3. The template: a blank package at the page size the completion chose.
size=$(python3 -I -c 'import json, sys; p = json.load(open(sys.argv[1]))["reference"]["page"]; print(p["width_emu"], p["height_emu"])' "$work/ref/guide.json")
python3 scripts/pptx_tools.py blank -o "$work/tpl.pptx" --width-emu "${size% *}" --height-emu "${size#* }" > /dev/null

# 4. Plan check, build, validation.
python3 scripts/plan.py check "$work/plan.json" --guide "$work/ref/guide.json" -o "$work/plan.check.json" > /dev/null
python3 scripts/build_deck.py "$work/deck/deck.json" --guide "$work/ref/guide.json" --template "$work/tpl.pptx" \
  -o "$work/out/deck.pptx" --renders "$work/out/renders" --plan "$work/plan.json" \
  --chrome draw --computed "$work/figures.txt"
python3 scripts/pptx_tools.py validate "$work/out/deck.pptx" --render > "$work/out/validate-render.json"
python3 scripts/pptx_tools.py validate "$work/out/deck.pptx" --emit --guide "$work/ref/guide.json" > "$work/out/validate-emit.json"
echo "validate: both clean; deck $work/out/deck.pptx"
