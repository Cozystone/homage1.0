# Pattern #10 — Cloudflare broker caller identity and freshness

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — no live multi-peer quality or throughput claim is made.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#10`, `cloud-brain-broker`, `caller hash`, `freshness`, `missing key`, and
`fail-open` found no prior RED/WIP remediation. The sole stash does not contain
the Cloudflare Worker. The Worker has only its original platform-layer history.

## Revalidated paths and invariant

Three failures reproduced at the real Worker `fetch` boundary:

1. With `ATANOR_BROKER_API_KEY` absent, every mutating route was authorized.
2. Registration accepted a caller-supplied `peer_id_hash` that disagreed with
   `node_id`/`node_public_id`.
3. Heartbeat created an unknown peer and assigned server-current `last_seen`,
   allowing an unregistered caller to manufacture active-peer freshness.

The invariant is: public status/network reads may remain anonymous, but broker
mutation requires a configured matching broker key; peer hashes are derived
from the declared public node identity; and only a registered identity may
refresh peer state. Legitimate registered clients must continue to register,
heartbeat, poll, and submit through the same payload contract.

## Pre-fix reproduction

`node --test infra/cloudflare/cloud-brain-broker/src/worker.test.mjs`

Result before fix: `0 passed, 3 failed`. Missing-key mutation, mismatched hash,
and unregistered freshness all returned HTTP 200 instead of the preregistered
401/422 rejection.

## Minimal fix

- `isAuthorized` now leaves only `GET /cloud/status` and
  `GET /cloud/network` public and fails closed for every other route when the
  Worker secret is absent.
- One server-side identity primitive derives
  `sha256("peer:" + node_public_id)` and rejects a disagreeing caller hash.
- Heartbeat requires a matching registered peer before updating `last_seen`.
- Task poll and submit reuse the same identity/registration boundary so the
  immediate alternate task routes cannot bypass it.
- Deployment documentation now marks the broker key as required for mutation.

Changed files:

- `infra/cloudflare/cloud-brain-broker/src/worker.ts`
- `infra/cloudflare/cloud-brain-broker/src/worker.test.mjs`
- `infra/cloudflare/cloud-brain-broker/README.md`
- `docs/ATANOR_PATTERN_10_CLOUD_BROKER_IDENTITY_RESULT_2026-07-28.md`

## Verification

- Security closure and legitimate control:
  `node --test infra/cloudflare/cloud-brain-broker/src/worker.test.mjs`
  → `3 passed`.
- Owning client compatibility:
  `python -m pytest -q apps/api/tests/test_cloud_broker_remote.py apps/api/tests/test_contribution_api.py`
  → `12 passed`.
- Runtime syntax:
  `node --check infra/cloudflare/cloud-brain-broker/src/worker.ts`
  → passed.
- Patch hygiene: `git diff --check` on the four Pattern #10 files → passed.

An ad-hoc standalone `tsc` invocation is not a repository-supported package
check: this directory has no TypeScript project or Workers type declarations.
It reports the pre-existing missing `KVNamespace`, `R2Bucket`, `D1Database`, and
`Queue` globals plus existing inferred-property errors. The real source was
instead imported and exercised by Node's TypeScript runtime in all adversarial
and legitimate controls.

The original issues no longer reproduce: missing-key mutation is 401 with no KV
write; a mismatched caller hash is 422 with no peer row; and a correctly hashed
but unregistered heartbeat is 422 with no freshness row. A correctly hashed,
registered caller still receives 200 and updates its server-generated
`last_seen`.

## Remaining boundary

This alpha broker still uses one shared broker secret, not per-peer signatures.
The fix proves server-side identity consistency and registration/freshness
binding; it does not claim cryptographic ownership of a public node identifier
or complete multi-peer verification. Those are explicit platform limitations,
not silently upgraded claims.

## Adjacent fragment-route closure

A cumulative route review found that the original GREEN was incomplete.
`POST /cloud/fragments/put` and `POST /cloud/fragments/submit` still selected
`created_by_peer_hash`/`peer_id_hash` directly from the request and preserved a
caller-provided `verification_state`. A caller holding the shared broker key
could therefore write as an unregistered or conflicting peer and could persist
`multi_peer_verified` without any multi-peer verification.

The follow-up tests were fixed before the implementation changed:

- an unregistered node with its own syntactically correct peer hash must be
  rejected without a fragment write;
- a registered node whose `created_by_peer_hash` conflicts with its derived
  identity must be rejected without a fragment write;
- a correctly registered node remains able to use both fragment POST routes,
  but a submitted `multi_peer_verified` value must be stored and returned as
  server-owned `single_peer_pending` with `requires_cross_check=true`.

Pre-fix:

`node --test infra/cloudflare/cloud-brain-broker/src/worker.test.mjs`

Result: `3 passed, 3 failed`. Both forged-peer cases returned HTTP 200, and the
legitimate control retained the injected `multi_peer_verified` state.

The two routes now reuse the same derived peer identity and registered-peer
lookup as heartbeat/task submission. `peer_id_hash`,
`created_by_peer_hash`, and `submitted_by_peer_hash`, when present, must all
match `sha256("peer:" + node_public_id)`. Fragment identity may use the
existing public-fragment `provenance.source_peer_id` field for compatibility,
but it must resolve to a registered peer. `storeFragment` overwrites every
caller verification-state proposal with `single_peer_pending` before hashing
and persistence.

Post-fix:

- Worker adversarial and legitimate controls: `6 passed`.
- Owning client/contribution compatibility:
  `python -m pytest -q apps/api/tests/test_cloud_broker_remote.py apps/api/tests/test_contribution_api.py`
  returned `13 passed`.
- Runtime syntax: `node --check infra/cloudflare/cloud-brain-broker/src/worker.ts`
  passed.

Mechanism is `GREEN`; capability remains `NOT_MEASURED`. Production/default
activation was not changed.

This closes independent hash/status self-attestation within the current
registered-identity contract. It still does not prove that a holder of the one
shared broker secret cryptographically owns a declared node identifier. A
per-peer signature or separately bound credential remains necessary for that
stronger claim, so this result must not be described as cryptographic
cross-contributor impersonation resistance.
