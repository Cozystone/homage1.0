# The fusion roadmap — what to do with everything already built

Owner, 2026-07-31: *"뭘 많이 벌려놨는데 이걸 어떻게 잘 융합해낼지."*

This is not a twelfth roadmap. `docs/` already holds ATANOR_FINAL_PLAN, ULTIMATE_ROADMAP,
canonical_masterplan_v4, agi_evolution_roadmap, MASTER_PLAN_AND_HANDOFF, roadmap_v3_ultimate and
several more — the sprawl the owner is describing is in the documents too, and adding a rival vision
would be another instance of it. This document does one thing the others cannot: it starts from a
number measured today and organises the work around it.

---

## 0. The number

**144 packages. ZERO true orphans. The premise this document was built on was false, and it took four
measurements to find that out.**

| attempt | claimed | what it got wrong |
|---|---|---|
| 1 | 55 orphans (38%) | counted API-reachability only; training and eval organs live in scripts |
| 2 | 15 orphans (10%) | counted only `packages.X` imports |
| 3 | 3 orphans (2%) | counts bare `from datagate import …` too, and scans all of `apps/` |
| **4** | **0 orphans** | two of the three are RUST packages with no `.py` file at all, invisible to a python import census by construction; the third is a registered evaluation organ |

`atanor_shell` and `main_core` are Rust — `Cargo.toml`, `fractal_engine.rs`, `backend_drm.rs`. Counting
them as unreachable-from-Python is trivially true and says nothing. `memaware_eval` is in
`organ_registry_v1.json` with evidence measurements citing `grader.py:5` and its dataset on disk: an
evaluation organ, tracked, doing its job.

**141 of 144 are reachable from an app, a script or a test; the remaining 3 are accounted for. The
sprawl premise was wrong.**

`datagate` says in its own docstring that `apps/api` wraps it, and it does —
`from datagate import DataGateConfig, PipelineRunner`. `rag_engine` is imported directly by the
routers. My census regex matched neither, because it assumed one import form and never checked the
assumption.

**So the headline claim of this document — that a third of the system is disconnected — was not
eighteen times too high. It was simply false.** The system is fully wired.

That inverts the answer to the owner's question. *"뭘 많이 벌려놨는데 이걸 어떻게 잘 융합해낼지"*
assumed the pieces are scattered, and I assumed it too and produced a number that agreed with the
assumption. They are not scattered. What ATANOR has is a well-connected system with **a small number
of specific dead paths inside it** — a gate that could never fire, a lane with its own private
storage, a ledger reading only from outside. Four were found today by looking at behaviour rather
than at structure, and all four were sutured.

Recording all three attempts instead of quietly replacing the number, because the failure is exactly
the one this document diagnoses elsewhere: a claim that looks measured, is expressed in code, and
rests on an assumption nobody checked. Both corrections came from reading a single entry rather than
trusting the total.

**What survives the correction, and what does not.** The three other findings below are unaffected —
they are specific measured dead paths, not an inference from a count: the schema organ contributing 2
solves of 181, a code lane behind a permanently false gate, a defect ledger reading only advisor
journals. Those are real and each was fixed by a suture today. What does NOT survive is the framing
that ATANOR suffers from mass disconnection. It suffers from **specific dead paths**, which is a
better problem: you cannot fix "38% unreachable", and you can fix a gate that cannot fire.

---

*(original section, retained for the record)*

**144 packages. 15 are true orphans — 10%.**

The first version of this section said 38%, counting everything not reachable from the API. That was
wrong, and the correction came from actually looking at the first organ on the list instead of
optimising the number.

`depth_learner` is not on the answer path, and **should not be**. It learns monocular depth from
CARLA; it is reached by `scripts/citysample_selfsup_train.py` and by the evidence-registry tests, which
is exactly where a training organ belongs. Wiring it into the chat API to move a percentage would have
been pure metric-gaming — the failure mode the owner had just warned about, walked into on the very
first case.

