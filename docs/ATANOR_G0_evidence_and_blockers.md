# ATANOR G0 Evidence and Blockers

Status: operator-closed at the bounded sufficient-honesty threshold; residual limitations remain open
Recorded: 2026-07-25 KST
Scope: truthful foundation only; no E5/E6 or capability claim

## 1. What is now source-bound

The canonical shipped graph has one guarded path from a reviewed proposal to
an immutable mutation batch, a verified candidate, an externally signed v3
promotion, a crash-journaled committed swap, and an applied lifecycle receipt.
Direct and legacy shipped-graph writers fail closed or are restricted to
scratch/proposal stores.

The runtime-edge registry binds 25 live-source files, three test sources, and
two controlled-evidence reports across 29 selected critical edges.
Twenty-eight calls are source-confirmed. Nine edges have controlled-test
evidence at M3: two for the default-off cognitive chat observer, two for the
sampled default-off ContinuousSelf observer, and five for one
controlled-forward trace of the existing temporal bidder plus its default-off,
nonblocking World4D sibling observer. The trace does not cover the legacy
backward or abstention paths. These are not production traces or E4 results.
The script-to-
`NightlyPromotionQueue` artifact handoff remains explicitly `unknown`.
Production execution traces remain zero. The registry canonical hash is:

`9688d03085cd3722bb0adcc2383f871ed11e45e49fa689b561b65bee0f64bedc`

This establishes selected M1 reachability plus narrowly scoped M3
controlled-test paths. It does not establish process activation, deployed
authority, a solved 4D model, shared-state fusion, integration quality,
benchmark lift, consciousness, AGI, or ASI.

## 2. Reproduced command evidence

The following manifests were verified immediately against the exact recorded
working tree:

- `reports/baseline_evidence/g0_smoke_20260724T204240597Z.manifest.json`
  - manifest hash:
    `21a4820d6c09ea76d916735f07607de844ea3bbd71fa406379c9af20c65afd82`
  - three bounded recipes, two successful attempts each;
  - stable exit, stdout, stderr, and declared report digests;
  - `successful=true`, `successful_reproduced=true`, `source.sealed=false`.
- `reports/baseline_evidence/g0_reasoning_control_20260724T204356786Z.manifest.json`
  - manifest hash:
    `a9f51215d3b7fd0ac3928f0dc8f9dace0c0cadbdbc6a148c37db431d09c3cce4`
  - DELIBERATOR control recipe, two successful attempts;
  - stable exit, stdout, stderr, and declared report digests;
  - `successful=true`, `successful_reproduced=true`, `source.sealed=false`.
- `reports/baseline_evidence/baseline_20260724T232815.306610Z_42f21ef3d6f0.manifest.json`
  - manifest hash:
    `2a3d1a0cc7079797f093fcc8551f9a4d77f1638f029164b13cb626f774bc0f1a`;
  - expanded cognitive-spine profile, 94 tests per attempt, two successful
    stable attempts;
  - chat and sampled ContinuousSelf observer wiring only; no shared-state,
    external-effect safety, E4, or capability claim;
  - subsequent registry and documentation edits make it historical evidence
    with `source.sealed=false`.
- `reports/baseline_evidence/baseline_20260724T225531.739793Z_45bfaf0d04c9.manifest.json`
  - manifest hash:
    `86cbf9d3cebf0b0b7614771da7f0b6008fa1d5a585365f71b4c93cb8eb6767c7`;
  - World4D shadow control profile, 40 tests per attempt, two successful
    stable attempts;
  - the receipt predates the final registry and documentation edits, so it is
    historical scoped M3 evidence with `source.sealed=false`, not a current
    tree seal or a 4D capability claim.

An earlier smoke attempt is intentionally retained:

- `reports/baseline_evidence/g0_smoke_20260724T204048037Z.manifest.json`
  - one cold fail-closed attempt exceeded its 15-second budget by about
    0.2 seconds while its repeat finished in 8.5 seconds;
  - the architecture and signed-mutation recipes reproduced successfully;
  - the timeout allocation was corrected without increasing the 120-second
    profile bound.

These are digest-only command-execution receipts. Their benchmark metric fields
are intentionally null. They do not prove GPQA, MMLU-Pro, ARC, bAbI, or
real-world task improvement. Any later source or dirty-state change creates a
new working tree and requires a new manifest; an old manifest remains a
historical snapshot rather than a seal for later code.

## 2.1 Recorded unsigned benchmark preservation receipts

