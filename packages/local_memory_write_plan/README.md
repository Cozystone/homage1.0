# Local Brain Memory Write Dry-run Planner

`packages/local_memory_write_plan` plans future Local Brain writes from approved
memory manifest drafts. It does not write Local Brain, create backups, execute
rollback, or enable apply.

The package produces:

- dry-run write candidates
- dry-run backup plans
- dry-run rollback plans
- validation records for required future gates
- proof output for non-mutating scenarios

Safety invariants:

- `local_brain_write=false`
- `local_brain_mutated=false`
- `memory_apply_enabled=false`
- `backup_plan_required=true`
- `rollback_plan_required=true`
- `requires_user_approval=true`

Future real memory writes still require an actual backup snapshot, rollback
availability, operator confirmation, edited summaries for sensitive or
voice-derived content, provenance checks, and a local-only write transaction.
