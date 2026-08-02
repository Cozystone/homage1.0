# ATANOR Atlas P2P Integration Gates

Status: real P2P is blocked; sandbox and read-only discovery only.

Atlas P2P must not move from proof sandbox to real networking until all gates
below are satisfied and reviewed:

1. Identity gate: peer identity, signature verification, revocation, and local
   trust score persistence are specified and tested.
2. Privacy gate: raw private data cannot leave the device, redaction is tested,
   and residual risk is measured.
3. License gate: every cartridge declares license, source, and usage policy.
4. Promotion gate: received public knowledge enters candidate review only, never
   production `verified_store_v0` directly.
5. Local Brain gate: remote packets cannot write Local Brain.
6. Transport gate: real libp2p/socket use remains disabled until the user
   explicitly enables a reviewed runtime.
7. Audit gate: exchange metadata is recorded without private raw payloads.

Current allowed mode:

- local deterministic sandbox
- signed cartridge metadata fixtures
- read-only peer registry fixtures
- no real public network
- no cloud upload
- no production mutation
- no Local Brain write

BLOCKED_BY_GATES means real Atlas P2P remains a future runtime milestone, not a
current production capability.
