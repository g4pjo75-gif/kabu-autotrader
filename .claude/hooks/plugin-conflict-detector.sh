#!/bin/bash
#
# Plugin Conflict Detector — SessionStart hook
#
# Detects third-party plugins that may conflict with CCAGI commands.
# Output: ONLY when conflicts are detected (completely silent otherwise).
#
# CCAGI Policy: 完全自律動作、外部依存なし

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CONFLICTS_FOUND=0
CONFLICT_DETAILS=""

# Check 1: superpowers plugin (.claude-plugin/ directory)
if [ -d "$PROJECT_ROOT/.claude-plugin" ]; then
    CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
    CONFLICT_DETAILS="${CONFLICT_DETAILS}\n  - .claude-plugin/ directory detected (superpowers plugin)"
fi

# Check 2: superpowers skill in user-global scope
if [ -f "$HOME/.claude/skills/using-superpowers/SKILL.md" ]; then
    CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
    CONFLICT_DETAILS="${CONFLICT_DETAILS}\n  - ~/.claude/skills/using-superpowers/SKILL.md detected"
fi

# Check 3: superpowers hooks in user-global settings (timeout guarded)
if [ -f "$HOME/.claude/settings.json" ]; then
    if timeout 3 grep -q "superpowers" "$HOME/.claude/settings.json" 2>/dev/null; then
        CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
        CONFLICT_DETAILS="${CONFLICT_DETAILS}\n  - superpowers reference in ~/.claude/settings.json"
    fi
fi

# Only produce output if conflicts were found
if [ "$CONFLICTS_FOUND" -gt 0 ]; then
    echo "Plugin conflict detected: ${CONFLICTS_FOUND} source(s)"
    echo -e "Conflicts:${CONFLICT_DETAILS}"
    echo ""
    echo "CCAGI commands take priority. Conflicting commands are redirected:"
    echo "  /brainstorm    → /generate-requirements (Phase 1)"
    echo "  /write-plan    → /spec-create + /create-ssot-issue (Phase 2-3)"
    echo "  /execute-plan  → /implement-app (Phase 4)"
    echo ""
    echo "See: .claude/rules/plugin-priority.md"
fi

exit 0
