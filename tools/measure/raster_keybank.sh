#!/bin/sh
# Measure the raster instrument on a deck whose OOXML values are known.
# The script renders the keybank deck at 100 dpi. Then it measures the renders as a scan.
# Compare the raster report with the draft that extract_style.py writes from the same deck.
#   sh tools/measure/raster_keybank.sh [keybank.pptx] [out_dir]
# The default deck is the copy that plugins/designing-presentations/fetch-refs.sh downloads.
# The default output is a new temporary directory.
set -eu
SKILL=$(cd "$(dirname "$0")/../../plugins/designing-presentations/skills/designing-presentations" && pwd)
DECK=${1:-$SKILL/refs/files/mi_keybank_first_niagara_fig_ma.pptx}
[ -f "$DECK" ] || { echo "no deck at $DECK: run plugins/designing-presentations/fetch-refs.sh, or give the deck" >&2; exit 2; }
OUT=${2:-$(mktemp -d "${TMPDIR:-/tmp}/raster_keybank.XXXXXX")}
python3 -I "$SKILL/scripts/render.py" "$DECK" --out "$OUT/renders" --dpi 100
python3 -I "$SKILL/scripts/raster_style.py" "$OUT/renders" --out "$OUT/raster" --page-emu 9144000x6858000
echo "renders and raster report in $OUT"
