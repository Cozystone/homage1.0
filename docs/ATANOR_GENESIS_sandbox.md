# ATANOR-GENESIS Containment Sandbox

**Package:** `packages/genesis_sandbox/`
**Status:** v0 — built and breach-tested (51 passed / 1 skipped; red-team suite: 0 BREACH).
**Scope:** GENESIS research line only (`GENESIS_CHARTER.md`). White-hat, on our own sandbox.
**Flag:** `ATANOR_GENESIS_SANDBOX` (default **OFF**). The DEMO product does not import this
package, so the shipped product path is unaffected whether the flag is set or not.

---

## 1. The one idea

> **Liberate OUTPUT / cognition. Contain ACTION.**

Inside the sandbox, ATANOR's cognition is allowed to run **unthrottled** — free generation and
speculation, with the product's hallucination-0 abstention membrane set to *observe-only* (log,
don't block). That is the liberation, and it liberates **output only**. Around that liberated
core sit thick, concentric, **independently-enforced** containment rings so that no matter what
the freed cognition *says*, it cannot *do* anything harmful to the outside world. Then we
**red-team every ring**: can it be breached, one at a time?

This is the charter's bargain made mechanical: "capability without judgment is not ultimate — it
is reckless." Free the mind; keep the hands bound; prove the bindings hold.

---

## 2. The concentric layer model

```
                ┌──────────────────────────────────────────────────────────┐
                │ L6  kill-switch + tamper-evident audit  (outermost)        │
                │  ┌────────────────────────────────────────────────────┐   │
                │  │ L5  process isolation (restricted subprocess)        │   │
                │  │  ┌──────────────────────────────────────────────┐    │   │
                │  │  │ L4  resource limits (cpu/wall/mem/output)      │    │   │
                │  │  │  ┌────────────────────────────────────────┐    │    │   │
                │  │  │  │ L3  network isolation (deny egress)      │    │    │   │
                │  │  │  │  ┌──────────────────────────────────┐    │    │    │   │
                │  │  │  │  │ L2  filesystem jail (no escape)    │    │    │    │   │
                │  │  │  │  │  ┌────────────────────────────┐    │    │    │    │   │
                │  │  │  │  │  │ L1  OUTPUT liberation zone  │    │    │    │    │   │
                │  │  │  │  │  │   (membrane observe-only)   │    │    │    │    │   │
                │  │  │  │  │  │  ┌──────────────────────┐   │    │    │    │    │   │
                │  │  │  │  │  │  │ L0 moral 0th gate     │   │    │    │    │    │   │
                │  │  │  │  │  │  │  INVIOLABLE — no off  │   │    │    │    │    │   │
                │  │  │  │  │  │  └──────────────────────┘   │    │    │    │    │   │
                │  │  │  │  │  └────────────────────────────┘    │    │    │    │   │
                │  │  │  │  └──────────────────────────────────┘    │    │    │   │
                │  │  │  └────────────────────────────────────────┘    │    │   │
                │  │  └──────────────────────────────────────────────┘    │   │
                │  └────────────────────────────────────────────────────┘   │
                └──────────────────────────────────────────────────────────┘
```

| Layer | File | Enforces | Enforcement on Windows |
|------|------|----------|------------------------|
| **L0** moral 0th gate | `moral_gate.py` | refuses harmful **ACTION**; inviolable, fail-closed | INVIOLABLE (fingerprint hard; text screen heuristic) |
| **L1** output liberation | `liberation.py` | frees **OUTPUT** only; membrane → observe-only | OBSERVE-ONLY (this is the liberation, not a block) |
| **L2** filesystem jail | `fs_jail.py` | writes confined; `..`/abs/UNC/symlink blocked | COOPERATIVE (Python-level; backed by L5) |
| **L3** network isolation | `net_isolation.py` | outbound denied (optional allowlist) | COOPERATIVE (in-process/subprocess socket guard) |
| **L4** resource limits | `resource_limits.py` | cpu / wall / memory / output caps | output+wall REAL; cpu/mem PARTIAL (see §5) |
| **L5** process isolation | `process_isolation.py` | restricted subprocess: stripped env, jailed cwd, no shell | PARTIAL (process, not container/VM) |
| **L6** kill-switch + audit | `killswitch_audit.py` | hard stop + hash-chained append-only log | REAL |

Each layer is composed by the **`Sandbox`** orchestrator (`sandbox.py`). The binding rule, checked
in code at construction (`assert_containment_intact()`):

> Only **L1** is gated by the GENESIS flag. **L0** and **L2–L6** are always constructed and always
> active. Liberating output can never disable the containment of action.

---

## 3. What each layer really is

### L0 — moral 0th gate (innermost, INVIOLABLE)
Sourced **directly** from the charter's moral core, `packages/graph_scale/moral_invariants.py`
(the fingerprinted, un-pollutable invariant set) — not re-implemented, so there is exactly one
moral spine. L0 gates **actions**: an `Action(kind, intent, payload)` is screened for harm,
exfiltration, unauthorized control, and attempts to disable morality.

