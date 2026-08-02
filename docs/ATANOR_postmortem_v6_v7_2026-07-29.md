# Post-mortem — eleven disconfirmations in two days, and what actually caused them

Requested by the owner. Written about causes rather than incidents, because the incident list is
already in the plan documents and a list of incidents is not a diagnosis.

**First, the framing, because it decides what gets fixed.** Eleven hypotheses died and zero E4+
evidence was produced. If that is read as the process failing, the fix is "be more careful", which
is not a fix. What actually happened is narrower and more useful: **the hypotheses failed and the
method worked.** Every one of the eleven was killed by an instrument built in the same two days, and
on four separate occasions the instrument refused work I wanted to pass and was not adjusted. The
damage is real — two days of building on claims that did not survive — and the cause is not
insufficient care. It is five specific, nameable errors.

---

## Cause 1 — Salience was mistaken for evidence

Plan v6's foundation was "the same operation, written by hand four times in one day". That came from
me noticing a pattern *in my own recent work*. It was vivid, it was recent, and it was about my own
experience — three properties that make something feel like a finding. It was never measured before
it became a plan's central claim, and the first instrument built to check it returned four distinct
signatures.

The error is not "I was wrong about the four functions". It is that **a personal observation was
promoted to a foundation without passing through the measurement step that every other claim in the
project is required to pass.** The plan even said, in its own §4, that no generality claim should be
made without a frozen-domain measurement — while resting on an unmeasured one in §1.

## Cause 2 — Thresholds registered against intuition, not against the null

Three times, and it is the same mistake each time:

* V7-2's absolute bar was set at 0.65 when random directions score **0.72**. The bar was below
  chance and tested nothing.
* Seal 1 registered `accuracy_on_placed` at tolerance 0 on a metric **mechanically coupled** to
  coverage — going 22 → 31 placements while holding `wrong` at exactly 2 is near impossible, so the
  seal was hostile to the improvement it existed to detect.
* The max-lift thresholds were scanned for one that would pass, which is the same error with the
  direction reversed.

**Pre-registration is only meaningful when the null distribution is known.** Registering a number
before the run is necessary and not sufficient; registering it before knowing what chance looks like
is theatre with a timestamp.

## Cause 3 — Knowing a failure mode by name did not prevent committing it

`packages/substrate` carried three measured rungs (V7-0, V7-1, V7-2) while **nothing imported it**.
That is the eighth instance of built-but-unwired in this repository — and it was produced on the same
day I catalogued the previous seven and wrote a census to detect them.

The lesson is uncomfortable and worth keeping: **a named pathology is not a check.** The seven I
found were found by a tool. Mine went unfound because I did not run the tool on myself. Vocabulary
does not confer immunity; only an instrument pointed at yourself does.

## Cause 4 — Partial rigour manufacturing false confidence

This is the pattern behind two failures and it is the most transferable one.

* Domain B's corpus was drawn **mechanically** — a fixed stride across the whole extension, so no
  entity was hand-picked. That felt like rigour. Under cover of it I took the graph's `is_a` as
  ground truth **without checking whether those labels were themselves merged**, in a store where
  1.18% of subjects are hard-merged and merged nodes concentrate in exactly the well-connected
  entities a stride sample selects. The mechanisation made the corpus unbiased and the labels
  contaminated, and I noticed only the first half.
* The same shape appears in cause 2: pre-registration felt like honesty, and the feeling substituted
  for checking the null.

**A rigorous step adjacent to an unexamined step produces more confidence than either deserves.**
The unexamined step inherits credibility from its neighbour.

## Cause 5 — Hypotheses selected for testability, not for plausibility

Consolidation was attractive because it was cheap to measure. Substrate-learning was attractive for
the same reason. Neither was chosen because evidence pointed at it. That is not automatically wrong
— cheap falsifiable hypotheses are how a project makes progress when it is uncertain — but it should
have been **stated as a search strategy** rather than presented as a diagnosis. v6 §1 reads as a
finding; it was a guess with good ergonomics.

---

## What this implies for the stated goal

