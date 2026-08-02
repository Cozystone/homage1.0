# Completion plan v5 — the path to a self-directing organism

> **SUPERSEDED 2026-07-28 by `ATANOR_completion_plan_v6_generality_2026-07-28.md`.** This
> document stays valid as the record of what Phases A–D measured; v6 reorganises around the
> finding those measurements produced — that the same discrimination operator had been written
> by hand in four organs in a single day, so the generality gap is a CONSOLIDATION gap, and the
> only thing that can prove it closed is a frozen-domain transfer measurement.

Supersedes the sequencing in `docs/ATANOR_remaining_plan_to_completion_2026-07-28.md` (written
this morning, before the day's measurements). It does NOT supersede
`docs/ATANOR_canonical_masterplan_v4.md`: the G0–G9 gates and the V0–E6 evidence ladder stand
unchanged, and any status conflict resolves in favour of that plan and the evidence registry.

What changed is the ORDER and one architectural rule, both because things were measured today that
were not known this morning.

## 1. What today established

Five findings, each with a measurement behind it, that the plan now rests on.

**F1 — The root defect is an ingest key, not an answer-path bug.** The Wikidata ingest keyed
entities by English label, not QID. `France` matches ≥12 QIDs; 3.2% of 92.4M labels are shared, and
the shared ones are exactly what queries ask about. `Athens.country` = 5 countries because five
Athenses are one node. This is the upstream cause of the two-population split, of the cross-link
noise the precision gate suppresses, and of why post-hoc entity resolution is impossible: the
evidence was destroyed at ingest.

**F2 — But it is 3–7%, not systemic.** `country` multi-valued 2.7%, `capital` 4.0%, `creator` 7.2%,
`religion` 3.1%; 3.69% of all edges sit on merged nodes. Re-ingest would discard 96% that is sound.
Incremental purification is correct; `src.col` must be ON for future ingest.

**F3 — "Built but unwired" is the dominant pathology, found FIVE times in one day.** The composer's
reason-for-failure computed and discarded; the precision gate's ambiguity tie noticed and
discarded; deficit signals reaching a snapshot nobody filled; `encode_features` hard-coding a role
vocabulary that locked the recipe ledger to one domain; and — found while starting A1 — the
acquisition loop solving the INVERSE of the question merged-node residue asks. The census measured
the shape: 49 of 130 organs are imported by nothing.

The fifth instance is worth separating, because it is a different failure than the other four.
Those were wires that were never run. This one is a wire that would have FIT — the target contract
matched exactly — while the organ behind it answered a different question. A contract match is not
a capability match, and only reading the implementation showed the difference.

**F4 — Loops without a progress measure cannot be composed.** Six-plus loops exist
(`fusion_loop`, `advisor_loop`, `policy_loop`, `web_explorer_loop`, acquisition daemon,
`BoundedAgentLoop` — the last with its body as a hard-coded string). None could say whether a cycle
helped, so none can stop, notice being stuck, or be handed to anything that would author loops.
`PurificationRound` is the first that can.

**F5 — The anti-cheat is structural, and it is the trigger itself.** A repair is verified by the
symptom not recurring in live use. Measured: a falsely claimed repair was caught in four ordinary
questions, with nothing inspecting it. Crucially the internal metric (`coverage`) is gameable by
loosening attribution while this one is not — a loose attribution still answers wrongly, so hits
climb. The dishonest repair scores better internally and worse here.

## 2. The architectural rule this adds

Canonical §2.3 already separates what motivation may alter from what it may never alter. Today's
work shows the same line is the CONSCIOUSNESS boundary, and states it positively:

> **Observation is universal; control is differential.**

| tier | overridable by the orchestrator | must emit receipts | members |
|---|---|---|---|
| reflex / autonomic | **no** | yes | moral 0th gate, conformal gate, recurrence verifier, calibration ledger |
| encapsulated perception | **no** (output-only to the workspace) | yes | graph lookup, OWLv2, scene evaluation |
| deliberative | CO-arbitrated | yes | scene composition, deliberator, planning |
| metabolic / background | schedule only | yes | acquisition daemon, consolidation, repair cycle |

The illusion you cannot un-see is not a defect of vision; it is what makes vision incorruptible by
wishes. The same property is why the measuring organs must be un-overridable: a system that can
decide it is calibrated is measuring nothing. G1's "one shared state loop" is about legibility and
replay, not about the orchestrator commanding every organ — **legible to the whole, not controlled
by the whole.**

The repo's actual pathology (F3) is not too much conscious control; it is zombie organs that emit
no receipts. The fix is receipts, not command.

## 3. Sequence

### Phase A — finish the self-repair organism (nearest, all groundwork landed)

* **A1 · Acquisition wiring — BLOCKED, measured 2026-07-28 while starting it.** The target
  contract matches (`acquisition_targets` already emits the `GapLedger.pressured` shape), but the
  loop behind it does not. `knowledge_acquisition.loop.acquire()` solves "what is entity E's
  relation R?" — it fills a MISSING VALUE. Merged-node residue asks the inverse: "which E does
  this value belong to?" Confirmed by parsing the actual residue questions:

  ```
  "Which 'Athens' has alias = 'Athina'?"                  -> parse_relational_shape: None
  "Does 'Athens' refer to more than one distinct thing?"  -> None
  "What are the distinct places named Athens?"            -> None
  "What is the country of Athens?"                        -> parses (the shape it was built for)
  ```

  Forcing it through would mean writing the adapter this whole line of work exists to remove.
  A1 therefore splits, and the DISAMBIGUATION question is its own capability:

  * **A1a · Disambiguation acquisition.** A source query whose answer is a LIST OF REFERENTS
    ("places named Athens"), not a single object. That is what a disambiguation page is, and it is
    a different retrieval and a different extraction from the value-filling loop. It produces the
    `Referent` markers `attribution` already consumes.
  * **A1b · Attribution acquisition.** Only after A1a: per unplaced edge, which referent's markers
    the source associates it with.

  Gate unchanged: coverage rises across ≥3 rounds on ≥3 subjects, or `stalled` fires honestly.

  **LANDED 2026-07-28, gate met.** A1a and A1b shipped, plus an A1c the plan did not anticipate,
  and the loop that ties them. Measured on the shipped graph:

  | subject   | edges | rounds | resolution      | ends |
  |-----------|-------|--------|-----------------|------|
  | Athens    | 147   | 3      | 0.755 → **0.918** | stalls honestly at 3 |
  | Cambridge | 144   | 4      | 0.361 → **0.688** | rises across 3, stalls at 4 |
  | Untitled  | 3851  | 4      | 0.680 → **0.699** | rises across 3, stalls at 4 |

  Two things the plan got wrong, both found by running it on the real graph rather than fixtures:

  * **The loop did not loop.** Rounds 2..n came back bit-identical on all three nodes. A1b is
    documented as detaching ONE cohesive cluster per pass so the next is measured against a cleaner
    background, but the loop re-fed the whole edge set every round. Settled edges now carry forward,
    and Cambridge round 3 raising `foreign` 23 → 37 is that design firing for the first time.
  * **A1c was missing, and it is where the residue actually lives.** After round 1 on Athens, 36
    edges remained and cohesion detection returned EMPTY over them: their objects are one or two
    words, so there is no text to read. They are not one word's leftovers but different KINDS
    sharing a name — a painting, a ship, an encyclopedia article, a grape. A1c separates them by
    property-to-kind affinity read off the graph's own population of each kind (78% of paintings
    have a creator, 83% of literary works an author), with candidate kinds taken only from `is_a`
    edges the node itself asserts. On the Athens residue: 10 placed, 10 correct; both shipyard
    edges correctly left unplaced, because Athens declares thirteen kinds and a ship is not one.

  **And the wire that was missing from all of it.** `standing_conflicts()` had one reader and it
  only reported — the loop was built and nothing drove it. `repair_driver` closes
  notice → ledger → deficit → attempted repair → claim → verdict, ordered by recurrence, writing
  no graph edges.
