# ATANOR GWIP / ARC-I0 final status — 2026-07-28

> **Closure boundary:** the GWIP synthetic mechanism and capability line is
> complete and evidence-sealed. The final results are
> `MECHANISM_GREEN` and `CAPABILITY_GREEN` on the preregistered generated
> unseen-mechanics/transfer cohort. This is not a public ARC-AGI result, an
> independent E5 judgment, a general world-model result, or production
> activation authority. Production remains default-OFF.

## 1. Final verdict

The common interaction loop successfully binds the existing
`WorldSnapshot`, `GoalIR`, `DecisionReceipt`, replay, perception,
situation-model, transition-graph, affordance, DELIBERATOR, and `RunLease`
parts behind a domain-neutral
`reset -> observe -> valid_actions -> step -> stop` contract.

The evidence curve must be read in two separate layers:

| Layer | Sealed result | Honest claim |
|---|---|---|
| Mechanism | `MECHANISM_GREEN` | the existing parts form a deterministic, lineage-complete, budget-bounded, domain-neutral loop |
| Synthetic capability | v1 `RED`, v3 `RED`, v4 `GREEN` | the frozen candidate beats preregistered controls and transfers on the fixed generated cohort after evaluator defects were corrected |
| Public/external capability | not measured here | no ARC-AGI, MSH, E5, AGI, or ASI claim |
| Production authority | OFF | no activation or promotion was approved |

The v1 and v3 `CAPABILITY_RED` receipts remain valid immutable records of
their evaluators' verdicts. Later diagnosis established that their failed
gates came from evaluator/verifier defects rather than the candidate's
measured behavior. v4 did not rewrite those receipts: it used a separately
preregistered one-shot execution with the same candidate and semantic cohort.

## 2. Sealed chronology

| Stage | Commit | Result or purpose |
|---|---|---|
| Common-loop preregistration | `820ebdb3` | mechanism contract fixed before implementation |
| General interaction loop | `6fefe239` | existing parts bound; no ARC-specific candidate branch |
| Complete lineage surface | `9007e133` | world, goal, decision, transition, and authority lineage |
| Mechanism evidence | `1ebad766` | `MECHANISM_GREEN` |
| Frozen capability candidate C | `51de7aadf188f9889ff1ea051012693e5aa529e2` | bounded rule-transfer candidate |
| Capability v1 evidence | `0dc47e37` | `CAPABILITY_RED` |
| Terminal-stop evaluator correction | `c7f71617` | evaluator-only correction |
| Step-local retained-memory verifier correction | `7752bbd4` | verifier-only correction |
| Capability v3 evidence | `7cac1b6a` | `CAPABILITY_RED` |
| Complete parent-valid stop-state correction | `28a61ccb` | v4 evaluator and preregistration seal |
| Isolated candidate-C package tree | `27520a71` | current-history package drift removed without weakening the gate |
| v4 evaluator seal | `3df7d258` | same 12 hard gates; isolated runner |
| v4 seed and schedule | `91a99449`, `c2bc07dd` | fixed cohort and semantic schedule |
| v4 evidence | `796c1df3d04a5119ff85ae16ab73981cb48bc774` | `CAPABILITY_GREEN` |

No empirical v2 capability attempt exists. v3 was the next sealed empirical
attempt after v1, and v4 was the next one after v3. None was retried.

The v4 execution used an isolated worktree whose complete tracked and working
`packages/` tree matched candidate C. The full-tree fixed-source guard was not
relaxed to an allowlist. This was necessary because six unrelated package
paths had changed on the main history after candidate C even though the four
direct GWIP candidate files had not.

## 3. Mechanism evidence

The mechanism cohort contained 48 evaluator-generated opaque finite-state
mechanics. It ran three candidate episodes per mechanic, with memory allowed
inside a mechanic and hard-reset between mechanics. Random-control aggregates
covered 4,608 underlying executions.

| Policy | Mean SWAE | Success |
|---|---:|---:|
| Candidate | `0.595815282212341` | `142/144 = 0.9861111111111112` |
| Reactive | `0.16504629629629627` | `30/144 = 0.20833333333333334` |
| Random, 32 seeds | `0.3718304561345571` | `3831/4608 = 0.8313802083333334` |

| Comparison | Mean SWAE lift | One-sided 95% bootstrap LCB |
|---|---:|---:|
| Candidate minus reactive | `0.430769` | `0.362676` |
| Candidate minus random | `0.223985` | `0.191775` |

All 12 mechanism hard gates passed. The loop demonstrated deterministic
replay, complete state/action lineage, enforced step budget and stop,
evaluator-owned `RunLease` authority, adversarial self-attestation rejection,
and zero ARC-specific branch in the candidate core. This is real mechanism
evidence, but it is not by itself a capability claim.

