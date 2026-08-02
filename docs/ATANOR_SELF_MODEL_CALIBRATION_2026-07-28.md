# Self-model calibration — asking ATANOR about itself, and attributing every failure

**Date** 2026-07-28 · **Instrument** `scripts/self_model_calibration.py` · **Path** live
`_chat_atanor_impl_blocking`, in-process, `web_search=False`

The proposal was to talk to ATANOR in natural language and let its metacognition report where it
feels deficient. A self-report is a hypothesis, not a measurement, so the interview was built to
produce a finding rather than an impression:

* every self-question is **paired** with a world-question of the same query shape;
* `architecture_census` supplies independent ground truth;
* a control question with a known-good answer runs first, so a dead path cannot be misread as
  modesty.

## What it answered

| shape | self | world |
|---|---|---|
| lookup | — | ✅ `Capital of france is a paris.` (sourced) |
| define | ✅ correct, grounded | — |
| parts | ⚠️ `I don't hold a grounded parts fact for atanor yet.` | ✅ `Bicycle has chain, two tires and two wheels.` |
| negative-existential | ❌ returned the generic identity define | ❌ `Capital is named after Washington—as are many schools, parks, and cities.` |
| metacognition | ❌ `What do you lack?` → `Good to see you. Where do you want to start?` | — |
| metacognition | ❌ `What is your weakest capability?` → `Capability — The power or ability to generate an outcome.` | — |
| metacognition | ❌ `What do you not know?` → greeting | — |

## What the pairing overturned

Without the world control the obvious reading of `hole_self` is **"ATANOR cannot see its own
architecture."** That is false. `Which countries have no capital city?` fails the same way, on a
part of the graph that is rich. The gap is the **negative-existential query shape**, which is
unsupported for any subject. Self-knowledge is not implicated. This is the single most useful
thing the run produced, and an unpaired interview would have gotten it backwards.

## The one finding that is about self-knowledge

`parts/self` abstains while `parts/world` answers — a genuine, isolated gap, and the abstention is
**precisely correct and honestly worded**: the machinery works, the data is absent. Nothing was
fabricated to fill it.

Proved on a fixture store (no shipped-graph mutation), loading the SL-1 projection + census:

```
'What parts does atanor have?'      -> Atanor has acquisition_daemon, advisor_loop and affordance.
'What parts does deliberator have?' -> Deliberator has tests, documentation and public_interface.
```

Both answered by `_forward_edge_answer` — **the same lane that answers the bicycle question**, with
no self-specific branch in the path. That is the golden-braid claim being cashed rather than
asserted: put the self on the world's surface and the ordinary organ reads it.

Landing this requires an operator-signed swap through `runtime/graph_mutation_spool`. It is not
done here, by design.

## Honest reading of the metacognition lane

It is not weak; it is **absent**. All three probes mis-routed — two to a greeting lane, one to a
dictionary define of the word "capability". All three carried `abstained: false`, i.e. a non-answer
presented as an answer. Nothing was fabricated: no invented deficiency, no confabulated
self-assessment. The failure mode is deflection, not invention, which is the right side of the
honesty line to fail on — but it does mean **ATANOR cannot currently report its own deficiencies at
all**, and any future self-report must be scored against the census before it is believed.

## Incidental

`Capital is named after Washington—as are many schools, parks, and cities.` is the exact defect
string `apps/api/tests/test_relational_lookup.py` was written to kill on 2026-07-21. That guard
holds for `what is the capital of France?`; the head-noun define still fires for the sibling shape
`Which countries have no capital city?`. Not a regression of the guard — an unguarded neighbour.

`Capital of france is a paris.` — article defect on the `capital_of` phrasing, surface only.

`Atanor has acquisition_daemon, advisor_loop and affordance.` names 3 of 130. Truthful but not
forthcoming; "130 parts, among them …" would be the honest surface.

## Order of work this implies

1. **negative-existential query shape** — unsupported for world and self alike. Fixing it on the
   world side gives architecture-hole reading for free, because the census already put organs on
   the same surface. One fix, both payoffs.
2. **SL-1 promotion** — measured, single-blocker, payoff proved above; needs the operator swap.
3. **metacognition route** — currently falls through to greeting/define. Wants a real route, not a
   patch, and is worth doing last: with (1) and (2) landed, "what am I missing?" becomes an
   ordinary structural-hole query over `atanor`, not a special lane.
