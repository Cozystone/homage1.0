# ATANOR — the final structure, the orphan census, and the order that cascades

Measured 2026-07-30. Every number here is reproducible:
`scripts/package_inventory.py`, `scripts/registry_wiring_fill.py`, `packages/operator_census`.

This document does **not** invent an architecture. One is already declared in
`data/architecture/catalog/organ_registry_v1.json` — 144 organs, with `lifecycle`,
`canonical_domain`, `built`, `wiring`, `authority`, `evidence`. What was missing was every
judgement: 125 of 130 entries carried `wiring.runtime_status: "unknown"`, and the `archive`
lifecycle the enum has always allowed had **never once been used**. Those columns are now filled
from measurement.

---

## I. The census

```
144 packages          262,133 lines
   live_default   69     reachable from apps/api/app/main.py through the import graph
   live_conditional 27   imported by a non-test package, not reachable from the entrypoint
   unwired        48     nothing but scripts imports it, or nothing at all
   test_only       0
```

**Wired means reachable, not mentioned.** An earlier pass counted importers with grep and called the
zero-count packages orphans. That is wrong in both directions: a package imported only by a script
is not wired, and a package imported by something itself unreachable is not wired either. The number
above walks the import graph with `ast` from the application entrypoint.

---

## II. Three kinds of orphan, and only one of them calls for wiring

The owner's correction is the load-bearing insight of this document: **some orphans are not unwired,
they are obsolete, and wiring them would drag dead architecture back into the live system.** The
registry's own `lifecycle` enum already distinguishes the cases. Sorting the 48 by what they *are*:

### fixture — INSTRUMENTS. Zero consumers is correct, and permanent.

`b5_missions` · `consciousness_audit` · `tom_bench` · `multimodal_tasks` · `transfer_gate` ·
`contrast_family` · `operator_census` · `self_check` · `spark_chamber` · `selfhood_runtime` ·
`selfhood_control` · `live_selfhood_monitor`

Benchmarks, probes and proof harnesses. Importing a measuring device into the runtime is the defect,
not the fix. These must never be "wired" and the count of them must never be read as debt.

*(Correction recorded: a first pass classified these by searching docstrings for words like "probe"
and "audit", which swallowed `co_allocator` — the Conscious-Orchestrator effort allocator, declared
`canonical`, an organ. The declared lifecycle outranks a keyword sweep. See §V.)*

### archive — SUPERSEDED. Nominated for retirement, never deleted by a script.

Built and last touched inside a single day, idle since:

| package | lines | idle | superseded by |
|---|---|---|---|
| `genesis_sandbox` | 3,455 | 6 d | — |
| `splatra_worldmodel` | 2,534 | 6 d | — |
| `federation` | 1,160 | 5 d | — |
| `local_memory_operator_confirmation` | 666 | 38 d | `autonomy_envelope` |
| `local_memory_write_plan` | 547 | 38 d | `autonomy_envelope` |
| `local_memory_sandbox` | 513 | 38 d | `autonomy_envelope` |
| `promotion_gate` | 511 | 38 d | **`autonomy_envelope`** (verified) |
| `promotion_manifest` | 484 | 38 d | **`autonomy_envelope`** (verified) |
| `turbovec_sandbox` · `airllm_offload_sandbox` · `runtime_control` · `cost_model` | ~700 | ~40 d | — |
| `atanor_shell` · `main_core` | **0** | 23 / 41 d | empty directories |

`promotion_gate` being unwired looked like a safety hole and is not one: operator-signed
default-deny promotion is enforced by `autonomy_envelope` (`operator_trust.py`,
`promotion_queue.py`), which is live. Checked before raising an alarm. This is exactly the owner's
category — a better structure arrived later and made the earlier one unnecessary.

**Retirement is the owner's decision. Nothing above has been deleted or re-labelled.**

### canonical — THE BETTER ARCHITECTURE, BUILT AND NOT ADOPTED. The only group that calls for wiring.

| package | lines | what it is | why it matters |
|---|---|---|---|
| `eye` | 1,153 | "a retina, not a sensor: sharp at the centre, coarse at the edge" | one door for vision; `packages/perception` has 20 consumers calling around it |
| `hand` | 771 | "one door for motor output" | same, for action |
| `image_schema` | 650 | the closed primitive basis; the speaker inverted | the organ built to answer *"can ATANOR be told the rules in English?"* — 12 scripts, 0 packages |
| `co_allocator` | 1,033 | Conscious-Orchestrator metacognitive effort allocator (NS-4/C1) | declared `canonical`; the CO is doctrine's central spine |
| `rag_engine` | 4,110 | relation-type schema loader, "4D BLOCKER #1" | its own docstring calls it a blocker |
| `depth_learner` | 1,022 | first continuous-modality organ (CARLA) | trained, measured, unconsumed |
| `kind_prediction` | 3,009 | domain B for the frozen transfer gate | the E5 transfer evidence the roadmap requires |
| `loop_schema` · `datagate` · `ontology_forge` · `guard` · `model` · `trainer` | ~2,400 | — | needs inspection before a verdict |

**Wiring these DELETES code rather than adding organs.** That is what makes them the first rung.

---

## III. The ideal structure — already declared, with its holes named

The registry's 13 `canonical_domain` values *are* the target architecture. Organ counts, and the
gaps that stand out:

