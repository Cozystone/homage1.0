# SPLATRA embodiment track — the Isaac bypass (Track E on our own substrate)

Owner directive (2026-07-19): Isaac Sim M0 is blocked (Blackwell RTX renderer incompat, confirmed by
NVIDIA's own compatibility checker crashing). Pivot Track E onto SPLATRA. Two repos supplied for reuse:
depth-anything.cpp and FaceAnything. Core question: **can SPLATRA deliver the same effect as Isaac Sim?**

This document answers that honestly and redefines Track E M0/M1 with zero Isaac dependency.

---

## 1. The honest comparison — Isaac Sim and SPLATRA are different KINDS of tool

| | Isaac Sim (Omniverse) | SPLATRA (ours) |
|---|---|---|
| What it is | An accurate **physics simulator**: given a scene, simulate rigorous rigid-body/articulation dynamics (PhysX 5) + exact sensors | A **generative imagination + spatial-reconstruction** engine: synthesize a body/scene from a concept's graph structure, rebuild a perceived room, measure what context survives |
| Physics | PhysX 5 — accurate contact, friction, joints; sim-to-real grade | **PBD** (position-based dynamics) — fast, visually plausible soft-body/contact; NOT rigid-body-accurate |
| Sensors | Ray-traced cameras (ground-truth depth/seg), IMU, contact/force | Rendered particle scene + our perception lane; depth via depth-anything.cpp (below) |
| Motor | Isaac Lab RL locomotion policy (trained G1) | Rig + FK + skinning + hormone→rig intent (procedural, not a trained locomotion policy) |
| Dependency | NVIDIA RTX + CUDA + driver (← the blocker) | **Ours. No external RTX/driver dependency.** CPU-viable |
| Unique power | Physical fidelity, sim-to-real transfer | **Generation** — it can IMAGINE a body/scene the concept implies, not only simulate a given one |

**Key insight: these are not competitors for the same job.** Isaac SIMULATES a given world with high physical
fidelity. SPLATRA GENERATES and REBUILDS worlds from concepts and perception. The right question is not
"which is better" but **"which one does Track E's actual job need?"**

## 2. What Track E's job actually is (doctrine) — and therefore what it needs

Track E's north star is **the developmental self**, not robot control. The charter is explicit
([[track-e-embodiment-promoted]], embodied_development_track): **운동 = 빌린 기관, 자아 = 그래프**; the
destination is the sim body itself, so **sim-to-real fidelity is out of scope** ("sim2real 갭은 현
단계 무해"). The self-formation loop is:

    act → forward-model predicts next sensory state → measure prediction error → surprise/hormone → graph write

This loop needs a body that (a) **moves**, (b) **produces sensor streams** (proprioception, contact, vision),
and (c) **generates prediction errors** when the world deviates from the learned forward model. It does
**not** need PhysX-accurate contact dynamics — it needs the self to learn *its own body's* dynamics,
whatever they are. The reaction engine ([[../docs/ATANOR_reaction_engine_research]]) computes surprise as
forward-model error over ANY sensor stream — PBD or PhysX, it is agnostic.

## 3. The verdict — "아이작심 만큼의 효과?"

**For the effect Track E actually pursues (the cognitive/developmental self): YES, SPLATRA is sufficient,
and in three ways it is a better fit for our goal:**
1. **It removes the external blocker** — no RTX/driver dependency; depth-anything.cpp runs on CPU.
2. **Half the pipeline is already SHIPPED on SPLATRA**: generative body (`splatra_imagination/generative.py`),
   structural forms (`imagination/splatra_cloud.py`), spatial-memory replay (`perception/spatial_memory.py`),
   the semantic-bottleneck autoencoder (`perception/reconstruction_loss.py`) — plus the sensory cortex
   (shipped today) and hormone dynamics. The self-formation loop drops onto these with no simulator to boot.
3. **Generation matches a *developing* self better than pure simulation** — a self that imagines, predicts,
   and rebuilds is exactly what SPLATRA is (an imagination compiler); Isaac can only step a given scene.

**For the effect Track E deliberately deprioritized: NO, SPLATRA does not match Isaac, and we must say so
plainly:**
- **Physical fidelity** — PBD ≠ PhysX. A "stumble on the stairs" in SPLATRA is plausible, not physically
  exact. Surprise is measured against an *approximate* world; the self learns a self-consistent but
  not physically-canonical body. Acceptable for cognition, not for physics research.
- **Sim-to-real transfer** — none. But we do not need it (charter).
- **Trained locomotion RL** — no Isaac Lab G1 policy. The motor organ is procedural (rig/FK + hormone
  intent), not a learned controller. This is the real gap; §5 addresses it.

**Bottom line: SPLATRA gets us the developmental self (Track E's real deliverable) with no blocker; it does
not get us physics-grade robotics — which the charter already put out of scope.** Isaac rejoins LATER, after
a driver fix, purely as the physics-accurate **locomotion organ** (a borrowed motor), while SPLATRA stays the
self/imagination substrate. Not either-or — a clean split of duties (exactly our Type-2 doctrine).

## 4. Repo reuse — honest, licensed, blocker-aware

- **depth-anything.cpp** (MIT code / Apache-2.0 weights; C++/ggml; **CPU, no CUDA**; quant to 99 MB):
  **integrate as the vision→3D bridge.** Single image → dense metric depth + camera pose + 3D point cloud
  (PLY). This is the perceptual grounding SPLATRA needs and it **runs around the Blackwell GPU block** (CPU
  inference). Wiring: it feeds `perception/spatial_memory.py` (depth → object positions → SPLATRA scene) and
  gives the body a real depth/vision sensor stream for the forward model. MIT = commercially safe. **1st
  integration target.**
- **FaceAnything** (**CC-BY-NC 4.0 — NON-COMMERCIAL**; PyTorch/CUDA; **15 GB** ckpt): 4D facial geometry from
  video. **License blocks product use — research/reference only, never shipped.** It also needs CUDA (Blackwell
  block persists) and 15 GB. We already have face identity via DeepFace ([[visual-cortex-face-v0]]). Verdict:
  **do NOT integrate into the product**; keep as a research reference for the face-reconstruction technique
  only. Flag recorded so no one wires an NC-licensed 15 GB CUDA model into the local AGI by accident.

## 5. Track E redefined on SPLATRA (no Isaac) — M0s → M5s

| stage | on SPLATRA | gate (pre-declared) |
|---|---|---|
| **M0s** environment | SPLATRA body (generative rig) + sensor taps: proprioception = rig joint state; contact = PBD collision; vision = rendered scene → depth-anything.cpp depth; episode logger | cold-boot → control round-trip reproduced; sensory cortex ingests all 4 modalities as Percepts |
| **M1s** babbling | random/curious rig motion → learn body-schema forward model (predict next rig+sensor state) | fingertip/joint prediction-error convergence curve (pre-declared baseline); generalize to unseen pose |
| **M1s+** reaction | reaction engine rides M1s forward model — surprise = prediction error over PBD/vision streams | surprise ∝ injected perturbation (G-R1); habituation curve (G-R2) — same gates as the reaction doc |
| **M2s** affordance | rig interacts with SPLATRA objects (grasp/push/drop) → sensorimotor evidence triples to graph | manipulation success + reproducible affordance triples |
| **M3s** self/other | self-caused (predicted) vs external (unpredicted) rig perturbation — agency PPI | self/other AUC ≥ pre-declared |
| **M4s** identity | rig experience → Genesis ledger + hormone signature; autobiographical episodes | narrative-consistency battery |
| **M5s** curriculum | developmental stages (reach→grasp→stack) + D3 curiosity intrinsic motivation | stage-graduation gates + transfer |

**Motor-organ note (the honest gap from §3):** without Isaac Lab's trained G1 policy, M0s–M2s use a
procedural motor (rig/FK + hormone intent + PBD). That is enough for the self-formation gates (they measure
prediction error and self-attribution, not gait quality). A *trained* locomotion policy is deferred to the
Isaac-rejoin phase (post driver-fix), or approximated by our own rig-prediction learner if we want it sooner.

## 6. Guardrails carried over (unchanged)
- **G1** VLM = retina not brain: depth-anything/DeepFace are perception sensors; their output enters the
  graph only as structured perceptual triples through the sensory cortex's evidence gate, never as asserted
  knowledge. NC-licensed models (FaceAnything) never ship.
- **G2** consciousness = measured correlates, never a claim (self/other AUC, prediction-error curves,
  narrative consistency, metacognitive calibration).
- **G3** resource discipline: SPLATRA/PBD is CPU/GPU-light; depth-anything.cpp is CPU. No operator GPU slot
  needed to start (unlike Isaac) — the pivot's practical win.

## 6.5 dimos (dimensionalOS) assessment + the MuJoCo find (2026-07-19)

Owner supplied https://github.com/dimensionalOS/dimos — "the agentic OS for physical space": a
generalist robotics framework (Unitree Go2/B1/**G1**, arms, drones; SLAM/nav/obstacle-avoidance;
perception; spatial memory) with a **MuJoCo** simulation backend.

**Charter verdict — do NOT adopt dimos wholesale.** Its agent/reasoning layer is **LLM-based** (MCP +
cloud/Ollama). That is the exact opposite of our north star (No LLM/sLLM; knowledge lives in the
graph, not weights). The self, reasoning and knowledge stay ATANOR's — never borrowed from an LLM OS.

**But one component changes the embodiment picture: MuJoCo.** MuJoCo (DeepMind, **Apache-2.0**) is a
rigorous rigid-body / contact / articulation physics simulator that has **NO RTX-renderer dependency**
— so it runs on this Blackwell box where Isaac's Kit/RTX renderer crashes. It fills the one honest gap
of §3 (SPLATRA's PBD is not physics-accurate) and is a **second, cleaner Isaac bypass**.

**Verified on this box (2026-07-19):** `pip install mujoco` (3.10.0) then a box dropped from z=1.0
came to rest at z=0.100 on the floor via genuine contact dynamics — CPU, no RTX, no crash. The
rigorous-physics body Isaac promised but could not boot, we now have. The Unitree **G1** model ships
in MuJoCo Menagerie (Apache-2.0), so the humanoid body is available without Isaac or dimos.

**Revised embodiment architecture (Type-2, three replaceable organs; cognition never borrowed):**
- **Cognition / self** = ATANOR graph + sensory cortex + reaction engine (ours, No-LLM). Immutable.
- **Self-formation substrate** = SPLATRA (generative body + imagination). M0s/M1s green (CPU).
- **Rigorous-physics body (borrowed organ)** = **MuJoCo + G1** (Apache-2.0, no RTX). For physics-grade
  affordance/contact/locomotion where SPLATRA's PBD is too soft. Optional, higher-fidelity lane.
- **Rejected**: dimos's LLM/MCP agent-reasoning (north-star violation). Borrowable later as reference:
  its SLAM/nav skills as motor organs (never its cognition), if a real robot ever enters scope.

Net: the same embodiment M0s→M5s gates run on SPLATRA (self) and, for physics fidelity, on MuJoCo+G1 —
BOTH bypass the Isaac RTX blocker, and neither imports an LLM into the cognition. Isaac itself becomes
redundant unless a specific Omniverse-only asset is needed later.

## 7. First action
M0s smoke: verify `splatra_imagination.generative` synthesises a body, tap rig joint state as proprioception
Percepts, and run one forward-model prediction step — the SPLATRA analogue of the Isaac headless-boot gate,
with no renderer to crash. depth-anything.cpp integration follows as the vision sensor.
