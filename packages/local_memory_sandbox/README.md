# Local Brain Sandbox Write Transaction Proof

`packages/local_memory_sandbox` provides a fake JSON Local Brain store in temp
directories only. It proves that approved memory write plans can be backed up,
applied, validated, and rolled back without touching real user memory.

The sandbox store uses these collections:

- `preferences.json`
- `personal_facts.json`
- `project_context.json`
- `corrections.json`
- `task_goals.json`
- `relationships.json`
- `sensitive_hold.json`

Safety invariants:

- `real_local_brain_write=false`
- `real_local_brain_mutated=false`
- real `data/memory` paths are rejected
- raw sensitive values are rejected
- raw voice transcript markers are rejected
- sandbox rollback must restore the pre-write hash

This package is not a production Local Brain writer.
