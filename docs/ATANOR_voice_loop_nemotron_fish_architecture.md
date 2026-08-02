# ATANOR Voice Loop: Nemotron ASR + Fish TTS Architecture

Status: proof-only.

The first voice loop gives ATANOR an ears-and-mouth interface without changing
memory, learning, stores, or production behavior. Nemotron ASR receives local
audio input, deterministic intent logic turns transcripts into reviewable voice
events, and Fish Speech 2 or Fish 1.5 is selected for speech output by local
benchmark policy. ASR and TTS do not create consciousness; they are interface
adapters around the existing proof-kernel architecture.

## Architecture

```text
AudioSource (file/mock, microphone disabled by default)
  -> NemotronASRAdapter or MockASRAdapter
  -> TranscriptSegment
  -> VoiceIntent detector
  -> TurnManager
  -> VoiceResponsePlan
  -> Autonomy / Surface bridge placeholder
  -> TTS selector
  -> FishTTSAdapter or MockTTSAdapter
  -> VoiceOutputEvent
```

## ASR Path

Nemotron ASR is the future local auditory adapter. The proof adapter lazily
imports NeMo, never opens a microphone, never downloads weights, never calls an
external service, and never persists transcripts by default. If the runtime is
unavailable, deterministic mock ASR keeps the proof runnable.

## TTS Path

Fish Speech 2 is preferred on high-end GPU profiles when benchmark results pass
TTFA, RTF, memory, and stability gates. Fish 1.5 is the fallback for weaker
devices. If neither runtime is installed, deterministic mock TTS returns a
reviewable `VoiceOutputEvent` without generated audio persistence.

## Benchmark Selector

The selector uses bounded local metadata:

- OS and CPU count;
- total and available RAM when safely available;
- CUDA, GPU name, and VRAM when safely available;
- disk free;
- optional runtime TTFA and RTF.

Policy:

- choose Fish 2 if stable, TTFA <= 700 ms, RTF <= 1.0, and memory is within
  budget;
- otherwise choose Fish 1.5 if stable and RTF <= 1.0;
- otherwise choose fallback/mock.

## Natural Conversation Loop

The proof scenarios cover:

1. Korean status request: "아타노르, 지금 상태 알려줘".
2. Morning brief request: "밤새 뭘 배웠어?"
3. Stop-speaking / barge-in: "그만 말해".
4. Memory command blocked: "이거 기억해줘".
5. Consent safety: microphone remains blocked by default.

## Privacy And Safety Rules

- no always-listening by default;
- no microphone recording without explicit future consent;
- no raw audio export;
- no generated audio persistence in proof mode;
- no voice cloning or imitation without explicit consent;
- no transcript write to Local Brain;
- no voice event write to Cloud Brain;
- no candidate ingestion;
- no production store mutation;
- no external LLM or external ASR/TTS service call.

## Relation To Autonomy Kernel

The voice loop can route status and morning-brief requests toward the Autonomy
Kernel as reviewable events. It does not execute generated code, approve
proposals, or mutate memory.

## Relation To Morning Brief

Morning Brief speech is a presentation layer for already reviewable summaries.
The proof path can produce a mock/proof brief, but a production path must use
audited Autonomy Kernel events and user-visible review boundaries.

## Relation To Atlas Congress

Atlas Congress remains a UI-preview/social deliberation shell. Voice events may
later become another review channel, but this proof does not add peer voice
streaming, cloud upload, or production sync.

## Future UI Integration

Future UI work should start with push-to-talk and explicit listening consent.
Always-on listening, hotword detection, and streaming microphone capture remain
out of scope until privacy gates and local-device controls are mature.

## Future TTS Voice Profile Consent

Any custom voice profile must require explicit consent, source provenance,
license review, and revocation controls. The proof loop must not clone or
imitate a real person's voice.
