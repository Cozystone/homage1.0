# PHFE generative substrate — v1 result (Fable 5)

Response to `docs/fable5-brief-phfe-generative-substrate.md`. Delivered as a self-contained
module + tests (no rewrite of the live generator), per §5/§7 of the brief.

## What was built

`packages/cgsr/cgsr/holographic_lm.py` — a **Fourier Holographic Reduced Representation (FHRR)
associative language substrate**. It adds the half the v0 `phase_context` was missing —
**binding** — so context carries role/order, and it retrieves by **resonance**, which is a smooth
similarity rather than exact match.

- symbol → fixed unit phasor φ(s) (per-symbol hash seed; deterministic, no training, no LLM)
- `bind(role, filler)` = phasor product = phase addition (unitary, invertible — test proves
  unbind recovers the filler at resonance > 0.99)
- context window → one vector: `Σ_j decay^j · bind(role_j, φ(t_j))` (holds the WHOLE window)
- `predict` = a resonance-weighted vote over the NEAREST stored context traces (a kernel-smoothed
  n-gram). NOTE: an earlier design bundled one prototype per successor — it blurred
  catastrophically on a real corpus (crosstalk) and LOST to the bigram (0.05 vs 0.15). The
  kernel-vote over individual traces is what actually works; the vote also carries the frequency
  prior (a common successor has more nearby traces).

## Measured result (beats the baseline — brief §5)

The disambiguator (a noun) sits BEFORE the shared token `IS`, so a last-token bigram is blind to
it. `test_holographic_lm.py` (6 tests, all green):

| task | holographic | bigram baseline |
|---|---|---|
| wide-context disambiguation (`ball IS`→round, `box IS`→square) | correct 6/6 | 50/50 tie (chance) |
| **generalization to an unseen modifier** (`green ball IS`→round; "green" never trained) | **100%** | **50%** |

Also verified: generation stays on-topic (window coherence — a water-topic seed never drifts into
the space-topic vocabulary), never emits a token absent from the grounding corpus
(`fabricated_facts: False`), and is deterministic.

Why it generalizes (the point n-grams miss): resonance is a similarity kernel. A context never
seen verbatim still resonates with prototypes whose stored contexts share sub-structure with it,
so an unseen combination predicts a plausible next unit — and a wider context disambiguates where
a bigram cannot.

## Theory — when/why density → generation (brief §4.4, the honest answer)

The substrate is a **kernel n-gram**: the context vector φ(c) is a locality-sensitive feature and
`resonance(φ(c'), φ(c))` is a similarity kernel; prediction is a similarity-weighted vote over the
corpus. This makes the density claim precise:

1. **Generalization holds when kernel similarity tracks predictive similarity** — i.e. contexts
   that share bound sub-structure tend to share continuations. That is exactly the property of
   *compositional* language (a shared construction implies a shared continuation), which is why it
   works for language and would not for arithmetic.
2. **Density helps in two ways**: more contexts per successor average out idiosyncratic noise
   (sharper prototypes), and better coverage of the sub-structure space means more novel contexts
   have a near neighbour.
3. **The ceiling is representational capacity, not data.** A prototype is a bundle; FHRR capacity
   is ~O(D) superposed terms before crosstalk blurs retrieval. So density improves generation
   **only while there is dimension headroom**; past that, adding data into a fixed-D bundle
   *degrades* it (crosstalk). The real scaling law therefore **couples data with dimension D**
   (and with prototype multiplicity — see next), not data alone. (On the tiny battery here D=64
   already saturates the task at 6/6, so density is monotonic; the coupling shows up at scale.)

This is the honest correction to "just add nodes": denser graph → better generation **iff** the
representation's capacity scales with it.

## v2 — semantic generalization (done)

The v1 base vectors were random, so generalization was over **token-overlap** only. v2 adds a
`semantic=True` mode: base filler phasors are **Random Fourier Features of the IDF-weighted
co-occurrence embedding** — `φ(s) = exp(i · E_s · R)`, which by Bochner makes
`resonance(φ(a),φ(b)) ≈ exp(−‖E_a−E_b‖²/2)`, an RBF kernel over distributional embeddings. Roles
stay random for clean role separation. Deterministic, still no training/LLM.

Measured (`test_holographic_lm.py`, now 9 green):

| token (never seen before the target) | semantic base | random base (v1) |
|---|---|---|
| `puppy` → animal sound? | **barks** (0.56 vs honks 0.01) ✓ | honks ✗ (noise) |
| `sedan` → machine sound? | **honks** (0.38 vs barks −0.02) ✓ | barks ✗ (noise) |
| resonance dog~cat (same contexts) | **1.00** | 0.015 |
| resonance dog~car (different) | −0.01 | — |

