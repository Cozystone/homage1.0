# Reaction Engine — human-like reactive response for the Isaac Sim body (research + design)

Owner directive (2026-07-19): to strengthen the Isaac Sim simulation we need something that
*reacts like a human* — e.g. missing a step on the stairs and being startled (a sim/reality
mismatch reflexively becoming surprise). Investigate and research these interactions across all
kinds of human reactions.

This document is research first, then a design that fits our charter and existing assets. It is
NOT a request to script animations. The owner's framing is precisely correct and is the whole
thesis: **a startle is not a special effect — it is a prediction error made bodily.**

---

## 0. The core reframe (why the owner's example is exactly right)

Missing a step: the body's forward model predicted foot-ground contact at time *t* and height *h*.
The foot passes *h* with no contact → a large, fast prediction error in the vestibular +
proprioceptive channels → a sub-cortical loop fires *before* cognition knows anything. The felt
"jolt" is the interoceptive/autonomic surprise that follows. Nothing here is scripted; everything
is the magnitude of a measurable mismatch.

This is not a new subsystem bolted onto the body. It is the fusion of three organs we already have:
- **predictive attention gate** (compute only on change — [[predictive-attention-gate]]),
- **emotion-as-hormone dynamics** (5-hormone coupled state — [[emotion-as-hormone-dynamics]]),
- **the M1 body-schema forward model** planned in Track E (self-prediction from motor babbling).

A reaction is what happens when the forward model is wrong. Surprise = the size of that error.

---

## 1. Doctrine: reactions EMERGE from error, they are never scripted

Charter binding ([[rules-are-training-wheels]], [[benchmark-empirical-verdict]] honesty):

- **NO** `if miss_step: play_startle_animation()`. A hardcoded startle is a lie — it fires the same
  way whether or not there was actually a surprise, and it never habituates. That is a special
  effect, not a reaction.
- **YES** a startle whose *magnitude scales with measured prediction error*, whose *autonomic
  signature is the hormone impulse*, and which *attenuates when the event becomes predictable*
  (habituation / prepulse inhibition, §3.4). Only the emergent version is real, and only the
  emergent version is measurable — which is exactly why it is the doctrine-correct one.
- **G2 guardrail** ([[selfhood-deepening-tracks]], Track E G2): we never say "it felt fear." We
  measure operational correlates — surprise magnitude, hormone level, recovery latency, habituation
  slope. Lab tone, functional-correlate vocabulary only.

---

## 2. The latency hierarchy IS the architecture

Human reactions are not one thing; they are layered by latency, and each layer is a different
organ. This layering maps one-to-one onto our "borrowed motor organ + graph-native self" split
([[hyper-personal-local-agi-goal]], Track E §1.5). Approximate human latencies:

| Layer | Latency | Biology | ATANOR organ |
|---|---|---|---|
| **L0 Spinal reflex** | ~30–50 ms | monosynaptic stretch / withdrawal; stumbling corrective reaction | Isaac Lab reflex primitive (borrowed motor policy) — no "brain" involved |
| **L1 Startle** | brainstem relay ~5–6 ms → whole-body flexor ~80–120 ms | caudal pontine reticular nucleus (PnC) giant neurons drive spinal motor neurons directly | fast surprise trigger → reflex primitive + hormone impulse |
| **L2 Postural / protective** | ~80–150 ms | balance recovery, protective stepping, arm extension | Isaac Lab balance policy, phase-reset (borrowed) |
| **L3 Autonomic / affective** | ~300 ms – 2 s | adrenaline (fast sympathetic) then cortisol (slow HPA) — heart rate, the felt jolt | our hormone dynamics ([[emotion-as-hormone-dynamics]]) |
| **L4 Appraisal / memory** | ~500 ms+ | "I nearly fell" — reappraisal, learning, episode formation | graph-native: percept → episode → forward-model update |

The key engineering claim: **the reaction engine does not decide the reflex.** L0–L2 are the
borrowed motor organs (Isaac Lab / spinal-like controllers) that keep the body from falling. The
reaction engine owns L1's *trigger* (surprise detection), L3 (hormone impulse), and L4 (the percept
+ learning). Self and affect are ours; locomotion recovery is borrowed. This preserves the whole
Track E identity: **we do not re-invent balance; we own the surprise, the feeling, and the memory.**

