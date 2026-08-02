# ATANOR × V-JEPA 2 — Latent Predictive Coding, cleanly fused (2026-07-24)

> **Canonical boundary (2026-07-25):** this is a G3 research design and
> mechanism record, not the solved center or the immediate execution spine.
> Frame-JEPA, SPLATRA, and the holographic 4D/block-universe path remain
> default-off/background hypotheses until each clears an independent E4 and
> then demonstrates paired E5 lift. “BUILT” below means only the stated scoped
> organ/mechanism; real-video training, general 2D→3D lift, long rollout, shared
> latent unification, and authoritative live integration remain unsolved. The
> current operator path is NL→goal compiler + scientific-knowledge staging →
> E4 → paired E5 GPQA/MMLU-Pro.

Owner ask: "atanor에 V-JEPA2의 원리를 이어볼 수 있을까 → 설계하고 깔끔하게 융합해줘."

Not a model port (V-JEPA 2 is ~1B params over 1M+ hours of video — outside our N1–N3 neuro-budget). We
adopt the **principle** at our scale and fuse it into organs that already exist.

## 1. The V-JEPA 2 principle (three claims we keep)

1. **Predict in LATENT space, not pixels.** Reconstructing pixels wastes capacity on unpredictable
   detail (lighting, noise, texture). Predicting the *representation* of a masked/future region keeps
   only what is semantically predictable.
2. **Non-generative, collapse-safe world model.** Context-encoder + predictor + an EMA (stop-gradient)
   target-encoder; representational collapse is prevented architecturally, no pixel decoder in the loop.
3. **Prediction error is the signal.** Latent surprise drives learning, attention, and (for us)
   doubt — and, action-conditioned, it drives planning.

## 2. The honest finding: ATANOR already has the SHAPE, in the wrong space

The three perception organs already run `predict → surprise → attention/compute-budget`. They just
predict in **discrete** or **pixel** space — exactly the axis V-JEPA says to move off.

| Organ | What it already does | The V-JEPA gap |
|---|---|---|
| `perception/attention.py` | `change_energy` = mean-abs-diff of two **retinal codes** (downsampled grayscale). Fires the detector on change. | Pixel-space delta: fires on lighting/noise, blind to semantic change with low pixel delta. Predicts nothing — only diffs last-vs-current. |
| `perception/video_events.py` | `predict_next` + `surprise` — a real world-model prediction (object permanence, causal continuation) and a prediction-error score feeding System-2. | Prediction is **symbolic** (scene-graph label/edge diff). Misses sub-symbolic change (a motion, a texture, a not-yet-named object shifting). |
| `perception/reconstruction_loss.py` | Owner's autoencoder-vision v0: bottleneck → rebuild → **semantic-topology** loss, decoder "DUMB on purpose", generative renderer barred from the truth signal. | Already JEPA-aligned in *doctrine*. Missing the **learned latent predictive layer** between retinal code and scene graph. |

So the fusion is not a new subsystem — it is **one latent predictive layer** slotted where these three
already reach for a prediction, upgrading their signal from pixel/discrete to **semantic-latent**.

## 3. The fused organ: `perception/latent_predictor.py` (new, ≤25M, No-LLM)

A small JEPA-style predictive coder over the retinal-code stream `attention.frame_signature` already
produces (no new sensor needed):

- **Context encoder** `f_θ`: retinal code (+ short history) → latent `z_t`.
- **Predictor** `g_φ`: `(z_{t-k..t}, mask/Δt)` → predicted latent `ẑ_{t+1}` of the masked/next region.
- **Target encoder** `f_ξ`: EMA of `f_θ` (stop-gradient) → true `z_{t+1}`. Collapse-safety = EMA
  asymmetry + a light variance/covariance term (VICReg-style) so `z` can't shrink to a constant.
- **Latent surprise** `s_t = ‖ẑ_{t+1} − z_{t+1}‖` — the single signal the three seams consume.

