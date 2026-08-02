# ATANOR SPLATRA Turbovec Particle Compression

Status: proof-only compression layer.

ATANOR's hologram orb is a local particle/splat-style body. Future scenes may be
far larger: rooms, city blocks, or city-scale holographic environments. The
SPLATRA Turbovec layer defines how those particle chunks can be compressed,
chunked, and selected by client budget before any production renderer is built.

## What It Compresses

- particle position relative to a chunk origin;
- low-precision velocity/deformation vectors;
- color and alpha;
- logarithmic radius;
- material identifiers through a local dictionary;
- emotion and audio-reactive weights.

The current backend is `local_quantized_zlib_proof`. It uses deterministic
quantization plus standard-library `zlib`; it does not depend on a GPU renderer.

## Chunk And LOD Strategy

Particles are grouped into cubic chunks. Each chunk can be downsampled into a
LOD pyramid. A future client can request nearby high-detail chunks and far-field
low-detail or impostor chunks.

Client proof budgets:

| Tier | Max particles | Max chunk bytes |
| --- | ---: | ---: |
| low | 20,000 | 2 MiB |
| medium | 100,000 | 12 MiB |
| high | 500,000 | 64 MiB |
| ultra | 2,000,000 | 256 MiB |

## Large City Readiness

This slice does not implement a city renderer. It does define
`CitySceneManifest` fields for district/tile ids, world bounds, LOD tiles,
streaming priority, near-field chunks, far-field chunks, impostor chunks,
materials, and estimated GPU memory. A deterministic synthetic city proof
generates towers, windows, street lights, fog, and sparks in memory only.

## Emotion And Audio Mapping

`emotion_mapping.py` maps valence, arousal, and future Fish audio energy into
bounded visual controls:

- particle velocity multiplier;
- shell ripple amplitude;
- brightness;
- color warmth;
- audio deformation strength.

Fish audio is not required for this proof. The mapping is ready for a later
audio envelope hookup.

## What This Does Not Solve

- no production city renderer;
- no GPU shader decoder;
- no external SPLATRA runtime integration;
- no Fish audio envelope integration;
- no learned physics simulation;
- no large scene assets committed.

## Safety

The proof does not write Local Brain, mutate `verified_store_v0`, promote
candidates, start learning runs, call external LLM/sLLM APIs, or commit generated
scene assets. Runtime proof outputs under `data/splatra_turbovec/proofs/` are
generated artifacts and should stay out of commits.

## Next Gates

- WebGL/WebGPU client decoder for the compact payload;
- SPLATRA orb LOD integration in the dashboard;
- Fish audio envelope to visual controls;
- Neural Emotion Engine v0 signal source;
- real SPLATRA cartridge adapter after license and package boundary review.
