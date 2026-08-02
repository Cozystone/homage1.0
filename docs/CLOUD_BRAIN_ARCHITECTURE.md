# Cloud Brain Architecture

## One-Line Definition

Cloud Brain is the shared public ontology layer for ATANOR: a governed,
continuously updated web knowledge graph that can lend verified graph fragments
to each user's local private brain without turning ATANOR into an external LLM
wrapper.

## Why This Exists

ATANOR separates knowledge from generation. The local private brain stores the
user's durable personal graph, while the generation layer remains a native
graph-token / syntax-assembly research engine. Cloud Brain extends this design
with a shared public memory:

- public web facts become candidate nodes and edges
- repeated, source-supported edges gain strength
- weak or stale edges decay
- only small verified graph fragments are pulled into the lab when needed
- local promotion requires evidence, repeated use, and resource safety

The goal is not to guarantee perfect truth. The goal is to make unsupported
claims inspectable, bounded, and rejectable instead of hiding them inside opaque
model weights.

## Three Brain Layers

### 1. Local Private Brain

The local private brain is the user's secure, persistent knowledge graph.

- Storage: `data/memory/homage.db`, SQLite WAL, append-only JSONL events.
- Scope: private documents, accepted local memories, user's repeated concepts.
- Runtime: local FastAPI + Knowledge Bakery Hippocampus worker.
- Rule: never upload private nodes to Cloud Brain unless a future explicit
  sharing workflow is added.

### Local Hippocampus Module

The current Alpha implementation adds a real continuous cumulative learner in
`packages/knowledge_bakery/knowledge_bakery/learning_daemon.py`.

- Watches `data/raw` for `.txt` and `.md` files.
- Moves stable files into `data/cleaned`.
- Runs `ontology_forge` on each new-file batch. This follows the DeepKE-style
  split of entity/relation/attribute extraction, but stays deterministic and
  local in Alpha.
- Refreshes the global `data/ontology` snapshot from all cleaned documents.
- Rebuilds the local memory index for GraphRAG and native graph-token
  generation.
- Persists a separate synaptic graph in SQLite WAL tables:
  `synaptic_nodes`, `synaptic_edges`, `ingested_files`, and `learning_events`.
- Optionally mirrors potentiation/decay into Neo4j when `NEO4J_URI`,
  `NEO4J_USER`, and `NEO4J_PASSWORD` are configured. Without Neo4j, SQLite WAL
  remains the source of truth.

### Canonical Concept Layer

The ontology pipeline now uses canonical UUID concepts instead of raw strings.
`packages/ontology_forge/ontology_forge/entity_resolver.py` resolves every
extracted entity through a contextual embedding path:

- preferred provider: local BGE-m3 (`BAAI/bge-m3`) through
  `sentence-transformers` or `FlagEmbedding`
- fallback provider: deterministic contextual hash for offline/dev machines
- schema: `Concept(concept_id, primary_name, aliases, context_vector)`
- edge rule: relationships always connect `concept_id -> concept_id`

The learning daemon points batch ingestion and full-memory refreshes at the same
local `data/memory/canonical_concepts.sqlite3` file. This means repeated
relations reinforce the same synaptic edge instead of generating fresh UUIDs on
each ingest.

When BGE-m3 is unavailable, the fallback intentionally refuses cross-alias
semantic merges. It keeps the system safe and deterministic, but true
cross-lingual entity linking requires installing the local embedding model.

### 2. Cloud Brain

Cloud Brain is the public/shared ontology memory.

- Input: governed web harvest, public documents, search/news/wiki snippets,
  public research references, and community-contributed graph fragments.
- State: public node ids, typed edges, source evidence, confidence, frequency,
  decay state, and freshness windows.
- Output: small signed ontology fragments, not natural-language model answers.
- UI role: deployed ATANOR shows Cloud Brain as a viewer; local ATANOR can run
  an actual worker and checkpoint its state.
