# Fable 5 brief — the PHFE generative substrate (the hard research bottleneck)

You are being handed ATANOR's single hardest, most open-ended problem. Everything else
(retrieval, reasoning composition, honesty gates, UI, the learning loop) is tractable
engineering that largely works. This is the one piece that is unsolved *science*, and it gates
the whole "No-LLM system that rivals GPT-class generation" vision.

Read this whole doc, then the four files in "What exists" before writing code.

---

## 1. The problem in one line

Design and prototype a **graph-native generative substrate** that (a) **generalizes to unseen
construction combinations** and (b) **maintains long-range coherence** — **without an LLM,
without an sLLM, without external neural generation.**

## 2. Why this is *the* bottleneck

ATANOR generates language from a **construction-transition model** over a surface graph
(`ASM_GENERATION_BASIS = "local_corpus_construction_transition_model"`). It is a weighted random
walk over token-adjacency counts. This is locally fluent for grounded short factual sentences
and already works (e.g. 쿠버네티스/GPU definitions). But a pure count-based transition graph hits
two hard ceilings:

1. **Generalization / sparsity.** A discrete transition graph has *no probability for a
   transition it never saw*. Most specific n-grams are rare; novel combinations get nothing.
   (This is the curse-of-dimensionality that plateaued n-gram LMs.) Neural LMs escape it with
   *distributed* representations that generalize across similar-but-unseen histories.
2. **Long-range coherence.** The Markov state is the *last token only*. It does not integrate
   the whole context, so a walk is locally smooth but drifts off-topic over a span. Transformers
   solve this with attention (every step conditions on all prior positions).

The graph-native (no-LLM) answer to BOTH is the project's own **PHFE / phase-resonance**
direction: a *superposed / interference* representation that (i) holds many context elements in
one state at once (coherence) and (ii) generalizes over *similar* constructions rather than
requiring the exact seen combination (generalization) — plus grounding anchors that keep it
truthful. Making that real is your task.

Status today (honest, measured 2026-07): native generation ≈ 38% complete, PHFE ≈ 30%. Creative
/ long-form generation essentially does not work; "시 써줘" → "안녕. 나 여기 있어." — that is graph
SIZE + this missing substrate, not a hard architectural wall.

## 3. What exists (read these first)

- `packages/cgsr/cgsr/asm_v0.py` — `_walk_for_frame` (the generation walk) and
  `_build_transition_graph` (the n-gram transition model). This is the baseline you must beat.
- `packages/cgsr/cgsr/phase_context.py` — **the v0 gesture at the answer, built this session.**
  `PhaseField` gives each token a phasor `exp(i·θ)` where `θ = π(1+tanh(IDF-weighted
  co-occurrence · fixed random projection))`; `Superposition` accumulates emitted tokens
  (`acc = decay·acc + phasor`) and scores a candidate by **interference**
  `Re(⟨acc, phasor⟩)/‖·‖`. It is wired into `_walk_for_frame` as a bounded additive nudge.
  Proven property: the *same* candidate pair flips ranking by accumulated context
  (동물>기계 after an animal opening, flips after a machine opening) — generation now conditions on
  the whole context. This is a crude, deterministic embedding; it is a starting point, not the
  answer.
- `packages/cgsr/cgsr/bpe_tokenizer.py` — data-driven subword units (BPE) that discover morpheme
  boundaries from frequency (고양이도 → [고양이, 도]). The units the substrate should operate over.
- `packages/holographic_fold/folding.py` — the existing **wave-interference fold core**
  (phase, amplitude, `re = amp·cos(phase)`, interference matrix). Currently a hidden trace; it is
  the physical substrate you can build the generator on.

Also useful as *examples of graph-native composition that already work*:
`app/services/transitive_reasoner.py`, `entailment_reasoner.py`, `compound_reasoner.py` — they
compose stated relations via transitive closure. Generation needs the analogous "compose, don't
memorize" move, but over surface constructions and probabilistically.

## 4. The research questions

