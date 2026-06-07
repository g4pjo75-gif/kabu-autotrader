---
name: pipeline-validator
description: AWS CodePipelineのデプロイ前検証を行うスキル。buildspec.yml、Doc…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "pipeline-validator")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
