#!/usr/bin/env bash
# Tests for scripts/sync-docs.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/sync-docs.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $1" >&2; exit 1; }

unit="$WORK/Unit"
mkdir -p "$unit/docs-parent" "$unit/src"
echo "keep" > "$unit/README.md"
echo "keep" > "$unit/src/main.py"
echo "stale" > "$unit/docs-parent/stale.md"

"$SCRIPT" "$unit"

[ -f "$unit/docs-parent/01_requirements.md" ] || fail "01_requirements.md copied"
[ -f "$unit/docs-parent/mock/index.html" ] || fail "mock copied"
[ -f "$unit/docs-parent/COPIED.md" ] || fail "COPIED.md written"
[ ! -e "$unit/docs-parent/init" ] || fail "init excluded"
[ ! -e "$unit/docs-parent/specs" ] || fail "specs excluded"
[ ! -e "$unit/docs-parent/plans" ] || fail "plans excluded"
[ ! -e "$unit/docs-parent/stale.md" ] || fail "stale file removed"
[ "$(cat "$unit/README.md")" = "keep" ] || fail "README outside docs-parent kept"
[ "$(cat "$unit/src/main.py")" = "keep" ] || fail "src outside docs-parent kept"
cmp -s "$ROOT/docs/07_units_contracts.md" "$unit/docs-parent/07_units_contracts.md" || fail "content identical"

set +e
"$SCRIPT" "$WORK/missing" 2>/dev/null; code=$?
"$SCRIPT" 2>/dev/null; code_noargs=$?
set -e
[ "$code" -eq 1 ] || fail "missing dir exits 1 (got $code)"
[ "$code_noargs" -eq 2 ] || fail "no args exits 2 (got $code_noargs)"

echo "OK: sync-docs"