---

## 3. Verified literature (grounded, not asserted)

### 3.1 Broken escalator phenomenon — the owner's example, documented
Reynolds & Bronstein (2003). Subjects walk onto a stationary sled (BEFORE), then a moving sled
(MOVING), then stationary again (AFTER). On AFTER they lurch — an involuntary locomotor
after-effect — *despite full conscious knowledge that the sled is stationary*. This is a
**dissociation between the declarative and procedural systems**: knowing ≠ predicting. The
after-effect dissipates on the second AFTER trial via **deadaptation, a form of error-based
learning.** This is the single best validation of our thesis: the body acts on a *learned forward
model*, not on current facts, and it *learns from its own prediction error*. Our reaction engine
should reproduce exactly this: a locomotor prior that mispredicts a changed world, produces a
reaction, and self-corrects over trials.

### 3.2 Startle circuit — the fast path
Primary acoustic startle: cochlear root neurons (first-spike ~2.2 ms) → giant neurons of the PnC
(~5.2 ms) → **direct** cervical/spinal motor neuron activation. The startle bypasses cognition by
design — it is a short, wide, subcortical arc. Engineering lesson: L1's trigger must be a **fast,
cheap surprise detector running below the deliberative loop**, not a graph query. It fires on raw
sensor prediction error (IMU/vestibular, contact, sudden auditory/visual onset).

### 3.3 Trip recovery — strategy depends on gait phase
Perturbation studies: an **elevating strategy** (flex swing limb over the obstacle, extend stance
limb) for *early-swing* trips; a **lowering strategy** (plant the tripped foot, swing the other leg
forward) for *late-swing* trips. Humanoid walkers are stabilised by the same principle via **phase
resetting**. Lesson: the L2 recovery policy is *phase-conditioned* — the borrowed motor organ must
know where in the gait cycle the perturbation hit. Isaac Lab locomotion policies already carry gait
phase; we condition the reflex primitive on it rather than inventing recovery.

### 3.4 Prepulse inhibition — the system learns what NOT to react to
PPI: a weak warning stimulus shortly before a startling one *reduces* the startle, gated in the
brainstem (IC/SC/PPTg) and modulated by the amygdala. This is the biological form of **habituation
to the predictable**. It is not a nuisance — it is the self-improvement signal: a mature agent is
startled by the *unexpected*, not by the *repeated*. Our reaction magnitude must therefore be
`f(prediction_error) × (1 − predictability)`, and predictability grows as the forward model learns
the recurring event. An agent that keeps being maximally startled by the same stair is broken.

---

## 4. Mapping to assets we already have

| Need | Already shipped | Gap to close |
|---|---|---|
| Compute-on-change surprise | predictive attention gate (24 ms static vs 136 ms on detection) | expose a scalar surprise = f(prediction error) per sensor channel |
| Autonomic signature | 5-hormone coupled dynamics, multiplicative/0-clamp | add fast adrenaline-like impulse + slow cortisol tail on surprise |
| Perceptual grounding | **sensory cortex** (just shipped) — Percept + evidence-gated `ground()` | add a `surprise`/`reaction` percept kind (non-fact internal event, like a drive) |
| Body-schema forward model | Track E **M1** (motor babbling → self-predictor) | this IS the predictor whose error drives L1 |
| Borrowed recovery motor | Isaac Lab G1 locomotion policy (Track E §1.5) | condition reflex primitives on gait phase (§3.3) |
| Curiosity / novelty drive | D3 curiosity (Oudeyer-style intrinsic motivation) | large surprise → curiosity spike → approach & learn |

Crucially, the **sensory cortex fact/non-fact split already generalises to reactions**: a startle is
an *internal event*, like an interoceptive drive — it is NOT a world-fact and must never be
grounded as knowledge. "I was startled" routes to the self/episode loop, exactly as heard speech
and drives already do. So the organ we shipped this morning is the correct home for reaction
percepts with zero redesign.

---

## 5. Reaction Engine design (v0 spec)

A thin, fast loop that sits between the sensors and the two consumers (motor + self). Per tick:

