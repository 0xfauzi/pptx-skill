#!/bin/sh
# Fetch the public reference decks listed in MANIFEST.md into refs/files/ (git-ignored).
# Every URL and sha256 comes from the manifest; a file whose hash differs is reported and
# renamed aside (*.mismatch), never silently kept. POSIX sh: run it with sh, dash or bash.
set -u
cd "$(dirname "$0")" || exit 1
if command -v sha256sum > /dev/null 2>&1; then hash256() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum > /dev/null 2>&1; then hash256() { shasum -a 256 "$1" | cut -d' ' -f1; }
else echo "neither sha256sum nor shasum is installed; nothing can be checked"; exit 1
fi
rows=$(grep -E '^\| [A-Za-z0-9_]+\.(pdf|pptx) ' MANIFEST.md) || { echo "no rows in MANIFEST.md"; exit 1; }
mkdir -p files
bad=0
checked=0
# a here-document, not a pipe: the loop runs in this shell, so bad survives it
while IFS='|' read -r _ name url _pub _doc _fmt _pages sha _rest; do
  name=$(echo "$name" | xargs); url=$(echo "$url" | xargs | sed 's/ (manifest URL.*//'); sha=$(echo "$sha" | xargs)
  case "$name" in *.pdf|*.pptx) ;; *) echo "UNREAD ROW: no file name read from it"; bad=1; continue ;; esac
  checked=$((checked + 1))
  if [ ! -s "files/$name" ]; then
    echo "fetch $name"
    curl -sSL --max-time 300 -A "pptx-skill refs/fetch.sh" -o "files/$name" "$url" || { echo "FAILED $name"; bad=1; continue; }
  fi
  got=$(hash256 "files/$name")
  if [ "$got" = "$sha" ]; then echo "ok    $name"; else echo "HASH MISMATCH $name: $got, manifest $sha"; mv "files/$name" "files/$name.mismatch"; bad=1; fi
done <<EOF
$rows
EOF
echo "$checked of $(printf '%s\n' "$rows" | wc -l | xargs) manifest rows checked"
exit $bad
