# Axis v7 — learning ON a shared substrate, not consolidating code

Replaces plan v6's mechanism. v6's own instruments falsified it five times in a day: syntactic
sharing is boilerplate, the four instances hold two interfaces not one, no contrast beat an
incumbent, and the frozen domain had no channel to register an effect anyway. There is no measured
mechanism by which merging code produces generality, and this document does not try to rescue one.

The axis moves. Not "make the organs share implementations" but **"make the OBJECTS share a space,
and let operations be transformations of that space."**

---

## 1. The measurement that makes this a live hypothesis rather than a rerun

The obvious objection is that ATANOR already has FHRR/VSA, so if a shared substrate produced
generality it would have produced it. Checked, and the objection does not hold — for a reason that
is the whole design:

```
vsa_reasoning/fhrr_core.py:5   "per-symbol unit-phasor atom, DETERMINISTIC HASH SEED"
                        :84   "Deterministic (seeded), NO TRAINING, No-LLM"
organs touching the substrate: 5 of 135
                               conformal_gate, evolution, meta_diagnosis, self_acceleration, vsa_reasoning
```

**Every concept's vector is a hash of its NAME.** Two things that behave identically receive
orthogonal vectors; two things that share nothing but a spelling receive related ones. The geometry
carries exactly zero behavioural information, so nothing can travel through it. And almost nothing
is on it: five organs, and their content is failure signatures and search guidance, not domain
objects.

So the substrate is not falsified. **It was never given anything to represent.** That is a
different situation from v6's, where the mechanism was tested and failed.

---

## 2. The hypothesis, stated so it can be killed

> **A vector must be derived from how a thing BEHAVES, not from what it is called.** Then
> similar-behaving things are geometrically near, and a transformation fitted in one region of the
> space applies to nearby regions — regardless of which domain contributed the points.

What that changes, concretely: transfer stops needing anyone to merge anything. Domain A and domain
B never share a line of code. They share *coordinates*. An operation learned as "move points like
this" is automatically defined on every point in the space, including points nobody was thinking
about when it was fitted.

This is the first mechanism in this project that would give the frozen-domain gate a real channel.
v6's fluency seal failed because the only shared package on its eval path contained no
discrimination computation. Under v7 the channel is not a package at all — it is the space, and
anything embedded in it is reachable.

### Why this stays No-LLM and cheap

"Learned" here does not mean gradient training. A behaviour vector is **analytic**: what a thing
does is already recorded, and projecting that record into the shared space is a linear operation.
The repository already holds the ingredient in the right shape and does not know it —
`type_affinity.TypeProfile.rates` is a behavioural embedding today, in a sparse basis of named
predicates rather than a hyperdimensional one:

```
painting        creator 0.785  made_of 0.735  genre 0.39  author 0.019  manufacturer 0.005
literary work   author  0.829  genre   0.36   creator 0.044
hill            country 1.00   located_in 0.86  creator 0.004
```

Those rows ARE the geometry the substrate lacks. Painting and literary work are near on `genre` and
far on `creator`/`author`; hill is far from both on everything except location. Nothing was trained
to produce that — it was read off 115M edges. The work is projection, not learning in the expensive
sense.

---

## 3. The falsifier ladder, cheapest first

Ordered so the axis can die early and cheaply. Each rung is pre-registered before it is run, and
each is reported whichever way it lands — the discipline that produced five useful negatives today.

**V7-0 · Does the behaviour embedding carry any signal at all?**
Embed graph entities from their predicate profiles. Check that two entities sharing an `is_a` kind
are nearer than two drawn at random.
*Gate:* same-kind distance strictly below cross-kind distance, on held-out kinds not used to build
the projection. If it fails, the axis is dead in an afternoon and nothing else is built.

**V7-1 · Does the geometry survive projection into the hyperdimensional space?**
The sparse profile is the easy case; FHRR is the claim. Project profiles into `HoloSpace` and check
the neighbourhood structure is preserved.
*Gate:* the ranking of nearest neighbours agrees with the sparse-basis ranking above a threshold
fixed in advance. A projection that scrambles neighbourhoods is a coding scheme again.

