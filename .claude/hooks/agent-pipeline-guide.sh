#!/bin/bash
# ===================================================================
# Agent Pipeline Guide - SessionStart Hook
# Related GitHub issues in project tracker
# Purpose: Inject CCAGI development workflow guidance at session start
# ===================================================================

set -euo pipefail

cat <<'GUIDANCE_EOF'

【CCAGI 開発ワークフロー ガイド】

■ Issue-First原則:
  開発作業（Phase 4+）前にIssue起票必須。
  複合タスク（3ステップ以上）→ Epic Issue + Phase/Wave/Cycle分解。
  `gh issue list` で既存Issue確認 → なければ `/create-issue`。

■ Agent Pipeline:
  ソースコード変更 → Agent経由（CoordinatorAgent or CodeGenAgent）。
  設定・ドキュメント変更 → 直接Edit可。

■ 並列度制限:
  subagentはマシンスペック自動検出（15〜20基本・上限40）で並列起動。並列可能な独立タスクは積極的に並列実行。

GUIDANCE_EOF

exit 0
