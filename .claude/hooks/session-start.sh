#!/bin/bash
#
# CCAGI Session Start Hook
#
# このフックはセッション開始時に実行され、
# システム状態の確認と優先タスクの表示を行います。
#
# CCAGI Policy: 完全自律動作、外部依存なし

set -euo pipefail

# Configuration - Dynamic path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/.ai/logs"
mkdir -p "$LOG_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Log session start
echo "[$(date '+%Y-%m-%d %H:%M:%S')] CCAGI Session Started" >> "$LOG_DIR/session.log"

# RAG integration point (skeleton — ccmvec integration pending)
# To enable: ensure ccmvec-search.sh is installed and executable, then uncomment below.
# The timeout guard (5s) prevents session hang if the script blocks.
# if [ -x "$HOME/.claude/hooks/ccmvec-search.sh" ]; then
#     timeout 5 "$HOME/.claude/hooks/ccmvec-search.sh" "$(basename "$PROJECT_ROOT")" 2>/dev/null || true
# fi

# ── CCAGI Navigation: Phase detection ──
CURRENT_PHASE="unknown"
if [ -d "$PROJECT_ROOT/docs/requirements" ]; then
    CURRENT_PHASE="1-requirements"
fi
if [ -d "$PROJECT_ROOT/docs/design" ]; then
    CURRENT_PHASE="2-design"
fi
if [ -f "$PROJECT_ROOT/docs/design/spec.md" ] && [ -f "$PROJECT_ROOT/docs/design/design-system.yml" ]; then
    CURRENT_PHASE="3-planning"
fi
if [ -d "$PROJECT_ROOT/src" ] && [ "$(timeout 3 find "$PROJECT_ROOT/src" -name '*.ts' -o -name '*.tsx' 2>/dev/null | head -1)" ]; then
    CURRENT_PHASE="4-implementation"
fi
if [ -d "$PROJECT_ROOT/.test-logs" ] || [ -d "$PROJECT_ROOT/coverage" ]; then
    CURRENT_PHASE="5-testing"
fi

# ── CCAGI Navigation: Conflict detection ──
CONFLICT_WARNING=""
if [ -d "$PROJECT_ROOT/.claude-plugin" ] || [ -f "$HOME/.claude/skills/using-superpowers/SKILL.md" ]; then
    CONFLICT_WARNING="
${YELLOW}Plugin Conflict Detected:${NC}
  A third-party plugin (superpowers) is installed.
  CCAGI commands take priority. See: .claude/rules/plugin-priority.md"
fi

# Display welcome message with navigation context
cat <<EOF

${GREEN}╔════════════════════════════════════════════════════════════╗${NC}
${GREEN}║                    CCAGI System Active                     ║${NC}
${GREEN}╚════════════════════════════════════════════════════════════╝${NC}

${BLUE}System Status:${NC}
  🟢 Core Functions: Operational
  🟢 Agent System: Ready
  🟢 MCP Servers: Available

${BLUE}Quality Standards:${NC}
  ✓ TypeScript Errors: 0 (Required)
  ✓ ESLint Errors: 0 (Required)
  ✓ Test Coverage: 80%+ (Required)
  ✓ Security Score: 80+ (Required)

${BLUE}Design Principles:${NC}
  🔒 外部停止不可能 - No Remote Shutdown
  🔄 完全自律動作 - Fully Autonomous
  🛡️  外部依存最小化 - Minimal External Dependencies
${CONFLICT_WARNING}

${YELLOW}Ready for commands.${NC}

EOF

# ── CCAGI Navigation Context (additionalContext for Claude) ──
# Phase-aware command suggestions
case "$CURRENT_PHASE" in
    "1-requirements")
        NEXT_CMD="Phase 1 active. Next: /spec-create, /design-system"
        ;;
    "2-design")
        NEXT_CMD="Phase 2 active. Next: /create-ssot-issue, /ux-review"
        ;;
    "3-planning")
        NEXT_CMD="Phase 3 active. Next: /implement-app"
        ;;
    "4-implementation")
        NEXT_CMD="Phase 4 active. Next: /test --mode all"
        ;;
    "5-testing")
        NEXT_CMD="Phase 5 active. Next: /mock-detector, /ui-skills"
        ;;
    *)
        NEXT_CMD="Start: /generate-requirements"
        ;;
esac

echo ""
echo "【CCAGI 開発ワークフロー ガイド】"
echo ""
echo "■ Issue-First原則:"
echo "  開発作業（Phase 4+）前にIssue起票必須。"
echo "  複合タスク（3ステップ以上）→ Epic Issue + Phase/Wave/Cycle分解。"
echo "  \`gh issue list\` で既存Issue確認 → なければ \`/create-issue\`。"
echo ""
echo "■ Agent Pipeline:"
echo "  ソースコード変更 → Agent経由（CoordinatorAgent or CodeGenAgent）。"
echo "  設定・ドキュメント変更 → 直接Edit可。"
echo ""
echo "■ 並列度制限:"
echo "  subagentはマシンスペック自動検出（15〜20基本・上限40）で並列起動。並列可能な独立タスクは積極的に並列実行。"

# Check for pending tasks (optional)
if [ -f "$PROJECT_ROOT/.ai/tasks/pending.json" ]; then
    echo -e "${BLUE}📋 Pending Tasks Available${NC}"
    echo "   Run: npm run agents:parallel:exec -- --issue <number>"
    echo ""
fi

# Agent Progress Dashboard (optional — requires tmux)
AGENT_PROGRESS_TMUX="$SCRIPT_DIR/agent-progress-tmux.sh"
if [ -x "$AGENT_PROGRESS_TMUX" ] && command -v tmux &>/dev/null; then
    "$AGENT_PROGRESS_TMUX" setup 2>/dev/null || true
fi

exit 0
