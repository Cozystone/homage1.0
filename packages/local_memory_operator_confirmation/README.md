# Local Memory Operator Confirmation

`packages/local_memory_operator_confirmation` implements the final human
confirmation gate before any future real Local Brain write can even be prepared.

It does not write Local Brain, does not enable apply, and does not mutate
production stores. A correct typed phrase can only set
`allowed_to_prepare_real_write=true`; `allowed_to_apply_real_write`,
`apply_enabled`, and `local_brain_write` remain false.

Required inputs:

- approved memory manifest id
- write dry-run plan id
- backup plan id
- rollback plan id
- sandbox transaction proof id
- explicit operator phrase

Runtime confirmation records are review metadata under
`data/review/local_memory_operator_confirmation/` by default and must not be
committed.