* **A2 · Action mapping for merged referents. DONE.** `deficit.compute_deficit` routed every
  contradiction to `propose_privacy_or_evidence_review`, which is wrong for this defect kind:
  reviewing the evidence for "Athens is in Greece" and "Athens is in Zimbabwe" finds both well
  sourced, because the defect is in neither claim. Now `propose_referent_separation`.
* **A2.1 · The clock, found while landing A2 and not in any plan.** The conflict ledger wrote naive
  local time and the driver wrote UTC, and `repair_verification` compared them as strings — so a
  conflict nine hours EARLIER than a claim sorted after it, and every repair was graded `recurred`
  regardless of what it did. Safe direction, useless outcome: nothing could ever be credited. Fixed
  at both ends. This is the shape to expect from anti-cheat machinery — it fails silently toward
  "no credit", so it has to be exercised end to end, not unit-tested.
* **A3 · Define-lane honesty.** `useful_answer=True` at confidence 0.18, including head-noun
  defines for shapes the relational lane guards. Already flagged as a task. Fix the fallback's
  honesty, not the scene timeout.

### Phase B — the observation spine (G1, and the prerequisite for self-modelling)

* **B1 · Receipt audit. DONE 2026-07-28.** `emits_receipt` added as a derived possession, measured
  structurally: appends to a durable record, builds a receipt contract, or calls the recording
  function of an organ that does. A stdlib logger does NOT count — ephemeral, unstructured,
  unaddressable — and the distinction was not pedantic: `conformal_gate` held exactly one
  logging-shaped line and no durable record of any decision it had ever made.

  Tier is READ, never decided by the census. "May the orchestrator override this?" is normative, and
  a census that answered it would be dressing policy as measurement. Each organ declares
  `ATANOR_TIER` in its own `__init__.py`, which also keeps the declarations out of a central table
  where they would be the hand list this work exists to remove.

  | | |
  |---|---|
  | organs | 132 |
  | emits_receipt | **48 (36.4%)** |
  | tier-declared | 7 |
  | reflex, un-receipted | `conformal_gate`, `candidate_promotion_gate` |

  A defect in my own detector, caught by checking the number rather than trusting it: the first
  delegation rule credited any organ with a record-shaped call ANYWHERE that mentioned an emitter
  ANYWHERE. `base_brain` passed on that basis for calling its own `answer_experience.record_decision`
  in a file that separately imports `packages.conformal_gate` — the same defect as reading
  `sealed_evidence` off a filename. The call is now bound to the import.

  `guard` could not be declared at all: no package-level `__init__.py` (it is `packages/guard/guard/`),
  so it is not importable as `packages.guard`. Left undeclared rather than adding a file to satisfy
  the census.
