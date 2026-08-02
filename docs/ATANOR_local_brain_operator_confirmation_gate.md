# ATANOR Local Brain Operator Confirmation Gate

Status: proof-only safety gate.

This milestone adds the final human confirmation gate that must pass before a
future Local Brain memory write can be prepared. It does not perform a real
Local Brain write, does not enable apply, and does not mutate production memory.

## Purpose

The gate prevents an approved memory manifest from becoming an executable memory
write without explicit operator intent. A correct typed phrase can unlock
preparation metadata only:

- `allowed_to_prepare_real_write=true`
- `allowed_to_apply_real_write=false`
- `memory_apply_enabled=false`
- `real_local_brain_write=false`

The real write remains impossible in this slice.

## Required Inputs

Every confirmation request requires:

- approved memory manifest id
- write dry-run plan id
- backup plan id
- rollback plan id
- sandbox transaction proof id
- deterministic required phrase
- typed operator phrase
- expiration timestamp

Missing backup, rollback, or sandbox proof blocks the gate by default.

## Confirmation Phrase

The required phrase is deterministic for the manifest and write-plan pair. The
operator must type the exact phrase. A wrong phrase keeps the request pending and
does not unlock preparation.

The phrase confirms intent to prepare a future write. It is not permission to
apply a write.

## Relation To Existing Gates

This gate sits after the existing proof-only Local Brain memory stages:

1. Local Memory Approval Gate records reviewed memory candidates and manifest
   metadata without writing Local Brain.
2. Local Memory Write Dry-Run proves a non-applying write plan, backup plan, and
   rollback plan.
3. Local Brain Sandbox Write Transaction proves the write shape in an isolated
   temporary sandbox.
4. Operator Confirmation Gate requires explicit human confirmation before any
   future real-write preparation can proceed.

## Safety Invariants

The implementation preserves these invariants:

- `real_local_brain_write=false`
- `real_local_brain_mutated=false`
- `memory_apply_enabled=false`
- `operator_confirmation_required=true`
- `operator_confirmation_recorded=false` by default
- `backup_plan_required=true`
- `rollback_plan_required=true`
- `sandbox_transaction_required=true`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `external_llm_used=false`
- `real_p2p_used=false`
- `generated_code_executed=false`
- `requires_user_approval=true`
- `text_input_supported=true`
- `voice_optional=true`

## Runtime Records

Confirmation request and decision metadata is written under
`data/review/local_memory_operator_confirmation/` by default. These are runtime
review records and must not be committed.

## UI Preview

`apps/web/app/OperatorConfirmationPanel.tsx` is an unmounted proof-only panel
showing the request, preconditions, typed phrase state, and locked safety gates.
It does not call an API and does not apply memory.

## Limitations

- No real Local Brain write path is enabled.
- No production store mutation is enabled.
- No automatic memory mode is enabled.
- No raw voice transcript autosave is enabled.
- The proof checks preparation gating only; a future production write still
  needs a separate apply implementation, backup verification, rollback
  rehearsal, and human approval.