- Future distribution: an AWS-hosted public ontology service should exchange
  signed graph fragments, not LLM completions. Local ATANOR keeps private memory
  local, asks Cloud Brain only for public graph fragments, and fuses them with
  local retrieval through confidence-weighted routing.

### 3. Lab Working Memory

The lab working memory is the short-lived context used during a query or build.

- It can bind local nodes, fresh web snippets, and Cloud Brain fragments.
- It should garbage-collect temporary edges after the query unless promotion
  conditions are met.
- It must label where each edge came from: local, web, Cloud Brain, or mixed.

## Query Flow

```text
User question
  -> Local Private Brain retrieval
  -> If confidence is weak, run governed web search
  -> If web search is unavailable, rate-limited, too shallow, or lacks context:
       request Cloud Brain fragments by topic/node ids
  -> Build temporary working graph
  -> Generate with ATANOR native graph-token/syntax engine
  -> Guardrail checks unsupported claims against evidence/edges
  -> If useful and repeated, promote candidate edges into local memory
```

Cloud Brain does not replace web search. It is a public graph cache that reduces
repeated web crawling and gives the lab a structured fallback when raw search
results are too noisy or unavailable.

## Cloud-Edge Hybrid Roadmap

ATANOR is evolving toward a local-first, cloud-assisted network. The important
rule is that server coordination and edge payload movement are separate.

### Phase 1: Local-First Core

- Heavy work runs on `127.0.0.1`: RAG, memory, graph traversal, extraction, and
  local answer attempts.
- Supabase/AWS-style services are optional metadata signaling only.
- If no server is configured, the backend still runs as a standalone local
  engine.

### Phase 2: Hybrid Scaling

- Idle Tier 1 / Tier 2 machines can announce capacity through an
  `EdgeComputeBroker`.
- The server may route metadata and batch-job intent, but heavy graph indexing
  and ontology payloads are transferred through edge transports.
- Failed P2P transfer falls back to a signed HTTP fragment endpoint when the
  peer exposes one.

### Phase 3: Autonomous Federated Network

- AWS/Supabase becomes a convenience layer rather than a requirement.
- Local peer discovery can replace server discovery through a peer directory or
  future LAN/DHT discovery.
- Switching from server-assisted to P2P-dominant mode should be a config change,
  not a rewrite.

Current implementation points:

- `apps/api/app/services/network_config.py` centralizes all network mode,
  timeout, signing, limit, and endpoint settings.
- `apps/api/app/services/hybrid_network_manager.py` separates
  `SignalingProvider` from `PayloadTransport`.
- `LocalPeerDirectorySignal` reads local peer hints without a server.
- `SupabaseSignalIndex` sends only vector footprints and peer metadata.
- `Libp2pTransport` and `HttpFallbackTransport` both implement payload
  movement, so graph fragments are not tied to server availability.
- `apps/api/app/services/edge_compute_broker.py` exposes idle capacity as safe
  metadata for future batch orchestration.

## Synaptic Lifecycle

### 1. Virtual Edge

New web or Cloud Brain evidence enters as a virtual edge:

```json
{
  "source": "rtx-5080",
  "relation": "uses_architecture",
  "target": "blackwell",
  "scope": "working",
  "weight": 0.12,
  "evidence_count": 1,
  "last_seen_at": "..."
}
```

### 2. Potentiation

Each repeated verified co-occurrence raises the edge:

```text
weight = min(1.0, weight + alpha * source_quality * user_reuse)
evidence_count += 1
last_seen_at = now
```

Useful signals:

- repeated user questions
- repeated independent sources
- high-source quality
- successful Guardrail support
- appearance in final accepted answers

In Alpha this is implemented as an UPSERT over the local synaptic graph:

```text
ON CONFLICT(edge_id):
  weight = weight + potentiation_increment
  count = count + 1
```

The optional Neo4j mirror uses Cypher `MERGE` on `(source)-[:RELATED
{relation}]->(target)` and applies the same weight increment.

### 3. Consolidation

When an edge passes the threshold, it moves from working memory to long-term
memory:

