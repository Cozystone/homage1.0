# Neural Emotion Bridges

Status: proof-only integration notes for ASM-v0, SPLATRA, Fish voice planning, and Agentic Micro-OS.

## ASM-v0 Surface Bridge

The surface bridge maps the internal vector to discourse controls:

- `warmth`
- `safety_weight`
- `brevity`
- `exploratory_suggestion_weight`
- `calmness`
- `formality`

These controls are metadata for construction-conditioned conversation. They are not fixed answer templates and do not replace ASM-v0 retrieval or construction selection.

## SPLATRA Bridge

The SPLATRA bridge maps the vector to visual behavior:

- shell ripple amplitude
- particle velocity
- brightness
- roundness
- fragmentation
- archetype switch probability
- pulse amplitude

Product UI may use these controls subtly in the hologram field. Lab UI may show the raw values for diagnosis.

## Voice Bridge

The voice bridge emits a plan for Fish-compatible prosody:

- speed
- pitch shift
- energy
- sampling temperature and top-p hints
- optional inline TTS tag such as `[whispering]`, `[sigh]`, or `[laugh]`

If Fish audio is unavailable, the bridge remains valid as a planned-only voice control layer and does not block text conversation.

## Agentic Micro-OS Bridge

The agentic bridge can adjust proof-only priorities:

- exploration priority
- review strictness
- loop budget multiplier
- cycle timing hint
- pause or require approval

It explicitly cannot bypass the Permission Gate, change autonomy tier, write Local Brain, or mutate Cloud Brain production stores.
