# How our eye eventually beats OWLv2 and OCR — and why not by being a better recognizer

**2026-07-30.**

> 지금은 우리가 OCR, OWLv2 등등에 지더라도 궁극적으로는 이길 방안이 필요해. 그것도 압도적 성능과 효율로.

Setting that direction honestly starts with conceding the losing route. **We will not win by being a better
feed-forward recognizer.** OWLv2 carries web-scale pretraining, and a smaller from-scratch ViT competing on
single-frame category recall loses that race for as long as it is the same race — our own numbers already
show the shape of it, the learned mask costing 20× the incumbent for worse downstream accuracy.

The win has to come from something a per-frame detector **structurally cannot have**. And the existence
proof that such a thing exists is a person: humans beat OWLv2 and OCR decisively, on 20 watts, without
web-scale labels. §4 is about what they have that a detector does not.

---

## 1. The thesis

> **We win by not being a recognizer.** A detector answers a question about an image. We maintain a
> predictive model of a world, in which recognition is a by-product and the cost is proportional to
> surprise.

That reframes the comparison. A detector's cost is flat: full frame, every frame, forever. Ours should
*fall* as the world becomes predictable — and that is a claim with a number attached.

---

## 2. The number the thesis rests on, measured

300 frames of Ms. Pac-Man, with the **cheapest possible predictor** — the previous frame:

| policy | pixels per frame | saving |
|---|---|---|
| recompute everything (what we do today) | 33,600 | 1.00× |
| recompute only where it changed | 346 | **96.9×** |
| … with a 2-pixel halo | 829 | 40.5× |
| … with a 4-pixel halo | 1,323 | 25.4× |

- **99.0% of every frame is unchanged.** 350 pixels of 33,600 move per step.
- 37.8% of frames change by under 1%.
- Holding the joystick still: 0.70% change per frame, a **144×** saving available.

**And this is the connection that matters.** The learned mask's disqualifying cost was 20×. The saving from
computing only where the world surprised us is 25–97×. So the strategy is not *"make the learned eye
cheaper per pixel"* — it is *"run it on 1–4% of the pixels"*. At that point the organ we measured as
unaffordable becomes cheaper than the hand rule that beat it.

**OWLv2 cannot do this.** A ViT needs the whole frame to produce its attention; there is no partial
forward pass over the 1% that moved. The advantage is not that our model is better — it is that a
stateful predictive system is *allowed* to skip and a stateless detector is not.

---

## 3. The four structural advantages, and which are real

| advantage | why a detector cannot have it | status here |
|---|---|---|
| **amortisation over time** | it re-derives the scene every frame. We know the same four ghosts have been present for 600 frames and do not re-detect them. | tracker + appearance identity exist; the skip does not |
| **cost proportional to surprise** | its cost is fixed by architecture. Ours can be proportional to prediction error. | measured headroom 25–97×; unwired |
| **action** | it must resolve ambiguity from one image. We can look again, move, change viewpoint. | the executor exists; no perception-driven saccade policy |
| **self-generated supervision** | it needed human labels at web scale. Action–consequence loops produce grounded labels for free, indefinitely. | `learned_signature` proves the principle (0.0% at random init → beats the colour rule); scale untouched |

The first two are efficiency; the last two are what eventually closes the accuracy gap.

---

## 4. Where we lose today — and why "forever" was wrong

An earlier draft of this section said we lose cold single-frame recognition of an arbitrary named category
"essentially forever on the data alone". **The owner pointed out the counterexample and it is decisive:
humans beat OWLv2 and OCR at exactly that task, and they do it without web-scale labels.** A person finds
an eraser in a photograph they have never seen, reads degraded handwriting that OCR cannot, and does both
on roughly 10⁴ explicitly labelled experiences and 20 watts. So the data-scale argument cannot be the whole
story, and citing it as a permanent ceiling was wrong.

**What the human advantage actually rests on is structural, and it is four things:**

| human structure | what a ViT does instead | why it generalises |
|---|---|---|
| **compositional parts** | 2-D texture statistics over a whole image | a novel eraser is recognised from parts, material and proportion, not from having seen a million erasers |
| **3-D and physical grounding** | no world; a flat pattern | viewpoint, occlusion and support are understood rather than memorised, which is where OWLv2 degrades and people do not |
| **function over form** | form only | an eraser is partly "the thing that would remove pencil" — an affordance, not an appearance |
| **definition by language** | needs examples | told "a soft block you rub on pencil marks", a person finds one immediately, from one sentence |