```text
if weight >= consolidation_threshold
and evidence_count >= minimum_sources
and guardrail_state == "supported"
and resource_envelope == "safe":
    persist edge as long-term synapse
```

Consolidation writes the edge to the local graph or, for public facts, to a
Cloud Brain candidate queue.

### 4. Decay

Unused edges lose strength:

```text
weight = weight * decay_lambda
```

Decay is slower for:

- local user-approved memories
- high-quality public sources
- frequently used domain anchors

Decay is faster for:

- single-source web snippets
- old news
- low-confidence extraction
- unsupported generated claims

### 5. Pruning

Edges below the pruning threshold are dropped or compacted into summary stats:

```text
if weight < prune_threshold and age > minimum_age:
    delete edge or archive as cold evidence
```

This is how ATANOR can learn continuously without allowing the graph to grow
without bound.

`POST /api/learning/daemon/decay` and non-dry-run
`POST /api/cloud-brain/prune` now call the local decay routine. It multiplies
SQLite synaptic edge weights, removes edges below threshold, then deletes
orphan synaptic nodes. If Neo4j is configured, the same decay/prune job is
mirrored there.

## Resource Strategy

Cloud Brain must be designed around hot windows, not full graph loads.

- RAM keeps only indexes, active frontier nodes, and short-lived working memory.
- SSD keeps durable event logs and graph tables.
- mmap/lazy loading maps only the selected subgraph for the current query.
- UI renders only active frontier, anchor nodes, and community summaries.
- GPU is reserved for compact native training/generation experiments, not for
  storing the world in parameters.

For the target workstation class:

- CPU: graph traversal, parsing, extraction, decay/pruning jobs.
- RAM: hot graph window and query context bundles.
- SSD: append-only event log, SQLite WAL hot index, compacted snapshots.
- GPU: future independent syntax assembler / native decoder experiments.

## Cloud Brain API Contract

Alpha facade implemented now:

- `GET /api/cloud-brain/status`
  - exposes the Cloud Brain contract over the current local daemon state.
- `POST /api/cloud-brain/query`
  - returns local Cloud Brain candidate fragments from the memory activation
    graph without calling an external LLM.
- `POST /api/cloud-brain/ingest`
  - alpha endpoint is honest dry-run/planned metadata until the shared public
    backend exists.
- `POST /api/cloud-brain/consolidate`
  - maps to the local daemon tick/consolidation path.
- `POST /api/cloud-brain/prune`
  - dry-run returns a plan; non-dry-run calls local synaptic decay/pruning.

The existing `/api/learning/daemon/*` routes remain as internal local-worker
controls. `/api/cloud-brain/*` is the public-facing contract. In Alpha it is a
local facade; a later milestone can replace its storage layer with a governed
shared graph protocol.

Internal local-worker endpoints:

- `GET /api/learning/daemon/status`
- `POST /api/learning/daemon/start`
- `POST /api/learning/daemon/resume`
- `POST /api/learning/daemon/tick`
- `POST /api/learning/daemon/decay`
- `POST /api/learning/daemon/checkpoint`
- `POST /api/learning/daemon/stop`

## Lab Integration

The lab should use Cloud Brain only as a structured fallback:

1. Try local private memory.
2. Try governed web search if freshness is needed.
3. If web search is limited or too noisy, pull Cloud Brain fragments.
4. Keep fragments temporary unless consolidation gates pass.
5. Display source labels so users can tell local memory, fresh web, and Cloud
   Brain apart.

This keeps the lab honest. The deployed UI can show Cloud Brain as a viewer, but
it must not pretend a public worker is running unless it is actually connected.

## Research Boundary

Cloud Brain is a graph-memory architecture, not a proof that the final native
decoder is solved. ATANOR Alpha still exposes weak generation when the graph is
weak. The right engineering behavior is:

- show weak output when the graph-token predictor is weak
- improve extraction, edge scoring, consolidation, and pruning
- avoid rule-based prose that makes the system look smarter than it is
- never route answer generation to an external LLM while claiming native output
