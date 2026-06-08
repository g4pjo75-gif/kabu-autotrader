---
name: SKILL
description: Wait for PR CI completion using rate-budget-aware helper. Uses scripts/wait-for-…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "SKILL")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
