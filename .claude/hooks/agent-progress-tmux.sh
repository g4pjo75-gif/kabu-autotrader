#!/bin/bash
# CCAGI Agent Progress tmux Dashboard Helper
# Manages a dedicated tmux session that tails agent-progress.log
#
# Usage:
#   agent-progress-tmux.sh setup    — Create tmux session with tail -f
#   agent-progress-tmux.sh teardown — Kill tmux session
#   agent-progress-tmux.sh status   — Check session status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
PROGRESS_LOG="${PROJECT_ROOT}/.ai/logs/agent-progress.log"
SESSION_NAME="ccagi-progress"

# === Functions ===

setup_dashboard() {
    if ! command -v tmux &>/dev/null; then
        echo "tmux not found. Skipping dashboard setup." >&2
        return 1
    fi

    # Already running
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Dashboard session already exists: $SESSION_NAME"
        echo "  Attach: tmux attach -t $SESSION_NAME"
        return 0
    fi

    # Ensure log file exists
    mkdir -p "$(dirname "$PROGRESS_LOG")"
    touch "$PROGRESS_LOG"

    # Create detached tmux session with tail -f on the progress log
    tmux new-session -d -s "$SESSION_NAME" -n "Agent Progress" \
        "tail -f '$PROGRESS_LOG'"

    echo "Dashboard started: tmux attach -t $SESSION_NAME"
}

teardown_dashboard() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        tmux kill-session -t "$SESSION_NAME"
        echo "Dashboard stopped."
    else
        echo "Dashboard not running."
    fi
}

status_dashboard() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "Dashboard: RUNNING (tmux attach -t $SESSION_NAME)"
    else
        echo "Dashboard: STOPPED"
    fi
}

# === Main ===
case "${1:-setup}" in
    setup)    setup_dashboard ;;
    teardown) teardown_dashboard ;;
    status)   status_dashboard ;;
    *)        echo "Usage: $0 {setup|teardown|status}" ;;
esac
