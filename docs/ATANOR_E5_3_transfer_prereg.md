# E5-3 · Transfer measured on the HARD consumer — pre-registration

Written before any A-side change, against a frozen snapshot of the extractor
(`data/e5_transfer_seal_3/property_extraction_FROZEN_A.py`, sha `5fc2d2e81dcee9f3…`).

## 0. What E5-2 established, and why this run is shaped by it

E5-2 failed cleanly: B1 +5.3%, B2 +1.9%, control bit-identical. That was not a malfunction, it was a
measurement, and it said something the passing E5-1 could not:

> A change to the shared substrate reaches a consumer in proportion to how directly that consumer
> reads it. B1 takes extractor output almost straight from prose. B2 goes through the property table,
> the local index and a **consensus** requirement, and roughly **a third** of the relative gain
> survives that trip.

So B1 is the easy arm and always was — E5-1's celebrated +19.7% was measured on it. **The hard arm is
the gate from here on.**

## 1. A — the change, and the measurement that chose it

The last two A-side changes both raised RECALL, which is what B1 rewards. B2 rewards CORROBORATION: a
row counts only once a second source confirms it. So recall is the wrong lever for B2, and the right
one had to be measured rather than guessed.

Measured on the candidate rows already on disk, agreement against ConceptNet by object length:

| words in object | used_for | capable_of |
|---|---|---|
| 1 | **0.441** | **0.185** |
| 2 | 0.229 | 0.000 |
| 3 | 0.219 | 0.020 |
| 4 | 0.250 | 0.062 |
| 5 | — | 0.000 |

**A single-word object is corroborated 2–9× more often than a multi-word one, and the drop starts
immediately at two words.** Which means E5-1's cap raise (4→6 words) bought B1 exactly the rows B2
cannot use.

The obvious response — shorten the objects — is wrong, and known to be wrong: bare stubs like
*"lung cancer capable_of originate"* are what E5-1 FIXED. So the proposal is to emit both. Measured on
multi-word objects only:

| | used_for (n=114) | capable_of (n=167) |
|---|---|---|
| full span alone | 0.228 | 0.018 |
| + first content word | 0.447 | 0.150 |
| + last word | 0.439 | 0.108 |
| **either matches** | **0.605** | **0.228** |

**The change: alongside a multi-word object, emit head-normalised companion rows.** The graph keeps
the specific fact; consensus gets a form it can match. 2.7× and 12.7× more corroborable, without
giving back what E5-1 won.

## 2. B — frozen from this moment

`wiki_property_sweep.py`, `run_acquisition_daemon.py`, `e5_b1_closeout.py`,
`acquisition_daemon/daemon.py`, `knowledge_acquisition/{loop,consensus,evidence}.py`,
`atanor_index/retriever.py`, `data/acquisition_daemon/deficit_questions.txt`.

Any change to one voids the run.

## 3. Baselines — the post-E5-2 state, same procedures

| metric | baseline | re-measured by |
|---|---|---|
| B1-rows | 7,127 | `e5_b1_closeout.py --pages 200000 --old <FROZEN_A>` |
| B1-per_1k | 35.6348 | same run |
| **B2-queued** | **800** | the daemon command, `--state data/acquisition_daemon/e5_3_b2` |
| B2-pursued | 26,349 | same run — the control |

## 4. The gate — inverted, because the arms are not equally hard

* **B2-queued ≥ 840** (+5% of 800). This is the gate.
* **B1-rows may not regress** (≥ −0.5%). Not a rise requirement — a floor. A gain on one consumer
  bought by losing the other is not transfer, it is a trade.
* **B2-pursued must return 26,349.** If the work changed, the yield comparison is not clean.

**INCONCLUSIVE COUNTS AS FAIL.**

## 5. Stated in advance

Head rows are shorter and less specific, and the honest risk is that they are *junk that happens to
match* — corroboration bought by saying less. Two things bound it: the full span is still emitted, so
nothing informative is lost; and B1, which rewards richness, must not fall.

**I expect B2 to rise, but by less than the 2.7×/12.7× the agreement study suggests** — that study
measured corroborability against ConceptNet, while B2's consensus is a different check over different
sources, and a lever measured on one oracle rarely transfers whole to another. Clearing +5% is the
claim; anything near the agreement-study multiple would be suspicious and gets audited before it is
reported.

If B2 fails again with B1 held, the reading is that the consensus gate is bounded by SOURCE COVERAGE
rather than by object form — that no rewriting of what we extract will help, because the second source
simply is not there. That would redirect the work from extraction to acquisition, and it is worth
knowing.

## 6. Result

**PASS. B2 +6.6% on the arm E5-2 proved is the hard one, with B1 held.**

Scored 2026-07-31, `data/e5_transfer_seal_3/verdict.json`. Seal integrity at score time: **B files 9/9
unchanged**, frozen extractor unmoved, A changed as intended.

| metric | baseline | required | measured | |
|---|---|---|---|---|
| **B2-queued** | 800 | ≥ 840 | **853** | **+6.6%** ✔ the gate |
| B2-pursued | 26,349 | = 26,349 | **26,349** | control held exactly |
| B1-rows | 7,127 | ≥ −0.5% | 12,299 | +72.6% ✔ floor |
| B1-per_1k | 35.635 | — | 61.495 | +72.6% |

### What this establishes, and what it does not

**Establishes:** a change to the shared substrate reached the consumer that sits behind a consensus
gate — the one E5-2 measured at +1.9% and failed on. The chain that produced it is fully recorded:
E5-2's clean failure said transfer attenuates through consensus; the diagnosis said B2's lever is
corroborability rather than recall; the measurement said corroborability collapses at two words
(used_for 0.441 → 0.229, capable_of 0.185 → 0.000); the change emitted head forms alongside the full
span; B2 moved from +1.9% to +6.6%.

**Does not establish:** that B1's +72.6% is a capability gain. It is not, and this was written down
before the run. Head rows multiply rows per object, so a yield metric rises mechanically. That is
exactly why the gate asked B1 only not to regress. **Reading +72.6% as the headline would be the
easiest false claim available today**, and it is not the result.

### The prediction, checked

Registered in §5: *"I expect B2 to rise, but by less than the 2.7×/12.7× the agreement study suggests
— a lever measured on one oracle rarely transfers whole to another. Clearing +5% is the claim;
anything near the agreement-study multiple would be suspicious and gets audited before it is
reported."*

+6.6% against a ConceptNet-measured 2.6× improvement in corroborability. The lever transferred, and it
transferred **small** — precisely the shape predicted, and the audit clause did not have to fire.

### Where E5 stands after three runs

| run | arms | verdict |
|---|---|---|
| E5-1 | B2 +19.7%, B1 void | PASS on one arm; the void was an instrument defect I introduced |
| E5-2 | B1 +5.3%, B2 +1.9% | clean FAIL — and the run that taught the most |
| **E5-3** | **B2 +6.6%**, B1 held | **PASS on the hard arm** |

Two passes and one failure, and the failure is what made the second pass possible. What is now
supported: a shared-substrate change reaches a direct consumer strongly and a consensus-gated consumer
weakly, and the weak path can be improved by targeting corroborability. What is still not supported:
that both arms clear a shared threshold in one run — E5-2 asked for that and got a no.