**Those four are precisely the four lines this project is already building.** The 4-D world model is the
second row. The image-schema basis and executor are the third. The `defined_as` graph traversal that let an
invented verb reach a goal functional from one sentence — `gorp` compiling to PROXIMITY polarity −1 and
reducing deaths at p=0.0151 — is the fourth, already demonstrated in the action line and not yet pointed at
vision.

So the honest position is stronger than the one it replaces: **we lose today because those four are not
joined, not because the corpus is out of reach.** The human existence proof says the architecture is
sufficient, and what remains is to build and connect it.

What that costs is not small, and it is the same three lines: **embodiment** supplies the intervention that
turns one view into many, **language** supplies the name and the definition, and **the executor** makes a
category useful rather than merely a label. Which is the real answer to 전체적으로 잘 결합되게 — these are
terms of one equation, and the eye's data problem is solved by the other two rather than by more images.

## 5. What would refute this

The thesis is falsifiable and the first test is cheap:

> **If wiring event-driven computation does not deliver a large measured saving on the real chain with
> accuracy held, the thesis is wrong.** The headroom is 25–97× in principle; if the chain delivers 2×, then
> the dependencies between organs are the cost and not the pixels, and the plan needs rewriting rather
> than continuing.

Two further predictions that can fail:

- cost per frame should **fall** as a scene stabilises. If it stays flat, we are a detector with extra steps.
- a category learned from acting should generalise from far fewer examples than one learned from labels
  alone. If it needs comparable data, the fourth advantage is imaginary and OWLv2 stays permanently.

---

## 5a. REFUTED IN PART, 2026-07-30, by its own registered test

F2 was run and the condition in section 5 fired. Recorded here rather than left for a reader to discover.

    cheap organ (subtraction)     pixels 35.9x fewer   wall clock 0.51x -- SLOWER
    expensive organ (learned)     pixels  8.7x fewer   wall clock 3.38x
    learned mask vs incumbent     was 68x, event-driven makes it 20.2x -- still unaffordable

**The 25-97x headroom does not convert to wall clock.** Fixed overheads -- change detection, dilation,
fancy indexing, kernel launches -- eat most of it, and on the cheap organ they exceed the work saved
outright. A numpy subtract-and-compare over 33,600 pixels costs 0.28 ms; deciding which 965 of them to
recompute costs more than doing all of them.

**And my first implementation was worse than wrong, it was flattering.** It counted the pixels it claimed
to skip while still calling  on the whole frame and merging the result. The 936 px/frame
figure was a projection of work avoided, not a measurement of work done, and the wall clock is what caught
it.

WHAT SURVIVED, and it is not nothing:
    accuracy held EXACTLY -- 64.8% -> 64.8% on the body criterion
    surprise beats random skipping at the same rate, 64.8% against 0.0%, so the selectivity is real even
      where the saving is not
    3.38x on the expensive organ, which is the direction being right and the magnitude being wrong

THE REVISION THIS FORCES. All three human savings mechanisms -- foveation, saccades, event-driven
recomputation -- pay in proportion to frame size and scene stability, and 160x210 is too small for any of
them: foveation gave 2.43x where a large frame gave 112x, and event-driven gives 3.4x where the pixel
arithmetic promised 25-97x. **So efficiency claims move to the large-frame domain and Atari stays as the
accuracy testbed.** F2 is not the load-bearing rung it was promoted to be; F3, measured where frames are
large, is.

## 6. Order, unchanged in substance and now motivated

`ATANOR_eye_efficiency_plan_2026-07-30.md` set F1–F5. This document changes only why:

- **F1 benchmark OWLv2 and OCR** — still first, because "압도적" needs a baseline and there is none yet.
- **F2 event-driven perception** — now the load-bearing rung, not merely an optimisation. It is what makes
  the learned organs affordable, and it is the thesis's own test.
- **F3 foveation and saccades** — where frames are large, driven by prediction error.
- **F4 cheap learned organs** — largely subsumed by F2: 1% of pixels is the fix, not a smaller net.
- **F5 categories** — gated on F1, and reachable only through embodiment and language, per §4.

---

## 7. What this document may not be used to claim

The 99%-unchanged figure and the 25–97× headroom are measured on 300 Atari frames on this machine with a
previous-frame predictor. Everything else is a plan. **OWLv2 has not been benchmarked**, no saving has been
realised on the real chain, and the claim that ATANOR's eye beats anything on efficiency is not available
today — the one place it was measured, it lost by 20×.
