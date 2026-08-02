# depth_learner — E4 sealed exam, PRE-REGISTRATION

Written 2026-07-30, **before any exam data was drawn**. Committed first so that the pass condition cannot
be adjusted after a number is seen. If any line below is changed after the seal is opened, the exam is void
and must be re-run on a fresh seal.

---

## 1. What is being claimed, and what is not

**Claim under test:** the monocular depth `depth_learner` learned on CARLA transfers to scenes it was never
trained on, measured against ground truth, by an evaluator who did not build it.

**Not claimed:** metric depth in City Sample (no ground truth exists there), general 3D understanding,
any capability outside driving-camera imagery, or anything about the other 143 organs.

## 2. Why this needs an exam at all — the existing evidence is M3, not E4

`data/depth_learner/proofs/citysample_transfer_verdict.json` already reports a real result: derotated flow
agreement ρ 0.283 on City Sample against a random control of −0.006, 54 of 61 pairs, p = 2.16e-10, with the
instrument validated on CARLA ground truth first (true 0.629 / net 0.683 / random 0.0014 / constant 0.0).

That is a good measurement and it is **M3**, because I wrote the harness, chose the data, and read the
result. A small p-value produced by the builder is a controlled test, not an independent one. E4 requires an
evaluator who is not the builder and a holdout the builder did not select.

## 3. The threat this exam must control, named from the existing proof's own caveats

The proof records: *"the two City Sample runs disagree more than sampling alone explains (travel2 read
0.187 in one sampling and 0.252 in another), and higher parallax did not give a higher score, which is
unexplained."*

**The instrument is unstable across samplings, and nobody knows why.** A single sealed run could therefore
land anywhere across that spread, so a pass condition on a point estimate would be a coin flip dressed as a
certificate. This exam therefore:

- runs **N = 20 independent frame samplings** of the sealed set, and
- puts the pass condition on the **10th percentile** of the resulting distribution, not its median, and
- requires the net's p10 to clear the strongest trivial baseline's **p90** — the distributions must not
  overlap at all.

## 4. Roles, and why they cannot be merged

| role | who | may see |
|---|---|---|
| builder | Claude (me) | the frozen checkpoint, the runner, this document. **Never the sealed answers.** |
| examiner | the operator, or an SBC running developer-blind (the MSH pattern) | everything, including answers |
| scorer | `scripts/depth_e4_exam.py score`, executed by the **examiner** | predictions + answers. Imports nothing from `packages/depth_learner`. |

I cannot open the seal, cannot score, and **cannot write the result into the registry** —
`packages/architecture_registry/tests/test_registry_is_enforced.py` fails if any organ carries an E4+ stage,
and amending that test is a deliberate act with the refs cited, not a side effect of a good number.

## 5. The seal

The examiner selects the sealed episode set **by their own rule** and does not disclose it to me. The corpus
is `D:\carla\episodes` (47 episodes, town metadata in each `ep*/meta.json`).

### 5a. AMENDMENT — 2026-07-30, before any seal was drawn

The first version of this section excluded `VAL_TOWNS` from seal material because "the builder knew which
towns were held out". **That reason was wrong.** The risk E4 controls is not that the builder KNEW the split,
it is that the builder CHOSE it to flatter a result. `VAL_TOWNS = ("Town06", "Town07")` and
`VAL_EPISODE_FRACTION = 0.15` are code constants fixed before training and before any transfer number
existed, so they cannot have been chosen to fit an outcome. Excluding them was also not survivable: the
never-trained pool is only 9 episodes and 2,640 frames, and there is no other unseen material.

This amendment is made while **no seal exists**. Amending after a seal is drawn voids the exam (§9); making
the rule right before drawing is the opposite of that.

**The never-trained pool, computed from `build_split` (deterministic, seed 7, fixed in code):**

```
val_town      ep030 (Town06), ep034 (Town07)                          600 frames
val_episode   ep000 ep038 ep120 ep122 ep203 ep300 ep302             2,040 frames
TOTAL         9 episodes                                            2,640 frames
```

