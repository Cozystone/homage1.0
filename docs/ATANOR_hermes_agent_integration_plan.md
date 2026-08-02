# ATANOR Hermes Agent Integration Plan

Hermes Agent contributes architecture, not a drop-in runtime. ATANOR should
absorb the useful shape: tool gateways, skills, cron, MCP, browser awareness,
trajectory compression, and bounded loops. The core model slot must remain
ATANOR-native and must not call external LLM/sLLM providers.

## Integration Gates

1. Intake only: scan Hermes source as inert text.
2. Architecture rewrite: reimplement safe patterns in ATANOR terms.
3. Capability kernel: every tool requires a scoped token.
4. Brain Access Road: no direct Local Brain or production Cloud Brain writes.
5. Cosmos Cell: broad autonomy only inside bounded SPLATRA proof space.
6. Human approval: git, memory write, promotion, and production mutation remain
   proposal-only.

## Code Reuse Policy

MIT code can be copied only after per-file review, source path and commit hash
recording, notice preservation, external provider removal, and tests proving no
external LLM/sLLM calls or unrestricted shell. V0 copies no Hermes code.
