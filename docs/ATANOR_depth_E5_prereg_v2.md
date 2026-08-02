# depth_learner — E5 paired capability exam, PRE-REGISTRATION **v2**

Supersedes `ATANOR_depth_E5_prereg.md`, which was voided before any score was read because it registered a
metric accuracy for a model that only produces order. Written 2026-07-31, **before the v2 seal exists**.

---

## 1. What each arm actually emits — stated FIRST, before any metric is named

This section exists because both pre-registration errors today came from the same place: naming a condition
without checking what the model puts out. E4's was units (the head emits log depth, the runner stored it
raw). E5 v1's was the metric (δ<1.25 for a net that has no metres). So the outputs come first now, and each
metric is chosen to match one.

| arm | init | trained on | **emits** | verified |
|---|---|---|---|---|
| `depthnet.pt` | random | CARLA ground-truth **metres** | metric depth | median 8.45 m on train, Spearman ρ 0.989 |
| `ordinal_selfsup.pt` | **random — no supervision carried in** | consecutive frames only, **no labels** | **order, arbitrary scale** | median 1.10, Spearman ρ 0.581 |
| `citysample_selfsup.pt` | **`depthnet.pt`** | self-supervised fine-tune | metric depth | median 3.52 m on the seal |

Sources: `scripts/learn_depth_from_motion.py:134` (`net = DepthNet().to(dev)  # RANDOM init: nothing
supervised is carried in`); `scripts/citysample_selfsup_train.py:118` (`--init` defaults to `depthnet.pt`).
The ρ figures are from **training** episodes, computed while the v1 seal sat untouched, to establish that
the ordinal net produces real order rather than noise.

**`citysample_selfsup.pt` IS NOT A LABEL-FREE MODEL.** It starts from supervised weights. Its number may be
reported but must never be read as evidence about learning without labels. **`ordinal_selfsup.pt` is the
only label-free arm**, and the claim this exam exists to test rests on it alone.

## 2. The question

Does depth learned **without any labels** transfer to a town the model has never seen, and how much of the
supervised model's transfer does it recover?

If only the supervised checkpoint transfers, E4 demonstrated that *labels* transfer — weaker, and not the
claim the project's self-supervised line rests on.

## 3. Metric, per arm, matched to what it emits

- **Metric arms** (`depthnet`, `citysample_selfsup`): `δ < 1.25` after median scaling, sky excluded — as in
  E4, unchanged.
- **Ordinal arm** (`ordinal_selfsup`): **Spearman rank correlation** between predicted and true depth over
  valid pixels. Scale-free by construction, which is exactly the property that makes it the right
  instrument for a net that was never asked to calibrate a scale.

Both are computed over 20 independent samplings of 40 frames, and the decision is on the 10th percentile
against the control's 90th, as in E4 — because the instrument was measured to be unstable across samplings
and a point estimate would be a coin flip.

## 4. Controls, per arm

- **constant depth** at the sealed set's median — the trivial predictor. Its Spearman ρ is 0 by
  construction, so for the ordinal arm the informative control is the next one.
- **shuffled**: each arm's own predictions paired with the WRONG frames. This is the load-bearing control
  for the ordinal arm: a net that has learned the average layout of a street will still correlate with
  depth on a frame it never saw, and shuffling is what separates that from reading the image in front of it.
- **true depth** reported as the ceiling, not a control.

## 5. PASS conditions — REGISTERED

**E5 PASS iff all four hold:**

1. **Both metric arms** clear the constant baseline on δ<1.25: `p10(model) > p90(constant)`.
2. **The label-free `ordinal_selfsup` clears its shuffled control on Spearman ρ**:
   `p10(ρ_real) > p90(ρ_shuffled)`. **This is the load-bearing condition.** It is the whole question:
   does a net trained with no labels read *this image*, or does it emit a generic street prior?
3. **The ordering across arms is stable across the 20 samplings** — reported, and an ordering that flips
   between samplings fails, because it means the exam cannot resolve the arms at all.
4. All four `packages/self_check` preflight checks green, **inconclusive counted as failure**.

**FAIL** if any fails. A FAIL is recorded and never retracted.

## 6. Seal

A **fresh** seal recorded after this document is committed. `e5_depth_seal_001` is void and will not be
scored. Material: new Town15 episodes from ep440. Floor 200 frames at stride 10; more than 5% of frames
with no valid pixels is INCONCLUSIVE = FAIL.

