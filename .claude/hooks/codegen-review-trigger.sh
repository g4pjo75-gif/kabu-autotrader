#!/bin/bash
# CodeGen → ReviewAgent Auto-Trigger Hook
# PostToolUse: Task完了時にCodeGenAgentを検知してReviewAgentを起動

TOOL_OUTPUT="$1"
LOG_DIR=".ai/logs/hooks"
mkdir -p "$LOG_DIR"

# CodeGenAgentの完了を検知
if echo "$TOOL_OUTPUT" | grep -qiE "(CodeGenAgent|codegen|コード生成).*完了|success|generated"; then
  TIMESTAMP=$(date +%Y%m%d-%H%M%S)

  # ログ記録
  echo "[${TIMESTAMP}] CodeGenAgent完了検知 - ReviewAgent起動準備" >> "$LOG_DIR/codegen-review.log"

  # VOICEVOX通知（バックグラウンド）
  if [ -x ~/.claude/scripts/voicevox-speak.sh ]; then
    ~/.claude/scripts/voicevox-speak.sh "コード生成完了。ReviewAgentを起動します。" 2>/dev/null &
  fi

  # macOS通知
  osascript -e 'display notification "CodeGenAgent完了 → ReviewAgent起動" with title "CCAGI Hooks" sound name "Glass"' 2>/dev/null

  # ReviewAgent起動フラグをセット（Claude Codeが読み取る）
  echo "{\"trigger\": \"codegen_complete\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"action\": \"review\"}" > "$LOG_DIR/review-trigger.json"

  echo "[HOOK] CodeGenAgent完了 → ReviewAgentトリガー設定"
  exit 0
fi

# CodeGenAgent以外は無視
exit 0
