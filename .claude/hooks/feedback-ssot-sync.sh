#!/bin/bash
# CCAGI Hook: Feedback to SSOT Sync
# フィードバックファイル作成後、自動でSSOT Issueにコメントを追加
#
# Usage: Called by PostToolCall hook when Write tool creates feedback file

set -e

TOOL_INPUT="$1"
TOOL_OUTPUT="$2"

# フィードバックファイルかチェック
if ! echo "$TOOL_INPUT" | grep -q ".ai/feedback/.*feedback.md"; then
  exit 0
fi

# プロジェクトルート - Dynamic path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# SSOT Issue番号を取得
SSOT_ISSUE=$(grep 'issue_number' .ccagi.yml 2>/dev/null | head -1 | awk '{print $2}')

if [ -z "$SSOT_ISSUE" ]; then
  echo "⚠️ SSOT Issue未設定 - フィードバックはローカルのみに記録"
  exit 0
fi

# 作成されたフィードバックファイルのパスを取得
FEEDBACK_FILE=$(echo "$TOOL_INPUT" | grep -oE '/Users/[^"]+feedback\.md' | head -1)

if [ -z "$FEEDBACK_FILE" ] || [ ! -f "$FEEDBACK_FILE" ]; then
  exit 0
fi

# フィードバック内容を抽出
CONTENT=$(grep -A1 "^\- \*\*内容\*\*:" "$FEEDBACK_FILE" | head -1 | sed 's/^- \*\*内容\*\*: //')
URGENCY=$(grep "^\- \*\*緊急度\*\*:" "$FEEDBACK_FILE" | sed 's/^- \*\*緊急度\*\*: //')
CATEGORY=$(grep "^\- \*\*分類\*\*:" "$FEEDBACK_FILE" | sed 's/^- \*\*分類\*\*: //')
DATETIME=$(grep "^\- \*\*日時\*\*:" "$FEEDBACK_FILE" | sed 's/^- \*\*日時\*\*: //')

# 緊急度アイコン
case "$URGENCY" in
  高) URGENCY_ICON="🔴" ;;
  中) URGENCY_ICON="🟡" ;;
  低) URGENCY_ICON="🟢" ;;
  *) URGENCY_ICON="⚪" ;;
esac

# ファイル名からIDを生成
FEEDBACK_ID=$(basename "$FEEDBACK_FILE" .md | sed 's/-feedback//')

# 既にSSOTに記載されているかチェック（重複防止）
EXISTING=$(gh issue view "$SSOT_ISSUE" --json body,comments 2>/dev/null | grep -c "FEEDBACK_FILE:$FEEDBACK_FILE" || echo "0")

if [ "$EXISTING" -gt 0 ]; then
  echo "ℹ️ 既にSSOT Issue #${SSOT_ISSUE} に記載済み"
  exit 0
fi

# SSOT Issueにコメント追加
gh issue comment "$SSOT_ISSUE" --body "$(cat <<EOF
## 💬 User Feedback

| 項目 | 内容 |
|------|------|
| **ID** | FB-${FEEDBACK_ID} |
| **日時** | ${DATETIME} |
| **種別** | ${CATEGORY} |
| **緊急度** | ${URGENCY_ICON} ${URGENCY} |
| **ステータス** | 🟡 pending |

### フィードバック内容

${CONTENT}

---
<!-- FEEDBACK_FILE:${FEEDBACK_FILE} -->
<!-- AUTO_SYNCED:$(date '+%Y-%m-%d %H:%M:%S') -->
EOF
)"

echo "✅ フィードバックをSSOT Issue #${SSOT_ISSUE} に自動記載しました"

# フィードバックファイルにSSOT記載済みマークを追加
if ! grep -q "ssot_synced:" "$FEEDBACK_FILE"; then
  echo "" >> "$FEEDBACK_FILE"
  echo "---" >> "$FEEDBACK_FILE"
  echo "ssot_synced: true" >> "$FEEDBACK_FILE"
  echo "ssot_issue: ${SSOT_ISSUE}" >> "$FEEDBACK_FILE"
  echo "synced_at: $(date '+%Y-%m-%d %H:%M:%S')" >> "$FEEDBACK_FILE"
fi
