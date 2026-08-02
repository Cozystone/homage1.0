# ATANOR Fish 2 Test Install Attempt

Status: `BLOCKED_MODEL_MISSING`.

Timestamp: 2026-06-23 KST.

This slice did not install Fish into global Python and did not download model
weights. The safe rule is unchanged: Fish must live in an isolated environment
and model weights must stay outside the repository.

## Preflight Results

- WSL/Ubuntu: present.
- WSL Python 3.12: present (`Python 3.12.3`).
- Windows global Python: `3.13.12`; not used as an install target.
- Torch: present (`2.11.0+cu128`).
- CUDA: available.
- GPU: `NVIDIA GeForce RTX 5080`.
- ffmpeg: available (`8.1.1`).
- Disk free: about `159.84 GiB`.
- Fish packages:
  - `fish_speech=false`
  - `fish_audio_sdk=false`
  - `fishaudio=false`
- Model path:
  - `ATANOR_FISH2_MODEL_DIR` not configured.
  - `FISH_SPEECH_MODEL_DIR` not configured.

## Verdict

The machine has a plausible isolated WSL/Python 3.12 target, but there is no
configured local Fish 2 model directory and no Fish package installed in the
isolated runtime. The correct result is `BLOCKED_MODEL_MISSING`.

No synthesis was attempted because that would either require guessing an install
path, installing into the wrong environment, or downloading model weights.

## Runtime Contract

- `voice_output.audio_available=false`
- `audio_url=null`
- `selected_engine=fish_2`
- `runtime_available=false`
- `text_fallback=true`
- `error_reason=fish_runtime_missing` or `model_missing`

The dashboard may keep the hologram visual speaking state as a UI affordance,
but it must not claim that Fish produced audio until a real browser-playable
audio file exists.

## Safety

- `fish_global_install=false`
- `model_weights_committed=false`
- `generated_audio_committed=false`
- `microphone_enabled=false`
- `raw_voice_saved=false`
- `external_llm=false`
- `external_sllm=false`
- `local_brain_write=false`
- `production_store_mutated=false`
