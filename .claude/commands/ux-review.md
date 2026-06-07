---
description: DAG分解後に必須で実行されるUXレビューコマンド。
---
このコマンドはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "ux-review")
```

**重要**: このコマンドを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