Self-supervised: it learns from the ordinary frame stream, no labels. Tiny by design (an MLP/temporal-
conv over the 1024-d retinal code, not a ViT) — report the actual param count; the budget ceiling is
25M and we expect far less.

## 4. The three clean seams (fuse, don't bolt on)

Respecting **one-model-not-modeswitch**: the predictor is one general organ; its error feeds existing
decision points. It never becomes a "video mode".

- **Seam A — `attention.py`:** add a latent path to `change_energy`/`decide`: gate on **latent
  surprise** `s_t`, not raw retinal delta. Effect: the expensive detector fires on *semantic* change
  and idles through lighting/noise — the V-JEPA robustness win, measured against the pixel baseline.
  Keep the pixel delta as a cheap fallback (cold start / pre-training).
- **Seam B — `video_events.py`:** add latent surprise **alongside** the existing symbolic `surprise`
  (never replacing it). Discrete scene-graph surprise catches named-object/edge changes; latent
  surprise catches sub-symbolic change the labels miss. `think_harder = symbolic OR latent`.
  Prediction stays a flagged hypothesis (generative-leap doctrine) — a latent prediction is DATA.
- **Seam C — the membrane (interface only, no edit now):** expose `s_t` as a **nonconformity
  candidate**. Perception-side latent surprise is a calibratable doubt signal the conformal gate can
  consume (ties to [[final-gate-research]]). Ship a clean read interface `latent_nonconformity()`;
  the actual wiring into `conformal_gate` is a follow-up (that package is under active hardening — do
  not touch it now).

## 5. Action-conditioned extension (V-JEPA 2-AC → Track E, later)

`g_φ(z_t, action) → ẑ_{t+1}` is exactly the embodiment forward model. Track E **M1** already learns a
proprioceptive forward model (babble → kinematics); the visual-latent version is the same principle on
the perception stream. Deferred to the embodiment track — noted, not built here.

## 6. Doctrine gates (binding)

- **No-LLM = runtime property:** a neural perception/prediction *organ* is legal ([[external-minds-are-data]]).
  Its output is DATA/proposal; the symbolic membrane verifies — a latent prediction is never enshrined as fact.
- **Non-generative:** no pixel decoder in the loss. A generative renderer, if ever, is an optional
  realism layer, never the truth signal (as `reconstruction_loss.py` already insists).
- **Neuro-budget N1–N3:** single model ≤25M; report actual count.
- **Physics-truth gate:** a prediction is learned/promoted only after passing physics-invariant checks
  ([[realcity-physics-truth-gate]]) — a surprise that violates physics is quarantined, not trained on.
- **Structure > memorization:** the coder learns predictable *structure*; prove generalization on a
  held-out sequence it never trained on, not memorized frames.

## 7. v0 = mechanism proof (honest boundary)

v0 proves the **mechanism**, not an internet-scale world model. On controlled/synthetic frame sequences
(scene-graph fixtures already in the tests + procedurally perturbed variants):

- Does **latent** surprise mark semantic events **better than** (a) the pixel retinal-delta baseline
  and (b) the discrete scene-graph surprise — especially on **low-pixel-delta semantic change** and
  **high-pixel-delta non-events** (lighting/noise)? Report precision/recall of event marking vs both baselines.
- Does it hold on a **held-out** sequence (generalization, not memorization)?
- Collapse check: latent variance stays bounded away from zero.

Honest verdict required: latent prediction error is a **better/■equal/worse** event+attention signal than
the pixel/discrete baselines — with the measured curve. No claim of a trained world model; v0 is the
predictive-coding layer + the three seams + the measurement.

## 8. Build plan

1. `perception/latent_predictor.py` — the coder (encoder/predictor/EMA-target, latent surprise, VICReg
   guard), self-supervised trainer on the retinal-code stream. numpy or light torch, ≤25M.
2. Seam A + B wiring (`attention.py`, `video_events.py`) — additive, pixel/discrete paths preserved as
   fallback; no existing test weakened.