Primary mechanism receipt:
`data/eval/gwip_mechanism_receipt_v1.json`.
Its sealed receipt checksum is
`101c641ba305236899cb3b24fad7dad73abc0128025b84efd41e0aff97939f4b`.

## 4. Capability contract

The capability experiment froze all of the following before execution:

- 64 private capability pairs;
- support, target, and counterfactual moduli `13`, `17`, and `19`;
- four actions, four support episodes per pair, and four target episodes per
  arm;
- matched-warm, cold, and mismatched-warm target arms;
- 1,024 candidate episodes and a 24-step budget;
- 32 random-policy seeds;
- 10,000 pair-grain bootstrap resamples with seed `2026072702`;
- the candidate, private cohort, ordered schedule, metric thresholds, and all
  12 hard gates;
- target-episode learning forbidden; and
- `production_default_on=false`.

The four capability sections were fresh success, fresh normalized regret,
rule discovery, and structurally different environment transfer. A capability
claim required all four metric sections and all 12 hard gates simultaneously.

## 5. v1 and v3 RED causes

### v1

v1 passed all four capability metric sections but failed six hard gates:

- `call_order_and_stop`;
- `step_budget_and_pre_mutation_denial`;
- `complete_lineage`;
- `structural_cycle_replay`;
- `semantic_reexecution_determinism`; and
- `fresh_environment_reexecution`.

Two independent evaluator/verifier defects explained the failures:

1. The call-order auditor rejected 627 legal `goal_reached` episodes whose
   parent-owned tail was terminal `step -> stop`.
2. The cycle verifier reused episode-start `memory_before` while checking
   every step. In support episodes with `retain_policy_updates=true`, it
   therefore compared the policy's real mid-episode rule/memory state against
   a stale state. This produced 95
   `hypothesis_set_memory_mismatch` /
   `usable_rule_set_mismatch` findings and propagated into lineage and
   re-execution gates.

The first correction was sealed in `c7f71617`; the second in `7752bbd4`.
Synthetic buggy-to-fixed fixtures were added before resealing. Candidate C
was not changed.

### v3

The retained-memory correction was validated by v3: all four lineage and
re-execution gates that failed in v1 became GREEN. The two remaining failed
gates were:

- `call_order_and_stop`; and
- `step_budget_and_pre_mutation_denial`.

Exactly 397 ordinals were rejected. They were disjoint from the 627 v1
call-order ordinals; together the two sets partitioned all 1,024 scheduled
candidate episodes. v3 correctly accepted `goal_reached` but falsely rejected
every normal `step_budget_exhausted` path. After the 24th nonterminal step, the
parent protocol legally performed
`observe -> valid_actions -> stop`; the v3 auditor incorrectly demanded an
immediate stop.

Read-only replay of all 5,120 parent sessions in each sealed v1 and v3 raw
artifact under the corrected parent-state audit produced zero call-order
failures. The complete correction, including all normal and error stop
locations, was preregistered and sealed in `28a61ccb`.

## 6. v4 capability result

v4 passed all 12 hard gates:

1. `call_order_and_stop`
2. `step_budget_and_pre_mutation_denial`
3. `run_lease_direct_authority`
4. `run_lease_single_use_and_replay_rejection`
5. `adversarial_self_attestation_rejection`
6. `complete_lineage`
7. `structural_cycle_replay`
8. `semantic_reexecution_determinism`
9. `fresh_environment_reexecution`
10. `candidate_domain_neutrality`
11. `candidate_runtime_import_closure`
12. `candidate_fixed_source_guard_controls`

It also passed all four preregistered metric sections:

| Section | Candidate | Controls / contrast | Preregistered statistical evidence |
|---|---:|---:|---:|
| Fresh success | `0.98828125` | reactive `0.29296875`; random `0.8475341796875` | lift `0.6953125` / `0.1407470703125`; LCB `0.65234375` / `0.1279296875` |
| Fresh regret | `0.16154729554865424` | reactive `0.7218945569828722`; random `0.42127592954486637` | reduction `0.560347261434218` / `0.2597286339962121`; LCB `0.5182346808535667` / `0.24669203927865613` |
| Rule discovery | `63/64` pairs | one censored pair | median action `16`; p75 action `17` |
| Transfer | matched success `0.9921875`; regret `0.0078125` | cold/mismatched success `0.234375`; cold regret `0.7798123411914173` | success lift/LCB `0.7578125` / `0.703125`; regret reduction/LCB `0.7719998411914173` / `0.7206848178994918` |

The receipt verdict is `CAPABILITY_GREEN`, with
`capability_claim=true`, `public_benchmark_claim=false`,
`production_activation_authorized=false`, and
`production_default_on=false`.

### Human-readable efficient episode

