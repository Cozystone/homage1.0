# PRD Engine Audit

Date: 2026-06-11

Source of truth: `docs/ATANOR_PRD.md`

## Summary

ATANOR Alpha currently satisfies the PRD's MVP direction as a transparent AI
factory scaffold: documents can pass through DataGate, Ontology Forge,
GraphRAG, Guardrail, telemetry, and BakeBoard visualization. It does not yet
fully satisfy the final PRD engine vision. The largest remaining gaps are real
Harvest crawling/licensing, Knowledge Bakery vector storage, full GraphRAG
community/summary retrieval, real ATANOR-Core-30M training, and the separate
ATANOR Utterance Engine.

## Module Coverage

| PRD module | Current status | Implemented now | Gap to PRD |
|---|---|---|---|
| ATANOR Harvest | Not implemented | Local raw document folder is used as the input source. | URL harvest, source/license metadata, robots status, upload workflow. |
| DataGate | Partial Alpha MVP | Rule-based local document gate, dedupe, length/special-char/link filters, quality score, accepted/rejected outputs, API/UI. | Language detection, PII/API-key filter, TRAINABLE/RAG_ONLY/REVIEW classes, richer source quality score. |
| Ontology Forge | Partial Alpha MVP | Deterministic node/edge extraction, confidence, JSON graph files, graph API/UI. | CAO activation/decay, evidence-gated edge updates, richer edge taxonomy, long-running ontology memory. |
| Knowledge Bakery | Minimal placeholder | Cleaned docs and ontology JSON are used directly by GraphRAG. | FAISS/Qdrant vector DB, graph DB, summary tree, claim-level evidence store. |
| ATANOR GraphRAG | Improved Alpha MVP | Chunking, BM25-style lexical ranking, ontology node matching, one-hop graph expansion, synthesized answer, citations, graph paths, retrieval trace. | Semantic vector search, Personalized PageRank, community-level retrieval, RAPTOR-style summaries, model context injection. |
| ATANOR Guard | Partial Alpha MVP | Claim/evidence overlap, ontology overlap, overclaim warning, score, API/UI. | Four-layer guard split, logical validity, safety policy layer, style/user-intent scoring, revision generation. |
| ATANOR-Core | Scaffold only | Small deterministic model/config object and safe dry-run checkpoint manifest. | Real tokenizer training, real 30M decoder training loop, checkpoint reload generation, concept/relation/verifier heads. |
| ATANOR Oven | Scaffold only | Dry-run loss trace, checkpoint manifest, API/UI. | Real dataset builder, GPU training loop, evaluation loop, activation logger. |
| Neuro-Efficiency Layer | Added research extension | Event sparsity planning, modular routing, continual/few-shot/self-supervised/compression plan. | Real event traces, hardware profile calibration, SNN/FPGA kernels. |
| ATANOR Utterance Engine | Not separated | GraphRAG currently performs deterministic answer synthesis. | Intent engine, preverbal message vector, frame selector, surface realizer, reference-tail builder. |
| BakeBoard | Strong Alpha MVP | Korean console UI, pipeline actions, ontology memory graph, RAG chat, system log, deployed fallback APIs. | Persistent history, WebSocket events, richer charts, document browser, full graph engine. |

## Current Engine Verdict

- Good enough for Alpha demonstration: yes.
- Good enough for PRD final architecture: no.
- Most production-critical next implementation: Knowledge Bakery persistence
  and vector/graph hybrid retrieval.
- Most visible UX gap just fixed in this pass: RAG graph manipulation and
  non-squeezed chat layout.

## Recommended Next Engine Tasks

1. Add `packages/knowledge_bakery` with document chunk registry, vector index
   abstraction, evidence store, and run manifest.
2. Add FAISS local index behind GraphRAG while keeping the current lexical
   retriever as fallback.
3. Persist GraphRAG retrieval traces and Guardrail reports in SQLite.
4. Split deterministic answer synthesis into a first `utterance_engine`
   package.
5. Replace dry-run training with a real tiny tokenizer/dataset/training loop
   before claiming ATANOR-Core-30M is implemented.
