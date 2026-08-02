# ATANOR Promotion Human Review Flow

## Purpose

Promotion Human Review Flow turns Candidate Promotion Gate dry-run output into
human review metadata. It lets a reviewer record decisions such as approve,
reject, defer, needs-more-evidence, and conflict-review without applying those
decisions to production.

This is not real promotion.

## Review Sessions

A review session records:

- source candidate run id
- dry-run report id
- verified store hash before review
- candidate store hash
- review items
- reviewer decisions
- safety invariants

Review sessions are metadata only. They must not modify `verified_store_v0`,
candidate stores, Local Brain, or runtime learning state.

## Decisions

Supported decisions:

- `approve_for_future_manifest`
- `reject`
- `defer`
- `needs_more_evidence`
- `conflict_review`

These decisions are records. They are not production actions.

## Deterministic Recommendations

The review policy can recommend:

- no source: reject
- conflict: conflict review
- low quality: needs more evidence
- generic predicate: defer
- high quality and source grounded: approve for future manifest

Recommendations do not decide automatically.

## Manifest Drafts

`PromotionManifestDraft` groups approved, rejected, and deferred item ids from a
review session. In this slice it is unsigned and always has:

- `signed=false`
- `ready_for_real_promotion=false`
- `actual_promotion_performed=false`
- `production_store_mutated=false`

A future signed manifest gate is required before real promotion can even be
considered.

## Relationship To Selfhood Runtime

Selfhood Runtime may propose a promotion review. It must still wait for explicit
user approval. It cannot apply review decisions, promote candidates, or mutate
production memory.

## Relationship To Logical Sphere

Logical Sphere should continue to separate verified counts, candidate counts,
and rendered counts. Human review records do not change verified counts.

## Future UI/API

This slice includes a standalone static `PromotionReviewPanel` component only.
Future live integration may add read-only review APIs and an action backend for
recording decisions, but that backend must still write review metadata only and
must not promote candidates.
