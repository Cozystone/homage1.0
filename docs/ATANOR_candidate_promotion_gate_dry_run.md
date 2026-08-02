# ATANOR Candidate Promotion Gate Dry-run

## Purpose

Candidate Promotion Gate is a read-only review step for Cloud Brain candidate
overlays. It estimates what a future human-approved promotion could add to
`verified_store_v0`, but it does not perform promotion and does not mutate
production data.

This gate exists because candidate learning runs are intentionally separated
from verified production knowledge. A candidate store can be internally
consistent while still requiring provenance, dedupe, conflict, evidence, and
human review before any item becomes verified Cloud Brain knowledge.

## Input Sources

The dry-run review compares two read-only inputs:

- Production verified store: `data/cloud_brain/verified_store_v0`
- Candidate overlay store: `data/cloud_brain/candidate_runs/<run_id>`

The loader accepts summary fields for concepts, relations, evidence, case
frames, store manifest hashes, source run identity, and source run status. A
user-stopped partial candidate run may be reviewed, but it must be reported as
partial rather than treated as a full 24-hour pass.

## Dry-run Only Invariants

The integration must preserve these invariants:

- `actual_promotion_performed=false`
- `production_store_mutated=false`
- `local_brain_write=false`
- `candidate_promotion=false`
- `dry_run_only=true`
- `external_llm_used=false`
- `real_p2p_used=false`
- `generated_code_executed=false`

Generated reports under `data/audits/promotion_gate/` are audit artifacts and
must not be committed.

## Policy

The default policy is intentionally conservative:

- provenance is required
- source identity is required
- license and usage permission are required
- low-confidence or rejected verification status is rejected
- conflicts are rejected
- manual approval is required
- actual promotion remains disabled

The dry-run may estimate:

- new concepts that could be created
- existing concepts that could be merged
- new relations that could be created
- existing relations that could be strengthened
- evidence that could be added
- case frames that could be created
- duplicates, no-source items, conflicts, low-quality items, and manual-review
  items

## Relation to Logical Sphere

Logical Sphere counts have two different meanings before and after a future
real promotion:

- Before promotion, verified counts remain unchanged because they come from
  production `verified_store_v0`.
- Candidate counts remain unpromoted learning output.
- A promotion dry-run gives only a possible verified delta.
- After a future real promotion, verified counts may increase and candidate
  items may be marked reviewed, promoted, or rejected.

This implementation does not add a UI panel or API endpoint. Any future UI
should label dry-run estimates as potential deltas, not as verified production
knowledge.

## Future Real Promotion Gates

Real promotion is out of scope until the following gates exist:

- signed promotion manifest
- provenance review
- dedupe review
- conflict detection review
- evidence threshold review
- privacy review
- human approval
- production hash pre/post audit
- candidate reviewed/promoted/rejected marking

Until those gates exist, Candidate Promotion Gate remains a dry-run review
tool only.
