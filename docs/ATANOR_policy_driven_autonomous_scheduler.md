# ATANOR Policy-driven Autonomous Scheduler v1

Status: proof-only.

Policy-driven Autonomous Scheduler v1 is an opt-in controller on top of Policy-driven Autonomous Loop v1. It does not autostart, does not install an OS service, and does not run as an unbounded daemon.

## Operating Model

- Disabled by default.
- `start` requires explicit operator confirmation.
- `tick` runs at most one bounded Policy Loop cycle.
- `stop` is always allowed.
- A stop file halts the scheduler.
- Permission Gate emergency stop halts the scheduler.
- Max runtime and max cycle caps are mandatory.

## Delay Policy

The scheduler computes the next delay from the current Neural Emotion state and Autonomy Policy decision:

- Higher curiosity shortens delay.
- Higher fatigue lengthens delay or requests rest.
- Higher caution increases review-first behavior.
- Review pressure pauses exploration and asks for review.
- Emergency stop immediately halts.

## What A Tick May Do

One tick may call the existing proof-only Policy Loop. That loop may:

- run bounded fixture web exploration,
- import draft-only Review Queue items,
- generate procedural SPLATRA frames,
- account for host status checks only.

It does not perform production writes, Local Brain writes, candidate promotion, commits, pushes, unrestricted shell, arbitrary JavaScript, microphone capture, or raw voice handling.

## Safety Invariants

- `external_llm=false`
- `external_sllm=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `permission_gate_bypass=false`
- `autonomy_tier_auto_changed=false`
- `auto_commit=false`
- `auto_push=false`
- `scheduler_opt_in=true`
- `scheduler_stoppable=true`
- `proof_only=true`

## API

- `GET /api/agentic-os/policy-scheduler/status`
- `POST /api/agentic-os/policy-scheduler/start`
- `POST /api/agentic-os/policy-scheduler/stop`
- `POST /api/agentic-os/policy-scheduler/tick`
- `GET /api/agentic-os/policy-scheduler/runs/{scheduler_id}`

## Future Plan

A future long-running scheduler can repeatedly call `tick` from a supervised runtime, but only after explicit operator opt-in, with the same stop file, emergency stop, max runtime, max cycles, Permission Gate, and no-mutation invariants.
