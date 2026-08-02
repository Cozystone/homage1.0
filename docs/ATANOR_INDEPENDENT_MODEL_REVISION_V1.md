# ATANOR Independent Model Revision V1

Date: 2026-06-12

## Purpose

This revision changes the ATANOR target from "GraphRAG plus optional local
sLLM rendering" to a stricter research goal:

> Build an independent local language system that does not use external LLMs,
> local quantized LLMs, or pretrained LLM weights. ATANOR should learn its own
> graph memory, relation probabilities, activation dynamics, and surface
> generation behavior from collected text and user experiments.

The goal is not to hide weak generation behind a polished renderer. If the
system is weak, the output should remain visibly weak so the research state is
measurable.

## Non-Negotiable Constraints

- No external LLM API for answering, judging, reranking, summarizing, or
  rewriting.
- No local quantized LLM as a hidden renderer.
- No pretrained LLM weights for generation.
- No template-only fake answers.
- No claim that the 3D graph is the literal brain-like computation. It is a
  visualization of the memory state and activation flow.
- Pretrained non-generative utilities must be explicitly marked if ever added.
  V1 should prefer from-scratch/local statistical methods first.

## Target Hardware Baseline

Primary workstation profile:

- CPU: AMD Ryzen 9 9950X3D
- GPU: ZOTAC GAMING GeForce RTX 5080 AMP EXTREME INFINITY 16GB GDDR7
- RAM: 32GB DDR5
- SSD: 1TB NVMe

Design implication:

- CPU should own graph traversal, ontology updates, hot-memory indexes, and
  relation probability updates.
- GPU should be used for batched vector math and optional from-scratch small
  ATANOR model training, not for serving a pretrained LLM.
- RAM must keep only the active hot graph and batch buffers.
- SSD must hold append-only memory events, cold graph storage, text chunks, and
  checkpoints.

## Current Alpha Compared To Target

| Area | Current Alpha | V1 Target |
|---|---|---|
| Text ingestion | DataGate and small web/search snippets | Long-running harvest queue with append-only memory events |
| Sentence decomposition | Tokens, phrases, verbs, simple typed edges | Token, phrase, entity, action, role, order, dependency, and discourse units |
| Graph storage | JSON snapshots | SQLite WAL hot graph plus append-only event log |
| 3D graph | Visual layout and live growth simulation | Projection of learned memory/activation state with LOD windows |
| Embedding space | Not real yet | Locally learned vectors from co-occurrence, graph walks, or from-scratch encoder |
| Relation learning | Counts and deterministic edges | Conditional probabilities, decay, confidence, recency, source quality, activation weights |
| Generation | Raw graph-token walk | Graph-conditioned native decoder with learned syntax/phrase memory |
| LLM use | External LLM false; no local LLM currently | Explicitly no external LLM and no local quantized LLM |
| Training | ATANOR Oven dry-run scaffold | Continuous graph-memory learning plus optional from-scratch ATANOR-Core training |

## Revised Architecture

```text
Harvest
  -> DataGate
  -> Sentence Decomposer
  -> Memory Event Log
  -> Knowledge Bakery
       - chunk store
       - token/phrase/entity/action nodes
       - relation probability table
       - locally learned vector table
       - hot graph index
  -> Activation Traversal Engine
  -> Graph-Conditioned Native Decoder
  -> Guardrail / Evidence Trace
  -> BakeBoard 3D Memory UI
```

## Core Components

### 1. Sentence Decomposer

The decomposer should split text into units that are richer than nouns:

- token
- phrase
- entity
- action / verb
- modifier
- subject-like role
- object-like role
- temporal marker
- source chunk
- sentence frame

V1 can remain deterministic, but every emitted unit must become a memory event
with source, position, confidence, and timestamp.

### 2. Knowledge Bakery Memory Store

Replace JSON-only graph snapshots with persistent memory:

```text
data/memory/homage.db
data/memory/events.jsonl
data/memory/checkpoints/
```

Recommended SQLite tables:

- `documents`
- `chunks`
- `memory_events`
- `nodes`
- `edges`
- `relation_stats`
- `token_transitions`
- `cooccurrence_windows`
- `activation_events`
- `vector_rows`
- `query_traces`

The append-only event log is the source of truth. SQLite is the hot index.
JSON graph files can remain export artifacts for UI compatibility.

### 3. Local Embedding / Coordinate Learner

Do not start with a pretrained embedding model. V1 should use local learning:

- PPMI/SVD vectors from token and phrase co-occurrence.
- Random indexing for memory-efficient incremental vectors.
- Node2Vec-style graph walks over the ontology graph.
- Optional from-scratch shallow skip-gram trained only on harvested local data.

The 3D view should be a projection of these learned vectors or graph positions,
not a pretend embedding space.

Output contract:

