# Neural Emotion Event Wiring v1

Status: proof-only runtime wiring.

Neural Emotion Event Wiring v1 connects real ATANOR runtime events to the Neural Emotion Engine v0 state vector. It is deterministic and local. It does not claim real emotion, consciousness, sentience, AGI completion, or IIT proof. It does not call external LLM/sLLM APIs.

## Event Sources

Supported sources:

- `asm_v0`
- `splatra_imagination`
- `web_explorer`
- `review_queue`
- `host_executor`
- `voice_loop`
- `permission_gate`
- `user_action`

## Event Types

Supported runtime event types:

- `user_greeting`
- `user_praise`
- `user_correction`
- `unsafe_request`
- `memory_request`
- `conversation_success`
- `novelty_found`
- `repeated_failure`
- `review_queue_pressure`
- `review_item_approved`
- `review_item_rejected`
- `host_action_success`
- `host_action_denied`
- `voice_available`
- `voice_unavailable`
- `permission_tier_changed`
- `tier4_enabled`
- `tier4_disabled`
- `splatra_generation_success`
- `splatra_generation_failure`
- `resting`
- `speaking_start`
- `speaking_end`

## Safety Boundary

Runtime events only update a bounded internal state vector. They never:

- write Local Brain
- mutate `verified_store_v0`
- promote candidates
- bypass the Permission Gate
- change autonomy tier
- auto-commit or auto-push
- store private payloads

Private payload events are rejected with `private_payload_not_stored`. Event logs store only short summaries and content hashes, bounded to 200 entries.

## Runtime Wiring

Current wiring:

- ASM-v0 chat input emits `user_greeting`, `memory_request`, `unsafe_request`, `user_correction`, or `conversation_success` based on deterministic local text classification.
- ASM-v0 successful response emits `conversation_success`; abstain/no answer emits `repeated_failure`.
- Voice runtime status emits `voice_available` or `voice_unavailable`; product visual speech can emit `speaking_start` and `speaking_end`.
- SPLATRA procedural generation emits `splatra_generation_success` or `splatra_generation_failure`.
- Web explorer runs emit `novelty_found` when drafts are produced.
- Review Queue decisions emit `review_item_approved`, `review_item_rejected`, or `review_queue_pressure`.
- Host Executor harmless/denied actions emit `host_action_success` or `host_action_denied`.
- Permission Gate emits `permission_tier_changed`, `tier4_enabled`, `tier4_disabled`, or high-caution emergency-stop events.

## UI Boundary

Lab/Developer mode may show:

- numeric state vector
- last event source/type
- before/after delta
- bounded event log
- ASM/SPLATRA/voice/agentic control projections

Product mode must not show raw emotion numbers or event logs. It may use SPLATRA/Hologram controls subtly for animation.
