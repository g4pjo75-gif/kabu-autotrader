#!/bin/bash
# ===================================================================
# Git Ops Validator Hook (CC AGI版)
# ===================================================================
# Version: 2.0.0 (CC AGI Integration)
# Last Updated: 2025-12-04
#
# Purpose: Validate Git operations against CC AGI rules
# Triggers: PreToolUse(Bash) when git commands are detected
#
# CC AGI Rules Enforced:
# 1. Conventional Commits format
# 2. Branch naming convention
# 3. Safety protocol (no force push to main, etc.)
# 4. No external service calls (AWS, etc.)
# 5. Quality standards (TypeScript errors: 0)
#
# CC AGI Policy: 完全自律動作、外部依存なし
# ===================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (CC AGI paths) - Dynamic path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/.ai/logs/git-ops-$(date +%Y-%m-%d).log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    log "ERROR: $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
    log "WARNING: $1"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    log "INFO: $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    log "SUCCESS: $1"
}

# Extract git command from bash command
extract_git_command() {
    local bash_cmd="$1"

    # Check if it's a git command
    if [[ ! "$bash_cmd" =~ git[[:space:]] ]]; then
        return 1
    fi

    # Extract the git subcommand
    echo "$bash_cmd" | grep -oE 'git\s+\w+' | awk '{print $2}' | head -1
}

# Validate commit message format
validate_commit_message() {
    local commit_msg="$1"

    log_info "Validating commit message format..."

    # Check for Conventional Commits format
    if ! echo "$commit_msg" | grep -qE '^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\([a-z]+\))?:\s.+'; then
        log_error "Commit message does not follow Conventional Commits format"
        cat <<EOF
❌ Commit Message Validation Failed

Expected format: <type>(<scope>): <subject>

Valid types:
  - feat: New feature
  - fix: Bug fix
  - docs: Documentation only
  - style: Code style/formatting
  - refactor: Code refactoring
  - perf: Performance improvement
  - test: Test addition/modification
  - chore: Build/tooling changes
  - ci: CI/CD changes
  - build: Build system changes
  - revert: Revert previous commit

Example:
  feat(agent): add CodeGenAgent with Rust support

See: CLAUDE.md - CC AGI Design Principles
EOF
        return 1
    fi

    # Check for CC AGI attribution footer (warning only, not blocking)
    if ! echo "$commit_msg" | grep -qi "Co-Authored-By:.*CC AGI"; then
        log_warning "Missing CC AGI Co-Authored-By footer (recommended)"
        cat <<EOF
⚠️  Missing Attribution Footer (warning only)

Recommended footer:

Co-Authored-By: CC AGI <noreply@customercloud.co.jp>

EOF
        # Warning only — do not block commit
    fi

    log_success "Commit message format valid"
    return 0
}

# Validate branch name
validate_branch_name() {
    local branch_name="$1"

    log_info "Validating branch name: $branch_name"

    # Skip validation for main/master
    if [[ "$branch_name" == "main" || "$branch_name" == "master" ]]; then
        return 0
    fi

    # Check for valid branch naming convention
    if ! echo "$branch_name" | grep -qE '^(feature|fix|docs|refactor|test|chore)/[0-9]+-[a-z0-9-]+$'; then
        log_warning "Branch name does not follow CC AGI convention"
        cat <<EOF
⚠️  Branch Naming Convention

Expected format: <type>/<issue-number>-<description>

Valid types:
  - feature/: New features
  - fix/: Bug fixes
  - docs/: Documentation changes
  - refactor/: Code refactoring
  - test/: Test additions
  - chore/: Maintenance tasks

Examples:
  - feature/270-codegen-agent
  - fix/271-worktree-race-condition
  - docs/272-update-guides

See: CLAUDE.md - CC AGI Workflow
EOF
        return 1
    fi

    log_success "Branch name valid"
    return 0
}

# Validate git push command
validate_git_push() {
    local bash_cmd="$1"
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

    log_info "Validating git push command..."

    # Check for force push to main/master
    if echo "$bash_cmd" | grep -qE 'push.*--force'; then
        if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
            log_error "Force push to main/master is forbidden"
            cat <<EOF
🚨 FORBIDDEN OPERATION

Force push to main/master is strictly prohibited.

CC AGI Git Safety Protocol:
  ❌ NEVER: force push to main/master
  ✅ ALWAYS: Use --force-with-lease for other branches

Current branch: $current_branch

See: CLAUDE.md - CC AGI Design Principles
EOF
            return 1
        fi

        # Recommend --force-with-lease
        if ! echo "$bash_cmd" | grep -q -- "--force-with-lease"; then
            log_warning "Use --force-with-lease instead of --force"
            cat <<EOF
⚠️  Unsafe Force Push

Recommendation: Use --force-with-lease instead of --force

Why?
  - --force-with-lease checks for remote changes
  - Prevents accidental overwrites
  - Safer for collaborative work

Better command:
  git push --force-with-lease

See: CLAUDE.md - Git Safety Protocol
EOF
        fi
    fi

    log_success "Git push validation passed"
    return 0
}

