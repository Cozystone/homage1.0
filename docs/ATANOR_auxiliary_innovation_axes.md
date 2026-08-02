# ATANOR Auxiliary Innovation Axes

This document introduces auxiliary innovation axes for ATANOR. They are
supporting layers, not replacements for Cloud Brain, CGSR, RHFC, Local Brain, or
the candidate learning spine.

The active 24h candidate-only learning run was not touched by this work. No
current production path imports or uses these auxiliary axes yet.

## Current Order

1. Dijkstra Trust Router
2. Tabularis Privacy Shield
3. Selfhood + Midnight Congress
4. MiroFish Deliberation Lab
5. Turbovec Compression Layer
6. AirLLM Offload Sandbox

## 1. Dijkstra Trust Router

Status: proof-only implementation in `packages/atlas_router`.

Purpose: find the safest and cheapest temporary path to public knowledge
fragments, graph cartridges, Atlas peers, Graph Hub entries, or Cloud Brain
sources. The cost model includes latency, bandwidth, compute cost, stale data
risk, failure risk, trust penalty, license risk, and privacy risk.

Dijkstra Trust Router is first because it directly supports future Graph Hub,
Atlas Network, cartridge selection, and peer/source routing. It only selects
temporary Working Memory attach paths. It never approves permanent Local Brain
writes.

## 2. Tabularis Privacy Shield

Status: proof-only implementation in `packages/tabularis_privacy`.

Purpose: transform private structured data into safe synthetic, anonymized, or
redacted representations before any Cloud, Atlas, or deliberation layer can see
it. Tabularis should be built second because privacy boundaries must exist
before broader source routing or multi-agent deliberation.

The current proof package classifies direct identifiers, quasi-identifiers,
sensitive attributes, and public attributes; redacts direct identifiers;
generalizes quasi-identifiers; creates deterministic proof-only aggregate
records; and emits reviewable privacy reports. It does not claim perfect
anonymity and is not a production privacy guarantee.

Tabularis must sit before any Atlas, MiroFish, Graph Hub, or cartridge workflow
that might receive private structured data. It must not export raw private data
and must not mutate Local Brain.

## 3. Selfhood + Midnight Congress

Status: PROOF_KERNEL_COMPLETE.

Commit: `336fd256`.

Purpose: close ATANOR's selfhood, ego-sync, and Midnight Congress work at the
proof-kernel level. The milestone includes the Autonomy Kernel self-model loop,
Ego Network cartridges, deterministic local Midnight Congress simulation,
Morning Brief / Morning Gift events, proposal-only patch planning, and
multi-device sync planning.

Production boundary: proof-only, not production. It does not implement
peer-network transport, cloud upload, Local Brain mutation, production mutation,
production code replacement, or generated code execution.

Next gates:

1. 24h final audit.
2. Candidate promotion gate.
3. Privacy gate.
4. Identity gate.
5. Atlas peer-transport gate.

## 4. MiroFish Deliberation Lab

Status: deferred descriptor only.

Purpose: future swarm-style deliberation over public or candidate knowledge.
MiroFish must not be built before candidate promotion gates exist, because a
deliberation layer without promotion discipline would amplify unreviewed
candidate artifacts.

## 5. Turbovec Compression Layer

Status: deferred descriptor only.

Purpose: future vector and graph compression plus hot/cold memory acceleration.
Turbovec should wait until graph scale and access patterns prove that
compression is the bottleneck.

## 6. AirLLM Offload Sandbox

Status: deferred descriptor only.

Purpose: future optional local or offloaded large-model reviewer/helper. It must
not become ATANOR's main engine, must not use external APIs by default, and must
remain behind explicit review boundaries.

## Protection Note

The 24h candidate-only learning run remains a protected experiment. This
document and the isolated `packages/atlas_router` and
`packages/tabularis_privacy`, `packages/autonomy_kernel`, and
`packages/ego_network` proof packages do not modify the active daemon, Cloud
Brain, API routes, Cloud Lab UI, candidate stores, production stores, Local
Brain, approved payloads, or runtime status files.
