# ATANOR Language / Reasoning Engine Contract

> What "the language engine runs perfectly, per our philosophy" means. This is the
> definition of done and the interface the rest of the system (incl. SPLATRA) relies on.
> English is completed first; Korean reuses the same pipeline + Korean morphology.

## Hard philosophy constraints (never violate)

- **No external LLM / sLLM** for generation. Answers come only from ATANOR's own
  base/local/cloud graph and learned constructions. Enforced flags on every answer:
  `external_llm=false`, `external_sllm=false`, `external_llm_used=false`,
  `external_sllm_used=false`.
- **No rule-based canned answers.** Surfaces are realized from the graph, not
  pulled from a hand-authored answer table. (`rule_based_answer_used=false`.)
- **Honest abstention.** If there is not enough verified evidence, say so plainly
  and do not fabricate. Abstaining is a valid, first-class outcome.
- **No silent mutation.** Local Brain write / Cloud promotion / candidate promotion
  require an explicit user-approval gate. (`local_brain_write=false`,
  `production_store_mutated=false`, `candidate_promotion=false` on read paths.)
- **Readable text stays DOM text.** The engine emits plain text; particles never
  carry the words a user must read.

## Definition of done (gates)

A philosophy-complete answer pipeline must, for every query, produce:

1. **A fluent, graph-grounded surface** (English first) — aggregated, article-correct,
   pronoun-using; no subject repetition; no language leakage. (M1 — done; M1.5 polish.)
2. **Honest grounding state**: `grounded | base_brain | abstained`, with a real
   reason when abstaining.
3. **Honest confidence**: derived from evidence count/quality, not a fixed constant. (M5)
4. **A `scene_grounding` block** classifying the verified evidence as abstract
   (text-only) vs concrete (scene-eligible). (M4 — see below.)
5. **No hand-authored answer strings on the path.** (M3)

Done = the above are locked by golden tests, the English benchmark (en_001–010)
improves, and `false_confident = 0`.

## The `scene_grounding` interface (bridge to SPLATRA)

Every answer result carries:

```jsonc
"scene_grounding": {
  "eligible": boolean,   // true ONLY if verified evidence has concrete entity + (spatial OR motion)
  "basis": string,       // why: "abstract_definition_no_entity_or_motion" | "concrete_entity_with_motion" | ...
  "entities": string[],  // concrete objects found in verified evidence
  "spatial":  string[],  // spatial relations linking entities
  "motion":   string[]   // motion / path cues
}
```

Rules:
- Abstract definitions ("X is a kind of Y", "gravity is the attraction between
  masses") → `eligible:false`. Explain in words; SPLATRA shows only ambient field.
- Concrete grounded events ("an apple fell from the tree toward Newton") →
  `eligible:true` with the apple/tree entities, the from→toward path, the fall motion.
- The extractor is **deterministic and inspectable** (lexicon + relation rules over
  the evidence sentences). This is linguistic *analysis*, not answer *generation*,
  so it does not violate the no-rule-based-answer constraint. It is conservative:
  when unsure, it abstains (`eligible:false`).

## Build order

M1 (done) → **M1.5 polish** → **M4 scene_grounding** (interface for CODEX) →
**M3 retire canned answers** → **M2 multi-hop reasoning** → **M5 honest confidence +
verified English corpus growth** → Korean.

See `packages/base_brain/zero_user_answer.py` (realizer),
`packages/base_brain/scene_grounding.py` (M4), and
`apps/api/app/routers/dual_brain.py` (`/api/chat/atanor`, conversation fallback).
