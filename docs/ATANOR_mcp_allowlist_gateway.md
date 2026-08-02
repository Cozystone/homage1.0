# ATANOR MCP Allowlist Gateway

Status: proof-only descriptor validator.

`packages/agentic_micro_os/mcp_allowlist.py` validates MCP tool descriptors
without calling a real MCP server.

## Validation

Each request must satisfy:

- descriptor name is known,
- descriptor hash matches the local allowlist,
- method is allowlisted,
- mutating methods are rejected,
- private payload keys are rejected.

The gateway returns a mocked validation result only. It does not call remote MCP
tools and it does not mutate Local Brain, Cloud Brain, candidate stores, files,
or git state.

## Current Descriptors

- `render_preview`
- `public_docs_lookup`

Descriptor hashes are deterministic and derived from the descriptor name plus
allowed methods. Future real descriptors should be reviewed and added one at a
time.

## Current API

- `GET /api/agentic-os/mcp/status`
- `POST /api/agentic-os/mcp/validate`
