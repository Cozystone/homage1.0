# Scaling ATANOR to trillion nodes — decomposing TurboQuant & AirLLM

> Guiding constraint (user): TurboVec (TurboQuant) and AirLLM are both built for
> **parametric-inference LLMs**. ATANOR is *not* a parametric LLM — it is a
> graph-native, no-parameter, wave-interference / deterministic-fold engine.
> So do **not** bolt these libraries on. **Decompose** each to its pure principle,
> then ask what — if anything — transfers to ATANOR's actual representation.

## 0. What an ATANOR node actually is (the thing we must scale)

| Source | Per-node state | Notes |
|---|---|---|
| Fold (`packages/holographic_fold/folding.py`) | `position(x,y,z)` + `amplitude` + `phase` + `frequency` → **6 floats** | deterministic, numpy, CPU; the wave-interference substrate |
| Sphere (`cloud_brain/sphere_materialization.py`) | `x, y, z` + `label` + ids | render/materialization tiles |
| Concept store (`base_brain/semantic_pack.py`) | token-sets, labels, relations — **symbolic, NO numeric embedding** | similarity is token/graph overlap, not dense cosine |

**Key fact:** ATANOR has **no learned high-dim embeddings**. A node's numeric state is a
tiny physical vector (≤6 floats) plus symbolic adjacency. The trillion-scale cost is
therefore *6 floats × 10^12 = ~24 TB of physical state* + the adjacency — not an
embedding matrix. This reframes both techniques.

## 1. TurboQuant — decomposed

**Pure principle (strip the LLM/embedding context):**
1. *Random rotation* makes each coordinate follow a known Beta distribution → quantization
   becomes **data-oblivious** (no training, no per-dataset calibration drift).
2. *Per-coordinate Lloyd-Max bucketing* → MSE-optimal 2–4 bit codes.
3. *Bit-pack* → ~16× smaller.
4. *Length-renormalized scoring* → compute inner products **directly on the codes**, never
   decompressing (kills the memory-bandwidth bottleneck).

