# E5 · The transfer gate — pre-registration

**Sealed 2026-07-31, before any work on the A side.** Nothing below may be edited after the first A-side
commit. A seal re-cut after seeing a result is not a seal.

---

## 0. Why this pre-registration exists and why it does not follow the v6 plan literally

`docs/ATANOR_completion_plan_v6_generality_2026-07-28.md` specifies E5 as: freeze B, consolidate the
operators G1 found in A, re-run B. That document then **corrected itself the same day**:

> G1 measured the four functions' structural signatures and got **four distinct shapes**, so the gate
> this document set for G1 reads FAIL. […] the widest [duplications] are BOILERPLATE: `to_dict`
> (12 organs), `_utc_now_iso` (11) […] Consolidating those is worth doing and will not move a
> capability metric. […] **G3's A-side lever is weaker than this plan assumed.**

Running the literal G3 would therefore burn a seal on a lever the plan itself records as unproven. The
likely null result would say "consolidating `to_dict` did not help" and would enter the record as "E5
negative", which is a different and much larger claim. So this pre-registration keeps the v6 GATE exactly
— freeze B, work A, B must move untouched — and replaces the A-side lever with one there is evidence
for.

**The substituted lever is a shared extractor, not a deduplication.** `packages/graph_scale/
property_extraction` is a single judgement called by four unrelated consumers built on different days
for different purposes. If improving it for ONE register moves an UNTOUCHED consumer, the machinery
generalised. If it does not, it was four consumers that happen to import the same file, and that is the
disease this project keeps diagnosing.

**This is a NARROW E5 and is labelled as one.** It measures transfer between text registers sharing one
extractor. It is not evidence that vision transfers to mathematics, and any later citation of it as
general transfer is a misquote of this document.

---

## 1. Domains

**A — worked.** Dictionary definition glosses (`data/graph_scale/kaikki-en.jsonl.gz`, noun entries).
Only gloss-lane metrics may be inspected while working. This is the register the extractor was first
written against, so it is where improvement is cheapest and least surprising.

**B — frozen, untouched.** Two consumers, chosen because neither shares A's register, its corpus, or its
call site:

* **B1 · Wikipedia lead sweep** — `scripts/wiki_property_sweep.py` over
  `data/knowledge_sources/enwiki-full.xml.bz2`. Encyclopedic lead sentences, not dictionary definitions.
* **B2 · Live acquisition loop** — `scripts/run_acquisition_daemon.py --local --table` over the
  26,544-question deficit set. Consensus over retrieved documents, not offline mining.

---

## 2. Metrics, fixed now

| id | metric | measured today | how it is re-measured |
|----|--------|----------------|------------------------|
| B1-yield | facts per 1,000 pages | see `seal.json` | re-run the sweep on the SAME first N pages |
| B1-agree | ConceptNet agreement, `used_for` | 0.471 (n=87) | same script, same corpus slice |
| B1-agree-c | ConceptNet agreement, `capable_of` | 0.235 (n=81) | same |
| B2-queued | facts reaching the 2-domain floor | 656 of 26,349 pursued | same command, same question file |

The exact values, the file hashes, and the commands are written to `data/e5_transfer_seal/seal.json` by
`scripts/e5_transfer_seal.py seal`, which also records the git commit. That file, not this table, is the
seal.

---

## 3. The gate

**PASS** iff, with **zero commits touching B's code, corpus, or evaluation**:

* B1-yield rises by ≥ 5% relative, **or**
* B2-queued rises by ≥ 5% relative,

and neither B1-agree metric falls by more than 0.02 absolute. A yield rise bought by extracting more
junk is not transfer, so agreement is a floor and not a target.

**FAIL** otherwise, including "no measurable change".

**INCONCLUSIVE** if B cannot be re-run identically — a corpus moved, a command errors, a metric returns
nan. Inconclusive counts as FAIL for the purposes of claiming E5, exactly as in the depth E4 exam.

---

## 4. What makes this honest

* **B is scored once, blind, at the end.** While working on A I may look only at gloss-lane numbers. If
  I inspect a B metric mid-work, this seal is spent and must be recorded as spent.
* **Any commit touching B's files voids the run.** The list of B files is fixed in `seal.json`; the
  scorer diffs them and refuses if they moved.
* **A negative result is reported as the headline**, not buried. The v6 plan is explicit that a negative
  here is the most valuable outcome available, because it would mean the shared-substrate story is
  wrong — and this project has zero E4+ evidence, so a false positive would be far more expensive than
  an honest null.
* **The improvement to A must be real work on A, not a change that targets B.** Adding a pattern because
  it looks like Wikipedia prose would be tuning on B through the shared file. The A-side change must be
  justified by a gloss-lane failure, and the justification is recorded in the result section.

---

## 5. Result

**PASS — on the B2 arm alone. The B1 arm is void, and that is a defect in this seal, not a finding.**

Scored 2026-07-31, `data/e5_transfer_seal/verdict.json`. Seal integrity verified at score time: **B files
8/8 unchanged, 0 moved, 0 missing**; the only file that moved was A's `property_extraction.py`, which is
the experiment.

