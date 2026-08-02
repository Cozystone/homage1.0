# One pattern-recognizer over one world model — the plan that retires query lanes

**2026-07-28 · owner directive.** "사람처럼 하나의 통합된 '패턴 인식 및 세계 모델'이 필요해. …
우리가 모든 질문에 대해 쿼리를 일일이 부여해줄 수 없잖아. 그건 결국 손목록이 될 거야. 현재로써는
보조바퀴 정도로 생각하고, 사람처럼 어떤 질문이든 관측과 예측 오차로 풀어내는 세계모델을 만들며
떼어주자."

This document is the plan for that. It supersedes the idea of "fixing the negative-existential
query" as a lane; that fix falls out of phase W0 as an ordinary composition.

## 1. The measured diagnosis

`parse_relational_shape` (packages/base_brain/relational_lookup.py) is 19 compiled regexes in 8
arms. But the ceiling is not the count — it is the RETURN TYPE:

```python
{"rel": ..., "rel_norm": ..., "entity": ..., "core": ..., "kind": ...}
```

A flat (relation, entity) pair. There is no slot for an operator (absence, count, comparison), no
way for a TYPE to be the subject, no way to nest. "Which countries have no capital city?" cannot
be *represented*, so no amount of additional arms can route it. Every new arm is one more entry in
the hand list the owner named.

Meanwhile the operators already exist:

| operator | where it already lives |
|---|---|
| extension of a type ("all countries") | `structural_gaps` argsort-groupby over `is_a` |
| projection of a relation over a set | `structural_gaps` `has_rel` boolean lookup |
| set difference / absence | `structural_gaps` — coverage holes ARE `EXTENSION − PROJECT` |
| multi-hop closure | spreading activation (`brain-like-reasoning`) |
| temporal order/interval | block-universe timeline + event-transition graph |
| forward simulation | SPLATRA JEPA rollouts (v0.2, rollout-stable) |
| verification membrane | conformal gate · TMS · physics-truth |

**One sentence: the operators exist; composition does not.** The question the owner quoted —
countries ∘ capital ∘ absence assembled into one scene, the difference read off — is exactly an
`EXTENSION − PROJECT` the codebase already computes for its own curiosity, unreachable from
language because language parses into a shape with no room for it.

## 2. Is this the universal 4D spacetime world model? — half of it

Two layers, one stack. Conflating them builds the wrong thing first.

* **Layer A — SCENE (composition).** One typed representation of what an utterance describes:
  entities, types, relations, states (including absence), quantities, time spans. Assembled by
  CONSTRUCTIONS (learned form↔meaning pairings — `construction_bank`), not by shape regexes.
  Evaluated by a small closed algebra. This answers concept questions. It is set algebra, not
  physics; a perfect 4D simulator alone would still not answer "which countries have no capital".
* **Layer B — 4D SUBSTRATE (prediction).** The block-universe timeline, the event-transition
  graph, and the JEPA/SPLATRA predictive core. This GROUNDS the scene: entities become tracks,
  relations become interactions, and *prediction error against observation* becomes the learning
  signal language alone never supplies.

The owner's sentence contains both: "하나의 **시공간적 장면**으로 조합하여(=B의 표면 위에서) 즉석에서
**인지적 차집합**을 떠올립니다(=A의 연산)."

The graph is the world model's *symbolic memory* (its timeless slice); the timeline is its
*history*; JEPA/SPLATRA is its *simulator*. SCENE is the lingua franca over all three. A question
is a **condition** placed on the world model; an answer is a **readout**; learning is the error
between predicted and observed readouts. That is 예측→관측→오차 applied to language, not only to
vision — and it is why this is one organ, not a mode switch: the same conditioning machinery runs
whether the input is a question, a percept, or an internal hypothesis. Irrelevant input simply
yields no condition (None), per the one-model doctrine.

## 2.5 Final form (owner-confirmed, 2026-07-28)

The owner's synthesis, adopted as the canonical shape — a 3-layer SINGLE engine, not two modules
wired together:

1. **융합 표상 공간** — entities, concepts, spacetime coordinates, properties as the same
   state-vectors/nodes. No input-type dispatch at the door: a language question, a falling-cup
   video, a code file all land on one graph/embedding surface.