**V7-2 · Is a fitted transformation domain-blind?**
Fit something on one region (e.g. a direction that separates two kinds) and apply it to points from
a region it never saw.
*Gate:* it performs above chance on the unseen region. This is the first rung that could actually
be called transfer.

**V7-3 · The frozen-domain gate, with a real channel this time.**
Embed a second domain's objects in the SAME space, freeze it under the §6 channel criterion —
provably traversed by the eval path — and run V7-2's transformation.
*Gate:* the frozen domain improves or gets cheaper, untouched. This is E5, and it is the first
E4+ evidence this project would have.

---

## 4. What this axis must not become

Named in advance, because each is the locally attractive failure and this plan has already been
caught by two of them in a different costume.

* **A universal embedding that everything is bent into.** If a domain has to be reshaped to fit the
  space, the space is a hand-authored ontology with vector notation. The test is whether the
  embedding is READ off behaviour the domain already records.
* **Trained end-to-end.** The moment the geometry needs a training loop with a loss the operator
  chose, it can be tuned toward the gate. Analytic projection keeps the geometry accountable to the
  data rather than to the objective.
* **Claiming the space before V7-0.** Sixteen measurements did not license a representation
  yesterday and one afternoon of projection will not either. The ladder exists so the claim arrives
  after the evidence, not with it.
* **Assuming this axis is right because the last one was wrong.** v6 died measured; that says
  nothing about v7. The only thing carried forward is the method.

---

## 5. Honest position

Everything above is V0 — a stated concept with a falsifier attached and no result. The one thing
that is measured is §1: the substrate is a hash-seeded coding scheme reaching 5 of 135 organs, which
is why the hypothesis is untested rather than refuted.

The correct next action is V7-0, and its most likely outcome is worth stating in advance so it is
not spun afterwards: profiles built from predicate prevalence may cluster by DOCUMENTATION DENSITY
rather than by kind — the exact confound that made a 223-member grape class swallow two shipyards
before prevalence replaced rate. If V7-0 fails that way, the fix is known; if it fails another way,
the axis is wrong.

---

## 6. The destination IS the fusion — and that is a constraint on the FIRST rung, not a reason to skip to the last

Owner, 2026-07-29: why not integrate it all now — FHRR, the predictive 4D world model, the ontology
— into the one central core the canonical hierarchy already names as the top goal?

**On the destination: agreed, and it was never in question.** The canonical goal is exactly that
fusion, and this axis is subordinate to it.

**On doing it now: no, and for the reason five things died today.** "Fuse everything" is v6's
consolidation thesis at larger scale — assert an integration, build it, and have no instrument that
can say whether it produced anything. The cost of being wrong scales with what was fused, and the
evidence available afterwards does not.

**But the question exposes a real defect in §2–§3 above, and it is corrected here.** §3 described
embedding GRAPH ENTITIES. If this substrate is to be the central core, an embedding designed around
graph entities is a knowledge-graph embedding wearing a core's name, and the discovery that it has
no channel to perception or physics arrives after it is built. That is precisely the fluency
mistake — no mechanistic channel — repeated at architecture scale.

### The correction: one occupancy condition, fixed before the first rung

> **The space admits anything expressible as ROLE-FILLER BINDINGS and scorable by PREDICTION ERROR.**

Neither half is invented for this document. FHRR binding *is* role-filler by construction, and
V-JEPA's whole content is "predict the next latent". The condition is stated so that both occupants
are admissible from the start:

| occupant | bindings | what it predicts |
|---|---|---|
| a graph entity | predicate → value | which other predicates it takes |
| a 4D world state | attribute → value, per object, per instant | the next state |

Both are the same shape: *a bundle of bindings whose behaviour is what it predicts.* So the
substrate is designed for both now, and **validated on the cheaper occupant first** — graph
profiles exist and cost nothing to project, 4D states need SPLATRA/JEPA running.

That is the whole difference between this and "fuse it now": the design admits the fusion, the
schedule does not pretend to have tested it. If V7-0 fails, one afternoon is lost instead of an
architecture.