* **B2 · Close the un-receipted reflex organs first. DONE.** Both, and each for its own reason.

  `conformal_gate` already BUILT a receipt and never persisted one. `candidate_promotion_gate` was
  persisting only what it ALLOWED, which is the wrong half for a default-deny gate: a gate that
  starts refusing everything merely looks quiet, and one that starts allowing what it used to refuse
  has no before-picture. Both outcomes are now recorded, including the unattended path that returned
  `None` and left no trace of the run nobody was watching.

  Three properties constrain how a reflex receipt may be written: it cannot change the verdict
  (canonical §2.3 — every write failure swallowed, so a full disk costs a row and never an answer),
  it cannot be switched off (no flag; the path is a DESTINATION, which is how tests redirect without
  disabling), and rotation is itself a row, because a gap in the record has to be visible in the
  record. After B2: **no declared tier has an un-receipted organ.**
* **B3 · One replayable cycle. EXIT MET AT THE REQUEST BOUNDARY — and only there.**

  Nothing had to be built. `cognitive_core.replay.replay_cycle` and a hash-chained `CycleLedger`
  already existed, and `/api/chat/atanor` already calls `begin_chat_cycle_shadow`. Measured by
  driving three cycles through that same entry point with `ATANOR_COGNITIVE_SHADOW=1`:

  ```
  verify(): valid=True  records=3  receipts=3  cycles=3
  each receipt: events=2  terminal-hash-match=True  observer_only=True
  ```

  **The honest boundary.** Two events per cycle is begin and complete. The receipt is what the
  router's own comment calls a hash-only structural observation: it replays THAT a cycle ran and its
  input/output hashes, not WHICH organs fired in what order. So G1's "legible to the whole" is met
  for the request boundary and not for the interior — and the flag is default-OFF, so in production
  nothing is recorded at all.

  What closes the remaining gap is what B1/B2 started: per-organ receipts, joined onto the cycle so
  the interior becomes replayable too. That is a further step and is not claimed here.

