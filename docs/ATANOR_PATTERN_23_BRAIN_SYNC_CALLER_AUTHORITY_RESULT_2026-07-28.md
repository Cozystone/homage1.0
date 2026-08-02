# Pattern #23 — Brain-sync raw caller authority

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `N/A` — no primary answer consumer uses this diagnostic
  working-memory/conflict surface
- Production defaults: unchanged; no feature was enabled and no answer path was
  promoted

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#23`, `brain sync`, `raw attach`, and `conflict resolution` found no prior
RED/WIP remediation. `refs/stash` contains neither target file. Path history
contains only the original graph-native platform implementation
(`aa71e6fb`).

## Revalidated vulnerable paths

Two public source-to-sink paths trusted values that the same caller supplied:

1. `POST /api/brain-sync/fragment/attach` accepted an arbitrary dictionary.
   `WorkingMemoryFragmentStore.attach()` spread the dictionary directly into
   the stored record, preserving caller-selected `verification_status`,
   `trust_score`, `priority`, `expires_at`, provenance flags, schema, and
   checksum.
2. `POST /api/brain-sync/conflict/resolve` passed two arbitrary dictionaries
   to `resolve_conflict()`. The resolver mapped their caller-selected
   `priority` strings directly to an authoritative winner; a missing local
   priority even defaulted to `local_verified`.

The neighboring public assemble route also accepted caller trust, origin, and
unbounded TTL metadata. None of these values had an independent server-bound
provenance provider.

The invariant is:

- a public fragment must have the canonical schema and a valid canonical
  checksum before any recursive processing;
- checksum proves integrity only, never verification or source authority;
- public ingress is reconstructed as `public`, `unverified`,
  `cloud_unverified`, `trust_score=0`, `authority=none`, and
  `server_bound_provenance=false`;
- expiry and structural/byte limits come from server `FragmentLimits`;
- raw conflict dictionaries cannot select an authoritative winner.

## Preregistered failures

Before the implementation change:

`python -m pytest -q apps/api/tests/test_brain_sync.py -k "raw_attach or conflict_resolution or legitimate_canonical"`

Result: `4 failed, 6 deselected`.

- caller priority selected `winner=local`;
- the store had no server limits and preserved raw attachment fields;
- a canonical store control could not use a bounded store instance;
- an explicit foreign schema was accepted.

The checksum/size hardening was also encoded before its implementation:

`python -m pytest -q apps/api/tests/test_brain_sync.py -k "invalid_caller_checksum or oversized_canonical_input"`

Result: `2 failed, 10 deselected`. An invalid checksum returned HTTP 200 and
oversized canonical input was accepted.

A change-aware bypass test then showed that nested
`evidence_summaries[].verification_status/priority` survived the first draft;
it failed once before the recursive authority-field sanitizer was applied.

## Minimal fix

- Canonical fragment checksum calculation now has an explicit scope and is
  verified with constant-time comparison.
- Attach requires the canonical schema and a present, valid checksum.
- Known list/dict shapes, node/edge counts, and inbound canonical bytes are
  checked before recursive sanitization. The final reconstructed fragment is
  checked against `max_bytes` again.
- Valid self-computed checksums may preserve a non-colliding correlation
  `fragment_id`, but cannot preserve or confer authority.
- Attach reconstructs only allowed fragment content with a new server
  timestamp/checksum, server-capped TTL, forced public origin, zero trust, and
  explicit unverified/no-authority fields.
- Authority-like keys are removed recursively from source metadata and
  evidence summaries.
- The public assemble route ignores caller trust/origin, caps TTL, and emits
  the same unverified contract.
- Raw conflict resolution now returns no winner, no selected record, priority
  zero on both sides, and `reason=no_server_bound_provenance`.
- The API maps invalid fragment input to HTTP 422 instead of attaching it.

Changed files:

- `apps/api/app/routers/brain_sync.py`
- `apps/api/app/services/brain_sync.py`
- `apps/api/tests/test_brain_sync.py`
- `docs/ATANOR_PATTERN_23_BRAIN_SYNC_CALLER_AUTHORITY_RESULT_2026-07-28.md`

## Verification

Applicability/buildability:

- `python -m compileall -q apps/api/app/routers/brain_sync.py apps/api/app/services/brain_sync.py apps/api/tests/test_brain_sync.py`
  — passed.
- `git diff --check` — passed for the candidate patch.

Security closure and legitimate behavior:

- `python -m pytest -q apps/api/tests/test_brain_sync.py`
  — `14 passed`.
- A syntactically valid, caller-self-computed checksum carrying
  `verified/local_private/trust=1`, a one-year expiry, private origin, and
  nested authority metadata is accepted only as a bounded unverified public
  fragment. Its authority fields are removed/forced, its checksum is
  reconstructed, and TTL is capped.
- Missing/invalid checksum, foreign schema, and oversized canonical input are
  rejected.
- A legitimate `BoundedFragmentAssembler` result still attaches to working
  memory, preserves its bounded graph content and source URL, keeps permanent
  local writes false, and has a valid reconstructed checksum.
- Caller-attested priority/provenance on both conflict arms returns no
  authoritative winner.

Neighbor regressions:

- `python -m pytest -q apps/api/tests/test_hybrid_network_manager.py apps/api/tests/test_cloud_broker_remote.py`
  — `21 passed`.

## Remaining boundary

There is still no server-bound provenance primitive for this raw conflict
API. Therefore it intentionally cannot produce an authoritative winner.
Adding a signed/operator-bound provenance provider would be a separate,
approval-gated design task. The canonical checksum remains integrity metadata
only and is explicitly labeled `checksum_authority=integrity_only`.
