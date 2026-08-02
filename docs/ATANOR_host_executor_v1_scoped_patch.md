# ATANOR Host Executor v1 Scoped Patch

Status: implemented behind Tier 4 Full Host Authority.

Host Executor v1 adds the first real source-edit capability, but only as a scoped text patch executor. It is not an unrestricted shell, not a delete tool, not a git automation tool, and not a Local Brain or Cloud Brain mutation path.

## What v1 Can Do

- Build a dry-run diff for an explicit text file target.
- Replace one exact `expected_old_text` occurrence with `replacement_text`.
- Create a backup before writing.
- Return a rollback patch and backup path.
- Roll back from the backup with a second typed confirmation.
- Write audit log entries for allow, deny, apply, and rollback decisions.

## Required Gate

Apply requires all of the following:

- Active `FULL_HOST_AUTHORITY` Tier 4 session.
- `full_file_write=true` sub-switch.
- Matching Tier 4 session id.
- Exact typed confirmation: `APPLY SCOPED PATCH`.
- Emergency stop absent.
- Explicit target path inside the allowlist.

Rollback requires:

- Active `FULL_HOST_AUTHORITY` Tier 4 session.
- `full_file_write=true` sub-switch.
- Matching Tier 4 session id.
- Exact typed confirmation: `ROLLBACK SCOPED PATCH`.
- Backup path inside the scoped patch backup directory.
- Emergency stop absent.

## Allowed Paths

- `apps/web/app/*.tsx`
- `apps/web/app/*.css`
- `apps/api/app/routers/*.py`
- `packages/agentic_micro_os/*.py`
- `packages/splatra_turbovec/*.py`
- `docs/*.md`

## Rejected Paths

- `data/**`
- `runtime/**`
- `external_repos/**`
- Local Brain stores
- `verified_store_v0`
- candidate stores
- `.env` files
- secrets
- binary files
- lockfiles

## Limits

- Target file size limit: 512 KiB.
- Diff preview limit: 300 lines.
- Text encoding: UTF-8 only.
- Patch mode: exact text replacement only.
- Destructive delete: not implemented.
- Unrestricted command execution: not implemented.
- Git commit/push: not implemented.

## Safety Invariants

- `external_llm=false`
- `external_sllm=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `arbitrary_js_eval=false`
- `auto_commit=false`
- `auto_push=false`
- `host_executor_v1_scoped_only=true`
- `human_approval_required=true`

## Future Gates

Future git commit or push support must be separate from this executor and require its own review gate, signed manifest, clean worktree check, generated-data exclusion check, and explicit operator confirmation.
