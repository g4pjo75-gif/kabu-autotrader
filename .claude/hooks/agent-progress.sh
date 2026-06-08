#!/bin/bash
# CCAGI Agent Progress Hook — Colored Console Output
# Trigger: PreToolCall + PostToolCall (Task tool)
#
# Claude Code hook that displays colored agent status in the terminal.
# Each agent type gets a unique color based on hue distribution (180-330 degrees).
# Colors avoid red/green/yellow to prevent confusion with error/success/warning.
#
# Compatible with bash 3.2+ (macOS default).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
PROGRESS_LOG="${PROJECT_ROOT}/.ai/logs/agent-progress.log"

mkdir -p "$(dirname "$PROGRESS_LOG")"

# === ANSI Color Definitions (256-color mode) ===
# Red(31)/Green(32)/Yellow(33) are NEVER used (reserved for error/success/warning)
# Hue distribution: Cyan(180) -> Blue(240) -> Purple(280) -> Magenta(310) -> Pink(330)
NC='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
DEFAULT_COLOR="\033[38;5;152m"

# Agent -> Color lookup (bash 3.2 compatible, no associative arrays)
# allow-dev-metadata: functional terminal display label per Decision 2026-04-24 Q1
#                     (color codes are visual labels, not IP-residue character names)
get_agent_color() {
    case "$1" in
        # Core pipeline agents (hue 180-280 = step progression)
        CoordinatorAgent)        echo "\033[38;5;44m"  ;; # Cyan (180) - Step 1
        CodeGenAgent)            echo "\033[38;5;75m"  ;; # Sky Blue (207) - Step 2
        ReviewAgent)             echo "\033[38;5;69m"  ;; # Cornflower (225) - Step 3
        IssueAgent)              echo "\033[38;5;27m"  ;; # Blue (240) - Step 4
        PRAgent)                 echo "\033[38;5;63m"  ;; # Slate Blue (260) - Step 5
        DeploymentAgent)         echo "\033[38;5;129m" ;; # Purple (280) - Step 6
        # Development agents
        FrontendAgent)           echo "\033[38;5;117m" ;; # Light Blue (195)
        BackendAgent)            echo "\033[38;5;57m"  ;; # Indigo (250)
        DatabaseAgent)           echo "\033[38;5;99m"  ;; # Blue Violet (270)
        ArchitectureAgent)       echo "\033[38;5;135m" ;; # Violet (290)
        APIAgent)                echo "\033[38;5;111m" ;; # Steel Blue (210)
        # Ops/Quality agents
        DevOpsAgent)             echo "\033[38;5;62m"  ;; # Slate (255)
        QAAgent)                 echo "\033[38;5;105m" ;; # Medium Purple (265)
        RefactorAgent)           echo "\033[38;5;68m"  ;; # Cornflower Dark (230)
        PerformanceAgent)        echo "\033[38;5;74m"  ;; # Cadet Blue (200)
        OptimizationAgent)       echo "\033[38;5;110m" ;; # Light Steel (215)
        MonitoringAgent)         echo "\033[38;5;67m"  ;; # Steel Gray (228)
        IncidentAgent)           echo "\033[38;5;61m"  ;; # Slate Purple (253)
        AWSAgent)                echo "\033[38;5;73m"  ;; # Teal (198)
        DeployInfraAgent)        echo "\033[38;5;103m" ;; # Mauve (262)
        # Automation agents
        BrowserAutomationAgent)  echo "\033[38;5;170m" ;; # Magenta (310)
        TmuxControlAgent)        echo "\033[38;5;213m" ;; # Pink (330)
        BatchIssueAgent)         echo "\033[38;5;176m" ;; # Light Magenta (315)
        RefresherAgent)          echo "\033[38;5;183m" ;; # Lavender (322)
        # Document agents
        DocumentationAgent)      echo "\033[38;5;152m" ;; # Light Cyan
        UXReviewAgent)           echo "\033[38;5;141m" ;; # Light Purple (285)
        MigrationAgent)          echo "\033[38;5;146m" ;; # Light Gray Blue
        AIProductAnalyzerAgent)  echo "\033[38;5;147m" ;; # Light Periwinkle
        # Special agents
        LicenseManagementAgent)  echo "\033[38;5;109m" ;; # Light Slate
        RustMigrationAgent)      echo "\033[38;5;139m" ;; # Dusty Purple
        # Explore/general
        Explore)                 echo "\033[38;5;80m"  ;; # Medium Cyan (186)
        Plan)                    echo "\033[38;5;43m"  ;; # Dark Cyan (178)
        general-purpose)         echo "\033[38;5;152m" ;; # Light Cyan
        # Default
        *)                       echo "$DEFAULT_COLOR" ;;
    esac
}

