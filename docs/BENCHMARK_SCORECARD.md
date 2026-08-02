# ATANOR — Honest Benchmark Scorecard (2026-07-15)

Measured this session on the live code + the indexed 141.7M-triple `world_pack_full` store. No hype,
no rounding-up — the BINDING doctrine is measure-don't-claim. Raw JSON in `reports/benchmarks/`.

> **Canonical correction (2026-07-25):** all GPQA numbers below are historical
> diagnostic outputs, not a current baseline or capability result. The local
> Diamond CSV has duplicate answer text across labels in rows 89, 126, and 191,
> so current accuracy is fail-closed until a corrected provenance-bound dataset
> exists. The active measurement path is NL→goal compiler + scientific-knowledge
> staging → E4 → counterbalanced paired E5. Rational/float DSL greens,
> DELIBERATOR control-probe success, and firing-rate changes are mechanism/M1
> evidence only.

## Results (all real, this run)

| Benchmark | Result | Verdict |
|---|---|---|
| **Reasoning gates** (`reasoning_vm`: falsifier·discrimination·entailment·discovery·mcq) | **106 / 106 pass** (falsifier 7/7) | ✅ green |
| **C4 fluency** (learned fusion realizer, KO) | fused **1.00 sentence/answer** (vs template 2.80), enumeration 0/5, grounding **5/5** | ✅ gate |
| **C3 factual MCQ @ scale** (210 graph-covered, type-matched hard distractors) | FUNCTIONAL cohort **84/84, 0 wrong, acc 1.00**; all-relations **108/210 answered, acc 1.00, 0 wrong** | ✅ un-hallucinatable |
| **C1 conceptual statement-MCQ** (is_a·capital·creator, 120) | **118 / 120** (is_a 38/40, capital 40/40, creator 40/40) | ✅ un-hallucinatable |
| **🟡 KMMLU public benchmark** (200 Q / 8 subjects, same cached items) | never-abstains now: **coverage 1.00**, **strict_acc ≈ 0.20** (guess 0.25). Open-book path (retrieved subset) **≈ 0.26 > random**; closed-book paths ≈ 0.17 | 🟡 **near random; honest** |

## What changed this session (2026-07-15, part 2)

- **기권 0% achieved (owner mandate):** the exam cascade never abstains — coverage went 0.14 → **1.00**.
  A pick is always returned, MARKED by confidence (grounded | openbook | inference | guess) so a guess
  is never asserted as fact. Honesty is preserved by *marking*, not by silence.
- **Closed-book graph = chance, MEASURED and settled.** Two runs on the same 200 items: wiki_kg 505k
  is_a alone **0.21**; full 141.7M pack ∪ wiki_kg **also 0.21** — both below the 0.25 guess floor. Adding
  141.7M facts moved the is_a path 6→34 fires but accuracy stayed random. Proof the graph lacks the
  PROPOSITIONAL content KMMLU asks for (it's `defined_as`-heavy + multi-sense noise + holes).
- **Open-book lever built + proven above random on its subset.** Harvested **685k** Wikipedia lead
  passages; retrieve the question's entity passage and pick the option its real prose supports. The
  openbook path scores **≈ 0.26** — the only path above the 0.25 guess line. It fires on ~35% of items
  (title-match recall); the rest fall to guessing, so the OVERALL stays ≈ random.

## Honest verdict — is the AI "complete"? NO.

**What genuinely works (un-hallucinatable, proven):** MCQ the graph *covers* — capitals, membership,
inception, authors, is_a (C3 84/84 acc 1.00, C1 118/120). The verify-gate means it **never emits a wrong
factual answer**. That is a real property LLMs lack, and it is measured, not claimed.

**The cold wall (honest):** on conceptual/propositional KMMLU the system is **near random (≈0.20)**. This
is a FUNDAMENTAL trade-off, not a bug: No-LLM means no parametric conceptual knowledge, so the only honest
lever is retrieval + entailment. Two bounded sub-problems remain, both long-road:
1. **Retrieval recall** — open-book fires on only ~35% of stems (needs a title-entity). Entity-less
   "which statement is correct" stems need content retrieval (BM25) + fuller passages, not just leads.
2. **Discrimination precision** — even when a passage is retrieved, token-support picks the right option
   only ~0.26. Needs real per-option claim entailment over the passage, not overlap.

**Framing (BINDING, no hype):** MMLU-style accuracy structurally **cannot credit our real edge** — it
scores a lucky guess and a grounded truth identically, so a hallucination-0 instrument looks average on
it. Reaching LLM conceptual-MCQ parity with No-LLM is a genuine multi-step road; this session moved
coverage 0.14→1.00 and proved open-book beats random on what it can retrieve, but did NOT reach parity —
stated plainly, not rounded up.

## Distance to the owner's goal ("overwhelmingly surpass all big LLMs")

- **Knowledge** — biggest lever. Full world-pack build (needs owner to free RAM / a bigger box) + web
  harvest of exam-domain knowledge into the graph.
- **Conceptual entailment** — extend C1 past factual lookup to science-relation entailment (long road;
  needs the knowledge first).
- **Register / blind_naturalness** — the ≈0.5 indistinguishability target is not yet measured at scale;
  bottleneck is corpus register (too encyclopedic), per the corpus-composition doctrine.
- **Autonomous compounding** — the C5 flywheel runs, but turn-N+1 > turn-N is not yet proven.

None of these is a session-fix. The path is real but long; the current state is a **verifiably honest
factual instrument**, not yet a general exam-crusher.

## Historical correction (2026-07-18): GPQA "below random" was a measurement artifact

The GPQA-Diamond closed-book 0.1465 (< 0.25 guess floor) reported above was NOT a capability
signal. Per-stage decomposition (E3, `scripts/diagnose_gpqa_stage_decomposition.py`) showed 89.4%
of items fell to the cascade's stable guess, and that guess scored 0.1356 — because it hashed the
RAW question stem with the SAME `sha256(question)` the GPQA harness uses to Fisher-Yates the
options. Guess pick and correct-answer position were deterministically coupled; analytically two of
the four layouts were unreachable (hit rate 1/6 ≈ 0.167), matching the measurement.

Fix: the scorer's guess stream is salted (`sha256("stable-guess::"+stem)`), decoupling it from any
stem-seeded harness. Re-measured (n=198): **0.2677** overall (guess path 0.2655, inference 0.2857).
se ≈ 0.031, so this is statistically AT the 0.25 floor — stated as artifact removal, not as
capability. KMMLU numbers are unaffected (dataset option order; no harness-side shuffle), so its
≈0.21 remains genuine chance-level. Full trail: docs/ATANOR_four_walls_research.md (E1–E4).
