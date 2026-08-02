# SPLATRA Turbovec

Proof-only particle/splat compression layer for ATANOR holograms and future
large SPLATRA-style scenes.

This package does not import or vendor SPLATRA. It defines a local data model,
deterministic quantization, chunked LOD manifests, device budgets, and bounded
emotion/audio visual controls. The current backend is
`local_quantized_zlib_proof`.

It does not implement a production city renderer, GPU shader decoder, Fish audio
integration, or real physics simulation.

Run:

```bash
python -m packages.splatra_turbovec.proof
```

Proof outputs are written under `data/splatra_turbovec/proofs/` and should not be
committed.