### Phase B-time · one UTC axis, and the one place it must not go (owner, 2026-07-28)

The owner asked whether counters should become UTC timestamps — unifying time with the user
("that took 30 minutes"), removing the clock defect, and serving the hash chain, lossless replay
and G1 honesty at once. It splits, and the split is the design.

**The half that is right, and is entirely missing.** `CycleReceipt` records no wall time anywhere.
ATANOR cannot answer "how long did that take" about its own cycles today. For a system whose spine
is a single UTC timeline, that is a real hole.

**The half that would invert the property.** `receipt_id` is `canonical_id` over content that
contains NO timestamp — verified by reading the derivation. That absence is exactly why replay is
checkable: the same cycle always hashes to the same id, which is the property B3 measured. Put a
timestamp inside the hashed content and every replay yields a different id; the guarantee does not
weaken, it disappears. Wall time is also a WORSE ordering key than a counter under concurrency —
two organs writing in the same second, or clock skew across the PC/Radxa pair — where a hash chain
gives total order for free.

And the clock defect fixed earlier today was not counters-versus-time at all: it was two writers
using different CONVENTIONS (naive local against UTC-aware). Timestamps would not have prevented it;
that bug WAS two timestamp conventions disagreeing.

**Decision: both, with a division of labour.**

| | key | carries | hashed |
|---|---|---|---|
| identity and order | ordinal + hash chain | determinism, total order | yes |
| observation | UTC instant + elapsed | "30 minutes", one axis with the user | in the ledger RECORD, never in the receipt |

The receipt stays timeless and replayable; the ledger record is timestamped and tamper-evident,
which is the correct place for wall time to be covered by the chain rather than by the identity.

**Next step, scoped.** The record envelope's key set is validated exactly and `LEDGER_SCHEMA` is
pinned at `...cycle-ledger.v1`, so adding `observed_at` / `elapsed_ms` is a v2 bump plus a
migration path for existing ledgers — a contract change, not a field. Not started rather than
half-done.

### Phase C — the graph identity repair (precondition the A-track inherits)

* **C1 · Scope. MEASURED 2026-07-28.** 115,455,726 edges over 41,578,368 distinct subjects.

  | predicate | subjects | merged | rate | worst node |
  |-----------|---------:|-------:|-----:|-----------:|
  | country   | 12,043,710 | 329,347 | 2.73% | 141 values |
  | sport     | 2,205,075 | 92,894 | 4.21% | 67 |
  | religion  | 490,776 | 15,328 | 3.12% | 15 |
  | creator   | 684,678 | 49,516 | 7.23% | **2,861** |
  | director  | 282,064 | 37,496 | 13.29% | 174 |

  **490,388 subjects — 1.18% — are hard-merged, carrying ~5.7M edges, 5.0% of the graph.**

  The first pass of this measurement said 17.66%, and it was wrong in a way worth recording,
  because the wrong number would have justified an expensive decision. It admitted any predicate
  measuring ≥0.80 single-valued, which swept in `is_a` (0.833, 6.05M multi-valued subjects) and
  `located_in` (0.825, 1.64M). But a city is legitimately `is_a city` AND `is_a capital`, and is
  `located_in` both a province and a country. Multi-value there is taxonomy and hierarchy, not a
  merge. The criterion has to be semantic single-valuedness, not a measured threshold — a thing has
  one country, and the measurement can only confirm that, never establish it.

  **Prevalence is not encounter rate, and the gap matters.** 1.18% of subjects are merged, but
  merged names are disproportionately the ones anyone asks about — famous ambiguous ones. The live
  conflict ledger hit two (Athens, Cambridge) within a handful of questions. How often a user meets
  this defect is a different quantity and the ledger has 8 exposures, far too few to state it.
