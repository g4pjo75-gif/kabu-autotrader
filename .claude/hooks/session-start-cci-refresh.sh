#!/usr/bin/env bash
# session-start-cci-refresh.sh — SessionStart hook
#
# Keeps the code-intelligence index (.ccidb/cci.db) fresh. If the index is
# older than the staleness TTL at session start, refresh it in the background
# so cci_query / cci_context / cci_impact return current symbols.
#
# Contract: exit 0 always (advisory only, never blocks SessionStart);
# fresh index (< TTL) → zero-overhead exit; stale → background refresh + advisory.
#
# Bypass: CCAGI_CCI_REFRESH_SKIP=1
# Tunable: CCAGI_CCI_STALE_TTL_SEC (default 21600 = 6h)

set -uo pipefail
[ "${CCAGI_CCI_REFRESH_SKIP:-0}" = "1" ] && exit 0

CWD="${CLAUDE_PROJECT_DIR:-$PWD}"
CCI_DB="$CWD/.ccidb/cci.db"
META="$CWD/.ccidb/meta.json"
LOCKFILE="$CWD/.ccidb/.cci-refresh.lock"
LOG="$HOME/.ccagi/cci-analyze.log"
STALE_TTL_SEC="${CCAGI_CCI_STALE_TTL_SEC:-21600}"

[ -d "$CWD/.ccidb" ] || exit 0
[ -x "$HOME/.ccagi/bin/ccagi-sdk" ] || exit 0

if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCKFILE" 2>/dev/null || stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0) ))
    [ "$LOCK_AGE" -lt 120 ] && exit 0
    rm -f "$LOCKFILE"
fi

NOW=$(date +%s)
if [ -f "$META" ]; then
    INDEXED_AT=$(grep -oE '"indexedAt"[^"]*"[0-9]+' "$META" 2>/dev/null | grep -oE '[0-9]+' | tail -1)
    if [ -n "${INDEXED_AT:-}" ]; then DB_AGE=$((NOW - INDEXED_AT))
    else DB_AGE=$(( NOW - $(stat -f %m "$CCI_DB" 2>/dev/null || stat -c %Y "$CCI_DB" 2>/dev/null || echo 0) )); fi
elif [ -f "$CCI_DB" ]; then
    DB_AGE=$(( NOW - $(stat -f %m "$CCI_DB" 2>/dev/null || stat -c %Y "$CCI_DB" 2>/dev/null || echo 0) ))
else DB_AGE=99999; fi

[ "$DB_AGE" -lt "$STALE_TTL_SEC" ] && exit 0

mkdir -p "$(dirname "$LOG")" 2>/dev/null
touch "$LOCKFILE"
EMB=""
if [ -f "$META" ] && grep -q '"embeddings"[[:space:]]*:[[:space:]]*[1-9]' "$META" 2>/dev/null; then EMB="--embeddings"; fi
(
    echo "[$(date +%Y-%m-%d_%H:%M:%S)] cci analyze (SessionStart, age=${DB_AGE}s, emb=$EMB)" >> "$LOG"
    CLAUDE_PROJECT_DIR="$CWD" timeout 300 "$HOME/.ccagi/bin/ccagi-sdk" cci analyze $EMB >> "$LOG" 2>&1
    echo "[$(date +%Y-%m-%d_%H:%M:%S)] cci analyze exit=$?" >> "$LOG"
    rm -f "$LOCKFILE"
) &

echo "[cci] index stale (age=${DB_AGE}s > ${STALE_TTL_SEC}s) — refreshing in background; next cci query will see fresh symbols (bypass: CCAGI_CCI_REFRESH_SKIP=1)" >&2
exit 0
