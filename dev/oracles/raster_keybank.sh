#!/bin/sh
# Raster oracle: render keybank (whose OOXML values are known) at 100 dpi, then measure the
# renders as if they were a scan. Compare the report against the extracted draft.
#   sh oracles/raster_keybank.sh [keybank.pptx] [out_dir]
# Defaults: $DECKGEN/fixtures/corpus/keybank.pptx (DECKGEN defaults to /home/user/deckgen),
# and a fresh temporary directory. Runs with plain python3 -I from the skill repo.
set -eu
SKILL=$(cd "$(dirname "$0")/../../plugins/designing-presentations/skills/designing-presentations" && pwd)
DECK=${1:-${DECKGEN:-/home/user/deckgen}/fixtures/corpus/keybank.pptx}
OUT=${2:-$(mktemp -d "${TMPDIR:-/tmp}/raster_keybank.XXXXXX")}
python3 -I "$SKILL/scripts/render.py" "$DECK" --out "$OUT/renders" --dpi 100
python3 -I "$SKILL/scripts/raster_style.py" "$OUT/renders" --out "$OUT/raster" --page-emu 9144000x6858000
echo "renders and raster report in $OUT"
