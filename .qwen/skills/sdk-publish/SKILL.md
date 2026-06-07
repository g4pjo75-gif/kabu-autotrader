---
name: sdk-publish
description: ccagi-sdk プレビュー/安定版リリース。ビルド→テスト→S3ア…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "sdk-publish")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
