# ATANOR Architecture

ATANOR is a graph-native, local-first AI architecture. Its central idea is simple: keep memory, provenance, retrieval, repair, and public knowledge exchange as explicit graph systems instead of hiding them inside a single remote model call.

## Architectural Principles

1. **Local-first by default.** Private memory belongs to the local runtime.
2. **Cloud is public graph infrastructure.** Cloud Brain stores public fragments and proof-state, not private local memory.
3. **Working Memory is temporary.** Cloud-attached and cartridge-attached nodes can help a session without silently becoming Local Brain.
4. **Graph packs are read-only by default.** Graph Hub cartridges attach as bounded knowledge surfaces.
5. **Repair requires review.** Production repair rules are inspectable and approval-based.
6. **Proof paths avoid external LLM masking.** Alpha proof flows do not depend on external LLM/sLLM answer generation.
7. **Honesty beats polish.** If a subsystem is local/mock/proof-scale, the UI and docs should say so.

## System Map

```text
                         +------------------------+
                         |      ATANOR Web Lab    |
                         | Next.js UI + 3D graph  |
                         +-----------+------------+
                                     |
                                     v
                         +------------------------+
                         |      FastAPI Runtime   |
                         | API routers + services |
                         +-----------+------------+
                                     |
        +----------------------------+-----------------------------+
        |                            |                             |
        v                            v                             v
+---------------+            +----------------+            +----------------+
|  Local Brain  |            |  Cloud Brain   |            |   Graph Hub    |
| private graph |            | public graph   |            | cartridges     |
| retrieval     |            | fragments      |            | install/audit  |
+-------+-------+            +-------+--------+            +-------+--------+
        |                            |                             |
        +-------------+--------------+--------------+--------------+
                      |                             |
                      v                             v
              +---------------+             +----------------+
              | Working Memory|             | Brain Graph    |
              | temp overlay  |             | tab-aware view |
              +-------+-------+             +-------+--------+
                      |                             |
                      +--------------+--------------+
                                     |
                                     v
                         +------------------------+
                         | Surface / Q / Cortex   |
                         | repair, salience, plan |
                         +------------------------+
```

## Local Brain

Local Brain is the private memory boundary. It stores and retrieves local concepts, graph traces, payload links, and synthesis context. The public architecture rule is that Cloud Brain and Graph Hub may provide temporary evidence, but they do not silently write into Local Brain.

Representative areas:

- `packages/rag_engine`
- `packages/knowledge_bakery`
- `apps/api/app/routers/memory.py`
- `apps/api/app/routers/graphrag.py`

## Cloud Brain

Cloud Brain is the public/shared graph layer. It handles semantic growth, public fragment ingestion, controlled self-growth proofs, contributor shards, cloud-attached nodes, and spherical materialization. It is intentionally described as proof-scale in this alpha.

Representative areas:

- `packages/cloud_brain`
- `apps/api/app/routers/cloud_brain.py`
- `data/cloud_brain/proofs`
- `infra/cloudflare/cloud-brain-broker`
- `infra/aws/cloud-brain-broker`

## Brain Graph Renderer

The Brain Graph layer materializes views for different sections of the product. Local, cloud, cartridge, contributor, and working-memory nodes can be represented without pretending they have the same privacy or provenance.

Representative areas:

- `packages/brain_graph`
- `apps/api/app/routers/brain_graph.py`
- `apps/web/app/Rag3DScene.tsx`
- `apps/web/app/CloudBrainSphereScene.tsx`

## Graph Hub

Graph Hub is a cartridge system for graph knowledge. It includes catalog entries, pricing modes, entitlements, installation, read-only attachment, sandbox checks, export, and audit trails. It is not a production marketplace yet.

Representative areas:

- `packages/graph_hub`
- `apps/api/app/routers/graph_hub.py`
- `apps/web/app/api/graph-hub/[...path]/route.ts`
- `data/graph_hub/catalog`
- `data/graph_hub/proofs`

## Surface Brain, Answer Quality, And Repair

Surface Brain turns weak output into inspectable improvement loops. Answer Quality Lab runs comparisons, Surface Repair proposes rule changes, and the review queue prevents unapproved production repair rules from appearing silently.

Representative areas:

- `packages/surface_brain`
- `packages/answer_quality`
- `apps/api/app/routers/surface_brain.py`
- `apps/api/app/routers/answer_quality.py`

## Q-Cortex And CORTEX-G2

Q-Cortex makes planning, evidence, and salience optimization explicit. CORTEX-G2 experiments with activation, prediction, dream loops, executive criticism, and verbalization routing.

Representative areas:

- `packages/q_cortex`
- `packages/cortex_g2`
- `apps/api/app/routers/q_cortex.py`
- `apps/api/app/routers/cortex.py`

## Proof Artifacts

ATANOR commits selected proof artifacts as public evidence of what the alpha currently demonstrates:

- Base Brain Pack v0 proof
- tab-aware Brain Graph proof
- Semantic Cloud Growth proof
- controlled self-growth proof
- remote Cloud Brain proof
- spherical chunk materialization proof
- CORTEX-G2 living loop proof
- Q-Cortex optimizer proof
- Surface Brain and repair/review proofs
- Graph Hub proof and sample catalog

Runtime traces, local databases, logs, caches, and large generated files remain ignored.

## Current Limitations

- The proof stores are small.
- Semantic extraction is deterministic v0, not a perfect parser.
- Graph Hub billing is local/mock.
- The Cloud Brain is not global web-scale.
- Marketplace/payment/DRM readiness is not claimed.
- Native answer quality is still alpha.

These limits are part of the public architecture story: ATANOR is being built as an honest, inspectable system rather than a polished black box.
