# ATANOR Constellation Ego Sync Architecture

This document defines the proof-only constellation ego-sync layer. It closes the
architecture at the proof-kernel level only; it is not peer-network transport,
cloud checkout, production DID custody, or Local Brain replication.

## Terms

- Autonomous Self-Model Loop: a world model and self model observe deficits,
  create proposal-only actions, and require user review.
- Amorphous Ego Sync: the future idea that a user's ATANOR self-model can appear
  across desktop, mobile, tablet, archive, and relay-like windows.
- Constellation Multi-Device: a local proof model of main_brain,
  mobile_window, tablet_window, relay_node, archive_node, and test_peer devices.
- Ego Cartridge: metadata-only proof bundle containing world/self model hashes,
  version, privacy grade, and dedupe-safe content hash.

## Proof Flow

1. World Model / Self Model emits a deficit signal.
2. Predictive checkout creates a dry-run `CheckoutRequest`.
3. Privacy gate blocks `private_local_only` cartridges from relay simulation.
4. Synthetic/public cartridges can be placed in a local in-memory fake relay.
5. Midnight Congress deliberates locally using deterministic roles.
6. Wake-up checkin creates a proposal-only merge result.
7. Sync planning compares constellation state and creates user approval events
   for conflicts.
8. Morning gift events summarize proposals for human review.

## Relationship To Existing Proof Axes

- Autonomy Kernel: provides the self-model loop and proposal-only action frame.
- Tabularis Privacy Shield: defines the privacy boundary that must mature before
  any private data can leave local context.
- Atlas Router: future routing policy reference; this proof does not call a real
  route or open a socket.
- Atlas Congress: UI preview of social deliberation; this package is the
  local deterministic kernel beneath that idea.

## Safety Boundaries

- raw private data never leaves in proof; residual risk must be measured before
  production.
- no external text-token API cost; local compute/storage/network cost still
  exists.
- fast sync is a future target; proof uses local deterministic relay simulation.
- proposal-only patches require sandbox tests and human approval.
- IIT-inspired integration metrics would not be consciousness proof.

## Deferred Production Work

- audited identity and key custody;
- future Atlas Network transport;
- promotion and privacy gates for durable memory;
- production cartridge serialization;
- conflict-aware human review UI;
- secure multi-device enrollment;
- production traffic A/B validation.
