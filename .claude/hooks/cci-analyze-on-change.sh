#!/bin/bash
# cci-analyze-on-change.sh — FileChanged hook
# Refreshes the code-intelligence index when a .rs/.ts/.tsx file changes.
# Mutual exclusion: skips if an analyze is already running.

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.file // empty' 2>/dev/null)
case "$FILE" in
  *.rs|*.ts|*.tsx) ;;
  *) exit 0 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
[ -d "$PROJECT_ROOT/.ccidb" ] || exit 0
[ -x "$HOME/.ccagi/bin/ccagi-sdk" ] || exit 0

LOCKFILE="$PROJECT_ROOT/.ccidb/.analyze.lock"
if [ -f "$LOCKFILE" ]; then
  OLD_PID=$(cat "$LOCKFILE" 2>/dev/null)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then exit 0; fi
  rm -f "$LOCKFILE"
fi

LOG_FILE="$HOME/.ccagi/cci-analyze.log"
mkdir -p "$(dirname "$LOG_FILE")"
META_JSON="$PROJECT_ROOT/.ccidb/meta.json"
EMB_FLAG=""
if [ -f "$META_JSON" ] && grep -q '"embeddings"\s*:\s*[1-9]' "$META_JSON" 2>/dev/null; then EMB_FLAG="--embeddings"; fi

(
  echo $$ > "$LOCKFILE"
  echo "[$(date +%Y-%m-%d_%H:%M:%S)] cci analyze triggered by $FILE (emb=$EMB_FLAG)" >> "$LOG_FILE"
  CLAUDE_PROJECT_DIR="$PROJECT_ROOT" timeout 300 "$HOME/.ccagi/bin/ccagi-sdk" cci analyze $EMB_FLAG >> "$LOG_FILE" 2>&1
  echo "[$(date +%Y-%m-%d_%H:%M:%S)] cci analyze exit=$?" >> "$LOG_FILE"
  find "$PROJECT_ROOT/.ccidb" -maxdepth 1 -name ".semantic.ccm.*" -mmin +5 -delete 2>/dev/null || true
  rm -f "$LOCKFILE"
) &
exit 0
