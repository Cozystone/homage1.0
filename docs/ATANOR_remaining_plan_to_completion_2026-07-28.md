# Remaining plan to completion, re-anchored 2026-07-28

Coordinates: `docs/ATANOR_canonical_masterplan_v4.md` (canonical execution spine, 2026-07-25) and
its G0–G9 gates / V0–E6 evidence ladder. This document does not replace it. It records where
2026-07-28's work landed on that spine, one root defect found today that changes priority
ordering, and the honest remaining sequence.

## 1. Where today's work landed

| Work | Canonical domain | Evidence stage | Note |
|---|---|---|---|
| SL-1 self-projection promoted to shipped graph | 6 Operational self / 2 World ledger | **M3** | Live answer path verified: `Atanor has acquisition_daemon, advisor_loop and affordance.` Not a capability lift — a representation landing. |
| Operator boundary provisioned (Ed25519) | 1 Membrane and governance | **operational** | Closes the promotion-law step 9 bypass for shipped graphs. Reusable; next promotion needs only steps 3–6 of the procedure. |
| Scene algebra + composer, wired as fallback lane | 3 Semantic compiler | **M3** | Negative-existential and counting questions now answer live. Old lanes provably untouched (never invoked when the prior lane resolves). |
| `dropped_qualifiers` abstention | 3 Semantic compiler / honesty | **M2** | Prevents confidently answering a narrower question than the one asked. |
| Two-population finding | 2 World ledger | **measurement** | Post-hoc entity resolution measured impossible; nothing built. |

None of this is E4 or above. Per §2.1, mechanism is not capability.

## 2. The root defect found today, and why it re-orders the plan

The Wikidata ingest is **keyed by English label, not by QID**. Measured:

* `France` maps to ≥12 distinct QIDs in the label store; every label probed hit the query limit.
* 2,945,206 of 92,416,762 labels (3.2%) are shared by more than one QID — and the shared ones are
  exactly the common entities queries ask about.
* The collapse is visible in the shipped graph:

```
Athens  country    -> Canada, Greece, United Kingdom, United States, Zimbabwe   (5 countries)
France  country    -> Belgium, Germany, Ireland, Italy
Athens  located_in -> 35 values incl. Auckland Art Gallery, Birmingham Museum
```

`Athens` is not one node with noisy edges. It is **several different Athenses merged into one
node** because they share a label. Same for `France` (the country, plus ships, people, communes).

This is the single upstream cause of several things previously treated as separate problems:

1. the two disjoint populations (`france` vs `France`) — a symptom, not the disease;
2. the cross-link noise the relational precision gate exists to suppress (`_FUNCTIONAL_RELS`
   single-valued resolution) — that gate is **papering over label collision**;
3. any complement/negative-existential readout resting on a merged node;
4. why post-hoc entity resolution is impossible: the evidence was destroyed at ingest, not merely
   unrecorded.

It also invalidates the label-based join measured earlier today (52/140 orphans, 0 false positives
on the sample). The sample was clean, but the mechanism is not safe at scale, because joining on
label would compound exactly the merge that caused the problem. **Do not build it.**

### What this changes

The canonical plan's §9 immediate critical path is an **A-track**: typed compiler profiles →
independent E4 → broad E5 on MMLU-Pro/GPQA. That sequencing is unchanged and remains correct.
But every one of those profiles reads the shipped graph, and a label-merged graph puts a ceiling
on grounded accuracy that no compiler profile can lift. A `scalar_quantity_resolve` profile
reading `Athens.country` gets five countries.

So the graph-identity repair is not a new competing priority — it is a **precondition the A-track
inherits**, and it should be sized and gated before the A-track's error distribution is used to
justify the next typed family (§9.5).

## 3. Remaining sequence

### Immediate — finish what today opened

**I1. Curriculum signal wiring.** `compose()` returns the reason a question could not be read;
`answer_bridge` discards it (`scene, _why = compose(...)`). Until it is logged, the composer cannot
widen from traffic and the "training wheels come off by measurement" plan (§3 of the scene plan doc)
has no data. Small, and it gates W1.

