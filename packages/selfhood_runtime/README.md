# Selfhood Runtime v0

Selfhood Runtime v0 is a proof-only integration layer for ATANOR. It connects
existing proof axes into one bounded loop:

1. observe input
2. detect a deficit or signal
3. run local deterministic deliberation when needed
4. check privacy, promotion, routing, and voice gates
5. produce a text response and optional mock voice event
6. wait for user approval

It is not real consciousness, not AGI, and not a production autonomy path.

## Safety Boundaries

- no production mutation
- no Local Brain write
- no real candidate promotion
- no real P2P
- no cloud upload
- no external LLM or sLLM
- no generated code execution
- no real hot-swap
- no always-on microphone
- voice is optional
- text input remains supported
- nontrivial actions require user approval

Run proof:

```powershell
python -m packages.selfhood_runtime.proof
```

The proof writes generated audit output under `data/audits/selfhood_runtime/`.
Those reports must not be committed.
