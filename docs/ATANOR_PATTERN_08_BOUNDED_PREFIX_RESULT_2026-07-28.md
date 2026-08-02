# Pattern #8 — bounded-prefix verification / full persistence

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — this result proves the submission boundary, not a live answer-quality lift.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#8`, `brain_link`, `bounded prefix`, and `persist all` found no prior RED/WIP
remediation of this finding. The only stash (`resonance-wip`) does not contain
`brain_link.py`. Existing Brain Link commits establish the feature history, not
an earlier closure attempt.

## Revalidated path and invariant

`apps/api/app/routers/brain_link.py::work_submit` accepted caller-controlled
`decompositions`, `_verify_submission` inspected only `decomps[:5]`, and
`_accumulate_decompositions(decomps)` persisted the entire list.

The invariant is: every decomposition reaching the contributed store must have
evidence membership checked against the coordinator-held claimed batch. A
legitimate batch with more than five valid decompositions must remain accepted.

## Pre-fix reproduction

The focused API-boundary fixture submitted five batch-bound decompositions
followed by a sixth forged decomposition. Before the patch, the request returned
`ok=True` and the capture sink received all six entries:

`python -m pytest -q apps/api/tests/test_brain_link_submission_trust_boundary.py`

Result before fix: `1 failed, 1 passed`; the forged-prefix test failed because
the forged sixth entry was accepted.

## Minimal fix

The verifier now iterates over the full list that the sink will persist. No
request schema, persistence API, economy behavior, or adjacent peer-trust
policy changed.

Changed files:

- `apps/api/app/routers/brain_link.py`
- `apps/api/tests/test_brain_link_submission_trust_boundary.py`
- `docs/ATANOR_PATTERN_08_BOUNDED_PREFIX_RESULT_2026-07-28.md`

## Verification

- Security closure and legitimate control:
  `python -m pytest -q apps/api/tests/test_brain_link_submission_trust_boundary.py apps/api/tests/test_brain_link_merge.py`
  → `6 passed`.
- Syntax/import buildability:
  `python -m compileall -q apps/api/app/routers/brain_link.py apps/api/tests/test_brain_link_submission_trust_boundary.py`
  → passed.
- Patch hygiene:
  `git diff --check -- apps/api/app/routers/brain_link.py apps/api/tests/test_brain_link_submission_trust_boundary.py`
  → passed (Git reported only the repository's existing CRLF normalization warning).

The original forged-suffix path no longer reproduces: the response is
`verification_failed`, reports `checked=6, matched=5`, and the persistence sink
is untouched. The legitimate six-decomposition control remains accepted and
all six entries reach the capture sink.

## Remaining boundary

This patch proves claimed-batch evidence membership only. It does not claim
semantic truth of caller-produced concepts/relations or complete multi-peer
verification, both of which remain outside Pattern #8 and are documented
platform limitations.
