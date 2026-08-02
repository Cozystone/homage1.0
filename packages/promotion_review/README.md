# Promotion Human Review Flow

`packages/promotion_review` stores human review metadata for Candidate Promotion
Gate dry-run outputs.

It is review-only:

- no production `verified_store_v0` mutation
- no candidate store mutation
- no Local Brain write
- no actual promotion
- no external LLM call
- no real P2P
- no generated code execution

Review sessions record candidate items, user/system recommendations, decisions,
and unsigned manifest drafts. A manifest draft is not a real promotion manifest
and is never marked ready for production in this package.
