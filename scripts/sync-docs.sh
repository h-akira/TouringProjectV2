#!/usr/bin/env bash
# Copy the parent's current docs into each unit's docs-parent/ as a read-only copy.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <unit-dir>..." >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/docs/"

for unit in "$@"; do
  if [ ! -d "$unit" ]; then
    echo "not a directory: $unit" >&2
    exit 1
  fi
  dest="$unit/docs-parent/"
  mkdir -p "$dest"
  rsync -a --delete --exclude 'init/' --exclude 'specs/' --exclude 'plans/' "$SRC" "$dest"
  cat > "${dest}COPIED.md" <<'EOF'
# docs-parent

親リポジトリ（TouringProjectV2）の `docs/` の写し。ここは編集しない。
直すときは親の `docs/` を直し、親で `scripts/sync-docs.sh` を実行して写し直す。
EOF
  echo "synced: $unit"
done
