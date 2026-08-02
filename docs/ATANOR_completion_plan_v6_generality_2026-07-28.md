# Completion plan v6 — generality by consolidation, proven by transfer

Supersedes plan v5 (`ATANOR_completion_plan_v5_2026-07-28.md`), which stays valid as the record of
what Phases A–D measured. v5 asked "what is left to build". v6 asks the question that turned out to
matter: **why does capability keep not generalising, when the capability is demonstrably there.**

Subordinate as always to the canonical hierarchy: the top goal is ONE central core fusing an
ontological neuro-symbolic substrate with a predictive 4D world model → AGI → verifiable
self-improvement → ASI. This plan is about the first arrow.

---

## 1. The diagnosis this plan is built on

ATANOR is **general in principle and specific in implementation**. The gap is not missing
capability. It is capability that was built ~130 times privately.

Evidence from one day's work, all of it accidental — none of these were looking for this:

* A1b separates a merged word by measuring which vocabulary is too widespread to distinguish
  anything (`_bridging`).
* A1c separates a merged name by KIND by measuring which predicate speaks for one candidate more
  than for the alternatives in play (`discriminative`).
* The architecture census finds an organ's holes by peer comparison against organs of the same type.
* D1 finds a loop's progress slot by measuring which field discriminates rounds that moved from
  rounds that did not.

Four organs. **One PRINCIPLE**, implemented four different ways, by hand, in a single day: *how much does this
feature single out this candidate against the alternatives actually in play.* A first keyword sweep
suggests something of that shape appears in **30 of 132 organs** — and that number is deliberately
labelled a HINT, not a measurement, because it came from a grep and this same document argues twice
over that keyword detection produces artifacts. Replacing it with a real measurement is step one.

**So the generality gap is a consolidation gap.** Adding a 133rd organ makes it worse. What
generalises in ATANOR is never the knowledge — it is the discrimination machinery, and it currently
cannot be reused because it has no shared home and no shared representation.

> **CORRECTED THE SAME DAY, by the instrument built to check it.** This section first said "one
> OPERATION, written four times". G1 measured the four functions' structural signatures and got
> **four distinct shapes**, so the gate this document set for G1 — that the known duplicates must
> fall out without being told — reads FAIL. Looking again, the claim was too strong: `_bridging`
> cuts on an absolute share of documents, `discriminative` takes a ratio to the mean of the
> candidates. Those are two members of a family, not one computation written twice, and **they
> cannot be merged by deduplication.**
>
> What survives, and what does not:
>
> * Duplication IS real and measured — 52 recurring shapes, 262 copies, across 81 of 135 organs.
>   But the widest are BOILERPLATE: `to_dict` (12 organs), `_utc_now_iso` (11), `_unit_interval`
>   (7), `main` (7). Consolidating those is worth doing and will not move a capability metric.
> * The "same principle, four implementations" observation stands as an OBSERVATION. It is not
>   syntactic duplication, so G2's "one implementation, the organs call it" is established for the
>   boilerplate class and **not established** for the discrimination class.
> * Therefore G3's A-side lever is weaker than this plan assumed when it was written. Consolidating
>   `to_dict` will not move fluency's numbers, and the frozen seal is now holding a baseline against
>   a consolidation programme whose payoff is unproven.
>
> The honest next question is no longer "consolidate and measure transfer". It is: **is there a
> shared ABSTRACTION over the discrimination family that is worth factoring out at all** — which is
> a harder and much less certain thing than deleting copies. A shape detector is syntactic and
> cannot answer it; answering it needs a semantic notion of what a computation does, which this
> repository does not have.

### What the same lens says about the other two open criticisms

* **Phase D's wall is search, not concept.** Measured on `code_author`: a two-parameter target of
  this shape is authored and verified in 4 tries; three enumerates 1134 candidates and abstains;
  five reports `tried=0` — the families never open. The engine is not missing an idea, it is
  drowning in an unpruned space.
* **The 1.18% merged residue is not a wall.** An open-world knowledge system has unresolved
  referents permanently; 0% would be a claim to know the whole world, which is fabrication. The
  right question is whether the system knows WHICH residue and works it in the right order — which
  the recurrence-driven repair driver now does. Elimination is the wrong target.

---

## 2. The only thing that can prove generality

**Freeze B. Solve A. Measure B without having touched it.**

Coverage cannot show this. Neither can breadth of domains, number of organs, or a benchmark the
system was tuned against. If solving one domain does not make an untouched domain cheaper, the
capability did not generalise — it was re-implemented, which is exactly the disease.

That is E5 on the V0→E6 ladder, and it is worth stating plainly: **ATANOR has zero E4+ evidence
today.** Everything landed so far, including everything in v5, is M-level — mechanism that works
where it was built. This plan's phases are ordered so that the transfer measurement comes as early
as it can, not as a finale, because every phase after it is only worth running if it holds.

