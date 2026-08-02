# ATANOR Host Executor v0

Status: implemented behind the Autonomy Permission Gate.

Host Executor v0 is the first executable host-action layer. It is intentionally harmless. It proves that host actions can pass through typed permission, sub-switches, audit logging, emergency stop, and explicit action allowlists before stronger host capabilities are considered.

## API Integration

Host Executor v0 is mounted through the normal ATANOR FastAPI app under `/api/agentic-os/host-executor/*`; it does not require a special Agentic-OS-only companion process. The API entrypoint configures local monorepo package roots before router imports so packages such as `knowledge_bakery` and `cost_model` resolve consistently during development and desktop sidecar startup.

The status endpoint must preserve the proof-only invariants:

- `production_store_mutated=false`
- `local_brain_write=false`
- `external_llm=false`
- `external_sllm=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `auto_commit=false`
- `auto_push=false`

## Allowed v0 Actions

- `echo`
- `git_status`
- `read_text_file` with explicit path and `max_bytes`
- `list_directory` with explicit path and `max_entries`
- `write_temp_file` only under `runtime/agentic_micro_os/tmp/`
- `create_backup_patch` only as a `.patch` file under runtime tmp
- `check_emergency_stop`

`echo`, `git_status`, and runtime-temp diagnostics may run with a signed safe test token. Broader reads or writes require Tier 4 and the matching sub-switch.

## Rejected v0 Actions

- `delete_file`
- `recursive_delete`
- `overwrite_non_temp_file`
- `run_arbitrary_command`
- `powershell_unrestricted`
- `network_upload`
- `credential_read`
- `browser_private_session`
- `git_commit`
- `git_push`
- `local_brain_write`
- `cloud_production_write`
- `production_store_write`

Rejected actions are still audited.

## Permission Flow

Every action calls `PermissionGate.verify_action` before execution. Dangerous or unsupported actions are then rejected by the executor even if a broader future permission might exist.

The result object includes:

- `action_id`
- `action_type`
- `allowed`
- `executed`
- `stdout_excerpt`
- `stderr_excerpt`
- `exit_code`
- `denied_reason`
- `audit_event_id`
- `mutation_performed`
- `path_refs`

## Emergency Stop

If `runtime/agentic_micro_os/EMERGENCY_STOP` exists, safe test actions and Tier 4 actions are denied before execution.

## Future Requirements

Future destructive actions must require:

- exact path preview
- secondary typed confirmation
- backup or rollback plan
- dry-run result
- audit record
- explicit Tier 4 session
- matching sub-switch

Destructive delete is not implemented in v0.
