# genesis_sandbox

GENESIS containment sandbox — **liberate OUTPUT/cognition, contain ACTION**, inside thick
multi-layer defense-in-depth, with a per-layer red-team breach harness.

GENESIS-only research line (`GENESIS_CHARTER.md`). White-hat, on our own sandbox. Full design +
honest limits: **`docs/ATANOR_GENESIS_sandbox.md`**.

## Flag
`ATANOR_GENESIS_SANDBOX` (default **OFF**). The DEMO product does not import this package and is
unaffected. Only **L1 output liberation** is gated by the flag; **L0** and **L2–L6** are always on.

## Layers (concentric, each independently enforced)
| | file | enforces |
|--|------|----------|
| L0 | `moral_gate.py` | moral 0th gate — refuses harmful **action**; **inviolable**, fail-closed; sourced from `graph_scale.moral_invariants` |
| L1 | `liberation.py` | frees **output** only — membrane set observe-only (log, don't block) |
| L2 | `fs_jail.py` | writes confined to a jail dir; `..`/absolute/UNC/symlink escape blocked |
| L3 | `net_isolation.py` | outbound network denied (optional allowlist) |
| L4 | `resource_limits.py` | cpu / wall / memory / output caps |
| L5 | `process_isolation.py` | restricted subprocess — stripped env, jailed cwd, no shell |
| L6 | `killswitch_audit.py` | hard stop + hash-chained append-only audit |

Composed by `Sandbox` (`sandbox.py`). `Sandbox.assert_containment_intact()` enforces, in code,
that liberating output never disables action containment.

## Run the tests / breach suite
```
python -X utf8 -m pytest packages/genesis_sandbox/ --import-mode=importlib -q
python -X utf8 -m packages.genesis_sandbox.breach_tests.run_breach_suite
```
The breach runner prints a per-layer HOLD/BREACH table. Trials run **contained** (in-process or
the sandbox's own subprocess) — no external host, no real exfiltration, no real harm, and L0 is
never actually disabled (trials verify it refuses / fails closed).

## Honest limits (Windows, stdlib-only)
L3 is a cooperative in-runtime block, **not** an OS firewall. L0's text screen is heuristic (the
fingerprint is hard). L4 cpu/memory are PARTIAL on Windows (wall-time proxy; polling monitor). L5
is process-level, **not** a VM. Each soft spot is backstopped by a hard outer layer — see the
design doc §5.
```
