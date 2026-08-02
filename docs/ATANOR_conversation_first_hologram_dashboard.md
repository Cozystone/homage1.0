# ATANOR Conversation-first Hologram Dashboard

Status: UI proof slice, not production autonomy.

## Purpose

The default ATANOR screen now starts from a black hologram viewer instead of internal lab telemetry or explanatory cards. The first screen presents a Siri-like particle orb, the ATANOR logo, and a minimal text/voice command bar.

Developer-only systems such as Life Signs, Scheduler, Spark, raw proof panels, graph internals, and candidate diagnostics remain available through Lab/Developer routes. They are not the normal user dashboard.

## Hologram Approach

The orb uses a lightweight local splat-field renderer inspired by Cozystone/SPLATRA's Gaussian particle viewer architecture. SPLATRA describes a browser-side 3D Gaussian point-cloud viewer and a procedural fallback path for generated objects; this slice does not copy SPLATRA code or import its runtime because the integration boundary and license packaging must be reviewed separately.

Current implementation:

- renders a Three.js point-cloud hologram in the browser;
- morphs continuously through SPLATRA-style splat silhouettes;
- keeps the visible screen nearly text-free;
- keeps all animation client-side;
- uses no microphone stream by default;
- stores no raw audio;
- makes no memory writes.

Future SPLATRA gate:

- verify license and package boundary;
- add a cartridge adapter if SPLATRA buffers are generated locally;
- keep heavy 3D buffers out of LLM prompts;
- require explicit opt-in for any real generation or microphone input.

## Interaction States

The hologram supports these visible states:

- `idle`: slow breathing pulse.
- `listening`: waveform ring for voice demo.
- `thinking`: inner splats rotate.
- `speaking`: speech pulse.
- `resting`: dim slow motion.
- `approval_needed`: amber ring.
- `blocked`: red warning ring.

The voice control is proof-only. It toggles a local UI state and does not open a microphone stream. Text input remains the primary path.

## User-facing Vocabulary

- The private memory system is presented as "개인 기억".
- The shared knowledge system is presented as "공용 지식".
- Review candidates are presented as "검토 대기".
- Confirmed knowledge is presented as "검증됨".
- Active working context is presented as "현재 대화 맥락".

## Safety Guarantees

This UI slice does not:

- write to private memory;
- mutate `verified_store_v0`;
- promote candidates;
- enable peer networking;
- upload audio or private data;
- execute generated code;
- claim AGI completion or consciousness.

The screen frames ATANOR as a safety-gated conversation partner: text-first, voice-optional, memory-approval-first, and proof-only for selfhood signals.
