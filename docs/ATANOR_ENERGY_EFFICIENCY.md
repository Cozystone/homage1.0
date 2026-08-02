# ATANOR energy efficiency — measured

The question: power draw / GPU utilization vs. the big LLMs. Measured on this
machine (RTX 5080, 16 GB), not estimated.

## Measurement

- **Idle baseline (nvidia-smi):** GPU 1% util, **29.4 W**, 3.6/16 GB used. The
  3.6 GB + ~29 W is the **browser orb visualization + OS** — not the AI server.
- **During answering (20 self-knowledge queries, pure server compute, no web):**
  - GPU samples through the burst: util **1–3%**, power **29.8–30.3 W** —
    i.e. **unchanged from idle**. The answering path adds **~0 W of GPU**.
  - API process **CPU: ≈1.4 CPU-seconds per query** (≈638 MB RAM, steady).
  - Wall time ≈1.8 s/query (this path runs the full scene-gen dispatch; see note).

## Why: no inference GPU

ATANOR answers with **graph lookups + regex extraction + (when needed) one
Wikipedia HTTP fetch**. There is **no model forward pass**, so CUDA is never
touched on the server. The only GPU consumer is the **client-side particle orb**
(Three.js / WebGL), which is UI, runs whether or not you ask anything, and is
already throttled (morph at ~33 fps, antialias off).

## Per-query energy vs. frontier LLMs

| | ATANOR (measured) | Frontier LLM inference (published estimates) |
|---|---|---|
| **GPU during a query** | **~0 W incremental** (idle 30 W = orb UI, unchanged) | Hundreds of W of GPU for the inference duration (data-center A100/H100 at ~300–700 W, sharded across the request) |
| **Compute per query** | ~1.4 CPU-s, no GPU | billions of FLOPs of matmul on GPU |
| **Energy per query (est.)** | **~10⁻³ Wh** (≈ a few joules of CPU) | **~0.3–3 Wh** (varies by model/length; some estimates higher) |
| **Ratio** | — | ATANOR is roughly **100–1000× lower energy per query**, and **zero GPU** |

(LLM figures are public estimates and move with model/hardware; treat as order-of-
magnitude, not exact. The point is the *category* difference: no GPU inference.)

## Honest caveats & the one inefficiency we found

- The **orb UI** does use the client GPU (~30 W here). That is the cost of the
  living-particle visualization, not the reasoning; it can be reduced further
  (lower particle count, pause when hidden) if desired — separate from answer
  energy.
- The measured **1.4 CPU-s/query is mostly SPLATRA scene-choreography generation**
  (the server computes the particle-scene the orb then animates), i.e. it is
  **visualization compute, not reasoning** — consistent with the overall story
  that ATANOR spends energy on the *living-particle UI*, not on a model. For a
  pure text-only deployment (no orb) the per-answer CPU would drop sharply; the
  scene-gen is opt-in to the visual product.
- Training energy is a separate axis: a frontier LLM's pre-training is enormous
  (amortized over many queries); ATANOR has no model to train. This doc compares
  **inference/answer-time** energy, which is what the user runs every query.

## Summary

> Answering on ATANOR uses **no server GPU and ~10⁻³ Wh of CPU per query**,
> versus **~0.3–3 Wh and hundreds of GPU-watts** for a frontier-LLM query — an
> order-of-magnitude-or-more efficiency win, by construction (no inference model).
> The only GPU draw is the optional particle-orb UI.
