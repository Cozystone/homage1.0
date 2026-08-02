# ATANOR Policy-driven Autonomous Loop v1

Status: proof-only.

Policy-driven Autonomous Loop v1 connects the Neural Emotion Engine, Emotion-driven Autonomy Policy, Open-Web Explorer, Review Queue, SPLATRA Imagination Field, Permission Gate, and Host Executor into one bounded run-once loop.

It is not a daemon and it does not run indefinitely. Each API call performs a small proof cycle and returns all budgets, actions, and safety flags.

## Control Flow

1. Read the current Neural Emotion snapshot.
2. Evaluate Emotion-driven Autonomy Policy v1.
3. Convert policy suggestions into bounded budgets.
4. Optionally run fixture-only Open-Web Explorer collection.
5. Import drafts into Review Queue as human-review items.
6. Optionally generate procedural SPLATRA imagination frames.
7. Optionally account for host status checks only when caution is low and host execution is explicitly allowed.
8. Emit bounded runtime events back into the Neural Emotion Engine.
9. Stop on max cycles, runtime budget, fatigue/rest, review pressure, or emergency stop.

## Policy Effects

- High curiosity increases the web explorer page budget within a hard cap.
- High caution increases review strictness and reduces host action availability.
- High fatigue reduces loop budget and can request rest.
- Repeated failures throttle retries and reduce exploration.
- High arousal shortens cycle behavior through the policy throttle.
- Tier 4 or tier-change context raises caution but never changes tier automatically.
- Voice unavailable increases text fallback emphasis only.
- Review queue pressure requests review instead of more collection.

## Budgets

The loop starts from conservative base budgets:

- `base_web_pages`
- `base_review_batch`
- `base_splatra_frames`
- `base_host_actions`

Policy output transforms these into:

- `web_pages_budget`
- `review_batch_budget`
- `splatra_frame_budget`
- `host_action_budget`

All values are clamped. Host budget is zero unless explicitly enabled and the policy remains low-risk.

## Safety Invariants

- `external_llm=false`
- `external_sllm=false`
- `real_emotion_claim=false`
- `consciousness_claim=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `permission_gate_bypass=false`
- `autonomy_tier_auto_changed=false`
- `auto_commit=false`
- `auto_push=false`
- `proof_only=true`

The loop never promotes candidates, mutates Local Brain, mutates production Cloud Brain, changes autonomy tier, bypasses Permission Gate, runs unrestricted shell, commits, or pushes.

## API

- `GET /api/agentic-os/policy-loop/status`
- `POST /api/agentic-os/policy-loop/run-once`
- `GET /api/agentic-os/policy-loop/runs/{loop_id}`

## UI

The Agentic Micro-OS Lab panel shows policy loop budgets, throttle/rest recommendations, a one-cycle proof button, last result metrics, and safety invariants. Product mode stays hidden from raw policy-loop internals.

## Future Work

- A scheduler can call `run-once` under explicit operator limits.
- A future daemon must preserve the same Permission Gate, emergency stop, and no-mutation invariants.
- Promotion to production knowledge remains a separate signed review-gate workflow.
