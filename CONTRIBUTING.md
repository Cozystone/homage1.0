# Contributing to ATANOR

ATANOR is a local-first AI OS research project. Contributions should improve
release readiness, privacy safety, runtime proof, UI clarity, documentation
honesty, or installability.

## Ground Rules

- Do not upload or request private Local Brain data.
- Do not expose raw IP addresses, exact locations, node IDs, device names,
  Payload Vault records, local file paths, secrets, or API keys.
- Do not claim the global contributor network is live unless real remote
  contributors have been verified.
- Label demo, preview, scaffold, and future-work states honestly.
- Keep external LLM answer generation disabled unless a future explicit policy
  changes that rule.

## Useful Checks

```powershell
python -m pytest apps/api/tests packages/rag_engine/tests packages/model/tests -q
npm --workspace apps/web run build
npm run audit:ui
```

## Pull Request Checklist

- [ ] Tests/build pass.
- [ ] No secrets or local absolute paths are added.
- [ ] UI copy distinguishes real, preview, scaffold, and future work.
- [ ] Privacy-sensitive identifiers are not shown in user-facing UI.
- [ ] Documentation is updated when behavior changes.
