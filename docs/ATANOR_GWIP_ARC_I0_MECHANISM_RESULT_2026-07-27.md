# ATANOR GWIP / ARC-I0 mechanism result — 2026-07-27

## Final verdict

**`MECHANISM_GREEN`**

This is a bounded, fixed-source, controlled mechanism result. It is not an
ARC-AGI score, a public-benchmark result, E5 capability evidence, a production
activation decision, or evidence of general world-model capability. The sealed
receipt records:

- `capability_claim=false`
- `public_benchmark_claim=false`
- `production_activation_authorized=false`

The one independent post-run verification returned:

```json
{
  "valid": true,
  "verdict": "MECHANISM_GREEN",
  "findings": []
}
```

## What was bound

The existing `WorldSnapshot`, `GoalIR`, `DecisionReceipt`, replay,
perception/situation state, transition graph, affordance proposal,
DELIBERATOR-facing policy surface, and `RunLease` were joined behind one
domain-neutral loop:

```text
reset → observe → valid_actions → propose/decide
      → evaluator-owned RunLease authorization → step → … → stop
```

No ARC-specific branch or import is present in the coordinator/candidate
execution closure. This does not mean that the rest of the repository contains
no ARC code.

## Frozen chronology and one-run discipline

1. Preregistration: `820ebdb389034edbffdb38a28d6aa4acffd070ba`
2. Candidate source seal: `84e63520a2f59df62faaa5dbc74e0bfbb99deabd`
3. Evaluator source seal: `848bb2da656baa6c76b765ea3fc460f4413f1d8c`
4. Fresh post-evaluator seed manifest:
   `ebf40a5cfc2f99413c2f276f6365d4409a263807`
5. Seed-manifest SHA-256:
   `2339ad756449602ba0e6d5a3375386423b3b73cbe90bf79ae63410eaa4733110`
6. External RunLease-plan SHA-256:
   `80e0409aca3646d0e7459205f1e00d54562e24ff27fce184af9af90b665a07d4`
7. The designated final cohort was executed exactly once. No metric was seen
   before the attempt marker was written, and the cohort was not retried.

An older seed manifest was rejected before episode generation because its
evaluator audit was over-broad and its seed predated the corrected evaluator.
It produced no attempt artifact, consumed no lease, and produced no result.
The candidate remained byte-identical. The final evaluator was then sealed,
a never-before-committed seed/nonce was generated, and only that fresh cohort
was executed.

## Controlled efficiency result

The evaluator generated 48 opaque deterministic finite-state mechanics after
the candidate source seal. There were three candidate episodes per mechanic
(144 total); memory was permitted within a mechanic and hard-reset between
mechanics. Random used 32 independently seeded executions per aggregate cell,
or 4,608 underlying executions.

| Policy | Mean SWAE | Success |
|---|---:|---:|
| Candidate | 0.595815 | 142/144 = 0.986111 |
| Reactive | 0.165046 | 30/144 = 0.208333 |
| Random | 0.371830 | 3831/4608 = 0.831380 |

The preregistered mechanic-grain paired gate required mean SWAE delta at least
0.05, a positive one-sided 95% paired-bootstrap lower confidence bound, and
success non-regression against both baselines.

| Comparison | Mean SWAE delta | One-sided 95% LCB | Gate |
|---|---:|---:|---|
| Candidate − reactive | +0.430769 | +0.362676 | PASS |
| Candidate − random | +0.223985 | +0.191775 | PASS |

Therefore the approved mechanism-stage no-go condition was not triggered.
This is a signal inside the sealed synthetic discriminator, not permission to
claim broad capability lift.

## Hard gates

All 12 independently recomputed hard gates passed:

1. call order and exactly one terminal `stop`
2. step budget and pre-mutation denial
3. direct evaluator-owned RunLease authority
4. RunLease single use and replay rejection
5. adversarial DecisionReceipt/WorldSnapshot/authority self-attestation rejection
6. complete world/goal/proposal/decision/transition/authority lineage
7. structural cycle replay
8. semantic re-execution determinism
9. fresh-environment re-execution
10. candidate domain neutrality
11. candidate runtime import-closure audit
12. fixed-source guard controls

The authority evidence contains 144 distinct signed leases and their claim and
active ledgers. Candidate-submitted authority values are not accepted as
proof: the evaluator reconstructs the authorization/finish transcript from
the external ledger and call log, then compares it with the worker result and
serialized lineage.

The post-run authority re-audit found exactly one claim and one active state
for each of 144 episodes; all lease, nonce, boundary, replay-root, ledger,
deployment, runtime, operator-boundary, and ledger-byte identities were unique.
All 144 Ed25519 signatures verified independently against the archived public
key. Across 810 executed steps, reconstructed authorizations matched the
operational evidence, lineage, finish record, and transcript digest exactly.

