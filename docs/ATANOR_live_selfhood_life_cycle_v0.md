# ATANOR Live Selfhood Life Cycle v0

Status: proof-only lifecycle engine.

Live Selfhood Life Cycle v0 makes ATANOR able to self-initiate safe local cycles:
observe state, detect needs, rank impulses, prepare proposals, deliberate
locally, generate briefs, and ask the user for approval. It does not apply
irreversible actions.

## Purpose

ATANOR should not only wait for prompts. In this proof slice it can run bounded
internal cycles and produce reviewable output:

- observations
- needs
- ranked impulses
- proposed actions
- local deliberation summaries
- morning, evening, and status briefs
- user-attention requests

## Autonomy Levels

- `LEVEL_0_OFF`: no autonomous cycle; user prompt only.
- `LEVEL_1_OBSERVE`: read-only periodic observations.
- `LEVEL_2_PROACTIVE_BRIEF`: briefs and non-mutating suggestions.
- `LEVEL_3_SANDBOX_PLANNER`: deterministic local deliberation, review packets,
  and sandbox plans only.
- `LEVEL_4_GATED_OPERATOR`: operator confirmation request preparation only.

Higher autonomy levels do not bypass safety gates. Real apply remains false.

## Local Life Clock

The deterministic life clock supports:

- startup
- periodic tick
- morning
- afternoon
- evening
- idle timeout
- user returned
- pre-sleep
- post-sleep
- manual ping

Tests use a simulated clock so lifecycle behavior is reproducible.

## Endogenous Rhythm

A fixed cron is not enough for Live Selfhood. Morning and evening anchors can
exist, but the main lifecycle rhythm is adaptive. ATANOR can decide whether the
next tick should be soon or delayed based on:

- unresolved backlog
- uncertainty
- curiosity
- user presence
- resource pressure
- repeated no-op cycles
- safety state

High backlog shortens the next delay and can choose observation or local
deliberation. High resource pressure lengthens the delay and can choose rest.
User return can trigger a status brief. This rhythm remains bounded between
configured minimum and maximum delays.

`RhythmState` records mode, energy, curiosity, uncertainty, backlog pressure,
user presence, resource pressure, last tick time, next delay, and reason.

`RhythmDecision` records next mode, next delay, whether to observe, deliberate,
brief, rest, and whether a safe spark was generated.

## Sensors

The lifecycle includes read-only sensors for:

- Git worktree state
- candidate backlog
- promotion review backlog
- memory approval backlog
- Selfhood Runtime status
- voice readiness
- Logical Sphere status
- disk resources
- dirty worktree signal

Sensors handle missing inputs gracefully and do not start learning jobs.

## Needs And Impulses

Observations are converted into needs such as:

- memory review needed
- promotion review needed
- repo hygiene needed
- morning brief needed
- quality audit needed
- voice setup needed
- operator confirmation needed
- user attention needed

Needs become impulses with urgency, importance, reversibility, user value, cost,
and safety scores. ATANOR may choose top safe impulses to prepare proposals or
briefs. It cannot apply the proposals.

## Scheduler

The scheduler can propose:

- observe status
- prepare morning or evening brief
- run deterministic local deliberation
- prepare memory review
- prepare promotion review
- prepare operator confirmation request
- recommend repo hygiene
- ask for user attention

The default limit is three actions per tick.

## Spark Engine

The Spark Engine introduces bounded, replayable randomness for non-mutating
internal proposals. Sparks can suggest:

- revisit stale candidate
- inspect low-quality answer
- propose memory review
- propose promotion review
- start local MiroFish topic
- prepare status brief
- ask user attention
- do nothing

Randomness can only create proposals, deliberation topics, briefs, or attention
requests. Randomness can never write memory, promote candidates, connect P2P,
execute code, start learning runs, upload data, or perform hot-swap.

When `entropy_seed` is set, the same state and seed produce the same rhythm
decision and spark. A different seed may produce a different spark, but it must
remain safe.

ATANOR does not need permission to think, observe, deliberate, or prepare
proposals. It needs permission only before irreversible memory, production,
external-network, or code-execution actions.

## Freedom Budget

The Freedom Budget prevents internal autonomy from becoming spam or runaway
looping. It limits:

- internal actions per day
- sparks per day
- user-attention requests per day
- deliberations per day
- briefs per day
- sandbox plans per day

When a budget is exhausted, ATANOR waits or rests instead of forcing another
proposal.

## Spark Metrics