| metric | sealed baseline | measured | change |
|---|---|---|---|
| **B2-queued** (facts accepted) | 656 | **785** | **+19.7%** |
| B2-pursued (questions worked) | 26,349 | 26,349 | **0.0%** |
| B1-agree_used_for | 0.471 | 0.4706 | −0.0009 |
| B1-agree_capable_of | 0.235 | 0.2892 | +23.1% |
| B1-yield_facts_per_1k_pages | 13.318 | 5.020 | −62.3% **(void, see below)** |

### What the B2 arm establishes

B2 is a clean frozen-B transfer. The B-side code was byte-verified unchanged, the question set was
byte-verified unchanged, the run was local-only (`--local --table --no-curiosity`, so no network
nondeterminism), and **`pursued` came out at exactly 26,349 — bit-identical to the baseline.** Identical
work on identical questions through unchanged code, yielding 656 → 785 accepted facts. The only changed
input in the system was A.

The A-side change was justified by a gloss-lane failure before B was ever consulted: definitional glosses
phrase purpose as "used **as** a …", which the extractor had no pattern for, and its 4-word object cap
truncated real complements. Adding the "used AS" pattern and raising the cap to 6 words lifted gloss-lane
recall 0.609 → 0.796. Neither change was made by looking at Wikipedia prose or at any B metric, which is
the §4 condition that separates transfer from tuning-on-B through a shared file.

### Why B1 is void, and why that is disclosed rather than dropped

The sealed B1 baseline (13.318 facts/1k pages) was computed over the **whole 6.9M-page corpus**, while the
re-run measured a **200,001-page slice**. Property density varies enormously across Wikipedia slices, so
the two numbers do not measure the same thing and their ratio means nothing. The −62.3% is a
slice-composition artifact, not a regression.

This is a defect I introduced when cutting the seal, and I found it only after the fact. Recording it
matters more than the PASS does: the scorer takes the **max** of the two yield metrics, so B1's void
number could not block the gate — which means the PASS rests **entirely on B2**, and anyone reading this
result should treat it as one arm of evidence, not two. A future E5 must re-cut B1's baseline on a fixed,
named slice with the same page count as the re-run.

The B1 **agreement** figures are still informative even with the yield void, because agreement is a rate
rather than a per-page yield: `used_for` held flat and `capable_of` rose. Whatever the A-side change did,
it did not buy facts by lowering the bar — which was the failure mode the agreement floor existed to catch.

### Boundary — what this is NOT

* Not two-arm evidence. One arm; the other is uninterpretable.
* Not proof of causation, though attribution to A is the only surviving explanation given verified-unchanged
  B bytes, an unchanged question set, no network, and an identical `pursued` count.
* Not a general claim about transfer across the system. It is one shared extractor propagating to one
  downstream consumer that was never touched.
* **It is ATANOR's first E5-shaped result.** Per the project's own ladder that is the first rung that
  counts as capability rather than mechanism — and per the GWIP lesson, a first green is exactly when the
  instrument deserves the most suspicion, not the least. The B1 defect found here is evidence that the
  suspicion is warranted.

---

## 6. B1 closeout — the void resolved (post-hoc diagnostic, not evidence)

Run 2026-07-31 after the seal was spent, `data/e5_transfer_seal/b1_closeout.json`, via
`scripts/e5_b1_closeout.py`. **This is not sealed evidence and cannot be**: A was already committed and
B2's direction was already known. It exists to turn a question the seal left as *unknown* into a fact.

Rerunning the sweep would not have answered it — `wiki_property_sweep` dedups against rows already on
disk, so a second pass over the same pages is scored against a ledger the first pass filled. Instead both
extractors were run over the **same streamed sentences**: same dump, same page order, same lead
selection, same subject filter, with the extractor as the only difference.

| over 200,001 pages, 78,992 subjects | pre-A | post-A |
|---|---|---|
| rows | 5,973 | **6,768** |
| per 1k pages | 29.86 | **33.84** |
| | | **+13.3%** |

**B1 did transfer.** The sealed run's −62.3% was entirely an artifact of comparing a whole-corpus
baseline against a 200k slice, exactly as the void section predicted — now confirmed rather than
asserted.

### The 206 "lost" rows are the best part of the change

The new extractor dropped 206 rows the old one produced, which looked like a trade. It is not: **all 206
share a subject and predicate with a row the new extractor added, and the true-loss count is zero.** They
are the same facts, re-formed:

```
lung cancer     capable_of  originate   ->  originate in the tissues of the lungs
delphi method   capable_of  rely        ->  rely on a panel of experts
humane society  capable_of  aim         ->  aim to stop cruelty to animals
koori           capable_of  correspond  ->  correspond to southern new south wales
```

The old extractor's 4-word object cap truncated complements down to bare verbs, which are nearly useless
as facts — *lung cancer is capable of "originate"* asserts almost nothing. So the +13.3% **understates**
the improvement: on top of 1,001 genuinely new rows, 206 stubs became real statements.

### What this changes and what it does not

It closes the void: B1's arm agrees in direction with B2's, and both point the same way. It does **not**
retroactively make E5 two-armed — a sealed arm must be measured blind against a baseline cut beforehand,
and this was neither. The lesson for the next seal stands unchanged: cut B1's baseline on a fixed, named
slice with the same page count as the run that will be compared to it.