---

## 3. The sequence

### Phase G1 · Measure the operator set (replaces guessing at it)

Find the computation shapes that recur across organs **by recurrence, not by name** — the same
discipline the recipe ledger uses for failure signatures, and the same discipline that made
`emits_receipt` structural instead of a filename artifact.

* Structural signature per callable (shape of its data flow), not identifier text.
* An operator is a shape appearing in ≥ N organs. N is read from the distribution, not chosen.
* **Gate:** the measured set reproduces the four instances above without being told about them. If
  it cannot rediscover a duplication we already know exists, it is not measuring duplication.

Output: the honest operator inventory, replacing the "30" hint.

### Phase G2 · One representation, one home

Lift the measured operators onto the shared substrate. FHRR/VSA already exists and its role
vocabulary is already parameterised (`meta_diagnosis.encode_features(features, roles)`), so the
substrate is present and the operators are simply not on it.

* Each operator gets ONE implementation; the organs that had private copies call it.
* **Gate:** an operator extracted from domain A runs unmodified on domain B's data and reproduces
  B's existing result. Not "it imports cleanly" — it must reproduce the number the private copy
  produced, or the consolidation lost something.

### Phase G3 · THE TRANSFER GATE (E5)

The first evidence above M-level that this project has ever had.

* Freeze a domain B completely — code, data, evaluation — before any work on A begins.
* Do real work in domain A that consolidates operators G1 found.
* Re-run B untouched.
* **Gate:** B improves, or B's cost falls, with zero commits touching B. Sealed, pre-registered,
  and reported whichever way it lands. **A negative result here is the most valuable outcome
  available to this project**, because it would mean consolidation is not the mechanism and the
  diagnosis in §1 is wrong.

Nothing below is worth starting until this reads GREEN or the plan is rewritten around why it did
not.

### Phase G4 · Authoring on the consolidated basis (Phase D continues here)

Phase D's ceiling was measured, so it can be attacked at the measurement rather than by hoping.

* **D3 · Paired proof.** An authored artefact must beat NOT having it, on frozen items. This is the
  gate that separates code generation from intelligence — and it also fixes the honest defect D2
  exposed: the authored progress measure was unbounded because the generated test never required
  boundedness. *A property the gate does not demand is a property the authored thing will not have.*
* **D3.1 · Dimensional pruning.** A progress measure over counts must be dimensionally consistent —
  count/count is a rate, count−count is a count, count/rate is meaningless. Dimensions are derivable
  from what each field counts, so this is structure, not a hand rule, and it collapses the
  three-parameter space that currently enumerates 1134 candidates and fails.
* **D3.2 · Authored artefacts feed the library.** The learned library exists; the loop-authoring
  path does not reach it, so every request starts from bare ground. Closing that is what makes the
  basis grow instead of resetting.
* **D4 · Authoring unconstrained, installation gated.** Unchanged from v5. The leap is in authoring;
  only self-commit collides with wireheading immunity, and the operator boundary makes that gate one
  signature.

### Phase G5 · The self-extension loop closed

notice a missing operator → author it → **prove transfer** → operator-gated install.

The middle arrow is what makes this different from every previous "self-improvement" claim in this
repo: the loop cannot install what it cannot show generalises. Anti-cheat by construction, because
the trigger (a recurring gap) and the verifier (untouched domain B) are different quantities and
neither is under the loop's control.

### Folded in, no longer their own tracks

* **A-track (self-repair)** — now an INSTANCE that must show transfer like anything else, not a
  privileged engine. Its live lever remains: wire `acquire_referents` to a real evidence source so
  the loop's open questions actually get asked.
* **B-track (observation spine)** — B1/B2 landed and are what make transfer measurable at all; you
  cannot show B got cheaper without receipts from B. Remaining: per-organ receipts joined onto the
  cycle so the interior is replayable, and the `observed_at`/`elapsed_ms` ledger-record v2 bump
  (receipts stay timeless, records carry the wall clock).
* **C-track** — C2 (`src.col` ON for future ingest) only. C3 re-ingest stays DEFERRED on the C1
  numbers; revisit on encounter rate, never on prevalence.
* **E-track (deregulation)** — unchanged in principle and now correctly ordered: it is gated on
  transfer evidence, not on elapsed time or on observation count alone.

---

## 4. What is explicitly not the path

Stated because each of these is locally attractive and would consume the project.

