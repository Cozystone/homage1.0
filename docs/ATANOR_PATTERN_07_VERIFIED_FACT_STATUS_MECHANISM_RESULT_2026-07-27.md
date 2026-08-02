# Pattern #7 mechanism result: GREEN, capability NO_SIGNAL

Preregistration seal: `6e8e70d5d3a43e63a179e7c22a002dc2b5f46bab`

## Verdict

- Mechanism: **GREEN**
- Capability: **NO_SIGNAL**, as preregistered
- Production default: unchanged

The original status-less Berlin row no longer becomes a
`VerifiedFactHit` and no longer creates a `verified_store_v0_readonly`
grounded context. Explicit `verified` and legacy `accepted` rows still retain
their fact text and source reference.

This is not a general truth-verification or capability-lift result. The
repository-local store selected by the default live resolver still has zero
answer-readable rows and has no public runtime writer. Synthetic rows were
used only to close the mechanism boundary.

## Narrow fix

Changed `packages/cgsr/cgsr/verified_fact_retrieval.py::_is_verified()` to:

- require at least one explicit status field
- accept only exact string states `verified` or `accepted`
- reject null, empty, unknown, negative, pending, and quarantined states
- reject malformed `verification` containers
- reject any row whose concurrently supplied status fields include a
  non-positive state

Final source SHA-256:
`a14adc4bcac7c7378d53f8e4aaf7ed93fbd23c756140eb1ee5044c05622568c6`.

The post-fix change-aware bypass additions cover malformed verification
containers, non-string flat status, a negative third status, and multiple
consistent positive statuses.

## Ordered verification

### Security closure and legitimate controls

```text
python -m pytest packages/cgsr/tests/test_verified_fact_status_authority_boundary.py -q
```

Result: `20 passed`.

The original adversarial selector changed from baseline
`8 failed, 4 passed, 3 deselected` to:

```text
python -m pytest packages/cgsr/tests/test_verified_fact_status_authority_boundary.py -q -k "missing_malformed_or_conflicting_status or rejected_row"
```

Result: `12 passed, 8 deselected`.

The legitimate-control selector produced:

```text
python -m pytest packages/cgsr/tests/test_verified_fact_status_authority_boundary.py -q -k "explicit_positive_status or legitimate_source_receipt"
```

Result: `4 passed, 16 deselected`. The fourth pass is the post-fix
multiple-consistent-positive-status bypass control; the two frozen direct
controls and frozen downstream receipt control all pass.

### Owning package and live-path checks

```text
python -m pytest packages/cgsr/tests/test_verified_fact_retrieval.py packages/cgsr/tests/test_conversation_grounding.py packages/cgsr/tests/test_conversation_honesty.py -q
```

Result: `24 passed`.

```text
python -m pytest packages/cgsr/tests/test_visual_imagination_planner.py -q
```

Result: `15 passed`.

```text
python -m pytest packages/cgsr/tests -q
```

Result: `359 passed`, 103 existing deprecation warnings.

Four focused API tests covering verified-store conversation use and resolver
selection produced `4 passed`:

```text
python -m pytest apps/api/tests/test_dual_brain_api.py::test_chat_conversation_uses_readonly_verified_store_for_grounded_visual_scene apps/api/tests/test_dual_brain_api.py::test_dashboard_conversation_returns_verified_speech_timeline_for_motion_scene apps/api/tests/test_dual_brain_api.py::test_verified_store_runtime_discovers_sibling_primary_store apps/api/tests/test_dual_brain_api.py::test_verified_store_runtime_falls_back_when_configured_path_is_missing -q
```

The broader exploratory API selector
`-k "verified_store or conversation"` produced `8 failed, 6 passed,
36 deselected`. Its failures were answer-kind/surface/SPLATRA/web-behavior
assertions outside `_is_verified()`. The one failed test whose name mentions a
verified store,
`test_korean_dashboard_conversation_returns_splatra_scene_plan_from_verified_store`,
was rerun in a detached temporary worktree at the sealed preregistration commit
and failed identically (`KeyError: splatra_scene_plan`). It is therefore a
pre-existing API failure rather than a #7 regression. The temporary worktree
was removed after comparison.

### Buildability and compatibility evidence

`compileall` passed for the changed source and test. `ruff` was unavailable in
the environment (`No module named ruff`). `git diff --check` passed.

A read-only audit of the populated sibling store found all 57,737 rows carry an
explicit nested `status="verified"`:

- evidence: 8,364 / 8,364
- relations: 33,032 / 33,032
- concepts: 8,060 / 8,060
- case frames: 8,281 / 8,281

Thus the fail-closed change does not reject the existing populated store's
normal rows.

No staging graph, verified store, sibling store, or production flag was
modified. Nothing was staged, committed, or pushed by this implementation
step.

## Remaining boundary

This fix does not authenticate whoever writes an explicit `verified` or
`accepted` value. The current default live store has no public runtime writer,
so that broader producer-authority question is outside this item. It must not
be inferred as solved from this mechanism GREEN.
