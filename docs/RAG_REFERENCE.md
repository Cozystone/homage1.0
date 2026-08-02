# RAG Reference Notes

## External References Checked

- Microsoft GraphRAG: graph-first RAG pipeline that extracts structured data
  from unstructured text, builds graph/community context, and uses that context
  during retrieval.
- Haystack: modular AI orchestration framework with explicit control over
  retrieval, routing, memory, and generation.
- MiroFish: inspected for console layout and GraphRAG process visualization.
  No source code was copied because the repository is AGPL-3.0.
- Reddit discussion:
  `https://www.reddit.com/r/MachineLearning/comments/1ookxb0/r_knowledge_graph_traversal_with_llms_and/`.
  The useful product lesson was the distinction between a semantic-similarity
  graph and a real knowledge graph: ATANOR should preserve typed nodes,
  relation semantics, deduplication, and update history rather than treating
  every chunk-neighbor link as ontology.
- Similarity Graph Traversal Semantic RAG research repo:
  `https://github.com/glacier-creative-git/similarity-graph-traversal-semantic-rag-research`.
  Useful ideas: anchor selection, neighbor traversal, hierarchical graph levels,
  and 3D traversal visualization. ATANOR keeps these as design influences, not
  copied source code.

## ATANOR Alpha Decision

ATANOR Alpha keeps a local deterministic RAG engine instead of vendoring a
large external framework. The implementation now follows a compact hybrid
GraphRAG shape:

1. Chunk accepted DataGate documents.
2. Tokenize query and chunks with Unicode-safe lexical tokens.
3. Match query terms against Ontology Forge nodes.
4. Expand retrieval terms through one-hop graph edges.
5. Rank document chunks with BM25-style lexical scoring, coverage, phrase
   bonus, and graph boost.
6. Return answer text, evidence docs, citations, graph paths, follow-up
   questions, and a retrieval trace.

The Build Start Alpha flow extends that shape with a 3D client-side traversal
view: Harvest evidence enters the graph as source-backed claims, typed
ontology nodes dedupe repeated concepts, relation edges carry labels, and the
training gate waits until the graph has enough nodes, edges, and evidence to
justify a ATANOR Oven dry-run.

## Why This Is Better Than The Previous Alpha RAG

The previous version returned matched documents and graph nodes only. The new
version exposes enough structure for a real product loop:

- `answer` for chat UI rendering.
- `citations` for source grounding.
- `retrieval_trace` for debugging and visualization.
- `retrieval_signals` on evidence chunks so the UI can show lexical and graph
  contributions.
- Stable API compatibility with the old `evidence_docs`, `matched_nodes`, and
  `confidence` fields.

## Next Upgrade Path

- Add persistent embeddings and vector search for semantic retrieval.
- Add graph community summaries once Ontology Forge has enough edges.
- Persist graph mutation history so Build Start can replay how nodes and
  relations were created over time.
- Store retrieval traces per session for evaluation.
- Add reranking and Guardrail-supported answer revision.
