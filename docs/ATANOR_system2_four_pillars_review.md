# Review: Gemini's "4 pillars for human-like deep intelligence" vs ATANOR (2026-07-20)

The owner relayed a Gemini analysis: to move from a System-1 reactive machine to a System-2 deep
intelligence you need (1) an internal simulation engine, (2) a causal world model, (3) metacognition
+ dynamic compute, (4) continuous plasticity without catastrophic forgetting. Honest review below —
what is RIGHT, where the framing is LLM-shaped and must be translated for a No-LLM graph engine, and
what ATANOR already has vs must build.

## Verdict up front
The four pillars are a genuinely good decomposition and I recommend adopting the frame. The striking
thing: ATANOR already has a partial organ for ALL FOUR, and for two of them the graph-native design
is *structurally* closer to the goal than an LLM is. The gap is not "we lack these ideas" — it is
"three of the four are v0/partial and need the same treatment we just gave temporal reasoning:
measured, sealed, learned-not-hardcoded." The one genuinely new build is counterfactual reasoning,
which sits directly on top of the causal field we built today.

## Pillar 1 — Internal simulation engine (System-2: search + self-correction before output)
- **LLM framing:** MCTS/tree-search over next-token rollouts; self-correct before emitting.
- **What ATANOR has:** `mirofish_deliberation` (real multi-step deliberation loop), `deliberator`
  (System-2 back-chaining for GPQA), `reasoning_vm` (predicate algebra), the realtime hear→fuse→
  think→**doubt** loop with a self-doubt gate, and — critically — the No-LLM generative-leap loop:
  *intuition proposes → verifier gates → only verified leaps are asserted*. That IS search + self-
  correction; we just do it over graph operations, not tokens.
- **Honest gap:** it is not yet a UNIFIED rollout that every answer passes through. Today deliberation
  is invoked on specific hard lanes, not as the default "simulate N futures, keep the best" spine.
- **Adopt:** promote the verify-before-assert loop to a general rollout: for a hard query, expand K
  candidate reasoning paths over the graph, score each with the existing verifier/critic, emit only
  the winner. We already have the pieces (proposer + frozen-oracle critic); the work is making it the
  default control flow, gated by pillar 3.

## Pillar 2 — Causal world model (causality, not correlation; counterfactuals)
- **This is literally today's work.** The learned temporal-causal precedence field
  (`packages/temporal_reasoning`) is a first causal-order world model: it learns "dispatch precedes
  arrive" from the world, not from a rule, and judges a specific timeline against it.
- **What was missing until now:** counterfactual reasoning ("if X instead of A, would the paradox
  vanish?"). That is a small, honest addition ON TOP of the field, and I am shipping a v0 of it in
  this same change (`anomaly.counterfactual`): edit one event's time/predicate, re-run the causal
  judgment, report what flips. This is the counterfactual primitive the pillar asks for.
- **Bigger arc:** the world model must widen beyond temporal order to full causal edges
  (caused_by / enables / prevents) learned the same self-supervised, sealed-holdout way. The
  temporal field is the template; the method generalizes.

## Pillar 3 — Metacognition + dynamic compute (know what you don't know; think longer on hard things)
- **What ATANOR has:** the 3-tier mind (R1 capability_tier detection + R1–R5 tier-aware router), the
  self-doubt gate, honest abstention (the entire MSH discipline is "know what you don't know and say
  so"), and confidence from the learned field (unknown vocab → no judgment, never a guess).
- **Honest gap:** compute is NOT yet allocated by difficulty. A trivial and a hard query get the same
  path. The metacognitive signal exists (confidence, tier, doubt) but does not yet *drive* how many
  rollouts pillar 1 runs.
- **Adopt (cheap, high-value):** wire the existing confidence/tier/doubt signal to the rollout budget
  — low confidence or high tier ⇒ expand more candidate paths and verify harder; high confidence ⇒
  answer directly. This is the single best leverage point: it makes pillars 1+3 one mechanism.

## Pillar 4 — Continuous plasticity without catastrophic forgetting
- **The graph-native design is a structural WIN here, and we should say so plainly.** Adding a triple
  to a knowledge graph does not overwrite other triples — there is no shared weight matrix to clobber.
  ATANOR already has: Layer-A live memory (inject a fact → recall it, no retraining), the CLS organism
  (D1 sleep consolidation, D3 curiosity), failure receipts, and learned discriminators that grow with
  data. This is exactly the "update on new experience/errors without breaking the steel structure of
  prior commonsense" the pillar describes.
- **Honest gap:** the learned sub-models (precedence field, encoders) ARE dense and can drift on
  refit. Our answer is already in-repo: frozen-oracle seals + sealed holdout + versioned refit, so a
  refit that regresses is caught, not silently absorbed. The web-roam fold + refit is the live
  instance of this loop.

## Net recommendation
Adopt the frame as ATANOR's System-2 roadmap, but translate it out of LLM terms:
- Pillar 1 = make verify-before-assert the default rollout (pieces exist).
- Pillar 2 = generalize the temporal causal field to causal edges; ship counterfactual v0 now.
- Pillar 3 = let confidence/tier/doubt drive the rollout budget (best single lever).
- Pillar 4 = already our structural strength; keep protecting the learned sub-models with sealed
  holdouts.
Nothing here asks us to abandon No-LLM; each pillar is buildable as graph + learned discriminators,
which is the whole thesis.
