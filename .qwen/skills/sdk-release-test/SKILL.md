---
name: sdk-release-test
description: ccagi-sdk リリース後の最終テスト。S3 URL から /tmp にダウンロ…
---
このスキルはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `skill_execute` を使用

```
skill_execute(name: "sdk-release-test")
```

**重要**: このスキルを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