**And the subset question dissolves at this pool size.** `--from-secret` was added to keep the draw out of
the builder's hands, then measured: with nine episodes and a 200-frame floor it takes EIGHT of nine whatever
passphrase is used, and two different secrets differed by a single episode. A passphrase that changes one
ninth of the seal is the appearance of independence, not independence.

So the registered draw is **`--all-unseen`: the entire never-trained pool**. That is strictly stronger,
because there is no subset for anyone to have chosen -- not the builder, not a passphrase, not the examiner.
`--from-secret` stays in the kit for when the corpus is large enough for a subset to carry information.

What independence then rests on, all three enforced rather than promised:
1. the frames were never trained on -- `build_split`, seed fixed in code before training
2. the builder cannot read the answers -- `RgbOnly` raises `PermissionError` on `depth_m` / `depth` /
   `semantic`, so the runner has no path to ground truth
3. the builder does not score -- `score` is the examiner's command, imports nothing from
   `packages/depth_learner`, and voids the exam on any hash mismatch

Frozen artefacts, dated 2026-07-29, unchanged after this document is committed:

```
D:\carla\depth_model\depthnet.pt            supervised on CARLA metres
D:\carla\depth_model\ordinal_selfsup.pt     ordering learned from motion, no labels
D:\carla\depth_model\citysample_selfsup.pt  self-supervised
```

The runner records a SHA-256 of the checkpoint it loaded. A verdict whose checkpoint hash differs from the
one recorded here at seal time is void.

## 6. Primary metric and pass condition — REGISTERED

**Primary:** `delta < 1.25` — the fraction of valid pixels whose predicted depth is within 25% of true
depth, after median scaling (monocular depth carries no absolute scale; `packages/depth_learner/model.py`
already computes the median-scaled variant). Sky is excluded from valid pixels, as `data.load` does.

**PASS iff all four hold:**

1. `p10(delta<1.25 | net)` > `p90(delta<1.25 | constant-depth baseline)` across the 20 samplings
2. the same ordering holds for `AbsRel` in the opposite direction (lower is better), so the verdict does not
   rest on one metric's quirk
3. `p10(delta<1.25 | net)` > `p90(delta<1.25 | shuffled-prediction control)` — the net must beat its own
   predictions applied to the wrong frames
4. every one of the four `packages/self_check` preflight checks is green, with **inconclusive counted as
   failure**

**FAIL** if any condition fails. **INCONCLUSIVE = FAIL**: if the seal yields fewer than 200 valid frames, or
the checkpoint hash does not match, or the loader raises, the exam has failed and a fresh seal is required.

## 7. Baselines, and why these ones

- **constant depth at the sealed set's median** — the strongest trivial predictor in monocular depth, and
  the one that exposes a model that has only learned the depth prior of driving scenes rather than the
  scene in front of it.
- **shuffled predictions** — the net's own outputs paired with the wrong frames. This separates "the model
  reads this image" from "the model emits plausible depth maps".
- **true depth** is reported as the ceiling for context. It is not a control: on `delta<1.25` it is 1.0 by
  construction.

## 8. What a PASS would and would not license

A pass licenses exactly one registry edit, made by the examiner and not by me: `depth_learner.evidence` from
`V0` to **E4**, citing the sealed manifest hash, the prediction hash, the verdict file, and the examiner's
identity. It licenses **no E5 claim** — E5 in this repository's usage additionally requires a paired
capability curve and a hidden holdout maintained across runs, and one sealed exam is not that.

A fail licenses nothing except the record that it failed, which is kept.

## 9. Void conditions

Restating, because this is the part that protects the result from me: the exam is void if this document
changes after the seal is drawn, if the checkpoint hash changes, if the builder sees the answers, if the
scorer is run by the builder, or if the seal is re-drawn after a verdict is read. A seal re-cut after seeing
a result is not a seal.

---

