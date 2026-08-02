# Pattern #17 — Caller-attested Agentic Review identity and scope

## Outcome

- Outcome: `partial / deferred`
- Mechanism: `PARTIAL GREEN` — forged caller metadata cannot authorize or
  widen a review decision, but no production HTTP path currently issues the
  session-bound delegation required for a legitimate decision.
- Capability: `NOT_MEASURED` — this authenticates a queue decision; it does not
  establish promotion quality or production capability.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#17`, `agentic_micro_os`, `reviewer`, `approved_for`, and `review decision`
found no prior RED/WIP remediation. The existing stash does not contain the
target path. Earlier commits created and later constrained the queue and
autonomous paths, but did not bind this review endpoint to operator authority.

## Revalidated path and downstream reach

`POST /api/agentic-os/review/decide` accepted `reviewer` and `approved_for`
directly from its public request body and persisted both in `ReviewDecision`.
It also changed the associated `ReviewItem.status` to `approved`.

That status is not a production mutation, but it is consumed by
`CandidatePromotionGate` as one eligibility condition for a later candidate
staging decision. The current promotion route remains staging-only and reports
`production_store_mutated=false`; no production or promotion implementation
was expanded here.

The invariant is: caller strings may not identify the reviewer or widen the
scope of a review decision. The reviewer must come from an independently
verified, server-held operator session and session-bound delegation. This
queue endpoint carries only `review_draft_write`, so its recorded scope is
always `draft_only`.

## Existing authority primitive and live-wiring limit

No new token institution was added. The router already owns the singleton
`PermissionGate`, whose `verify_bound_operator_action()` requires:

- an active server-held full-host operator session;
- a bearer delegation minted during and bound to that exact session and
  operator;
- the requested `review_draft_write` scope;
- unexpired state, no emergency stop, and the existing audit/counter checks.

The Surface Brain review API already uses this exact primitive and header
contract. Pattern #17 reuses it rather than treating sanitized caller metadata
as authority.

That primitive is currently usable only through an in-process issuance path.
The positive control calls `gate_for_test().enable_full_host()` and
`issue_signed_delegation()` directly; it does not prove that a production
caller can obtain review authority. The live
`POST /api/agentic-os/permission/full-host/enable` route is intentionally
fail-closed with `signed_operator_run_lease_required`, and no non-test caller
of `issue_signed_delegation()` provides an alternate live issuance path.

The existing AUT-0 `RunLease` is not an unambiguous replacement. Its live
binding is purpose-specific to `AGENTIC_POLICY_DAEMON_RUNNER_ID` and the
agentic scheduler action classes. Its contract also says that an activation
result is an audit value, not a bearer capability. Reusing it as a human
reviewer delegation would widen policy rather than connect an already-defined
review action, so that work is deferred pending a separately approved,
purpose-specific authority design.

## Pre-fix reproduction

`python -m pytest -q apps/api/tests/test_agentic_review_authority_boundary.py`

The initial preregistered boundary probe failed `2` tests before the fix. A
caller claiming `reviewer=root_operator` and
`approved_for=promotion_request` received `allowed=true`, changed the item to
`approved`, and persisted both unverified strings. The control path had no
independent authority receipt.

## Minimal fix

- `/review/decide` now requires
  `X-Atanor-Operator-Delegation` through the existing process-owned
  `PermissionGate`.
- Missing, forged, stale, wrong-session, or wrong-scope delegations fail with
  HTTP 403 before queue mutation.
- Persisted `reviewer` comes only from the bound server session's operator
  identity; the request body's `reviewer` field is non-authoritative.
- Persisted `approved_for` is forced to `draft_only`, the maximum scope of
  `review_draft_write`; the request body's value is non-authoritative.
- Runtime event type is based on the queue's actual safe decision rather than
  the caller-requested decision.
- The live full-host route remains fail-closed; this change does not create a
  production issuance path for review authority.
- No production merge, candidate promotion, or new authentication mechanism
  was added.

Changed files:

- `apps/api/app/routers/agentic_micro_os.py`
- `apps/api/tests/test_agentic_review_authority_boundary.py`
- `apps/api/tests/test_agentic_review_queue_api.py`
- `docs/ATANOR_PATTERN_17_REVIEW_OPERATOR_BINDING_RESULT_2026-07-28.md`

## Verification

- Forged-token adversarial test, test-internal bound-operator control, and
  production-surface fail-closed control:
  `python -m pytest -q apps/api/tests/test_agentic_review_authority_boundary.py`
  — `3 passed`.
- Review queue, permission boundary, and existing Surface Brain consumer
  regressions:
  `python -m pytest -q apps/api/tests/test_agentic_review_queue_api.py apps/api/tests/test_agentic_permission_gate_api.py apps/api/tests/test_surface_brain_operator_boundary.py packages/agentic_micro_os/tests/test_permission_gate.py`
  — `30 passed`.
- Syntax/buildability and focused diff hygiene are checked before handoff.

The adversarial control keeps a test-internal active session but supplies a
forged delegation and forged body metadata. It receives 403, leaves the item
pending, and persists no decision or forged strings. The in-process positive
control supplies a real session-bound `review_draft_write` delegation while
still putting forged metadata in the body; the stored reviewer is the
server-bound operator and the stored scope is `draft_only`. A separate live
surface control proves that `/permission/full-host/enable` issues neither a
session nor a delegation and that `/review/decide` consequently remains
fail-closed.

## Remaining boundary

Caller strings no longer mint or widen a queue/status review decision. An
approved item can be considered by the separate candidate-staging gate, but
that gate remains non-production and outside this finding. However, the live
review endpoint is effectively disabled for legitimate production callers
because no live review-delegation issuance path exists. Full mechanism GREEN
therefore requires a separately approved purpose-specific signed review
action, or an equally narrow operator boundary, without weakening the current
fail-closed behavior. Production promotion still requires its own
independently verified authority and was not touched.