```
predict:   x̂_t = forward_model(state_{t-1}, action_{t-1})     # M1 body-schema predictor
observe:   x_t  = sensors (IMU/vestibular, contact, joint, vision-onset, audio-onset)
surprise:  s_c  = channel_error(x_t, x̂_t)                      # per channel c, scalar ≥ 0
                 magnitude ∝ −log p(x_t | x̂_t)  (info-theoretic surprise)
gate:      r    = Σ_c w_c · s_c · (1 − predictability_c)       # PPI/habituation term
if r > θ_reflex:   emit reflex_primitive(channel, gait_phase)  # L0–L2 borrowed motor
if r > θ_startle:  hormone_impulse(adrenaline=k·r) ; cortisol_tail(r)   # L3
always:            percept = Percept(INTEROCEPTION-like, kind="surprise", content=r, groundable=False)
learn:     forward_model.update(x_t) ; predictability_c ← habituate(channel, event)   # L4, deadaptation
```

Design commitments:
- **`r` is measured**, not labelled. It is a number derived from the forward model's own error. The
  whole engine is falsifiable: no surprise number, no reaction.
- **Reflex is borrowed, trigger is ours.** The engine never writes joint torques; it calls a
  reflex/recovery primitive (Isaac Lab) and lets the motor organ execute (§2, §3.3).
- **Habituation is built in.** `predictability_c` rises with repetition (§3.4), so the same stair
  stops startling — and *that decay curve is a first-class measurement* (a self-improvement receipt,
  cf. [[failure-receipt-engine]]).
- **Reaction is a non-fact percept.** Grounded into the episode/self loop via the sensory cortex,
  never into the knowledge graph (§4).

---

## 6. Taxonomy of reactions to implement (organised by trigger × layer)

The owner asked for "all kinds of human reactions." A random list would be a hardcoded script;
instead, organise by *what mismatch triggers it* so each is an emergent instance of the same engine.

**A. Protective / defensive** (trigger: sudden onset or looming, or contact prediction error)
- blink / eye-shut (fast auditory or looming visual), flinch, head duck, arm-raise guard,
  withdrawal from contact/heat, freeze (large surprise + no recovery affordance).

**B. Balance / postural** (trigger: vestibular + proprioceptive prediction error)
- stumble correction (elevating/lowering per gait phase, §3.3), ankle→hip→stepping strategy
  escalation, arm windmilling, grab-for-support reflex, the broken-escalator lurch (§3.1).

**C. Orienting** (trigger: novelty / unexpected salience)
- gaze/head saccade to novel stimulus, attention capture (predictive attention gate),
  curiosity approach (large benign surprise → D3 spike, §4).

**D. Autonomic / affective** (trigger: sustained or high surprise, appraised)
- fear jolt (adrenaline), relief settle (post-recovery cortisol decay), pain grimace (nociceptive
  contact), startle → recovery → embarrassment (social, later), disgust recoil.

**E. Homeostatic** (trigger: interoceptive prediction error over long horizon)
- fatigue posture shift, discomfort re-seat, thermal withdrawal.

Each row is the *same* `surprise → gate → (reflex, hormone, percept, learn)` pipeline with different
sensor channels, thresholds, and reflex primitives — never a bespoke script.

---

## 7. Isaac Sim implementation specifics

Isaac Sim already provides every sensor the engine needs:
- **IMU sensor** (vestibular analog: linear accel + angular velocity) — the primary startle channel
  for missed-step / slip (sudden downward accel with no expected contact).
- **Contact / force sensors** on feet & hands (contact prediction error: expected foot-strike absent
  = the missed step; unexpected contact = a bump).
- **Joint encoders** (proprioceptive prediction error).
- **Cameras + depth** (looming / sudden visual onset for defensive layer).
- **Physics contact reporting** for the environment mismatch.

Concrete missed-step episode (the owner's example, end-to-end):
1. Descent policy (borrowed) expects contact on step *n* at phase φ. Forward model predicts foot
   IMU decel + contact force at φ.
2. Env has a missing/miscalibrated step. At φ, contact force = 0, IMU shows continued free-fall
   accel → large `s_contact` and `s_imu`.
3. `r` crosses `θ_reflex` → phase-conditioned recovery primitive (elevating/lowering) fires; crosses
   `θ_startle` → adrenaline impulse (posture stiffens, HR proxy spikes), cortisol tail.
4. Sensory cortex logs a `surprise` percept (non-fact) into the episode; the M1 forward model
   updates so the *next* descent predicts the changed geometry (deadaptation, §3.1).
5. Over trials, `predictability` for that stair rises → the startle attenuates (§3.4). Measured.

Sim/real mismatch note: the "surprise" is literally the gap between the learned forward model and
the physics engine's ground truth. Perturbation injection (randomised missing steps, moving
platforms à la Reynolds & Bronstein, slips, pushes) is the *curriculum* that both trains recovery
and generates the reactions — the same perturbation-based balance training used in rehab robotics.