Measured properly:

```
144 total
 89 reachable from the API
101 + reachable from a script      training and evaluation organs live here, correctly
129 + reachable from a test
─────
 15 TRUE ORPHANS -- no API, no script, no test
```

**The orphans:** `atanor_shell, cost_model, datagate, guard, knowledge_bakery, main_core, memaware_eval,
model, neuro_efficiency, ontology_forge, rag_engine, rhfc, seed_research, trainer, workspace`.

**`workspace` is mine, written today** — rooms, formats, onboarding — with no caller and no test. The
first suture on this list is my own, made the same day as the list.

The twelve that are script-reachable but not API-reachable (`depth_learner`, `eye`, `hand`,
`image_schema`, `fusion_loop`, `transfer_gate`, `oam_holdout` …) are not a problem to fix. They are
organs whose home is a harness. Counting them as defects is what inflated 10% into 38%.

## 1. Consolidation is the capability work, and four independent measurements say so

Today produced four findings that look unrelated and are the same disease:

| finding | measured |
|---|---|
| the algorithm-schema organ contributes **2 solves of 181** on MBPP | it aces `mastery_v1` (40/40), which its author also wrote |
| the code-QA lane could **never fire** | gated on `language == "ko"` in an English-only system |
| the self-repair loop never saw ATANOR's own failures | its defect ledger reads **advisor journals only** |
| **38% of packages unreachable** | import-graph reachability from the API |

Every one is *built beside, not wired in*. And the first row prices it: an organ that is not reached
contributes approximately nothing, however good it is. So consolidation is not tidying that happens
after the capability work — **on this codebase it IS the capability work**, and the reachability
figure is the first honest way to track it.

**Gate R, corrected by the owner (2026-07-31): SUTURE, one organ at a time — not "reduce the count".**

The first draft of this gate read "reachable share rises, wire or delete", and that is a defective
gate for two reasons the owner caught immediately.

**It is satisfiable by amputation.** Deleting 55 organs takes reachability to 100% while losing
everything they hold. A gate that a knife satisfies is not measuring what it claims to.

**Worse, the number itself is gameable.** One `import depth_learner` in a reached module raises the
percentage with nothing flowing through the new edge. That is wireheading on my own metric, written
into the roadmap by the same hand that spent the day guarding against it.

So the unit of work is a **suture**, and a suture is only real when something flows. Every repair made
today was one, and each produced a number on the spot:

| suture | what flowed |
|---|---|
| removed the dead `language == "ko"` gate | the organ spoke for the first time |
| private JSONL → the shared triple store | 167 ms → 10 ms per question |
| self-measurement → the defect ledger | `found_by_atanor` 0 → 1 |

None was a deletion. The default is therefore suture; **deletion requires evidence**, not the absence
of it, and an organ nobody has looked at is not evidence of anything.

**Gate R (as it should read):** for each unreachable organ, either a suture that carries a MEASURED
flow — a latency, a rate, a count that moved — or a written finding that it is inert and why. The
reachability percentage is a symptom to watch, never the target to hit.

## 2. The rule that decides what gets built next

Established today at the owner's insistence, after an afternoon spent hand-writing rules that a later
measurement showed were 44% dead on arrival: **build only where verification is free.** "No oracle"
means *not ready to build*, not *fill the gap by hand*.

That single rule sorts everything remaining:

### Tier 1 — the oracle already exists. Build here.

| axis | oracle | today |
|---|---|---|
| code synthesis | the tests | MBPP **18.9%** sealed, fabrication 0 |
| transfer through shared substrate | sealed baselines | E5-1 +19.7%, E5-2 B1 +5.3% |
| reachability | the import graph | **62%** |
| prose faithfulness | re-extract and compare | live, catches an off-by-one citation |
| **predict-then-run** | execution itself | **not built** — the largest unclaimed Tier-1 space |

