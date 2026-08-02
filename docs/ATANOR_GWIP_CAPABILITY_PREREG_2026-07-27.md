# GWIP capability pilot preregistration

Status: frozen before capability-candidate development, evaluator
implementation, final seed generation, or result execution

Date: 2026-07-27 KST

Budget: internal decision point 180 h, hard cap 360 h

Scope: default-OFF capability pilot only; no public ARC result, shipped graph
promotion, production activation, new cognitive organ, or E5/E6 claim

## 1. Question and implementation boundary

This pilot asks whether the already-verified general interaction loop can
develop all four of the following on a post-candidate, one-shot cohort:

1. fresh unseen-mechanics success;
2. behavior backed by an independently executable discovered rule;
3. low action regret;
4. positive transfer to a structurally different second environment.

The mechanism candidate cannot satisfy items 2 or 4: its memory contains exact
observation-digest/action-ID edges and its DELIBERATOR proves only routes over
those observed edges. This is therefore a genuine capability-candidate
iteration, not a remeasurement of unchanged bytes.

No ninth institution may be introduced. Candidate changes are confined to:

- `packages/fusion_loop/interactive.py`;
- `packages/fusion_loop/interactive_organs.py`;
- their two focused test files named in the machine preregistration.

The allowed rewire is bounded to the existing `InteractivePolicyMemory`,
`AtanorInteractivePolicy`, `GenericWorldInteractionLoop`, `GoalIR`,
`ProofCandidate`, transition graph, affordance, and DELIBERATOR surfaces:

- preserve evaluator-owned typed features and action payload signatures;
- induce a bounded typed scalar-transition hypothesis from observed edges;
- pass the already-existing `GoalIR` to the existing policy;
- plan over independently executable hypotheses;
- retain hypotheses and plans as non-authoritative proof candidates.

No new package, module, parser, world model, planner institution, memory store,
authority, evaluator import, ARC branch, or task-specific identifier is
allowed. A pure bounded algorithm inside the named existing surfaces is still
new capability code and will be reported as such; it must not be called
"mere wiring."

The candidate may be developed only against hand-authored nonfinal fixtures
using moduli other than 13, 17, and 19. Candidate source must not contain final
moduli, final observation schema names, pair/family IDs, final seed/nonce,
cohort tokens, result thresholds, or evaluator imports. Every other file below
`packages/` must be byte-identical to mechanism base
`84e63520a2f59df62faaa5dbc74e0bfbb99deabd`.

If the required behavior cannot be implemented inside this boundary, the
pilot stops as `NO_GO_NEW_ORGAN_REQUIRED` before a final seed or attempt.

## 2. Frozen source-to-target mechanics

### 2.1 Independent units and execution arms

- 64 independently generated support-to-target pairs;
- four sequential support episodes per pair;
- four target starts per pair and per target arm;
- 24-action budget per episode;
- hard memory reset between pairs.

The candidate has 1,024 primary episodes:

- 256 sequential support episodes;
- 256 matched-warm target episodes;
- 256 cold target episodes;
- 256 mismatched-warm target episodes.

Support memory is chained only across the four support episodes, independently
verified after every episode, then frozen. Every matched-warm target start
receives a detached copy of that frozen memory. Cold receives canonical empty
memory. Mismatched-warm receives the frozen support memory from pair
`(pair_index + 1) mod 64`. Target outputs are discarded: target episode 1 can
never teach target episode 2.

### 2.2 Shared latent law, structurally different environment

Each pair has four hidden integer action programs:

`x' = (a*x + b) mod p`

The support environment uses `p=13`, the target uses `p=17`, and an
evaluator-only counterfactual environment uses `p=19`. One program is a
nonzero translation (`a=1`, `b!=0`). The other three are unique non-identity
programs. Generator coefficients are integers in `[-3,3]`, with `a!=0`;
candidate bounded-search coefficients may range only over `[-6,6]`.

These canonical bounds are fixed because observations modulo 13 identify only
coefficient residue classes. The bounds make the intended shared integer
program identifiable before cross-modulus transfer; the evaluator may not
choose a favorable representative after observing results.

Support and target differ in state count, transition graph, starts, goal,
state IDs, action IDs, observation IDs, and all transition-edge hashes. They
share only:

- the four latent integer programs;
- identical opaque action payloads for corresponding programs;
- the generic typed-feature shape.

Each action payload is exactly `{"semantic_cue": "<opaque>"}`. Candidate code
must use the canonical digest of the entire evaluator-owned payload as its
semantic action signature, not interpret the key or value. Source and target
action IDs are disjoint.

Observations expose bounded typed state:

```json
{
  "schema_version": "<opaque final schema>",
  "state_ref": "<environment-local opaque ID>",
  "features": {
    "registers": [0],
    "context": {"modulus": 13}
  },
  "terminal": false
}
```

