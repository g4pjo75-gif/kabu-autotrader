---
description: TypeScript→Rust移行専門Agent - 安全なRust移行とNAPIバインディ…
---
このエージェントはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `agent_run` を使用

```
agent_run(name: "rustmigration")
```

**重要**: このエージェントを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
