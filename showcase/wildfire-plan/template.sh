#!/bin/sh
# The template of the wildfire section: the reference's masters and layouts with every slide
# removed, its agency wordmark redrawn as the fictional Ridgeline mark, and its document
# properties and prompt texts replaced.
# usage: sh template.sh SKILL REF WORK   (run by showcase/rebuild.sh)
set -eu
skill=$1 ref=$2 work=$3
python3 "$skill/scripts/pptx_tools.py" template "$ref" -o "$work/tpl.ref.pptx" > /dev/null
# ppt/media/image1.jpeg is the background of the master and of the title layout, wordmark included.
python3 -I -c 'import sys, zipfile; open(sys.argv[2], "wb").write(zipfile.ZipFile(sys.argv[1]).read("ppt/media/image1.jpeg"))' \
  "$work/tpl.ref.pptx" "$work/img/background.ref.jpeg"
python3 -I "$work/make_bg.py" "$work/img/background.ref.jpeg" "$work/img/ridgeline_bg.v1.jpeg" "$work/img/bg_preview.v1.png" > /dev/null
python3 -I "$work/make_bg2.py" "$work/img/ridgeline_bg.v1.jpeg" "$work/img/ridgeline_bg.jpeg" "$work/img/bg_preview.png" > /dev/null
python3 -I "$work/clean_template.py" "$work/tpl.ref.pptx" "$work/tpl.pptx" > /dev/null
