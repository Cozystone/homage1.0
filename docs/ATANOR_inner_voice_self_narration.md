# ATANOR Inner Voice Self-Narration

Status: proof-only implementation.

Inner Voice is an explicit self-narration channel generated from observable
ATANOR state:

- current emotion vector label and controls
- autonomy policy decision
- permission tier
- candidate actions
- blocked actions
- uncertainty
- next intent

It is not raw hidden chain-of-thought from an external LLM. It is not a proof of
real consciousness, sentience, AGI, or IIT. It is a bounded telemetry layer for
studying whether the self-model loop is coherent enough to inspect.

Visibility:

- Lab/dev can inspect recent frames and briefs.
- Product mode receives only a short redacted summary if explicitly requested.
- Private payloads, secrets, Local Brain content, and raw memories are redacted.

Safety invariants:

- `external_llm=false`
- `external_sllm=false`
- `consciousness_claim=false`
- `real_emotion_claim=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `raw_hidden_cot_claim=false`
- `inner_voice_is_explicit_generated_channel=true`

The intended use is behavioral evaluation: goals, tension, choices, blocked
actions, and next intent can be audited without pretending that hidden reasoning
is consciousness.
