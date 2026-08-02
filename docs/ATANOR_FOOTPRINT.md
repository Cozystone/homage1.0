# ATANOR footprint — VRAM, disk, RAM (measured) vs. local LLMs

Measured on this machine, not estimated.

## What ATANOR's answer engine actually needs

| Resource | ATANOR (measured) | How we know |
|---|---|---|
| **Model weight files** | **0 bytes** | no `.safetensors/.gguf/.bin/.pt/.onnx` > 50 MB anywhere in the repo |
| **VRAM to answer** | **0** | GPU stays at idle (1–3%, ~30 W) through answering — no model forward pass (see ENERGY doc) |
| **ML framework (torch)** | **not used by the answer path** | only 2 files import torch — `voice_loop/benchmark.py` (TTS) and `neuro_efficiency/hardware_adapter.py`; the chat path (dual_brain → base/cloud/surface/cgsr) imports none |
| **Core answer-only Python deps** | **~11 MB** | fastapi + uvicorn + starlette + pydantic |
| **RAM (API process)** | **~100 MB** | uvicorn working set, measured |
| **Knowledge store on disk** | **~0.2 MB base graph; ~60 MB Cloud + ~62 MB Surface graphs** | the "knowledge" is graph data files, not weights (q_cortex's 214 MB is experimental, not required to answer) |

> torch IS installed in the shared dev conda env (**4.2 GB**), but it's there for
> the optional voice/hardware experiments — **the answer engine never loads it**.
> A minimal answer-only deploy is ~11 MB of web deps + the graph data.

## vs. running a local LLM

To run a local LLM you must download and load weights, the torch/CUDA stack, and
hold the model in VRAM (or RAM for CPU inference):

| Local model | Weights on disk | VRAM to run (typical) |
|---|---|---|
| Phi‑3‑mini (3.8B) | ~2.4 GB (4‑bit) / ~7.6 GB (fp16) | ~4–8 GB |
| Llama 3 8B / Mistral 7B | ~4–5 GB (4‑bit) / ~16 GB (fp16) | ~6–10 GB |
| Gemma 2 9B | ~5.5 GB (4‑bit) / ~18 GB (fp16) | ~8–12 GB |
| Llama 3 70B | ~40 GB (4‑bit) | ~48 GB (2× 24 GB GPU) |
| **ATANOR answer engine** | **0 GB weights** (~0.06–0.12 GB graph) | **0 GB** |

Plus, every local-LLM option needs the **~4–5 GB torch/CUDA runtime** that ATANOR's
answer path does not.

## The honest trade-off

- ATANOR fits in **megabytes and zero VRAM** because the "intelligence" is an
  explicit graph + live retrieval, not billions of weights. You can run the answer
  engine on a machine with **no GPU at all**.
- The cost: its knowledge is the **graph + whatever it can fetch from the public
  web**, so it needs internet for facts it hasn't cached, and it has no parametric
  world-model to fall back on (it abstains instead). A local LLM carries its
  knowledge in the weights and works fully offline, at 1000×+ the footprint.

## Summary

> **ATANOR's answer engine: 0 model weights, 0 VRAM, ~11 MB core deps, ~100 MB
> RAM, ~MB-scale graph data — runs on a GPU-less machine.** A comparable local
> LLM needs **2.4–40 GB of weights, 4–48 GB of VRAM, and a ~4–5 GB torch/CUDA
> stack.** Two different categories: parametric model vs. graph + retrieval.