---

## 8. Measurement gates (no hype — this is how we know it's real)

Pre-registered, before any data:
- **G-R1 Surprise validity**: injected perturbation magnitude vs measured `r` shows monotone
  correlation (ρ ≥ pre-declared). If reactions fire without a surprise number tracking the
  perturbation, the engine is scripted — FAIL.
- **G-R2 Habituation**: on repeated identical perturbation, `r` (and startle magnitude) decays with
  a fitted curve; novel perturbation re-elevates it (PPI/dishabituation, §3.4). A flat curve = no
  learning = FAIL.
- **G-R3 Recovery is borrowed**: reaction engine emits *no* joint torques directly; all recovery
  goes through the motor primitive. Audit (wiring check) — direct torque write = FAIL.
- **G-R4 Non-fact discipline**: zero `surprise`/reaction rows in the knowledge graph; all in the
  episode/self loop. Same gate the sensory cortex already enforces.
- **G-R5 Broken-escalator replication**: reproduce the BEFORE/MOVING/AFTER protocol; measure the
  after-effect lurch and its dissipation over ≥2 AFTER trials. A qualitative match to the human
  dissociation curve is the capstone evidence.

No claim of "feels" anywhere — G2 vocabulary only (surprise magnitude, latency, decay slope).

---

## 9. Track E milestone integration (where this lives)

This is not a new track; it threads existing Track E gates ([[hyper-personal-local-agi-goal]],
embodied development track):
- **M1** (sensorimotor babbling → body-schema predictor): the forward model whose error IS surprise.
  Reaction engine v0 rides directly on M1 — no M1, no honest surprise.
- **M2** (object play → affordance): reactions to object contact/drop are the same surprise pipeline;
  affordance learning and startle share the forward model.
- **M3** (self/other): a self-caused vs externally-caused perturbation must feel different — startle
  is stronger for the unpredicted/external (self-action is predicted, hence pre-inhibited, the PPI
  of agency). Directly serves the self/other AUC gate.
- **M4** (identity integration): "I nearly fell on the stairs" becomes an autobiographical episode
  with a hormone signature — narrative + affect binding.

**Prerequisite honesty**: the reaction engine cannot be meaningfully built before M1 exists, because
without a learned forward model there is no error to be surprised by — only a hardcoded trigger,
which we forbid (§1). Sequence: E9 verdict → GPU free → Track E M0 (Isaac Sim wiring) → M1
(forward model) → **reaction engine v0 rides on M1**. Building it earlier would force the scripted
version we reject. This document is the design to execute at M1, not a green light to script now.

---

## Sources
- Reynolds RF, Bronstein AM. "The broken escalator phenomenon. Aftereffect of walking onto a moving
  platform." *Exp Brain Res* (2003). https://link.springer.com/article/10.1007/s00221-003-1444-2 ;
  https://en.wikipedia.org/wiki/Broken_escalator_phenomenon
- Trial-number effect on the broken-escalator aftereffect. https://pubmed.ncbi.nlm.nih.gov/16639502/
- Primary acoustic startle pathway (cochlear root neurons + PnC). *J Neurosci* (1996).
  https://www.jneurosci.org/content/16/11/3775 ; startle circuit lesion/stimulation:
  https://pubmed.ncbi.nlm.nih.gov/7086484/
- Amygdala modulation of prepulse inhibition via the PnC. *BMC Biology* (2021).
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8176709/
- PPI as a brainstem sensorimotor-gating hallmark. https://pmc.ncbi.nlm.nih.gov/articles/PMC7563436/
- Trip recovery: elevating vs lowering strategy by swing phase. *Exp Brain Res* (1994).
  https://pubmed.ncbi.nlm.nih.gov/7705511/ ; humanoid recovery via phase resetting / biomechanical
  simulation: http://graphics.cs.cmu.edu/projects/trip/