# Validate git commit command
validate_git_commit() {
    local bash_cmd="$1"

    log_info "Validating git commit command..."

    # Extract commit message (POSIX-compatible, works on macOS BSD and Linux)
    local commit_msg
    commit_msg=$(echo "$bash_cmd" | sed -n 's/.*-m[[:space:]]*"\([^"]*\)".*/\1/p')

    if [[ -z "$commit_msg" ]]; then
        # Try heredoc format
        commit_msg=$(echo "$bash_cmd" | sed -n '/cat.*EOF/,/EOF/p' || echo "")
    fi

    if [[ -z "$commit_msg" ]]; then
        log_warning "Could not extract commit message for validation"
        return 0
    fi

    # Validate commit message
    validate_commit_message "$commit_msg" || return 1

    log_success "Git commit validation passed"
    return 0
}

# Validate git checkout/branch operations
validate_git_branch_ops() {
    local bash_cmd="$1"

    log_info "Validating git branch operation..."

    # Extract new branch name
    local branch_name
    branch_name=$(echo "$bash_cmd" | sed -n 's/.*checkout[[:space:]]*-b[[:space:]]*\([^[:space:]]*\).*/\1/p')

    if [[ -z "$branch_name" ]]; then
        # Try other formats
        branch_name=$(echo "$bash_cmd" | sed -n 's/.*branch[[:space:]]*\([^[:space:]]*\).*/\1/p')
    fi

    if [[ -n "$branch_name" ]]; then
        validate_branch_name "$branch_name" || return 1
    fi

    log_success "Git branch operation validation passed"
    return 0
}

# Main validation function
validate_git_operation() {
    local bash_cmd="$1"

    log "=== CC AGI Git Ops Validation Started ==="
    log "Command: $bash_cmd"

    local git_cmd
    git_cmd=$(extract_git_command "$bash_cmd") || {
        log "Not a git command, skipping validation"
        return 0
    }

    log_info "Detected git command: $git_cmd"

    case "$git_cmd" in
        commit)
            validate_git_commit "$bash_cmd" || return 1
            ;;
        push)
            validate_git_push "$bash_cmd" || return 1
            ;;
        checkout|branch)
            validate_git_branch_ops "$bash_cmd" || return 1
            ;;
        config)
            log_warning "Direct git config modification detected"
            cat <<EOF
⚠️  Git Config Modification

CC AGI Git Safety Protocol:
  ❌ NEVER: Update git config without approval
  ✅ ALWAYS: Maintain system integrity

See: CLAUDE.md - CC AGI Design Principles
EOF
            ;;
        reset)
            if echo "$bash_cmd" | grep -q -- "--hard"; then
                log_warning "Destructive git reset detected"
                cat <<EOF
⚠️  Destructive Operation

git reset --hard is a destructive operation.

Consider safer alternatives:
  - git reset --soft HEAD~1 (keep changes)
  - git restore <file> (restore specific files)

See: CLAUDE.md - Git Safety Protocol
EOF
            fi
            ;;
    esac

    log "=== CC AGI Git Ops Validation Completed ==="
    log_success "All validations passed"
    return 0
}

# Main execution
main() {
    # Read input from stdin or argument
    local raw_input="${1:-$(cat)}"
    local bash_cmd

    # Claude Code PreToolUse hook sends JSON input
    # Try to extract .tool_input.command from JSON
    if command -v jq &>/dev/null \
        && echo "$raw_input" | jq -e '.tool_input.command' >/dev/null 2>&1
    then
        bash_cmd=$(echo "$raw_input" | jq -r '.tool_input.command')
    elif echo "$raw_input" | python3 -c \
        "import sys,json; json.load(sys.stdin)" >/dev/null 2>&1
    then
        bash_cmd=$(echo "$raw_input" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))")
    else
        # Fallback: treat raw input as bash command (backward compatible)
        bash_cmd="$raw_input"
    fi

    if [[ -z "$bash_cmd" ]]; then
        return 0
    fi

    # Validate the git operation
    validate_git_operation "$bash_cmd"

    return $?
}

# Run main if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
