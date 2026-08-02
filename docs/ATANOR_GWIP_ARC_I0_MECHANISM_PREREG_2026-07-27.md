# GWIP / ARC-I0 mechanism preregistration

Status: frozen before candidate implementation  
Date: 2026-07-27 KST  
Budget: checkpoint 32 h, hard cap 64 h  
Scope: mechanism only; no capability pilot, public ARC evaluation, shipped graph
promotion, or production-default change

## 1. Question and boundary

This slice asks whether existing ATANOR components can be joined into one
domain-neutral interactive loop:

`reset -> observe -> valid_actions -> step -> stop`

The coordinator belongs in the existing `packages/fusion_loop` namespace. It
may adapt existing organs, but it must not create a new authority, truth,
memory, perception, world-model, affordance, or deliberation institution.

The required existing parts are:

- `GoalIR`, `WorldSnapshot`, `CognitiveMoment`, and `DecisionReceipt`;
- `CycleReceipt`, `CycleLedger`, structural replay, and fresh-environment
  re-execution;
- deterministic perception and the situation model;
- the event transition graph as an advisory hypothesis;
- affordance resonance, restricted to evaluator-returned valid actions;
- DELIBERATOR as a proof-producing selector over learned transition facts;
- the existing externally signed `RunLeaseStore` as the only step authority.

`DecisionReceipt.verify_identity()`, contract adapters, and canonical hashes
prove only self-consistency. They are not accepted as provenance, validity, or
authority.

## 2. Pre-implementation trust findings

The following RED controls were reproduced before implementation:

1. A caller can reseal a `DecisionReceipt` whose proposed action changes from a
   valid move to an invented action, and both `verify_identity()` and
   `adapt_decision_receipt()` accept the self-consistent object.
2. A caller can construct a prefix-shaped observed claim ID and seal a
   `WorldSnapshot` without proving that the claim exists in an evaluator-owned
   observation registry.
3. `dataclasses.replace(valid_boundary, trust_root=attacker_root)` preserves
   the module token in `RunLeaseBoundaryConfig`. `RunLeaseStore` then accepts an
   attacker-signed lease because it re-reads, but does not use, the pinned
   external trust root.

Consequently:

- the environment cannot submit a receipt, `allowed` flag, source status,
  lease context, lease boundary, store, or per-step cost;
- the coordinator constructs receipts only after reading the actual
  evaluator-owned observation and valid-action set;
- an independent trace verifier compares every receipt to evaluator-owned
  witnesses and actual post-step observations;
- the evaluator/composition root owns the external key, configuration, replay
  ledger, `RunLeaseStore`, live-context construction, lease activation, and
  authorization call;
- the RunLease pinned-key substitution flaw must be closed by a focused
  adversarial regression before the common loop can be GREEN.

## 3. Fixed implementation surface

Allowed candidate surfaces:

- `packages/fusion_loop/interactive.py`;
- `packages/fusion_loop/interactive_organs.py`;
- exports in `packages/fusion_loop/__init__.py`;
- a narrow general-interaction profile in the existing
  `packages/autonomy_envelope/run_lease.py`;
- focused tests under the owning packages.

Allowed evaluator surfaces:

- `scripts/gwip_mechanism_eval.py`;
- `scripts/tests/test_gwip_mechanism_eval.py`;
- a post-candidate seed/nonce manifest and sealed result/receipt files.

The candidate must not import evaluator code or data. The evaluator may import
the candidate.

## 4. Mandatory mechanism gates

Any failure below makes the result RED regardless of efficiency.

### 4.1 Call order and stop

- The environment observes exactly
  `reset -> observe -> valid_actions -> step`, repeated as needed, then one
  `stop`.
- No `step` occurs before a successful evaluator-owned RunLease authorization.
- Explicit goal/terminal, step-budget, lease-denial, and operator-stop paths
  all terminate and call `stop` exactly once.
- The internal step counter and atomic RunLease cycle/action charge both
  enforce the budget.
- At a 20-step budget, a proposed step 21 is denied before environment
  mutation.

### 4.2 Determinism and replay

- Two fresh executions with identical environment input, environment seed,
  policy seed, starting policy memory, goal, and canonical IDs have identical
  semantic trace digests.
