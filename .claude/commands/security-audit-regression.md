---
description: 過去の全セキュリティ修正の regression を一括検証する。
---
このコマンドはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "security-audit-regression")
```

**重要**: このコマンドを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
