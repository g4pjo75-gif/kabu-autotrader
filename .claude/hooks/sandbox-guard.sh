#!/bin/bash
# Sandbox Guard - PreToolUse hook for Docker Desktop Sandbox operations
# Validates sandbox create/rm commands with safety limits
#
# - Enforces maximum sandbox count (5)
# - Warns on force deletion
# - Prevents accidental sandbox cleanup without proper policy

MAX_SANDBOXES=5
COMMAND="${TOOL_INPUT:-}"

# Only process docker sandbox commands
if ! echo "$COMMAND" | grep -q "docker sandbox"; then
  exit 0
fi

# sandbox create: check count limit
if echo "$COMMAND" | grep -q "docker sandbox create"; then
  CURRENT=$(docker sandbox ls 2>/dev/null | grep -c "e2e-shard" || echo 0)
  if [ "$CURRENT" -ge "$MAX_SANDBOXES" ]; then
    echo "BLOCK: Sandbox limit ($MAX_SANDBOXES) reached. Current: $CURRENT. Remove unused sandboxes first."
    exit 1
  fi
fi

# sandbox rm --force: warn
if echo "$COMMAND" | grep -q "docker sandbox rm.*--force"; then
  echo "WARNING: Force sandbox deletion requested"
fi

exit 0