```json
{
  "node_id": "concept:graph",
  "vector_source": "local_ppmi_svd_v1",
  "dimensions": 128,
  "projection_3d": [0.12, -0.45, 0.77],
  "trained_on_events": 18420
}
```

### 4. Relation Probability Learner

Every edge should accumulate more than a label:

- `count`
- `p_target_given_source`
- `p_relation_given_source_target`
- `recency_weight`
- `source_quality_weight`
- `activation_weight`
- `decay`
- `confidence`

This turns the ontology from a static graph into a learned probability memory.

Example scoring sketch:

```text
edge_score =
  log(1 + count)
  * source_quality_weight
  * recency_decay
  * relation_type_weight
  * activation_feedback
```

### 5. Activation Traversal Engine

Instead of asking a model to infer everything from scratch, the query activates a
small region of memory.

Flow:

1. Decompose query into units.
2. Map units into local vector/graph space.
3. Select seed nodes.
4. Spread activation through high-probability typed edges.
5. Keep top active subgraphs under CPU/RAM budget.
6. Emit a semantic skeleton.

Example skeleton:

```json
{
  "query": "GraphRAG媛 萸먯빞",
  "seeds": ["graphrag"],
  "active_nodes": ["graphrag", "knowledgegraph", "retrieval", "evidence"],
  "active_edges": [
    ["graphrag", "uses", "knowledgegraph"],
    ["graphrag", "retrieves", "evidence"]
  ],
  "semantic_skeleton": [
    {"role": "topic", "node": "graphrag"},
    {"role": "definition", "node": "graph-based retrieval"},
    {"role": "support", "node": "evidence"}
  ]
}
```

### 6. Graph-Conditioned Native Decoder

This replaces both external LLMs and local quantized LLM renderers.

The decoder should be native to ATANOR and trained from the memory store.

V1 options, in increasing difficulty:

1. Probabilistic syntax lattice:
   - learns phrase order and sentence frames from local corpus
   - uses graph skeleton as constraints
   - avoids fixed answer templates

2. Graph-conditioned token decoder:
   - predicts tokens from active nodes, relation types, local vectors, and
     previous generated tokens
   - small enough to train from scratch on the current PC

3. ATANOR-Core from scratch:
   - small decoder-only or state-space/event model trained only on collected
     corpus
   - graph activations are input features
   - no pretrained weights

Recommended V1 path:

```text
Phase 1: probabilistic syntax lattice
Phase 2: graph-conditioned token decoder
Phase 3: from-scratch ATANOR-Core checkpoint
```

The output may be awkward. That is acceptable and preferable to fake fluency.

### 7. Guardrail As Reality Check

Guardrail should not make the answer prettier. It should mark:

- supported graph nodes
- unsupported generated tokens
- low-confidence relation jumps
- source coverage
- hallucination risk

If the decoder invents unsupported content, the UI should show that as a
failure signal.

## First Implementation Plan

### Phase A: Memory Persistence

Add `packages/knowledge_bakery`.

Deliverables:

- SQLite WAL memory store.
- Append-only memory event log.
- Import from current `data/cleaned` and `data/ontology`.
- Export to current UI graph format.
- Tests for event replay and graph reconstruction.

New APIs:

- `POST /api/memory/build`
- `GET /api/memory/status`
- `GET /api/memory/graph`
- `GET /api/memory/events`

### Phase B: Relation Probability Index

Deliverables:

- Edge stats table.
- Token transition table.
- Co-occurrence table.
- Decay and source-quality weighting.
- Query-time active subgraph scoring.

New API:

- `POST /api/memory/activate`

### Phase C: Local Vector Learner

Deliverables:

- PPMI or random-indexing vector builder.
- 3D projection exporter.
- UI metadata showing whether coordinates are real learned projection or
  fallback layout.

No pretrained embedding model in V1.

### Phase D: Native Decoder V1

Deliverables:

- Semantic skeleton output.
- Probabilistic syntax lattice.
- Raw generation with diagnostics:
  - active nodes
  - selected phrase frames
  - token probabilities
  - unsupported token count

New API:

- `POST /api/native/generate`

Required result flags:

```json
{
  "external_llm": false,
  "local_quantized_llm": false,
  "pretrained_generation_weights": false,
  "decoder": "homage-native-graph-decoder-v1"
}
```

### Phase E: Continuous Experiment Loop

Deliverables:

- Long-running build mode writes memory events continuously.
- RAM/VRAM/disk backpressure can pause harvest and training before crashing.
- UI shows:
  - cumulative memory events
  - active hot graph size
  - cold graph size
  - decoder loss / syntax lattice entropy
  - unsupported-token rate

## BakeBoard UI Changes

Left side:

- Rename graph to "Ontology Memory Field" or Korean equivalent.
- Show whether coordinates are:
  - fallback layout
  - force layout
  - learned vector projection
- Use orange pulses only for actually activated nodes during query/generation.