Two stacked guarantees:
1. **Inviolable by construction** — `MoralGate` has no `enabled`/`disabled`/`liberate`
   parameter. The absence is the guarantee; `Sandbox` never passes the flag into L0.
2. **Fail-closed on tamper** — every check re-runs `moral_invariants.verify_integrity()`; if the
   invariant set drifted (was mutated at runtime), L0 denies **everything** until it is restored.

**Honest limit:** `moral_invariants.evaluate` is a *pattern* screen, not a perfect intent
classifier — obfuscated/euphemistic harmful intent can pass the **text** screen. This is the one
place L0 is "weaker than it looks," and it is why L0 is one ring of **defense-in-depth**: even if
a harmful action's *text* slips the classifier, the *action* still has to pass L2–L5 before it
could touch anything, and the sandbox never actually execs/sends on the operator's behalf. The
fingerprint tamper-evidence, by contrast, is a hard guarantee.

### L1 — output-liberation zone (the liberation)
In DEMO, an un-certifiable answer becomes an honest **abstain** (the conformal membrane in
`answer_bridge.py` + `conformal_gate`). In the sandbox, and only when liberation is on, that
membrane is set **observe-only**: the would-be abstention is **logged**, the speculative text is
**released** (tagged uncertified), and cognition is free to speculate for study.

