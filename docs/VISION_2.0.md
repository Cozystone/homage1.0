# ATANOR 2.0 Vision

## Global Scalability And Expansion Matrix

ATANOR 1.0 is the single-node sovereign core: a local-first Ghost Shell, Payload Vault, hardware-adaptive runtime, and template-free local synthesis pipeline that can run on a Tier 1-M workstation without external LLM dependency.

ATANOR 2.0 expands that core into a global, trigger-driven, cloud-assisted edge intelligence network. The 2.0 rule is strict: no future cloud layer may weaken the local-first contract. Cloud systems may broker metadata, synchronize abstract topology, or coordinate peer capacity, but private payloads and local compute remain isolated unless an explicit operator policy enables sharing.

## Current Baseline

| Area | ATANOR 1.0 State |
| --- | --- |
| Runtime mode | `Sovereign Fortress` |
| Default network posture | Local-only, no external LLM egress |
| Payload plane | Local Payload Vault with SQLite WAL |
| Control plane | Ghost Shell SHA-256 topology |
| Chunk ceiling | Hardware-adaptive, Tier 1-M target `max_chunk_nodes: 5000` |
| Generation | Local autonomous synthesis over fetched Ghost Shell context |
| Cloud readiness hooks | `AbstractVaultRepository`, `AWS_MODE`, `ATANOR_GATEWAY_API` |

## Layer 1: Trigger-Driven Runtime Matrix

The runtime must not switch architecture because of marketing, operator mood, or static config alone. It switches when measurable network thresholds are crossed.

### Stage 0: Sovereign Fortress

Trigger:

- Active Node = `1`

Mode:

- `Sovereign Fortress`

Execution contract:

- Absolute local execution.
- Zero external LLM calls.
- Zero mandatory external network egress.
- 100% local device threadpool for ingestion, Ghost Shell traversal, Payload Vault resolution, and synthesis.

Default configuration:

```text
AWS_MODE=false
ATANOR_NETWORK_MODE=local_first
ATANOR_GATEWAY_API=http://127.0.0.1:8500
```

Implementation posture:

- This is the ATANOR 1.0 alpha baseline.
- Cloud Brain UI may display future topology state, but it must not become a required backend.

### Stage 1: Cloud Brain Broker

Trigger:

- Global concurrently connected GitHub or desktop users >= `500`

Mode:

- `Cloud Brain Broker`

Action:

- Flip `AWS_MODE=true`.
- Activate the universal `AbstractVaultRepository` dispatch path.
- Stream lightweight metadata, indexes, heartbeats, and synchronization telemetry through `ATANOR_GATEWAY_API`.
- Use encrypted Amazon S3 metadata mesh for shared abstract registry state.

Strict boundary:

- The shared cloud mesh receives metadata and abstract hash topology only.
- Raw private payload text must remain in local Payload Vault unless the user explicitly exports a sanitized public fragment.

Expected driver path:

```text
AbstractVaultRepository
  -> LocalFileSystemDriver       # Stage 0 default
  -> AmazonS3Driver              # Stage 1 cloud metadata/payload abstraction
```

Required measurements:

- Active node count.
- Peer heartbeat age.
- Metadata publish latency.
- Local-to-cloud sync queue depth.
- Payload privacy policy state.

### Stage 2: Mixture Of Edge Experts

Trigger:

- Aggregated network VRAM >= `10 TB`

Mode:

- `Mixture of Edge Experts (MoEE)`

Action:

- Instantiate the MoEE Decentralized Router.
- Treat peer machines as domain-specialized edge experts.
- Interlink compartmentalized ontology graphs through a global virtual network map.
- Route cross-domain synthesis requests to peer clusters without requiring a central GPU cluster.

Design principle:

- Each edge node remains sovereign.
- The network routes task fragments, not whole private brains.
- Expert routing is based on declared capability, observed reliability, trust score, and available hardware tier.

Routing dimensions:

| Dimension | Example |
| --- | --- |
| Hardware | VRAM, RAM, CPU threads, disk throughput |
| Knowledge | Dominant ontology clusters and anchor hashes |
| Trust | Proof-of-Knowledge history and contradiction rate |
| Availability | Idle status, thermal state, battery/AC state |

### Stage 3: Consensus Governance

Trigger:

- Network request rate >= `5,000 RPS`

Mode:

- `Consensus Governance`

Action:

- Enforce `Proof of Knowledge`.
- Before committing new hash slots into the global registry, require `70%` cross-node validation consensus over SHA-256 Ghost Hash topological paths.
- Reject or quarantine noisy, hallucinated, malicious, or corrupted subgraphs.

Consensus contract:

```text
candidate_fragment
  -> hash path validation
  -> contradiction scan
  -> cross-node topology agreement
  -> 70% commit threshold
  -> global registry append or quarantine
```

Non-negotiable safeguards:

- Old facts are not overwritten during conflicts.
- Temporal decay lowers stale priority without deleting history.
- Malicious noise injection is handled as a governance problem, not a generation prompt problem.

## Layer 2: Follow-The-Sun Matrix

The global network must not depend on one operator's machine staying online forever. ATANOR 2.0 uses a rolling edge relay model that tracks time zones, idle compute, and critical metadata availability.

### Global Time Zone Relay Protocol

Requirements:

