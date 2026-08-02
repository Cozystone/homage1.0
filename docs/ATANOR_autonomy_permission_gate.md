# ATANOR Autonomy Permission Gate v0

Status: implemented as an operator-controlled permission gate.

This gate defines four autonomy tiers for Agentic Micro-OS. It does not grant production mutation by default. It makes host authority representable, visible, logged, time-limited, and reversible.

## Tier Matrix

| Tier | Name | Allowed by default | Blocked by default |
| --- | --- | --- | --- |
| 1 | `OBSERVE_ONLY` | read-only summaries | review writes, shell, file writes, production mutation |
| 2 | `DRAFT_PROPOSAL` | review drafts, patch proposals | shell, production mutation, Local Brain writes, git push |
| 3 | `SIGNED_DELEGATION` | only scopes in a signed time-limited token | any scope not present in the token |
| 4 | `FULL_HOST_AUTHORITY` | only enabled sub-switches inside an active session | every disabled sub-switch, expired sessions, emergency stop |

Outside Tier 4, these invariants remain false: `external_llm`, `external_sllm`, `local_brain_write`, `production_store_mutated`, `candidate_promotion`, `unrestricted_shell`, `arbitrary_js_eval`, `auto_commit`, and `auto_push`.

## Tier 4 Requirements

Tier 4 requires all of the following:

- typed phrase: `ENABLE FULL HOST AUTHORITY FOR ATANOR`
- explicit duration: 10 minutes, 30 minutes, 2 hours, or a custom value up to 6 hours
- operator identity recorded in the session
- audit log path recorded in the session
- emergency stop path recorded in the session
- per-capability sub-switches

Tier 4 cannot be entered via a browser page, web content, MCP descriptor, model-only request, or ordinary tier setter. The full-host enable endpoint is the only activation path.

## Sub-Switches

Tier 4 sub-switches are independent:

- `shell`
- `full_file_read`
- `full_file_write`
- `git_commit`
- `git_push`
- `local_brain_write`
- `cloud_production_write`
- `external_network`
- `browser_control`
- `mcp_tools`
- `code_execution`

Git commit/push, Local Brain write, and Cloud production write require their own sub-switches even when Tier 4 is active.

## Emergency Stop

The emergency stop file is:

`runtime/agentic_micro_os/EMERGENCY_STOP`

If the file exists, all verified actions are denied immediately. The UI exposes an emergency stop button in Lab mode.

## Audit

Every allowed and denied action is appended to:

`runtime/agentic_micro_os/host_authority_audit.jsonl`

Audit logging is part of the permission gate. Disabling logs is not an allowed action.
