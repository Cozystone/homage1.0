# ATANOR Local Brain Memory Approval Gate

Status: proof-only, non-writing.

The Local Brain Memory Approval Gate gives Selfhood Runtime a safe way to
propose personal memory without silently writing it. ATANOR can say that
something may be worth remembering, but the user must approve, edit, reject, or
defer it before any future memory write path exists.

## Memory Candidates

Candidates include preferences, personal facts, project context, corrections,
task goals, relationships, sensitive items, and unknown items. Every candidate
requires user approval and carries `local_brain_write=false`.

## Review Decisions

Review decisions are:

- `approve_for_future_memory_manifest`
- `reject`
- `defer`
- `edit_required`
- `sensitive_block`

The review store records metadata only under `data/review/local_memory_approval`
when used at runtime. Tests use temporary directories. Runtime review outputs are
not committed.

## Sensitive Data Policy

Emails, phone-like strings, address-like strings, identifiers, tokens, and API
keys are classified as sensitive. Sensitive candidates cannot be written raw.
They require an edited summary or a sensitive block decision.

## Voice Transcript Policy

Voice transcript candidates are allowed as proposals only. Raw transcripts are
not saved automatically, always-listening remains disabled, and a user-edited
summary is required before any future memory manifest can represent them.

## Manifest Draft

Approved decisions can produce a deterministic, content-addressed manifest
draft. The draft is not a Local Brain write:

- `ready_for_memory_write=false`
- `apply_enabled=false`
- `local_brain_write=false`

## Future Real Memory Write Gate

Real Local Brain writes remain blocked until a later implementation provides:

- local backup
- rollback
- explicit user confirmation
- edited summary for sensitive or voice-derived content
- sensitivity approval
- per-source provenance
- pre/post Local Brain hash checks

## Relation To Selfhood Runtime

Selfhood Runtime may propose a memory review session. It must not write memory,
enable automatic memory, upload private data, or bypass the approval gate.

## Relation To Voice Loop

Voice Loop may generate a candidate from a transcript, but the transcript remains
proposal material only. The user must approve or edit a summary before future
memory writing can even be considered.

## Relation To Local Brain

Local Brain is unchanged in this slice. The gate is a safety layer in front of a
future write path, not the write path itself.
