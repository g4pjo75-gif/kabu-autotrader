#!/usr/bin/env bash
# user-prompt-cci-freshness.sh — UserPromptSubmit hook
#
# Mid-session code-index freshness check that does not depend on local file edits
# (catches long sessions where the index drifts past the SessionStart TTL without
# a file-change trigger). Throttled so it is near-zero-overhead on most prompts;
# stale → background `ccagi-sdk cci analyze` + 1-line advisory.
#
# Bypass: CCAGI_CCI_FRESHNESS_SKIP=1
# Tunables: CCAGI_CCI_PROMPT_THROTTLE_SEC (default 1800=30m), CCAGI_CCI_PROMPT_STALE_TTL_SEC (default 7200=2h)

set -uo pipefail
[ "${CCAGI_CCI_FRESHNESS_SKIP:-0}" = "1" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CCI_DB="$PROJECT_ROOT/.ccidb/cci.db"
[ -f "$CCI_DB" ] || exit 0
[ -x "$HOME/.ccagi/bin/ccagi-sdk" ] || exit 0

THROTTLE_SEC="${CCAGI_CCI_PROMPT_THROTTLE_SEC:-1800}"
STALE_TTL_SEC="${CCAGI_CCI_PROMPT_STALE_TTL_SEC:-7200}"
THROTTLE_FILE="$PROJECT_ROOT/.ccidb/.prompt-freshness-check"
LOCKFILE="$PROJECT_ROOT/.ccidb/.analyze.lock"

now=$(date +%s)
if [ -f "$THROTTLE_FILE" ]; then
  last=$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)
  case "$last" in (*[!0-9]*|'') last=0 ;; esac
  [ $((now - last)) -lt "$THROTTLE_SEC" ] && exit 0
fi
echo "$now" > "$THROTTLE_FILE" 2>/dev/null || true

mt=$(stat -f %m "$CCI_DB" 2>/dev/null || stat -c %Y "$CCI_DB" 2>/dev/null || echo "$now")
age=$((now - mt))
[ "$age" -lt "$STALE_TTL_SEC" ] && exit 0

if [ -f "$LOCKFILE" ]; then
  pid=$(cat "$LOCKFILE" 2>/dev/null || echo)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then exit 0; fi
  rm -f "$LOCKFILE" 2>/dev/null || true
fi

LOG="$HOME/.ccagi/cci-analyze.log"; mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
EMB=""; META="$PROJECT_ROOT/.ccidb/meta.json"
if [ -f "$META" ] && grep -q '"embeddings"[[:space:]]*:[[:space:]]*[1-9]' "$META" 2>/dev/null; then EMB="--embeddings"; fi

echo "[cci] index ${age}s stale (> ${STALE_TTL_SEC}s) — refreshing in background (mid-session)" >&2
(
  echo $$ > "$LOCKFILE" 2>/dev/null || true
  echo "[$(date +%Y-%m-%d_%H:%M:%S)] cci analyze (UserPromptSubmit, age=${age}s, emb=$EMB)" >> "$LOG"
  CLAUDE_PROJECT_DIR="$PROJECT_ROOT" timeout 300 "$HOME/.ccagi/bin/ccagi-sdk" cci analyze $EMB >> "$LOG" 2>&1
  echo "[$(date +%Y-%m-%d_%H:%M:%S)] cci analyze exit=$?" >> "$LOG"
  rm -f "$LOCKFILE" 2>/dev/null || true
) &
exit 0
