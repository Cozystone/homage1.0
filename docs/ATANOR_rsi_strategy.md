# Completing RSI — a strategy grounded in what a day of running the loop measured

Owner asked for a strategy to finish recursive self-improvement. This is written after the loop ran
end to end: found its own defects, judged them, applied two patches that survived blind measurement,
diagnosed its own plateau, performed its own escape, enumerated its own evidence sources, and went to
the live web when it ran out. All of that works. RSI does not, and the ledger says so.

---

## 0. The finding that reframes everything: the metric is blind to what it measures

```
cycle                                      kind      gain
E5-1                                       product   0.1970
E5-2                                       product   0.0530
loop-stations-1-2-3                        capacity  0.0000
E5-2 (scored)                              product   0.0190
reachability-census (3 attempts)           capacity  0.0000
E5-3 (scored)                              product   0.0660
self-applied patch: able to -> capable_of  product   0.0906
self-applied patch 2: designed to          product   0.0385
escape performed: has_a added              capacity  0.0000
oracle expansion + shipped graph           capacity  0.0000
```

**Every capacity cycle scores exactly zero.** They score zero *by construction*: `gain` is measured on
a product metric, and a cycle that improves the improver moves no product metric on the day it lands.

And capacity cycles are the only kind that compounds. Product cycles accumulate — two patches, the
second worth less than half the first, which is ordinary fruit-picking. So `gains_holding` averages a
series in which the compounding cycles contribute nothing, and is structurally incapable of detecting
the thing it was built for. **The instrument, not the loop, is why RSI reads false.**

## 1. What compounding actually looked like, once, today

It did happen, exactly once, and it is visible in the record.

Fixing within-cluster discrimination — a capacity cycle, scored 0.0 — changed which proposals could
pass the judge. Before it: **zero survivors**. After it: `able to`, `designed to`, `intended to` became
proposable, and two of them became patches that survived blind measurement at **+0.0906 and +0.0385**.

So that capacity cycle *enabled* ~0.13 of product gain that was impossible before it. That number is
the compounding, and nothing in the ledger records it.

**Strategy element 1 — credit ENABLEMENT, not gain.** A capacity cycle is scored by the product gain
that became possible after it and was not possible before. Concretely: run the proposer before and
after, and the delta in *what survives the gates* is the enablement. Compounding is then a real
question with a real answer: is enablement per capacity cycle shrinking or not?

This is measurable today with data already on disk, and it replaces a metric that cannot move with one
that can.

## 2. What the loop still needs a person for — precisely

Every escape today was diagnosed by the loop and **built by a person**:

| the loop said | a person wrote |
|---|---|
| relation vocabulary is saturated | `relation_discovery` — test pairs against an external inventory |
| the discriminator is too weak | measure the FIRST token instead of the last |
| oracle coverage is the constraint | enumerate the seven files already on disk |
| relation evidence is genuinely absent | fetch under 2-domain consensus, disputed cue excluded |

Look at what those four changes actually *are*: swap which token is measured; read seven files instead
of one; add a filter; compare against a different table. **None is a novel algorithm.** They are moves
within a small structured space — change the signal, change the source, change the filter, change the
comparison set.

**Strategy element 2 — make the escape space TYPED and searchable, not free-form code.** The loop
cannot write an organ, and at 18.9% on MBPP it will not learn to soon. But it does not need to. If
escapes are expressed as a small vocabulary of transformations over the pipeline it already has —

```
SIGNAL      measure a different property of the same objects  (last token -> first token)
SOURCE      draw evidence from a different place              (one file -> seven -> the web)
FILTER      exclude something that was being included         (the disputed cue; already-covered cues)
COMPARISON  judge against a different reference set           (our rows -> an external vocabulary)
```

— then escaping is a SEARCH over four move types, each with a free oracle: apply it, measure
enablement, keep or revert. That is the same generate-and-verify shape the loop already runs on
patterns, lifted one level up to run on itself.

**This is the concrete route to closing the last gap**, and it does not require code synthesis to get
good first.

## 3. Why the plateau fires immediately after every escape

Measured: the loop escaped, added `has_a`, and the very next run plateaued again. That is not failure —
it is the signature of a **one-move-deep** search. The loop makes a move, exhausts what the move
opened, and stops.

**Strategy element 3 — escapes must compose.** A search over move types is only compounding if a
SIGNAL move can be followed by a SOURCE move on the result. Today each escape was hand-applied in
isolation. A loop that can apply two moves and measure the pair is doing something a person did today
by remembering the previous step.

The measurable gate: **does a two-move escape ever beat both of its one-move parts?** If never, the
moves are independent and this is accumulation with extra steps. If sometimes, that is compounding
with a mechanism.

## 4. The three floors, checked against today

The owner's framing — self-verification, infinite data, compute efficiency — held up, with one
correction and one addition.

* **Self-verification: solid.** Six times today an honest gate caught something, including three times
  it caught *me*: the judge defeated at scale, a "recursion" that was an abstention hole, a consensus
  result that was my own TypeError swallowed by a bare except.
* **Infinite data: a consequence, not a floor.** Once verification is honest, data generation follows
  from it — the web acquisition works precisely because consensus is the verifier. Solving the first
  gives the second.
* **Compute efficiency: reframe as VERIFICATION THROUGHPUT.** The rate-limiting step measured today
  was not electricity. It was 1.2 hours per B2 arm to test one change. At that rate the loop gets a
  handful of verified cycles a day, and with diminishing product returns that is very little. **Cheap
  proxies that correlate with the expensive gate are worth more than faster hardware.**
* **The missing floor: SELECTION.** Verification says whether a candidate is right; it never says which
  candidate to try or whether the question is worth asking. Today: 32 proposals, 31 refused — the
  verification worked perfectly and produced almost nothing, because selection was one shape wide.

## 5. What has no oracle, and therefore is not next

Stated so it does not get hand-filled, which is the failure this project keeps having to reverse:

* **aptness** — is this the right abstraction, the right question, the right thing to say
* **novel organ design** — inventing a move type not in the vocabulary above
* **relation invention proper** — proposing a predicate no external source names

These are the frontier. Building them without an oracle produces confident wrong answers, and a day
spent hand-writing register lexicons — 44% of which turned out not to exist in this codebase — is what
that costs.

## 6. The gates, in order, no dates

1. **Enablement scoring.** Credit capacity cycles with the product gain they unlock. Replaces a metric
   that cannot move. *(Free oracle: rerun the proposer before/after.)*
2. **Typed escape space.** Express the four move types as things the loop can apply and measure, not
   as things a person writes. *(Free oracle: apply, measure enablement, revert.)*
3. **Composed escapes.** Two moves, measured against both one-move parts. *(Free oracle: same.)*
4. **Cheap proxy for the expensive gate.** Something that predicts the 1.2-hour B2 result in seconds,
   with its correlation measured and stated. Verification throughput is the real budget.
5. **Enablement not shrinking across capacity cycles.** This is RSI, and it is a chart, not an opinion.

## 7. One sentence

The loop is not failing to compound; it is compounding invisibly and rarely — once today, unrecorded —
and the work is to measure enablement, give escapes a vocabulary they can search instead of a person
to write them, and make verification cheap enough to run the search.
