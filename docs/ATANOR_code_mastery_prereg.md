# Code mastery — external benchmark pre-registration

Written **before** the benchmark data is downloaded or inspected, so that what counts as a result is
fixed by the design rather than chosen after seeing the numbers.

## Why this measurement exists

`mastery_v1` reports **40/40, fail 0, abstain 0**. That number is close to meaningless as evidence of
capability, and the reason is structural: I wrote the tasks *and* the algorithm schemas that solve them.
A curriculum authored by the same hand that authors the solver measures the hand, not the capability. The
project's own doctrine already says this — a sealed, externally-authored holdout is the only thing that
counts as capability evidence.

The gap between "40/40 on my own tasks" and "writes code like a senior engineer" is, right now, entirely
unmeasured. This pre-registration puts the first honest coordinate in that gap.

## What is measured

**MBPP** (Mostly Basic Python Problems, Austin et al. 2021) — ~974 tasks, each a natural-language
description plus assert-style tests. It maps onto `authorship_harness.Task` without reshaping: description
→ `docstring`, the tests → `test`, the function signature recovered from the tests. Nothing about the task
is rewritten to suit the engine; a task the engine cannot parse counts as an abstention, not an exclusion.

MBPP is chosen over HumanEval because its tasks are assert-based (a direct fit for the existing verifier)
and because it is large enough to split into a tuning half and a sealed half — which is the part that
actually protects the result.

## The split, and why it is the whole point

The real risk is not a bad first number. It is tuning the engine against the benchmark and then reporting
that benchmark — the failure this project has hit before, and the reason `mastery_v1` is weak evidence.

So MBPP is split **once, by task id parity, before any measurement**:

- **TUNE slice** (even ids) — may be inspected, iterated against, and used to grow the schema library.
- **SEALED slice** (odd ids) — measured once now to establish the baseline, then **not looked at again**
  until a later run, after which it is re-sealed with a fresh unexamined slice if it has been contaminated.

Any future claim of improvement must show it on the sealed slice. An improvement visible only on the tune
slice is memorization, and will be reported as such.

## The engine state being measured

The engine is measured **exactly as it stands** — the code committed before this document. No schema is
added, no family is widened, no cue is tuned for MBPP first. That is what makes this a baseline rather than
a demonstration.

## What counts as what

There is **no pass/fail threshold**, because there is no prior to bet against — this is a first
measurement, and inventing a threshold now would only create the temptation to report a favourable one.
What is recorded instead, for both slices:

- **solve rate** — verified bodies / total tasks
- **abstention rate** — the honest floor; abstaining is not failure
- **fabrication rate** — shipped bodies that fail held-out tests. **This must be 0.** It is the one number
  that is a gate: a body that passes the visible tests but fails held-out tests means the no-fabrication
  floor leaked, and that is a defect regardless of how good the solve rate looks.
- **by source** — library / skeleton / composition / schema / induced, so growth can be attributed

## Stated in advance: the expected shape of the result

Recorded now so it cannot be revised afterward. The engine's families are domain-blind structures over a
handful of shapes; MBPP contains many tasks needing string formatting, regex, bespoke arithmetic, and
library calls that no family reaches. **I expect a low solve rate — plausibly under 20% — with high
abstention and zero fabrication.** If the number comes in far higher, the first suspicion is a leak in the
harness (e.g. tests visible to the search that should be held out), not a triumph; it gets audited before
it gets reported.

## Result

Run 2026-07-31, `data/code_reason/mbpp_external.json`, engine frozen as committed.

| | TUNE (even ids) | SEALED (odd ids) |
|---|---|---|
| solved | 89 / 486 | 92 / 487 |
| **solve rate** | **18.3%** | **18.9%** |
| abstention | 81.7% | 81.1% |
| **fabrication** | **0** of 89 | **0** of 92 |
| by source | skeleton 51, composition 35, library 2, schema 1 | skeleton 59, composition 32, schema 1 |

### The pre-registered prediction was correct

Written above before the data was downloaded: *"plausibly under 20% — with high abstention and zero
fabrication."* Measured: 18.3% / 18.9%, 81% abstention, 0 fabrication. Recording this because the
prediction was cheap to make and would have been embarrassing to get wrong in either direction — a much
higher number would have meant a harness leak, and it was pre-committed that a high number gets audited
before it gets reported.

### The two slices agree, which is the useful part

18.3% vs 18.9% — within 0.6 points across 973 independently authored tasks. The measurement is stable and
not an artifact of which half was drawn. That makes the sealed slice a usable yardstick: a later run that
moves it by more than a couple of points has moved something real.

### The finding that matters: the elaborate schemas are nearly dead weight

`mastery_v1` scores 40/40 largely on the algorithm-schema organ — DP-2D, topological sort, backtracking,
graph traversal, keyed-store, induced value-maps. On MBPP that entire organ contributes **2 solves out of
181** (one `scanrun`, one `stackscan`). Everything else came from the simplest families: bare expression
skeletons (110) and 2-3 stage compositions (67).

This is direct evidence for the cascade pathology already recorded in this project — depth invested in the
wrong layer. The schemas were built to clear tasks I wrote, and they clear those tasks, and they do almost
nothing on tasks somebody else wrote. Adding a thirteenth schema is now measurably the wrong move; the
solve rate lives in the cheap families and in whatever would let the engine reach the 81% it abstains on.

### The fabrication-zero result is real but weakly measured — stated plainly

Only **11 of the 181 solved tasks had held-out tests at all** (6 in tune, 5 in sealed), because MBPP's
`challenge_test_list` is empty for most problems. So "fabrication 0" rests on 11 checks, not 181. It is
consistent with the no-fabrication floor holding on an external benchmark, and it is *not* strong evidence
of it. The stronger design — holding back one of the three visible asserts on every task — was not used
here because it would make the solve rate incomparable to published MBPP numbers. A follow-up run in that
configuration is the honest way to actually establish the floor.

### Context, so 18.9% is read correctly

Strong LLMs report roughly 60–80% on MBPP. This engine is well below that and abstains on four fifths of
the benchmark. That is the true starting coordinate, and it is the number any future claim of code
improvement has to move — on the sealed slice, which has now been spent once and should be treated as
consumed if it is ever tuned against.