1. **Representation.** What is the right distributed/phase representation of a construction and
   of the running context so that *similar* constructions interfere constructively (generalize)
   while *dissimilar* ones interfere destructively? The current `phase_context` uses a random
   projection of raw co-occurrence — too crude. Candidates: learned-but-transparent phase
   assignment, holographic reduced representations (HRR / circular convolution binding),
   vector-symbolic architectures, resonate-and-fire dynamics. None may be an LLM.
2. **Generation dynamics.** How does the next unit get *selected* from the interference field
   such that the output is fluent AND novel AND coherent over a long span? (Beam over
   interference? A fold-relaxation that settles into a sentence? Resonance selection?)
3. **Grounding.** How do evidence/graph facts anchor the field so coherence doesn't come at the
   cost of truth (no fabrication)?
4. **Theory.** *When and why* does density → good generation? Characterize the conditions under
   which more graph data yields generalizing generation vs merely memorizing. This is the
   intellectual core the user keeps asking about — a real answer here is high value.

## 5. Success criteria (measurable — beat the baseline)

- **Generalization test:** produce a fluent, correct Korean sentence for a construction
  combination NOT present verbatim in the training corpus (held-out), scored better than the
  `_walk_for_frame` n-gram baseline on a small battery.
- **Coherence test:** a multi-clause generation stays on one topic (a coherence metric — e.g.
  mean pairwise relatedness of content units, or staying within a semantic field) measurably
  better than the Markov baseline.
- **Guarantee:** `external_llm: False`, `fabricated_facts: False` hold — verifiable, not
  asserted. Grounded generations cite.
- **Bonus (high value):** a written characterization answering research question 4.

Deliver as a self-contained module (like `phase_context.py`) + tests, not a rewrite of the live
generator. Integration into the live path is Claude's job (see §7), so keep a clean interface.

## 6. Hard constraints (do NOT violate — these are the user's standing rules)

- **No LLM / no sLLM anywhere in the answer or generation stack.** No calling an external model,
  no embedding API, no transformer weights. Distributed/learned representations are allowed only
  if they are transparent and trained in-repo without being a language model (e.g. co-occurrence
  factorization, HRR binding). If unsure, it's out.
- **No fabrication. Honest abstention stays.** Never trade coherence for made-up facts. Never
  claim 환각 0%.
- **Knowledge goes to the graph/data, not hand-coded rule tables.** Morphology/LAD in code is
  fine (segmentation, 받침 allomorphy). Antonym/causal lexicons now live in
  `data/lexicon/ko_relation_lexicon.json` — extend data, not code.
- **Do not break the live demo.** The web app runs on :3200 and the Cloud Brain backend is the
  Oracle deploy (operator-gated). Work in `packages/`, keep tests green, commit locally, do not
  push or deploy.
- **Determinism preferred.** Reproducible > stochastic where possible; if stochastic, seed it.

## 7. Work division (so surfaces don't collide)

- **Fable 5 (you):** this substrate — representation, generation dynamics, theory. Own
  `packages/cgsr/cgsr/phase_context.py` and any new generative-core modules + the fold bridge in
  `packages/holographic_fold/`.
- **Claude:** integration + breadth — wire your substrate into `_walk_for_frame`/the live answer
  path, the graph→answer-pack coverage builder (P0 bottleneck), BPE→graph ingestion, reasoners,
  demo hardening, tests.
- **Codex:** review + guardrail — verify no LLM leaks in, architecture/honesty review, rollback
  log.

## 8. References

- BPE — Sennrich et al. 2016. SentencePiece — Kudo & Richardson 2018.
- Holographic Reduced Representations — Plate 1995. Vector-Symbolic Architectures — Gayler 2003.
- Grokking / mechanistic interpretability of learned arithmetic (Fourier features) — Nanda et al.
  2023 (as evidence that "computation can emerge in a continuous substrate," and why a discrete
  count graph does not — the substrate matters).
- In-repo prior art: `docs/phase-holographic-folding-engine` spec (if present),
  `packages/holographic_fold/`, memory note "phase-holographic-folding-engine".

---

Start by reproducing the `phase_context` proof (the ranking flip), then push on research
question 1 (a representation that generalizes) with a held-out generalization test as your
target metric. Keep it honest — a smaller real result beats a big claimed one.