### The rung that gets added because of this

**V7-2b · Cross-modality occupancy, before any claim of a core.** Take one 4D world state from the
existing SPLATRA/JEPA path, express it under the occupancy condition, and place it in the same
space. *Gate:* its nearest neighbours are other world states rather than arbitrary graph entities —
i.e. the space did not collapse the two modalities into noise when it got both. Until that reads
green, this is a shared substrate for one modality, and calling it the central core would be the
sixth assertion of the day.

---

## 7. Three precisions on the two-axis picture (owner, 2026-07-29)

The owner's statement of the architecture: FHRR as the substrate of concepts, relations and laws —
rational thought; the 4D spacetime world model as the imagination simulator running those rules
forward; the two bound by one mathematical spec (role-filler binding), and honesty emerging from
that binding the way a person with solid concepts imagines without hallucinating.

The direction is right and is already what §6's occupancy condition formalises. Three precisions,
recorded because if the framing above becomes the official story unamended, it will be asserted and
then measured false — which has happened five times in two days.

**A shared format buys TRANSFERABILITY, not TRUTHFULNESS.** These are different properties and the
analogy quietly merges them. A binding algebra will bind nonsense perfectly well: the FHRR
superposition of arbitrary role-filler pairs is well-formed and can be entirely false. Nothing in
the representation objects. What produces honesty in ATANOR today is not the substrate but the
MEMBRANE — the conformal gate, physics-truth, the TMS firewall — and no amount of shared geometry
replaces it. The axis is a transfer mechanism; the membrane remains the honesty mechanism.

**FHRR is a coordinate system, not a logic.** It gives binding, superposition and approximate
unbinding — an associative memory with algebraic structure. A "rule" in FHRR is similarity-based
retrieval, not entailment; it cannot tell you that something FOLLOWS, only that something is NEAR.
ATANOR's actual entailment lives in the symbolic spine (back-chaining, the truth-maintenance
system). So the honest picture has three parts and not two:

| part | gives | does not give |
|---|---|---|
| FHRR substrate | shared coordinates, so transfer has a channel | entailment, truth |
| symbolic spine | entailment, contradiction, retraction | a shared space between modalities |
| 4D world model | forward simulation over space and time | a check on whether the simulation is true |

and the membrane is the fourth thing, which is what keeps the third one honest.

**Where this actually stands today.** V7-0 passed on a SPARSE NAMED-PREDICATE basis, 49 entities,
four held-out kinds. `fhrr_core` is still a hash-seeded coding scheme and V7-1 has not run. So
"FHRR as the semantic substrate" is not yet true of this codebase — it is the target of the next
rung, and calling it the architecture before V7-1 reads green would be the assertion this whole
document is structured to avoid.

---

## 8. V7-2b CANNOT BE RUN AS SPECIFIED — and the reason falsifies §6's occupancy condition

Rung V7-2b was to place a real SPLATRA/JEPA world state in the same space and check the two
modalities did not collapse into noise. Inspecting what a world state actually is stopped it before
a line of probe code was written, and the finding is worth more than the rung would have been.

**A world state here is `Transition`: `x_light` (a turbovec light vector — a dense continuous field
embedding), `action` (a 3-vector), `pos` (N×3 true positions).** It is not a set of named
role-filler bindings and it has no predicates in the graph sense.

So the occupancy condition fixed in §6 — *the space admits anything expressible as ROLE-FILLER
BINDINGS and scorable by PREDICTION ERROR* — **is not satisfied by the modality it was written to
admit.** That condition was stated confidently, before rung one, as the thing that made the fusion a
constraint rather than an aspiration. It is the sixth claim in two days to be measured false.

### Why forcing it would be the move already refused twice

The world state could be given roles: bin the positions into named cells, or name the turbovec
dimensions. That is inventing a shape so a member fits, which was refused for `loop_schema.
read_schema` (two aligned sequences) and again for `edge_attribution._bridging` (normalises by
population size) — at the cost, that second time, of losing a family member. The same standard has
to hold when the cost is losing the fusion story.

