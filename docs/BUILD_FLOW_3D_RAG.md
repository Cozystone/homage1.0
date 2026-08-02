# Build Start and 3D GraphRAG Flow

## Product Flow

The target user flow is:

1. Click `Build ?쒖옉`.
2. Harvest a governed set of web references.
3. Convert evidence into a typed ontology/RAG memory graph.
4. Grow the graph visually as concepts, relations, and source-backed evidence
   arrive.
5. When the graph is large and grounded enough, open the ATANOR Oven training
   gate.
6. Switch the right panel from learning trace to RAG chat once the user wants
   to inspect or question the learned memory.

## Current Alpha Implementation

- `POST /api/factory/build/start` starts a deterministic Alpha run.
- The route fetches a small allowlisted reference set and reports per-source
  harvest status.
- The response includes typed 3D graph nodes, typed relation edges, staged
  graph frames, a traversal path, a learning trace, and a training-gate report.
- The BakeBoard `Build ?쒖옉` button switches the console into 3D GraphRAG mode.
- The left memory panel renders a Three.js graph with drag rotation, wheel
  zoom, traversal highlighting, and node selection.
- The right process panel lists harvest metrics, graph growth, source cards,
  learning trace events, and the Alpha training-gate state.
- The RAG chat workbench receives the same evidence signals so the user can
  question the learned memory after the graph forms.

## Design Decisions From Research

- Keep a strict distinction between semantic-similarity graphs and knowledge
  graphs. ATANOR can use similarity for traversal, but ontology nodes and edges
  must remain typed and deduped.
- Store source provenance and evidence snippets for every learned relation.
- Treat graph mutation as a first-class event stream; future versions should
  persist the moment each node and edge was created or updated.
- Use 3D traversal as an inspection surface, not as the retrieval algorithm
  itself. Retrieval quality still comes from DataGate quality, ontology typing,
  evidence scoring, and Guardrail checks.

## Alpha Safety Boundary

The current flow is intentionally not broad autonomous crawling and not real
model training. It is an observable Alpha scaffold that proves the PRD flow:
Harvest signals become typed GraphRAG memory, the memory grows on screen, and a
training gate decides when the ATANOR Oven dry-run may start.

## Next Engineering Steps

1. Replace allowlisted reference fetches with governed Harvest connectors.
2. Persist Build Start runs, graph frames, and source provenance.
3. Add a vector index and summary tree for the Knowledge Bakery layer.
4. Convert graph growth events into real training/evaluation traces.
5. Add Guardrail revision loops before any answer or training sample is trusted.
