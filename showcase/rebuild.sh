#!/bin/sh
# Rebuild one showcase deck from its sources with the skill in this repository.
# usage: sh showcase/rebuild.sh DECK WORK [REF]
#   DECK  lbo-committee-book | grocery-strategy | software-earnings | parks-annual-report |
#         board-transformation | transit-outlook | wildfire-plan
#   WORK  an absolute path to an empty work directory outside the skill
#   REF   for a deck with a reference.json (transit-outlook, wildfire-plan) only: an absolute
#         path to the public reference deck that reference.json names; its sha256 must match
# Writes WORK/out/deck.pptx, WORK/out/renders/slide-NN.png, WORK/out/deck.build.json and
# the two validation reports; exits non-zero on the first step that fails.
set -eu

deck=${1:?usage: rebuild.sh DECK WORK [REF]}
work=${2:?usage: rebuild.sh DECK WORK [REF]}
ref=${3:-}
case $work in /*) ;; *) echo "WORK must be an absolute path" >&2; exit 2 ;; esac

here=$(cd "$(dirname "$0")" && pwd)
src=$here/$deck
skill=$(cd "$here/../plugins/designing-presentations/skills/designing-presentations" && pwd)
[ -d "$src" ] || { echo "no showcase deck named $deck" >&2; exit 2; }

mkdir -p "$work/ref" "$work/deck" "$work/out"
cp "$src"/*.py "$src"/*.json "$work"/
for f in "$src"/*.sh; do [ -f "$f" ] && cp "$f" "$work"/; done
[ -d "$src/img" ] && cp -R "$src/img" "$work/img"
mkdir -p "$work/img"
# A completion names a logo file by its path in the work folder: @WORK@ stands for WORK.
sed "s#@WORK@#$work#g" "$work/completion.json" > "$work/ref/completion.json"
rm "$work/completion.json"

field() { python3 -I -c 'import json, sys; v = json.load(open(sys.argv[1]))[sys.argv[2]]; print("" if v is None else v)' "$src/reference.json" "$1"; }

# 1. The guide: the draft of the reference (or the blank draft), completed by the deck's completion.
cd "$skill"
if [ -f "$src/reference.json" ]; then
  case $ref in /*) ;; *) echo "$deck needs REF, an absolute path to $(field file) from $(field url)" >&2; exit 2 ;; esac
  got=$(python3 -I -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ref")
  [ "$got" = "$(field sha256)" ] || { echo "REF has sha256 $got, not the $(field sha256) of reference.json" >&2; exit 2; }
  pages=$(field digest_pages)
  python3 scripts/extract_style.py "$ref" -o "$work/ref/draft.json" --report "$work/ref/draft.md" > /dev/null
  python3 scripts/gallery.py digest "$ref" --out "$work/ref/digest" --guide "$work/ref/draft.json" ${pages:+--pages "$pages"} > /dev/null
  cp "$work/digest.json" "$work/ref/digest/digest.json"   # the digest answered after looking at each crop
  python3 scripts/complete_guide.py "$work/ref/draft.json" "$work/ref/completion.json" -o "$work/ref/guide.json" \
    --digest "$work/ref/digest" > "$work/ref/complete.log"
  chrome=$(field chrome)
else
  python3 scripts/extract_style.py --blank -o "$work/ref/draft.json" --report "$work/ref/draft.md" > /dev/null
  python3 scripts/complete_guide.py "$work/ref/draft.json" "$work/ref/completion.json" -o "$work/ref/guide.json" > "$work/ref/complete.log"
  chrome=draw
  ref=
fi

# 2. The template: the deck's own template script, or a blank package at the guide's page size.
if [ -f "$work/template.sh" ]; then
  sh "$work/template.sh" "$skill" "$ref" "$work"
else
  size=$(python3 -I -c 'import json, sys; p = json.load(open(sys.argv[1]))["reference"]["page"]; print(p["width_emu"], p["height_emu"])' "$work/ref/guide.json")
  python3 scripts/pptx_tools.py blank -o "$work/tpl.pptx" --width-emu "${size% *}" --height-emu "${size#* }" > /dev/null
fi

# 3. The figures: every stated figure computed and asserted by the deck's own script.
cd "$work"
if [ -f build_spec.py ]; then
  python3 build_spec.py > figures.txt          # also writes deck/deck.json
elif [ -f make_deck.py ]; then
  python3 figures.py > figures.txt             # also writes data.json
  python3 make_deck.py > /dev/null             # writes deck/deck.json (and plan.json, for a reference deck)
else
  python3 figures.py > figures.txt
  mv deck.json deck/deck.json                  # the deck spec is written by hand
fi

# 4. Plan check, build, validation.
cd "$skill"
python3 scripts/plan.py check "$work/plan.json" --guide "$work/ref/guide.json" -o "$work/plan.check.json" > /dev/null
if [ -n "$ref" ]; then
  python3 scripts/build_deck.py "$work/deck/deck.json" --guide "$work/ref/guide.json" --template "$work/tpl.pptx" \
    -o "$work/out/deck.pptx" --renders "$work/out/renders" --plan "$work/plan.json" \
    --reference "$ref" --chrome "$chrome" --computed "$work/figures.txt"
else
  python3 scripts/build_deck.py "$work/deck/deck.json" --guide "$work/ref/guide.json" --template "$work/tpl.pptx" \
    -o "$work/out/deck.pptx" --renders "$work/out/renders" --plan "$work/plan.json" \
    --chrome "$chrome" --computed "$work/figures.txt"
fi
python3 scripts/pptx_tools.py validate "$work/out/deck.pptx" --render > "$work/out/validate-render.json"
python3 scripts/pptx_tools.py validate "$work/out/deck.pptx" --emit --guide "$work/ref/guide.json" > "$work/out/validate-emit.json"
echo "validate: both clean; deck $work/out/deck.pptx"