# Agent -> Emoji lookup (Option A: universal, no character convention required)
get_agent_emoji() {
    case "$1" in
        CoordinatorAgent)        echo "🎯" ;; # target — orchestration
        CodeGenAgent)            echo "💻" ;; # laptop — code generation
        ReviewAgent)             echo "🔍" ;; # magnifying glass — review
        IssueAgent)              echo "📋" ;; # clipboard — analysis
        PRAgent)                 echo "🔗" ;; # link — PR connection
        DeploymentAgent)         echo "🚀" ;; # rocket — deploy
        BrowserAutomationAgent)  echo "🌐" ;; # globe — browser
        TmuxControlAgent)        echo "📺" ;; # TV — terminal
        BatchIssueAgent)         echo "📦" ;; # package — batch
        RefresherAgent)          echo "🔄" ;; # refresh — update
        *)                       echo ""   ;;
    esac
}

# === Input parsing ===
HOOK_EVENT="${CLAUDE_HOOK_EVENT:-}"
TOOL_INPUT="${1:-}"

# Extract agent type and description (same pattern as agent-logger.sh)
AGENT_TYPE=""
AGENT_DESC=""
if [ -n "$TOOL_INPUT" ]; then
    if command -v jq &>/dev/null; then
        AGENT_TYPE=$(echo "$TOOL_INPUT" | jq -r '.subagent_type // empty' 2>/dev/null || echo "")
        AGENT_DESC=$(echo "$TOOL_INPUT" | jq -r '.description // empty' 2>/dev/null || echo "")
    else
        AGENT_TYPE=$(echo "$TOOL_INPUT" | grep -oE '"subagent_type":\s*"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
        AGENT_DESC=$(echo "$TOOL_INPUT" | grep -oE '"description":\s*"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
    fi
fi

# Exit silently if not a Task tool call with subagent_type
[ -z "$AGENT_TYPE" ] && exit 0

# === Color & Emoji lookup ===
COLOR=$(get_agent_color "$AGENT_TYPE")
EMOJI=$(get_agent_emoji "$AGENT_TYPE")
EMOJI_DISPLAY=""
[ -n "$EMOJI" ] && EMOJI_DISPLAY=" ${EMOJI}"

TIMESTAMP=$(date '+%H:%M:%S')

# === Console Output ===
if [ "$HOOK_EVENT" = "PreToolCall" ]; then
    echo -e "${COLOR}┌─ 🚀 ${BOLD}${AGENT_TYPE}${NC}${COLOR}${EMOJI_DISPLAY} ── ${DIM}${AGENT_DESC}${NC}"
    echo -e "${COLOR}│  ${DIM}${TIMESTAMP}${NC}"

    # Log to file (for tmux tail)
    echo "[${TIMESTAMP}] START ${AGENT_TYPE}${EMOJI_DISPLAY}: ${AGENT_DESC}" >> "$PROGRESS_LOG"

elif [ "$HOOK_EVENT" = "PostToolCall" ]; then
    echo -e "${COLOR}└─ ✅ ${AGENT_TYPE}${EMOJI_DISPLAY} ${DIM}done ${TIMESTAMP}${NC}"
    echo ""

    # Log to file
    echo "[${TIMESTAMP}] DONE  ${AGENT_TYPE}${EMOJI_DISPLAY}" >> "$PROGRESS_LOG"
fi

exit 0