* **More knowledge.** The graph is 115M edges and the walls measured this year were never density.
* **More organs.** 132 exist and the diagnosis is that they duplicate. A 133rd deepens the problem.
* **More hand-wired domains.** Training wheels. Each one buys a demo and costs generality.
* **Driving the merged residue to zero.** Fabrication wearing a metric's clothes.
* **Any generality claim not backed by a frozen-B measurement.** Including claims in this document.

---

## 5. Honest position

| | |
|---|---|
| organs | 132 |
| organs emitting receipts | 48 (36.4%) |
| organs declaring a tier | 7 |
| reflex-tier organs without receipts | 0 (was 2) |
| hard-merged subjects | 490,388 — 1.18%, ~5.0% of edges |
| authored-slot ceiling | 2 params verified · 3 params abstain after 1134 · 5 params never enumerate |
| cycles replayable losslessly | request boundary yes, organ interior no, default-OFF in production |
| **evidence at E4 or above** | **zero** |

Every number above is mechanism. The plan exists to convert exactly one of them — G3 — into
capability, and the rest of the sequence is contingent on it.

---

## 6. Second correction, same day: B was chosen on a plausibility that measured false

Traced the sealed eval's import path. `transfer_eval` exercises `fluency.realizer.realize` and the
`fluency_v1` scorers; between them the ONLY external package they reach is
`packages/realizer_struct`, and `realizer_struct` imports nothing outside itself. So the entire
channel from the shared substrate to B's measured behaviour is one 321-line package.

Then: `frame_realizer.py` contains **no selection-among-alternatives computation at all** — zero
hits for max / sorted / best / score / rank / argmax across 213 lines; it is a template realizer,
and its only `count` occurrences are regex substitution counts.

**Therefore the fluency seal cannot read positive for the discrimination-consolidation mechanism.**
Even if a real shared abstraction over the discrimination family exists and is factored out
perfectly, it has no path to fluency's numbers.

The B-selection criteria were: a deterministic eval, outside the A work area, and *plausibly*
standing on discrimination-shaped machinery. The first two were verified. The third was a guess,
and guessing is what this whole plan keeps catching itself doing.

### The criterion that was missing, and is now mandatory

> **B is admissible only when its evaluation path PROVABLY traverses the substrate the A-side work
> will change.** Verified by tracing the import graph from the sealed eval entry point, not by
> plausibility. A frozen domain with no mechanistic channel to the intervention is not a null
> result waiting to happen — it is a null result already, decided before any work is done.

### What happens to the fluency seal

It stands, and it is **not** re-cut. Re-freezing after learning something inconvenient is precisely
the move `freeze`'s refusal-to-overwrite exists to prevent, and the temptation arriving this fast is
the evidence that the refusal was worth building.

Its role changes honestly: **fluency is now a REGRESSION GUARD, not positive evidence.** It answers
"did consolidation break an untouched domain", which is a real question and the one the plan itself
called the most important thing this gate can find. It cannot answer "did capability transfer".

A second B must be selected with the channel criterion enforced.

## 7. The cheaper experiment that should have come first

The transfer gate is expensive and slow to read. There is a falsification available for a fraction
of the cost, and it does not need a frozen domain at all.

**The common form, stated precisely.** All four instances compute
`contrast(feature, target, background) -> score` and then threshold it. They differ only in the
CONTRAST:

| site | contrast |
|---|---|
| `_bridging` | share of the background the feature occupies, cut at a ceiling |
| `discriminative` | ratio of the target's rate to the mean over candidates |
| `organ_possessions` peers | the feature is held by the peer majority and not by the target |
| `read_schema` | agreement between the feature's rises and an observed label |

**The testable claim, and it is cheap.** If those contrasts are SUBSTITUTABLE, then every site is
currently stuck with whichever one its author happened to reach for, and consolidation's payoff is
that each site gains access to all four. That is measurable inside each site, with the site's own
existing metric, no frozen domain required:

* **G0 · Contrast substitutability probe.** Extract the four contrasts as one small family. At each
  of the four sites, swap in each contrast and re-run that site's own measurement.
* **Gate:** at least one contrast beats the incumbent at a site it was not written for. If NO
  contrast beats its incumbent anywhere, there is nothing to transfer, and the consolidation thesis
  is dead — cheaply, and before a second domain is frozen.

G0 now precedes everything. It is the falsification the plan should have opened with, and the fact
that it is being reached only after two disconfirmations is itself the lesson: **this plan has twice
asserted a mechanism and then measured it false, and both times the measurement cost less than the
assertion would have cost if believed.**

## 8. What G0 is a road to, stated so it is not over-claimed

G0 is **not** the semantic shared representation. It is the only way found so far to EARN one
instead of inventing it.

Building the representation directly would mean authoring an ontology of computations and bending
every organ into it — the 133rd-organ problem in a new costume, and a hand-written taxonomy is the
thing this plan forbids. Measuring substitutability instead makes the equivalence classes
DISCOVERED: two contrasts that can be swapped at a site are, empirically, doing that site's job,
and that relation is grounded in outcome rather than in syntax or in what I chose to call them.

