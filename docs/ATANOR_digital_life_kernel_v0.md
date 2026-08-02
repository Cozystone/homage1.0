# ATANOR Digital Life Kernel v0

Status: proof-only architecture slice.

Digital Life Kernel v0 is a local autonomous organism-loop scaffold for ATANOR.
It turns bounded observations into typed signals, maps those signals to
review-gated action proposals, simulates the proposals in a local sandbox, and
emits events for later UI or congress surfaces.

It is not production integration, not real consciousness, and not AGI. It is a
long-term AGI-oriented architecture component whose current role is to prove
safe control-plane boundaries.

## Safety Boundaries

- No production `verified_store_v0` mutation.
- No Local Brain write.
- No candidate promotion.
- No generated code execution.
- No real P2P or cloud upload.
- No external LLM or sLLM calls.
- No autonomous self-modification.
- All actions are proposal-only and require review by default.

## Relationship To Existing Proof Layers

- Autonomy Kernel: provides the earlier proof-only self-model loop pattern.
- Ego Network: provides identity, sync, and Midnight Congress planning concepts.
- Atlas Router: provides trust-routing vocabulary for future route decisions.
- Tabularis Privacy: provides privacy-gate concepts and risk vocabulary.
- Atlas Congress: can later present proposals, but this slice has no UI wiring.

## Kernel Cycle

1. Observe bounded local state.
2. Compute `LifeSignal` values such as `promotion_candidate`,
   `resource_pressure`, `privacy_risk`, or `social_congress_ready`.
3. Convert each signal into a `LifeActionProposal`.
4. Simulate the proposal in a local sandbox.
5. Emit `life.*` events.
6. Wait for review.

## Future Gates

- Promotion gate before any candidate-store promotion.
- Privacy gate before any sharing or cartridge exchange.
- Identity gate before any multi-device sync.
- Real P2P gate before any socket, WAN, or libp2p integration.
- Signed cartridge gate before accepting external cartridge metadata.
- Cooperative stop support before another long standalone runner.

The preceding 24h candidate run is treated only as
`USER_STOPPED_PARTIAL_WITH_EXTERNAL_FINALIZATION`, not as a full 24h PASS.
