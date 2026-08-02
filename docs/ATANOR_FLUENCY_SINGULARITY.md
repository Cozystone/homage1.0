# ATANOR Fluency Singularity — the plan to speak, without bound and without lying

Owner (2026-07-15): fluency is the most important thing — devise how to reach its *singularity*.
This is that plan, built to the honesty doctrine, not around it.

## 0. The one honest reframe (what "singularity" means here)

There is no mystical threshold. The honest, buildable version of a fluency **singularity** is a
**self-reinforcing flywheel**: the system's own *verified-fluent* speech becomes new register data,
which makes the next generation more fluent, which produces better data — **fluency compounding
without new hand-authoring**, and bounded only by (a) register coverage and (b) the grounding
invariant (it may never become fluent *lying*). We do not *claim* to have reached it. We **measure**
whether the flywheel is compounding — the naturalness curve is the scoreboard.

Two hard invariants sit above everything (BINDING):
- **발화 = 생성 아니면 침묵** (voice-or-silence): fluency is generated from grounded structure, never
  a template recital and never fabrication.
- **답한다 ≠ 지어낸다**: as fluency rises, the danger is *fluent-but-false* (the LLM failure). Every
  fluent surface stays tethered to the grounded skeleton. This is our structural edge, not a caveat.

## 1. The measured diagnosis (why we're at ~83% and flat at 0.60)

- Conversational fluency is **~83%** (measured 2026-07-10), knowledge-grounded and abstention-free.
- But quality is **flat at ~0.60** and 500→6000 corpus lines didn't move it. The root cause is
  **NOT model size** (we're No-LLM) and **NOT knowledge** (the world pack won't fix speech). It is
  **register poverty**: the 30k voice corpus is **52% encyclopedic, 2% conversational, 0% questions**
  (`packages/autonomy_kernel/register_diet.py`, `[[corpus-composition-is-the-bottleneck]]`).
  Wikipedia teaches *facts*, not *talk*. Scaling an encyclopedic corpus scales recitation, not
  fluency.

**So fluency = register coverage × discourse-pattern mastery × generation-not-template, tethered to
grounding.** The singularity is reached by turning that product into a self-feeding loop.

## 2. The four pillars — each a SHIPPED organ that needs connecting, not inventing

| Pillar | What it does | Organ (real, shipped) |
|---|---|---|
| **F1 Register acquisition** | learns *how people talk* (comfort, argue, explain, joke) from real boards — register, never facts | `autonomy_kernel/register_harvest.py`, `register_diet.py`, `register_seed.py` |
| **F2 Discourse generalization** | learns discourse patterns from real prose as reusable transforms (뼈+살), not templates; plans content→sentence→surface with an *inspectable* plan | `base_brain/discourse_learner.py`, `cgsr/discourse_planner.py`, `answer_quality/surface_feedback.py` |
| **F3 Self-play distillation** | Speaker proposes phrasings of the SAME grounded facts, a Critic scores, winning discourse patterns distil into the surface generator (offline) | `base_brain/speech_selfplay.py`, `evolution/critic_arena.py` |
| **F4 Integrity gate** | frozen-oracle Critic + a faithfulness HARD GATE so a phrasing can NEVER score high by drifting off the grounded skeleton | `evolution/critic_integrity.py` |

The organs exist. The singularity is what happens when they are wired into **one continuous,
measured, quality-gated loop** instead of four separate offline tools.

## 3. The flywheel — the singularity mechanism (quality-gated, No-LLM)

```
  F1 register_harvest ──▶ F2 discourse_learner/planner ──▶ generate (뼈+살) ──▶ F3 speech_selfplay
        ▲  (roam web, harvest        (patterns as reusable      (skeleton from graph      (Speaker vs Critic
        │   register by register)     transforms + word-choice   + register flesh)         over SAME facts)
        │                             from the lexical field)                                      │
        │                                                                                          ▼
        │                                                                            F4 critic_integrity
        │                                                                            (frozen oracle +
        │   winning patterns that RAISE blind-holdout naturalness AND keep grounding 100%           faithfulness
        └────────────────────────  fed back as new register data  ◀───────────────────────────────  HARD GATE)
```

