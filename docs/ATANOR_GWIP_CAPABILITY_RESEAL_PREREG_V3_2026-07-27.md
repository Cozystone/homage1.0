# GWIP capability verifier-only reseal preregistration v3

## Claim boundary

This is one fixed-candidate, fixed-dataset, verifier-only reseal of the
GWIP/ARC-I0 capability pilot. It may establish only the capability claim
already defined by the original preregistration. It is not an ARC benchmark,
production activation, E5, or external-attestation claim.

The operator selected the sequence label `v3`. Repository evidence contains
one earlier materialized GWIP capability preregistration and attempt (`v1`).
No `v2` preregistration, attempt, raw evidence, or receipt exists. The `v3`
label therefore records the operator-directed retry sequence; it does not
claim that two prior empirical executions occurred.

## Frozen candidate

- Candidate commit:
  `51de7aadf188f9889ff1ea051012693e5aa529e2`
- Candidate source digest:
  `b5709ea5852b56f447d20238a816fa88d1f7b74128daaf77bb7cfa6c833f30ce`
- Candidate package changes after candidate C: forbidden.
- Production default: OFF.

## Frozen dataset and scoring contract

`data/eval/gwip_capability_prereg_v3.json` is byte-identical to the original
machine preregistration. Its expected raw SHA-256 is
`12d9bd9f7a22d6463ddae53ac543507fa2e102dea4ce4cd7f8835547d63155da`.
Every threshold, bootstrap rule, arm, episode count, step budget, and no-go
criterion remains unchanged.

The v3 seed must reuse the original generator seed and nonce rather than
sample a new cohort. The regenerated cohort must satisfy all of:

- Original seed bytes SHA-256:
  `fc73d4a1b127ce6bfc0a950dcf9d012cd22d90c7d80261d975c574a3da6e2604`
- Private cohort SHA-256:
  `31d343f80960ebbef860fc75cda46f852ea7fc87dfa579b4461c602c68d30a0b`
- Pair count: 64.
- Candidate episode count: 1,024.
- Every v3 semantic episode input digest equals the corresponding v1
  semantic episode input digest.

A fresh schedule nonce, RunLease key, authority root, and archive are allowed
only as operational witnesses. They may not alter the episode inputs, arm
ordering, candidate, scoring, or gates.

## Unchanged hard gates

All twelve gates remain conjunctive and unchanged:

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

Capability may be claimed only if all twelve hard gates and all four original
metric sections pass without reinterpretation.

## Superseded evidence retained verbatim

The existing v1 evidence is immutable and must remain present under its
original paths:

- Preregistration raw SHA-256:
  `12d9bd9f7a22d6463ddae53ac543507fa2e102dea4ce4cd7f8835547d63155da`
- Semantic schedule raw SHA-256:
  `17d4e1c75b0a8eb01caa98d62f1f57dd77f01ffd8ba9ec307ed27aff38ec681b`
- Raw evidence gzip SHA-256:
  `0612a080e549918eabfe8f453abba1f8176daf48b5cddd9cff2ff50f02a429c3`
- Receipt raw SHA-256:
  `d12d75fdce8c0d97eba53559eb82a29c15ef0ac424e809e758a69ed8833c213a`
- Receipt checksum:
  `5677e18f9ea900253d0aeabb0c62d4b5a2985d90a27a998402e924b23b2a2cd5`
- Authority archive SHA-256:
  `c8da1fc3310198f80b33ff212ab415ed6ba44657d5bdcd238f8aa1c16ea35a95`
- Original verdict: `CAPABILITY_RED`.

The v1 receipt is not overwritten or reinterpreted.

## Allowed evaluator delta

No candidate or dataset delta is allowed. The only behavioral evaluator
corrections permitted between the original evaluator and the v3 evaluator
are:

1. Commit `c7f7161714ab29107b15ffdee9cd840ed5b8f7fd`: accept a
   terminal/success or exact-budget step followed directly by `stop`, and
   report the untruncated lineage failure count.
2. Commit `7752bbd430aec0613aca8d20b91c102f4c565934`: advance the
   independent Rule-IR verifier with parent-witnessed per-step memory when
   `retain_policy_updates=true`, while preserving the original fixed-memory
   behavior when `retain_policy_updates=false`.
3. Versioned output paths and lineage fields required to preserve v1 and make
   the v3 attempt write-once. These are bookkeeping changes only.

The v3 receipt must include a checksummed `verification_lineage` stating this
allowed delta and independently proving candidate, preregistration, cohort,
episode inputs, hard gates, and metric thresholds unchanged.

## One-shot rule

The v3 attempt file must be created exclusively before candidate execution.
Exactly one v3 execution is allowed. There is no mechanical retry. A runtime,
verification, or gate failure consumes the attempt and seals `CAPABILITY_RED`.
Thresholds and gates may not be altered after observing the result.

Required v3 artifact paths are distinct from v1:

- `data/eval/gwip_capability_seed_manifest_v3.json`
- `data/eval/gwip_capability_semantic_schedule_v3.json`
- `data/eval/gwip_capability_attempt_v3.json`
- `data/eval/gwip_capability_raw_evidence_v3.json.gz`
- `data/eval/gwip_capability_authority_v3.tar.gz`
- `data/eval/gwip_capability_receipt_v3.json`

`production_default_on=false`, `public_benchmark_claim=false`, and no-push
remain mandatory regardless of verdict.
