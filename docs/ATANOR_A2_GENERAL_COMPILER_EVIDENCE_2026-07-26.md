# ATANOR A2 General NL-to-Goal Compiler Evidence — 2026-07-26

## Verdict

A2 reached Stage 6 of 6 within the approved 24-hour budget, but the capability
verdict is **RED / no-go**.

The mechanism exists: a graph-owned generic predicate can be extracted,
compiled, staged, proof-checked, and observed without answer authority. The
fresh predicate battery and the exposed MMLU-Pro OFF/ON curve do not establish
a capability gain:

- Stage 5 strict gate: failed, 51 recorded failures.
- Stage 6 MMLU-Pro: OFF 4/40 (0.10) and ON 4/40 (0.10).
- Generic firing on the 40-item slice: 0/40.
- Wins: 0. Regressions: 0. Accuracy delta: 0.00.
- E4: false. E5: false. Promotion: false. Live answer authority: false.

This is the required distinction between a working mechanism and measured
ability. Green unit tests are not counted as benchmark progress.

## Time budget

- Approved budget: 24 hours.
- Start: 2026-07-25 22:26:24 KST.
- Twelve-hour checkpoint: 2026-07-26 10:26:24 KST.
- Hard stop: 2026-07-26 22:26:24 KST.
- Stage 6 receipt written: 2026-07-26 00:09:29 KST.
- Elapsed to Stage 6 receipt: approximately 1 hour 43 minutes.

## Six-stage ledger

| Stage | Delivered mechanism or measurement | Status |
|---|---|---|
| 1 | Real Wikidata property catalog: 13,693 entries; dump-bound catalog and snapshot digests | Complete |
| 2 | Read-only generic predicate socket over real B1 and S1 stages; graph-owned internal predicate names; bounded subject index | Complete |
| 3 | Pinned spaCy dependency role extractor; subject–relation–object receipts with fail-closed eligibility checks | Complete |
| 4 | Arbitrary graph-owned predicate goal compilation, exact proof replay, default-off non-authoritative shadow observer | Complete |
| 5 | Fresh real-store predicate/adversarial battery | Complete as RED, unsealed diagnostic |
| 6 | Fixed exposed MMLU-Pro OFF/ON curve, reverse-order replay, exact rescoring, GPQA fail-closed census | Complete as RED, non-promotable measurement |

## Stage 1–4 mechanism evidence

The implementation candidate is frozen at
`1399eec46dd3786caf95edfc083ae395888c8277`.

Key commits:

- `d18d13cd`: real Wikidata property catalog.
- `7c24367b`: read-only generic predicate socket.
- `09b58708`: pinned dependency role extractor.
- `5fea4760`: graph-owned generic predicate goal compilation.
- `99cf2403`: exact content-role predicate binding.
- `a4b48bef`: generic predicate proof verification.
- `a5c22a9b`: bounded shadow evaluation.
- `0c9746d3`: default-off observer wiring.
- `1399eec4`: exact proof-replay hardening.

The catalog contains 13,693 entries. Its catalog digest is
`9877b3418f3c8407a0fb190c104aa7b8987477a26a510e8eb9857fc5dc121db8`;
the bound snapshot digest is
`e781f5912b65811657fe7c3b84c492241a27940c40d77b71f441df44abf6d426`.

The socket reads the real B1 store with 108,124,683 rows and the S1 literal
store with 1,088,188 rows. It uses stage-owned predicate identifiers rather
than inventing Wikidata PIDs. The S1 QID/PID sidecar digest is
`764f98db865a9e0cbfe91d97797c028fa3d878d09077132c82f90ec560228746`.

The Stage 4 observer is disabled unless
`ATANOR_GENERIC_PREDICATE_SHADOW=1`. It has no answer authority and performs no
network, graph, or grader writes. `grounded` means only that the local proof
receipt replayed; it does not mean the benchmark answer is correct.

Focused Stage 4 tests passed 80/80. The full reasoning VM passed 570 tests and
retained one pre-existing unrelated failure:
`test_doubt_gate.py::test_multihop_reader_ace2_lane_constructs`, caused by the
undefined name `MultiHopReader`.

## Stage 5 fresh predicate diagnostic

The Stage 5 candidate is the same frozen commit. The raw diagnostic receipt
SHA-256 is
`c85461625cc22af59adbacffc2a066ec183277d998252f3b6f5dbb66027fc6ed`.

