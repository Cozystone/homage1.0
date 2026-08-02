# ATANOR Signed Promotion Manifest Gate

Status: proof-only, non-applying.

The Signed Promotion Manifest Gate is the next safety layer after candidate
promotion dry-run and human review. It turns reviewed candidate decisions into a
deterministic, content-addressed manifest draft without mutating any production
store.

## Flow

1. Candidate promotion dry-run reports possible effects.
2. Human review marks items as approved, rejected, deferred, conflict review, or
   needs more evidence.
3. The manifest gate builds a canonical manifest draft from the review session.
4. A proof-only signer attaches `proof-signature:<canonical_hash>`.
5. The manifest remains non-applying and not ready for real promotion.

## Canonical Hashing

Manifest hashing uses deterministic JSON canonicalization with stable key order,
normalized whitespace, stable item ordering, and excluded signature/timestamp
fields. The content-addressed manifest id is:

`promotion-manifest:<short_hash>`

The hash binds the review session id, candidate run id, store hashes, counts, and
reviewed item records.

## Proof-Only Signing

The current signature is not cryptographic signing. It does not use private
keys, wallets, DID networks, Web3, P2P, or production credentials. It exists only
to test manifest plumbing:

`proof-signature:<canonical_hash>`

Proof signing never enables apply.

## Required Future Gates

Real promotion remains blocked until a later implementation provides all of
these gates:

- real cryptographic signature verification
- complete human review
- complete conflict review
- rollback plan
- production apply dry-run
- backup snapshot
- operator confirmation

Until then:

- `ready_for_real_promotion=false`
- `apply_enabled=false`
- `production_store_mutated=false`
- `local_brain_write=false`
- `candidate_store_mutated=false`

## Logical Sphere Relation

Logical Sphere counts may use reviewed candidate and manifest metadata for
read-only diagnostics. A manifest draft does not change logical counts in
production, does not send candidate-pair edges, and does not promote candidate
content into `verified_store_v0`.

## Selfhood Runtime Relation

Selfhood Runtime may propose that a reviewed candidate batch should prepare a
signed promotion manifest draft. It cannot sign real manifests, apply manifests,
mutate stores, execute generated code, or perform hot-swap. Any runtime proposal
must remain a proposal-only patch requiring review.
