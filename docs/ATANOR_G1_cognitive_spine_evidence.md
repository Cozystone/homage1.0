# ATANOR G1 Cognitive Spine Evidence

Status: two narrow live-path M3 seams; G1 remains in progress
Recorded: 2026-07-25 KST
Scope: default-off chat plus sampled ContinuousSelf observation; no shared-state,
E4/E5, consciousness, or capability claim

## 1. Implemented slices

### 1.1 Chat boundary

The live `chat_atanor` boundary can open and close one canonical cognitive
cycle when server-owned `ATANOR_COGNITIVE_SHADOW` is exactly `1`. The disabled
branch returns before reading request fields or accessing its observer ledger.
Streaming reaches the same boundary and does not create a second cycle.

### 1.2 ContinuousSelf step boundary

The already-live `ContinuousSelf.step()` can now emit a sampled digest
projection when both of these server flags are exactly `1`:

- `ATANOR_COGNITIVE_SHADOW`
- `ATANOR_CONTINUOUS_SELF_CYCLE_SHADOW`

Only a pre-step tick divisible by 30 is sampled. The current observation and
pre/post state projections are detached while the existing self lock is held.
Receipt construction, queue submission, file locking, replay validation, and
append happen after that lock is released.

The observer calls the legacy step body zero additional times. Observer setup,
capture, receipt, queue, worker, and ledger faults cannot rerun the step,
replace its return object, or replace its original exception object and
traceback. A completed receipt means only that the legacy method reached its
return boundary.

The ContinuousSelf observer persists only deterministic digests of an exact
primitive allowlist: observation scalars, ticks and resume count, five bounded
vitals, introspective pressure, a fixed mode enum, research counters, an
open-question boolean, and collection lengths. The audited constructor
excludes raw thoughts, questions, understandings, timestamps, URLs, goals,
narrative entries, action and attention payloads, and the hormone dictionary.
The digests are unkeyed and low-entropy fields remain dictionary-testable and
linkable; they are not a privacy guarantee.

## 2. Shared contract and storage

Both seams use the canonical occurrence-level cycle contract:

- semantic IDs remain distinct from occurrence IDs;
- observations, propositions, episodes, goals, plans, actions, evaluations,
  and learning candidates have fixed entity kinds;
- events form a contiguous ingress-to-terminal chain with before/after state
  hashes;
- replay executes no model, tool, action, or network;
- receipt authority is observer-scoped and cannot authorize truth,
  permissions, promotion, routing, or legacy actions;
- JSONL record fields, literal indexes, reconstructed nested receipts, event
  status, hash-chain parents, and replay state must match exactly.

The chat and ContinuousSelf observers use separate ledger files. For each
process and resolved ledger path, the ContinuousSelf dispatcher has one
bounded daemon writer with queue capacity 8. Multiple API processes can
therefore create multiple writers for the same ledger; their appends and
configured 256-record/4-MiB caps serialize under the existing local
cross-process file lock. Configured byte overflow is rejected before full
parsing. Queue overload, writer failure, or quota exhaustion drops telemetry
instead of delaying the legacy step. These local controls do not establish
global single-writer ownership, an external ACL, immutable witness, or remote
durability.

The principal sources are:

- `packages/cognitive_core/cycle.py`
- `packages/cognitive_core/replay.py`
- `packages/cognitive_core/cycle_ledger.py`
- `packages/cognitive_core/chat_shadow.py`
- `packages/cognitive_core/continuous_self_shadow.py`
- `packages/continuous_self/loop.py`
- `apps/api/app/routers/dual_brain.py`
- `apps/api/app/routers/continuous_self.py`

## 3. Controlled evidence

The controlled profile is `cognitive_spine_control` in
`data/eval/catalog/baseline_suite_v1.json`. Its process defaults both observer
flags to `0`, disables networking cooperatively, and explicitly exercises the
enabled and disabled branches. Each attempt runs 94 tests covering contracts,
adapters, replay, exact ledger reconstruction, concurrent caps, privacy-field
exclusion, chat equivalence, ContinuousSelf sampling, exactly-once behavior,
original exception preservation, lock placement, async backlog, and stalled
writer behavior.

