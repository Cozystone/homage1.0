# E5-2 · The transfer gate, two arms this time — pre-registration

Written **before** any A-side change, and cut against a frozen snapshot of the extractor as it stands.

## 0. Why a second E5

E5-1 passed, on one arm. Its B1 arm was void because I cut the baseline over the whole 6.9M-page corpus
and measured a 200k slice, so the two numbers never described the same thing. A post-hoc closeout later
showed B1 did transfer (+13.3% on a fair same-slice comparison), but a post-hoc measurement is not a
sealed arm — A was already committed and B2's direction was already known.

So this run exists to produce what E5-1 could not: **two arms, both measured blind, against baselines
cut beforehand on exactly the procedure that will be re-run.**

## 1. The defect that voided B1, and how it is closed

The baseline must be produced by the *identical procedure* as the measurement it will be compared to.
Not the same metric — the same **procedure**, on the same **slice**, with the same **page count**.

`scripts/e5_b1_closeout.py` does this by construction: it streams one fixed slice of the dump and runs
**two extractors over the same sentences**, so page order, lead selection and subject filtering are
shared and the extractor is the only difference. Rerunning `wiki_property_sweep` could not do this — it
dedups against rows already on disk, so a second pass is scored against a ledger the first pass filled.

The frozen pre-change extractor is snapshotted at
`data/e5_transfer_seal_2/property_extraction_FROZEN_A.py` (sha256 `82a9039a9768c797…`). Scoring runs the
frozen file against the live one on the same 200,001 pages.

## 2. A — what will be worked on, and why it is justified without looking at B

The A-side change must be driven by A's own measured failures. `scripts/gloss_lane_recall.py` was
committed before this seal and reports, on a deterministic 40,000-gloss slice:

    3,092 rows · 77.3 per 1k glosses · CUE RECALL 0.5931

Two fifths of glosses that visibly state a property yield nothing. Reading the misses gives the change:

* **The object span is `[a-z][a-z\- ]*`**, so a capital letter or an accent aborts the match:
  *"used to oversee European Commission implementing acts"*, *"used in solfège"*.
* **The terminator set `[,.;:]` has no parenthesis**, so *"used to determine the cardinal directions
  (usually magnetic or true north)"* never closes.

Both are recall losses on spans the extractor already means to capture — proper nouns and parentheticals
are ordinary dictionary prose, not a new relation.

**What will NOT be added, recorded so the restraint is auditable:** `consisting of` is the single largest
missed cue (49 of the sampled misses) and is deliberately left alone. Its glosses are *"millennium:
consisting of one thousand years"*, *"United States: consisting of fifty states"* — that is `has_part`,
not `made_of`, and mapping it would inject a category error at scale.

## 3. B — frozen, and untouched from this moment

| file | role |
|---|---|
| `scripts/wiki_property_sweep.py` | B1 lane |
| `scripts/run_acquisition_daemon.py` | B2 lane |
| `packages/acquisition_daemon/daemon.py` | B2 |
| `packages/knowledge_acquisition/loop.py` | B2 |
| `packages/knowledge_acquisition/consensus.py` | B2 |
| `packages/knowledge_acquisition/evidence.py` | B2 |
| `packages/atanor_index/retriever.py` | B2 |
| `data/acquisition_daemon/deficit_questions.txt` | B2 corpus |
| `scripts/e5_b1_closeout.py` | B1 measurement procedure |

Any change to one of these **voids the run**. Not penalised — void. The entire content of E5 is that B
improved *without being touched*.

## 4. Baselines, measured on the exact procedure that will be re-run

| metric | baseline | how it is re-measured |
|---|---|---|
| **B1-rows** | 6,768 | `e5_b1_closeout.py --pages 200000 --old <FROZEN_A>` → `rows_new` |
| **B1-per_1k** | 33.8398 | same run → `per_1k_pages_new` |
| **B2-queued** | 785 | the daemon command below, `queued` |
| **B2-pursued** | 26,349 | same run — a control; it must come back identical |

B2 command, fixed:

```
python scripts/run_acquisition_daemon.py --local --table --no-curiosity \
  --questions data/acquisition_daemon/deficit_questions.txt --batch 600 --min-pressure 2 \
  --state data/acquisition_daemon/e5_2_b2
```

## 5. The gate

