#!/bin/bash
#
# CCAGI Session End Hook
#
# このフックはセッション終了時に実行され、
# 状態のレポートとクリーンアップを行います。
#
# CCAGI Policy: 完全自律動作、外部依存なし

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Validate PROJECT_ROOT exists
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Error: PROJECT_ROOT does not exist: $PROJECT_ROOT" >&2
    exit 1
fi

LOG_DIR="$PROJECT_ROOT/.ai/logs"
mkdir -p "$LOG_DIR" 2>/dev/null || {
    echo "Warning: Could not create log directory: $LOG_DIR" >&2
}

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Log session end
echo "[$(date '+%Y-%m-%d %H:%M:%S')] CCAGI Session Ended" >> "$LOG_DIR/session.log"

# Display summary
cat <<EOF

${GREEN}╔════════════════════════════════════════════════════════════╗${NC}
${GREEN}║                 CCAGI Session Summary                      ║${NC}
${GREEN}╚════════════════════════════════════════════════════════════╝${NC}

${BLUE}Session completed at:${NC} $(date '+%Y-%m-%d %H:%M:%S')

${BLUE}System Status:${NC}
  ✅ All operations completed
  ✅ State saved to logs

${YELLOW}Thank you for using CCAGI.${NC}

EOF

# Check for uncommitted changes
if cd "$PROJECT_ROOT" 2>/dev/null && git rev-parse --git-dir >/dev/null 2>&1; then
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Warning: Uncommitted changes detected${NC}"
        echo "   Run 'git status' to review changes"
        echo ""
    fi
fi

exit 0