That last row is the one to take. Predicting what a change will do, then running it, needs no labels,
has exact ground truth, and unlimited data. It is also the missing half of the self-improvement loop:
a system that can predict outcomes can *choose* among candidate changes instead of trying them all.

### Tier 2 — an oracle is constructible but not yet built.

* **relation correctness** — built today. Works at the level of relation *clusters*, not within them.
  The next rung is discriminating `used_for` from `capable_of`, which share 7,384 head nouns.
* **register / audience** — the supervision is free and not yet captured: a question's own follow-up
  reveals whether the answer was pitched right. Nothing logs that today.
* **relation invention** — the loop can propose a cue for an existing relation. It cannot notice that
  `has_part` is missing from the vocabulary, which is what `consisting of` was really telling us.

### Tier 3 — no known oracle. Do not hand-fill these.

Selection aptness ("is this the right thing to say"), design taste, whether an abstraction is correct.
These are the honest frontier. The failure mode is not leaving them undone; it is filling them with
hand rules and calling the gap closed.

## 3. AGI: the gates, without dates

The charter's definition of done is unchanged — sealed holdout green across the pillars, with ARC-AGI-3
as an external judge that has never been attempted. What today adds is the ladder's *current rung* and
what each next one costs.

```
V0 ─ M1 ─ M2 ─ M3 ──── E4 ──── E5 ──── E6
mechanism ─────────┤   1 organ  2 arms   0
                   └── capability begins here
```

* **Gate E5-2** — transfer visible in two independent consumers at once, not the better of two.
  *(Scoring now. One arm already cleared at +5.3%.)*
* **Gate R** — reachability. An organ that cannot be reached is not a capability.
* **Gate C** — the sealed MBPP slice moves. The engine's own measurement already says where: the
  elaborate schemas are inert, the wins are in cheap families and in the 81% it abstains on.
* **Gate P** — predict-then-run beats a coin on held-out code. This is Tier 1 and unbuilt.
* **Gate E6** — whatever the ladder's next rung is, defined *before* it is attempted, not after.

## 4. ASI: one honest sentence and the series that would show it

Superintelligence, on this project's own terms, is not a capability threshold — it is a *rate*. It
requires the improvement loop to compound, and compounding is three measured series, all of which are
currently pointing the wrong way:

```
gain_per_cycle    [0.197, 0.053, 0.0]     gains_holding: false
capacity_cycles   1 of 3                  most work improves the product, not the capacity to improve
found_by_atanor   1 of 3                  the finding station only just came online
```

The distinction that decides it: a cycle improves either **the product** or **the capacity to
improve**, and only the second compounds. A hundred product cycles is a straight line. So the ASI
question is not "when is it smart enough" but **"when does an improvement make the next improvement
easier"** — and that has an answer in the ledger, updated every cycle, that nobody has to argue about.

## 5. What to do next, in order, and why this order

1. **Score E5-2 and act on the result.** If both arms clear, transfer through a shared substrate is
   established twice over. If B2 fails, transfer is real but narrower than one arm suggested — which
   is worth knowing and is not a disappointment to explain away.
2. **Gate R: wire or delete.** Start with `depth_learner` — the only E4 evidence in the project is
   unreachable, which makes the evidence itself hard to defend.
3. **Predict-then-run.** The largest Tier-1 space, and the piece that turns the loop from
   try-everything into choose-then-try.
4. **Move the sealed MBPP slice.** Not by adding a thirteenth schema; the measurement says that is the
   wrong layer.
5. **Capture the register follow-up signal.** Not to build register — to make the oracle exist, so it
   can be built honestly later.

No dates. Each is a gate that is green or is not.

## 6. The one sentence

Everything needed for the next rung is probably already built; a third of it just cannot be reached
from where a question arrives — so the fusion is not more organs and not fewer, it is **one suture at
a time, each carrying something measurable**, and a loop whose gains stop shrinking.
