# /execute-plan → CCAGI Phase 4: Implementation

This command is redirected from a third-party plugin to CCAGI's workflow.

**Do not use an execute-plan workflow.** Instead, execute CCAGI Phase 4:

```
/implement-app
```

This triggers CoordinatorAgent → CodeGenAgent pipeline with full Phase gate enforcement.

For conflict resolution between CCAGI commands and third-party plugins, run `ccagi-sdk doctor`.
