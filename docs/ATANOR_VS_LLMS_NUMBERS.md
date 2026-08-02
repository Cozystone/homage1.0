# ATANOR vs. big-company LLMs — numbers, honestly

The explicit ask: put ATANOR's answer performance next to the big LLMs **in
numbers**. The honest constraint up front:

> We **cannot** run GPT-4 / Gemini / Claude / Llama on ATANOR's own question set —
> by design ATANOR uses no external LLM, and we hold no provider keys. So this is
> **not a head-to-head on one shared test**. ATANOR's column is *measured on our
> set*; the LLM columns are *each vendor's / a third party's published numbers on
> their own benchmarks*. Treat it as a **directional** comparison of where each
> system is strong, not as "ATANOR beats X by N points".

## A. Where ATANOR's design wins: grounding & honesty

| Axis | ATANOR (measured, our set) | Frontier LLMs (published, their benchmarks) | Why |
|---|---|---|---|
| **Hallucination rate** | **~0%** — 0/7 invented-entity traps fabricated (abstained instead) | **~1.5–6%** grounded summarization hallucination — Vectara HHEM leaderboard: GPT‑4 Turbo ≈1.5–2%, Claude/Gemini ≈3–6%; **much higher (10–30%+)** on open long-tail QA without retrieval | ATANOR answers are extractive (the answer *is* the source sentence) or it abstains. LLMs generate, so a non-zero fabrication rate is intrinsic. |
| **Citation precision** | **~100%** — every web answer carries the exact source URL it came from | **<100% and variable** (ALCE benchmark shows even strong RAG LLMs mis-attribute a meaningful fraction); **0% by default** without a RAG harness | The cited page IS the page the answer was extracted from. |
| **Abstention** ("I don't know") | **High** — abstains on traps and when the web is unreachable | **Low** — LLMs are trained to be helpful and tend to answer anyway; TruthfulQA exists precisely because models assert plausible falsehoods | A property of the no-guess design. |
| **Provenance / auditability** | **Full** — every answer emits a reasoning certificate (evidence, derivation kind, guarantees) | **Limited** — chain-of-thought is not a verifiable source trail | |
| **Privacy** | **Local-first** — private memory on-device, never uploaded | **Cloud API** — prompts leave the device | Structural. |
| **Model cost / latency** | **~0 model cost**; self/graph answers ~instant, web answers ~1–2 s | Per-token API cost; latency varies | No large-model inference. |

> TruthfulQA reference point: even GPT‑4-class models score only ~0.6–0.8
> "truthful & informative" — i.e. they still produce confident falsehoods a
> non-trivial share of the time. ATANOR's failure mode is the opposite: it
> under-answers (abstains) rather than over-claims.

## B. Where the LLMs win: coverage & reasoning (ATANOR does not compete)

| Axis | ATANOR | Frontier LLMs (published) |
|---|---|---|
| **Broad knowledge — MMLU** | **N/A** (no generation; limited to graph + retrievable web) | GPT‑4 ≈86%, Gemini Ultra ≈90%, Claude 3.5 Sonnet ≈88% |
| **Math reasoning — GSM8K** | **N/A** | ≈92–97% |
| **Code — HumanEval** | **N/A** | ≈74–92% pass@1 |
| **Multi-hop reasoning** | **v1 only** — deterministic 2-entity comparisons (born-first / older), retrieve→retrieve→compare; no general chained reasoning | Strong, general |
| **Open-ended generation / dialogue (Arena Elo)** | **N/A** — does not free-form generate | The entire leaderboard |
| **Answer coverage** | Lower — says "모르겠다" where an LLM attempts an answer (sometimes right, sometimes hallucinated) | High |

## C. The one-paragraph honest summary

> ATANOR is **not** a generative LLM and does **not** compete on MMLU / GSM8K /
> HumanEval / Arena — those are N/A for it. On the **grounding-and-honesty axes**,
> its measured numbers are at the strong end and structurally hard for a
> generative LLM to match: **~0% hallucination and ~100% citation precision**,
> versus frontier LLMs' **~1.5–6% grounded-hallucination (and far higher
> un-retrieved) with sub-100%, often-absent citation**. The price ATANOR pays is
> **coverage and reasoning depth**: it abstains where an LLM would answer, and its
> multi-hop reasoning is at v1 (deterministic comparisons) versus the LLMs' broad
> chained reasoning. In short: **ATANOR trades the LLMs' breadth for near-zero
> fabrication and full provenance** — an honest, different point on the curve.

## Sources & caveats
- ATANOR numbers: `packages/answer_quality/factual_qa_benchmark.py`, reports in
  `data/audits/factual_qa_benchmark/` (small held-out KO+EN set; small-N, so the
  rates are indicative, not tight intervals).
- LLM numbers are **approximate, from public model cards / papers / leaderboards**
  (MMLU/GSM8K/HumanEval vendor reports; Vectara HHEM hallucination leaderboard;
  Stanford ALCE for citation; TruthfulQA). They move as models update; verify
  against the current leaderboard before quoting externally.
- Different test sets ⇒ **directional comparison only**, by explicit design
  constraint (no external LLM, no keys).
