#!/bin/bash
# Agent Worktree Pre-Hook - Create worktree before Sub-Agent execution (CCAGI版)
# Version: 3.0.0 (Claude Code Hook Integration)
# Usage: Called by PreToolUse(Task) hook via hooks.json
# Input: $TOOL_INPUT env var (JSON) from Claude Code hook system
#
# CCAGI Policy: 完全自律動作、外部依存なし
# Note: Does NOT use set -e to avoid breaking Claude Code hook chain on non-fatal errors

set -uo pipefail

# Source worktree manager functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/worktree-manager.sh" ]]; then
    echo "WARN: worktree-manager.sh not found. Skipping worktree creation." >&2
    exit 0
fi
source "$SCRIPT_DIR/worktree-manager.sh"

# Check jq availability
if ! command -v jq &>/dev/null; then
    log WARN "jq not installed. Skipping worktree creation."
    exit 0
fi

# Parse JSON input from env var or argument
parse_task_input() {
    local input="${1:-${TOOL_INPUT:-}}"

    if [[ -z "$input" ]]; then
        log WARN "No TOOL_INPUT provided. Skipping."
        SUBAGENT_TYPE="unknown"
        return 1
    fi

    # Extract fields using jq
    SUBAGENT_TYPE=$(echo "$input" | jq -r '.subagent_type // .type // "unknown"' 2>/dev/null || echo "unknown")
    TASK_DESC=$(echo "$input" | jq -r '.description // .prompt // "task"' 2>/dev/null || echo "task")
    ISSUE_NUMBER=$(echo "$input" | jq -r '.issue_number // .issue // ""' 2>/dev/null || echo "")
    PROMPT=$(echo "$input" | jq -r '.prompt // ""' 2>/dev/null || echo "")

    log INFO "Parsed Task input: subagent=$SUBAGENT_TYPE, issue=$ISSUE_NUMBER, desc=$TASK_DESC"
}

# Main execution
main() {
    log INFO "PreToolUse(Task) hook triggered - Creating worktree for CCAGI Sub-Agent"

    # Check if main session is already in a worktree (ERROR - Orchestrator should stay in main)
    if is_in_worktree; then
        log WARN "Main session is already in a worktree. Skipping worktree creation."
        exit 0
    fi

    # Parse input (from argument $1 or TOOL_INPUT env var)
    parse_task_input "$@" || exit 0

    # Validate subagent_type
    if [[ "$SUBAGENT_TYPE" == "unknown" ]] || [[ -z "$SUBAGENT_TYPE" ]]; then
        log WARN "No subagent_type specified in Task tool input. Skipping worktree creation."
        exit 0
    fi

    # Skip worktree for lightweight agent types that don't need isolation
    case "$SUBAGENT_TYPE" in
        Explore|Plan|claude-code-guide|statusline-setup|haiku)
            log INFO "Skipping worktree for lightweight agent: $SUBAGENT_TYPE"
            exit 0
            ;;
    esac

    # Call worktree-manager.sh to create worktree
    log INFO "Creating worktree for CCAGI Sub-Agent: $SUBAGENT_TYPE"

    if [[ -n "$ISSUE_NUMBER" ]]; then
        create_subagent_worktree "$SUBAGENT_TYPE" "$TASK_DESC" "$ISSUE_NUMBER" "$PROMPT" || {
            log WARN "Worktree creation failed (non-fatal). Continuing without worktree."
            exit 0
        }
    else
        create_subagent_worktree "$SUBAGENT_TYPE" "$TASK_DESC" "" "$PROMPT" || {
            log WARN "Worktree creation failed (non-fatal). Continuing without worktree."
            exit 0
        }
    fi

    local worktree_path=$(get_last_created_worktree_path)

    if [[ -n "$worktree_path" ]]; then
        log SUCCESS "Worktree created successfully: $worktree_path"

        # macOS notification (CCAGI: ローカル通知のみ)
        if [[ "$OSTYPE" == "darwin"* ]] && command -v osascript &>/dev/null; then
            osascript -e "display notification \"Creating worktree for $SUBAGENT_TYPE\" with title \"CCAGI Orchestrator\" sound name \"Glass\"" 2>/dev/null || true
        fi
    else
        log WARN "Worktree path not found after creation. Continuing without worktree."
    fi

    exit 0
}

# Run main
main "$@"