- RunLease nonce/timestamp/counter values are excluded from the semantic
  equality comparison but remain separately bound in operational evidence.
- `replay_cycle()` reconstructs the identical terminal canonical state.
- A fresh environment re-executes the recorded actions and independently
  matches every observation, valid-action set, transition result, terminal
  condition, and stop reason.

### 4.3 Complete lineage

For 100% of executed steps the verifier must establish this chain:

`evaluator observation -> ClaimEnvelope -> WorldSnapshot -> GoalIR ->
 evaluator valid-actions digest -> affordance/proposal -> DecisionReceipt ->
 evaluator-direct RunLeaseStore.authorize -> environment action result ->
 next observation -> learned transition edge`

The selected action must occur exactly once in the evaluator-owned valid set.
A self-consistent forged receipt, forged world snapshot, forged `allowed`
field, stale/replayed lease, altered valid-action set, wrong parent, or altered
post-state must fail closed.

### 4.4 Domain neutrality

Candidate import closure must contain none of:

- `packages.arc_agi`;
- `packages.eval_evidence.arc_agi1_prediction`;
- ARC evaluation scripts or data;
- `packages.vsa_reasoning.tests.test_arc_probe`.

The reusable coordinator and organ adapters contain no task IDs, mechanic IDs,
fixture seed/nonce, oracle/transition table, grid/cell/pixel/color vocabulary,
or domain-name branch. State and action payloads are opaque bounded JSON.

## 5. Fixed unseen-mechanics discriminator

This is a controlled mechanism discriminator, not the separately unapproved
capability pilot.

### 5.1 Cohort

- 48 independently generated deterministic finite-state mechanics;
- 8--12 opaque states and 3--4 opaque, per-mechanic permuted action IDs;
- no grids, colors, cells, images, ARC tasks, or public benchmark artifacts;
- evaluator-owned hidden transition table and reachable opaque goal state;
- three reset episodes per mechanic, with memory permitted only inside that
  mechanic and a hard reset between mechanics;
- maximum 20 executed steps per episode.

The generator is committed before the candidate is run. The candidate source
is committed before a separate seed/nonce manifest is generated and committed.
The transition tables are generated only after that source seal. Static and
runtime audits reject any candidate import or access to the evaluator, seed
manifest, mechanic identity, table, oracle, or optimum.

Candidate input is limited to `reset`, `observe`, `valid_actions`, step results,
and a `GoalIR` containing an opaque target reference.

### 5.2 Controls

- Reactive: stateless choice minimizing
  `SHA256(observation_digest || action_id)`.
- Random: uniform choice under each of the 32 fixed policy seeds in
  `data/eval/gwip_mechanism_prereg_v1.json`.
- Candidate, reactive, and random run on independent environment clones with
  counterbalanced order.

### 5.3 Metric and preregistered no-go

For each episode:

`SWAE = success * optimal_shortest_path_steps / executed_steps`

A failure or budget exhaustion has SWAE 0. The evaluator computes the optimum
from its hidden transition table. The three episode values are averaged to one
score per mechanic (`n=48` independent paired units). Random is first averaged
over its 32 seeds within each mechanic.

The candidate must clear all of these against **each** baseline separately:

1. mean SWAE delta at least `0.05` absolute;
2. one-sided paired 95% bootstrap lower confidence bound greater than `0`
   using 10,000 mechanic-level resamples and the frozen bootstrap seed;
3. candidate success rate no lower than the baseline success rate.

Failure against either baseline is the preregistered 32--64 h no-go. No
threshold, denominator, sample, ordering rule, or cohort may be changed after
results are visible.

## 6. Verdict vocabulary

- `MECHANISM_GREEN`: every hard gate passes and the bounded
  unseen-mechanics no-go is cleared.
- `MECHANISM_RED`: a hard gate fails.
- `NO_GO`: hard gates may pass, but the preregistered efficiency/success test
  fails.

Even `MECHANISM_GREEN` establishes only a default-off, controlled common loop
and a bounded mechanism discriminator. It does not establish ARC improvement,
general benchmark lift, E5 capability, production authority, AGI, or ASI.