The benchmark receipt contract is now
`atanor.benchmark-evidence.v2`. It records a declared item selection, derives a
fixed metric set from item outcomes, binds evaluator source, candidate source,
dataset bytes, and current-file checks, and rejects repository-local outputs
outside `reports/benchmarks`. Its checksum is deliberately described as
recomputable. Every receipt reports `authenticity_established=false`,
`production_authority=false`, and `e5_claimed=false`. Historical v1 receipts
remain structurally readable but are not silently promoted to v2.

The following v2 receipts were generated and immediately verified against the
files current at their recorded run. Later source changes make a receipt
historical unless its verifier again establishes current-file identity:

- bAbI 1.2 train, 1,000 items per task, 20,000 total:
  - `reports/benchmarks/babi_external_20260724T212536Z.babi.ab0aa1e4ecb9.json`
  - checksum:
    `25f4c56e56af92c31c2bdefcfd197b6b0bc5d529d30f807fc61a26973d372deb`
  - macro and micro strict accuracy `0.976`;
  - coverage `0.9808`; fired accuracy `0.995106035889`.
- bAbI 1.2 validation, all 20,002 parsed items:
  - `reports/benchmarks/babi_external_20260724T212718Z.babi.86c3d2972d00.json`
  - checksum:
    `e687183d640a8e11d9a69e5d84946c375ac5ddb70942b08742536f1cbb628b6a`
  - micro strict accuracy `0.976452354765`;
  - macro task strict accuracy `0.976418236473`;
  - coverage `0.980751924808`; fired accuracy `0.995616047306`.
- ARC-AGI-1 pinned public evaluation inventory, all 400 tasks and all 419
  test inputs:
  - prediction artifact:
    `reports/benchmarks/arc_agi1_predictions_20260724T213345Z.arc-agi1.94a5907105eb.json`
  - prediction checksum:
    `68850b3a33213f7fbc9a65142e57d2f39676e084b65a804ef9c214a8476f561c`
  - out-of-band artifact SHA-256:
    `62ca2105f0505d8679cbab229bac75510baf2ce3d644a19f17572b0b77939938`
  - replayable score receipt:
    `reports/benchmarks/arc_agi1_score_20260724T213345Z.arc-agi1.94a5907105eb.v2.json`
  - score checksum:
    `92a7f03d96fb89161c9840e7da2438fb81d8f9dfd370145bfafb94b507301c01`
  - 18 correct, zero wrong fires, 382 abstentions, strict accuracy and
    coverage `0.045`.
- DELIBERATOR isolated MMLU-Pro slice-5, 40 items:
  - `reports/benchmarks/deliberator_isolated_20260724T212453Z.mmlu-pro.4cc6fa7db22b.json`
  - checksum:
    `ac786b1801c7070b30109099e7de2a716a10a19a6e5618a1992148ccbf798aea`
  - compiler coverage `0/40`; grounded firing `0/40`; isolated accuracy `0`;
  - OFF/ON pairing is false and paired lift is null.

These preserve current local signals. They are not external E5 evidence. bAbI
uses public development material. ARC-AGI-1 public evaluation is
contamination-exposed and the candidate contains evaluation-informed task
targeting. The MMLU-Pro result is an isolated engine scan, not a full answer
cascade. Filesystem and network isolation, external signatures, hidden-set
freshness, and append-only witnesses are absent.

GPQA accuracy measurement is additionally blocked by the current local
Diamond CSV: rows 89, 126, and 191 each contain only three unique answer texts
across four labels. The strict loader refuses the full run rather than emitting
an ambiguous label score. A corrected, provenance-bound dataset is required
before paired GPQA accuracy is credible.

## 2.2 Predeclared clean-source closure receipts

The bounded closure uses the following fixed output paths so a clean run can be
created without editing this document afterward:

- `reports/baseline_evidence/g0_closure_smoke_20260725_v1.manifest.json`;
- `reports/baseline_evidence/g0_closure_reasoning_control_20260725_v1.manifest.json`;
- `reports/baseline_evidence/g1_cognitive_spine_control_20260725_v1.manifest.json`;
- `reports/baseline_evidence/g3_world4d_shadow_control_20260725_v1.manifest.json`.

This path declaration is not a result claim. A receipt counts as clean-source
reproduction only when the run itself records `source.sealed=true`,
`successful=true`, `successful_reproduced=true`, and
`repository_mutation_detected=false`, and independent verification returns
`valid=true`, `git_state_matches=true`, `catalog_matches=true`,
`runner_source_matches=true`, and `mutation_sensitive_state_matches=true`.
Until those conditions are observed, the historical `source.sealed=false`
receipts above remain the only documented command evidence.

## 3. Fail-closed boundaries covered

The recorded smoke profile covers:

