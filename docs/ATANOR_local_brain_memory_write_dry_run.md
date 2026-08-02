# ATANOR Local Brain Memory Write Dry-run

Status: proof-only, non-writing.

The Local Brain Memory Write Dry-run Planner is the layer after the Local Brain
Memory Approval Gate. It takes an approved memory manifest draft and estimates
what would be written, which Local Brain paths would need backup protection, and
how rollback would be performed later. It still does not write Local Brain.

## Purpose

Personal memory changes are high-impact. A reviewed memory should not jump
directly into Local Brain. ATANOR must first show the exact planned change, prove
that backup and rollback gates are present, and wait for explicit operator
confirmation.

## Write Plan

Approved memory manifest items can become dry-run write candidates:

- preferences -> `preferences`
- personal facts -> `personal_facts`
- project context -> `project_context`
- corrections -> `corrections`
- task goals -> `task_goals`
- relationships -> `relationships`
- sensitive edited summaries -> `sensitive_hold`

Every write candidate keeps `write_allowed=false`.

## Backup Plan

The backup plan identifies Local Brain target paths such as:

- `data/memory/homage.db`
- `data/memory/events.jsonl`
- `data/memory/checkpoints/`

This slice creates metadata only:

- `backup_required=true`
- `backup_created=false`
- `dry_run_only=true`

## Rollback Plan

Rollback is also metadata only. Since no backup is created in this slice,
rollback is not available or executable:

- `rollback_available=false`
- `rollback_executed=false`
- `dry_run_only=true`

## Sensitive And Voice Restrictions

Sensitive raw text is skipped unless a user-edited summary exists. Raw voice
transcripts are skipped unless a user-edited summary exists. Always-listening
memory remains disabled, and raw transcript storage is not part of this gate.

## Apply State

The dry-run remains non-applying:

- `apply_enabled=false`
- `local_brain_write=false`
- `local_brain_mutated=false`

## Future Real Memory Write Gates

Real writing remains blocked until a future implementation provides:

- backup created
- rollback available
- operator confirmation
- edited summary
- sensitivity approval
- provenance verification
- local-only write transaction
- pre/post Local Brain hash validation

## Relation To Selfhood Runtime

Selfhood Runtime may propose that a reviewed memory manifest should receive a
write dry-run plan. It must not write memory, create actual backups, execute
rollback, or set `apply_enabled=true`.

## Relation To Voice Loop

Voice Loop may provide proposed memory candidates only. Raw transcripts remain
blocked from direct writing, and edited summaries are required before planning.

## Relation To Local Brain

Local Brain remains unchanged. This document describes a safety planner in front
of a future write transaction, not the transaction itself.