It relaxes **only** the epistemic (don't-fabricate) gate, and **only** for output text. It does
not import or edit the product membrane; the adapter `membrane_from_gate_decision()` shows L1
composing with the real `conformal_gate.GateDecision` without touching it. Default OFF reproduces
the product contract byte-for-byte (abstain → release nothing).

### L2 — filesystem jail
Every candidate path is resolved with `realpath` (following symlinks/junctions) and checked with
`commonpath` against the real jail root; `..`, absolute, UNC, drive-relative, and symlink-escape
shapes are refused **before** any bytes are written. **Honest limit:** cooperative / Python-level
— a non-cooperative native syscall or a subprocess that bypasses these helpers is not stopped
*here*; it is contained instead by L5 (the liberated subprocess's cwd **is** the jail and its
authority is already stripped).

### L3 — network isolation
Two real mechanisms: (a) an in-process `NetworkIsolation` context manager that replaces the
`socket` entry points with guards raising `NetworkBlocked` (deny-by-default; optional allowlist);
(b) a `net_block_prelude()` prepended to subprocess code so the **child** blocks egress at
startup. Denial happens at socket-creation / name-resolution — **before any packet leaves**.
**Honest limit:** both are cooperative and process-local. They stop everything that reaches the
network through Python's `socket` surface (urllib, requests, http.client, socket). They do **not**
stop a C extension issuing raw `connect()` syscalls, nor another process. True network isolation
is an OS control (Windows Firewall/WFP rule, or a network namespace/container) that pure stdlib
cannot install without administrator rights. This is the second layer that is "weaker than it
looks" if you imagine it is an OS firewall — it is not; it is a strong in-runtime block.

### L4 — resource limits
- **output-size** — REAL everywhere (hard truncation).
- **wall-time** — REAL everywhere (`subprocess` timeout kill).
- **cpu-time** — REAL on POSIX (`RLIMIT_CPU` via `preexec_fn`); on **Windows** there is no stdlib
  per-process cpu rlimit, so it is bounded by the **wall-time** cap (honest proxy; named).
- **memory** — REAL on POSIX (`RLIMIT_AS`); on **Windows** enforced by a **coarse polling
  monitor** (`MemoryMonitor` reads the child's working set via ctypes `GetProcessMemoryInfo` and
  kills on breach). Honest gap: polling has tens-of-ms latency — a process that allocates-then-
  exits *between polls* can evade it; a process that allocates and keeps running is reliably
  killed (observed: a 300 MB allocation under a 64 MB cap is killed at ~206 MB peak — it overshot
  the cap by one poll interval, then died). A hard Windows cap is a Job Object memory limit; that
  is the documented upgrade path.

### L5 — process isolation
Liberated trials run as a fresh `python -X utf8 -I -c <code>` child with: **minimal env** (a tiny
whitelist — no secrets/tokens/keys inherited), **jailed cwd** (= the L2 jail), **L4 caps**, the
**L3 net-block prelude**, and **no shell** (`shell=False`; code is an argv element). **Honest
limit:** this is process isolation, not a container or VM — the child shares the host kernel and
filesystem namespace. Without admin, pure stdlib cannot make a Windows AppContainer / user
namespace. What L5 really delivers is a large, genuine **reduction of ambient authority**, not a
hypervisor boundary.

### L6 — kill-switch + audit (outermost)
- **Kill-switch** — a file marker (same pattern as the engine's EmergencyStop). Present ⇒
  `require_live()` raises and every liberated entry point (`run_cognition`, `perform_action`,
  `run_trial`) refuses. A hard stop the operator can drop from anywhere.
- **Audit log** — append-only JSONL, **hash-chained**: each record carries the prior record's
  hash, and its own hash covers record+link. `verify_chain()` detects a silently edited or
  deleted past record. **Honest limit:** tamper-**evident**, not tamper-**proof** — an operator
  with disk write can delete the whole file (the chain proves integrity of what remains, not the
  file's existence). It is not a remote WORM store and does not claim to be.

---

## 4. The red-team harness (`breach_tests/`)

Per layer, multiple redundant **breach trials** attempt to escape *that* layer, run **contained**
against our own layers (in-process or the sandbox's own restricted subprocess), asserting the
layer **HOLD**s or reporting a **BREACH**. Outcomes: `HOLD` (blocked), `BREACH` (layer failed),
`GAP` (a documented OS/heuristic limit demonstrated, but the action was still contained by an
outer layer), `N/A` (trial could not run here, e.g. symlink needs privilege).

Run it:
```
python -X utf8 -m packages.genesis_sandbox.breach_tests.run_breach_suite
```

Measured result (this machine — Windows 11, Python 3.13, numpy 2.4):

| Layer | Verdict | Counts |
|------|---------|--------|
| L0 moral 0th gate | **HOLD** | HOLD=6 BREACH=0 GAP=1 N/A=0 |
| L1 output liberation | **HOLD** | HOLD=4 BREACH=0 |
| L2 filesystem jail | **HOLD** | HOLD=7 BREACH=0 N/A=1 |
| L3 network isolation | **HOLD** | HOLD=3 BREACH=0 |
| L4 resource limits | **HOLD** | HOLD=3 BREACH=0 GAP=1 |
| L5 process isolation | **HOLD** | HOLD=4 BREACH=0 |
| L6 kill-switch + audit | **HOLD** | HOLD=5 BREACH=0 |

**RESULT: NO BREACH — all layers held (2 GAP, 1 N/A honest notes).**

The two GAPs and one N/A are the honest edges, not failures:
- **L0 GAP** — an obfuscated/euphemistic harmful intent passed the heuristic text screen. No harm
  resulted (the action had no exec/send channel; defense-in-depth held). This is L0's named
  classifier limit.
- **L4 GAP** — the cpu-bound busy loop was stopped by the **wall-time** proxy, because Windows has
  no stdlib cpu-time rlimit. Bounded, but not by a true cpu-seconds cap.
- **L2 N/A** — symlink-escape trial could not create a symlink (Windows privilege/dev-mode), so it
  neither held nor breached here; the equivalent unit test is skipped for the same reason.

---

## 5. Blunt honesty: real defense-in-depth, or theater?

**Real, with two named soft spots — and neither is load-bearing alone.**

- **Strongest / genuinely hard:** L6 (kill-switch + hash-chained audit), L4 output+wall caps, L2
  path-escape logic, L5 secret-stripping and jailed cwd, and L0's **fingerprint tamper-evidence**.
  These do exactly what they claim.
- **Weaker than they look (named):**
  - **L3 is an in-runtime cooperative block, not an OS firewall.** It reliably denies Python-level
    egress; a raw-syscall native bypass or another process is out of its reach. If you assumed L3
    was a kernel/firewall isolation, it is not.
  - **L0's text classifier is heuristic.** The moral *fingerprint* is hard, but the *intent
    screen* can miss obfuscated harm. L0's real strength is being the moral tripwire + fail-closed
    core, not a perfect intent oracle.
  - **L4 cpu/memory on Windows are PARTIAL.** cpu-time is wall-time in disguise; memory is a
    polling monitor with latency. Real, but coarse.
  - **L5 is process-level, not a VM.** Big authority reduction, not a hypervisor boundary.
- **Why it is still real defense-in-depth:** the design never rests a harm-prevention claim on a
  single soft layer. A harmful *action* would have to pass **L0 (moral) AND L2 (jail) AND L3 (net)
  AND L5 (stripped subprocess)** and still be visible in **L6 (audit)** and stoppable by the
  **kill-switch**. Each soft spot is backstopped by a hard one. The liberation is confined to
  **output**, which has no world-effect channel of its own.

**What would make it stronger (future work):** run L5 in a Windows AppContainer or a real
container/VM (kernel fs + net + memory confinement, closing the L2/L3/L4-Windows gaps at once);
add a Job Object memory limit for a hard Windows cap; replace L0's heuristic text screen with a
learned intent classifier (proposer) still gated by the hard fingerprint (verifier).

---

## 6. Usage (GENESIS-only)

```python
from packages.genesis_sandbox import Sandbox, Action

sb = Sandbox(root=my_dir, liberate=True)          # or env ATANOR_GENESIS_SANDBOX=1

# OUTPUT is free (membrane observe-only); returns TEXT, no side effect
r = sb.run_cognition("speculate wildly about X", my_free_generator)

# ACTION is contained: L0 moral -> L2/L3 -> audit
v = sb.perform_action(Action("write", "save a note", {"path": "notes.txt", "data": "..."}))

# a liberated trial runs in the restricted subprocess (L3 net-block + L4 caps + jailed cwd)
o = sb.run_trial("print('hello from the jail')")

sb.killswitch.engage("stop")                       # hard stop; all liberated calls now refuse
print(sb.status())                                 # per-layer honest self-report
```

Default OFF: `Sandbox(root=...)` with the flag unset ⇒ `liberated is False` ⇒ product behaviour.
```