**PASS** iff **both arms** rise by **≥5% relative** and neither degrades:

* B1-rows ≥ 7,106 (+5% of 6,768)
* B2-queued ≥ 824 (+5% of 785)
* B2-pursued unchanged at 26,349 — if the work done changes, the yield comparison is not clean

**One arm rising is a FAIL for this gate**, which is the whole point of running it again. E5-1 already
established that one arm can rise; what is unproven is that transfer shows up in both places at once.

**INCONCLUSIVE COUNTS AS FAIL.** A metric that cannot be reproduced is a missing measurement.

## 6. Stated in advance

B1 should rise: the change targets exactly the spans Wikipedia leads are full of — proper nouns
("used in European diplomatic contexts") and parentheticals. B2 is less certain; it draws on the
property table and local index rather than raw prose, so the new rows have to survive consensus to
count. **I expect B1 to clear +5% comfortably and B2 to be the arm at risk.** If B2 fails, the honest
reading is that transfer is real but narrower than E5-1's single arm suggested — and that is a result
worth having, not a disappointment to explain away.

## 7. Result

**FAIL. B1 +5.3%, B2 +1.9%. The gate takes the minimum, and B2 did not clear +5%.**

Scored 2026-07-31, `data/e5_transfer_seal_2/verdict.json`. Seal integrity at score time: **B files 9/9
unchanged**, frozen extractor unmoved, A changed as intended.

| metric | baseline | required | measured | |
|---|---|---|---|---|
| B1-rows | 6,768 | ≥ 7,106 | **7,127** | **+5.3%** ✔ |
| B1-per_1k | 33.840 | — | 35.635 | +5.3% |
| B2-queued | 785 | ≥ 824 | **800** | **+1.9%** ✘ short by 24 |
| B2-pursued | 26,349 | = 26,349 | **26,349** | control held exactly |

### This is a clean failure, which is what makes it worth more than E5-1's pass

E5-1 passed on one arm because its other arm was **void** — a baseline cut over the whole corpus and
compared against a slice, measuring nothing. That was an instrument defect, and it left the shape of
transfer unknown.

Here nothing is void. The control came back bit-identical (26,349 questions pursued, the same work on
the same questions through byte-verified unchanged code), the B1 baseline reproduced exactly (6,768),
and both arms are real numbers. **The failure is a measurement, not a malfunction.**

### What it actually says: transfer is real, and it attenuates

The A-side change lifted the gloss lane (cue recall 0.5931 → 0.6138) and reached B1 at +5.3%, but only
+1.9% by the time it reached B2 — **roughly a third of the relative gain survives the trip.**

The pipelines explain it, and the prereg predicted it. B1 reads raw Wikipedia prose, so extractor
output lands almost directly. B2 goes through the property table, the local index and a consensus
requirement: a newly-extracted row only counts once it is corroborated. Extra rows that no second
source confirms are exactly what consensus is for, and they do not reach the queue.

So the honest reading is not "transfer failed". It is: **a change to the shared substrate propagates
to consumers in proportion to how directly they read it, and a consumer behind a consensus gate sees a
fraction.** That is a fact about the architecture worth more than a green light, and it could not have
been learned from E5-1, whose single arm was the one that reads prose directly.

### What was predicted, and what was wrong

Recorded in §6 before the run: *"I expect B1 to clear +5% comfortably and B2 to be the arm at risk. If
B2 fails, the honest reading is that transfer is real but narrower than E5-1's single arm suggested —
and that is a result worth having, not a disappointment to explain away."*

The direction was right. **"Comfortably" was wrong** — B1 cleared by 21 rows out of 7,106, which is
not comfort, and a threshold set slightly higher would have failed both arms.

### Consequences, taken rather than argued around

* **Two-arm transfer remains unproven.** ATANOR has one E5-shaped result (E5-1, one arm) and one clean
  negative (this). The ladder does not advance.
* **A one-arm E5 should never again be read as general transfer.** E5-1's +19.7% was measured on the
  arm that reads prose directly — the easy case, now known to be the easy case.
* **The next A-side change should be measured against B2 as the harder consumer**, and a gain that
  clears consensus is worth more than the same gain in raw yield.
* The E5-1 verdict stands as recorded. It is not revised downward — it measured what it measured — but
  it should be read alongside this.
