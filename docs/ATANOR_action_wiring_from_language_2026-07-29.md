# Wiring an action that was never wired

**2026-07-29. Owner's question, and it reframes the whole problem:**

> 근데 고민은 atanor가 할 수 있는 무궁무진한 행위에 대해 일일히 다 매칭을 시킬 순 없잖아. 처음 보는
> 요청을 받아도 이걸 어떻게 배선시켜서 시행하면 될지 즉석에서 생각해내는게 맞는거 아니야? 배선 안된건
> 못하는 게 아니라.

That is the correct objection and it kills the obvious repair. Adding `avoid`, `eat`, `chase` to a
handler table would make today's demonstration work and would leave the architecture exactly as
broken, because the next sentence uses a verb that is not in the table. A system whose action
vocabulary is the size of its handler table is not going to be general no matter how large the table
gets. **The wiring itself has to be derived at request time.**

This document is the research and the plan. It is written because the codebase currently contains the
failure in its purest form — `packages/affordance/context_affordance.py` loads **five** hand-written
affordance entries, keyed by Korean cue words — and because the assets needed to replace it are
already here and already measured.

---

## 1. What is actually broken, stated precisely

Today's audit found three facts that are one fact:

| where | what | evidence |
|---|---|---|
| ingestion | the sentence→structure path recognises **31 verbs**, all definitional (`is`, `contains`, `refers`, `describes`…) | `ENGLISH_VERB_LEMMAS`, `cgsr/ingestion/decomposer.py` |
| comprehension | imperatives are unparseable **by construction** — position 0 is excluded from the verb search, and verbs are found by an `(ed\|es\|s)$` suffix, so plural nouns become verbs | `situation_model/builder.py:151,153` |
| action | the affordance layer is a catalogue of 5 hand-written entries | `affordance/context_affordance.py` |

And it explains a fourth, measured in the Atari line the same day: the agent **dies more often than
random** because death pays exactly 0 reward, so the learner cannot see it. Language has no `avoid`;
the game has no cost for being caught. Both are the same hole: **the system has representations of
static facts and none of actions-and-their-consequences.**

Meanwhile the same codebase generates fluent English and answers multi-hop questions. That is not a
contradiction: **speaking and understanding are different organs here, and only the intake is empty.**
ATANOR has memorised an encyclopedia and can talk from it; it cannot read a new sentence.

---

## 2. How humans avoid needing one handler per verb

Six mechanisms, each with what it implies for architecture. These are the load-bearing ones; the
citations are anchors, not authority.

### 2.1 The basis is small because verbs are not primitive — image schemas are

Before language, infants already represent SOURCE-PATH-GOAL, CONTAINER, CONTACT, SUPPORT, BLOCKAGE,
ATTRACTION, LINK, NEAR–FAR, PART–WHOLE, and FORCE (Mandler; Lakoff & Johnson). Talmy's force dynamics
covers the whole *avoid / block / let / make / prevent* family with two participants and a tendency
parameter. There are on the order of **twenty** such schemas and they underlie the action vocabulary
of every human language.

> **Implication:** you wire ~20 schemas, not ~10,000 verbs. Wiring cost becomes O(1) in vocabulary.
>
> **ATANOR already has about six of them, implemented and validated**: `WorldState` tracks `loc`
> (containment/place), `holding`/`holder_of`/`gives` (possession and transfer), `spatial_edges`/`adj`
> (relative position and topology), `traj`/`motions` (path), `bigger` (scalar order), and `belief`
> (theory of mind). bAbI 0.9755 was earned on exactly this basis. **The idea is not speculative here;
> it is the part that already works.**

### 2.2 Levin classes: 10,000 verbs collapse to ~50 by their syntax

Levin (1993) showed English verbs group into ~50 classes by which syntactic alternations they permit,
and that class membership predicts meaning components. The mapping vocabulary→basis is therefore not
memorisation of 10,000 entries but classification into a few dozen.

### 2.3 Syntactic bootstrapping: an unseen verb gets its structure from its frame

Naigles (1990): two-year-olds hearing *"the duck is gorping the bunny"* infer that *gorp* is causative;
hearing *"the duck and the bunny are gorping"* infer it is not. **From the frame alone, with no
referent and no prior exposure to the word.** The syntactic frame carries the argument structure.

> **Implication:** the parser must return *frames*, not look up verbs. `[V NP]` tells you there is an
> agent and a patient before you know what the verb means. This is precisely what `builder.py` cannot
> do, and precisely what a learned frame tagger would do for words it has never seen.

### 2.4 Where the schema comes from for a word never encountered — two routes, both already available

- **Distributional.** Verbs sharing contexts share schemas; a learned verb-embedding → schema
  classifier generalises to unseen verbs by proximity. This is the project's standing
  *learned-discriminator* doctrine applied to a new target.
- **Definitional.** Dictionaries define rare verbs with common ones — *shun: to avoid deliberately*.
  Humans acquire most of their vocabulary this way, not from experience. ATANOR already ingests Kaikki
  and already computed dominant senses from it.

### 2.5 Ideomotor coding: a verb should compile to a *preference over futures*, not to a procedure

James's ideomotor principle, and its modern form in common-coding theory (Prinz; Hommel): actions are
represented by their **effects**, not their motor details, and selecting an action means imagining its
outcome. You do not have a motor program for "avoid"; you have a predictor and a preference.

