# ATANOR Emotion Runtime Events

Status: deterministic local control events.

The emotion runtime event bus is the shared bridge between ATANOR runtime surfaces and Neural Emotion Engine v0.

## API

- `GET /api/neural-emotion/events`
- `POST /api/neural-emotion/events/emit`
- `GET /api/neural-emotion/controls/current`
- `POST /api/neural-emotion/reset`

Compatibility endpoints from v0 remain:

- `GET /api/neural-emotion/status`
- `GET /api/neural-emotion/snapshot`
- `POST /api/neural-emotion/event`
- `POST /api/neural-emotion/decay`
- `POST /api/neural-emotion/controls`

`/reset` is lab/dev only. Product workspace reset requests are rejected.

## Bridge Behavior

The event bus maps runtime events to the internal engine:

- novelty increases curiosity
- unsafe or Tier 4 events increase caution and arousal
- repeated failures increase fatigue and caution
- approved review items increase valence and lower caution
- denied/rejected events increase caution
- speaking events drive `speaking_energy`
- resting decays arousal/fatigue pressure

The resulting controls are exposed as:

- ASM-v0 `surface_bias`
- SPLATRA `splatra_controls`
- Fish/voice `voice_controls`
- Agentic Micro-OS `agentic_controls`

## Future Audio Envelope Mapping

When Fish2 local audio becomes available, voice runtime can update the same vector with audio envelope features:

- speech start/end
- amplitude envelope
- estimated energy
- synthesis failure
- selected voice profile availability

This future integration must keep raw microphone/voice capture disabled unless separately approved, and it must not use audio data for Local Brain writes.