```
core_spine               6      the symbolic backbone
world_ledger             9      what is known, and when
semantic_compiler        7      language into structure
world_model_4d          12      prediction over space and time
unified_deliberator      5      System-2
operational_self        14      continuity, autobiography, identity
interoception_resource   5      hormones, effort, metabolic tuning
membrane_governance     15      the verification membrane; moral 0th gate
language_action         15      speaking, and acting on what was said
learning_evolution      18      the flywheel
embodiment               1   <- ONE ORGAN, while Track E is doctrine's mainline
evaluation              13      the instruments (correctly unwired)
platform                10
```

Two structural holes, both measured rather than felt:

1. **`embodiment` holds one organ** while embodiment was promoted to the mainline track. `eye`,
   `hand`, `depth_learner` and `splatra_worldmodel` all belong to this domain and none of them is
   wired. The body is declared and not connected.
2. **Nothing enforces the registry.** `architecture_registry` — "strict, read-only validation for the
   ATANOR organ registry" — is itself unwired. The registry drifted to 125 `unknown` *because
   nothing checked it.*

---

## IV. The attack order, ranked by measured downstream reach

### Rung 1 — adopt the organs already built. Deletes code, adds nothing.

`eye`, `hand`, `image_schema`, `co_allocator`, `self_check`, `operator_census`. Each is a
consolidation point that was built and then not adopted, so the scattered old way is still the live
way. Reach: `perception`'s 20 consumers, and the whole understanding trunk.

**Gate:** a rung only counts when a call site is *removed*, not when an import is added.

### Rung 2 — consolidate the 52 recurring shapes. This is the cascade.

Measured by `packages/operator_census`, by AST shape rather than by name:

```
recurring_shapes              52     distinct computations re-implemented
duplicate_copies             261
organs holding a duplicate    81     of 143
widest single shape           12     copies of one computation
```

**261 copies of 52 computations across 81 of 143 organs.** Consolidating removes ~209 copies. Start
at `graph_scale` — it holds 12 re-implemented shapes and 141 modules import it, so a fix there
travels further than a fix anywhere else. Then `brain_link` (8), `digital_life_kernel` (7),
`reasoning_vm` (6), `continuous_self` (6).

This is what makes the *depth* work of 2026-07-30 pay: one shared gate, learned across scenes, is
the consolidation target — not a better threshold inside one organ.

### Rung 3 — enforce the registry, or all of the above rots back.

Wire `architecture_registry` into the test suite so `wiring.runtime_status` cannot silently return
to `unknown`, and so a new package cannot appear undeclared (14 did).

### Rung 4 — data, where measurement says it is the lever (§V).

### Rung 5 — archive, with owner sign-off.

---

## V. Data — the owner's hypothesis, against what is already measured

> *"another bottleneck is probably data — feeding more into what is already well built might
> unexpectedly solve related problems. Sentences, images, even video."*

Correct, and the measurements already in hand say **which** data, and it is not symmetric.

### Where volume is measured NOT to be the lever: text

- The English rebuild **removed** corpus — 26.9M → 7.17M triples, physically — and the system got
  better.
- Fluency's real cause was measured as **register complexity plus entity memorisation**, not corpus
  size.
- The voice-corpus root cause was learning *speech* from a *fact database* — a composition error
  that more sentences of the same kind makes worse.

So a sentence-collection tour aimed at **volume** repeats a measured mistake. Aimed at **register** —
imperatives, dialogue, procedures, narrative — it is exactly right, and the seed label set already
awaiting operator review is that shape.

### Where volume IS the lever, and 2026-07-30 proved it: scenes

The morning's rung established that a per-scene significance test **cannot have power at n = 10**,
because ten is how many things a frame holds. A gate whose prior is learned across *thousands* of
scenes does have power. That prior cannot be built from one Atari rollout — it needs **many scenes,
which means images and video.**

This is the strongest instance of the owner's hypothesis in the whole system, and it is the *same*
lever that would make the ~102 hand-chosen score thresholds derivable instead of chosen.

### Organs already built and starving

`depth_learner` (CARLA, trained, unconsumed) · `splatra_worldmodel` (rich dynamics, 0 consumers) ·
`kind_prediction` (domain B for the transfer gate). Feeding these is literally
*"데이터를 투입해서 기관을 계몽시킨다"* — and each is already written.

### Constraints that hold regardless

Unattended web crawling is an outward-facing act and the owner's call to authorise. Scraping Google
Images is against their terms — openly-licensed datasets instead. Downloading video from YouTube is
against their terms and is the owner's decision, not mine.

---

## VI. A correction I owe this document

`packages/operator_census` already existed, and its docstring says: *"which computations does ATANOR
keep re-implementing? Measured by SHAPE, never by name. A keyword sweep cannot establish it — this
repository produced two keyword artifacts in a single day."*

`scripts/macro_audit.py`, written earlier today, counts `< 0.5` patterns with a regex and was
presented as the consolidation measurement. **It is the third keyword artifact that docstring
predicted**, produced by the method it warns against, while the organ that does it properly sits
unwired. The threshold count (399 sites, 59% of them twelve round numbers) still stands as a fact
about hand-chosen constants; the *consolidation* claim belongs to the shape census — 52 shapes, 261
copies, 81 organs — and that number is the one to plan against.
