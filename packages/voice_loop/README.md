# ATANOR Voice Loop

`packages/voice_loop` is a proof-only full voice loop for ATANOR.

It models:

- Nemotron ASR as ATANOR's ears / auditory input adapter;
- transcript events and deterministic voice intent detection;
- turn-taking, interruption, and stop-speaking state;
- Autonomy Kernel handoff as a self-model and proposal-loop bridge;
- Surface Brain / CGSR handoff as the future "what and how to say" layer;
- Fish Speech 2 / Fish 1.5 selection as ATANOR's mouth / speech output path;
- deterministic mock ASR/TTS for tests and proof runs.

Safety boundaries:

- ASR/TTS alone do not create consciousness.
- The package does not claim AGI or self-modifying agency.
- Always-listening is disabled by default.
- Microphone recording requires a future explicit opt-in path.
- Voice cloning or imitation is disabled without explicit consent.
- Transcripts are not written to Local Brain.
- Voice events are not written to Cloud Brain.
- Voice input is not used as candidate-learning input.
- No external service inference is used by tests or proof runs.
- Generated audio is not persisted in proof mode.

Fish 2 is selected only when a benchmark profile is stable and fast enough.
Fish 1.5 is the fallback for weaker devices. If Fish runtimes are not installed,
the proof loop uses deterministic mock TTS. Model weights, caches, recordings,
and generated audio must not be committed.

Run tests:

```powershell
python -m pytest packages/voice_loop/tests -q
```

Run proof:

```powershell
python -m packages.voice_loop.proof
```

Proof outputs are written under `data/audits/voice_loop/` and must not be
committed.
