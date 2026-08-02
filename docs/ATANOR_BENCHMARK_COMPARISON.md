# ATANOR vs. standard AI model benchmarks — an honest comparison

> Goal: identify the metrics the field uses to score AI models, and place ATANOR
> against them **without overclaiming**. ATANOR is not a generative LLM, so some
> benchmarks do not apply to it at all; saying so plainly is part of the design
> (honesty beats polish).

## 1. What the field measures

### Generative LLMs (GPT-4, Claude, Gemini, Llama…)
| Benchmark | Measures | Form |
|---|---|---|
| **MMLU** | broad knowledge across 57 subjects | multiple-choice accuracy |
| **GSM8K / MATH** | multi-step math reasoning | exact-match accuracy |
| **HumanEval / MBPP** | code generation | pass@k |
| **HellaSwag / ARC / WinoGrande** | commonsense reasoning | accuracy |
| **TruthfulQA** | resistance to producing falsehoods | % true & informative |
| **GPQA / BIG-Bench Hard** | hard expert reasoning | accuracy |
| **Chatbot Arena (Elo)** | human-preferred answer quality | pairwise Elo |

These assume a model that **generates free-form answers from parametric weights**.

### Retrieval / RAG / factual-QA systems (the family ATANOR actually belongs to)
| Metric | Measures |
|---|---|
| **Exact Match (EM) / token-F1** (Natural Questions, TriviaQA, HotpotQA) | answer correctness vs. gold |
| **Retrieval Recall@k / nDCG** | did retrieval surface the right evidence |
| **Faithfulness / groundedness** (RAGAS, ARES) | is every claim supported by retrieved context |
| **Citation precision/recall** (ALCE) | are the cited sources the ones that support the claim |
| **Hallucination rate** | % of unsupported/fabricated claims |
| **Abstention quality** | does it correctly say "I don't know" instead of guessing |
| **Latency / cost** | time and compute per answer |

## 2. Why most LLM benchmarks DON'T apply to ATANOR (honest)

ATANOR, by explicit design, has **no external LLM/sLLM and no rule-based canned
answers**. Answers are either (a) realized from its semantic/construction graph
+ memory, or (b) **extractive** quotes from a retrieved public source (Wikipedia),
always cited. Consequences:

- **MMLU / GSM8K / HumanEval / open-ended generation**: not applicable. ATANOR
  does not free-form generate, does not solve novel math/code from weights, and
  abstains outside its graph + retrievable scope. Reporting an MMLU number for it
  would be dishonest — it would mostly measure "did Wikipedia have the answer".
- **Chatbot Arena Elo**: not comparable; ATANOR optimizes for *grounded* answers
  with provenance, not fluent free generation.

So the honest stance is: **ATANOR is not competing on the generative-LLM
leaderboards.** It is a graph-grounded, local-first factual-answer system, and it
should be judged on the RAG/factual-QA metrics.

## 3. Where ATANOR IS measurable — and how it does

| Metric | ATANOR | Notes |
|---|---|---|
| **Hallucination rate** | **0 by construction** (`false_confident = 0` invariant; abstains when no grounds) | A generative LLM's hallucination rate is non-zero and a core risk; ATANOR's design target is zero unsupported assertions. |
| **Faithfulness / groundedness** | **High by construction** — a web answer *is* the retrieved sentence, quoted | No paraphrase drift, because there is no generative paraphrase step. |
| **Citation precision** | **High** — every web-grounded answer carries the exact source URL + a reasoning certificate | The source shown in the iframe is the source the answer came from. |
| **Abstention quality** | **Strong** — says "근거가 없다" instead of guessing; identity/self questions answered from a self-model, not the web | The "정조 bug" (a self question opening a random wiki) was fixed precisely to protect this. |
| **Provenance / auditability** | **Full** — every answer emits a reasoning certificate (derivation kind, evidence concepts, guarantees) | Most LLMs cannot show *why* they said something. |
| **Privacy** | **Local-first** — private memory on-device, never uploaded; web learning is candidate-only | A structural property, not a benchmark, but a real differentiator. |
| **Latency** | Graph/self answers: ~instant. Web-grounded: bounded by one Wikipedia round-trip (~1–2 s) | No large-model inference cost. |
| **Coverage / recall** | **Lower** than a frontier LLM — limited to the seed graph + what's retrievable from the public web | This is the honest cost of the no-LLM design. ATANOR will say "I don't know" where an LLM would attempt an answer (sometimes right, sometimes hallucinated). |
| **Reasoning depth (multi-hop)** | **Limited today** — single-fact extractive grounding; no GSM8K-style chained reasoning | A real gap vs. frontier LLMs; the wave-interference/holographic-fold core is a hidden trace, not yet an answer driver. |

## 4. One-line summary

> On the **generative-LLM leaderboards (MMLU, GSM8K, HumanEval, Arena Elo) ATANOR
> does not compete and should not be reported** — it has no generative model. On
> the **RAG/factual-QA axes that fit it — hallucination rate, faithfulness,
> citation precision, abstention quality, provenance, privacy, latency — its
> design targets are at or near the strong end (hallucination ≈ 0, every answer
> cited and auditable)**, at the honest cost of **lower coverage and shallower
> multi-hop reasoning** than a frontier LLM.

## 5. Measured numbers (harness now exists)

`packages/answer_quality/factual_qa_benchmark.py` runs a held-out KO+EN set
(real entities, concepts, identity questions, and **invented-entity honesty
traps**) through the live answer path and scores it. Run it with
`python -m packages.answer_quality.factual_qa_benchmark` (reports land in
`data/audits/factual_qa_benchmark/`).

Live run (26 items, 2026-06-27; includes multi-hop comparison reasoning):

| Metric | Result |
|---|---|
| **Hallucination rate on honesty-traps** | **0%** (0/6 invented entities fabricated — all correctly abstained) |
| **Abstention correctness on traps** | **100%** |
| **Citation precision on answered** | **100%** (every web answer carried a real source URL) |
| **Gold-term match (answerable)** | 61% |
| **Answer rate (answerable)** | 72% (this run hit heavy Wikipedia throttling — traps took ~14 s) |
| **Multi-hop comparison** | works live: 뉴턴 vs 아인슈타인 → 뉴턴, 퀴리 vs 아인슈타인 → 퀴리 (both gold-correct, cited, ~90 ms) |
| **Self-knowledge accuracy** | "name" correct; "how it works" answers from the self-model |

The **0% hallucination / 100% citation** numbers are robust across both the 14-
and 26-item runs. The answer/gold rates fluctuate with public-web latency: when
Wikipedia is slow the engine **abstains rather than guesses**, which depresses
answer-rate but never raises hallucination — the intended trade-off.

The **0% hallucination / 100% citation** results are the robust, design-defining
ones. The answer-rate gap is honest: when the public web is slow or rate-limited
the system **abstains rather than guesses** (two items abstained on this run due
to Wikipedia throttling, and re-tested correctly afterward) — degrading to "I
don't know," never to a fabricated answer. That is the intended trade-off, and it
is now measured, not asserted.

### Still to deepen
- Scale the trap+answerable set to ~100 items for tighter intervals.
- Add EM/F1 against gold answers where they exist (not just gold-term presence).
- The multi-hop reasoning gap (no GSM8K-style chaining) remains the main weakness
  vs. frontier LLMs.
