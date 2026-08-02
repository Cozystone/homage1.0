# ATANOR A-track evidence ledger — 2026-07-25

> **Closure update — 2026-07-26:** The operator formally paused A-track after
> reviewing the complete evidence curve and the A/B continuation scopes.
> Sections 10–13 are the closing record. All staging artifacts are retained;
> no staged data is promoted to the shipped graph.

## 1. Verdict

The NL-to-goal compiler and provenance-bound scientific staging now form a
real, default-off execution path. A narrow atomic-number intervention has a
current-replayable self-measured E4-development receipt. The same mechanism
does **not** reach the exposed 40-item MMLU-Pro development slice, so it has
produced no measured benchmark-capability lift.

These are separate results:

| Axis | Current result | Honest classification |
|---|---:|---|
| Typed atomic-number compilation | 15/15 frozen positive inputs | narrow mechanism reach |
| Stage-causal atomic intervention | strict accuracy 0/15 OFF → 15/15 ON | self-measured E4-development evidence |
| Public MMLU-Pro compiler reach | 0/40 OFF → 0/40 ON | no new benchmark reach |
| Public MMLU-Pro strict accuracy | 0/40 OFF → 0/40 ON | no capability lift |
| GPQA Diamond | unavailable | fail-closed dataset arm |
| Independent canonical E4 | not passed | external evaluator boundary absent |
| E5 capability gate | not passed | no positive paired benchmark curve |

Mechanism firing, a green unit suite, and a sealed local measurement protocol
are not substitutes for task capability.

## 2. Implemented path

The current narrow path consists of:

1. `science_goal.py`: deterministic NL-to-typed-goal compilation for four
   atomic-number surfaces, with evaluator eligibility separated from compiler
   validity and fail-closed unsupported/ambiguous handling.
2. `science_staging.py`: strict canonical stage loading, checksum and
   provenance binding, functional-conflict rejection, read-only snapshots, and
   structural OFF isolation.
3. `science_exam.py`: gold-absent candidate arguments, DELIBERATOR execution,
   and acceptance only when every proof leaf is stage-bound.
4. Frozen positive, candidate-negative, and mutated-stage controls.
5. Two current-replay verifiers: a narrow E4-development receipt and a paired
   exposed-MMLU development receipt.

The candidate arguments contain only an opaque item ID, stem, and choices.
This is **argument separation**, not process-level gold isolation: candidate
and evaluator still run in the same process.

## 3. Narrow E4-development receipt

Receipt:
`reports/benchmarks/science_stage_e4_20260725_postscope_v3.json`

| Binding | Value |
|---|---|
| Schema | `atanor.science-stage-paired-e4-receipt.v3` |
| Manifest checksum | `f8e2f14d277f6272bc2c4a977627e68eb5fbcd641fafa6ff56b330d958555e47` |
| Frozen fixture SHA-256 | `b0ae7a07694a40551659becba33370b3140fe7927ac846a180e87d84eb80c1b1` |
| Stage digest | `796954cf210144582a6eff9ceb4e7ad213587c0bd08dbbed4eb67e669b22f42e` |
| Stage bound bytes | 7,625 |
| Current verification | `verified_sealed=true`, findings 0 |
| Authority flags | `independent=false`, `e5_claimed=false`, `authenticity_established=false` |

Measured positive curve:

| Condition | Compiled | Fired | Grounded | Correct | Abstained | Wrong fire |
|---|---:|---:|---:|---:|---:|---:|
| OFF | 15/15 | 0/15 | 0/15 | 0/15 | 15/15 | 0 |
| ON | 15/15 | 15/15 | 15/15 | 15/15 | 0/15 | 0 |

All 15 transitions were `abstain_to_correct`; regressions were zero.
Three negative candidates produced six abstentions with zero raw or accepted
fires. Both mutated-stage controls were rejected before a snapshot reached the
reasoner and replayed stably.

This demonstrates a bounded causal mechanism: access to the exact validated
stage changes answers on matched atomic-number fixtures. It does not establish
broad scientific reasoning, source authenticity, hidden-holdout performance,
independent E4, or E5.

## 4. Exposed MMLU-Pro paired development curve

Receipt:
`reports/benchmarks/science_stage_mmlu_pro_20260725_postcommit_v1.json`

| Binding | Value |
|---|---|
| Schema | `atanor.science-stage-mmlu-pro-paired-dev-receipt.v1` |
| Manifest checksum | `1be2c61d8f385d4f9701d2d039a9d7f3286a25d612da7890173a845d8fab9e6e` |
| Dataset SHA-256 | `a1325092eabfb8dc394ef37f64fe63d79c002678b9d9d3b580605d41690e8b36` |
| Selection | exposed first 5 items × 8 categories; 40 total |
| Order | 20 OFF→ON, 20 ON→OFF; reverse semantic replay |
| Current verification | `verified_sealed=true`, findings 0 |
| Authority flags | `independent=false`, `e5_claimed=false`, `external_authenticity_established=false` |

