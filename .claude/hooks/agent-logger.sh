#!/bin/bash
#
# CCAGI Agent Logger Hook
#
# エージェント実行後に詳細なログを ./logs に記録
#
# Trigger: PostToolCall (Task tool)
# Output: Structured log file in ./logs/agents/
#
# Log Format: YAML-based structured template
#

set -euo pipefail

# ==============================
# Configuration
# ==============================

# Dynamic path resolution (with CLAUDE_PROJECT_DIR fallback for compatibility)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
LOG_DIR="${PROJECT_ROOT}/logs/agents"
TEMPLATE_DIR="${PROJECT_ROOT}/logs/templates"

mkdir -p "$LOG_DIR"
mkdir -p "$TEMPLATE_DIR"

# ==============================
# Input Parameters
# ==============================

# CLI引数から取得（hooks.jsonの呼び出し形式に合わせる）
# hooks.json: .claude/hooks/agent-logger.sh "$TOOL_OUTPUT" "$TOOL_INPUT"
TOOL_OUTPUT="${1:-}"
TOOL_INPUT="${2:-}"

# TOOL_INPUTがJSON形式の場合はパース
AGENT_TYPE=""
AGENT_DESC=""
AGENT_PROMPT=""

if [ -n "$TOOL_INPUT" ]; then
    if command -v jq &> /dev/null; then
        AGENT_TYPE=$(echo "$TOOL_INPUT" | jq -r '.subagent_type // empty' 2>/dev/null || echo "")
        AGENT_DESC=$(echo "$TOOL_INPUT" | jq -r '.description // empty' 2>/dev/null || echo "")
        AGENT_PROMPT=$(echo "$TOOL_INPUT" | jq -r '.prompt // empty' 2>/dev/null | head -c 500 || echo "")
    else
        # jqがない場合はgrep fallback
        AGENT_TYPE=$(echo "$TOOL_INPUT" | grep -oE '"subagent_type":\s*"[^"]*"' | cut -d'"' -f4 || echo "")
        AGENT_DESC=$(echo "$TOOL_INPUT" | grep -oE '"description":\s*"[^"]*"' | cut -d'"' -f4 || echo "")
    fi
fi

# Skip if no meaningful input
if [ -z "$AGENT_TYPE" ] && [ -z "$AGENT_DESC" ] && [ -z "$TOOL_OUTPUT" ]; then
    exit 0
fi

# ==============================
# Log Generation
# ==============================

generate_log_id() {
    echo "$(date '+%Y%m%d_%H%M%S')_$(openssl rand -hex 4 2>/dev/null || echo $$)"
}

generate_agent_log() {
    local log_id="$1"
    local agent_type="$2"
    local description="$3"
    local prompt="$4"
    local output="$5"
    local status="$6"
    local start_time="$7"
    local end_time="$8"

    # Calculate duration
    local duration_sec=$((end_time - start_time))

    # Determine status icon
    local status_icon="✅"
    if [ "$status" != "success" ]; then
        status_icon="❌"
    fi

    # Truncate output if too long
    local output_truncated="$output"
    if [ ${#output} -gt 2000 ]; then
        output_truncated="${output:0:2000}...[truncated]"
    fi

    # Generate log content using template
    cat << EOF
# ═══════════════════════════════════════════════════════════════
# CCAGI Agent Execution Log
# ═══════════════════════════════════════════════════════════════

log_metadata:
  log_id: "${log_id}"
  version: "1.0.0"
  generated_at: "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ───────────────────────────────────────────────────────────────
# Agent Information
# ───────────────────────────────────────────────────────────────

agent:
  type: "${agent_type}"
  description: "${description}"
  status: "${status}"
  status_icon: "${status_icon}"

# ───────────────────────────────────────────────────────────────
# Execution Timeline
# ───────────────────────────────────────────────────────────────

execution:
  start_time: "$(date -r "$start_time" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')"
  end_time: "$(date -r "$end_time" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')"
  duration_seconds: ${duration_sec}
  duration_human: "$((duration_sec / 60))m $((duration_sec % 60))s"

# ───────────────────────────────────────────────────────────────
# Input (Prompt)
# ───────────────────────────────────────────────────────────────

input:
  prompt: |
$(echo "$prompt" | sed 's/^/    /')

# ───────────────────────────────────────────────────────────────
# Output (Result)
# ───────────────────────────────────────────────────────────────

output:
  result: |
$(echo "$output_truncated" | sed 's/^/    /')

# ───────────────────────────────────────────────────────────────
# Environment Context
# ───────────────────────────────────────────────────────────────

environment:
  git_branch: "$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo 'unknown')"
  git_commit: "$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
  working_directory: "${PROJECT_ROOT}"
  user: "${USER:-unknown}"
  hostname: "$(hostname -s 2>/dev/null || echo 'unknown')"

# ═══════════════════════════════════════════════════════════════
EOF
}

# ==============================
# Main
# ==============================

main() {
    # Record start time (approximate - using current time)
    local start_time=$(date +%s)
    local end_time=$(date +%s)

    # Skip if not a Task tool call (AGENT_TYPE/AGENT_DESC are already set from CLI args parsing)
    if [ -z "$AGENT_TYPE" ] && [ -z "$AGENT_DESC" ]; then
        exit 0
    fi

    # Determine status from output
    local status="success"
    if echo "$TOOL_OUTPUT" | grep -qiE "(error|failed|exception|traceback)"; then
        status="failed"
    fi

    # Generate log ID and filename
    local log_id=$(generate_log_id)
    local log_filename="${LOG_DIR}/${log_id}_${AGENT_TYPE:-agent}.log"

    # Generate and save log
    generate_agent_log \
        "$log_id" \
        "${AGENT_TYPE:-unknown}" \
        "${AGENT_DESC:-No description}" \
        "${AGENT_PROMPT:-No prompt provided}" \
        "$TOOL_OUTPUT" \
        "$status" \
        "$start_time" \
        "$end_time" > "$log_filename"

    # Also append to daily summary log
    local daily_log="${LOG_DIR}/daily_$(date '+%Y%m%d').log"
    local status_upper=$(echo "$status" | tr '[:lower:]' '[:upper:]')
    echo "[$(date '+%H:%M:%S')] ${status_upper} | ${AGENT_TYPE:-agent} | ${AGENT_DESC:-}" >> "$daily_log"

    # Update latest.log symlink
    ln -sf "$log_filename" "${LOG_DIR}/latest.log" 2>/dev/null || true

    # Console output for debugging (optional)
    if [ "${CCAGI_DEBUG:-}" = "true" ]; then
        echo "[CCAGI Agent Logger] Log saved: $log_filename"
    fi
}

main "$@"

exit 0