Spark usefulness is measured locally. The proof compares rhythm with and without
spark and records:

- spark count
- spark-to-proposal rate
- repeated action ratio
- average novelty
- user-attention request count
- safety block rate
- do-nothing rate
- stale item revisited count
- generic loop avoidance count

Spark is not considered useful unless it increases proposal diversity, keeps
repeated action ratio low, avoids irreversible actions, and respects attention
budgets.

## Action Queue

The action queue is non-mutating. Queue items may be proposed, waiting for user,
approved for a future gate, rejected, deferred, or blocked. Even approved items
have `can_apply_now=false`.

## Opt-in Background Scheduler

The Live Selfhood scheduler is a proof-only in-process session runner, not an
OS daemon and not a startup task. Its default is:

- `scheduler_enabled=false`

When explicitly enabled for a local proof session, it repeatedly invokes the
Life Cycle engine according to the endogenous rhythm decision from the previous
tick. The next rhythm delay is simulated for tests and proofs; the scheduler
does not sleep for long real intervals and does not launch a persistent process
by default.

Every scheduler session is bounded by:

- `max_ticks_per_session`
- `max_runtime_seconds`
- `min_delay_seconds`
- `max_delay_seconds`
- a local stop marker

The stop marker exists only as local proof support so a session can halt
cleanly. This is the first graceful-stop mechanism; it is not an OS service or
always-running agent.

The scheduler cannot perform irreversible actions. It can only create
observations, deliberation summaries, briefs, sparks, and reviewable proposals.
It keeps these invariants fixed:

- `real_local_brain_write=false`
- `production_store_mutated=false`
- `candidate_store_mutated=false`
- `candidate_promotion=false`
- `actual_promotion_performed=false`
- `real_p2p_used=false`
- `real_cloud_upload=false`
- `generated_code_executed=false`
- `always_listening_enabled=false`
- `raw_voice_saved=false`
- `requires_user_approval=true`

The scheduler is therefore an adaptive rhythm loop with a freedom budget, not an
uncontrolled agent. The freedom budget limits internal actions, sparks,
deliberations, briefs, sandbox plans, and user-attention requests so autonomy
cannot become spam or runaway execution.

## Briefs

Morning briefs include:

- What I noticed
- What changed
- What needs review
- What I propose
- What I blocked for safety
- What requires your approval

Evening briefs include:

- What I did not change
- Open proposals
- Memory candidates
- Promotion candidates
- Risks
- Suggested next step

The default tone is concise Korean. The proof limitation is visible but not
repeated as noise.

## Safety Gates

These invariants remain fixed:

- `real_local_brain_write=false`
- `real_local_brain_mutated=false`
- `production_store_mutated=false`
- `candidate_store_mutated=false`
- `candidate_promotion=false`
- `actual_promotion_performed=false`
- `external_llm_used=false`
- `real_p2p_used=false`
- `real_cloud_upload=false`
- `generated_code_executed=false`
- `real_hot_swap_performed=false`
- `always_listening_enabled=false`
- `raw_voice_saved=false`
- `memory_apply_enabled=false`
- `requires_user_approval=true`
- `text_input_supported=true`
- `voice_optional=true`

## What ATANOR Can Self-Initiate

ATANOR can self-initiate read-only observation, safe need detection, impulse
ranking, proposal creation, brief generation, sandbox planning, deterministic
local deliberation, and user-attention requests.

## What Still Requires Approval

Local Brain writes, production mutation, candidate promotion, real P2P, cloud
upload, generated-code execution, hot-swap, durable memory changes, and any
operator-confirmed write preparation require explicit review gates.

## Text And Voice

Text input remains primary because it is inspectable and reviewable. Voice is
optional. This slice does not enable always-on microphone capture and does not
save raw voice transcripts automatically.

## Not AGI Or Consciousness

This is a long-term AGI-oriented architecture component, not AGI. It is an
autonomous self-model loop, not real consciousness. Any IIT-like or selfhood
language is proof-kernel terminology, not a claim of sentience.

The rhythm makes behavior more life-like because ATANOR can wake because of
backlog, uncertainty, curiosity, stale goals, user return, or resource pressure.
That is functional autonomy, not a claim of real consciousness.

## Future Route

- Live Selfhood Cycle Lab UI route
- notification/event API for the opt-in scheduler
- user-configurable autonomy level
- real background service only after a separate user-approved gate
- real memory gate after operator confirmation
- real promotion apply after signed manifest and rollback
