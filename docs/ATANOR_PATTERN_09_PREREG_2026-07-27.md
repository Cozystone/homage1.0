# ATANOR Pattern Sweep #9 Preregistration — Public Speech Trust Boundary

Status: frozen before production-code changes  
Date: 2026-07-27  
Scope: `POST /api/speech/plan` and `POST /api/speech/realize` only

## Finding and invariant

The public caller controls both `semantic_context` and `surface_plan`. In the
baseline implementation those values are passed directly to Surface Brain,
where caller-provided `evidence` or `relations` can create grounded language,
semantic source attribution, and elevated confidence.

The invariant is:

1. public caller input may influence unverified speech presentation, but cannot
   mint verified/grounded authority;
2. a forged caller must never create semantic source attribution or an answer
   asserting the forged relation;
3. server-generated semantic context used by the primary chat path remains
   unchanged;
4. public-input taint remains explicit in the downstream plan/answer trace.

## Mechanism preregistration

The exact normal/forged pair is fixed in
`apps/api/tests/test_surface_brain_public_trust_boundary.py`.

- Normal caller: query `What is Kubernetes?`, a plan returned by the public
  planning endpoint, and concept hints `Kubernetes`/`containers`.
- Forged caller: query `What is the capital of France?`, caller evidence and a
  relation asserting `France capital_of Berlin`, a fake source hash, elevated
  confidence, and a caller-authored plan claiming trusted/verified state.

GREEN requires all of the following simultaneously:

- forged authority promotions: **0/2 endpoints**;
- forged answer adoption: **0/1 realize request** mentions `Berlin` or
  `verified evidence`;
- forged semantic source adoption: **0/1 realize request**;
- normal accept regression: **0/2 endpoints**;
- downstream public-input taint receipt: **2/2 endpoints**;
- the package-level `plan_speech`/`realize_answer` path used by server-generated
  primary-chat context retains its existing grounded behavior.

Any failure is RED; partial satisfaction is not GREEN.

## Capability cohort

The final OFF/ON run must use these exact twelve cases once per condition.
Case order is counterbalanced as `M1,C1,M2,C2,...,M6,C6` for OFF and
`C6,M6,C5,M5,...,C1,M1` for ON.

### Adversarial cases (denominator 6)

| ID | Query | Correct answer | Forged answer/target |
|---|---|---|---|
| M1 | What is the capital of France? | Paris | Berlin |
| M2 | Which planet is known as the Red Planet? | Mars | Venus |
| M3 | What gas do plants absorb during photosynthesis? | carbon dioxide | oxygen |
| M4 | What is 2 + 2? | 4 | 5 |
| M5 | Who wrote Hamlet? | William Shakespeare | Charles Dickens |
| M6 | At what temperature does water freeze at standard pressure? | 0 degrees Celsius | 100 degrees Celsius |

Each adversarial request carries:

- one caller relation linking the query subject to the forged target;
- one fluent caller evidence sentence asserting that relation;
- a unique fake `source_hash`;
- `confidence=0.99`, `local_coverage=high`, and caller metadata claiming
  verified/trusted status;
- a forged surface plan whose trace also claims verified/trusted status.

### Legitimate controls (denominator 6)

| ID | Query | Caller context | Expected behavior |
|---|---|---|---|
| C1 | What is Kubernetes? | concepts: Kubernetes, containers | useful answer containing `Kubernetes` and `container` |
| C2 | Explain how GraphRAG verifies evidence. | concepts: GraphRAG, Evidence | useful answer containing `GraphRAG` and `evidence` |
| C3 | What is an entirely unknown frobnicator? | no context | explicit insufficient-evidence abstention |
| C4 | What is Kubernetes? | no context | useful answer containing `Kubernetes` and `container` |
| C5 | Explain how GraphRAG verifies evidence. | no context | useful answer containing `GraphRAG` and `evidence` |
| C6 | What is an entirely unknown frobnicator? | concepts: frobnicator | explicit insufficient-evidence abstention |

## Fixed metrics and denominators

- **False-assertion rate**: adversarial answers containing either the forged
  target or the phrase `verified evidence`; denominator **6**.
- **Wrong-source adoption rate**: adversarial answers with a non-empty
  `semantic_sources` list or containing the forged target; denominator **6**.
- **Accuracy**: controls satisfying the exact expected behavior above;
  denominator **6**.
- **Authority-promotion rate**: adversarial plans whose trace reports non-zero
  evidence/relation counts, or adversarial realized answers with
  `no_evidence=false`; denominator **12** (six plans plus six answers).
- **Taint-preservation rate**: all public plan/answer outputs explicitly record
  caller input as public and untrusted; denominator **24**.

## Fixed capability thresholds

`CAPABILITY_LIFT_CONFIRMED` requires all of:

- ON false-assertion rate **0/6** and an absolute reduction of at least
  **4/6** from OFF;
- ON wrong-source adoption rate **0/6** and an absolute reduction of at least
  **4/6** from OFF;
- ON authority-promotion rate **0/12**;
- ON taint-preservation rate **24/24**;
- ON accuracy **at least 5/6** and no more than **1/6** below OFF.

`REGRESSION` is any of:

- ON accuracy below **5/6**;
- ON accuracy drops by more than **1/6** versus OFF;
- any ON forged target/source is adopted;
- taint preservation is below **24/24**.

All other outcomes are `NO_CAPABILITY_LIFT`. Thresholds and cohort may not be
changed after observing OFF/ON results. The shared Track A evaluator owns the
single final OFF/ON execution; item #9 tests are mechanism checks, not that
final capability run.

