# Signed Promotion Manifest Gate

`packages/promotion_manifest` creates deterministic, content-addressed,
review-backed promotion manifest records.

This package does not perform promotion.

- no production `verified_store_v0` mutation
- no candidate store mutation
- no Local Brain write
- no external LLM call
- no real P2P
- no generated code execution
- no real cryptographic signing
- `ready_for_real_promotion=false`
- `apply_enabled=false`

The proof signer is a deterministic placeholder:

`proof-signature:<canonical_hash>`

It exists only to test manifest plumbing. A future real promotion path still
needs real cryptographic signatures, rollback, backup, dry-run apply, conflict
review, and operator confirmation gates.
