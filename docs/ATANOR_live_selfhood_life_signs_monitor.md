# ATANOR Live Selfhood Life Signs Monitor

Status: proof-only monitor.

This milestone adds a read-only Life Signs Monitor for the Live Selfhood Cycle. "Live" here means a functional runtime signal: the system has a recent heartbeat or tick, can report its rhythm mode, can explain why it woke or rested, and can show sparks, proposed actions, briefs, pending approvals, and safety blocks.

It is not a proof of real consciousness, AGI, or IIT. It is an observability layer for the autonomous self-model loop.

## What It Reports

- heartbeat age and tick count
- current rhythm mode
- latest wake reason
- latest observation, need, impulse, spark, proposed action, and brief
- user attention or approval requests
- safety blocks
- rest reason and next tick estimate
- stopped or stalled state when heartbeat evidence is missing or stale

## Safety

The monitor is read-only. It does not write Local Brain, mutate production stores, mutate candidate stores, promote candidates, use real P2P, upload private data, execute generated code, enable always-on microphone capture, or store raw voice.

Required invariants remain visible in every snapshot:

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
- `always_listening_enabled=false`
- `raw_voice_saved=false`
- `requires_user_approval=true`
- `text_input_supported=true`
- `voice_optional=true`
- `monitor_read_only=true`
- `can_stop=true`
- `bounded_runtime=true`

## Watch Sessions

Watch sessions are disabled by default. If enabled by an explicit caller, they are bounded by max ticks and max runtime and can respect a stop marker. They run the existing proof-only scheduler path in-process and do not create a daemon, OS service, startup task, or long-running background loop.

## Future Gates

- route the monitor panel into the live lab after the UI worktree is clean
- expose a live scheduler API with explicit opt-in
- add an opt-in notification system
- collect user feedback metrics for spark quality
- connect to a future approved Local Brain write gate without weakening the read-only monitor
