# ATANOR Autonomous Creative XAI — design + what's built (Fable 5)

The two halves of "our own LLM", both graph-native, No-LLM, density-scaling, grounded:

1. **Grounded generation / generalization** — `packages/cgsr/cgsr/holographic_lm.py` (FHRR kernel
   substrate). Beats n-grams on a real held-out corpus (0.166 vs 0.150), generalizes to unseen
   contexts, semantically (puppy→barks via distributional base). See `phfe-substrate-v1-result.md`.
2. **Concept creation with explanation** — `packages/cgsr/cgsr/creative_engine.py` (this doc).

## The design (user's Autonomous Creative XAI — adopted)

Core philosophy kept verbatim: **explain the BROKEN PREMISE and the SEARCH PATH, not the result.**
Pipeline: world model (graph) → assumption mining → assumption breaking → concept evolution →
value evaluation → self-purpose generation → XAI. Creativity = Novelty × Consistency × Surprise ×
Utility; explainability = premise-change, not result-attribution.

## Innovations added

1. **Conceptual blending as a first-class operator** (Fauconnier–Turner), alongside assumption-
   breaking. `blend(A,B)` fuses two concepts' relation sets (전화⊕카메라 → 통신+촬영 기기). The
   richest human creativity is relational recombination, not only constraint removal.
2. **Grounding-as-citation** — every creation carries `grounding`: the real triples it recombined.
   This unifies creativity with the No-환각/XAI philosophy: a creative concept's "근거" is the graph
   structure it came from. Nothing is invented from nothing; the recombination path is cited.
3. **All value terms are graph statistics, not hand rules** — Consistency = shared type / neighbor
   Jaccard; Surprise = inverse co-linkage; Novelty = relation-set not already carried by any
   concept; Utility = distinct functions covered. So it works on ANY triples and gets sharper as
   the graph grows — density-proportional by construction, not per-answer rules.

## What's built + measured

`creative_engine.py`: `blend`, `break_assumption`, graph-derived value scoring, `self_questions`
(mines the highest-leverage premises → its own problems), `invent` (autonomous ranked proposals),
and `CreativeConcept.explain()` (broken premise + search path + grounding + score breakdown).
Deterministic, No-LLM. 7 unit tests + a real-graph smoke test (runs on the live 1,012-triple
candidate graph; every output cites real triples and explains its broken premise).

Verified: `blend(전화,카메라)` (same type, rarely combined) scores above the incoherent
`blend(자동차,감자)` (disjoint types → consistency 0, rejected) — creation ≠ random.

## Honest answer to "규모만 키우면 조 단위로 되나?"

Creation quality is bounded by the graph's **relational richness**, not node count alone. The
current real graph is ~90% IS_A (plus noise like "2 IS_A 영화"), so `invent()` is dominated by
IS_A-breaking — correct but shallow. Compelling blends need functional/causal relations
(USED_FOR, ENABLES, HAS_PART, CAUSES). So the scaling law is **density × relational diversity ×
representation dimension**, not scale alone. Enriching relation TYPES (not just adding IS_A nodes)
is the highest-leverage next step for creativity.

## Roadmap (honest)
- Enrich the learner to extract functional/causal relations, not mostly IS_A → unlocks real blends.
- Feed `invent()` outputs into the candidate store as proposed concepts (operator-reviewed), and
  name/realize them via the holographic surface generator — closing creation → expression.
- `break_assumption` + `self_questions` already give autonomous problem generation; a meta-loop
  (learn which premise-breaks score highest) is the next autonomy step.

Not a fluent free-text LLM yet — it invents CONCEPTS (relation structures) with grounded
explanations; fluent naming/prose needs the surface generator to mature + a richer graph.
No push / no deploy.
