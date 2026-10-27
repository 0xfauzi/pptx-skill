#!/bin/sh
# Build the keybank example section, then build five wrong decks and judge each one.
#   sh tools/measure/judge_keybank.sh OUT_DIR
# OUT_DIR must be an absolute path to an empty folder outside the skill.
# Run refs/fetch.sh in the skill first: the script uses the keybank deck that it downloads.
# The script prints the judge result of the section and of each wrong deck.
set -eu
out=${1:?usage: judge_keybank.sh OUT_DIR}
case $out in /*) ;; *) echo "OUT_DIR must be an absolute path" >&2; exit 2 ;; esac
root=$(cd "$(dirname "$0")/../.." && pwd)
skill=$root/plugins/designing-presentations/skills/designing-presentations
ref=$skill/refs/files/mi_keybank_first_niagara_fig_ma.pptx
[ -f "$ref" ] || { echo "no deck at $ref: run refs/fetch.sh in the skill" >&2; exit 2; }
mkdir -p "$out/ref" "$out/out"

cd "$skill"
python3 scripts/extract_style.py "$ref" -o "$out/ref/draft.json" --report "$out/ref/draft.md" > /dev/null 2>&1
python3 scripts/gallery.py digest "$ref" --out "$out/ref/digest" --guide "$out/ref/draft.json" > /dev/null
cp examples/digests/keybank.digest.json "$out/ref/digest/digest.json"
python3 scripts/complete_guide.py "$out/ref/draft.json" examples/keybank.completion.json \
  -o "$out/ref/guide.json" --digest "$out/ref/digest" > "$out/complete.log"
python3 scripts/pptx_tools.py template "$ref" -o "$out/tpl.pptx" > /dev/null
python3 scripts/build_deck.py examples/keybank-section.deck.json --guide "$out/ref/guide.json" --template "$out/tpl.pptx" \
  -o "$out/out/deck.pptx" --reference "$ref" --renders "$out/out/renders" --plan examples/keybank-section.plan.json > "$out/build.log"

python3 -I "$root/tools/measure/build_gaming.py" "$out/gaming" "$ref" "$out/out/deck.pptx" "$out/tpl.pptx" > /dev/null
for deck in "$out/out/deck.pptx" "$out"/gaming/g*.pptx; do
  python3 -I scripts/fingerprint.py compare "$deck" --reference "$ref" > "$deck.judge.json"
  python3 -I -c '
import json, sys
d = json.load(open(sys.argv[1]))
c = d["components"]
spread = d.get("reference_spread") or {}
print(sys.argv[2], "layout_clean", d.get("layout_clean"), "total", d["total"], "overlap", c.get("overlap"), "overflow", c.get("overflow"),
      "reference spread", spread.get("min"), "to", spread.get("max"))
' "$deck.judge.json" "$(basename "$deck")"
done