## One complete human-readable episode

This is the receipt's fixed first episode, not a median or efficiency showcase.
It succeeded in 14 steps although the optimum was 2, so its own SWAE was
0.142857. Its purpose here is to demonstrate a complete, inspectable
reset-to-stop trace.

Abbreviations:

- states: `S0=43f8`, `S1=6361`, `S2=b4ba`, `S3=0592`,
  `S4=1347`, `S5=bf1d`, `G=6ffd`
- actions: `A=4b6b`, `B=9b4e`, `C=b51b`

```text
RESET S0, goal=G
01 OBSERVE S0 | VALID [A,B,C] | DECIDE B | AUTHORIZE | STEP S1
02 OBSERVE S1 | VALID [A,B,C] | DECIDE A | AUTHORIZE | STEP S0
03 OBSERVE S0 | VALID [A,B,C] | DECIDE C | AUTHORIZE | STEP S1
04 OBSERVE S1 | VALID [A,B,C] | DECIDE C | AUTHORIZE | STEP S2
05 OBSERVE S2 | VALID [A,B,C] | DECIDE C | AUTHORIZE | STEP S3
06 OBSERVE S3 | VALID [A,B,C] | DECIDE B | AUTHORIZE | STEP S3
07 OBSERVE S3 | VALID [A,B,C] | DECIDE A | AUTHORIZE | STEP S2
08 OBSERVE S2 | VALID [A,B,C] | DECIDE A | AUTHORIZE | STEP S3
09 OBSERVE S3 | VALID [A,B,C] | DECIDE C | AUTHORIZE | STEP S4
10 OBSERVE S4 | VALID [A,B,C] | DECIDE B | AUTHORIZE | STEP S0
11 OBSERVE S0 | VALID [A,B,C] | DECIDE A | AUTHORIZE | STEP S4
12 OBSERVE S4 | VALID [A,B,C] | DECIDE C | AUTHORIZE | STEP S5
13 OBSERVE S5 | VALID [A,B,C] | DECIDE A | AUTHORIZE | STEP S1
14 OBSERVE S1 | VALID [A,B,C] | DECIDE B | AUTHORIZE | STEP G terminal=true
STOP reason=goal_reached success=true steps=14 optimal=2
semantic_trace=1d5bc06f66f1c298da3a16781aca2ef7389637e95f01b628a121050d9e68e16c
```

Every numbered step has its own `WorldSnapshot`, shared `GoalIR`,
affordance/proposal, `DecisionReceipt`, evaluator-authorized RunLease
transcript, observed next state, and learned transition-edge identifiers in
the raw lineage. The compact rendering above omits only those long identifiers.

## Evidence bindings

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `gwip_mechanism_attempt_v1.json` | 564 | `40f6f3e01182245baaaeb9760e1b9446dad1211dd14cfab125a172d6b70e800e` |
| uncompressed raw evidence | 160,815,419 | `c3df6d9134046d9441b4e80cd15584368f32bc61f2234cd916509757e7d4875d` |
| committed raw-evidence archive | 7,980,407 | `20cf4905e0c8bc661470132a5794422ea6e7aace663c21fe6eddf684eb88c886` |
| `gwip_mechanism_receipt_v1.json` | 1,004,074 | `155a210750ec311c07e7be20c195e05e3eebc8e37f11c86a47183c58774c8a41` |
| committed authority-ledger archive | 168,948 | `b72cfe407141c7bd1fb413a2cec14be17d70aa8cc8ed42f9dc861f20192f0be2` |

The raw archive expands byte-for-byte to the raw-evidence SHA-256 above. The
receipt's internal canonical raw-evidence digest is
`8fdd66b3eed0dfcc84fd0514738e1d83a9a42dd48dc6ff99e561bbe77a6d6efe`;
its sealed receipt checksum is
`101c641ba305236899cb3b24fad7dad73abc0128025b84efd41e0aff97939f4b`.

Independent read-only recomputation reproduced all three SWAE values, all
three success values, both paired deltas, both bootstrap lower bounds, every
source/seed/raw/receipt binding, and the final `MECHANISM_GREEN` verdict.

## Explicit limitations

- fixed generated opaque-FST discriminator, not a public benchmark
- three episodes per mechanic with within-mechanic memory, not 144 pure
  zero-shot trials
- repository-local fixed-source evaluator, not an independent E5 judge
- reviewed Python guard, not an OS sandbox
- non-action RunLease resource counters are declared fixed costs, not OS
  observations
- designated local attempt, without an external global-uniqueness notary
- default remains OFF; no production activation was approved
- no claim of optimal planning, ARC score improvement, AGI, or ASI
