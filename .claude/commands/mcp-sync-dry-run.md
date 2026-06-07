---
description: sync-to-delivery.sh を --dry-run で実行し、ccagi-delivery への影響を…
---
このコマンドはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "mcp-sync-dry-run")
```

**重要**: このコマンドを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