| Curve | OFF | ON | Delta |
|---|---:|---:|---:|
| Evaluator denominator | 40 | 40 | 0 |
| Compiler input-valid | 40 | 40 | 0 |
| Compiler reach | 0 | 0 | 0 |
| Raw / accepted firing | 0 / 0 | 0 / 0 | 0 |
| Grounded | 0 | 0 | 0 |
| Strict accuracy | 0/40 | 0/40 | 0 pp |
| Abstention | 40/40 | 40/40 | 0 |
| Wrong fire | 0 | 0 | 0 |

All 40 transitions were `abstain_to_abstain`; exact paired McNemar
`p=1.0`. The exact 95% binomial interval for each 0/40 strict score is
`[0, 0.088097302879]`. Zero wrong fires are vacuous because firing is zero.

The receipt's `paired_development_measurement_gate_passed=true` means that the
fixed denominator, OFF isolation, ON binding, counterbalance, semantic replay,
and deterministic result derivation completed. It does not mean the capability
gate passed.

Runtime identity, timestamps, and wall/CPU/RSS telemetry are deliberately
absent. An unsigned in-process evaluator cannot attest those values; therefore
`process_resource_curve_claimed=false`.

## 5. GPQA remains fail-closed

The current local Diamond CSV has:

- 198 rows;
- SHA-256
  `41d1213cd7a4998605a26c2798500652572007161b3a92817ba46b35befcd305`;
- four labels but only three normalized answer texts at zero-based rows
  89, 126, and 191.

No GPQA accuracy or lift is valid until either an official corrected release or
a provenance-bound adjudicated derivative resolves those rows without silently
shrinking the denominator. The corrected artifact must bind the original row
hash, field-level patch, rationale, corrected row hash, whole-dataset hash, and
independent reviewer signatures.

## 6. What `sealed=true` means here

For these two receipts, current verification covers:

- exact evaluator, candidate, dataset, and stage byte scopes before and after
  execution;
- the complete loaded project-local candidate module closure;
- fixed denominators and item/choice identities;
- structural OFF absence and exact ON snapshot binding;
- deterministic condition semantics, reverse replay, grading, transitions, and
  derived metrics;
- immutable base state, negative controls, and recomputable canonical checksum.

It does not cover:

- an external signature or trusted timestamp;
- an independent evaluator, process, filesystem, key, or operator;
- hidden or contamination-free data;
- OS-enforced no-network/hermetic execution;
- upstream dataset or scientific-source authenticity;
- production authority or a resource-cost curve.

Thus `verified_sealed=true` is a local deterministic-reproduction property, not
an E5-equivalent authority claim.

## 7. Error-driven next compiler/stage families

> **Historical note:** This section records the next-family hypothesis made
> after the atomic experiment. It is not the current execution order. The
> scalar, relation, and generic-compiler results in Sections 11–13 supersede
> that recommendation.

The exposed 40 items were classified evaluator-side by executable typed
contracts, not by keyword matching. The next profiles must be added beside the
sealed atomic profile rather than mutating it.

| Priority | Typed family | Structural development reach ceiling | Main leverage |
|---|---|---:|---|
| 1 | `scalar_quantity_resolve` | 4/40 | connects rational/float DSL, units, dimensions, lookup, and formula derivation |
| 2 | `typed_relation_select` | 12/40 | reuses provenance-bound triples and closed ontology predicates |
| 3 | `finite_predicate_extension` | 4/40 | exact finite-set and quantifier reasoning without a new engine |

Their non-overlapping structural ceiling is 20/40; the presently
source-groundable estimate is 19/40. These are reach ceilings, not accuracy
forecasts.

The immediate implementation order is:

1. create a parallel `science-stage.v2` profile for
   `scalar_quantity_resolve`;
2. freeze paraphrase and counterfactual E4-development fixtures that do not
   copy the exposed MMLU stems or option strings;
3. bind rational values, unit IDs, dimension signatures, formula ASTs,
   uncertainty/tolerance, source statement bytes, revision, locator, license,
   and quarantine state;
4. reject dimension mismatch, ambiguous tolerance, conflicting facts,
   out-of-domain formula use, non-finite values, and conservation violations;
5. rerun the exact 40-item OFF/ON curve and report reach, firing, grounding,
   correctness, wrong fires, abstentions, and regressions separately;
6. proceed to relation and finite-extension profiles only after their own
   negative and mutation gates pass.

Stage data must never contain benchmark item IDs, question text, choice keys,
whole option strings, or answer labels.