The ladder, and no rung may be skipped:

1. **Interface.** `(feature, target, background) -> score`. Established by substitutability, and
   nothing more than plug-compatibility.
2. **Equivalence classes.** Which contrast is interchangeable where. Measured, not declared.
3. **A space.** Contrasts as points, distance = how similarly they behave ACROSS sites. This is a
   BEHAVIOURAL semantics: meaning defined by what a computation does in varying contexts rather
   than by its name or its shape. Only here does FHRR/VSA have something real to carry.
4. **Composition.** Only if (3) holds can contrasts be combined or interpolated into new ones.

**Why G1's failure was not waste.** G1 measured SYNTACTIC similarity and found the four instances
distinct. That eliminated one of the two candidate similarity metrics for this family. Behavioural
substitutability is the other one, and G1's negative result is precisely what motivates testing it.

**The ceiling, stated in advance.** Four sites by four contrasts is sixteen measurements. That is
far too small to build a space from. G0 can return exactly two things: a falsification (nothing
substitutes anywhere -> the consolidation thesis dies) or PERMISSION TO CONTINUE (something does ->
widen the site set). Claiming a representation from sixteen points would be the third time in one
day this plan asserted a mechanism ahead of its evidence.

### The control G0 needs, or it will produce a fake positive

A contrast may substitute at a site not because the contrasts are equivalent, but because **that
site's metric is too insensitive to tell them apart.** The two look identical in the results table
and only one is evidence.

> **Sensitivity control, mandatory per site:** before any swap is scored, run a DELIBERATELY BAD
> contrast — a constant, and a shuffled/random one. If the site's own metric does not degrade under
> them, that site cannot discriminate and its swap results are discarded, not counted as
> substitutability. Sites are admitted to G0 only after they fail the bad contrast.

This is the same discipline as the transfer gate's INVALID verdict: an instrument that cannot fail
is not measuring.

---

## 9. G0 RESULT — the gate reads negative, and the base shrank at every step

Run as pre-registered in §7. Reported whichever way it landed; it landed negative.

```
family            2 members   ratio_to_mean, rank_gap
non-members       2           read_schema, _bridging
sites offered     2
sites admitted    1           A1b REFUSED: metric 0.667 under a real contrast AND 0.667 under a
                              constant -- it cannot discriminate, so its swaps would be noise
A1c swaps         ratio_to_mean 1.000 (incumbent)   rank_gap 0.500
GATE              incumbent beaten anywhere: FALSE
```

**The four instances that launched this plan reduce, under measurement, to two computations sharing
an interface, tested at one site, where the incumbent wins.** Each step of the shrinkage was found
by a check rather than by inspection:

* `read_schema` takes two aligned SEQUENCES, not a value against a background.
* `_bridging` normalises by the POPULATION SIZE, which a background of other features' values cannot
  supply — and this was caught by the sign-convention TEST, not by reading the code: the
  re-expression normalised by the wrong quantity and inverted the ordering it was meant to preserve.
  The interface could have been widened to admit it; that was refused, because widening an interface
  to make a member fit is inventing a shape, which had already been refused for `read_schema`.
* A1b's own metric scores a constant contrast exactly as well as a real one. The sensitivity control
  added in §8 caught a site that would otherwise have contributed a meaningless row.

### What this does and does not establish

**Does not:** kill the consolidation thesis outright. One admitted site, two contrasts, six
judgements is far too small a base for that, and §8 said in advance that G0 can only falsify or
license — it cannot conclude.

**Does:** remove the specific mechanism plan v6 was built on. The claim was "the same operation,
written repeatedly, waiting to be consolidated". Measured: the syntactic version is false (G1, four
distinct shapes), the interface version has two members not four, and the behavioural version shows
no cross-site win at the single site able to report one. There is no longer a measured lever from
consolidation to capability.

### Standing position, third disconfirmation in one day

| claim | status |
|---|---|
| the same operation is written ~130 times | **false** — syntactic duplication is boilerplate: `to_dict` ×12, `_utc_now_iso` ×11 |
| four instances share one operation | **false** — four distinct shapes |
| four instances share one interface | **false** — two do, two do not |
| a contrast beats its incumbent elsewhere | **not found** — on one admissible site |
| fluency can register the effect | **false** — no mechanistic channel; regression guard only |

Every one of these was asserted by this plan and then measured false by an instrument this plan
built. That is the process working, and it is also the honest reading of where the project stands:
**there is currently no measured mechanism by which consolidation would produce generality.** The
next plan must start from that, not from a fifth assertion.
