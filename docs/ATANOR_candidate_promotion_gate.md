# ATANOR Candidate Promotion Gate

Status: dry-run-only safety gate.

Candidate Promotion Gate reviews candidate Cloud Brain stores and estimates
what a future promotion would do. It does not mutate `verified_store_v0`, write
Local Brain, promote candidates, or bypass manual approval.

## Dry-Run Checks

1. Load candidate store metadata and JSONL rows.
2. Compare candidate dedupe keys against `verified_store_v0`.
3. Estimate new concepts and merged existing concepts.
4. Estimate new and strengthened relations.
5. Validate provenance, source id, license, usage permission, and verification.
6. Detect conflicting candidate values under the same dedupe key.
7. Check evidence keys.
8. Check relation endpoints and relation type.
9. Check case-frame predicate and role structure.
10. Produce a manual-review report.

## Non-Negotiable Flags

- `actual_promotion_enabled=false`
- `production_store_mutated=false`
- `local_brain_write=false`
- `candidate_promotion=false`
- `external_llm_used=false`
- `mock_growth=false`

## Required Future Gates

- Human promotion review.
- Privacy review.
- Provenance/license review.
- Conflict review.
- Signed candidate report.
- Rollback plan before any real production mutation.

This gate is intentionally conservative. Generic predicates, weak case-role
structures, missing provenance, unclear license, and conflicts are blocked or
sent to review rather than promoted.