## 10. EXAM 001 — FAIL, recorded permanently

Sealed 2026-07-30 by the owner with `--all-unseen`: 9 episodes, 264 frames, answers
`sha256 7e373287145b18bb…`, checkpoint `03a4e037a9a9fed8…`, predictions `6cc39ae27020f6c6…`,
scored by the owner. Verdict file: `data/e4_depth_seal_001/verdict.json`.

```
arm           delta<1.25 p10    median       p90   AbsRel med
net                   0.1902    0.2087    0.2248       0.7437
constant              0.1708    0.1924    0.2131       0.9108
shuffled              0.1792    0.2020    0.2178       1.0302
true                  1.0000    1.0000    1.0000           --

1  net p10 > constant p90    FAIL   (0.1902 vs 0.2131, overlapping)
2  AbsRel agrees             pass   (0.744 < 0.911)
3  net p10 > shuffled p90    FAIL   (0.1902 vs 0.2178, overlapping)
4  preflight all green       FAIL   (resolution: effect is 1.59x the noise, needs 2x)
VERDICT                      FAIL
```

**WHAT IT MEASURED WAS MY HARNESS, NOT THE MODEL, AND THE FAIL STILL STANDS.** `DepthNet.forward`
returns LOG depth — the code says so in a comment, and `model.metrics` opens with
`p = torch.exp(pred_log)`. The runner stored the raw head output and `score` read it as metres. Median
scaling hides that at the median pixel and destroys it everywhere else, which is exactly the shape of the
result: δ near 0.21, and a shuffled control almost tied with the net because log-space compression makes
every frame's map look alike once rescaled.

Proof that does not depend on the score: the stored per-frame medians were 0.128–2.950, which as metres
would put an entire street inside three metres. `exp` of them is 1.14–19.11 m, against this corpus's 8.7 m
constant baseline.

**The failure is recorded and not retracted.** Exam 001 failed. What failed was the instrument, and an
instrument defect found after the seal was opened does not convert into a pass.

**The seal is spent.** I have seen arm-level numbers from it, so re-scoring seal 001 — even with a fix that
uses no information from the result — would be reading a second number off a seal I have had feedback
about. That is the mechanism a seal exists to block. Any rescore of 001 is labelled DIAGNOSTIC and can
never be an E4 attestation.

**Fixed for exam 002:** the runner now applies `exp` and clamps to `[0.5, 200]` exactly as `metrics` does,
and a UNITS PREFLIGHT refuses to write predictions whose median falls outside 3–60 m. Before the seal was
spent I checked that predictions were non-degenerate and never that they were in the right units; that gap
is now closed in code rather than in intention.

E4 for `depth_learner` therefore remains **unclaimed**, and the registry still reads V0.

### 10a. The diagnostic rescore of seal 001 — strong, and not an attestation

With the units bug fixed, the same spent seal rescored:

```
arm           delta<1.25 p10    median       p90   AbsRel med
net                   0.5549    0.6103    0.6540       0.2933
constant              0.1708    0.1924    0.2131       0.9108
shuffled              0.3223    0.3458    0.4032       0.7484
true                  1.0000    1.0000    1.0000           --

1  net p10 > constant p90    pass   (0.5549 vs 0.2131)
2  AbsRel agrees             pass   (0.293 vs 0.911)
3  net p10 > shuffled p90    pass   (0.5549 vs 0.4032)
4  preflight all green       pass   (resolution 8.15x the unit, discriminator lift +0.4179)
```

