---
name: migration-engine
description: Abstract migration engine with YAML-defined specs for codebase migrations. Suppo…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "migration-engine")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
