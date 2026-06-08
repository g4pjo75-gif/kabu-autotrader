---
name: security-scanner
description: ProwlerとOWASP ZAP (Baseline Scan)を使用してセキュリティチェック…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "security-scanner")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