### The deeper mismatch, stated precisely

| | graph entity | 4D world state |
|---|---|---|
| what varies | WHICH relations it has | the VALUES of attributes it always has |
| the vector | a distribution over predicates | continuous coordinates |
| "distance" | how differently it distributes | how far apart in the field |

A distribution over `{pos_x, pos_y, pos_z}` is not a meaningful object. These are different KINDS of
quantity, and no amount of shared dimensionality makes them the same kind. Two vectors in one
container that share no roles are two orthogonal subspaces stapled together — which is not a shared
substrate in any sense that could carry transfer, because a direction fitted in one has no meaning
in the other.

### What survives, and the corrected condition

The half both modalities genuinely share is **prediction**, not binding. A graph entity predicts
which predicates it takes; a world state predicts the next state. That is a real common structure
and it is where the axes join — at the LOSS, not at the REPRESENTATION.

> **Corrected occupancy condition:** the substrate is shared where two things are scored by the same
> prediction error, and NOT wherever two things happen to be vectors of the same width.

That is a weaker claim than §6's and it is the one the code supports. It also relocates the fusion:
FHRR is the coordinate system for the SYMBOLIC modality, the world model is the simulator for the
CONTINUOUS one, and what makes them one system is a shared predictive objective plus the membrane —
not a shared binding algebra. The owner's picture in §7 stands, with the join moved one level down.

**V7-2b is therefore withdrawn rather than failed**, and replaced by a question that can be
answered: *is there a prediction task both modalities can be scored on?* Until that exists, this is
a one-modality substrate, and §6's promise that the design "admits both now" was not true when it
was written.

---

## 9. Promotion verdict on the real residue: NOT PROMOTED, and the cause is named

The shadow was run against A1c on the REAL 36-edge Athens residue -- not the hand-built fixtures
that made the prevalence fix look finished.

```
residue edges                         36
A1c placed                            10   (its measured baseline: 10 placed, 10 correct)
shadow placed                         15
exact agreement                       31/36 = 0.86
agreement on A1c's placements         10/10
```

**The good half is real and independent.** Every edge A1c places, the shadow places identically --
a substrate built from behaviour distributions, with no knowledge of A1c's thresholds, reaches the
same ten verdicts.

**The bad half is disqualifying.** The shadow places five more, and all five are wrong. Every one is
a `located_in` edge (Achaea, Lexington, Midlands Province, Claiborne Parish) that A1c abstained on
with *"fits weather station and neighborhood about equally"*. Precision: **10/15 = 0.67 against
A1c's 10/10 = 1.00.**

The promotion criterion was that the shadow's predictions match A1c's accuracy. They match on what
A1c places and are worse overall, so the criterion is not met and nothing is promoted.

### The cause, and why the fix is not applied in the same breath

`kind_match` has support and coverage but **no MARGIN gate** -- no check that the winner beats the
runner-up decisively. `located_in` is held by every place-kind and therefore separates none of them;
`weather station` wins only because it has few defining predicates, so covering one of them scores
high. A1c already solved this, structurally, with `top < runner * margin -> unknown`.

Adding it now would be principled rather than fitted -- the argument is A1c's, established before
this comparison existed. But it would also be a change made immediately after seeing which cases
failed, and the honest sequence is to record the verdict first so the next reading is against a
stated baseline rather than against a moving one. **NOT PROMOTED, precision 0.67, cause: missing
margin gate.** The next run is a re-measurement against exactly these numbers.

### What this says about the axis

V7-3 remains blocked and is now blocked for a better reason. The substrate has a channel (the M3
shadow) but has not earned authority on the one domain where it can be checked. Freezing a second
domain to test transfer from an organ that is less precise than the one it shadows would be
measuring the propagation of a defect.

### Re-measurement after the margin gate — criterion MET, with the caveat that matters

Measured against the baseline fixed in the previous section, not against a moving one:

| | before | after |
|---|---|---|
| A1c placed | 10 | 10 |
| shadow placed | 15 | **10** |
| exact agreement | 31/36 = 0.86 | **36/36 = 1.00** |
| shadow precision | 10/15 = 0.67 | **10/10 = 1.00** |

