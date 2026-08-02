# ATANOR G3 World4D Shadow Evidence

Status: narrow temporal-query M3; G3 remains an unfinished research gate
Recorded: 2026-07-25 KST
Scope: default-off sibling observation only; no E4/E5 or world-model claim

## 1. Why this seam exists

BlockUniverse, perception JEPA, and SPLATRA world-model experiments remain
separate mechanisms with incompatible state and evidence. The first safe
fusion step is a common predictive contract plus a sibling observer whose
adapter output is never applied to the answer path.

The existing BlockUniverse path already bids into the CGSR response workspace
at capped grounding `0.45`; it is a real conditional answer-influence path.
The new path only enqueues independent shadow observation before that legacy
bidder runs. Its result is ignored by the response workspace. This observer
does not make the legacy bidder non-authoritative and does not sandbox the
provider it calls.

## 2. Implemented slice

`packages/world4d` now provides:

- `World4DRequest` with bounded direction, horizon, branch count, source
  digest, and fixed read-only/no-authority flags;
- `World4DStep` restricted to `PREDICTED` or `RETRODICTED`, always a
  hypothesis and never accepted as fact;
- `World4DCheck` whose strongest positive verdict is
  `not_contradicted`, never `true`, `valid`, or `verified`;
- exact-key, type, size, count, direction/tier, quarantine, provider-identity,
  and request/source-pairing validation;
- bounded trajectories and provider results that are ineligible for live
  answer use;
- a generic provider protocol whose effects are not isolated or attested;
- a BlockUniverse provider using a private pathless in-memory timeline and a
  strict, byte-bounded, read-only load of
  `data/temporal_reasoning/precedence_field.json`;
- no dynamic fitting in the shadow provider; the frozen local artifact has
  byte SHA-256
  `53065e0bb97576b8980da45c597b354c655bd468fec66c2e33003845a442aac8`,
  but is unsigned, unsealed, and externally unattested;
- a default-off adapter that touches no request/provider/payload/sink factory
  while disabled;
- a bounded daemon dispatcher with a single queue of capacity 64; submission
  is nonblocking and overflow drops telemetry instead of delaying an answer;
- receipts capped at 8 KiB that exclude raw request and provider payloads;
- exact raw-ledger validation, canonical reconstruction, frozen error codes,
  and a strict hash-chained local JSONL observer sink;
- fixed receipt claims only that the observer adapter output was not applied
  to the answer. Provider effects are explicitly unattested and provider
  isolation is explicitly unenforced. Capability claims are empty and E4/E5
  are false.

Forward BlockUniverse rows form one ordered predicted trajectory of at most
three steps. Backward rows are separate one-step retrodicted alternatives;
they are not falsely flattened into a historical chain. Any provider row that
loses its explicit `hypothesis=true` marker is rejected.

The provider reuses the BlockUniverse projection algorithms over the separate
frozen precedence artifact. That does not establish equality with the learned
field assembled dynamically by the legacy causal-overlay path.

## 3. Live boundary and controlled evidence

After a query has passed the existing temporal grammar, the response workspace
checks exact server-side `ATANOR_WORLD4D_SHADOW=1`. Only then does it import and
submit work to the sibling observer. Non-temporal requests and other truthy
strings do not activate it. The legacy bidder then runs independently and
unchanged. A stalled provider or receipt lock can consume the sole observer
worker and cause subsequent telemetry to be dropped, but cannot block the
answer path.

The controlled profile is `world4d_shadow_control` in
`data/eval/catalog/baseline_suite_v1.json`. It runs the World4D contract,
provider, privacy, ledger, failure-containment, and live OFF/ON equivalence
tests twice with the process default set to OFF.

The historical execution receipt is
`reports/baseline_evidence/baseline_20260724T225531.739793Z_45bfaf0d04c9.manifest.json`.
It recorded two stable successful attempts, manifest hash
`86cbf9d3cebf0b0b7614771da7f0b6008fa1d5a585365f71b4c93cb8eb6767c7`,
file SHA-256
`8b9f4421cfa6d426da80f4f34fe99a19bd2cff9a8974bed43fd147cd29c13bf8`,
and `source.sealed=false`. It verified against its recorded dirty tree.
Subsequent registry and documentation edits make it historical evidence, not a
seal for the later tree. The controlled profile currently runs 40 World4D
tests per attempt, including a stalled-worker test that proves answer identity
while the observer worker remains blocked.

The runtime graph records five relevant scoped M3 edges:

- existing response workspace to the legacy BlockUniverse bidder;
- response workspace to the sibling World4D adapter;
- adapter to the BlockUniverse provider;
- provider to BlockUniverse;
- adapter to the receipt sink.

All five have empty capability claims and `e5_claimed=false`. The legacy edge
is explicitly a conditional decider, with one controlled forward temporal
answer trace only; it does not receipt-bind the backward or abstention paths.
The four observer edges are bounded guards with no answer authority.
Accordingly, the `cgsr` and `temporal_reasoning` organ rows have narrowly
scoped secondary authority because of the pre-existing legacy bidder, while
the new `world4d` observer has no canonical authority.

## 4. Explicit non-fusion and blockers

This slice does not bind a live JEPA or SPLATRA provider.

- Perception JEPA has no source-bound live checkpoint/provider contract.
- SPLATRA world-model training and proof code creates models or codecs
  in-process and returns arrays or `FieldState` values without a frozen
  inference artifact boundary.
- The SPLATRA physics gate checks a small bounded invariant set. Its `ok` result
  can mean only `not_contradicted` by those checks, never world truth.
- The local precedence artifact is unsigned and unsealed. It is not proven
  equal to the legacy causal-overlay field.
- The generic provider protocol has no process isolation, timeout, or
  side-effect attestation. One stalled observation can stop telemetry progress
  until restart even though it cannot stop the answer path.
- Logical temporal consistency, conformal calibration, real-video/sensor
  training, long-horizon stability, and shared object identity remain absent.
- The audited live constructor excludes raw prompts, event tokens, latent
  vectors, and particle arrays from persistence. Hashes of low-entropy inputs
  are not independently proven private, and the strict receipt is not a
  replayable copy of the provider payload.
- No production trace, external evaluator, immutable witness, or external ACL
  is bound.

A future SPLATRA/JEPA provider must load frozen model and codec digests, perform
inference on copies, avoid training and EMA updates, apply raw physics checks
without repairing a proposal into compliance, quarantine on contradiction,
and preserve uncertainty. It remains shadow-only until independent E4 and
paired E5 gates.

## 5. Gate decision

> One default-off, non-authoritative temporal-query World4D sibling observer
> reached scoped M3 wiring evidence on the recorded dirty tree. Focused tests
> preserved the legacy answer, kept the answer path nonblocking under a
> stalled observer, and forced every accepted projection to remain a
> hypothesis.

G3 does not exit until a shared event/object/pose/time schema, source-bound
world ledger, frozen inference providers, real video or sensor learning,
calibrated multi-step prediction, temporal-leakage controls, independent E4,
and paired downstream E5 lift are sealed.