> **This is the central architectural claim of this document.**
>
> `avoid X` → prefer futures where distance to X stays large
> `eat X`   → prefer futures where X becomes contained in me
> `chase X` → prefer futures where distance to a moving X shrinks
> `guard X` → prefer futures where distance to X stays small **and** others' distance to X stays large
>
> Every one of those is the same executor with a different scoring function. **No handler is ever
> written.** The only table is schema → scorer, and it has ~20 rows because §2.1 says so.

### 2.6 Two speeds: novel actions are slow and effortful, then they compile

Humans do not execute a genuinely novel instruction fluently. They reason it out, simulate, try, and
it becomes automatic with practice (Fitts & Posner: cognitive → associative → autonomous). The failure
mode for an unwired action is *slow*, not *impossible* — which is exactly the owner's point.

> **Implication:** the system should **compile its own wiring and cache it**. First encounter runs the
> slow path (parse → schema → simulate → search). Repetition promotes it to a stored policy. ATANOR
> already has both halves: the DELIBERATOR for the slow path and a promotion gate for caching.

---

## 3. The proposed architecture

```
  a sentence nobody anticipated
        │
        ▼
  [LEARNED] frame tagger        →  argument structure          works on unseen verbs (§2.3)
        │                            (agent, patient, path…)
        ▼
  [LEARNED] verb → schema       →  one of ~20 image schemas    generalises by embedding / gloss (§2.4)
        │
        ▼
  schema + arguments            →  GOAL FUNCTIONAL over        the ONLY hand-written table,
        │                            predicted world states     ~20 rows, closed (§2.1, §2.5)
        ▼
  world model rolls futures     →  search picks the action     ONE generic loop, no per-verb code
        │
        ▼
  outcome cached                →  compiled policy             slow path becomes fast path (§2.6)
```

**Wiring cost is O(1) in the number of verbs.** Nothing is added to the codebase when a new verb
arrives. That is the whole point, and it is the property the current design lacks.

### What each stage needs, and what already exists

| stage | needs | state today |
|---|---|---|
| frame tagger | predicate–argument head over a sequence encoder | backbone exists (`Ace2Encoder`, 325k steps) but has **no such head** — its heads are RTD, answerability, span start/end, support |
| verb → schema | ~20-way classifier over verb embeddings + gloss fallback | does not exist; Kaikki glosses and the graph are available |
| schema → goal functional | ~20 scorers over typed relations | the **relations** exist (`WorldState`); the scorers do not |
| predict & search | a forward model and a rollout loop | measured in the Atari line: constant-velocity ghost prediction, 2.19 px error at turns, and `splatra_worldmodel/jepa.py` for the visual case |
| caching | promotion of a derived policy | `candidate_promotion_gate` exists |

---

## 4. The falsification test, registered before anything is built

A system that executes `avoid`, `eat`, and `chase` because those three were built is a lookup table
with extra steps. The only test that separates composition from tabulation:

> **It must correctly execute verbs it has never seen, supplied only as a sentence.**

Three tiers, in ascending difficulty, all measurable in Ms. Pac-Man where behaviour is scoreable:

1. **held-out synonym** — `shun the ghosts`, `devour the pellets`. Never in any table.
2. **held-out schema-mate** — `flee from the ghosts`, `hoard the pellets`: different syntactic frame,
   same schema.
3. **invented word with a gloss** — `gorp the ghosts`, where the only information is
   *"to gorp is to keep away from"*. This tests §2.4's definitional route with no distributional
   support whatsoever.

Success is **behavioural, not parse-level**: deaths per thousand steps must fall for the avoid-family
and pellets per thousand steps must rise for the eat-family, against the random control measured in
the same run. A correct parse that does not change behaviour counts as a failure.

---

## 5. Order of work

The executor is built first, and deliberately **before** any language touches it.

**Rung A — the goal functional alone, no language at all.**
Hand the existing agent a scoring function over *predicted* states (`maximise distance to the moving
things`) and search over the predictor already measured today. No parser, no verb, no schema.

This is the decisive first test because of what today's Atari audit found: **death pays exactly zero
reward**, so no reward-based learner can avoid it. A preference over predicted futures needs no reward
signal at all — which is precisely the ideomotor claim in §2.5. If deaths do not fall, the executor is
wrong and every layer above it is pointless. If they do, the hardest measured problem of the day is
solved by the mechanism the language layer will later target.

**Rung B — schema → goal functional, verb supplied by hand.**
Wire three schemas (repulsion, attraction-to-consumable, pursuit) to scorers. Still no parser. Confirms
that the ~20-row table is expressive enough to cover distinct instructions with one executor.

**Rung C — the learned frame tagger.**
A predicate–argument head on the existing backbone. This is the piece that was never trained and is
the actual missing organ. Held out: imperative sentences, which the current path cannot represent at
all.

**Rung D — verb → schema, and the falsification test in §4.**
Only here does an unseen verb get executed. Until D passes on tier 3, no claim about generality is
available.

---

## 6. What this document may not be used to claim

Nothing here is a result. Rungs A–D are unbuilt. The measured facts it rests on are: the 31-verb
lexicon, the two lines in `builder.py`, the five affordance entries, the absent predicate-argument
head, and today's Atari numbers (deaths 12.4 vs random 11.0 per thousand steps; death reward 0.00
across 16 deaths). Everything else is a plan, and plans are not evidence.
