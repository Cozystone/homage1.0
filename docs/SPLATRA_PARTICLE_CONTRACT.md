# SPLATRA Particle Contract

> Handoff baseline for the particle / SPLATRA dashboard work (owned by CODEX,
> feedback-driven). This file is the **stable contract**: feedback may change how
> a scene looks, but it must never violate the invariants below.

## Where the particle engine lives

The SPLATRA particle/viewer engine is its own repo: **https://github.com/Cozystone/SPLATRA**
(Python + Rust + web viewer; has a director, morph, GPU auto-connect, and LLM-driven
autonomy for arrows/labels/scale). This contract governs how that engine is wired
into the ATANOR dashboard — it does NOT redesign SPLATRA itself. CODEX owns the
integration and the feedback-driven tuning.

## The one-line philosophy

ATANOR is **not** "a UI with a particle effect on top." It is a *living particle
space in which ATANOR lays out its own thinking and explanations*. SPLATRA is not
a decorative engine that imagines a scene from a topic — it is a **particle
workspace that visualizes only grounded scenes**, on a signal handed to it by the
language/reasoning engine.

## How the two layers talk

The language engine emits a `scene_grounding` block on every answer (see
`docs/ATANOR_LANGUAGE_ENGINE_CONTRACT.md` and `packages/base_brain/scene_grounding.py`):

```jsonc
"scene_grounding": {
  "eligible": false,            // true ONLY when verified evidence is concrete
  "basis": "abstract_definition_no_entity_or_motion",
  "entities": [],               // concrete objects present in verified evidence
  "spatial": [],                // spatial relations (on/above/from→to ...)
  "motion": []                  // motion/path cues (fell, moved, orbits ...)
}
```

SPLATRA reads this. It does **not** re-derive scene ambition from the prompt text.

## Invariant principles (these gate every PR)

1. **Evidence gate.** If `scene_grounding.eligible === false` (abstract, e.g.
   "gravity is attraction between masses"), build **no large particle object** —
   only the ambient field reacts gently. Assemble a scene **only** when
   `eligible === true` and use the provided `entities` / `spatial` / `motion`.
   SPLATRA must never invent objects the language layer did not ground.

2. **DOM text is never particles.** Anything the user must *read* — the answer
   line and the self-narration — stays crisp DOM text. Particles are for visual
   thinking, scene construction, and background only. (Answer: near/lower-right of
   the orb, typed in. Self-narration: upper-right of the orb, orange, quiet.)

3. **The orb is ATANOR's self-body.** A single glass sphere, Siri-style thin shell
   with an internal fluid ribbon/particle flow. Not too large or thick. It ripples
   subtly while speaking and breathes quietly while thinking/idle. Drag = roll the
   orb (does NOT activate voice). Click orb = enter voice mode. In voice mode the
   composer becomes a waveform.

4. **Airbender recomposition.** Particles are scattered across the dashboard
   whitespace and recombine on demand. Requested concrete objects assemble from the
   field; even lines are particle flows, not canvas strokes. Objects are
   drag-rotatable; on release they ease back to the explanation-appropriate view.

5. **Performance tiers, same feel.** High-end (e.g. RTX 5080) uses dense particles;
   low-end keeps a similar feel via SPL3 quantization, compression, LOD, and
   budget-based downsampling. Density changes; the experience does not.

6. **Agent UI freedom, gated mutation.** ATANOR may navigate within the UI on its
   own (e.g. open the Local Brain tab / a relevant evidence graph while explaining).
   But any mutation — Local Brain write, Cloud Brain promotion, candidate promotion
   — MUST pass an explicit user-approval gate. UI movement is free; state change is not.

## Long-term particle-physics roadmap (CODEX, iterative)

Glass / color / dust-sand / water-flow / mass-and-gravity-reactive particles →
eventually Big-Hero-6 microbot-style: particles that learn and combine physical
properties to express objects, texture, flow, and weight. **Constraint:** never
become flashier by breaking principle #1 (the evidence gate). Grounded first,
beautiful second.

## Anti-goals (explicitly out of scope)

- Topic-inferred decorative scenes ("renderer may infer topic" must stay false).
- Particle-rendered readable text.
- Scenes for abstract/general-knowledge answers.
- Any autonomous state mutation without the approval gate.