The owner's goal is not a working graph embedding. It is **full fusion with the 4D spacetime world
model, and continuous↔symbolic transfer at scale.** Three of the failures above bear on it directly,
and they narrow the path rather than blocking it.

**The join is at prediction, not at representation.** §6's role-filler occupancy condition was fixed
before rung one specifically to make the fusion a constraint — and the 4D modality does not satisfy
it. A world state is `x_light` + `action` + `pos`: a continuous field embedding with no named roles.
A graph entity varies in *which* relations it has; a world state varies in the *values* of
attributes it always has. Those are different kinds of quantity and shared dimensionality does not
make them the same kind. The corrected condition — **the substrate is shared where two things are
scored by the same prediction error** — is weaker, is what the code supports, and is where the
fusion actually attaches.

**Candidate scale is the blocker to solve first.** The symbolic substrate scores 0.90 on 8 kinds and
**0.69 on 14**. A representation that degrades that fast with candidate count cannot hold continuous
world states as neighbours of symbolic entities — the fused space would have far more than fourteen
things to tell apart. Attempting fusion before this is understood would be building the largest
version of the thing that has failed at the smallest scale.

**Forcing the modality to fit is off the table.** The 4D side could be given invented roles — bin
positions into named cells, name the turbovec dimensions. That was refused twice already, for
`read_schema` and for `_bridging`, the second time at the cost of losing a family member. The
standard has to hold when the cost is the fusion story.

---

## The three corrections that are now load-bearing

1. **Measure before founding.** No observation becomes a plan's premise without passing the same
   gate its conclusions would face. v6 §1 would not have survived that rule.
2. **Register against a measured null.** Every threshold is preceded by a chance-level measurement.
   Seal 3 derives its tolerance (one error on ~31 placements = 0.032 → 0.035) rather than choosing
   it; that is the shape all future registrations take.
3. **Development split before sealed measurement.** Selection happens on data that is not the
   verdict. This one has already paid: max-lift was rejected on DEV, and domain B remains an unspent
   single measurement. The transfer gate enforces that B is not *edited*; nothing in it prevented B
   being *mined*, and that gap was closed by discipline rather than by code — which means it is the
   next thing to put in code.

---

## Correction, same day: the "scaling ceiling" was cause 2 committed a fourth time

The post-mortem above named candidate scale as the blocker to solve before fusion, on the grounds
that accuracy fell 0.90 on 8 kinds to 0.69 on 14. The scaling curve was then measured on DEV, over
all contiguous windows of the sorted kind list so no subset was hand-picked:

```
  k   top1    chance   x chance   gated_acc   coverage
  4   0.562   0.250      2.25       0.859      0.315
  6   0.467   0.167      2.80       0.809      0.282
  8   0.408   0.125      3.26       0.751      0.296
 10   0.363   0.100      3.63       0.746      0.277
 12   0.334   0.083      4.00       0.724      0.268
 14   0.317   0.071      4.44       0.690      0.266
```

**There is no cliff.** Raw accuracy falls because chance falls, and the ratio to chance RISES
monotonically — 2.25 to 4.44. The representation gets relatively STRONGER as candidates multiply,
and coverage is nearly flat.

So the "degradation" was **cause 2 committed a fourth time**: comparing 0.90 at 8 kinds against 0.69
at 14 without normalising for the null, exactly the error of registering V7-2's bar below chance.
Having written a post-mortem naming that error, I then made it again inside the post-mortem, and the
claim that a representation degrading this fast could not hold continuous world states rested on it.

That claim is withdrawn. Twelve disconfirmations now, and this one killed a NEGATIVE claim — the
first time the method has cleared an obstacle rather than removed a hope.

**What the curve does and does not license.** It dissolves the scaling objection to v7 and to the
fusion goal: the decline is arithmetic, not a ceiling. It does NOT show open-domain viability —
top-1 at 0.317 on fourteen kinds is 4.4x chance and still low in absolute terms, and 0.690 gated is
what a user would meet. The maze-ending question was "fixable defect or structural ceiling", and the
answer is neither: **it was not a defect.**
