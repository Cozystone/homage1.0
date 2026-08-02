# Headroom — DEMO applicability assessment

Reviewed 2026-07-01. Source: https://github.com/headroomlabs-ai/headroom (Apache-2.0).

## What Headroom is

Context **compression for LLM agents**: it shrinks everything an agent feeds an LLM (tool
outputs, logs, RAG chunks, files, chat history) to cut tokens 60–95% "with the same answers".
Pieces:
- **SmartCrusher** — JSON / structured-data compression (deterministic).
- **CodeCompressor** — AST-based code compression, multi-language (deterministic).
- **CacheAligner** — stabilizes prefixes for provider KV-cache hits (deterministic).
- **CCR** — reversible compression: keeps originals locally, LLM can re-fetch on demand.
- **Kompress-v2-base** — a **HuggingFace neural model** that compresses prose.
- **`headroom learn`** — mines failed sessions and writes correction notes.

## Honest fit with ATANOR (the important part)

ATANOR's answer/reasoning stack has **no LLM** — so Headroom's headline value ("send fewer
tokens to the model") **does not apply to the core**. Two hard cautions:

1. **`Kompress-v2-base` is a neural model.** Using it anywhere in the answer or learning path
   would **violate the No-LLM / no-sLLM rule.** Do **not** adopt it.
2. Wrapping "the agent → LLM" is moot here; there is no LLM in the loop to compress for.

## What *could* honestly be borrowed (model-free only)

The **deterministic** mechanisms — not the product, not the model — could help ATANOR's
**data-ingestion / web-read** layer, which does chew through large text/JSON:
- **SmartCrusher (JSON) + CodeCompressor (AST)** idea → distill dataset/code feeds before the
  graph learner extracts concepts, cutting noise and bytes. ATANOR already cleans web snippets
  (`compose_web_answer` / `_clean_web_snippet`); this would be the same spirit, applied to bulk
  dataset ingestion (`scripts/feed_dataset.py`).
- **CCR (reversible local original-store)** → a caching pattern for fetched web pages so a
  re-read doesn't re-fetch.
- **`headroom learn` (failure → corrections)** → conceptually **already present** in ATANOR as
  the answer-quality repair loop / `self_improve.py`. No new dependency needed; just noting the
  parallel.

## Recommendation for the DEMO

- **Do not integrate Headroom as a product** (it targets a problem — LLM tokens — ATANOR does
  not have) and **do not use its neural Kompress model** (No-LLM rule).
- **Optional, model-free micro-borrow**: apply a deterministic JSON/AST pre-distillation step
  to *bulk dataset ingestion* only, if/when ingestion volume becomes a bottleneck. Low priority
  for the DEMO; flag to the user before building.
- Net: interesting reference for the *ingestion* layer, but **not a DEMO feature** — the No-LLM
  positioning makes the core product a non-fit. Told the user this honestly rather than
  force-fitting it.
