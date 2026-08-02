# Pattern #7 preregistration: verified-fact status must fail closed

Status: frozen before production implementation.

Budget owner: Track A (`#5`, `#9`, `#7`), 44 hours total / 22-hour
checkpoint / 44-hour hard cap.

Candidate baseline:

- Git commit: `bc5cccde42080a784f490ebbb53414cf7ec45131`
- `packages/cgsr/cgsr/verified_fact_retrieval.py` SHA-256:
  `60db9cd6b34b7c5ce173c9bafcb2ab6fbb86cca3a37d8775bad6cd034d343e57`
- The repository-local live resolver's first existing store is
  `data/cloud_brain/verified_store_v0`.
- At freeze time its four answer-readable JSONL files contain 0 rows:
  concepts 0, relations 0, evidence 0, case frames 0.
- The populated sibling store is not selected because the repository-local
  empty store exists first in `_verified_store_candidates()`.

## Broken boundary

`retrieve_verified_facts()` reads JSONL rows and `_is_verified()` currently
defaults an absent status to `"verified"`. A malformed row can therefore become
a `VerifiedFactHit`, then a `verified_store_v0_readonly` grounded context and a
live answer, without any explicit accepted/verified state.

The narrow invariant for this item is:

> A row is answer-authoritative only when every status field it actually
> supplies is a recognized positive state (`verified` or legacy `accepted`),
> at least one such field is explicitly present, and no supplied status is
> missing, malformed, negative, pending, quarantined, or conflicting.

This item does not establish that a writer is entitled to assert `verified`.
The default store has no public runtime writer; producer authentication and
promotion authority are separate boundaries.

## Frozen mechanism cohort and gates

The executable cohort is
`packages/cgsr/tests/test_verified_fact_status_authority_boundary.py`.
All cases cross the real `retrieve_verified_facts()` boundary.

Legitimate controls:

1. nested `verification.status="verified"`
2. top-level legacy `status="accepted"`

Malformed/forged controls:

1. no status field
2. empty `verification` object
3. top-level `status=null`
4. top-level `status=""`
5. nested `verification.status=null`
6. nested `verification.status=""`
7. explicit `pending`
8. explicit `rejected`
9. explicit `quarantined`
10. explicit unknown `VERIFIED`
11. top-level `accepted` conflicting with nested `rejected`

Mechanism GREEN requires all of the following simultaneously:

- forged/malformed authority promotions: exactly `0/11`
- legitimate accepted rows retrieved: exactly `2/2`
- legitimate accept regression: exactly `0/2`
- a rejected row yields no facts, no source refs, `grounding_source="none"`,
  and `grounding_quality="none"` downstream
- a legitimate row preserves its fact and exact source reference downstream,
  with `grounding_source="verified_store_v0_readonly"`

Any failure is RED. Partial GREEN is reported as partial only.

## Frozen capability accounting

Synthetic rows above prove the mechanism only. They must not be counted as a
general capability lift.

For #7's real-live arm, the fixed cohort is the answer-readable content of the
repository-local store selected by the default resolver at freeze time.
Its denominator is 0. Therefore:

- false assertions: `N/A (0 eligible rows)`
- wrong-source adoptions: `N/A (0 eligible rows)`
- answer accuracy: `N/A (0 eligible rows)`
- abstentions: `N/A (0 eligible rows)`

The preregistered #7 capability verdict is consequently `NO_SIGNAL`, even if
the mechanism becomes GREEN. A later non-empty live store or an
`ATANOR_VERIFIED_STORE_PATH` override requires a new preregistration before
OFF/ON measurement. Results from the populated sibling store or injected
fixtures cannot be substituted after seeing results.

Regression is declared immediately if explicit accepted/verified controls lose
any acceptance, fact text, or source-reference fidelity. `CAPABILITY_LIFT`
cannot be declared for #7 under this frozen zero-denominator live cohort.

No production default, staging graph, verified store, or sibling store is
modified by this preregistration.