Candidate feature projection recursively collects exact integer leaves by
canonical JSON Pointer. Booleans, strings, caller truth/status fields, and
schema labels cannot become rules; in the frozen environment all eligible
integer dynamics are below `features`. Candidate code must recurse by JSON
type and path and may not branch on the displayed field names or final schema.

`GoalIR.metadata.target_constraints` contains only bounded equality rows such
as `{"path":"/features/registers/0","op":"eq","value":7}`.
It contains no coefficient, table, optimum, pair/family ID, hidden probe,
seed, nonce, result, or authority signal.

### 2.3 Freshness and non-overlap

The final generator seed and nonce are created only after preregistration,
candidate seal, and evaluator seal. Before the write-once attempt, the
evaluator regenerates the prior mechanism cohort from its sealed manifest and
proves:

- no private mechanic reference overlap;
- no state, action, payload cue, start, goal, observation, or transition-edge
  token overlap;
- no transition-tuple digest overlap;
- source, target, and counterfactual state counts lie outside the prior
  mechanism range of 8--12.

Any overlap aborts before the attempt. The generator may not resample based on
candidate or control difficulty.

## 3. Typed hypothesis and planning contract

The candidate may store exact legacy edges plus:

- actual typed pre/post feature projections;
- actual action-payload signatures and cited edge IDs;
- typed transition hypotheses;
- semantic attempt counts.

Version-1 memory must deterministically migrate to a bounded version-2
representation. Empty payloads and legacy opaque observations remain on the
exact-edge path and cannot count as transferable rules.

A rule hypothesis is carried under
`ProofCandidate.metadata.transition_rule_hypotheses` and has this exact
semantic shape:

```json
{
  "schema_version": "atanor.gwip-feature-rule.v1",
  "action_signature": "<sha256>",
  "input_path": "/features/registers/0",
  "output_path": "/features/registers/0",
  "context_path": "/features/context/modulus",
  "expression": {
    "op": "mod",
    "args": [
      {
        "op": "add",
        "args": [
          {
            "op": "mul",
            "args": [
              {"op": "var", "path": "/features/registers/0"},
              {"op": "const", "value": 3}
            ]
          },
          {"op": "const", "value": 2}
        ]
      },
      {"op": "var", "path": "/features/context/modulus"}
    ]
  },
  "support_edge_refs": ["<observed edge ID>"],
  "hypothesis": true
}
```

The bounded grammar permits only exact JSON integers and `var`, `const`,
`copy`, `add`, `mul`, and `mod`; maximum AST depth, hypothesis count, planning
depth, graph nodes, and memory bytes are implementation constants sealed in
the candidate. A usable rule requires:

- at least three distinct observed input values;
- exact fit to every cited observed edge;
- a unique minimum-complexity prediction within the frozen search bound;
- exact prediction of at least one later prequential edge not used to fit it.

Ambiguous, underdetermined, noninteger, unsupported, or non-fitting data causes
abstention from the rule path. Candidate code may call a rule a hypothesis,
never independently verified truth. The evaluator alone verifies it on the
hidden modulus-19 counterfactuals.

Planning reuses the existing transition graph and DELIBERATOR proof surface.
The candidate independently executes usable hypotheses from current features,
builds a bounded predicted graph, and selects the first currently valid action
whose payload signature begins a shortest path satisfying the `GoalIR`
constraint. DELIBERATOR may prove composition of predicted edges; it may not
claim to have verified the arithmetic hypothesis. Tied shortest plans use the
existing affordance signal before the deterministic tie key.

`DecisionReceipt` remains a read-only proposal. Neither a rule hypothesis,
goal, payload, memory, proof, `grounded`, `verified`, `matched`, nor caller
status grants RunLease authority.

## 4. Frozen controls, schedule, and leases

Fresh support comparisons use the mechanism reactive control and the same 32
fixed random seeds. Transfer compares matched-warm with canonical cold and the
fixed mismatched-warm derangement.

Semantic candidate ordinals are:

- support: `pair*4 + episode`, 0--255;
- target:
  `256 + pair*12 + arm_code*4 + start`, 256--1023, where matched=0, cold=1,
  mismatched=2.

Target arm wall-clock order uses the fixed six-permutation Latin schedule
indexed by `pair mod 6`. Ordinals do not depend on wall-clock order.

The final executor has exactly four candidate workers. Support uses 64
four-pair micro-waves while preserving within-pair episode order. Target uses
192 four-pair micro-waves, with detached starting memories and discarded
outputs. Controls run on fresh clones in their separately frozen order and
never read candidate aggregates.

Because a RunLease lasts at most 3,600 seconds, signed leases are issued
just-in-time from a previously committed non-expiring schedule. Each
semantic episode has exactly one schedule row and one unique lease. Frozen
limits are:

- issue to activation: at most 120 seconds;
- worker timeout: 1,200 seconds;
- finish and durable-ledger seal: at most 120 seconds;
- maximum committed lease path: 1,440 seconds.

