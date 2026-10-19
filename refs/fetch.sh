#!/usr/bin/env bash
# Fetch the public reference decks listed in MANIFEST.md into refs/files/ (git-ignored).
# Every URL and sha256 comes from the manifest; a hash mismatch is reported, never silently kept.
set -u
cd "$(dirname "$0")"
mkdir -p files
while IFS='|' read -r _ name url _rest; do
  name=$(echo "$name" | xargs); url=$(echo "$url" | xargs | sed 's/ (manifest URL.*//')
  case "$name" in *.pdf|*.pptx) ;; *) continue ;; esac
  [ -s "files/$name" ] && { echo "have $name"; continue; }
  echo "fetch $name"
  curl -sSL --max-time 300 -A "pptx-skill refs/fetch.sh" -o "files/$name" "$url" || echo "FAILED $name"
done < <(grep -E '^\| [a-z0-9_]+\.(pdf|pptx) ' MANIFEST.md)
echo "--- hashes ---"
sha256sum files/* 2>/dev/null
