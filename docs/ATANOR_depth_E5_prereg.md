# depth_learner — E5 paired capability exam, PRE-REGISTRATION

Written 2026-07-30, **before any exam data was drawn and before any of the three checkpoints was run on a
sealed set together**. Committed first so the pass condition cannot be adjusted after a number is seen.

Predecessor: `ATANOR_depth_E4_prereg.md`. E4 passed on seal 002 — net δ<1.25 0.4850 median against a
constant baseline at 0.2042 and a shuffled control at 0.3427, scored by the operator on Town15.

---

## 1. What E5 asks for that E4 did not

This repository's usage, recovered from `docs/ATANOR_G0_evidence_and_blockers.md`: E4 is an independent
functional gate; **E5 is a paired capability measurement**. One sealed exam showing an organ beats its
controls is E4. E5 requires the measurement to be *paired* — a curve across conditions rather than a point
— so that what varies is the capability and not the luck of one draw.

**The question this exam asks:** does depth learned WITHOUT LABELS transfer to a town the model has never
seen, and how much of the supervised model's transfer does it recover?

That is a capability curve with three points, and all three artefacts already exist, frozen since
2026-07-29:

```
depthnet.pt            supervised on CARLA ground-truth metres        (the E4 organ)
ordinal_selfsup.pt     ordering learned from motion, NO labels
citysample_selfsup.pt  self-supervised
```

**Why the question is worth an exam.** The whole project rests on structure learned without a teacher. If
only the supervised checkpoint transfers, then what was demonstrated at E4 is that *labels* transfer, which
is much weaker and much less interesting. If the label-free checkpoints clear the controls too, the claim
becomes that the geometry is recoverable from motion alone — and that is the claim the roadmap's
self-supervised line actually needs.

## 2. Seal

A **fresh** seal, recorded after this document is committed. Seal 002 is spent — it has produced a verdict,
so any number read off it now is diagnostic.

Material: new Town15 episodes, numbered from ep420. Town15 was never a training town and never a validation
town. The seal records `frames_postdate_checkpoint`, and the exam is VOID if that is false: a checkpoint
cannot have trained on frames that did not exist when it was written, and that is a filesystem fact rather
than a promise about anyone's restraint.

Frame floor 200 at stride 10, as in the E4 prereg. More than 5% of frames carrying no valid pixels is
INCONCLUSIVE, which counts as failure.

## 3. Roles

Unchanged from E4 and unchanged for the same reason. I may run `run`; the operator draws the seal and runs
`score`. `packages/architecture_registry` refuses any E4+ stage that does not cite a verdict carrying
`attestation: true`, a `pass`, and a named examiner, so a stage cannot be written on my say-so even by
accident.

## 4. Primary metric and pass condition — REGISTERED

Metric as in E4: `δ < 1.25` after median scaling, sky excluded, 20 samplings of 40 frames, with `AbsRel`
reported alongside.

**E5 PASS iff all four hold:**

1. **Every one of the three checkpoints** clears the constant-depth baseline: `p10(model) > p90(constant)`
   for each. A capability curve whose points are not individually above chance is not a curve.
2. **The label-free `ordinal_selfsup` clears the shuffled control**: `p10 > p90(shuffled)`. This is the
   load-bearing condition — it separates "the model reads this image" from "the model emits a plausible
   driving-scene prior", for the checkpoint that never saw a depth label.
3. **The ordering is stable across the 20 samplings**: the supervised checkpoint's median δ exceeds each
   self-supervised one's, or the difference is within the samplings' own spread. Either outcome is
   reportable; what fails is an ordering that flips between samplings, because that means the exam cannot
   resolve the three at all.
4. All four `packages/self_check` preflight checks green, **inconclusive counted as failure**.

**FAIL** if any condition fails. A FAIL is recorded and not retracted.

## 5. What a PASS would license, and what it would not

A pass licenses `depth_learner.evidence` from `E4` to **E5**, cited the same way, edited only with an
attested verdict in hand.

It would **not** license: any claim about real-world imagery, any claim about towns other than Town15, any
claim that the depth is *good* — δ<1.25 near 0.49 is a weak model that clearly beats its controls, and
published monocular work reaches 0.85+ on KITTI. The claim under test is transfer, and specifically
**label-free** transfer.

It also would not license E6, which in this repository's usage needs an external blind examiner rather than
the operator.

## 6. Void conditions

Unchanged: void if this document changes after the seal is drawn, if a checkpoint hash changes, if the
builder scores, if the seal is re-drawn after a verdict is read, or if `frames_postdate_checkpoint` is
false. A seal re-cut after seeing a result is not a seal.

## 7. Prediction, recorded before the data exists

So that the outcome is informative either way, and so I cannot claim afterwards to have expected it:

I expect `depthnet.pt` to pass conditions 1 and 2 comfortably, having already done so on seal 002. I expect
`ordinal_selfsup.pt` to clear the constant baseline and **I am not confident it clears the shuffled
control** — the shuffled arm reached 0.3427 on seal 002 against the supervised model's 0.4850, so a
label-free model has a narrow band to land in. If it fails condition 2, the honest reading is that
label-free ordering recovers scene-level depth statistics but not per-image geometry, which is a real and
publishable negative rather than a disappointment.

---

## 8. VOID — this pre-registration is mis-specified, found before any score was read

**Seal `data/e5_depth_seal_001` is void and will not be scored.** No verdict was produced from it and no
accuracy number was read off it. What voids it is a defect in §4, not in the data.

**The defect:** §4 registers `δ < 1.25` — a METRIC accuracy — for all three checkpoints, and
`ordinal_selfsup.pt` does not produce metres. Its own module says why, and said so before I wrote this
document: *"Monocular vision cannot recover metres in the first place — halving every distance and halving
the motion looks identical — so a rank is the honest form of what a single moving eye can know."* Median
scaling fixes one global multiplier; it cannot rescue a model whose output is monotone in depth but not
proportional to it.

**Caught by the units preflight**, which was added after exam 001's units bug and fired here before the
seal was spent: `ordinal_selfsup` median output 1.129, outside the 3–60 m plausible band. The guard worked.

**Verified on TRAINING episodes, with the seal untouched:**

```
depthnet.pt          Spearman rho vs true depth 0.989   median output 8.45   metres
ordinal_selfsup.pt   Spearman rho vs true depth 0.581   median output 1.10   arbitrary scale
```

The ordinal net is not broken — it produces real order, well above chance, at a scale it was never asked to
calibrate. Scoring it on δ<1.25 would have measured my metric choice, exactly as exam 001 measured my units.

**A second finding, recorded rather than folded in:** `citysample_selfsup.pt` carries `init: depthnet.pt`
and `scripts/citysample_selfsup_train.py` defaults `--init` to the supervised checkpoint. It is a
supervised model fine-tuned self-supervised, **not a label-free model**, and its number must never be read
as label-free evidence. `ordinal_selfsup.pt` is the only genuinely label-free arm —
`scripts/learn_depth_from_motion.py:134` reads `net = DepthNet().to(dev)  # RANDOM init: nothing supervised
is carried in`.

**This is the second pre-registration error of the day and it is the same family as the first.** E4's was
units, E5's is the metric; both come from registering a condition without checking what the model actually
emits. The correction for v2 is structural: **each arm is scored on the quantity it was trained to
produce**, and the prereg must state, per arm, what the model outputs before naming a metric for it.

Superseded by `ATANOR_depth_E5_prereg_v2.md`, which requires a fresh seal.