2. **시공간 예측 & 연산 동역학** — on that surface, causal/physical input runs the sandbox
   simulation (predict state B from state A + action); conceptual/logical input runs the algebra
   (extension × projection × complement). State-change and set-difference on the same substrate.
3. **차집합·투영 자율 평가기** — one verifier currency: logical readouts and physical rollouts are
   both scored as prediction error against internal knowledge / external observation. Error → 0
   confirms; error > 0 is formalized into a HOLE — in knowledge *or in architecture* (the census
   gives the latter its coordinates) — and drives surgery.

Two calibrations, so the claim stays inside the honesty line:

* "같은 연산기" is today **same substrate + same currency**, two computations. The route to a
  literally-single operator is VSA/FHRR (superposition = sets, binding = dynamics, one vector
  space) — `vsa_reasoning` / `holographic_fold` are the candidate organs. Until that is measured,
  say substrate, not operator.
* "오차 0 → 확정" is necessary, not sufficient: zero error against wrong internal knowledge is
  still wrong (faithful-to-wrong-source is our known residual). The membrane — conformal, TMS,
  physics-truth, k-source consensus — remains the final gate on every confirmation.

## 3. Training wheels, and how they come off

The regex arms are not deleted on day one — they are DEMOTED, per `rules-are-training-wheels`:

1. Each lane's firing is already logged by the flywheel logger as (question → fired intent →
   router shadow guess → gold). The lanes ARE the teachers. This wiring exists (dual_brain.py).
2. The scene path runs as a CO workspace bidder beside them, logging its own parse and readout.
3. A wheel comes off (lane demoted to teacher-only, then removed) when the scene path matches or
   beats that lane on its own logged gold — `router_readiness` is already the gauge. Removal is
   per-lane and measured, never a big-bang rewrite.

The scene layer must never become the 20th regex arm wearing a trench coat: constructions are
DATA (learned, promotable through the ordinary candidate gate), not code branches. A new question
shape is a new composition or a new construction — never a new lane.

## 4. Phases

* **W0 — scene + graph evaluation (now).** `Scene` schema; closed algebra (EXTENSION, PROJECT,
  COMPLEMENT, INTERSECT, COUNT, EXIST, LOOKUP); evaluator over the live TripleStore; seed
  constructions covering today's regex shapes plus quantified/negative-existential composition.
  Gate: "which countries have no capital city?" and "which atanor organs have no tests?" answered
  by the SAME organ with certificates, zero self-specific branching (census already put organs on
  the world surface). Wire as a CO bidder; flywheel logs on.
* **W1 — wheel removal.** Per-lane router_readiness measurement; demote lanes the scene path
  dominates; surface the scoreboard in the proof docs. Constructions begin absorbing paraphrase
  variety from logged traffic (learned, not hand-added).
* **W2 — temporal/dynamic scenes.** TIME slots condition the event-transition graph and JEPA
  rollouts; "what happens if/after X" becomes readout of a predicted trajectory, verified by
  physics-truth; readout errors feed the gap ledger → acquisition daemon (prediction error as
  curiosity pressure — the loop that makes the model SELF-improving rather than hand-fed).
* **W3 — perception fusion.** The same Scene emitted from percepts (OWLv2 objects, SPLATRA
  state), so language and perception condition one world model and MSH-style exams stop being
  text-only.

Standing constraints throughout: No-LLM, English-only, 작화0 (readouts carry certificates; an
unevaluable scene abstains with its unbound part named), membrane verification on every readout,
operator gate on any store mutation.

## 5. What this dissolves (rather than fixes)

* the negative-existential gap — W0 composition, no lane;
* metacognition ("what do you lack?") — with SL-1 landed, it is `EXTENSION(atanor_organ) −
  PROJECT(has_a·tests)` over the self's own rows: an ordinary scene, which is why the metacog
  route is built AFTER composition, not as a special lane before it;
* the "one question, one query" treadmill the owner refused — new shapes become compositions;
* the self/world split in the answer path — one evaluator serves both, which is the golden-braid
  claim cashed at the query layer.
