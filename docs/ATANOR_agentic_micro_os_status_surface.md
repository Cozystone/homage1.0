# ATANOR Agentic Micro-OS Status Surface

Status: proof-only lab surface.

## Endpoints

- `GET /api/agentic-os/status`
- `POST /api/agentic-os/action/validate`
- `POST /api/agentic-os/brain-access/request`
- `POST /api/agentic-os/loop/propose`
- `GET /api/agentic-os/hermes-intake/status`

## UI Route

- Lab route: `?section=agent-os&workspace=lab`
- Product mode: hidden from normal navigation

## Safety Flags

- `external_llm=false`
- `external_sllm=false`
- `hermes_runtime_executed=false`
- `hermes_code_copied=false`
- `local_brain_direct_write=false`
- `production_store_direct_write=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `arbitrary_js_eval=false`
- `auto_commit=false`
- `auto_push=false`
- `human_approval_required=true`
- `proof_only=true`

## Blocked Actions

The status surface explicitly displays the blocked actions: unrestricted shell,
arbitrary JavaScript, Local Brain direct write, production write, candidate
promotion, auto commit, and auto push.

## Scope

This surface is a visibility layer over the proof kernel. It does not connect a
real Hermes runtime, real browser automation, real MCP server, real cloud tool,
or production SPLATRA renderer.
