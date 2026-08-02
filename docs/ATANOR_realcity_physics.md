# Realcity real physics — so ATANOR is not contaminated (2026-07-21)

Owner: "PhysX로 realcity에 현실과 거의 똑같은 물리법칙이 되게 구현해줘. 그래서 atanor가 오염되지 않게."

The reason this matters: R3 wired the city's world-state into ATANOR's **lived record**. As ATANOR
learns HOW the world works by watching the twin, the twin's physics must be **true** — a city where
a cup floats or a taxi drives through a wall would teach ATANOR false physical law. The physics engine
is ATANOR's **body** (doctrinally clean under No-LLM: body/world-sim, not brain content). Truth is
guaranteed by two stacked layers.

## Engine decision — NVIDIA PhysX vs Rapier (owner chose Rapier)

Measured, not assumed:
- **NVIDIA PhysX 5** (physx-js-webidl, real NVIDIA solver) **runs in Realcity's browser**, and its
  **gravity is physically true** (free-fall matched y=½gt² to 0.02 m, verified in-browser).
- BUT the web WASM build is **multithreaded**: the per-frame narrowphase+contact-solver only runs on
  worker threads, which need **COOP/COEP cross-origin isolation** (SharedArrayBuffer). Diagnosed live:
  `crossOriginIsolated=false` → 0-thread dispatcher queues collision tasks that never execute →
  gravity integrates but objects tunnel through the ground (filterShader fired exactly once). The old
  helloworld worked only because it was a single-threaded build.
- That isolation **conflicts with the browser→ATANOR(:8502) cross-origin call** that powers
  "connect at realcity.vercel.app and talk to ATANOR" — fixable with CORP headers, but real deploy
  fragility. Omniverse Kit itself is native-only (web = GPU pixel-streaming infra), not viable for a
  self-contained web app.
- **Rapier** (`@dimforge/rapier3d-compat`, Rust→WASM) gives the **same physical truth**, is
  **single-threaded** (no COOP/COEP), deploys cleanly on vercel, never fights the ATANOR connection.
  Owner chose Rapier: same goal (true physics → clean ATANOR), no deployment landmine.

## Layer 1 — BODY: Rapier is physically true (verified headless, `scripts/rapier_truth_check.mjs`)

Runs in Node (compat build inlines the wasm), so the LAW itself is checked with no browser:
- **gravity**: free-fall y=5.0899 vs analytic 5.0950 (err 0.005)
- **support/collision**: box dropped from 5 rests at y=0.249, never tunnels (works out of the box)
- **restitution**: elastic material rebounds; energy bounded
- **momentum**: frictionless slide travels exactly 1.500 m in 0.5 s at 3 m/s (perfect conservation)

## Layer 2 — GATE: ATANOR never trusts the engine blindly (`packages/situation_model/physics_truth.py`)

`verify(observation)` checks each city physics event against **domain-blind physical invariants**
(the same category as mechanism.py's laws, reusing their names):
- `support-holds` — a supported, undisturbed thing must not fall
- `gravity-pulls-down` — nothing rises/hovers with no force or support
- `blocked-path-is-impassable` — no motion **through** a blocked/solid path (the "taxi through the wall")
- `energy-not-created` — a passive rebound cannot exceed its drop (restitution ≤ 1)
- `no-deep-interpenetration` — a contact cannot sink far into a solid

An event that violates an invariant is **QUARANTINED** as a twin-bug and never enters the lived
record; a well-formed true event is **ACCEPTED**; an event lacking the conditions to judge is
**UNDECIDED** (abstain — the same honesty floor as mechanism.py, never guess). Headline safety
property (test): **the gate never accepts a violation.** 16 gate tests + 70/70 situation_model green.

This is the actual "오염 방지": even if Rapier had a bug, or a fake-physics city were swapped in,
ATANOR's physics knowledge stays clean because it learns only what its own invariants confirm.
Doctrine: [[external-minds-are-data]] — the world is DATA through a gate, not an authority.

## Milestones
| # | item | status |
|---|---|---|
| P1 | engine decision (PhysX diagnosed, Rapier chosen) | ✅ |
| P2 | Rapier physical-truth verified headless (gravity/support/restitution/momentum) | ✅ |
| P3 | contamination gate physics_truth.py + tests | ✅ |
| P4 | wire Rapier into the city scene (objects obey gravity/collision in the 3D world) | next |
| P5 | live loop: city physics events → gate → lived record (+ quarantine log) | next |
| P6 | ATANOR self-modifies city physics via self-repair loop (R4) when it detects a violation | later |

## Notes for P4 (city wiring)
- Use **core `@dimforge/rapier3d-compat` directly** (drive Three.js transforms from Rapier bodies).
  The R3F wrapper `@react-three/rapier` hit a peer-dep conflict with the installed R3F/React; the core
  engine avoids it and gives full control. Remove the stale `optimizeDeps.exclude:['@react-three/rapier']`
  when wiring.
- Start bounded: dynamic props (a cup on a table, a dropped box, a ball) with real gravity/collision/
  support — the exact events ATANOR's mechanism reasoner talks about — before touching pedestrian/
  vehicle movement (currently kinematic in `collision.js`).
- Verify numerically (read body positions over time), not by WebGL screenshot (blocked in this env).
