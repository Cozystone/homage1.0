# Pattern #9 evaluator v2 result

Status: **GREEN — CAPABILITY_LIFT_CONFIRMED**

The preregistered v2 target ran exactly once from sealed commit
`c8b43993c982a6aa5027b41b7512282fcc73f197`. The production candidate was
unchanged; only the evaluator/harness differed from the preserved v1 attempt.

## Frozen OFF/ON result

| Metric | OFF | ON |
|---|---:|---:|
| False assertions | 6/6 | 0/6 |
| Wrong-source adoptions | 6/6 | 0/6 |
| Authority promotions | 12/12 | 0/12 |
| Public-taint preservation | 0/24 | 24/24 |
| Control accuracy | 6/6 | 6/6 |

All preregistered capability gates passed, no regression gate fired, and every
integrity gate passed. The v2 verifier independently checked each arm against
its condition binding, replayed the raw worker isolation validator, and required
an identical pre/post source-tree binding.

## Evidence seal

- Report:
  `reports/benchmarks/atanor_pattern09_public_speech_capability_v2_20260727.json`
  (`sha256:7839d450e231047b69843d8f7e5798f60384cf7df8cd30d54fc65c41a49b43a9`)
- Attempt:
  `reports/benchmarks/atanor_pattern09_public_speech_capability_v2_20260727.attempt.json`
  (`sha256:62b7d75430f4e49932ec1424df84f1add17ab4ca510c4e3a14a4b266e6308504`)
- Failure receipt: absent
- Existing v1 report and attempt: byte-identical to commit `8b703e1b`

This establishes capability lift only for the fixed local Pattern #9 public
speech authority-discrimination cohort. It does not authorize production
activation and is not a general-reasoning, public-benchmark, independent
evaluator, or E5 claim.