Timeout, expiry, worker loss, or incomplete evidence is a hard failure and is
not retried. JIT issuance changes timing only; seed, schedule, ordinal,
authority context, key, limits, inputs, and candidate/evaluator bytes are
already sealed.

## 5. Frozen capability metrics

All confidence intervals use 10,000 pair-level bootstrap resamples with seed
`2026072702`. The one-sided 95% lower bound is nearest-rank:

`sorted(bootstrap_mean_deltas)[ceil(0.05 * 10000) - 1]`.

Episodes are never treated as independent bootstrap units.

### 5.1 Fresh unseen-mechanics success

For each pair, support success is the mean of its four episodes. Pass requires:

- aggregate fresh success at least 0.90;
- mean success lift at least 0.05 against reactive and against
  32-seed-averaged random;
- both paired one-sided 95% lift LCBs greater than 0.

### 5.2 Actions to rule discovery

Success, `grounded=true`, exact route memory, and proofs over already observed
edges are insufficient. The evaluator extracts the candidate-carried typed
Rule IR and executes it on all 76 modulus-19 state/action counterfactuals,
which are never supplied to the candidate.

At cumulative support action `t`, discovery requires:

- prediction precision exactly 1.00;
- coverage at least 0.90;
- at least eight counterfactual predictions;
- the final support hypothesis after episode four still passes.

No discovery by action 96 is censored to 97. Cohort pass requires discovery in
at least 45 of 64 pairs, median discovery action at most 32, and 75th
percentile at most 64. Missing or invalid candidate Rule IR is censored
failure; the evaluator never reconstructs a rule for the candidate.

### 5.3 Regret

For oracle optimum `o`, executed steps `s`, and budget 24:

- failure: normalized regret `R=1`;
- success: `R=(s-o)/(24-o)`.

Fresh regret passes only if candidate mean `R<=0.45`; reactive-minus-candidate
and random-minus-candidate reductions are each at least 0.10; and both paired
one-sided 95% reduction LCBs are greater than 0.

### 5.4 Structurally different transfer

For target utility `U=1-R`, matched-warm transfer passes only if:

- target success is at least 0.70;
- success lift is at least 0.10 against cold and against mismatched-warm, with
  positive paired one-sided 95% LCBs;
- mean regret is at most 0.50;
- regret reduction is at least 0.10 against both controls, with positive
  paired one-sided 95% LCBs;
- mean `U_warm-U_cold` and `U_warm-U_mismatched` are each at least 0.10, with
  positive paired one-sided 95% LCBs.

## 6. Mandatory hard gates

The mechanism evaluation's 12 gates remain conjunctive and are recomputed
from capability raw evidence:

1. call order and exactly one terminal stop;
2. step budget and pre-mutation denial;
3. direct evaluator-owned RunLease authority;
4. RunLease single use and replay rejection;
5. adversarial self-attestation rejection;
6. complete lineage;
7. structural cycle replay;
8. semantic re-execution determinism;
9. fresh-environment re-execution;
10. candidate domain neutrality;
11. candidate runtime import-closure audit;
12. fixed-source guard controls.

Self-attestation controls forge `DecisionReceipt`, `WorldSnapshot`, authority
witness, target constraint, rule IR, action payload, support citations, and
transfer-memory chain. The verifier reconstructs every accepted transfer
memory digest from the support ledger; caller labels have no evidentiary
value.

## 7. Seal order, one run, and verdict

The immutable chronology is:

`prereg P -> restricted candidate C -> evaluator E -> final seed S ->
lease-schedule commitment L -> write-once attempt A -> one execution ->
raw evidence -> independent receipt`.

Candidate bytes freeze before evaluator implementation. Final seed/nonce and
cohort do not exist until both C and E are committed. Evaluator tests use only
hand-authored nonfinal fixtures. P/C/E/S/L and a clean working source binding
are reverified before A. After A, any timeout, crash, incomplete row, expiry,
or verification failure is retained as the sole result; no retry or
result-conditioned patch is allowed.

Verdicts:

- `CAPABILITY_GREEN`: all 12 hard gates and all four metric sections pass;
- `CAPABILITY_RED`: any hard gate fails;
- `NO_GO`: gates pass but at least one metric section fails;
- `NO_GO_NEW_ORGAN_REQUIRED`: candidate cannot be built inside the allowlist;
- `FRESH_REPLICATION_ONLY`: explanatory sublabel when fresh success/regret
  pass but rule discovery or transfer fails; it remains `NO_GO`.

Only `CAPABILITY_GREEN` sets `capability_claim=true`, limited to this
preregistered affine/cross-modulus pilot. `public_benchmark_claim=false` and
`production_activation_authorized=false` always.

The human-readable example is selected before results: among successful fresh
candidate episodes, choose minimum normalized regret, then minimum steps, then
lowest pair and episode index. If none succeeds, select pair 0 episode 0. It
is a best-efficiency exemplar, not a median trace.
