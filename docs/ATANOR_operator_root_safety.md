# ATANOR Operator-Root Safety Notes

ATANOR may eventually operate as an owner-authorized local agent. The safety requirement is not to make host autonomy impossible; it is to make it impossible by accident.

## Activation Rules

Tier 4 requires:

- exact typed phrase
- explicit duration
- visible Lab UI warning
- audit log
- emergency stop
- enabled sub-switch for each action class

The phrase is:

`ENABLE FULL HOST AUTHORITY FOR ATANOR`

## Operator Responsibilities

Before enabling Tier 4, the operator should check:

- the requested task scope
- which sub-switches are needed
- whether file writes, git actions, Local Brain writes, or Cloud production writes are genuinely required
- whether any private data could leave the machine
- whether emergency stop is available

## Safe Defaults

The default tier is `DRAFT_PROPOSAL`. In that state ATANOR can draft review items and patch proposals, but cannot mutate production stores, write Local Brain memory, run unrestricted shell commands, or push code.

## Destructive Actions

Destructive delete is intentionally not implemented in the v0 helper surface. Future support must require secondary confirmation, exact path preview, backup/rollback plan, and audit entry before any destructive operation.

## Host Executor v0

The first host executor layer is harmless-only. It can run diagnostics such as `echo` and `git_status`, and it can write only under `runtime/agentic_micro_os/tmp/`. It rejects arbitrary commands, deletes, credential reads, uploads, production writes, Local Brain writes, git commit, and git push.

The purpose of v0 is to prove that executable local actions can be routed through the permission gate without creating a silent broad-authority path.

## Host Executor v1 Scoped Patch

The second host executor layer can apply real scoped text patches, but only under Tier 4 with `full_file_write=true`, matching session id, exact typed confirmation, backup, rollback, audit log, and emergency stop checks.

Operators should review the dry-run diff before typing `APPLY SCOPED PATCH`. Rollback requires a separate `ROLLBACK SCOPED PATCH` confirmation and the backup path created during apply.

This layer remains forbidden from Local Brain writes, Cloud production writes, candidate promotion, destructive delete, arbitrary command execution, git commit, and git push.
