# The eye: which layers may be written, and which must be learned

**2026-07-30. The owner's question, and it deserved an audit rather than a reassurance:**

> 색 뿐만이 아니라 사람 눈이 보고 느끼고 해석하는걸 최대한 모방하고싶어. 우리가 기능 추가하듯 능력을
> 넣어주는게 아니라. 지금 그렇게 가는거지?

**No. Mostly not.** Counted rather than asserted.

---

## 1. The audit

| | count |
|---|---|
| perception modules that **learn** (`fit`/`train`/`backward`/`optim`) | **2** — `learned_signature`, `latent_predictor` |
| perception modules that are **pure rules** | **20** — coherence, common_fate, efference, events, object_recognition, scene_graph, sprite_tracker, self_criterion, one_eye, handle, attention, plausibility, scene_weave, spatial_memory, open_vocab, face_cortex, geo_anchor, reconstruction_loss, user_state, `__init__` |
| hand-written constants and thresholds | `appearance_presence` 27, `fovea` 15, `sprite_tracker` 9, `self_criterion` 8 |

And the decisive number: **the hand-written colour rule (48.5% unconditional on-body) still beats the
learned embedding (42.7%)**. Every result in the perception line so far has been carried by rules I
wrote. Nine attempts at body-finding, and most of them were "one more hand-designed statistic" — which
is exactly the pattern the question was pointing at.

---

## 2. But "learn everything" is also wrong, by the standard of imitating a human eye

The retina is **not trained**. Centre-surround antagonism, graded acuity falling off from the fovea,
separate motion channels — genetically specified, present at birth, not shaped by experience. So
`fovea.py`'s fifteen constants are **a faithful imitation, not a shortcut**. Replacing them with
something learned would be less human-like, not more.

The mistake is not that hand-written layers exist. It is that **the hand-written layers are in the
wrong places.**

| stage | in humans | in ATANOR | faithful? |
|---|---|---|---|
| transduction / retina | not learned — genetically specified | 15 constants in `fovea.py` | **yes** |
| oriented edges / features | emerge from image statistics; partly experience-dependent | absent | — |
| motion segmentation | **learned**; infants use common fate before shape | rule: background subtraction | **no** |
| object constancy | **learned from motion** | `learned_signature`, wired 2026-07-30, not yet winning | partly |
| categories ("that is an eraser") | learned socially, from being told | absent | **no** |
| affordances | learned by acting | 5 hand-written entries in `packages/affordance` | **no** |

Infants track objects through occlusion by **common fate** long before they use shape or colour, and
that competence is acquired. Ours is `common_fate.py`, a rule — and it was measured failing (0.782
against a 0.802 control). The stages a human *learns* are precisely the ones being hand-written here.

---

## 3. The rule this settles

> **A layer that humans are born with may be written. A layer humans acquire must be learned.**

That is the test to apply to every perception organ from now on, and it is falsifiable per organ rather
than being a slogan: for each, ask whether a newborn has it. If yes, a rule is faithful. If no, a rule is
a training wheel and must be replaced by something fitted from experience — and the replacement has to
BEAT the rule on a measured number before the rule is deleted, not instead of it.

Two guards that follow, both learned the hard way this week:

- **A learned replacement needs a random-init control.** `learned_signature` reaches 42.7% where the same
  architecture with random weights reaches 0.0%, which is how we know the temporal supervision taught
  something rather than convolutions flattering themselves. Without that arm the comparison is empty.
- **Built is not wired.** `learned_signature.py` was written on 2026-07-29 and *nothing called it* until
  2026-07-30. That is the fourth such case this week. An organ that is not on a live path has not been
  built, and the audit above is the only thing that finds them.

---

## 4. Order of work

Sequenced by the table in §2 — the stages humans learn, in the order they develop.

**E1 — motion segmentation, learned.** Replace background subtraction. It is a rule standing where an
acquired competence belongs, and it is upstream of everything: every later organ consumes its blobs.
Self-supervised signal available with no labels: pixels that move together over time belong together.
Registered against the incumbent's own numbers — detection is currently 100% on the body, so the bar is
that a learned segmenter matches it while also being robust where subtraction is not (static sprites,
which subtraction removes by construction — the defect that killed the pellet map).

**E2 — finish object constancy.** The embedding over-splits: 55 buckets against the hand rule's 8,
because the merge radius is derived as half the median nearest-neighbour distance, a heuristic calibrated
on a 4-dimensional colour descriptor and reused unchanged on a 32-dimensional embedding where those
distances concentrate. Fix the radius derivation for dimension, then the learned eye either beats 48.5%
or it does not — and that is the first fair test of it.

**E3 — categories.** Needs labels or a licensed corpus, which is a network and licensing decision and
therefore the owner's. Explicitly NOT needed for E1 or E2: constancy requires no category. Scraping
Google Images is against their terms and the images are individually copyrighted; openly-licensed
datasets are the route if this is taken.

**E4 — affordances, learned by acting.** The five hand-written entries in `packages/affordance` are the
last catalogue in the perception line. The image-schema basis plus the executor already provide the
machinery for an affordance to be *derived* from what an action achieves, so this is a wiring and
measurement job rather than a new organ.

---

## 5. What this document may not be used to claim

Nothing here is a result. The audit counts are real, the 48.5% / 42.7% / 0.0% comparison is measured, and
E1–E4 are unbuilt. The claim that ATANOR "sees like a person" is not available and is not made: what is
available is a per-stage account of where it does and does not, and a test — born with it or acquired —
for deciding which layers are allowed to be written by hand.
