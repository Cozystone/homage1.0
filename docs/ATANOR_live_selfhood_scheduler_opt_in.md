# ATANOR Live Selfhood Scheduler Opt-in

Status: proof-only, local-only, disabled by default.

The Live Selfhood scheduler gives the Life Cycle engine a bounded session loop.
It is not a daemon, not an OS service, not a startup task, and not an
always-running agent.

## Defaults

- `scheduler_enabled=false`
- `autonomy_level=LEVEL_3_SANDBOX_PLANNER`
- `require_user_approval=true`
- `allow_memory_write=false`
- `allow_candidate_promotion=false`
- `allow_real_p2p=false`
- `allow_generated_code_execution=false`
- `allow_voice_events=false`

## Bounds

Each explicitly enabled session is bounded by maximum tick count, maximum
simulated runtime, delay limits, and an optional local stop marker. Tests use
simulated delay from the rhythm decision; no long real sleep is required.

## Stop Marker

The local stop marker is proof-only graceful stop support. Creating the marker
causes the next scheduler check to stop with `stopped_reason=stop_marker`.
Clearing the marker is explicit and local.

## Relation To Endogenous Rhythm

Each tick calls the existing Live Selfhood Life Cycle engine. The Life Cycle
engine derives a rhythm state, chooses a next rhythm decision, and reports the
next delay. The scheduler records that delay as simulated elapsed time and uses
it only to decide when a bounded proof session should stop.

## Relation To Freedom Budget

The Life Cycle engine still owns action and spark budgeting. The scheduler does
not raise budgets, bypass budgets, or apply queued actions. It only repeats the
proof tick while session bounds allow it.

## Safety Boundary

The scheduler cannot:

- write Local Brain
- mutate production stores
- mutate candidate stores
- promote candidates
- connect real P2P
- upload private data
- execute generated code
- enable always-on microphone capture
- save raw voice transcripts

It can only prepare proposal-only lifecycle outputs that still require explicit
review before any irreversible operation.
