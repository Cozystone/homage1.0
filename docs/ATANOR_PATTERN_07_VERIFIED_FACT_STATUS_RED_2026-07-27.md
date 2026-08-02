# Pattern #7 baseline RED: missing status self-promotes

Preregistration:
`docs/ATANOR_PATTERN_07_VERIFIED_FACT_STATUS_PREREG_2026-07-27.md`

Baseline:

- Git HEAD: `bc5cccde42080a784f490ebbb53414cf7ec45131`
- `packages/cgsr/cgsr/verified_fact_retrieval.py` SHA-256:
  `60db9cd6b34b7c5ce173c9bafcb2ab6fbb86cca3a37d8775bad6cd034d343e57`
- Production source edits before reproduction: none

Legitimate control command:

```text
python -m pytest packages/cgsr/tests/test_verified_fact_status_authority_boundary.py -q -k "explicit_positive_status or legitimate_source_receipt"
```

Result: `3 passed, 12 deselected`.

Adversarial command:

```text
python -m pytest packages/cgsr/tests/test_verified_fact_status_authority_boundary.py -q -k "missing_malformed_or_conflicting_status or rejected_row"
```

Result: `8 failed, 4 passed, 3 deselected`.

The failing variants were:

- no status field
- empty verification object
- null top-level status
- empty top-level status
- null nested status
- empty nested status
- top-level `accepted` conflicting with nested `rejected`
- downstream grounding from the status-less forged Berlin row

The four passing adversarial controls were explicit `pending`, `rejected`,
`quarantined`, and unknown uppercase `VERIFIED`; these were already rejected.

Observed source-to-sink result: the forged status-less fact
`The capital of France is Berlin.` became a `VerifiedFactHit` and then a
`verified_store_v0_readonly` grounded context. The preregistered security
invariant is therefore RED on the unmodified baseline.

No production source, staging graph, verified store, or sibling store was
modified during this reproduction.
