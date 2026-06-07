#!/bin/bash
#
# CCAGI Format Check Hook
#
# このフックはEdit操作後に自動的にフォーマットをチェックします。
#
# CCAGI Policy: 品質基準維持、自動フォーマット

set -euo pipefail

# Configuration - Dynamic path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Input (file path from TOOL_INPUT)
FILE_PATH="${1:-}"

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Check if file is TypeScript/JavaScript
if ! echo "$FILE_PATH" | grep -qE '\.(ts|tsx|js|jsx)$'; then
    exit 0
fi

# Run Prettier on the file (non-blocking)
if command -v prettier &> /dev/null; then
    cd "$PROJECT_ROOT"
    prettier --write "$FILE_PATH" 2>/dev/null || true
fi

exit 0
