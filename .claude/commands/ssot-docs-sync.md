---
description: SSOT Issue（正）からdocs（副）への同期を行う。
---
このコマンドはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "ssot-docs-sync")
```

**重要**: このコマンドを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
