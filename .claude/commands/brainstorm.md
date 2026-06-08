# /brainstorm → CCAGI Phase 1: Requirements

This command is redirected from a third-party plugin to CCAGI's workflow.

**Do not use a brainstorm workflow.** Instead, execute CCAGI Phase 1:

```
/generate-requirements
```

This generates:
- `docs/requirements/requirements.md` (functional requirements)
- `docs/requirements/non-functional.md` (non-functional requirements)
- `docs/requirements/design-requirements.md` (design requirements)

For conflict resolution between CCAGI commands and third-party plugins, run `ccagi-sdk doctor`.
