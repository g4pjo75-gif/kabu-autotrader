---
description: ccagi-delivery との結合テスト (path dependency解決, cargo check) を実…
---
このコマンドはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "mcp-integration-test")
```

**重要**: このコマンドを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
