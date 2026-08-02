# Durable multi-source seed + grow-only ingestion — design (one-shot reset, never again)

Operator constraint: "if we reset this time, we can't keep resetting" → this reset must build a
foundation that is **grow-only, self-healing, never-reset-again**. Diverse sources, faithful
(collect real sentences → deterministic decompose, never paraphrase/invent — No-LLM), large
(trajectory toward billions+), legally sourced. Be deliberate.

## The 5 invariants that make "never reset again" TRUE
1. **Idempotent, provenance-keyed, append-only.** Every sentence carries a content+source hash;
   ingestion dedups on it. Re-running ANY source never duplicates and never needs a wipe. New
   sources only ADD. (verification_gate already dedups; we extend the key to be per-source-stable.)
2. **Per-source reversibility.** Every row keeps `source_id` + `license` + `source_kind`. A bad
   source is removed by **filtering its rows out** (rebuild-without-source), never by wiping the
   whole graph. So a mistake costs one source, not the foundation.
3. **Bounded memory (the historical reset cause was OOM).** All ingestion goes through the bounded
   runner caps (max_store_mb / max_candidate_files / ResourcePressureMonitor) + streaming reads.
   It throttles, it never crashes-and-resets.
4. **Schema migration, not wipe.** Schema changes add fields / run a migration over the sidecar,
   never rebuild-from-zero.
5. **Faithful + auditable.** Source text stored verbatim as evidence; the graph is derived
   deterministically. Every node/edge traces to a real sourced sentence (4D provenance/temporal).
   → defensible on a public repo; consistent with No-LLM/honesty.

If these 5 hold, this reset is the LAST one: from here the graph grows, self-heals per-source, and
caps itself. That is the deliverable, not "a big one-time dump".

## Source adapters (diverse, legally sourced)
Each adapter = a script that yields `(text, source_id, source_kind, license, url, lang)` real
sentences → the existing `verify_sentence → decompose_sentence → accumulate` path. NO paraphrase.
| kind | source | license | note |
|---|---|---|---|
| structured | **Wikidata** (CC0) | CC0 | triples→IS_A(P31)+typed; **time-qualifiers→4D temporal** ⭐ |
| encyclopedic | Wikipedia / Wiktionary | CC BY-SA | dump/API, polite UA |
| encyclopedic | 나무위키 (Namuwiki) | CC BY-NC-SA | ⚠ NC — flag if demo is commercial |
| news | RSS headlines/summaries + licensed news API | per-API terms | **no full-article scrape** (copyright) |
| corpus | Common Crawl / OSCAR (CC) | CC | bulk public web, scale source |
| search | search API snippets (Tavily) | reference_only | already wired in daemon |
**Forbidden:** bulk-scraping copyrighted news bodies or SNS (ToS/copyright). Provenance gate rejects
disallowed source_types — keep it strict.

## Who collects (operator's question, answered)
Collection is an **I/O / bandwidth / storage** problem, not an LLM-token problem — so neither
Claude-via-browser nor Codex-clicking is the tool; both are slow and the wrong axis. **Programmatic
adapters do the collecting**, run continuously by the bounded daemon. Browser control only for the
few no-API/JS-rendered sources, used sparingly. **Codex's credits are best spent WRITING/reviewing
adapters fast**, not "being the collector".

## Staged plan (deliberate — validate before scaling; never a blind big dump)
- **S0 (design):** this doc + Codex review (architecture risk gate).
- **S1:** adapter framework + the idempotency/provenance/per-source-removal contract; ONE adapter
  (Wikidata subset) → fresh store; **idempotency test (run twice → 0 dup)** + clean-relations +
  4D temporal populated. Small (≈50–200k nodes). [auto_ok / local]
- **S2:** add 2–3 more adapters (Wikipedia, CC corpus, RSS-summary). Re-validate invariants 1–5 at
  larger scale; bounded-memory holds. Per-source removal demonstrated.
- **S3:** make THIS the live foundation — uvicorn restart (fixed decomposer) + bounded continuous
  daemon runs all adapters grow-only. [operator gate on the live cutover]
- **S4:** scale out over time (billions trajectory) — same pipeline, more sources/time, bounded.

## Asks for Codex (risk gate)
1. Is the per-source-removal-by-provenance the right "never wipe" mechanism, or do we need a
   shard-per-source layout from the start?
2. Idempotency key: content-hash vs (source_id+content)-hash — which avoids cross-source dup loss
   AND cross-source false-merge (the source_hash issue from the P0 analysis)?
3. Smallest S1 that proves all 5 invariants before we commit any scale.