## 8. Independent E4 → real E5 gate

Canonical independent E4 requires a candidate/evaluator split with separate
images, UIDs, filesystems, codebases, and signing keys; OS-enforced network and
mount isolation; a precommitted frozen candidate; externally authenticated
dataset/stage artifacts; fresh-process replay; and a detached evaluator
signature over the full result root and one-time nonce.

The broad science E5 precommit uses three arms:

1. authenticated full MMLU-Pro: ON−OFF strict accuracy at least +3 pp;
2. corrected and authenticated GPQA Diamond: at least +5 pp;
3. a fresh hidden isomorphic science holdout: at least +5 pp with
   pre-run power at `α=.05`, power at least 0.80.

Every arm additionally requires paired 95% CI lower bound above zero,
Holm-corrected exact McNemar familywise `p≤.05`, zero provenance/fabrication or
integrity violations, no forbidden safety regression, predeclared strata with
no material regression, and frozen legacy-anchor loss no greater than 1 pp.
Public MMLU-Pro and already exposed GPQA can be authenticated benchmark anchors,
but they can never become hidden holdouts for this candidate family.

Passing only an atomic-number hidden evaluation can yield at most a scoped
atomic-number promotion. It cannot be promoted to broad science capability.

## 9. Current regression evidence

Focused compiler, staging, E4, paired-MMLU, and DELIBERATOR preservation suites
are green. The full `packages/reasoning_vm/tests` run most recently recorded
288 passes and one known pre-existing unrelated failure:
`test_doubt_gate.py::test_multihop_reader_ace2_lane_constructs`, where
`MultiHopReader` is undefined. That unrelated failure is not repaired by
expanding this targeted A-track.

## 10. A1 knowledge-staging closure

The knowledge work completed full-dump, staging-only passes. The naming below
separates the original two-pass entity pipeline from the later independent
literal pass so that “PASS-2” is not ambiguous.

| Pass | Measured result | Boundary |
|---|---:|---|
| Original PASS-1: dump-bound label/property catalog | 8,212,427,041 lines scanned; 13,693 property labels; 24,463 property aliases; 13,694 property types | Complete metadata scope over the 70,949,764,306-byte truthy dump; no shipped write |
| Original PASS-2: entity-valued B1 staging | 108,124,683 edges; 40,369,354 distinct subjects; 19 internal predicates; 10,253.7 s | Curated entity relations were compressed into the existing internal vocabulary |
| Independent literal PASS-2: S1 staging | 1,088,188 edges; 1,087,367 distinct subjects; 5,683.0 s | QID/PID provenance retained for every staged row; unit-bearing quantities deferred |

The literal stage contains 4,952 `atomic_number` rows and 1,083,236
`chemical_formula` rows. Its aligned QID/PID sidecar contains 1,088,188
records. The manifest declares `completion_state=complete` and
`promotion_eligible=true`; this means the staging artifact completed its own
contract, not that it received production authority.

Primary artifacts:

- `D:/wikidata/wd_labels_v2.sqlite`
- `data/graph_scale/staging_b1_wikidata/B1_WIKIDATA_MANIFEST.json`
- `data/graph_scale/staging_s1_wikidata_literals/S1_WIKIDATA_LITERAL_MANIFEST.json`

Both staging stores are preserved. `data/graph_scale/kg_triples` was not
promoted or mutated by this closure.

## 11. Six structural approaches and public evidence

The operator counts six structural directions explored during A-track. Four
produced public-slice measurements. Two were falsified or held before an
implementation candidate existed; those two must not be misreported as
benchmark-tested implementations.

| Direction | Mechanism result | Fixed public-slice result | Capability verdict |
|---|---|---|---|
| 1. Atomic relation | Typed atomic-number compiler, stage binding, proof replay, and a 15/15 matched-fixture causal curve | MMLU-Pro OFF 0/40 → ON 0/40; compiler reach 0/40 | No public lift |
| 2. Scalar quantity | Exact neutralization compiler, rational/unit path, formula proof, and one accepted grounded fire | OFF 0/40 → ON 1/40; one win; exact McNemar `p=1.0`; post-hoc exposed-development target | Chance-compatible; no general capability claim |
| 3. Typed relation sibling | P17 diagnostic compiler, stage binding, proof-carrying sibling, and additive-preservation control | Atomic+scalar 1/40 → atomic+scalar+relation 1/40; relation selected 0/40 and invoked 0/40 | Zero incremental reach or lift |
| 4. General NL-to-goal compiler | Real 13,693-property catalog, dependency roles, generic predicate socket, proof membrane, and default-off observer | Baseline OFF 4/40 → counterfactual ON 4/40; role extracted 8/40 → context ready 3/40 → compiled 0/40 → fired 0/40; `p=1.0` | RED / no-go |
| 5. W0 predicate-width direction | Read-only scoping examined the 108,124,683-edge B1 store compressed to 19 predicates against PID-preserving sources | No implementation candidate and no new OFF/ON run; therefore no attributable public result | Hypothesis not promoted; no evidence of lift |
| 6. Multi-sentence contract relaxation | A bounded sandbox tested the nine exact-one-sentence rejections | Safe recovery 0/9; three irrelevant-context false-safe hazards; no code change and no new public run | Falsified at the safety check; no evidence of lift |

