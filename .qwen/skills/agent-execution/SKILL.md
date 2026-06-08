---
name: agent-execution
description: Execute CCAGI Agents (Coordinator, CodeGen, Review, Security, Test, PR, Issue) w…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "agent-execution")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