All five `located_in` false placements now abstain. The promotion criterion — the shadow's
predictions match A1c's accuracy — is met.

**THE CAVEAT, and it limits what may be claimed.** The margin constant is 1.6, taken from A1c. So
part of this agreement is INHERITED rather than independent: the substrate now abstains where A1c
abstains partly because it was given A1c's threshold. The honest statement is that the shadow no
longer regresses against the organ it shadows — not that it rediscovered the boundary on its own.

**AND PERFECT AGREEMENT MEANS IT ADDS NOTHING NEW.** Reproducing A1c exactly is what promotion
requires (do not make things worse) and is not evidence of capability beyond A1c. The substrate's
reason for existing is that it is DOMAIN-BLIND where A1c is graph-specific, and nothing measured so
far exercises that. Agreement on one node's 36 edges licenses promotion; it does not license the
word "transfer".

That is exactly what V7-3 is for, and it is now unblocked for the first time: there is a substrate
with a channel that has earned authority on the one domain where it could be checked.

---

## 10. V7-3 FIRST READING — REGRESSED. The first frozen-domain transfer measurement this project has taken.

A-side work: `rank_kinds` now weights each predicate's contribution by how much it DISTINGUISHES a
kind rather than by its raw prevalence — the same move `type_affinity.discriminative` makes and the
substrate was not making. A change to the REPRESENTATION; the decisiveness margin was not touched.
`packages/kind_prediction` was not edited (surface hash intact, verified by the gate).

```
                    baseline    now        verdict
coverage            0.261905    0.369048   improved   (+41% relative)
correct            20          28          improved   (+8)
abstention_rate     0.738095    0.630952   improved
accuracy_on_placed  0.909091    0.903226   REGRESSED  (-0.006)
wrong               2           3           REGRESSED  (+1)

GATE: REGRESSED
```

**What actually happened:** nine more entities were decided, eight of them correctly. Precision on
the new placements is 8/9 = 0.89.

**Why the verdict is REGRESSED anyway:** the pre-registered signature was *coverage rise with
accuracy INTACT*, and accuracy fell. The gate ranks a regression above a win by construction,
because I built it that way so a win could not average a regression away. It reads as designed.

**The distinction that must not be blurred.** The gate says the pre-registered signature was not
met. It does NOT say the change was bad — 8-for-1 is a good trade by any ordinary standard. Whether
to accept it is a DECISION, and this instrument deliberately does not make decisions. Saying "0.006
is noise" here is precisely the move the instrument exists to refuse.

### A design flaw in the seal, stated but NOT fixed by re-cutting it

With `tolerance=0.0`, any coverage increase that is not perfectly precise reads REGRESSED. Going
from 22 placements to 31 while keeping `wrong` at exactly 2 is close to impossible, so this seal is
structurally hostile to the very improvement it was written to detect. That is a real fault in how I
registered it — the same class as V7-2's absolute bar being set below chance: **a threshold
registered without knowing the measurement's natural variance.**

It is NOT fixed here. Re-cutting a seal after seeing the result is what `freeze`'s
refusal-to-overwrite exists to prevent, and it applies when the seal is unfair to me exactly as much
as when it is convenient. A tolerance that admits this trade would have to be registered on a NEW
seal, before its first reading, and the decision to do that is the operator's.

### Honest position on E5

This is the first frozen-domain transfer measurement in the project's history, and it reads
negative. The underlying effect is real and in the predicted direction — a representational change
in A moved an untouched B substantially — but it did not clear the bar as written. **E4+ evidence
remains zero**, and the correct summary is: transfer was observed, the gate was not passed.

### Route (b) is blocked, and the blocker is a defect in how I built B

Owner chose (b): find a representational improvement that raises coverage with accuracy INTACT, so
the seal passes as written rather than being re-cut. Diagnosing the three wrong predictions ended it:

