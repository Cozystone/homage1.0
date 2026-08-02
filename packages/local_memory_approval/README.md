# Local Brain Memory Approval Gate

`packages/local_memory_approval` manages proposed Local Brain memory writes as
reviewable metadata. It does not write Local Brain.

The package supports:

- deterministic memory candidate classification
- human approval decisions
- JSON review metadata sessions
- non-applying memory manifest drafts
- proof-only signatures

Safety invariants:

- `local_brain_write=false`
- `local_brain_mutated=false`
- `production_store_mutated=false`
- `memory_apply_enabled=false`
- `requires_user_approval=true`
- raw voice transcripts are not saved as memory
- sensitive raw values require edit or block

Future real memory writing still needs local backup, rollback, edited summaries,
sensitivity approval, per-source provenance, and explicit operator
confirmation.