The apparent scalar `1/40` is not a positive benchmark curve: it was selected
after inspecting the exposed item, has one discordant pair, and yields
`p=1.0`. The relation lane adds nothing to it. The general compiler's live
baseline differs from the earlier abstaining science-only curve, so its
`4/40` must not be compared as an A-track gain; its paired intervention delta
is exactly zero.

## 12. Continuation scopes

### A — repair the remaining 23/36 role-extraction failures

The 23 machine failures form five structural clusters:

1. four main/subordinate-clause WH-contamination cases;
2. ten choice-completed stem-ellipsis cases;
3. four quantity/degree/manner/superlative typed-query cases;
4. four control/preposition/clause role-propagation cases; and
5. one fronted WH-object ambiguity.

Existing dependency annotations plausibly support a shared selection-layer
repair for about 9/23. No case establishes that replacing the spaCy model is
required. The largest cluster, 10/23, lacks an explicit answer slot in the
stem and therefore needs a choice-aware input, receipt, and compiler contract
rather than a parser patch.

Rough implementation scope:

| A scope | Time range | Confidence |
|---|---:|---|
| Clause-scoped WH repair and fixed-curve replay | 6–12 h | Medium |
| Existing-annotation selection repairs, about 9 cases | 12–24 h | Low–medium |
| Typed-query contract | 24–60 h | Low |
| Choice-aware/latent-slot ellipsis path | 40–80 h | Low |
| Honest coverage of all 23 failures | 60–120 h or more | Low |

Fifteen of the 23 failures are still multi-relation or multi-step in semantic
shape, and only eight are direct-query candidates. A safe-role count can rise
without improving `compiled`, `fired`, or accuracy. The expected near-term
capability gain is therefore low.

### B — connect general multi-step deliberation to `back_chain`

`back_chain` is not wholly disconnected. The atomic path already submits a
typed direct goal to DELIBERATOR and binds proof leaves to provenance. The
missing work is a different contract:

- an immutable bounded conjunctive/DAG plan with named variables;
- explicit derive/prove/compare choice semantics;
- a read-only multi-subject fact accessor plus source-bound stem facts;
- sealed predicate, rule, and kernel registries; and
- independent replay of the complete multi-step proof tree.

In a qualitative, gold-blind sample of eight N/M-shaped items, one was
structurally compatible with the current engine after symbolic encoding, five
needed new domain rules, kernels, and compilers, and two required semantics
outside the current positive-Horn model. None was a ready wiring-only public
win.

| B scope | Time range | Confidence |
|---|---:|---|
| Typed graph-only linear demonstration | 6–12 h | Medium–high; mechanism only |
| Provenance-safe thin adapter | 16–32 h | Medium |
| Reusable multi-goal bridge and proof membrane | 26–50 h | Medium |
| One new domain-capability pilot | Additional 20–50 h | Low–medium |
| Broad coverage of the heterogeneous 25 N/M items | 80–240 h or more | Low |

B is more aligned with eventual capability than A, but it is not a grounded
six-to-eight-hour public-capability lever.

## 13. Formal closure and restart gate

Operator decision on 2026-07-26:

> Pause A-track. Accepted capability-gain-per-hour ordering:
> **A-track pause > B > A**.

This closes the current A-track as an evidence-preserving research branch:

- mechanism artifacts and staging remain intact;
- no staged artifact is promoted to the shipped graph;
- no E4, E5, E6, broad-science, GPQA, or production-authority claim is made;
- no further parser, predicate-family, or `back_chain` implementation follows
  from this ledger; and
- future work requires a separate operator approval.

A-track may be reconsidered only when a public or independently sealed item
family has all of the following before implementation:

1. the required premises demonstrably exist in the staged graph;
2. the family is solvable with the current engine or a small, explicitly
   bounded set of new rules/kernels;
3. an observable upper bound on correct firing can be preregistered;
4. the evaluation separates mechanism reach from strict accuracy and includes
   a fixed counterfactual control; and
5. the expected capability gain per hour exceeds the competing system axes.

Absent those conditions, increasing parser coverage, firing rate, or unit-test
coverage is maintenance evidence, not measured capability progress.