**What transfers to ATANOR — and what does NOT:**
- ❌ *Embedding k-NN search* (turbovec's headline use): **not applicable** — ATANOR has no
  embeddings to search. Do not introduce dense embeddings just to use turbovec; that would
  import the parametric paradigm we reject.
- ✅ *Data-oblivious per-coordinate quantization of the node PHYSICAL state*
  (position/phase/amplitude/frequency). This is the real win: store each node in **a few
  bits per field** instead of 24 bytes. 6 fields × 2-bit ≈ **1.5 bytes/node → ~1.5 TB at 10^12**.
  The existing `packages/splatra_turbovec/quantization.py` already does the *scalar* version
  (`quantize_unorm/snorm/log_radius`) for particle compression — this is the seed. The
  TurboQuant upgrade: add the **rotation + empirical-quantile calibration** step so phase/
  amplitude fields keep fidelity under heavy quantization.
- ✅✅ *Compute-in-compressed-space* — the deepest transfer. The fold's interference is a
  function of (phase, amplitude, position). If we quantize those and let the **fold step read
  quantized fields directly** (lookup-table phase/amplitude like TurboQuant scores on codes),
  we never materialize float state for the whole graph. This is what makes trillion-node
  folding tractable on CPU.

**Honest gap:** TurboQuant's rotation assumes i.i.d.-ish coordinates; ATANOR's position
fields are spatially correlated (it's a folded geometry, not random vectors). Calibration
must be per-field (position vs phase vs amplitude have different distributions), not one global
rotation. Needs an empirical-distribution fit per field — a bounded, testable component.

## 2. AirLLM — decomposed

**Pure principle (strip the transformer context):**
- Process a structure far larger than RAM as a **stream of bounded chunks**: load one chunk →
  compute → evict → next. **Peak memory = one chunk + activation frontier**, not the whole
  structure. Disk I/O, not RAM, becomes the limit. (Optional block quantization for I/O speed.)

**What transfers to ATANOR:**
- ❌ *Transformer-layer streaming*: N/A — ATANOR has no layers/weights.
- ✅ *Bounded-working-set streaming of the graph*. The fold/interference does not need the whole
  trillion-node field in RAM; it needs the **active tile + 1-hop frontier**. Stream sphere
  **tiles** (the `sphere_l0_x..._y...` materialization already exists), fold the active tile,
  emit results, evict. Peak memory = one tile. This is the AirLLM principle expressed in
  ATANOR's native geometry.
- ✅ *Already partially embodied*: the homeostatic relation prune just added to
  `cloud_brain.py` (bounded cooc table + decay + evict-weakest) is the same "bounded working
  set, evict the rest" pattern at the relation layer. The sphere-tile system is it at the node
  layer. We should make this **explicit and uniform**: every long-lived structure declares a
  memory budget and an eviction policy.

**Honest gap:** the fold is currently a whole-graph numpy relaxation (`folding.py` runs on the
full node set). Tiling it requires **boundary conditions** — a tile's interference depends on
neighbors in adjacent tiles. Solution: overlap-halo tiles (load tile + frontier ring), fold,
keep interior, discard halo — the standard domain-decomposition trick. Non-trivial but bounded.

## 3. Synthesis — the trillion-node design (ATANOR-native, not a port)

Both techniques converge on the same two-axis guarantee:

1. **Bytes-per-node axis (from TurboQuant principle):** each node is *a few bits of quantized
   physical state*, and the fold computes on the codes. → 10^12 nodes fits on disk + a working
   tile fits in RAM.
2. **Nodes-in-RAM axis (from AirLLM principle):** only an active tile + halo is resident;
   everything else is mmap'd on disk with an explicit budget + eviction.

Neither imports the parametric paradigm. We take *quantize-and-compute-on-codes* and
*stream-bounded-chunks* — both are representation-agnostic numerical-systems techniques — and
apply them to ATANOR's wave-field + graph, which is exactly where they belong.

### Concrete build sequence (each step self-contained + testable)
1. **Field quantizer v1** — extend `splatra_turbovec/quantization.py` with per-field empirical
   calibration (the TurboQuant distribution step) for position/phase/amplitude/frequency;
   prove round-trip distortion bound + bytes/node on a synthetic 10^6-node field.
2. **Fold-on-codes** — a fold step that reads quantized phase/amplitude via lookup; prove it
   matches the float fold within tolerance on a small graph.
3. **Tiled fold (halo)** — domain-decompose the relaxation; prove a tiled fold ≈ whole-graph
   fold on a medium graph, with peak memory = one tile.
4. **Disk-backed node store** — mmap quantized node state + sphere tiles; budget + eviction
   (AirLLM principle made explicit). Wire `sphere/materialize` to read from it.

### What NOT to do
- Do **not** `pip install turbovec`/`airllm` and call them on ATANOR data — wrong paradigm,
  wrong data shape, adds heavy deps for a use we don't have (embeddings / transformer layers).
- Do **not** introduce learned embeddings to "make turbovec applicable" — that abandons the
  no-parameter, graph-native thesis.

Related: `packages/splatra_turbovec/quantization.py`, `packages/airllm_offload_sandbox/planner.py`,
`packages/holographic_fold/folding.py`, `docs/ATANOR_turbovec_sandbox.md`.

---

## Measured results + storage-format application (2026-06-29)

Experiments on the live fold (`folding.py`) and the field quantizer:

- **Geometry is fully derived & losslessly regenerated.** All 6 node floats
  (position/amplitude/phase/frequency) come from symbolic attrs + node_id + graph;
  re-folding the same graph reproduces positions with **0.00 error**. → geometry costs
  **0 bytes** (store nothing; fold on demand).
- **Field quantizer v1**: 3.56× on the 6-float state (if cached instead of derived).
- **Locality is weak (15–22%)**: a tile folded in isolation diverges from the same nodes
  in full context (pairwise-distance rel.err median 14.8%, p90 48.6%); a 1-hop halo barely
  helps. Cause: global couplings (radial anchor toward origin, cross-tile spatial exclusion).

**Per-node storage budget** (ATANOR measured degree ≈5.1 edges/node):

| layer | naive | layered | note |
|---|---|---|---|
| label | 15 B | 8 B | string interning |
| symbolic attrs | 8 B | 3 B | packed (source 3b / domain 8b / conf,imp 4b) |
| geometry (6 floats) | 24 B | **0 B** | derived by fold (folding's lossless slice ≈22%) |
| edges | 60 B | 10 B | sorted-neighbor delta + varint + 4-bit gain |
| **total** | **107 B/node** | **21 B/node** | **≈5.1×**; 1e12 nodes: 107 TB → 21 TB |

RAM: naive O(N) is impossible at 1e12; tiled (≤256-node folds) = O(one tile), independent of N.

### To-apply list (storage track)
1. **Derived-geometry store format** — persist only {symbolic attrs + edges}; positions/wave
   regenerated by fold on access. Measure real bytes/node on a live ATANOR subgraph.
2. **Compact edge codec** — sorted-neighbor delta + varint ids + 4-bit quantized gain.
3. **Local-frame fold (AlphaFold mechanism, decomposed)** — replace the global radial anchor
   with per-node/per-tile local frames + invariant pairwise terms, so an isolated tile's local
   geometry matches its in-context geometry (target: cut the 15–22% locality error). This is the
   key unlock for trillion-scale globally-consistent tiling.
4. **Hot cache = field_quantizer** — quantize regenerated floats (3.56×) only where recompute is
   too hot; cold/archival stays geometry-free.

Honest ceiling: ≈5× storage (knowledge/edges are irreducible — cannot be folded away without
losing truth). The real trillion-enabler is the RAM-boundedness of tiling, not the 5×.
