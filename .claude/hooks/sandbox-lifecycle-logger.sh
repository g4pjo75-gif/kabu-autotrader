#!/bin/bash
# Sandbox Lifecycle Logger - PostToolUse hook for Docker Desktop Sandbox operations
# Records sandbox create/exec/stop/rm/save/ls events to .test-logs/sandbox-lifecycle.jsonl

COMMAND="${TOOL_INPUT:-}"
LOGFILE=".test-logs/sandbox-lifecycle.jsonl"

# Only process docker sandbox commands
if ! echo "$COMMAND" | grep -q "docker sandbox"; then
  exit 0
fi

mkdir -p .test-logs

ACTION=$(echo "$COMMAND" | grep -oE "(create|exec|stop|rm|save|ls)" | head -1)
SANDBOX_NAME=$(echo "$COMMAND" | grep -oE "e2e-shard-[0-9]+" | head -1)

if [ -n "$ACTION" ]; then
  echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"action\":\"$ACTION\",\"sandbox\":\"${SANDBOX_NAME:-unknown}\",\"command\":\"$COMMAND\"}" >> "$LOGFILE"
fi

exit 0