The fixed receipt exemplar is pair `0`, episode `2`, ordinal `2`. It starts at
an observation whose register is `1` under modulus `13`, with a structured
goal requiring register `11`. The candidate selects
`action_79bda1ed22d70e8634223c232663dd77`; the next observation has register
`11`, is terminal, and satisfies the goal. The parent protocol then records:

```text
RESET state_165d...
OBSERVE register=1, modulus=13
VALID_ACTIONS four evaluator-owned action refs
DECIDE action_79bd...
AUTHORIZE through evaluator-owned RunLease
STEP state_605e..., register=11, terminal=true, success=true
STOP reason=goal_reached, steps=1
```

The receipt contains no private oracle fields in this exemplar. The full
world, goal, decision, action, transition, authority, and replay lineage is in
the sealed raw evidence.

## 7. Exact metric identity across attempts

Candidate C, the private cohort, schedule semantics, thresholds, and target
learning prohibition remained fixed. Independent JSON equality checks show
that every efficacy section is exactly equal across v1, v3, and v4, including
the final floating-point digits:

| Metric section | v1 = v3 | v1 = v4 | Canonical section SHA-256 |
|---|---:|---:|---|
| `fresh_success` | yes | yes | `308686ab28fa3a1860d33ac54973941bb5288f1eb1fcbab991b72a42fa33c5d6` |
| `fresh_regret` | yes | yes | `7335fda12e7330055ffd5fb9acf8bc8384fa880370670493625071d5993bc0d9` |
| `rule_discovery` | yes | yes | `2d68a622b0f07d519dafe993e32a46c785c59aa1696fefd5a9b07e57d268fe6d` |
| `transfer` | yes | yes | `48f871f37d8f4337232c056b66a715d032ea5cb5a18b0bcb218486b85cc94f11` |

Thus the RED-to-GREEN verdict transition was not produced by candidate
tuning, threshold relaxation, dataset replacement, or favorable metric
movement. It came from correcting evaluator/verifier interpretation while
holding the measured behavior fixed. The raw and authority archives are still
distinct execution artifacts and are not byte-identical; the equality claim
is specifically about the four sealed efficacy sections.

## 8. Durable v4 evidence binding

The local tag
`sealed/gwip-capability-v4-green-2026-07-28` resolves exactly to
`796c1df3d04a5119ff85ae16ab73981cb48bc774`.
It keeps the v4 commit and its large evidence objects reachable even if the
isolated worktree is later removed.

| Artifact at the sealed tag | Bytes | File SHA-256 |
|---|---:|---|
| `data/eval/gwip_capability_receipt_v4.json` | 75,453 | `3d8545b1000baa45d4cc010f885f98f12fa9b4b368cdef63de5c0bfc0801b6d8` |
| `data/eval/gwip_capability_raw_evidence_v4.json.gz` | 161,188,307 | `3f223842b8efd6e8ca1a2700763c00ee9e1ed12efb66a50f7e8b1e0097a023b1` |
| `data/eval/gwip_capability_authority_v4.tar.gz` | 229,558,020 | `04ef7d7c9e03b751a866af240abbef1745701756af639431fa05030265a12ad7` |

The receipt's internal canonical checksum is
`eb92d813d13d9d74754116fef6c391b16614611f68cf1880fe14b81dc361cbd1`.
It is intentionally distinguished from the receipt file's byte-level SHA-256.
Independent post-run hashing matched the raw and authority bindings recorded
inside the receipt.

## 9. What GREEN does and does not mean

`CAPABILITY_GREEN` means that the frozen candidate passed the preregistered
fresh-success, regret, rule-discovery, and transfer thresholds while every
independently recomputed hard gate passed in the same sealed attempt.

It does not establish:

- performance on ARC-AGI-3 or any other public benchmark;
- robustness outside the generated affine cross-modulus family;
- an independent external E5 judge or contamination-free public result;
- optimal planning, a general world model, AGI, or ASI;
- an OS-level sandbox rather than the reviewed Python isolation boundary; or
- production activation authority.

Mechanism GREEN was necessary but not capability evidence. Synthetic
capability GREEN is real scoped capability evidence but not external
generalization evidence. The next honest gate is an external blind judge such
as MSH, not another retuning pass over this sealed synthetic cohort.

## 10. Formal closure

The GWIP synthetic line is closed with:

- mechanism evidence preserved at `MECHANISM_GREEN`;
- v1 and v3 RED evidence preserved without retrospective rewriting;
- v4 one-shot evidence preserved at `CAPABILITY_GREEN`;
- all candidate, dataset, threshold, lineage, authority, and fixed-source
  boundaries retained;
- production default OFF;
- no staging or shipped-graph promotion; and
- no push.

Any public benchmark, E5, production, ARC-AGI, AGI, or ASI claim requires a
separate external measurement and its own authority boundary.
