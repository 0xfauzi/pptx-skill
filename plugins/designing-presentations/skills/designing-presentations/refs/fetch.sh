#!/usr/bin/env bash
# Fetch the public reference decks listed in MANIFEST.md into refs/files/ (git-ignored).
# Every URL and sha256 comes from the manifest; a file whose hash differs is reported and
# renamed aside (*.mismatch), never silently kept.
set -u
cd "$(dirname "$0")"
mkdir -p files
bad=0
while IFS='|' read -r _ name url _pub _doc _fmt _pages sha _rest; do
  name=$(echo "$name" | xargs); url=$(echo "$url" | xargs | sed 's/ (manifest URL.*//'); sha=$(echo "$sha" | xargs)
  case "$name" in *.pdf|*.pptx) ;; *) continue ;; esac
  if [ ! -s "files/$name" ]; then
    echo "fetch $name"
    curl -sSL --max-time 300 -A "pptx-skill refs/fetch.sh" -o "files/$name" "$url" || { echo "FAILED $name"; bad=1; continue; }
  fi
  got=$(sha256sum "files/$name" | cut -d' ' -f1)
  if [ "$got" = "$sha" ]; then echo "ok    $name"; else echo "HASH MISMATCH $name: $got, manifest $sha"; mv "files/$name" "files/$name.mismatch"; bad=1; fi
done < <(grep -E '^\| [A-Za-z0-9_]+\.(pdf|pptx) ' MANIFEST.md)
exit $bad
