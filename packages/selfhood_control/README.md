# ATANOR Selfhood Control Plane

`packages/selfhood_control` is a proof-only orchestration package. It connects
existing proof kernels into one local control-plane loop:

- Autonomy Kernel world/self snapshots and deficit signals;
- Ego Network deterministic Midnight Congress and morning events;
- Tabularis Privacy Shield review;
- Atlas Trust Router proof route selection;
- Voice Loop transcript/status response bridge.

This is an AGI-oriented architecture proof, not production AGI and not a
consciousness claim. It does not perform production self-modification, execute
generated code, write Local Brain, mutate production stores, use peer-network
transport, upload to cloud, or call external LLMs. Every proposal requires user
approval.

Run tests:

```powershell
python -m pytest packages/selfhood_control/tests -q
```

Run proof:

```powershell
python -m packages.selfhood_control.proof
```

Proof outputs are audit files under `data/audits/selfhood_control/` and must not
be committed.