**I2. Reverse index (predicate → subjects).** Large-extension types cost 45–280s; currently
survived by a wall-clock timeout that silently falls back. Without it the scene algebra is
restricted to small types, which is a capability ceiling disguised as a latency setting.

### Graph identity — the precondition

**GI1. Scope the damage.** How many shipped subjects are label-merges? Measure by re-deriving, for
a sample of high-degree subjects, how many distinct QIDs share their label, and how many of their
single-valued relations hold conflicting values. This is measurement only; it decides whether GI2
is a re-ingest or a targeted repair.

**GI2. QID-keyed re-ingest (operator-gated).** Key entity nodes by QID, carry the English label as
an attribute, and emit `alias`/`same_as` from upstream identity data — never from spelling. The
label DB (`D:/wikidata/wd_labels_v2.sqlite`, 6.7 GB, QID→label intact) makes this re-runnable
without re-downloading the 70 GB dump. Goes through the normal mutation-batch → signed promotion
chain now that the operator boundary exists.

**GI3. Retire the precision gate's workaround** only after GI2 clears, and only if measurement
shows the single-valued conflicts are gone. It is a training wheel over a data defect; removing it
before the defect is fixed would regress answers.

### W-track — the unified scene/world model (docs/ATANOR_unified_scene_world_model_plan.md)

**W1. Wheel removal.** Per-lane `router_readiness` measurement; demote regex lanes the scene path
dominates to teacher-only, then remove. Lane by lane, never a big-bang rewrite (§2.6).

**W2. Temporal and dynamic scenes.** TIME slots condition the event-transition graph and JEPA
rollouts; "what happens after X" becomes a readout of a predicted trajectory, verified by
physics-truth. **This is where the self-improvement loop closes**: readout error becomes curiosity
pressure feeding the gap ledger and acquisition daemon. Maps to canonical G3.

**W3. Perception fusion.** The same Scene emitted from percepts (OWLv2 objects, SPLATRA state), so
language and perception condition one world model. Maps to canonical G3/G8.

### Then the canonical A-track (§9), unchanged

Typed compiler profiles → independent E4 evaluator boundary → broad E5 precommit on authenticated
MMLU-Pro / corrected GPQA / fresh hidden holdout → G7 benchmark ascent → G9 final seal.

## 4. What is deliberately NOT being built

* **Post-hoc entity resolution** — measured: alias covers 2%, neighbourhood overlap 0.000,
  relation-profile similarity does not discriminate (0.778 for `country`/`Protein`). Building it
  would assert identity on no evidence.
* **A metacognition lane.** `Which atanor organs have no tests?` fails because Scene has no
  two-hop qualifying restriction, not because metacognition is missing. Widening W0 composition
  resolves it; a dedicated lane would be the hand-list the owner forbade.
* **Label-based graph joins** — see §2.

## 5. Open defects flagged, not fixed

Both confirmed pre-existing via `git stash` and unrelated to today's changes:

* `resolve_relational` routes `what is the capital of France?` through a ConceptNet compound-node
  artifact into the define lane (`intent: "define"`, expected `"relational"`).
* Relational router held-out accuracy has drifted to 0.731 against a ≥0.9 gate; the held-out set
  dates to 2026-07-21 and three graph promotions have landed since.

## 6. Honest position

Nothing today moved a benchmark. The scene algebra makes a class of question answerable that was
previously unrepresentable, and SL-1 makes the system's own architecture readable by the organ that
reads world knowledge — both are representational groundwork the canonical plan calls M3, and both
must still clear E4/E5 through an evaluator ATANOR cannot modify before any capability claim.

The most valuable output of the day is arguably negative: three separate resolution mechanisms were
measured and rejected rather than built, and the root cause turned out to be an ingest key
decision, not anything in the answer path.