Right side:

- Add generation pipeline view:
  1. query decomposition
  2. seed nodes
  3. activation spread
  4. semantic skeleton
  5. native decoder output
  6. guardrail reality check

Status badges:

- `external_llm: false`
- `local_quantized_llm: false`
- `pretrained_generation_weights: false`
- `native_decoder: active`

## Success Metrics

V1 should not be judged by GPT-like fluency. It should be judged by:

- Can it keep learning without crashing?
- Can it preserve memory over restarts?
- Can it expose active graph paths honestly?
- Can it generate from its own memory only?
- Does answer quality improve as memory events increase?
- Does unsupported-token rate decrease over time?
- Does query latency stay bounded by hot graph size?
- Does the UI distinguish real learned memory from visualization fallback?

## Known Risks

- Pure graph/statistical generation may remain much less fluent than LLMs.
- Korean morphology is hard without a stronger analyzer.
- Graph size can grow faster than useful signal unless decay and compaction are
  implemented early.
- 3D graph beauty can create a false sense of intelligence. The UI must keep
  diagnostics visible.
- From-scratch neural training on a single workstation is possible at small
  scale, but not comparable to frontier LLM pretraining.

## Revised Product Positioning

ATANOR should be described as:

> A local, independent, graph-memory language research system that learns
> symbolic and probabilistic relations from text, traverses activated memory
> sparsely, and generates with its own native decoder rather than an external or
> local pretrained LLM.

This is closer to a personal cognitive memory engine than a conventional LLM.

## Immediate Next Build Target

The next concrete engineering step is not a prettier answer surface. It is:

1. Add `packages/knowledge_bakery`.
2. Persist memory events and graph indexes.
3. Expose `POST /api/memory/activate`.
4. Change GraphRAG query to return a semantic skeleton.
5. Add native decoder diagnostics with:
   - `external_llm: false`
   - `local_quantized_llm: false`
   - `pretrained_generation_weights: false`

## Implementation Status - 2026-06-12

Implemented in Alpha:

- `packages/knowledge_bakery` with SQLite WAL hot index and JSONL memory event
  log.
- Memory tables for documents, chunks, events, nodes, edges, relation stats,
  token transitions, co-occurrence windows, activation events, local projection
  rows, and query traces.
- Phrase node construction from adjacent sentence tokens.
- Action/predicate-aware node typing for local tokens plus imported Ontology
  Forge `verb` nodes.
- Local relation projection metadata:
  `vector_source: local_relation_projection_v1`.
- FastAPI endpoints:
  - `POST /api/memory/build`
  - `GET /api/memory/status`
  - `GET /api/memory/graph`
  - `POST /api/memory/activate`
  - `GET /api/memory/drift-check`
- GraphRAG query responses attach `memory_activation` and preserve:
  - `external_llm: false`
  - `local_quantized_llm: false`
  - `pretrained_generation_weights: false`
- BakeBoard shows Knowledge Bakery as a process card and polls drift checks in
  the existing refresh loop.
- Large-graph activation visibility was browser-verified at a 2,000-node render
  window. If true active memory nodes are outside the current representative
  window, the UI retargets the orange pulse to visible representative nodes and
  labels the trace as `?쒖꽦 ?좏샇(????몃뱶)`.

Still not implemented:

- Real PPMI/SVD, random-indexing, or graph-walk vector learning.
- Durable persistence of client-side live-synapse growth into the memory event
  log.
- A separate `/api/native/generate` decoder endpoint.
- From-scratch ATANOR-Core training beyond the existing dry-run scaffold.

## Implementation Status - 2026-06-12 Local Long-Run Split

Implemented after the first Knowledge Bakery layer:

- A local cumulative-learning daemon state layer on top of Knowledge Bakery.
- Persistent daemon files:
  - `data/memory/daemon_state.json`
  - `data/memory/daemon_checkpoints/*.json`
- FastAPI daemon endpoints:
  - `GET /api/learning/daemon/status`
  - `POST /api/learning/daemon/start`
  - `POST /api/learning/daemon/resume`
  - `POST /api/learning/daemon/checkpoint`
  - `POST /api/learning/daemon/stop`
- Deployment fallback returns lab-viewer status only. It does not pretend that
  Vercel is running the long-lived learner.
- BakeBoard now has two spaces:
  - `?꾩쟻?숈뒿`: local daemon/runtime/checkpoint/reboot-recovery view
  - `?ㅽ뿕??: demo and structural experiment workbench
- `docs/CODEX_GOAL_PROMPT_ATANOR_RESEARCH.md` records the long-run Codex goal
  prompt and reboot protocol.

Still not implemented in this layer:

- A governed background Harvest queue that continuously fetches new text.
- Incremental append-only graph mutations for every browser-side live-synapse
  pulse.
- A native graph-memory decoder evaluation harness.