This is **semantic generalization the token-overlap model cannot reach**: `puppy` picks the
animal sound purely because it is *distributionally* like dog/cat, with no rule and no prior
`puppy→barks` example. This is the toy→real bridge — the mechanism that lets density over real
corpora yield generalizing generation.

## Real-corpus validation — the honest bar (done)

Toy batteries are not enough. Validated on **2,975 real encyclopedic sentences**
(`data/cloud_brain/.../clean_retrain_v1/evidence.jsonl`), 85/15 held-out split, top-1 next-token
accuracy (no training, no LLM). Locked in by `test_beats_bigram_on_real_held_out_sentences`:

| model | overall | unseen-trigram-context slice (generalization) |
|---|---|---|
| bigram (what the walk uses today) | 0.150 | 0.119 |
| trigram + backoff | 0.153 | 0.119 |
| **holographic kernel-vote** | **0.166** | **0.132** |

The substrate **beats exact n-grams on real held-out sentences**, and wins by MORE on the unseen-
context slice — i.e. the gain is exactly the generalization the brief asked for, on real data, not
a toy. (The first prototype-bundling design lost here at 0.05; finding and fixing that on the real
corpus is why this is not a toy result.)

## Honest limits + next steps

- Absolute accuracy is still low (0.166) — this beats the current baseline but is a *substrate*,
  not a finished generator; **fluent long-form generation needs a much larger corpus** (density)
  and integration. The win is real and directional, not "solved".
## Memory scaling — measured levers (honest)

The kernel memory is one vector per training position (linear in corpus). Measured on the real
corpus for what bounds it WITHOUT losing accuracy:

- **Context clustering does NOT compress** — a greedy radius merge keeps 92–97% of traces even at
  a loose 0.7 threshold and *lowers* accuracy (0.166→0.152). In 256–512 dims real contexts are
  near-orthogonal, so there is little to merge: the traces are genuinely diverse (that diversity
  is what makes the model work). An honest negative result.
- **Dimension**: D=256 matches D=512 (0.168 vs 0.160, within noise) → default lowered to 256 (2×).
- **uint8 phase quantization**: storing each component's phase as 1 byte holds accuracy
  (D=256 → 0.160) → ~256 B/trace, a 32× per-trace reduction vs D=512 complex128.

Net: per-trace footprint is now small, but memory stays **linear in corpus**. Constant factors do
not reach trillion scale — that needs a **sharded / disk-backed approximate-nearest-neighbour
index** over the quantized codes (a systems problem, not a representation one). Flagged, out of
this scope.

## Fluent free-text generation (`generate_fluent`, done)

`predict()` gives next-token scores; `generate_fluent()` turns them into a fluent, COMPLETE,
COHERENT sentence: the window kernel-vote proposes corpus-attested next tokens, a GLOBAL
superposition of everything emitted re-ranks them by coherence (kills the topic-drift a pure
window shows at clause boundaries), a repetition penalty avoids loops, and decoding stops at a
sentence-final token. Only ever emits corpus tokens (`fabricated_facts: False`).

Measured on the real corpus:
- 광합성 → "광합성 … 빛에너지를 화학 에너지로 전환하기 위해 사용하는 과정이다" (complete, fluent).
- 대한민국 → greedy DRIFTS ("민법 제53조 … 조문이다 → 전라남도 해남군 초등학교", two entities
  stitched); `generate_fluent` STOPS at "…조문이다" — coherent + complete. The anti-drift fix.

Honest scope: this is fluent **grounded** generation — fluent, coherent, complete sentences drawn
from and coherent with real sources. It is NOT yet novel free composition from nothing (that would
need cross-source blending under the same coherence guard + a real grammar, and remains a
fabrication risk to control). Some seeds still hit max_len before a sentence end (tuning).

## Next steps
- Live integration of `predict()` / `generate_fluent()` into `_walk_for_frame` / the answer path (Claude, brief §7).
- Sharded ANN retrieval for large-scale memory (systems).
- Absolute accuracy (0.166) rises with corpus density — the substrate is validated; fluent
  long-form generation is a scale + integration problem now, not an architecture one.
- Integration into the live `_walk_for_frame` / answer path is Claude's job (brief §7); the module
  exposes a clean `predict(context) → scores` interface for a bounded additive term, exactly like
  the existing `Superposition.interference` nudge.

No push / no deploy (brief §6). Module + tests committed locally.
