# ATANOR Agentic Micro-OS

Status: proof-only bounded agent OS.

The Agentic Micro-OS gives ATANOR a capability-gated execution model. It is not
an infinite autonomous daemon and it does not have unrestricted tools.

## Kernel

- `CapabilityToken` scopes every permitted action.
- Forbidden capabilities include unrestricted shell, arbitrary JS, Local Brain
  direct write, production store direct write, candidate promotion, git commit,
  git push, microphone enable, unscoped private file read, and private upload.
- Allowed proof capabilities include dashboard action, mocked browser/API/MCP
  calls, Cloud verified read summaries, candidate draft writes, Local Brain
  redacted summaries, and human approval requests.

## Loop

`BoundedAgentLoop` stops at budget, records redacted observations, drafts skills,
and writes proposal-only patch manifests. It never auto-promotes skills, commits,
pushes, or mutates memory.

## Status Surface

The proof kernel is now exposed through a proof-only status surface:

- FastAPI router: `/api/agentic-os/status`
- Action validation: `/api/agentic-os/action/validate`
- Brain Access Road request: `/api/agentic-os/brain-access/request`
- Bounded proposal loop: `/api/agentic-os/loop/propose`
- Hermes intake status: `/api/agentic-os/hermes-intake/status`
- Lab UI route: `?section=agent-os&workspace=lab`

The panel is hidden from normal product navigation. It is intended for
Lab/Developer inspection only and shows the safety locks before any real browser,
MCP, cloud, or coding autonomy is enabled.

## Limitations

- No real Hermes runtime is executed.
- No Hermes code is copied into ATANOR.
- Tool Gateway, MCP Gateway, Browser Gateway, and Cloud Gateway are mock/proof
  surfaces only.
- Local Brain direct writes, production store writes, candidate promotion,
  unrestricted shell, arbitrary JavaScript, auto commit, and auto push stay
  blocked.

## Next Connector Gates

Real connector work should proceed only through narrow gates: browser-read
allowlist, MCP descriptor allowlist, SPLATRA evaluator loop, Brain Access Road
review UI, and bounded autonomous scheduler.
