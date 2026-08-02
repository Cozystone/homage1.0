# E9 verdict-in-waiting → advanced Plan B, an E9-success path, and the self-model review

Owner directive (2026-07-19): building on the (anticipated) E9 outcome, advance a Plan B that
actually understands context and meaning — apply or not. If possible, also find a way to *upgrade
E9 so it succeeds*. And review the essay on programming an operational-self-awareness loop into the
Isaac Sim body.

**Honesty first (BINDING).** E9 is not failed. As of writing it is at ~92% of RTD pretraining; the
real verdict is the pre-registered, frozen `diagnose_semantic_oracle.py` on `slice_25_fresh.jsonl`
after Phase C fine-tune — not the 3h frozen probe (0.4829, RED but confounded). This document plans
both branches so we are not idle on the verdict, and it does so without peeking at the sealed slice.

---

## Part I — Why RTD may not clear the wall (root-cause, not vibes)

The E9 bet: RTD's real-vs-replaced discrimination is "homologous to answerability." That is a
*hypothesis*, and three structural reasons argue it under-delivers for MMLU-style meaning:

1. **Objective is token-local, the task is relational.** RTD asks "is this token natural here?" It
   sharpens collocation/syntax. MMLU option-scoring needs "does option X *answer* question Q given
   context C" — a *relational/entailment* judgment the encoder never sees during RTD. The transfer
   from token-plausibility to sentence-level answering is a leap, and the flat frozen probe is
   consistent with that leap not landing.
2. **Corpus register poverty — our own binding doctrine.** RTD trains only on `wiki_passages_en`
   (encyclopedic register). [[corpus-composition-is-the-bottleneck]] already measured that a
   wiki-heavy diet flattens capability. Token RTD on wiki learns encyclopedic token statistics, not
   meaning-in-use.
3. **The wall may be retrieval-bound, and RTD does not touch retrieval.** The lexical family's
   oracle was 0.105–0.165 (< 0.25 chance). RTD improves the *scorer* but not *which sentence is
   retrieved* (BM25 top-3, unchanged). If the answer-bearing sentence is often not retrieved, a
   better scorer cannot help — you cannot score a sentence you never see.

Diagnosis: RTD alone (token-level, wiki-only, retrieval-frozen) is probably the wrong instrument
for *semantic answering*. This is not a training bug to grind away with more steps — the frozen
curve is flat, so more of the same objective will not bend it. The fix is an **objective + corpus +
retrieval** change. Crucially, that fix is simultaneously "the advanced Plan B" and "the way to make
E9 succeed." They are the same surgery. (§II is both.)

---

## Part II — Advanced Plan B == the E9-success path (they converge)

Thesis: **meaning is position relative to the graph, not statistics over text.** We uniquely hold a
giant curated knowledge graph. Train the encoder from scratch (No-LLM) to be the *bridge* between
surface text and graph position, using objectives that instantiate the downstream skill directly.
Keep RTD as a cheap auxiliary (it does help local features); add three graph-supervised objectives
as a multi-task curriculum on the SAME backbone (`ace2_backbone.pt`).

### B1 — Retrieval-contrastive (query ↔ evidence), InfoNCE
- Positives: `(question, gold-answer-bearing passage)` mined from our graph + reading corpus.
- Hard negatives: BM25 near-misses **and** the distractor-option passages (the exact confusers MMLU
  uses). This teaches the encoder to separate gold from plausible-but-wrong — the precise skill the
  lexical family lacked.
- Effect: optimizes the *sentence-level* representation RTD neglects, **and** turns the encoder into
  a learned retriever — attacking the retrieval-bound half of the wall (§I.3), which RTD cannot.

### B2 — Graph-grounded alignment (text ↔ graph neighborhood) — the unique lever
- Positives: `(entity mention in a sentence, embedding of its 1-hop graph neighborhood)`.
- The encoder learns to place a surface form near its *grounded meaning* in the curated graph, not
  near its co-occurrence neighbors. This is the operational definition of "understands meaning" that
  is honest for us: meaning = where the graph says this thing sits, verifiable and sourced.