3. Seam C interface `latent_nonconformity()` — exposed, NOT wired into `conformal_gate` yet.
4. Mechanism-proof harness + honest scorecard vs both baselines + held-out + collapse check.
5. Tests green (existing `perception` suite unchanged + new); local commit, no push.

## 9. The 3D twin — SPLATRA-coupled world model (owner's real-time-sim insight)

Owner's idea: JEPA predicts the *next physical change* as a **light vector**, Dynamic 3DGS expresses it
as real-time particle deformation → real-time autonomous 3D sim with **no hand rigging, no 2D video
reconstruction**. Feasible — and most of it already exists. This is the **generative/embodiment face**
of the same principle; §1–8 are the perception/video face.

### The pieces already on disk
- `packages/embodiment/splatra_body.py` — ALREADY runs the owner's exact loop, CPU, No-LLM:
  `act → body responds → forward model PREDICTED it → prediction error = surprise → habituates`. That
  is V-JEPA 2-AC (action-conditioned) on a SPLATRA body. **Gap:** it predicts a 9-d *pose* (centroid +
  extent + tip), not the full field.
- `packages/splatra_turbovec/` — the **light vector**: a compressed field codec (`field_quantizer`,
  `codec`, `quantization`) for the particle field. This IS "가벼운 벡터" — JEPA predicts in THIS space,
  not pixels, not raw particles (exactly JEPA's predict-in-latent).
- `packages/splatra_imagination/generative.py::synthesize_form` — body/scene particles; `Particle`
  already carries velocity (vx,vy,vz) + material — a physics-ready state.

### The fused pipeline (predict light → deform → VERIFY → render)
```
state ──encode──▶ turbovec z_t ──JEPA g_φ(z_t, action)──▶ ẑ_{t+1}   (light-vector prediction)
                                              │
                                    decode ẑ ▶ per-particle Δ (Dynamic 3DGS deformation)
                                              │
                              PBD / physics-truth VERIFY  ◀── the symbolic membrane in 3D
                                              │  (interpenetration? momentum? ground _GROUND_Y?)
                        pass ▶ render/advance   fail ▶ quarantine (never learned)  [[realcity-physics-truth-gate]]
```
- **Membrane in 3D**: JEPA *proposes* dynamics (neural, light vector); **PBD/physics *verifies*
  (symbolic)**; a predicted deformation that breaks a physics invariant is quarantined, not trained on.
  The 3DGS layer RENDERS; it is never the truth signal (same rule as §6 / `reconstruction_loss.py`).
- **No rig / no video reconstruction**: deformation is driven by the predicted field-delta + PBD
  constraints, not a hand-authored skeleton or a pixel decoder.

### Placement (adjacent, non-conflicting)
New `packages/splatra_worldmodel/` — imports `splatra_turbovec` (light vector), `embodiment.splatra_body`
(the proven act→predict→surprise kernel + PBD), `splatra_imagination.generative` (body). Read-only
imports; generalize the 9-d forward model to the turbovec field-delta by wrapping, not editing, the
existing organs. Reuses the §3 JEPA recipe (EMA target, latent surprise, VICReg guard) over turbovec.

### Honest boundary (완벽히는 아직)
- The latent→deformation **decode is a learned map** — reconstruction is MOVED from 2D pixels to the
  **compressed 3D field** (structured, physics-constrained), not eliminated.
- v0 = **mechanism proof on TOY dynamics** (a falling / deforming body): does JEPA-over-turbovec predict
  the next field-state better than a no-model / linear baseline, does physics-truth catch injected
  violations, does it hold on **held-out** dynamics, does the latent avoid collapse. NOT a general
  real-world simulator; grounding real physical-state at fidelity is the open frontier.
- Honest verdict required: BETTER/EQUAL/WORSE than baseline with numbers; "real-time autonomous sim"
  is the aspiration this v0 measures the first rung of, not a claim.

## 10. Learning from real video (owner's YouTube insight) — the honest bridge off toy dynamics

§9's boundary was "toy dynamics, not real-world sim." Owner's fix: learn from real video (YouTube etc.),
self-supervised — which IS V-JEPA 2's actual recipe (1M+ hours of internet video). Right principle.
Four honest constraints, foregrounded, then the aligned loop.

### Constraints (no pretense)
1. **Scale.** V-JEPA 2 = ~1B params / 1M+ hours / GPU cluster. Our budget is ≤25M on a local box. We
   learn from a **small curated stream → a NARROW world model**, not a V-JEPA-2. State this plainly.
2. **2D→3D gap.** YouTube is 2D; the §9 SPLATRA model is 3D. Video most naturally trains the **2D
   frame-JEPA** (§1–8). Feeding the **3D** model needs a 2D→3D **lift** (monocular depth / structure-
   from-motion / the `perception.spatial_memory` 3D-lift). That lift is the real bottleneck:
   `video → depth/SfM lift → turbovec state → SPLATRA JEPA`.
3. **Contamination (doctrine-critical).** YouTube is full of CGI / cartoon / edited / impossible
   physics. Naive learning = FAKE physics + [[consciousness-stream-pollution]] ("web noise as self").
   The **physics-truth gate is the firewall**: only physically-consistent motion trains the model;
   cartoon/impossible motion is quarantined. We already have this gate — it is *exactly* what makes
   learning from real video safe. This is the alignment win, not an afterthought.
4. **Copyright / ToS / autonomous download.** Mass-downloading YouTube is operator-gated (copyright,
   platform ToS, the download-permission rule). We do NOT autonomously scrape YouTube. Start with
   **openly-licensed / physics-simulation / small curated** video; sourcing at scale is the owner's call.

### The aligned loop
```
autonomous daemon curates physics-relevant clips (operator-gated sourcing)
   → 2D→3D depth/SfM lift
   → PHYSICS-TRUTH GATE  (fake/CGI/impossible motion → quarantine, never learned)
   → turbovec state
   → SPLATRA JEPA (§9) self-supervised, ≤25M
   → world model improves toward REAL dynamics
```
The OAM autonomous-acquisition daemon ([[autobiography-and-causal-corpus]] / the "밤새 스스로 배워온다"
engine) drives curation; the physics-truth gate is the contamination firewall; the budget stays ≤25M.

### Honest frame
This turns §9's toy dynamics toward real dynamics **at our scale** — a narrow, physics-gated world
model, never a claim of V-JEPA-2 parity. Depends on §9 (#74) landing first (you can't train a world
model that doesn't exist yet). v0 = learn from a small curated/licensed physics-video set through the
gate; measure whether real-video-trained prediction beats toy-only. **Autonomous YouTube-at-scale is
the aspiration this measures the first rung of — operator-gated, not autonomous.**

## 11. The unified picture (owner's synthesis) — JEPA × block-universe × membrane = the temporal membrane

Owner (2026-07-24): *"JEPA = a proposer that efficiently lays future-latent-state hypotheses onto the 4D
holographic block-universe timeline; the T0 membrane = the judge that keeps only the physically/logically
non-contradictory trajectories."* **Correct as architecture** — it is the neuro-symbolic thesis (neural
proposes, symbolic verifies) applied to the **time axis**. It names the convergence point of three
threads into one loop.

### Mapping to organs — BUILT vs ASPIRATIONAL (honest)
| Role in the synthesis | Organ | Status |
|---|---|---|
| JEPA proposes future latent-state hypotheses | frame-JEPA (§1–8, #73), SPLATRA world model (§9, #74/#76) | **BUILT**; predictions flagged `is_hypothesis=True` |
| 4D holographic block-universe timeline (the substrate) | [[unified-utc-timeline]] V2.1; FHRR/VSA holographic | **BUILT as an organ** — but JEPA-predictions-laid-**onto**-it = **NOT yet wired** (separate organs) |
| Judge — **PHYSICAL** contradiction | physics-truth gate | **BUILT + wired** into §9 (36/36 injected violations quarantined) |
| Judge — **LOGICAL** contradiction over trajectories | TMS temporal-consistency gate (V2.2, task #8) | **PENDING** |
| Judge — statistical / calibrated | conformal membrane | **BUILT** for the answer lane; **not yet over trajectories** |

"물리/논리적 모순" maps *exactly* onto **physics-truth (physical) + TMS (logical)** — the owner named both
halves of the judge. The conformal gate adds the calibrated statistical layer.

### Honest refinement (doctrine)
The judge keeps *trajectories not yet contradicted* — which **stay HYPOTHESIS-FLAGGED**. It does not assert
"truth". Everything on the block-universe axis is a marked guess (retrodiction / prediction / invariant),
never stated as fact ([[voice-or-silence-doctrine]] / generative-leap). So precisely: "진실만 골라내는"
→ **"모순 없는 가설만 남기는"**. That distinction is what keeps hallucination at zero — a non-contradicted
future is still a flagged hypothesis, not a certified fact.

### The integration this names (the "temporal membrane")
Wire JEPA's predicted trajectories **onto** the block-universe timeline, then route the 4D trajectory
through the membrane trio (physics-truth ✓ + TMS temporal gate [V2.2 #8] + conformal). Prerequisite:
V2.2 (#8). Sequenced AFTER the decisive proposer-side tests (#76 SPLATRA-vs-linear, #77 H4 open-ended)
land — no point wiring a trajectory judge onto a proposer we haven't yet validated.

## 12. The unification — ONE perception, ONE world model, ONE reasoner (owner's correction, 2026-07-24)

**Owner corrected a real error of mine.** Proposing a *separate ARC world model* violates
[[one-model-not-modeswitch]] (BINDING) — a second engine keyed to a specific input, the exact trap the
doctrine forbids. Humans do not build a different world model for a phone screen vs the world; they run
**one** world model on different content. The correct architecture:

```
single general PERCEPTION → ONE modality-agnostic WORLD MODEL (JEPA latent prediction)
                                          → H4 REASONING / invention → membrane VERIFY
```

- **NOT per-domain models.** The frame-JEPA (§1–8) and the SPLATRA world model (§9) are **not two
  models** — they are **one predictive core over a COMMON latent**, with perception as the single
  encoder. The latent is the equalizer — which is JEPA's own thesis: predict in latent space,
  source-modality-agnostic. §9–11's "two faces" = two INPUT modalities into ONE model, never two models.
- **ARC-AGI-3 is not a special case.** It is the ONE world model + H4, fed ARC grids through the ONE
  perception. No mode-switch, no ARC-specific model.

**The real crux (honest).** The hard part is the **single general perception** that encodes ANY input —
continuous physics AND discrete/symbolic ARC grids, a screen, video — into the common latent *faithfully*.
That is exactly where the neuro-symbolic split lives, and it lives **inside the one pipeline**: neural
predicts (world model), symbolic invents/reasons (H4), membrane verifies — one substrate, never a second
engine. The earlier "ARC rules are symbolic" point stands, but as a property of the ONE reasoner (H4),
not a reason to fork a model.

So the build direction is **unification**, not construction of an ARC model: unify the JEPA predictors
into one world model over a common latent + one general perception encoder + H4 reasoning over it.

Related: [[video-understanding-stitch]] [[predictive-attention-gate]] [[grounded-constrained-generation]]
[[final-gate-research]] [[realcity-physics-truth-gate]] [[unified-utc-timeline]] [[track-e-embodiment-promoted]]
[[splatra-generative-and-fable5-priorities]] [[splatra-imagination-compiler]] [[consciousness-stream-pollution]]
[[voice-or-silence-doctrine]] [[autobiography-and-causal-corpus]] [[external-minds-are-data]]
[[temporal-causal-physics]] [[one-model-not-modeswitch]].
