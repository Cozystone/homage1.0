# Cloud Brain pipeline-fix Step 3 — durable bounded continuous worker (DESIGN ONLY)

Codex recommendation #3 for "infinite learning that never OOM-resets". This is DESIGN
(no live change applied) because it modifies the RUNNING daemon worker — it needs Codex's
approach review before touching the live loop. Steps 1–2 (decomposer) are already applied.

## Findings (read-only, file:line)
- `apps/api/app/routers/cloud_brain.py:1573` `_continuous_worker()` is a daemon thread
  (started at `:1664`). At `:1635` it calls
  `_learning_loop_for_request().run_once(payloads=payloads, ...)` **directly** — this bypasses
  the bounded runner's caps (store_mb, candidate_files, CPU, ResourcePressureMonitor).
- The bounded path `bounded_learning_runner.py:328 run_bounded_candidate_learning(...)` enforces
  `BoundedLearningRunConfig` caps (`:67` max_payloads/max_seconds/max_store_mb/max_cpu_percent/
  max_candidate_files, presets at `:99/:109/:119`) and pulls payloads from a **feeder**
  (`:371 feeder.run_once().payloads`) — NOT a drop-in for the worker, which builds its OWN
  payloads from Tavily/wiki (`:1602/:1607`).
- Firehose / unbounded-growth risks Codex flagged: `utterances.jsonl` append (~`:1468`) and
  `relation_discovery.jsonl` grow with no size cap; `read_text().splitlines()` full-file loads
  in `accumulator.py:81/231` and `candidate_read_model.py:36`.

## Two integration options for the cap (pick one — Codex to advise)
**A. Make the bounded runner accept provided payloads.**
Add `payloads: list | None = None` to `run_bounded_candidate_learning`; when given, skip the
feeder pull (`:371`) and batch THOSE through the same cap loop (`:416-425`, ResourcePressureMonitor,
max_store_mb / max_candidate_files checks). Worker `:1635` then calls
`run_bounded_candidate_learning(config=<profile>, payloads=payloads)` instead of `run_once`.
- Pro: one cap implementation, worker reuses it fully. Con: touches the runner signature.

**B. Inline cap guard in the worker (minimal).**
Before `:1635`, check the candidate store size (max_store_mb) and a ResourcePressureMonitor reading;
if over cap, skip the tick (sleep) instead of ingesting. Keep `run_once` but gate it.
- Pro: smallest change, runner untouched. Con: duplicates cap logic; weaker than A.

**Recommendation:** A (single source of truth for caps), behind a feature flag
`ATANOR_CONT_BOUNDED=1` so it's reversible (flag off = current behaviour).

## Firehose / file-growth rotation (lower risk, can land first)
- Add size-based rotation to the `utterances.jsonl` and `relation_discovery.jsonl` appenders:
  when a file exceeds `MAX_FIREHOSE_MB` (e.g. 64 MB), rename to `*.<ts>.jsonl` (or drop oldest)
  and start fresh. Bounded disk, bounded memory on later reads.
- For the full-file `read_text().splitlines()` loads (`accumulator.py:81/231`,
  `candidate_read_model.py:36`): switch to streaming line iteration or a maintained count, so
  large stores don't load entirely into RAM (the real OOM cause).

## Rollout (each reversible; live worker change LAST)
1. (this doc) design + Codex approach review.
2. Firehose rotation + streaming reads (no behaviour change to learning, just bounded I/O). [auto_ok]
3. Bounded-worker integration (option A) behind `ATANOR_CONT_BOUNDED` flag. [auto_ok, but live worker]
4. Step 4: re-train new run-id store with fixed pipeline → validate via battery → **swap active
   pointer** [operator_only — irreversible live transition].

## Asks for Codex
1. Option A vs B for the cap?
2. Is restarting/!modifying the running `_continuous_worker` safe live, or stop→patch→start?
3. Firehose rotation vs hard-cap-and-drop — which fits the "permanent memory" goal (don't lose history)?