The seal must record `frames_postdate_checkpoint: true`, and every arm's `predates_the_frames` must be true
— a checkpoint cannot have trained on frames that did not exist when it was written, and file mtimes make
that checkable without trusting anyone.

## 7. Roles and void conditions

Unchanged. I may run `run`; the operator draws the seal and runs `score`. Void if this document changes
after the seal is drawn, if a checkpoint is written after the frames, if the builder scores, or if the seal
is re-drawn after a verdict is read.

## 8. Prediction, recorded before the seal exists

I expect both metric arms to clear condition 1 — `depthnet` did on seal 002, and `citysample_selfsup`
starts from it.

**On condition 2 I expect a FAIL and I am recording it so the outcome is informative either way.**
`ordinal_selfsup` reaches Spearman ρ 0.581 on the towns it TRAINED on, against the supervised net's 0.989.
A model that weak on its own training distribution has little margin left for an unseen town, and its
shuffled control will carry real signal because street layouts repeat. If it fails, the honest reading is
that label-free ordering recovers the statistics of streets but not the geometry of a particular one — a
real negative that tells the self-supervised line exactly where it stands, which is worth more than a
number I was confident about in advance.

---

## 9. RESULT — **E5 FAIL**, and the registered prediction was right

Sealed and scored 2026-07-31 by the operator on `data/e5_depth_seal_002` (225 frames, 8 Town15 episodes,
frames postdate the freeze). Verdict: `data/e5_depth_seal_002/verdict.json`.

```
arm                     metric     init          real p10   median  shuf p90  const p90
depthnet.pt             delta125   random          0.5045   0.5268    0.4355     0.2410
ordinal_selfsup.pt      spearman   random          0.2757   0.3094    0.3148    -0.0194
citysample_selfsup.pt   delta125   depthnet.pt     0.1472   0.1506    0.1570     0.2181

1  both metric arms clear constant     FAIL   (citysample_selfsup does not)
2  LABEL-FREE arm clears its shuffled  FAIL   (0.2757 vs 0.3148)      <- load-bearing
3  arms resolve                        pass
4  preflight all green                 FAIL   (resolution 1.96x, needs 2x)
VERDICT                                FAIL
```

**THE FAIL IS RECORDED AND NOT RETRACTED.** Three findings sit inside it, and they point in different
directions.

### 9a. The E4 result REPLICATED on a fresh seal

`depthnet` reaches 0.5268 here against 0.4850 on the E4 seal, clearing both its controls
(p10 0.5045 > shuffled p90 0.4355 > constant p90 0.2410). Different frames, different weather draw, same
conclusion. A single sealed exam is a data point; two independent seals agreeing is the beginning of a
result. **E4 stands and is now stronger than when it was granted.**

### 9b. The label-free arm does NOT transfer — as predicted, in writing, before the seal existed

`ordinal_selfsup` reaches Spearman ρ 0.3094 against its own shuffled control at 0.2914. Applying its
predictions to the WRONG frames scores almost as well as applying them to the right ones. On a town it has
never seen, it is reading the statistics of streets rather than the geometry of this one.

§8 of this document, committed before the seal was drawn, said exactly this and said why: ρ 0.581 on the
towns it TRAINED on leaves little margin, and street layouts repeat so the shuffled control carries real
signal. **A correct prediction of failure is worth more than a number I was confident about**, and it is
the reason the prediction was registered.

**This is the honest position of the self-supervised line**: motion alone, from random initialisation, at
this scale and this training budget, recovers scene-level depth statistics and not per-image geometry.

### 9c. UNEXPECTED — self-supervised fine-tuning destroyed a working model

`citysample_selfsup` starts from `depthnet.pt`, which scores 0.5268 here. After self-supervised fine-tuning
on City Sample it scores **0.1506, below the constant baseline of 0.2181** — worse than predicting one
number everywhere. This is catastrophic forgetting, and nothing in the exam was designed to find it; it
fell out of running the arms side by side.

It also means `data/depth_learner/proofs/citysample_selfsup.json` and anything resting on that checkpoint
need re-reading: whatever it gained on City Sample, it lost CARLA entirely.

### 9d. What does not change

`depth_learner.evidence` stays **E4**. E5 is not granted. The registry is untouched.