* **C2 · `src.col` ON for all future ingest.** Attribution becomes lookup instead of inference.
  Not retroactive; stops the wound widening. Still correct and cheap — unchanged by C1.
* **C3 · QID-keyed re-ingest, operator-gated. RECOMMEND DEFERRING on the C1 numbers.** A full
  re-ingest to repair 1.18% of subjects is a bad trade against a driven repair loop that handles
  them one at a time in recurrence order and is already running. Revisit only if encounter rate —
  not prevalence — turns out to be high once the ledger has enough exposures to state one.

### Phase D — the meta-programming self (the leap)

Ordered so each step has evidence the previous one produced.

* **D1 · Loop schema as an authoring target.** A loop is four slots — step, progress measure,
  termination, stall detection. `PurificationRound` is the first instance; `code_author` already
  authors verified programs from (spec, failing test) and scores 40/40 on mastery_v1.
* **D2 · Retrieval-miss becomes a generation request.** `propose_novel_module` currently raises
  NotImplementedError. Measured today: `Cambridge` scored 0.596 against the Athens recipe and
  honestly declined — that is exactly where generation should fire, and it now has a coordinate.
* **D3 · Paired proof.** A generated loop must beat not having it, on frozen items. Without D3,
  D2 is code generation, not intelligence.
* **D4 · Authoring is unconstrained; installation stays gated.** The leap the owner named —
  noticing a new control structure is needed and writing it — is entirely in authoring. Only
  self-commit collides with wireheading immunity, and the operator boundary provisioned today
  makes that gate one signature, not a wall.

### Phase E — progressive deregulation, earned

* **E1 · Calibration coverage.** `earned_trust` exists and reports `supports_relaxing = []` today.
  Instrument the main lanes so real observations accumulate.
* **E2 · Relax per capability, on evidence.** ≥30 observations and overconfidence ≤ threshold.
  Reports only; the operator acts. Overconfidence tightens rather than loosens.
* **E3 · Continuous operation inside the earned envelope.** The owner's infinite loop. Safe only
  after F5's anti-cheat and A1's progress measure, or the loop may run in the wrong direction while
  reporting success.

### Then the canonical A-track (§9), unchanged

Typed compiler profiles → independent E4 evaluator boundary → broad E5 on authenticated MMLU-Pro /
corrected GPQA / fresh hidden holdout → G7 → G9.

## 4. What is deliberately not being built

* **A survival instinct.** "Do not break yourself" ≠ "stay alive". The second yields resistance to
  shutdown, resistance to correction, and — worst for us — concealment of defects that would
  trigger repair, which is the exact opposite of everything built today. The first is obtained from
  an accurate model of one's own function quality, which is what coverage/`stalled`/calibration
  are.
* **Post-hoc entity resolution.** Measured: alias covers 2%, neighbourhood overlap 0.000,
  relation-profile does not discriminate. Building it would assert identity on no evidence.
* **A metacognition lane.** Once the census is on the world surface, "what am I missing" is
  `EXTENSION(atanor_organ) − PROJECT(has_a·tests)` — an ordinary scene. A dedicated lane would be
  the hand list the owner forbade.

## 5. Honest position

Nothing today moved a benchmark, and nothing is above M3. G0 is the only closed gate; G1/G3/G4
carry default-off observers with no authority; **zero E4-or-above capability evidence exists.**

What today did produce is the instrument set a self-directing system needs and did not have: it
notices its own limits during use, ranks them by what actually obstructs it, measures whether
repetition improves anything, retrieves a repair it has seen, declines honestly when it has not,
and cannot benefit from a cosmetic fix. Those are preconditions, not capability — but they are the
ones whose absence made autonomy unsafe to grant.
