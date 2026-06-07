---
description: jj periodic housekeeping specialist (cron-like). Owns stale-bookmark prune, keep…
---
このエージェントはCCAGI MCPサーバーを通じて実行されます。

**実行方法**: MCPツール `agent_run` を使用

```
agent_run(name: "jj-janitor")
```

**重要**: このエージェントを独自に代替実装してはいけません。必ず上記MCPツールを呼び出してください。