| entity | B's label | predicted | the entity's actual behaviour |
|---|---|---|---|
| Deposition | literary work | **painting** (1.70 vs 0.286) | creator, made_of, located_in, religion |
| Traveler | video game | **literary work** | author, part_of — `author` is the strongest literary signal |
| Kukryniksy | encyclopedia article | video game | country, genre, occupation — a Soviet artist collective |

**All three are cases where the GRAPH'S LABEL is the doubtful party.** Two are almost certainly
merged nodes — the exact defect the substrate exists to detect — and the third is a Wikipedia
artifact kind rather than a kind of thing. On `Deposition` the substrate is overwhelmingly confident
and it is more likely right than the label is.

So **domain B's ground truth is contaminated by the very defect the substrate was built to find.**
The measurement's ceiling is not the representation; it is the labels. No representational change
short of ignoring evidence removes those three, which means route (b) cannot be delivered: coverage
can rise, `wrong` cannot return to 2.

### What follows, and what does not

**B is not edited.** It is frozen, and correcting its labels after seeing which ones hurt is exactly
the exam-editing the gate exists to prevent — the fact that the correction would be *justified*
makes it more tempting, not less.

**The seal is not re-cut.** Twice now a seal has turned out to be unfair to the work it measures
(V7-2's bar below chance, this tolerance, now these labels), and each time the discipline held. That
consistency is worth more than any single reading.

**The defect is mine and it is specific:** I drew B's corpus mechanically, which prevented
hand-picking, and then took the graph's `is_a` as ground truth without checking whether those labels
were themselves merged. In a store where 1.18% of subjects are hard-merged and merged nodes are
disproportionately the famous ones, a mechanically-drawn sample of well-connected entities is
*enriched* for exactly the contamination that matters.

**The route forward is a THIRD seal with labels that were checked**, registered before its first
reading. That is a real piece of work, not a tweak, and the decision to spend it is the operator's.

### Standing position

E4+ evidence remains zero. What the day produced instead is an instrument that has now refused the
work three separate times — once when the bar was mis-set, once when the tolerance was hostile, and
once when its own ground truth was contaminated — and was not adjusted on any of those occasions.
The substrate's lift-weighted representation moved an untouched domain by +41% relative coverage at
89% precision on the new decisions; that effect is real, is recorded, and is not certified.

---

## 11. Diagnosing the 53 abstentions — and catching myself searching the sealed domain

```
abstained                                    53
  score 0, no defining predicate covered      6
  margin-blocked, top1 CORRECT               16   <- recoverable ceiling
  margin-blocked, top1 WRONG                 31   <- abstention is protecting us
```

**The margin is doing real work.** Lowering it uniformly would gain 16 correct and 31 wrong. Seal 3's
signature is `correct` up with `wrong` NOT up, so a uniform loosening is not merely unhelpful, it is
the opposite of the target.

So the question became whether anything separates the recoverable 16 from the protected 31.
Hypothesis: an entity whose top-1 is right holds at least one predicate STRONGLY SPECIFIC to that
kind, diluted by shared ones; an entity whose top-1 is wrong holds only shared predicates. Measured
before building anything:

```
top1 CORRECT (n=16)   max-lift median 3.08   mean 3.16
top1 WRONG   (n=31)   max-lift median 1.73   mean 2.15
```

The signal is real. It is also not clean: at every threshold the recovery is impure — 9 correct with
6 wrong at 2.0-3.0, 7 with 5 at 3.5, 3 with 1 at 4.0. **Every threshold brings wrong along**, so
max-lift alone cannot deliver seal 3's signature.

### The part that matters more than the negative result

Producing that table meant scoring candidate thresholds AGAINST B'S LABELS. **That is searching the
sealed domain, not measuring it.** Had I continued — 4.5, 5.0, a second feature, a combination — a
threshold with zero wrong would eventually have appeared, and it would have been overfitting wearing
a gate's clothes. Pre-registration, controls, hash chains and a refusal-to-overwrite, all defeated
at the last step by looking at the answers.

**No threshold is applied.** The seal is not read, and B's independence for a future honest
measurement survives only because the search stopped here rather than at the first passing value.

**The rule this establishes, which was missing:** a candidate improvement must be developed and
SELECTED on A-side data or a held-out split, and only then measured ONCE against B. The frozen
domain is a verdict, never a search space. The transfer gate enforces that B is not EDITED; nothing
in it prevents B being MINED, and that gap is now on the record.

### Where this leaves V7-3

`correct` cannot be raised without raising `wrong` by any means found so far, and the means that
would find one are not legitimately available. The honest next step is a development split drawn
from kinds NOT in B — the substrate can be tuned freely there, and B stays a single unspent
measurement. That is real work and it is where the next session starts.

---

## 12. Development split — the hypothesis dies where it should, and B stays unspent

Built from 14 kinds chosen from a fixed candidate list and asserted DISJOINT from B's eight in code,
158 entities, same mechanical stride draw. Selection now happens here; B is measured once, later.

```
DEV baseline            correct 29   wrong 13   of 158     (abstained 100)
  abstained, top1 correct  16
  abstained, top1 wrong     84
max-lift >= 2.0 / 3.0    +10 correct  +13 wrong
max-lift >= 4.0 ... 8.0   +3 correct   +4 wrong
```

**Every threshold adds more wrong than correct.** The max-lift hypothesis is rejected — on the
development split, which is the whole point of having one. Yesterday's version of this project would
have found that out by spending the sealed domain.

### The finding nobody was looking for

**Accuracy degrades sharply as the candidate set grows: 0.90 on B's 8 kinds, 0.69 on DEV's 14.** And
84 of DEV's 100 abstentions have a WRONG top-1, against 31 of 53 on B — the margin is doing far more
protective work here, and would have to, because the representation separates far less well.

That is a scaling property of the substrate and it was invisible while only one domain existed. It
also reframes what "raise coverage" means: on 8 kinds the substrate is mostly right and abstaining
conservatively; on 14 it is mostly wrong and abstaining necessarily. A representation whose accuracy
falls this fast with candidate count is not yet a substrate for open-domain use, whatever it scores
on a small closed set.

### Position

Seal 3 remains unread. The route to reading it is a representational change that survives DEV, and
max-lift was the obvious candidate and is gone. The next candidates have to explain the 8-vs-14
degradation, not just recover borderline cases — which is a better question than the one this
section started with.

## 13. The sixth witness, measured — competent about WHERE, mute about WHAT

The 4D world state was refused as a sixth witness on an argument: no shared referents. An argument
is not a measurement, so it was measured. 5,509,430 per-frame positions of 190 moving objects were
captured out of a running Realcity by a three-line probe that exported the position each frame had
already computed — nothing in the capture path reads a kind label, so the trajectory cannot have
been coloured by the answer.

**Two tasks, and only the second can fail.** Car-vs-NPC is disjoint by construction (6–12 m/s vs
1.2 m/s), so passing it shows the pipeline runs and nothing else. The real task is NPC ROLE over 10
classes, and the generator says exactly what should happen: `NPCAgent.update()` never reads
`this.role`, so motion carries no role information; but roles are drawn from `NPC_ROLES[zone(dist)]`,
so position does. Pre-registered before any run, against the permutation null rather than intuition:
**dynamics at chance, place above chance.**

### The first cut was defective, and the defect is the interesting part

The first partition put every speed statistic in `dynamics` and `ext_x`/`ext_z` in `place`. Both
labels were wrong. Every speed there is a 3-D magnitude, so it contains `dy` — and `dy` is the
terrain gradient under the object, a pure function of WHERE IT IS. `vt_mean` is nothing but slope.
So `dynamics` silently carried place and read 0.233 (p = 0.006), and the pre-registration recorded a
FAILURE in the direction opposite to the prediction. Meanwhile `place` held two range-of-motion
features and read non-significant. Re-cut by **what each quantity is a function of** rather than by
what it sounds like:

```
  B: npc role (120 objects, 10 classes)      top1    centroid   null    p
  all features                               0.283     0.167    0.128   0.0005
  dynamics only        [defective cut]       0.233     0.117    0.128   0.0060
  place only           [defective cut]       0.183     0.158    0.128   0.0815
  MOTION_H  terrain-blind (dx,dz only)       0.175     0.108    0.129   0.1364
  TERRAIN   height + vertical step           0.225     0.142    0.128   0.0055
  EXTENT    how far it ranged                0.158     0.100    0.128   0.2514
  LOCATION  radius only                      0.217     0.233    0.129   0.0245
```

On the corrected instrument the pre-registration **holds in all four cells**: terrain-blind motion is
at chance, extent-of-motion is at chance, and both position-derived channels are above it. The 0.233
"dynamics" signal was the terrain leak, entirely.

### The ceiling says the channel is nearly saturated, and how low that ceiling is

`zone(dist)` returns a zone and the role is then drawn UNIFORMLY from that zone's pool, so position
can tell a witness which pool and nothing about which draw. The leave-one-out majority role within
each true zone — the most any position-based witness could score — is **0.275**. LOCATION's centroid
reaches 0.233, about 85% of it. All-features 1-NN reads 0.283, one object above the ceiling and
0.2 standard errors from it: indistinguishable, not evidence of extra signal.

So the physics channel here is not weak because the measurement is crude. It is weak because the
world only put 0.275 of role information into position, and the witness found most of it.

### The substrate's own scoring rule ran on a continuous modality, unmodified

`decisive_kind` — the same function that scores graph entities, no change — was given each object's
speed histogram in place of a predicate distribution (a bin plays the part of a predicate, "has mass
in this bin" the part of "holds this predicate"; nothing is given a name and no role is invented,
which is the line `read_schema` and `_bridging` were both refused at). Reading:

```
  kind (car/npc)   coverage 1.000  (190/190)   accuracy_on_placed 1.000
  role (10 class)  coverage 0.000  (0/120)     accuracy_on_placed  n/a
```

**It placed every object where the signal existed and refused every object where it did not.** The
abstention discipline transferred to a modality it was never fitted on, without being told to. That
is the first evidence in this project that the mechanism — not the representation — is modality-
general, and it is the strongest thing this measurement produced. The caveat is real and stated: the
12-bin discretisation over [0, 0.30] is a choice I made, so this is a probe of the scoring rule, not
a second measurement of the witness.

### Error correlation with the graph witnesses: UNDEFINED, and that is the verdict

Independence is only defined when two witnesses judge the SAME defendants. `npc17` is not an entity
the shipped graph holds a single fact about, so the graph witnesses produce no error vector to
correlate against — not an uncorrelated one, none. What the data does support is the correlation
BETWEEN the physics channels, which is reported for what it is: LOCATION × MOTION_H 0.184,
LOCATION × TERRAIN −0.041, MOTION_H × TERRAIN 0.067.

**The sixth witness's verdict is refined, not overturned.** It was refused for having no shared
referents; it still has none. What is now measured rather than assumed is that its competence is
real but is about a DIFFERENT QUESTION than the panel votes on — it testifies to where a thing is,
while the panel is deciding what a thing is. A witness that answers a different question is not
admissible however competent it is, and that is a cleaner reason to exclude it than the one it was
excluded on.

### What this does and does not say about the fusion goal

It does not say the 4D fusion is blocked. It says **Realcity cannot be the testbed for it**: the
world couples physics to symbol only through `zone(dist) → role pool`, a coupling capped at 0.275,
and the symbolic side of every object is a role string with no graph behind it. A testbed for
continuous↔symbolic transfer needs objects that are simultaneously graph entities with real
predicate behaviour AND things with trajectories. Realcity has the second and not the first.

It also puts one concrete brick under the corrected join condition from §6 — that the substrate is
shared where two things are scored by the same rule. Today `decisive_kind` scores both, correctly,
including correctly refusing. That is one rule spanning two modalities, which is less than fusion
and is not nothing.

*(§12's closing claim that accuracy "degrades sharply, 0.90 on 8 kinds to 0.69 on 14" was withdrawn
by the same-day correction in `ATANOR_postmortem_v6_v7_2026-07-29.md`: normalised for chance the
ratio RISES 2.25 → 4.44 and there is no cliff. That paragraph stands as written history, not as a
live finding.)*