The historical execution receipt is
`reports/baseline_evidence/baseline_20260724T232815.306610Z_42f21ef3d6f0.manifest.json`.
It recorded two stable successful attempts, manifest hash
`2a3d1a0cc7079797f093fcc8551f9a4d77f1638f029164b13cb626f774bc0f1a`,
file SHA-256
`a5b3443918a29dde763dd0af803804b653ace9861c8eb3589b41637cd89c96a5`,
and `source.sealed=false`. It verified immediately against its recorded dirty
tree. Subsequent registry and documentation changes make it historical
evidence, not a seal for the later tree.

The source-bound runtime graph records four scoped cognitive M3 edges:

- `chat_boundary_to_cognitive_shadow`;
- `cognitive_shadow_to_cycle_ledger`;
- `continuous_self_step_to_cognitive_shadow`;
- `continuous_self_shadow_to_cycle_ledger`.

All have empty capability claims, `e5_claimed=false`, and zero production
traces. The existing `continuous_self_to_intrinsic_drive` edge remains M1,
unattested, and without a controlled or production trace.

The organ registry classifies `cognitive_core` as `live_conditional` M3, while
the whole legacy `continuous_self` organ is recorded separately as
`live_default` M1. The latter is imported and started by the API regardless of
the default-off observer flags, so assigning the observer's M3 stage to the
whole organ would be a false promotion. The scoped M3 claim exists only on the
four runtime-graph edges above and on the `cognitive_core` observer package.
Both organ rows retain registry authority `none`. Here `none` means the
registry grants or infers no authority. It does not mean that the legacy
ContinuousSelf step lacks persistent or external effects.

## 4. Ownership and unresolved effects

For chat, `dual_brain.chat_atanor` owns ingress and terminal observation. For
ContinuousSelf, the existing step lock owns only the synchronous mutation
region. The observer projection is not the canonical live or persisted
`SelfState`.

The legacy step can evolve and save self-state, perform research, apply
already-approved parameter changes, create or stage proposals, trigger
self-improvement, start intrinsic-drive and roamer work, converse or post
through enabled integrations, retrain lexical state, and append monologue
material. Background threads can outlive the step and receive mutable state
without honoring the self lock. The observer does not authorize, block,
isolate, enumerate, or prove completion of those effects.

API workers can also instantiate separate ContinuousSelf loops against the
same state path. The current temporary-file replace has no process-level
state-owner lease or CAS. Cross-process state consistency, parent-cycle
continuity, session identity, and a controlled legacy seed remain unresolved.

Migration therefore remains:

`inventory -> contract -> adapter -> shadow -> paired evaluation -> canary ->
primary/fallback -> retirement`

No duplicate router, self loop, state store, or background action path is
retired by this slice.

## 5. Explicit limitations

- Digest replay is structural, not complete private-payload or live-state
  replay.
- A returned-step receipt does not show that swallowed internal operations
  succeeded, that `save_state` persisted, or that background effects completed.
- The observer-scoped false authority fields do not characterize the legacy
  step's action, truth, permission, or promotion effects; those remain
  unattested.
- Cross-process state ownership and unlocked daemon-thread mutation remain
  unresolved.
- The receipt dispatcher is single-worker only per process and resolved ledger
  path; concurrent processes may each own a worker for the shared ledger.
- The local ledger lacks external key custody, signature, append-only witness,
  remote durability, and production exercise.
- An earlier unsealed local diagnostic of the broader dual-brain API had 20
  failures and 33 passes. That separate regression debt is not hidden by this
  focused green profile.
- The repository is dirty and the command receipt reports
  `source.sealed=false`.

## 6. Gate decision

> Two default-off live observation seams have scoped M3 wiring evidence: chat,
> and a sampled ContinuousSelf step projection. The latter preserves
> exactly-once legacy execution and moves ledger work outside the self lock,
> but does not make the legacy step side-effect-free, fault-transparent,
> authoritative, shared-state canonical, or capability-improving.

G1 does not exit until complete-cycle private replay, deterministic seeded
transitions, all critical-path adapters, one real shared state loop, safe
cross-process ownership, and independent E4 conformance are sealed. This work
does not demonstrate GPQA, ARC, general reasoning, local frontier-model
parity, phenomenal consciousness, AGI, ASI, or E5 lift.