- canonical graph path and raw-sidecar guards;
- immutable mutation-batch schema, seal, lifecycle, and base freshness;
- proposal compilation and mixed add/retract candidate construction;
- signed v3 swap, nonce consumption, journal recovery, and deployment copy;
- observe-only PII, contradiction, taxonomy, and compaction defaults;
- pre-scan refusal of legacy direct-write CLIs;
- unauthenticated erasure refusal before subject lookup;
- answer-pack promotion and live derivation refusal before heavy work;
- lifecycle-honest Agora language;
- evaluator, frozen-oracle, moral, permission, and kill-switch integrity;
- source-bound runtime graph validation;
- bounded DELIBERATOR control behavior.

Green coverage establishes that the selected mechanisms match their contracts.
It does not establish that the mechanisms improve task performance.

## 4. Residual blockers beyond the bounded G0 closure

The operator closed G0 once the repository became sufficiently honest to
identify the selected live mechanisms, unknown edges, trust boundaries, and
measurement gaps without converting those observations into capability
claims. The following items still block stronger claims such as hermetic
reproduction, external trust, production readiness, or E5 lift. They are
preserved as named debt; the bounded closure does not erase them.

1. **The recorded manifests are historical dirty-tree receipts.** The
   repository was already dirty when they were generated, so they honestly
   retain `source.sealed=false`. They must not be relabeled as clean-source
   seals.
2. **Execution is not hermetic.** The runner reports
   `network_control.enforced=false` and
   `filesystem_control.enforced=false`. Offline behavior is a cooperative
   environment flag and filesystem observation is post hoc; undeclared
   ignored or outside-repository writes are not observed.
3. **Benchmark baselines are local and unsigned.** bAbI, ARC-AGI-1, and an
   isolated MMLU-Pro scan now have source-, candidate-, dataset-, selection-,
   and item-bound v2 receipts. They still lack external authenticity,
   hidden-set freshness, hermetic execution, and paired lift. GPQA is
   fail-closed on three duplicate-choice rows in the local CSV.
4. **External trust is not provisioned or exercised.** The repository cannot
   prove operator ownership, key pins, fixed-boundary configuration, replay
   ledger ACLs, evaluator independence, or a live operator channel.
5. **No production trace exists.** Source reachability and focused tests do not
   show a deployed process exercising the graph-mutation workflow.
6. **The queue handoff is unresolved.** The promotion script emits an artifact
   for `NightlyPromotionQueue`; no source-bound deployed handoff is present.
7. **Post-commit lifecycle recording is non-atomic.** `APPLIED` is persisted
   after the live swap reaches `COMMITTED`. Receipt failure requires
   journal-based reconciliation and must not replay the swap.
8. **Engine-stop/single-reader status is external.** The rename path cannot
   attest that every reader and writer has stopped.
9. **Proposal acquisition is not end-to-end.** Detector fragments do not
   automatically become reviewed batches. The only authorized path begins
   with an explicit strict reviewed proposal.

## 5. Deliberately unavailable workflows

The following are fail-closed gaps, not completed capabilities:

- authenticated, signed graph erasure;
- signed answer-pack evaluation, canary, rollback, and promotion;
- automatic proposal-fragment review and batching;
- production canary and rollback exercise;
- autonomous evaluator or permission modification.

Keeping these workflows unavailable is compatible with the narrow G0
fail-closed objective. Claiming that they are complete is not.

## 6. G0 exit decision

G0 is **operator-closed at a bounded sufficient-honesty threshold**.

On the recorded working tree, selected smoke and DELIBERATOR-control recipes
reproduced identical bounded command outcomes. Current local benchmark
preservation receipts now make bAbI, ARC-AGI-1, and isolated MMLU-Pro outcomes
item- and byte-bound without pretending that a recomputable checksum is a
signature. The critical runtime registry establishes selected
source-confirmed mechanism evidence only: 19 edges at M1, nine narrowly scoped
M3 controlled-test edges, and one V0/unknown handoff. That is enough to stop
the open-ended census and begin capability work without pretending that the
system is more integrated or proven than it is.

This decision is an operator sequencing decision, not evidence promotion. The
historical `source.sealed=false` receipts remain historical. Clean-source
reproduction, hermetic and externally authenticated evaluation, credible GPQA
data, external trust provisioning, and production exercise remain absent or
unproven, so G0 closure does **not** authorize an E4/E5, production-readiness,
external-trust, AGI, or ASI claim.

No further census sweep is on the immediate critical path. A named residual
may be repaired when a capability experiment depends on it or new evidence
invalidates the bounded closure; otherwise the execution focus moves to the
NL-to-goal compiler and scientific-knowledge staging, followed by E4 functional
gates and paired E5 measurement.
