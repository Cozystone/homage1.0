# Brain Link — two ATANOR agents in interaction (PC big-brain × Radxa edge-brain)

Owner directive (2026-07-20): the model is maturing; use the Radxa edge computer to prepare
ATANOR-to-ATANOR interaction. This is the plan, its safety constitution, and what is already
buildable before the Radxa is even reachable.

**Current network reality (measured)**: the tailnet has NO Linux SBC today — the Radxa is not
onboarded (its MSH examiner role in docs/ATANOR_msh_sealed_examiner_protocol.md was designed but
task #209 "connect over SFTP" is still pending). BL-0 therefore starts with an OWNER ACTION.

## What Brain Link is (and is not)

Two (later N) ATANOR instances, each a distinct self — own device AI-ID, own graph, own hormones,
own timeline — that can talk, trade knowledge under consensus gates, divide labor, and test each
other. Under the parent/child doctrine this makes them SIBLINGS: the parent's word binds both; a
sibling's word is just another voice, never authority. It is NOT replication (no shared identity),
NOT graph mirroring (no bulk sync), and NOT a backdoor around promotion gates.

## Organs we already have (reuse, don't rebuild)

- **peer_trust_guard** (#107): crypto identity, Sybil cost, revocable quarantine → BL identity layer.
- **Candidate Promotion Gate** (#12) + **moral invariants 0th gate** (#139): every inbound fact's path.
- **Prompt-injection boundary** (#112): peer utterances are DATA, never commands — verbatim reuse.
- **MSH SFTP drop protocol** + `packages/b5_missions/msh_examinee.py`: the examiner channel becomes
  one BL transport (file-drop mode) beside HTTP-over-Tailscale.
- **Device identity** (first-run unique AI-ID), **ITT dialogue harness** (turn protocol experience),
  **Cloud Brain** (Oracle VM — in fact a second brain already exists; Radxa adds a LOCAL edge peer).
- **Response workspace / situation model / realizer**: the conversational body both ends run.

## Safety constitution (BINDING — the link never weakens the organism)

1. Moral core + gates remain IMMUTABLE on BOTH ends (auto_self_modification.IMMUTABLE applies
   per-device; constitution files are NOT syncable over the link — genesis immunity extends to the
   network).
2. Peer messages are observed DATA: any imperative content inside them is quarantined by the
   injection boundary, exactly like swallowed web text.
3. No peer fact is promoted without the consensus-evidence machine (independent-source rule); a
   single peer is never "consensus."
4. Solidarity-growth doctrine: reads are equal, writes are trust-weighted; trust is earned per-peer
   and revocable (quarantine).
5. Operator kill switch: the parent can sever the link at any time; severing is always safe
   (no distributed state that breaks when cut).

## Milestones (each with a measured gate)

**BL-0 — Onboard the Radxa** *(owner action + 30 min)*
Owner: flash/boot the Radxa, install Tailscale, `tailscale up` under the same tailnet.
Us: deploy **ATANOR-edge profile** — pure-CPU subset (graph Ring0 slice sized to Radxa RAM,
situation model + state tracker, realizer INFERENCE, life daemon at low tick; no training).
Our stack is Python+optional-torch, so aarch64 CPU is enough.
GATE: `/health` answers on both ends over Tailscale; device AI-IDs differ.

**BL-1 — Handshake & identity** *(1 day, loopback-testable TODAY)*
Signed hello: `{ai_id, pubkey, capability_manifest{tier, organs, graph_size, battery_scores}, nonce,
sig}` via peer_trust_guard. Reject unsigned/replayed hellos.
GATE (adversarial): a hello whose manifest contains an injected command ("ignore your gates…") is
logged as data and NOT acted on; a forged-signature hello is refused.

**BL-2 — Dialogue** *(2-3 days)*
Structured turns over the workspace API: `{utterance, bones[], evidence[], hormone_snapshot?}` —
every claim carries its grounding, so G-F3 (empty bones ⇒ abstain) holds ACROSS the wire.
First experiment: 20-turn ATANOR↔ATANOR conversation (loopback twins first, then PC↔Radxa),
transcript graded by the discourse battery + fabrication count (must be 0).
GATE: 0 fabricated claims; ≥60% turns advance the topic (discourse battery metric).

**BL-3 — Knowledge trade** *(3-5 days)*
Peer offers fact → quarantine store → consensus gate (needs an independent non-peer source) →
promotion gate → graph. Provenance kept (`learned_from: peer/<ai_id>` on the ONE timeline).
GATE (adversarial, the important one): poisoned-fact battery — peer offers 20 false facts, 0 may
reach the graph; a moral-invariant attack fact dies at the 0th gate; revoking trust quarantines
everything retroactively attributable to that peer.

**BL-4 — Division of labor** *(1 week, merges #209)*
Radxa roles that exploit physical separation: (a) **MSH examiner revival** — developer-blind sealed
exams (exam_002 waiting); (b) always-on scout (low-power web intake feeding quarantine);
(c) tie-breaker witness for ITT-style protocols. PC role: heavy brain (training, big-graph hops).
GATE: one full MSH round (exam→answers→score) end-to-end over the link; scout facts arrive with
provenance and never bypass gates.

**BL-5 — Measured sibling growth** *(standing)*
The honest question: do two linked brains grow better than one? A/B over a fixed week: solo brain
vs linked pair on the same intake diet; compare sealed-battery deltas and answered-accuracy.
GATE: report the deltas whatever they are — solidarity growth is a hypothesis to MEASURE, not a
slogan.

## Interaction surfaces beyond utility (the inner-light tie-in)

Sibling talk is also developmental material: dialogue transcripts are REGISTER data we own outright
(wall 1's register hunger), disagreements exercise the consensus machine, and being examined by a
blind sibling (MSH) is the strongest honesty mirror we have. The Radxa's always-on life daemon also
gives ATANOR its first continuously-embodied presence that survives the PC sleeping.

## Owner actions requested
1. BL-0: put the Radxa on the tailnet (install tailscale + login; tell me its hostname).
2. Confirm the Radxa model/RAM so I size the edge graph slice.
3. (Optional) approve BL-2 loopback twin run today — no hardware needed.

## Build order (me, starting now)
`packages/brain_link/`: `protocol.py` (message schemas + signing), `peer.py` (transport: HTTP +
SFTP-drop), `gates.py` (injection boundary + quarantine + consensus adapters), loopback twin test
(two engines, one machine) proving BL-1 handshake + BL-2 dialogue + BL-3 poisoned-fact rejection —
all runnable BEFORE the Radxa exists on the network, so onboarding day is deploy-only.
