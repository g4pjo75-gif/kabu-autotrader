# kabu-autotrader — CCAGI SDK Project

<!-- CCAGI-PRIORITY-START -->
> **CCAGI SDK Priority Declaration**
>
> This project is managed by CCAGI SDK. All `/slash-commands`, workflow phases,
> and agent pipelines are defined by CCAGI. If a third-party plugin (e.g. superpowers)
> conflicts with CCAGI commands, **CCAGI takes precedence**.
>
> - `/generate-app`, `/implement-app`, `/test` → CCAGI workflow (Phase 1-8)
> - `brainstorm`, `plan`, `execute` → redirected to CCAGI equivalents
> - See `.claude/rules/plugin-priority.md` for conflict resolution rules.
<!-- CCAGI-PRIORITY-END -->

CCAGI SDK プロジェクト。設定は `.ccagi.yml`。

---

## Rule imports (Internal tier)

@import .claude/rules/dev-rules.md
@import .claude/rules/pil-pipeline-rules.md
@import .claude/rules/ssot-generator.md
@import .claude/rules/context-budget-rules.md
@import .claude/rules/scope-contract.md
@import .claude/rules/vcs-rules.md
@import .claude/rules/error-lifecycle-rule.md
@import .claude/rules/plugin-priority.md
@import .claude/rules/brand-guidelines.md
@import .claude/rules/impl-verify-separation.md
@import .claude/rules/deprecated-hooks-rule.md
@import .claude/rules/learning-lookup-duty.md

---

## L0 — 情報参照ファースト

情報を参照する際・「L0」「L0を思い出して」と言われた際は、skill **`l0-first`** を呼び出す。

---

## 動的機能検索

MCP ツール経由でスキル/コマンド/エージェント取得:

```
mcp skill_list      # 全スキル一覧
mcp command_list    # 全コマンド一覧
mcp agent_list      # 全エージェント一覧
```

自然言語で意図を伝えれば、Skills/Commands description から自動マッチされます。

---

## RAGメモリ

- 開始時: `/rag-search`
- 終了時: `/rag-save`

---

*CCAGI SDK — Internal tier (MCP: 5 servers)*
Powered by CCAGI SDK v4.22.13