All four registered conditions hold, with wide non-overlapping margins, and the shuffled control is now
clearly beaten (0.346 median against the net's 0.610) — the model reads the image rather than emitting a
generic driving-scene prior. On never-trained towns.

**This is still not E4, and the reason is not that the fix is suspect.** `exp` is fixed by the model's own
definition and uses no information from the result; I can defend that single change. The reason a seal is
single-use is different: once feedback flows, the number of "fixes" I could have tried is unbounded, and I
would have stopped at whichever one passed. Even having stopped at the first, the process is no longer
blind, and no outside reader can distinguish one honest fix from the seventh attempt. That is the whole
function of a seal, and it does not weaken because the number came out well.

**What it does license:** spending the owner's time collecting fresh CARLA episodes for a real exam 002. On
the failed run that would have been a waste; on this evidence it is justified.

**A TOOL DEFECT FOUND HERE AND FIXED.** This diagnostic run OVERWROTE `verdict.json`, replacing the recorded
FAIL with a pass. For a while the only surviving trace of exam 001's failure was a git commit message. An
artefact recording a failure must never be silently swapped for one recording a pass. `score` now writes
`verdict_diagnostic_NNN.json` when a verdict already exists, refuses to print "E4 PASS" on a spent seal, and
stamps `attestation: false`. The FAIL verdict has been restored to `verdict.json`.

`depth_learner.evidence` remains **V0**.

---

## 11. EXAM 002 — **E4 PASS**. The first capability-stage evidence in this repository.

Sealed and scored 2026-07-30 by the owner. Verdict: `data/e4_depth_seal_002/verdict.json`.

```
arm           delta<1.25 p10    median       p90   AbsRel med
net                   0.4563    0.4850    0.5151       0.3430
constant              0.1926    0.2042    0.2266       0.7972
shuffled              0.3136    0.3427    0.3866       0.6213
true                  1.0000    1.0000    1.0000           --

1  net p10 > constant p90    PASS   0.4563 vs 0.2266
2  AbsRel agrees             PASS   0.343 vs 0.797
3  net p10 > shuffled p90    PASS   0.4563 vs 0.3866
4  preflight all green       PASS   resolution 8.36x, discriminator lift +0.2808
VERDICT                      E4 PASS
```

**WHY THIS ATTESTS AND EXAM 001'S RESCORE DID NOT.** Every link is checkable without trusting the builder:

```
checkpoint frozen            2026-07-29T13:08:16
pre-registration committed   2026-07-30T19:09:27   conditions fixed before the data existed
exam data created            2026-07-30T23:18:18   the model provably never trained on it
```

Town15 was never in training and was never a validation town, across eight weather conditions. The seal had
produced no prior verdict (`attestation: true`, `seal_spent_before_this_run: false`), and the examiner is the
operator, not me. Answer, prediction and checkpoint hashes all match the manifest.

**ONE FRAME WAS EXCLUDED AND IT IS RECORDED.** Of 252 sealed frames, one had zero valid pixels -- depth
uniformly 1000 m, the sky sentinel everywhere. It is uninformative for every arm equally, so it is dropped
from all of them, the count is printed, and more than 5% would be INCONCLUSIVE, which counts as failure.
Exam 002's first scoring run returned nan for everything because of that single frame; that failure was
arithmetic, produced no model numbers, and so did not spend the seal.

**WHAT THIS DOES NOT SAY, and the limits matter more than the pass.**

- `delta<1.25` of 0.485 is a WEAK monocular depth model. Published models reach 0.85+ on KITTI. The claim
  is that it TRANSFERS, not that it is good.
- The shuffled control reaches 0.343 against constant's 0.204, so a generic driving-scene prior carries most
  of the distance. The net adds roughly 0.14 on top of it. That is the honest size of "reads this image".
- One town, one simulator, camera imagery. Nothing here speaks to real-world transfer.
- This is E4, not E5. E5 additionally needs a paired capability curve and a hidden holdout maintained across
  runs; one sealed exam is not that.

**REGISTRY.** This licenses exactly one edit, made by the examiner: `depth_learner.evidence` from `V0` to
`E4`, citing this document, `data/e4_depth_seal_002/verdict.json`, and the answer/prediction hashes.
`packages/architecture_registry/tests/test_registry_is_enforced.py` was amended deliberately on the same day
so that an E4+ organ must CITE an attested verdict -- a bogus claim without one still fails the suite.

