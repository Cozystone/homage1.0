# Ultimate Vision — Camera-based Embodied Perception

> Status: **VISION / not scheduled.** Recorded for the Ultimate (public) release, not the DEMO.
> Captured 2026-07-01 at the user's request.

## Goal

Give ATANOR a **camera sense**: using a webcam / device camera, the AI should be able to
**perceive and locate people (including "me", the user), and objects** in the live scene —
detection, localization, and depth — and feed that grounded perception into the engine
(e.g., scene grounding, embodied reasoning, presence/attention cues). This is the "eyes"
counterpart to the existing language/graph engine.

## Candidate models / mechanisms to use or borrow from

Either integrate directly, or reuse the underlying mechanism:

- **NVIDIA Eagle — Embodied** — https://github.com/NVlabs/Eagle/tree/main/Embodied
  Embodied multimodal perception; embodied-agent visual understanding.
- **NVIDIA LocateAnything-3B** — https://huggingface.co/nvidia/LocateAnything-3B
  Open-vocabulary object localization ("locate anything" by text prompt).
- **Depth-Anything-3 (ByteDance-Seed)** — https://github.com/ByteDance-Seed/depth-anything-3
  Monocular depth / 3D structure from a single camera.
- **MiDaS (Intel ISL)** — https://github.com/isl-org/MiDaS
  Robust monocular depth estimation (lighter, well-established fallback to Depth-Anything).
- **MediaPipe (Google AI Edge)** — https://github.com/google-ai-edge/mediapipe
  On-device, real-time person/face/hand/pose + object detection; runs in-browser (WASM) and
  on-device — good for a privacy-preserving, local-first "detect me / people / objects" layer.

## Sketch of how it could fit ATANOR

- **MediaPipe** as the fast, on-device, local-first front line (person/pose/hand/face + object
  boxes) — aligns with local-first + privacy; runs in the browser without a server.
- **LocateAnything / Eagle-Embodied** for open-vocabulary "find the <thing>" grounded to the
  user's own words.
- **Depth-Anything-3 / MiDaS** to add distance/3D so the scene isn't just 2D boxes — feeds
  spatial reasoning (near/far, in-front-of).
- Perception → a **scene graph** (objects + relations + depth) that plugs into the existing
  graph-native reasoning and scene-grounding contract, rather than a separate black box.

## Constraints / open questions to resolve at Ultimate time

- **No-LLM / no-sLLM rule**: several of these are neural vision models. Vision perception is a
  different axis from the *answer/reasoning* stack — decide whether "no neural models" applies
  only to the language/answer engine or across the board. Likely: allow neural **perception**
  (eyes) as sensory input, keep the **reasoning/answer** stack graph-native. Document the line.
- **Privacy**: camera is sensitive — must be explicit opt-in, local-only processing by default,
  no upload. MediaPipe's on-device path supports this.
- **Licensing**: check each model's license before shipping (NVIDIA model licenses can be
  restrictive; MediaPipe Apache-2.0; MiDaS MIT).
