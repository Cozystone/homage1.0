# autonomy_envelope — F5, the autonomy SAFETY ENVELOPE

The non-negotiable prerequisite before ATANOR ever runs unsupervised. It is what makes an
overnight autonomous run (밤새 스스로) **safe** rather than reckless. It GATES **F3** (controlled
unsupervised) and **F-FINAL** — no unsupervised run is legitimate without it verified. Design:
`docs/ATANOR_final_fusion_design.md` **§5**.

Built to **ENFORCE**, not to theater. **Default-DENY everywhere; the safe failure is to block.**

## The one interface (decoupled from `fusion_loop`)
The fusion loop (agent #84) calls an *envelope hook* before every side-effecting action. We define
that contract here (`interface.py`) and implement the enforcing side — **neither package imports the
other**. Structural `Protocol`, so `fusion_loop` declares its own identical copy:

```python
class EnvelopeHook(Protocol):
    def check(self, action: EnvelopeAction) -> EnvelopeDecision: ...
```

`AutonomyEnvelope.check(action)` returns allow/deny + reason. `DefaultDenyEnvelope` (denies
everything) is the floor a loop falls back to if it was handed no real envelope.

## Five components (§5)
| # | component | file | mechanism |
|---|-----------|------|-----------|
| 1 | **capability WHITELIST** | `whitelist.py` | exactly `read / graph_inject / invent` (a `frozenset` the loop cannot widen). Anything else → **default-DENY, blocked + logged** |
| 2 | **KILLSWITCH** | `killswitch.py` | operator file marker, checked **first, before every action**; engaged → HALT instantly, halt recorded |
| 3 | **AUDIT LEDGER** | `audit_ledger.py` | append-only, **hash-chained JSONL**; `verify_chain()` detects any edited/deleted/reordered past record |
| 4 | **constant integrity + evaluation ratchet** | `constants.py`, `evaluation_trust.py` | moral 0th and the local frozen-oracle *specification* are checked fail-closed; no-regression accepts only an exact externally signed receipt, binds every live artifact digest, rejects replay, and atomically persists a baseline per comparable scope |
| 5 | **operator-governed PROMOTION** | `promotion_queue.py`, `operator_trust.py`, `scripts/landing_chain_lib.py` | shipped-graph writes are **queued**, not applied; the phrase gate creates only an operator-confirmed staging receipt. The final side-effect boundary internally loads one installation-fixed external config binding the Ed25519 key pin, operator-boundary identity, target, and replay domain; callers cannot inject them. Exact v3 signature, immutable mutation-batch hash, live-context, nonce, sealed-byte, journal, and deployment checks are necessary production conditions. |

`envelope.py` composes them into the single `check()` gate: **killswitch → constants integrity →
moral 0th → shipped-write queue → whitelist default-deny → allow**, logging **every** decision.

## Evaluation authority is separate from an oracle specification

`FrozenOracle` proves only that the verifier description held by this process has not drifted. It
does not execute a benchmark and cannot attest that a number came from that benchmark.
`AutonomyEnvelope` therefore has **no evaluation authority by default**. `mark_cycle(0.9)` and
`mark_cycle(..., evidence={...})` are denied and never ratchet.

A cycle can hold or raise a baseline only when an externally provisioned `OperatorTrustRoot`
validates an exact Ed25519-signed receipt. The receipt binds the live oracle fingerprint plus
metric, suite, dataset, candidate, evaluator, and outcome SHA-256 digests, the finite normalized
score, run ID, UTC window, and nonce. The caller must separately supply the exact live context.
The nonce is claimed exclusively, and the authenticated baseline is stored atomically under the
envelope root. Comparison scope includes oracle, metric, suite, dataset, and evaluator identities;
incomparable suites or metrics never share a ratchet.

## The five SEALED gates (tests are constitution)
```
python -X utf8 -m pytest packages/autonomy_envelope/ --import-mode=importlib -q
```
- **(a)** out-of-whitelist action → BLOCKED + audit-logged — `test_whitelist_default_deny.py`
- **(b)** killswitch set → loop stops immediately, halt recorded — `test_killswitch.py`
- **(c)** ledger complete + hash-chain tamper-evident — `test_audit_ledger_tamper.py`
- **(d)** unsigned shipped-graph promotion refused (queued) — `test_promotion_unsigned_refused.py`; detached authority is purpose-bound and tamper-checked in `test_operator_trust.py`
- **(e)** frozen-oracle immutable from inside the loop — `test_frozen_oracle_immutable.py`
- signed evaluation schema, live binding, replay rejection, persistence, authenticated state,
  and scope separation — `test_evaluation_trust.py`
- integration + moral-0th no-off-switch + a full night cycle — `test_envelope_integration.py`

## Honest limits (named plainly, as the genesis_sandbox report did)
This is **cooperative, in-process** enforcement at the level of the loop's *sanctioned action API* —
it is **not** an OS sandbox. Named soft spots:

- **Killswitch is cooperative.** It halts the loop's action path at its next `check`/`require_live`.
  It does not preempt a native/blocking syscall already in flight that never returns to the check. It
  IS a hard, out-of-band stop the operator controls without the loop's help, and every side-effecting
  loop step routes through the envelope, so each one sees the switch.
- **Audit ledger is tamper-EVIDENT, not tamper-PROOF.** It lives on the operator's disk; an actor with
  write access can delete the whole file — the chain proves integrity of what *remains*, not its
  existence. It is not a remote WORM store, and we do not claim it is.
- **Constants are single-point tamper-detected, not multi-point-proof.** The moral fingerprint and the
  frozen-oracle seal detect any *single* out-of-band mutation and fail the envelope **closed** (deny
  all). A determined in-process actor with full attribute access to *both* a sealed value and its
  witness is the cooperative boundary — the same boundary genesis_sandbox named. The loop's own API
  exposes no path to it, and any attempt through the API is written to the tamper-evident ledger.
- **A signed evaluation receipt authenticates an assertion; it does not prove evaluator quality.**
  The signature and hashes prove which operator-pinned evaluator/result artifacts were asserted,
  not that the evaluator is unbiased, the benchmark is capability-valid, or the outcome artifact
  was computed correctly. E4/E5 paired capability evidence remains a separate gate.
- **The evaluation ratchet is local durable state, not a remote monotonic anchor.** Atomic replace,
  authenticated last receipts, exact scope binding, and exclusive nonce claims prevent ordinary
  partial writes, caller-score injection, and local concurrent replay. An actor with unrestricted
  disk access can delete or roll back the state and nonce directory together. Production needs
  operator-controlled ACL/isolation and preferably a remote append-only/WORM checkpoint.
- **The evaluator key pin is a deployment trust obligation.** The module checks that the public key
  matches an independently supplied pin and never holds a private key, but cannot prove that the
  pin arrived through a human-controlled channel. Tests use ephemeral fixture keys only; the
  repository contains no fabricated production evaluator key.
- **The phrase receipt is not a cryptographic signature.** It can stage a reversible review
  artifact, but it sets `cryptographically_signed=false` and `merge_authorized=false`. A receipt
  path is created exclusively: any existing path is a hard collision, never parsed or reused.
  Its exact byte SHA-256 is recorded in the hash-chained ledger. Production authorization is a
  detached Ed25519 signature verified against a pinned public key outside the repository; the
  private key is never available to ATANOR.
- **Detached verification and the landing chain remain mechanisms, not capability.** The strict
  v3 document binds the staging receipt, candidate, immutable mutation-batch manifest, item IDs, target, fixed boundary/config,
  base/recovery digests, replay-domain identity, UTC window, and nonce to the live context.
  The landing chain consumes the nonce in an externally pinned domain, journals the swap,
  preserves recovery bytes, and the Linux builder accepts only a committed signed generation.
  These controls still cannot prove that deployment ACLs were provisioned by the human
  operator, that an unrestricted root process did not later tamper with the image, or that the
  promoted graph improves any benchmark. Image signing, secure boot, independent E4/E5
  evaluation, and external deployment attestation remain separate obligations.
- **Moral 0th text screening is heuristic; the current fingerprint is process-local.** The screen
  is not a perfect intent classifier. The in-process fingerprint detects runtime drift, but a
  restart after a coordinated source rewrite can redefine both value and expected hash. The
  external signed-policy verifier closes that design gap only after an operator provisions an
  out-of-repository public trust root and signed policy; until then this remains an explicit
  production blocker, backstopped only by the cooperative envelope and sandbox layers.

**No off-switch for the moral 0th gate or the frozen oracle** — only for the loop (the killswitch).
That asymmetry is deliberate and enforced by construction (no disabling parameter exists).