| Metric | Result |
|---|---:|
| Positive examples | 84 across 21 predicates |
| Compile coverage | 38/84 (45.2381%) |
| Exact subject and predicate | 36/84 (42.8571%) |
| Proof-verified and grounded | 36/84 (42.8571%) |
| Wrong compiles | 2 |
| Negative final firings | 3/30 |
| Provenance/PID failures | 0/36 |
| Mutation-rejection failures | 0/36 |
| Bounded-context failures | 0/64 |
| Strict invariance | 76/168 |
| Conditional invariance after baseline compilation | 76/76 |

The strict gate failed with 51 recorded failures. The evaluation is retained
only as a development diagnostic. Its worker ran in the same repository with
inherited filesystem access; the original evaluator script and plan were not
bound into the raw receipt; and the original no-write check did not cover the
whole repository. The legacy receipt schema contains the phrase
`source-separated-self-measurement`, but that phrase is not an isolation or
independence attestation.

## Stage 6 OFF/ON curve

Dataset:

- `data/benchmarks/mmlu_pro/slice_5.jsonl`
- 40 fixed exposed development items.
- Eight categories with five items each.
- SHA-256:
  `a1325092eabfb8dc394ef37f64fe63d79c002678b9d9d3b580605d41690e8b36`.
- Primary order balance: 20 OFF→ON and 20 ON→OFF.
- A fresh process replayed the reverse per-item order.

The OFF condition is the direct declared baseline. The ON condition computes
the same baseline and applies an evaluator-only counterfactual override only if
the synchronous generic lane fires and its proof verifies again. The live
answer remains the baseline in both conditions.

| Metric | OFF | ON |
|---|---:|---:|
| Strict accuracy | 4/40 (0.10) | 4/40 (0.10) |
| Eligible | 0/40 | 40/40 |
| Role extracted | 0/40 | 8/40 |
| Context ready | 0/40 | 3/40 |
| Compiled | 0/40 | 0/40 |
| Engine called | 0/40 | 0/40 |
| Fired | 0/40 | 0/40 |
| Proof verified | 0/40 | 0/40 |

Derived curve:

- Accuracy delta: 0.00.
- Wins: 0.
- Regressions: 0.
- Wrong fires: 0.
- Exact two-sided McNemar p-value: 1.0.
- Live-answer invariance: 40/40.
- Semantic reverse-order replay: passed.
- Measurement-integrity checks: passed.
- Stage 5 prerequisite: failed.
- Promotion gate: failed.

The machine receipt checksum is
`73bb30fadbd76742230d612758b57195d4cd20329bfac44b0055c8281b2de4f4`.
The receipt file SHA-256 is
`063286223a6c7c609cdffb54a2f5d6b0a3827a327114372bc15a5418cf39386f`.

The Stage 6 harness independently reconstructs correctness from the fixed
dataset and gold labels, rejects result or scope tampering after checksum
recalculation, binds an exact frozen-tree candidate census, and validates the
canonical no-authority protocol. It still runs locally without OS-level gold
filesystem isolation and does not carry the full proof/replay payload needed
for an independent verifier to re-execute those proofs. Therefore the receipt
is self-measured development evidence, not an external seal.

## GPQA blocker

No GPQA accuracy or lift is claimed. The local 198-row file is fail-closed
because zero-based rows 89, 126, and 191 do not contain four case-fold-distinct
answer texts. The fixed file SHA-256 is
`41d1213cd7a4998605a26c2798500652572007161b3a92817ba46b35befcd305`.
Rows were not dropped, deduplicated, repaired, or scored.

## Bound artifacts

- Stage 5 diagnostic generator:
  `scripts/atanor_a2_stage5_fresh_holdout.py`.
- Stage 5 raw diagnostic:
  `reports/benchmarks/atanor_a2_stage5_fresh_holdout_v1.json`.
- Stage 6 paired-curve harness:
  `scripts/generic_predicate_mmlu_pro_receipt.py`.
- Stage 6 harness tests:
  `scripts/tests/test_generic_predicate_mmlu_pro_receipt.py`.
- Stage 6 raw receipt:
  `reports/benchmarks/generic_predicate_mmlu_pro_stage6_v1.json`.

## Final classification

- Mechanism completion: yes, for the bounded A2 generic compiler shadow.
- General predicate robustness: no; Stage 5 is RED.
- Exposed MMLU-Pro capability improvement: no.
- GPQA capability measurement: blocked.
- E4: no.
- E5: no.
- E6: no.
- Production or live-answer authority: no.
- Independent or external evaluation: no.

The next A2 iteration would need to improve proposal-side coverage and reject
ambiguous relations, then rerun the exact Stage 5 and Stage 6 gates. That is a
new development decision; it is not implied or authorized by this evidence
record.
