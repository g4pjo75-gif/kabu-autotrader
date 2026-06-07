#!/bin/bash
# Agent Worktree Post-Hook - Cleanup worktree after Sub-Agent execution (CCAGI版)
# Version: 3.0.0 (Claude Code Hook Integration)
# Usage: Called by PostToolUse(Task) hook via hooks.json
# Input: $TOOL_OUTPUT env var (JSON) from Claude Code hook system
#
# CCAGI Policy: 完全自律動作、外部依存なし
# Note: Does NOT use set -e to avoid breaking Claude Code hook chain on non-fatal errors

set -uo pipefail

# Source worktree manager functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/worktree-manager.sh" ]]; then
    echo "WARN: worktree-manager.sh not found. Skipping worktree cleanup." >&2
    exit 0
fi
source "$SCRIPT_DIR/worktree-manager.sh"

# Check jq availability
if ! command -v jq &>/dev/null; then
    log WARN "jq not installed. Skipping worktree cleanup."
    exit 0
fi

# Parse JSON input from env var or argument
parse_task_result() {
    local input="${1:-${TOOL_OUTPUT:-}}"

    if [[ -z "$input" ]]; then
        log WARN "No TOOL_OUTPUT provided. Skipping cleanup."
        SUBAGENT_TYPE="unknown"
        return 1
    fi

    # Extract fields using jq
    SUBAGENT_TYPE=$(echo "$input" | jq -r '.subagent_type // .type // "unknown"' 2>/dev/null || echo "unknown")
    SUCCESS=$(echo "$input" | jq -r '.success // true' 2>/dev/null || echo "true")
    RESULT=$(echo "$input" | jq -r '.result // ""' 2>/dev/null || echo "")

    log INFO "Parsed Task result: subagent=$SUBAGENT_TYPE, success=$SUCCESS"
}

# Check if Sub-Agent execution was successful
check_execution_success() {
    # Check git status for uncommitted changes (indicates work was done)
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        log INFO "Changes detected in worktree - Sub-Agent made modifications"
        return 0
    fi

    # Check if commits were made
    local main_branch="main"
    local commit_count=$(git rev-list --count HEAD ^"$main_branch" 2>/dev/null || echo "0")

    if [[ "$commit_count" -gt 0 ]]; then
        log INFO "Found $commit_count new commit(s) in worktree"
        return 0
    fi

    log WARN "No changes or commits detected in worktree"
    return 1
}

# Main execution
main() {
    log INFO "PostToolUse(Task) hook triggered - Cleaning up CCAGI Sub-Agent worktree"

    # Parse input (from argument $1 or TOOL_OUTPUT env var)
    parse_task_result "$@" || exit 0

    # Skip lightweight agents that don't use worktrees
    case "$SUBAGENT_TYPE" in
        Explore|Plan|claude-code-guide|statusline-setup|haiku|unknown)
            log INFO "Skipping cleanup for agent type: $SUBAGENT_TYPE"
            exit 0
            ;;
    esac

    # Find the most recent agent worktree
    local agent_worktree_path=$(find_recent_agent_worktree "$SUBAGENT_TYPE" 2>/dev/null || echo "")

    if [[ -z "$agent_worktree_path" ]]; then
        log INFO "No agent worktree found for: $SUBAGENT_TYPE (may not have been created)"
        exit 0
    fi

    log INFO "Found agent worktree: $agent_worktree_path"

    # Change to worktree directory to perform checks
    cd "$agent_worktree_path" || {
        log WARN "Failed to enter worktree directory: $agent_worktree_path"
        exit 0
    }

    # Check if Sub-Agent execution was successful
    if check_execution_success; then
        log SUCCESS "Sub-Agent execution completed successfully"

        # Log for manual cleanup - auto-merge is risky
        log INFO "Worktree has changes. Use /worktree-cleanup to merge when ready."
        log INFO "Worktree path: $agent_worktree_path"

        # macOS notification
        if [[ "$OSTYPE" == "darwin"* ]] && command -v osascript &>/dev/null; then
            osascript -e "display notification \"$SUBAGENT_TYPE completed with changes\" with title \"CCAGI Orchestrator\" sound name \"Frog\"" 2>/dev/null || true
        fi
    else
        log INFO "Sub-Agent made no changes. Cleaning up empty worktree."

        # Safe to auto-cleanup empty worktrees
        cleanup_task_worktree true 2>/dev/null || {
            log WARN "Auto-cleanup failed. Manual cleanup: /worktree-cleanup"
        }
    fi

    exit 0
}

# Run main
main "$@"
