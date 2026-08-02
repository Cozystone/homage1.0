# GWIP capability verifier-only reseal preregistration v4

## Activation boundary

This document prepares, but does not execute, one new fixed-candidate,
fixed-dataset, verifier-only GWIP capability reseal. It becomes executable
only after the evaluator correction, its regression tests, this human
contract, and the machine contract are committed as a reviewed logical unit
and the root operator separately authorizes the one-shot run.

The repository contains two immutable empirical attempts: v1 and v3. No v2
attempt exists. v4 is therefore the third empirical attempt and the next
operator sequence label. It is not a retry of either write-once artifact.

## Claim boundary

The attempt may establish only the capability claim and thresholds fixed by
the original preregistration. It is not an ARC benchmark, production
activation, E5, or external-attestation claim. Production remains OFF
regardless of verdict.

## Frozen candidate

- Candidate commit:
  `51de7aadf188f9889ff1ea051012693e5aa529e2`
- Candidate source digest:
  `b5709ea5852b56f447d20238a816fa88d1f7b74128daaf77bb7cfa6c833f30ce`
- Candidate package changes after candidate C: forbidden.
- Production default: OFF.

No file under `packages/` is part of the v4 evaluator correction.

## Frozen dataset and scoring contract

`data/eval/gwip_capability_prereg_v4.json` is byte-identical to v1 and v3.
All three files have raw SHA-256:
`12d9bd9f7a22d6463ddae53ac543507fa2e102dea4ce4cd7f8835547d63155da`.

Every threshold, bootstrap rule, arm, episode count, step budget, and no-go
criterion remains unchanged. A v4 seed and schedule must reproduce:

- original seed bytes SHA-256:
  `fc73d4a1b127ce6bfc0a950dcf9d012cd22d90c7d80261d975c574a3da6e2604`;
- private cohort SHA-256:
  `31d343f80960ebbef860fc75cda46f852ea7fc87dfa579b4461c602c68d30a0b`;
- pair count: 64;
- candidate episode count: 1,024;
- exact per-ordinal semantic episode input equality with v1 and v3.

A fresh schedule nonce, RunLease key, authority root, and archive are allowed
only as operational witnesses. They may not alter episode inputs, arm order,
candidate behavior, metrics, or gates.

## Unchanged hard gates

All twelve gates remain conjunctive:

1. `call_order_and_stop`
2. `step_budget_and_pre_mutation_denial`
3. `run_lease_direct_authority`
4. `run_lease_single_use_and_replay_rejection`
5. `semantic_reexecution_determinism`
6. `structural_cycle_replay`
7. `fresh_environment_reexecution`
8. `complete_lineage`
9. `adversarial_self_attestation_rejection`
10. `candidate_domain_neutrality`
11. `candidate_runtime_import_closure`
12. `candidate_fixed_source_guard_controls`

Capability may be claimed only if all twelve gates and all four original
metric sections pass without reinterpretation.

## Preserved predecessor evidence

The v1 and v3 preregistrations, attempts, raw evidence, archives, and receipts
remain immutable at their existing paths.

| Attempt | Raw evidence SHA-256 | Receipt checksum | Verdict |
| --- | --- | --- | --- |
| v1 | `0612a080e549918eabfe8f453abba1f8176daf48b5cddd9cff2ff50f02a429c3` | `5677e18f9ea900253d0aeabb0c62d4b5a2985d90a27a998402e924b23b2a2cd5` | `CAPABILITY_RED` |
| v3 | `dcaf8141dff574ec28bab6a18da1829fad47f0bd9a2ca45c3bff2dc2bce34202` | `e86a97ae9fad9fb4293882186826f5299cd01e5035e132f307215b0c5be6004e` | `CAPABILITY_RED` |

Neither receipt may be overwritten, reinterpreted, or used as the v4
attempt.

## Allowed evaluator delta

Candidate and dataset deltas are forbidden. The only new behavioral
evaluator delta relative to v3 is the parent call-order auditor correction
diagnosed in
`docs/ATANOR_GWIP_V3_CALL_ORDER_RED_DIAGNOSIS_2026-07-28.md`:

- ordinary nonterminal steps return to the independently enforced
  `need_observe` state even when the executed count reaches 24;
- an actual next step remains forbidden when its zero-based index is at or
  above the budget;
- `stop` is accepted from the same three live states accepted by the sealed
  parent protocol;
- terminal/success steps still require immediate `stop`;
- post-stop activity and every prior digest/index/action check remain
  fail-closed.

The reviewed evaluator file must have raw SHA-256:
`75e188bbe41c8974ca1a14421514b0caadd1b7d6267ae28bbe2980a5bbfb0230`.
Any different behavior or digest invalidates this preregistration before
execution.

Prior verifier corrections remain exactly those already admitted by v3:

- `c7f7161714ab29107b15ffdee9cd840ed5b8f7fd`;
- `7752bbd430aec0613aca8d20b91c102f4c565934`.

Versioned v4 output paths, attempt binding, and verification-lineage fields
may be added only as write-once bookkeeping. Such tooling must be reviewed
and committed before the attempt is created; it may not change candidate,
data, gates, metrics, or evaluator behavior.

## Termination-path controls

Before v4 is executable, synthetic tests must prove all of:

- `goal_reached` and `environment_terminal`: terminal step then stop;
- `step_budget_exhausted`: step 24, observe, valid actions, denial of step 25,
  then stop;
- `operator_stop_requested` and `post_observation_mismatch`: stop after
  observation;
- `no_valid_actions`, `policy_abstained`,
  `proposal_not_in_evaluator_valid_set`, and RunLease denials: stop after
  valid-actions processing;
- caught error/finally termination from every parent-live state;
- a real step 25, activity after a terminal step, and activity after stop
  remain rejected.

The synthetic v3 reproduction must fail under the superseded v3 auditor and
pass under the reviewed v4 auditor.

## One-shot rule

No v4 attempt or empirical execution exists at preregistration time. After
separate root approval, the attempt file must be created exclusively before
candidate execution, and exactly one v4 execution is allowed. A runtime,
verification, or gate failure consumes the attempt and seals
`CAPABILITY_RED`. No mechanical retry or post-result threshold
reinterpretation is permitted.

Required new paths are distinct from v1 and v3:

- `data/eval/gwip_capability_seed_manifest_v4.json`
- `data/eval/gwip_capability_semantic_schedule_v4.json`
- `data/eval/gwip_capability_attempt_v4.json`
- `data/eval/gwip_capability_raw_evidence_v4.json.gz`
- `data/eval/gwip_capability_authority_v4.tar.gz`
- `data/eval/gwip_capability_receipt_v4.json`

`production_default_on=false`, `public_benchmark_claim=false`, staging/graph
unchanged, and no-push remain mandatory.
