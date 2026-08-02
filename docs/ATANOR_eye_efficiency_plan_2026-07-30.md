# The eye, built for efficiency: what human vision actually spends, and what ours does

**2026-07-30. The owner set the criterion, and it is the right one because it is measurable:**

> 핵심은 사람의 정보처리과정이야. 사람만큼 효율적이어야해. 역으로 OCR, OWL 등이 연산이나 전반적으로 더
> 효율적이면 그거로 가야겠지. 궁극적으로는 우리의 눈이 전부 처리할 수 있게 하는게 좋고.

Accuracy alone has been the only axis measured in this line so far. Adding cost changes the verdict on
work already done, starting with mine.

---

## 1. What human vision spends, and where the savings come from

Four mechanisms, and they are the reason a 20-watt brain outperforms a datacentre at this task:

| mechanism | what it buys |
|---|---|
| **retinal compression** | ~100 million photoreceptors reduced to ~1 million ganglion axons before anything leaves the eye. 99% is discarded at the sensor. |
| **foveation** | high acuity over roughly one degree — a tiny fraction of the field — with cortical magnification spending area where the detail is. |
| **saccades** | 3–4 fixations a second, with vision *suppressed* during the movement. The useful input rate is a few hertz, not sixty. |
| **predictive coding** | only prediction *error* propagates upward. A static scene costs almost nothing. |

The common thread is that **nothing pays for what does not change and nothing pays for detail it is not
using.** Our pipeline currently violates both: every pixel of every frame, at full resolution, every step.

---

## 2. Measured cost of each path we have (160×210 Atari frame, 33,600 px)

| stage | pixels touched | ms / frame | note |
|---|---|---|---|
| subtraction + blobs (incumbent) | 33,600 | **1.01** | the hand rule |
| foveated retina (`packages/eye/fovea.py`) | 27,650 | 0.17 | compression **2.43×** |
| learned mask (stride 2, GPU) | 8,400 | **20.18** | 4× fewer pixels, **20× the wall clock** |
| OWLv2 (`packages/perception/open_vocab.py`) | full frame | *not measured* | ~600 MB of weights, a full ViT forward per frame |

**Two corrections to things I have said or implied.**

- `fovea.py`'s 112× compression figure was measured on a **large** frame. At 160×210 it delivers **2.43×**,
  because the fovea's patches are a large fraction of a small image. The retina we already built does not
  help at Atari scale.
- The learned mask touches four times fewer pixels and costs **twenty times more wall clock**, because
  every pixel gets a convolution. Cost was never in the pixel count; it is in the work per pixel.

**And the strategic consequence:** on the efficiency criterion the learned eye currently loses on *both*
axes — 20× the cost for 44.2% downstream body-finding against the hand rule's 68.0%. Saying so is the
point of adding the axis.

**Atari is the wrong stage for an efficiency claim.** Foveation, saccades and predictive coding all pay in
proportion to frame size and scene stability, and a 160×210 frame that changes every step is the worst
case for all three. The efficiency work belongs where the frames are large — City Sample, screens,
cameras — and the accuracy work belongs here, where ground truth is cheap.

---

## 3. Where each human mechanism stands in ATANOR

| mechanism | built? | wired to a live perception path? | measured payoff |
|---|---|---|---|
| retinal compression / foveation | yes, `packages/eye/fovea.py` | **no** — the Atari path takes full frames | 2.43× at 160×210; the 112× figure was a large frame |
| saccades / where-to-look | partial — `Retina.look`, `surprise` | **no** policy on any live path | unmeasured |
| predictive coding | partial — `packages/perception/events.py` with divisive normalisation | **no** | unmeasured |
| event-driven / skip-if-unchanged | **no** | — | every frame pays full cost today |
| learned segmentation | yes, `packages/perception/learned_mask.py` | measured, **not adopted** | 20× cost, worse downstream |
| learned object constancy | yes, `packages/perception/learned_signature.py` | wired 2026-07-30 | beats the colour rule 58.8% vs 48.5%, transfers |

Three of the four human savings mechanisms are **built and unwired**. That is the same pathology this
repository keeps finding, and here it is the direct cause of the efficiency gap: we are not slow because
we lack the organs, we are slow because they are not on the path.

---

## 4. The position on OWLv2 and OCR

The owner's framing is the correct one and it resolves a tension rather than dodging it. This project
forbids pretrained language models and has been importing a ~600 MB pretrained Google detector into a live
vision path. Two rules settle it without hypocrisy:

1. **An external model may be used while it is genuinely better on both axes.** Efficiency is a real
   argument, not a compromise: if OWLv2 answers a question in less total compute than our own path would,
   using it is the efficient choice and pretending otherwise is vanity.
2. **It is retired the moment ours wins on both axes, and not before.** Not when ours is philosophically
   purer, not when ours is close — when it is measured better on accuracy *and* cost.

What follows from that: **OWLv2 is not benchmarked yet, so no claim about replacing it is available.** The
first honest step toward independence is measuring what it costs and what it delivers, on the same frames,
against our own path. Until then "차차 대체" has no baseline to move against.

---

## 5. The order of work, each with a gate on BOTH axes

Every rung registers an accuracy number and a cost number, and passes only on both. A win on accuracy that
costs 20× is not a win under this criterion — which is exactly what the learned mask turned out to be.

**F1 — measure OWLv2 and OCR honestly.** Same frames, same questions, our path against theirs: accuracy,
milliseconds, memory. Without this the independence plan is a preference rather than a decision. Cheapest
rung here and it gates everything in §4.

**F2 — event-driven perception: pay only for change.** The largest single saving available and the one
human vision leans on hardest. Nothing recomputes on a frame whose prediction error is low. `events.py`
has the machinery and is unwired. Gate: identical accuracy on the Atari chain at a measured fraction of
the compute.

**F3 — foveation where it pays, with a where-to-look policy.** Not at 160×210, where it buys 2.43×. On
large frames, with saccades driven by prediction error rather than by a scan pattern. Gate: measured
compression *and* no accuracy loss on the same task, at a frame size where the compression is real.

**F4 — make the learned organs cheap enough to adopt.** The mask is correct in principle and 20× too
expensive; the fix is architectural (evaluate it where change is, at low resolution, or once per object
rather than once per pixel) rather than a better threshold. Gate: within 2× of the incumbent's cost while
holding downstream accuracy.

**F5 — categories, only if efficiency permits.** The stage that needs labels or a licensed corpus. Its
gate is F1's numbers: if our own path cannot beat OWLv2 on cost, an owned category model is a research
project rather than a replacement, and OWLv2 stays.

---

## 6. What this document may not be used to claim

The cost table is measured on 60 frames on this machine and nothing else in it is a result. OWLv2 is
**not** benchmarked and its row says so. F1–F5 are unbuilt. The claim that ATANOR sees as efficiently as a
person is not available, and the numbers in §2 currently say the opposite in the one place they were
measured.