1. Track approximate geographic region, local timestamp, uptime window, and idle status of active peer nodes.
2. Replicate critical abstract index fragments before a region enters predictable downtime.
3. Prefer waking or idle nodes in North America, Europe, and Asia-Pacific as relay targets based on the global clock.
4. Never replicate private raw payloads by default; replicate only abstract Ghost Shell index fragments and signed metadata envelopes.

Example flow:

```text
East Asia Tier 1-M node enters local night
  -> relay planner detects shutdown probability
  -> critical abstract hash indexes are copied to waking EU/NA peers
  -> global topology remains queryable
  -> original node can rejoin and reconcile deltas later
```

Result:

- The network behaves like a virtual global IDC.
- Compute capacity is harvested from the natural rotation of idle edge devices.
- No single user machine becomes a permanent bottleneck.

Operational metrics:

- Regional active peer count.
- Relay replication lag.
- Fragment redundancy factor.
- Peer shutdown prediction confidence.
- Reconciliation conflict count.

## Layer 3: Hyper-Local Attention Mesh

ATANOR must scale toward trillion-node knowledge space without ever forcing the browser, GPU, or local RAM to hold the full network. The 2.0 mesh keeps inference bounded by separating macro-navigation from micro-activation.

### Bi-Level Neuromorphic Attention Pipeline

Macro-level:

- Read only the top `100` high-density global anchor nodes.
- Deduce the macro-topography of the query.
- Target budget: sub-millisecond routing over compact anchor indexes.

Micro-level:

- Use macro anchors to activate exactly one localized viewport.
- Spin up at most `max_chunk_nodes: 5000` context paths on Tier 1-M hardware.
- Treat every other node as cold/dormant storage.

Invariant:

```text
global graph size may grow without bound
active inference window remains bounded
```

Target complexity:

- Memory overhead: `O(1)` relative to total graph size.
- Runtime overhead: bounded by hardware tier and chunk ceiling.
- Rendering overhead: bounded by active viewport virtualization.

Anti-hairball rules:

- Never render the whole graph.
- Never retrieve the whole graph.
- Never hydrate the whole Payload Vault.
- Never let low-confidence distant edges enter the active context just because they exist.
- Always route through anchor selection before micro-activation.

## Runtime Switch Registry

| Stage | Trigger | Runtime Mode | Primary Switch | Core Action |
| --- | --- | --- | --- | --- |
| 0 | Active Node = 1 | `Sovereign Fortress` | `AWS_MODE=false` | Full local execution |
| 1 | Active Nodes >= 500 | `Cloud Brain Broker` | `AWS_MODE=true` | Shared encrypted metadata mesh |
| 2 | Aggregated VRAM >= 10 TB | `MoEE` | `ATANOR_NETWORK_MODE=server_assisted` or `p2p_dominant` | Edge expert routing |
| 3 | Network RPS >= 5,000 | `Consensus Governance` | `ATANOR_PROOF_OF_KNOWLEDGE=true` | 70% validation before global commit |

## Environment Variables

| Variable | Stage | Meaning |
| --- | --- | --- |
| `AWS_MODE` | 1+ | Enables cloud-capable vault driver dispatch |
| `ATANOR_GATEWAY_API` | 0+ | Central frontend/backend gateway switch |
| `NEXT_PUBLIC_ATANOR_GATEWAY_API` | 0+ | Browser-visible gateway switch |
| `ATANOR_NETWORK_MODE` | 0+ | `local_first`, `server_assisted`, or `p2p_dominant` |
| `ATANOR_S3_VAULT_BUCKET` | 1+ | S3 vault bucket for cloud driver |
| `ATANOR_S3_VAULT_PREFIX` | 1+ | S3 key prefix for cloud driver |
| `ATANOR_ENABLE_SERVER_SIGNALING` | 1+ | Enables server-side metadata signaling |
| `ATANOR_PROOF_OF_KNOWLEDGE` | 3+ | Enables consensus validation gate |

## Alpha Compliance Notes

The current Tier 1-M core must remain compliant with this roadmap by preserving these constraints:

- `AbstractVaultRepository` must stay the only Payload Vault abstraction boundary.
- `ATANOR_GATEWAY_API` must remain the central routing switch for metadata and SSE paths.
- Legacy `HOMAGE_*` names remain supported during Alpha migration as fallback aliases.
- Stage 0 must work fully offline.
- Stage 1+ must not require a rewrite of local RAG, Ghost Shell, or LocalSynthesizer.
- Cloud-native Docker deployment must remain stateless: persistent memory belongs in mounted volumes, S3, or external stores.
- Temporal decay must preserve older facts and only change retrieval priority.

## Near-Term Implementation Queue

1. Add a `RuntimeStageResolver` service that computes Stage 0-3 from live peer count, aggregate VRAM, and RPS.
2. Add a cloud metadata registry schema for anchor hashes, peer heartbeats, and proof records.
3. Extend `AmazonS3Driver` from lazy read support into signed metadata publish support.
4. Add MoEE routing stubs with capability-scored peer selection.
5. Add Proof-of-Knowledge validation envelope and 70% consensus gate.
6. Add Follow-The-Sun relay planner with region-aware cache replication.
7. Add anchor-index query API that returns macro top 100 anchors before active chunk expansion.

## Executive Summary

ATANOR 2.0 is not a larger monolith. It is a staged expansion of the local sovereign core into a global, cloud-assisted, edge-owned knowledge network. The architecture scales by keeping all active computation hyper-local, all raw payloads protected by policy, and all global coordination reduced to metadata, signed hash topology, and bounded chunk activation.
