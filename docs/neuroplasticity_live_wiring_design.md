# Neuroplasticity live-wiring — design (for the next focused session)

The mechanisms exist and are tested (`packages/cloud_brain/neuroplasticity.py`): data-derived
predicate informativeness, time-decay + pruning (LTD), usage reinforcement, and a combined
`plasticity_tick`. What remains is wiring them into the running system. This doc pins the
exact integration points + the one real design decision, so the next session can execute
cleanly (it is delicate hot-path work — do it with fresh budget, not at a tail end).

## The one real decision: which store carries plasticity weights?
There are two stores (see [[answer-pack-vs-cloud-graph-split]] in memory):
- **Candidate store** `data/cloud_brain/candidate_runs/<active>/relations.jsonl` —
  written by `VerifiedStore`; rows have NO `weight` field; this is what `/status` counts and
  what the worker grows. Relation rows: relation/source_concept_id/target_concept_id/...
- **SemanticCloudStore** `packages/cloud_brain/semantic_store.py` (`load_relations`/
  `save_relations`, dict[relation_id]→row) — rows DO have `weight`/`seen_count`; this is the
  semantic_dedupe path that already does +0.08 strengthening.

**Recommendation:** make the **candidate store** the plasticity substrate (it is the live
graph the worker grows and answers read). Add `weight` (+ `info_weight`, `usage_count`) to
its relation rows; `plasticity_tick` already assigns `weight = informativeness` when missing,
so the first tick backfills weights for existing rows. Keep SemanticCloudStore as-is. (The
alternative — converging both stores — is a larger refactor; not required for plasticity.)

## Integration point A — `plasticity_tick` as the worker's "sleep consolidation"
File: `apps/api/app/routers/cloud_brain.py`, function `_continuous_worker()` (~line 1573),
the `while True:` learn loop (interval `ATANOR_LEARN_INTERVAL_SEC`, default 60s).

Add a maintenance cadence INSIDE the loop (runs in the worker thread → no external writer,
no race with learning writes since both are this thread):
```
# every N ticks, consolidate: informativeness reweight -> decay -> prune (bounded memory)
if tick_count % PLASTICITY_EVERY == 0:
    store = _active_candidate_store()
    rels = list(store.load_relations())            # or read relations.jsonl
    res = plasticity_tick(rels, datetime.now(timezone.utc),
                          half_life_days=float(os.getenv("ATANOR_PLASTICITY_HALFLIFE","45")),
                          prune_floor=float(os.getenv("ATANOR_PLASTICITY_FLOOR","0.05")))
    store.save_relations(res["kept"])              # pruned rows dropped -> bounded
    # log res["stats"]; emit to metrics
```
Notes:
- `PLASTICITY_EVERY` ~ every 30–60 learn ticks (i.e. tens of minutes), not every tick.
- This is the decay/prune half of plasticity; it BOUNDS memory (ties to the durable
  "bounded" invariant in [[clean-foundation-live]]). Parse-error edges seen once fade and
  get pruned; corroborated/used edges survive.
- IS_A is held strong inside `plasticity_tick` (info=1.0) so taxonomy never decays away.

## Integration point B — `reinforce_traversed` at answer time (learn from thinking)
File: `apps/api/app/services/alpha_services.py`, method `activate_memory(query,...)` (~line
113). It returns `active_nodes` / `active_edges` / `semantic_skeleton` — the edges traversed
to answer. After activation, reinforce those edges so used associations strengthen + refresh
recency (so the next decay tick won't prune them):
```
from packages.cloud_brain.neuroplasticity import reinforce_traversed
edge_ids = [e.get("relation_id") for e in activation.get("active_edges", []) if e.get("relation_id")]
# load -> reinforce_traversed(relations, edge_ids, now, amount=0.03) -> save
```
Notes:
- Keep `amount` small (~0.02–0.03) so a single query nudges, not dominates.
- This must be cheap: batch the save, or accumulate reinforcement and flush on the worker's
  maintenance tick (preferred — avoids a write on every query / read-path latency + race).
  Recommended: activate_memory only RECORDS traversed edge_ids into an in-memory counter;
  the worker's plasticity tick (A) applies the reinforcement + decay together. This keeps the
  hot read-path write-free and resolves the race cleanly.

## Why a restart is required
Both are code changes in already-imported modules; the running uvicorn will not hot-reload
them. Go-live = the named operator restart (Option A: stop worker → restart :8502 → resume
worker), same sequence proven for the earlier go-live. Predicate-relation answer rendering
(already committed, `eff4db5c`) also activates on that same restart.

## Verification plan
1. Unit: `neuroplasticity._self_test()` stays green.
2. After wiring + restart: let the worker run; confirm relation rows gain `weight`/`info_weight`;
   confirm low-info predicates (be/하다) carry low weight, contentful high, with NO word list.
3. Decay/prune: seed an old un-reinforced junk edge; confirm a maintenance tick prunes it and
   relation count stays bounded over time (memory does not grow unboundedly).
4. Usage: ask the same question repeatedly; confirm the traversed edges' `weight`/`usage_count`
   rise and they survive a decay tick that prunes un-asked peers.
5. Answers stay honest (named→grounded, non-named→abstain) — no regression.

## Open follow-ups (not blocking)
- Surface a Cloud Brain panel metric for plasticity (avg weight, pruned/tick, top reinforced).
- Promotion already carries predicate relations; once weights exist, rank/threshold promoted
  predicate relations by weight so only strong associations reach answers.