Each turn of the wheel: harvest thin registers → generate → self-play → the Critic keeps only
phrasings that **(a) raise held-out naturalness AND (b) stay perfectly grounded** → those become
training register for the next turn. If naturalness keeps rising without new human authoring, the
wheel is **self-sustaining** = the honest singularity. Runs on the always-on autonomous daemon while
the world pack / GPU sit idle.

## 4. The two guards that keep the singularity honest (BINDING)

1. **Anti-wireheading (frozen critic).** A self-improving fluency loop's obvious failure is the
   system learning to *game its own fluency score* — inventing register that scores high but is
   gibberish. `critic_integrity.py` already closes this: a candidate Critic must agree with a
   **sealed human exam**, and cannot pass while deleting the faithfulness gate. The flywheel's Critic
   MUST be frozen-oracle-verified every turn (`[[recursive-self-improvement-plan]]`). Without this,
   the singularity produces confident nonsense.
2. **Grounding fidelity = 100%, non-negotiable.** The Critic scores *faithfulness-to-skeleton*
   alongside naturalness, and faithfulness is a HARD GATE (not a weighted term). A gorgeous sentence
   that drifts from the 뼈 is rejected outright. Fluency rises; hallucination stays at zero. This is
   the one thing an LLM cannot promise and we can.

## 5. The singularity condition — measured, not claimed

- **`register_coverage`** — distribution over registers (explain / narrate / dialogue / persuade /
  console / instruct / humor). Drive the 2%-conversation up; measure the vector, harvest where thin
  (active learning).
- **`blind_naturalness`** — a sealed holdout of human-vs-ATANOR pairs; can a judge tell? Track the
  curve turn over turn.
- **`grounding_fidelity`** — fraction of fluent surfaces fully entailed by the skeleton. Must read
  **1.00** every turn or the turn is void.
- **Singularity = `blind_naturalness` keeps rising across flywheel turns with NO new hand-authored
  data, while `grounding_fidelity` holds at 1.00.** If it plateaus, the wheel is register-starved →
  back to F1 (not a model-size problem). We publish the curve; it either compounds or it doesn't.

## 6. Build ladder L0–L5 (each measurable)

- **L0 — baseline** *(now)*: measure the corpus register distribution + `blind_naturalness` today
  (the honest 0.60 / 83% starting point). No claim without this number.
- **L1 — register active-learning**: point `register_harvest` at the *thinnest* registers (drive
  conversation/question/emotional-support up). Metric: `register_coverage` flattens toward uniform.
- **L2 — discourse transforms**: promote `discourse_learner` patterns to reusable content-independent
  transforms (acknowledge→reframe→ground→offer, etc.), applied over any skeleton via
  `discourse_planner`. Metric: `blind_naturalness` on unseen topics.
- **L3 — close the flywheel**: wire F1→F2→generate→F3→F4→back-to-F1 on the autonomous daemon, one
  quality-gated turn at a time. Metric: does turn N+1 beat turn N on held-out?
- **L4 — enforce the guards**: `critic_integrity` frozen-oracle check + faithfulness HARD GATE on
  every turn. Metric: `grounding_fidelity` == 1.00, Critic-exam agreement stable.
- **L5 — read the curve**: is `blind_naturalness` compounding (singularity) or plateauing
  (register-starved)? Publish it. Steer F1 accordingly.

## 7. What we are NOT doing (anti-hype boundary)

- Not bolting on an LLM for fluency (it buys tokens and pays with drift + hallucination — the exact
  thing we exist to avoid; `discourse_planner.py` states this).
- Not claiming a mystical threshold — "singularity" here is a *measured, self-sustaining flywheel*,
  nothing more.
- Not letting fluency outrun grounding — a fluent falsehood is a worse failure than an awkward truth.
- Not scaling the encyclopedic corpus and calling it fluency (measured dead end).

The claim is narrow and true: **fluency is a register-acquisition + self-reinforcing-generation
problem, we have every organ, and the singularity is the flywheel compounding under a frozen critic
and a 100% grounding gate — which we measure and publish.** See `[[fluency-doctrine]]`
`[[voice-or-silence-doctrine]]` `[[world-roaming-register-learning]]` `[[corpus-composition-is-the-bottleneck]]`.
