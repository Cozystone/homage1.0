# Pattern #19 — Remote contribution acceptance by omission

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — this corrects pending-credit accounting and
  does not establish contribution quality or settlement capability.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#19`, `contribution_service`, `pending credit`, `accepted=True`, and
`credit confirmation` found no prior RED/WIP remediation. The existing stash
does not contain the target path. Path history contains the original
graph-native contribution feature and unrelated text cleanup only.

## Revalidated path and invariant

For a remote broker, `ContributionService.submit_task_result()` evaluated:

`bool(remote_payload.get("accepted", True))`

If the remote response omitted `accepted`, the local service therefore treated
the submission as accepted, incremented completed-task and pending-credit
counters, created a pending `ContributionCredit`, and entered
`verification_pending`.

This path does not confirm or settle credit: `amount_confirmed` remains `0.0`
and confirmed-credit totals remain zero. The invariant for this finding is
therefore narrow: omission must not create even pending acceptance. Only an
explicit literal `accepted: true` may create the pending record.

## Pre-fix reproduction

`python -m pytest -q apps/api/tests/test_cloud_broker_remote.py::test_remote_omission_cannot_default_to_accepted_pending_credit apps/api/tests/test_cloud_broker_remote.py::test_contribution_service_can_use_remote_broker`

Result before fix: `1 failed, 1 passed`. The omission case produced
`pending_credits=1.0`; the explicit legitimate `accepted: true` control
continued to produce a pending record with zero confirmed credit.

## Minimal fix

- Remote acceptance is now
  `remote_payload.get("accepted") is True`.
- Missing, false, null, numeric, or string-like truthy values fail closed.
- The explicit legitimate remote acceptance behavior is unchanged.
- Credit confirmation, settlement, remote broker authentication, and payout
  logic were not added or changed.

Changed files:

- `apps/api/app/services/contribution_service.py`
- `apps/api/tests/test_cloud_broker_remote.py`
- `docs/ATANOR_PATTERN_19_REMOTE_ACCEPTANCE_OMISSION_RESULT_2026-07-28.md`

## Verification

- Omission adversarial case plus explicit legitimate acceptance control:
  `python -m pytest -q apps/api/tests/test_cloud_broker_remote.py::test_remote_omission_cannot_default_to_accepted_pending_credit apps/api/tests/test_cloud_broker_remote.py::test_contribution_service_can_use_remote_broker`
  — `2 passed`.
- Remote broker and contribution API regressions:
  `python -m pytest -q apps/api/tests/test_cloud_broker_remote.py apps/api/tests/test_contribution_api.py`
  — `13 passed`.
- Syntax/buildability and focused diff hygiene are checked before handoff.

The omission control now records the remote response for diagnostics but
creates no credit, leaves both pending and confirmed totals at zero, and
increments the rejected-task counter. The explicit `accepted: true` control
still creates exactly a pending internal accounting record and leaves
confirmed credit at zero.

## Remaining boundary

This closes only omission-as-acceptance in the local pending-credit surface.
The remote broker response is not independently cryptographically attested in
this slice, and no claim is made that pending credit is verified economic
value. Confirmation and settlement remain absent and out of scope.
