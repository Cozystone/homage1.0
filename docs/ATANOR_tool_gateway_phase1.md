# ATANOR Tool Gateway Phase 1

Status: proof-only connector gate.

Phase 1 gives Agentic Micro-OS three bounded tool surfaces:

- Browser Read: reads caller-provided public visible-text snapshots only.
- MCP Allowlist: validates descriptor hash, method, and private payload policy.
- SPLATRA Cosmos Evaluator: scores visual/particle candidates without applying patches.

## Safety Contract

- `external_llm=false`
- `external_sllm=false`
- `hermes_runtime_executed=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `arbitrary_js_eval=false`
- `auto_commit=false`
- `auto_push=false`
- `human_approval_required=true`
- `proof_only=true`

The gateway does not grant general autonomy. It creates inspectable capability
boundaries that future agents must pass through before any real connector is
considered.

## API Surface

- `GET /api/agentic-os/browser-read/status`
- `POST /api/agentic-os/browser-read`
- `GET /api/agentic-os/mcp/status`
- `POST /api/agentic-os/mcp/validate`
- `POST /api/agentic-os/splatra/evaluate`

The normal product dashboard stays clean. These cards are exposed in the Lab
Agentic OS route only.

## Non-Claims

- No real MCP server is called.
- No browser automation is performed.
- No arbitrary JavaScript is evaluated.
- No generated code is executed.
- No candidate is promoted.
- No Local Brain or production Cloud Brain store is mutated.
