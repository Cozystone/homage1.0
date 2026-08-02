# ATANOR Local Memory Approval Live UI

Status: review/API/UI slice, no real Local Brain write.

## Purpose

Local Memory Approval gives users a first product-facing review surface for proposed
Local Brain memories. It can classify candidate text, show deterministic policy
recommendations, record approve/reject/defer/edit/sensitive-block decisions, and
preview a manifest draft. The manifest remains non-applying.

## Status API

The review router provides a review-only status payload with these locked
invariants. The router is tested directly; app-level mounting is a separate,
tiny follow-up because this slice avoided mixed application shell files.

- `local_brain_write=false`
- `apply_enabled=false`
- `voice_raw_blocked=true`
- `text_input_supported=true`
- `voice_optional=true`
- `external_llm_used=false`

Review metadata is stored under `data/review/local_memory_approval/` by default.
Tests override this path with a temporary directory.

## Session Flow

`POST /api/local-memory-approval/session` accepts local text snippets and a source
type such as `user_text`, `project_fact`, `preference`, or `voice_transcript`.
Each snippet becomes a `MemoryCandidate` through deterministic local policy code.
No external model is called.

## Decision Flow

`POST /api/local-memory-approval/sessions/{session_id}/decision` records one of:

- approve for a future manifest
- reject
- defer
- edit required
- sensitive block

Decisions are review metadata only. They never apply to Local Brain.

## Manifest Preview

`POST /api/local-memory-approval/sessions/{session_id}/manifest-draft` builds a
canonical manifest preview with approved, rejected, and deferred candidate ids.
The draft always keeps:

- `ready_for_memory_write=false`
- `apply_enabled=false`
- `local_brain_write=false`

Sensitive and voice-derived candidates require edited summaries before they can
be considered valid for a future write gate.

## No Real Local Brain Write

This slice intentionally stops before production memory writing. It does not
modify real Local Brain storage, production verified stores, candidate stores, or
learning runs.

## No Raw Voice Auto-save

Voice remains optional. A voice transcript can become a review candidate, but raw
voice text is not automatically saved as memory. Voice-derived memory candidates
default toward edit-required or defer decisions.

## Sensitive Handling

Sensitive raw text is blocked from automatic memory. Sensitive candidates either
require a sanitized edited summary or are rejected through `sensitive_block`.

## Future Production Memory Write Gate

A later production write gate must add operator confirmation, backup and rollback
proofs, per-source provenance checks, and sensitivity approval. This review
surface provides only the human decision and manifest-preview layer.

## Relation to Selfhood Runtime

Selfhood Runtime may propose memory review sessions, but it must stay proposal
only. It cannot write memory automatically and cannot bypass this review gate.

## Relation to Voice Loop

Voice Loop remains optional and text input remains primary. Voice outputs or
transcripts do not become durable memory unless a user explicitly reviews and
approves sanitized memory candidates in a future write-enabled gate.