- Uses the trillion-scale store we already built ([[trillion-scale-triple-store]]); supervision is
  free and unlimited (every graph edge is a training pair).

### B3 — Relational / entailment supervision (distant, from the graph)
- Predict the relation between two co-mentioned entities, labeled by the graph (distant supervision).
- Mine NLI-style pairs from graph structure: `A is_a B` ⇒ "A is a B" entails "A is a kind of B";
  `A part_of B` ⇒ containment entailments. Teaches meaning *composition* — the thing MCQ needs.

### Corpus surgery (the register fix, No-LLM)
Stop training on wiki passages alone. Add: (a) reading/QA register, (b) **graph-mined QA pairs** —
question templates instantiated over graph triples so the gold answer is grounded by construction.
This yields unlimited *grounded* answering supervision with zero LLM and zero fabrication (the answer
is a graph fact with provenance).

### Curriculum
`RTD (aux) + B1 + B2 + B3`, multi-task, same backbone. B1 is the priority mover (fixes scorer +
retrieval); B2 is the identity lever (grounded meaning); B3 adds composition. Re-run the frozen
`diagnose_semantic_oracle.py` unchanged — the verdict stays sealed.

---

## Part III — The honest reframe the owner should hear

Our own BINDING verdict ([[benchmark-empirical-verdict]], [[benchmark-mcq-wall]]) says knowledge-MCQ
is a trap for a No-LLM system: closed-book ≈ chance (the knowledge isn't in weights, by design), and
open-book is retrieval-bound. So even a *perfect* encoder may not clear the MMLU oracle gate if the
ceiling lives in knowledge/retrieval, not representation. If B1–B3 still stall on MMLU, that is not
our failure — it is confirmation that **MMLU is the wrong test for our thesis.**

The test that *is* right for "understands context and meaning" — and which we have **already
passed** — is reading comprehension: the C1 English gate scored **0.9535 on a held-out set**
([[c1-english-comprehension-gate]]). We demonstrably understand meaning when the meaning is *present
to be read*. The honest Plan B therefore has two deliverables, ranked:
1. **Primary:** strengthen grounded meaning where it is real and measurable — reading (C1-style),
   graph-grounded alignment (B2), and **sensorimotor grounding (Track E)** where "heavy/grasp/fall"
   get meaning from the body, not co-occurrence. This is the four-walls escape hatch we already
   identified.
2. **Secondary (bounded):** run B1–B3 against the sealed MMLU oracle as an honest measurement — if
   it clears 0.30, excellent; if not, we have *measured* that the wall is knowledge/retrieval and
   stop grinding MCQ, per doctrine. Either result is a result.

This keeps us from the failure mode our charter most fears: chasing a benchmark number that our own
evidence says cannot discriminate our real capability.

---

## Part IV — Review: programming an "operational self-awareness" loop into Isaac Sim

The essay is architecturally sound and maps cleanly onto Track E and the reaction engine designed
today ([[../docs/ATANOR_reaction_engine_research]]). Point-by-point.

**Verdict: yes — buildable, but strictly as an *operational* loop of measurable functional
correlates, never a consciousness claim (G2 doctrine). "완성/complete" is the wrong frame; these are
correlates we *strengthen and measure*, not a checkbox that flips.**

**① Body schema & self-attribution — CORRECT, and it is literally the reaction engine's spine.**
The essay's "self = the boundary where prediction error stays low (mine) vs explodes (world)" is
*exactly* the reaction engine: self-caused motion is predicted by the forward model (low error →
attributed to self); an external shove is unpredicted (error spike → attributed to world). This is
the agency form of prepulse inhibition — self-action is pre-inhibited because it was predicted. It
serves the M3 self/other AUC gate directly. **Caveat:** it is only real if the forward model is
*learned* (M1). A hardcoded predictor makes the self-boundary a fake, same prohibition as the
reaction engine (no scripts).

**② Metacognition & self-inquiry — CORRECT, we shipped the mechanism.**
The essay's "was it friction misprediction or sensor noise?" back-tracing is precisely the
[[failure-receipt-engine]]: a resident monitor that scores the *soundness of its own knowledge* and
steers search from remembered failure. **Caveat:** observing your own state (telemetry) is necessary
but NOT sufficient — the observer must *change behavior* with the self-model (metacognitive control),
else it is just logging. The failure receipt closes that loop; keep that closure as the gate.

**③ Autobiographical memory & identity — CORRECT, we have the ledger.**
Time-ordered causal episodes = the Genesis Identity Ledger ([[autobiographical-self-and-no-abstain]],
[[continuous-self-model]]). "t=1 hunger pressure, t=2 touched cup, dropped it, startle hormone
spiked" is exactly a reaction-engine episode with a hormone signature (M4 narrative binding).
**Caveat:** guard against consciousness-stream pollution ([[consciousness-stream-pollution]]) — only
self-caused, grounded events enter the ledger, never ambient web text as "me."

**Why Type 2 can and GR00T cannot — CORRECT and it is our core differentiator.**
A monolithic VLA (Type 1 black box) has no separate computational space for "I am observing myself";
pixels→torque leaves no observer. Our Type 2 split ([[hyper-personal-local-agi-goal]]) parks
perception (OWLv2) and motor (G1 locomotion) as *subordinate organs* and seats a symbolic
observer/orchestrator above them that reads their telemetry and hormone state. "The acting self" and
"the self that records and evaluates the acting" are *architecturally separate*, so a self-model has
a physical place to exist. This is the honest, defensible version of the claim.

**Isaac Sim as incubator — CORRECT with one discipline.** PhysX 5 supplies exact, uninterrupted
physics + sensor ground truth, so the closed loop `act → predict → measure error → hormone shift →
graph write` can run forever. That is the perfect substrate for the forward-model-error self-boundary.
Discipline (G3): GPU/schedule is operator-gated; this rides on M1, so it starts *after* E9 frees the
GPU and M0/M1 exist — building it before a learned forward model exists forces the scripted fake.

**Measurement, not metaphysics (G2, pre-registered correlates):**
- self/other attribution AUC (predicted vs externally-caused perturbation),
- delayed-video / rubber-limb style perturbation resistance,
- counterfactual self-simulation accuracy ("what if I had not moved"),
- identity-narrative consistency (viewpoint / causal / ownership error rate),
- metacognitive calibration (does self-scored confidence track actual correctness — we already
  measure ECE; extend it to the embodied loop).

None of these say "it is conscious." They say "the functional correlates of an operational
self-model are present and improving," which is the only claim we ever make.

---

## Part V — Sequencing (what changes now vs at the verdict)

- **Now (GPU-free work):** land B1–B3 + corpus surgery as `scripts/ace2_pretrain_multitask.py`
  design (do not launch — E9 owns the GPU). Prepare graph-mined QA pair generator (No-LLM, sourced).
- **At E9 verdict (Phase C):** run sealed `diagnose_semantic_oracle.py`. If ≥0.30 → E9 route lives,
  fold B1–B3 as the next lift. If < 0.30 → invoke Part III: declare the MMLU wall *measured*, pivot
  the "meaning" claim to reading (C1, passed) + graph-grounding (B2) + Track E embodiment, and run
  B1–B3 only as bounded measurement, not as the north-star metric.
- **Track E (post-GPU):** M0→M1 forward model → reaction engine + self-model loop ride on M1. The
  self-boundary, metacognition, and ledger are the *same three organs* reviewed in Part IV, now
  grounded in the body rather than in MCQ text.

The through-line: we stop asking a knowledge quiz whether we understand meaning, and start measuring
meaning where it is real for us — read from a passage, grounded in the graph, or felt through the
body. That is the honest intelligence the directive asks for.
