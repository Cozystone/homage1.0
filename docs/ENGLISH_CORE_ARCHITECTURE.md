# ATANOR — English-Core Architecture ("think in English")

**Owner directive, 2026-07-15 (BINDING):** "구조를 전부 영어 기반으로 가자. 생각을 영어로 하는거야."
The reasoning CORE thinks in English. Korean (and every other language) becomes a thin I/O shell around
an English brain. This supersedes the earlier Korean-first stance for the *core* — Korean morphology
(Kiwi, josa/받침 rules) is not deleted, it is **quarantined to the output lane** where it belongs.

## Why (measured, not asserted)
This session's measurements drove the pivot:
- Closed-book graph reasoning is at **chance** on conceptual MCQ, in both languages (KMMLU 0.21, MMLU
  ~0.26). Knowledge + retrieval is the lever, not the graph reasoner.
- The open-book lever, when it fires, scores **0.375 in English vs 0.234 in Korean** — English prose is
  structurally cleaner for extraction & retrieval (`X is a Y`, whitespace tokens, no morphology), and
  English Wikipedia is ~10× the knowledge.
- So: build the brain in the language where the signal is cleanest (English), and reach every other
  language through a mapping shell — exactly how a person who masters English then reads a foreign
  textbook with a bilingual dictionary.

## The three layers

```
  ┌── INPUT ADAPTER (any language → English concepts) ───────────────────────────┐
  │   KO question → English concept keys via:                                     │
  │     1. Wikidata Q-id cross-lingual label (광합성 → Q11982 → Photosynthesis)   │
  │     2. KO→EN lexicon fallback (surface gloss)                                  │
  └───────────────────────────────────────────────────────────────────────────────┘
                                     │  (English concept keys)
  ┌── ENGLISH REASONING CORE (the "thinking") ───────────────────────────────────┐
  │   • Knowledge substrate: English world-graph + English Wikipedia passages     │
  │   • Tokenization: whitespace (NO Kiwi in the core)                             │
  │   • Reasoning: discrimination / exam cascade / open-book / entailment,         │
  │     all over English concepts + English prose. Verify-gate 1.00 (No-LLM).      │
  └───────────────────────────────────────────────────────────────────────────────┘
                                     │  (English-grounded answer + citation)
  ┌── OUTPUT REALIZER (English answer → user's language) ─────────────────────────┐
  │   English answer → Korean sentence at the LAST mile. Kiwi / josa / 받침 /       │
  │   sentence-ending rules live HERE only — the morphology "hell" is confined to  │
  │   one output stage, never the reasoning core.                                  │
  └───────────────────────────────────────────────────────────────────────────────┘
```

## Self-evolution: cross-lingual bootstrap (endorsed direction)
Once the English core is strong, other languages are learned by **contrastive alignment** against it:
a Korean-harvested fact `[광합성, 유발, 산소]` is accepted only if it aligns (via Q-id) with the English
master graph's `[Photosynthesis, produces, Oxygen]`. The English graph is the **reference truth**, so
studying Korean cannot poison the core — this is the quarantine→consensus→promote machine we already have
([[consensus-evidence-machine]], [[candidate-promotion-gate]]), now with English as the absolute anchor.

## Concrete state / plan
- **Done this session:** English open-book pipeline (`--lang en` harvest → 278k Simple English passages),
  standard-MMLU harness (`--bench=mmlu`), English stopwords, case-insensitive + relevance-ranked retrieval.
  The reasoning paths are already language-agnostic; English is now the primary substrate.
- **Next (English core):** scale knowledge (full enwiki, ~30 GB working — owner provisioning), then attack
  scoring precision (per-option entailment over the passage, beyond token overlap).
- **Next (I/O shell):** `crosslingual` concept adapter (Q-id bridge, world pack already carries Wikidata
  Q-ids + multilingual labels) + keep the Korean realizer for output.

Honesty (BINDING, unchanged): measure-don't-claim, no hype. English-first raises knowledge & retrieval —
the conceptual-reasoning ceiling is still a real multi-step road, stated plainly.
