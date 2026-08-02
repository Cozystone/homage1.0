# Context Capsule

## Current Objective

Homage1.0 Alpha end-to-end MVP is implemented, verified, and deployed with a
research-backed Neuro-Efficiency Layer and a sustained-learning stability
profile with startup hardware benchmark adaptation.
Latest work also changed RAG answer behavior so no-direct-evidence structure
questions still generate a native architecture answer, external unknown facts
return no-evidence memory coverage instead of architecture leakage, and GraphRAG
signals now show active node pulses rather than path text. The latest update
adds `∞` continuous learning mode with cumulative elapsed time, a stop control,
and a bounded rolling 3D graph render window. The current follow-up clarifies
the real/simulated boundary, adds adaptive 3D zoom, and blocks/stops infinite
learning when real local telemetry crosses safety watermarks. Current work adds
a local-web-to-local-FastAPI companion connection and clarifies that
`target_nodes` is a long-run budget while `graph_3d` is a representative browser
sample. Production UI now works as a fallback demo/lab viewer; real PC
measurement and real cumulative learning should use local web + local FastAPI
unless an HTTPS local companion is configured.
Current UI follow-up makes `실험실` the first/default workspace, turns
the old `누적학습` space into a read-only local/API viewer, collapses the lab flow to
`수집 / 학습 / 출력`, and fixes misleading graph growth jumps/detached visual
clusters. Latest follow-up makes the learning signal truthful: moving orange
edge pulses are shown only when `POST /api/memory/build` actually adds visible
relations, Guardrail is folded into the output stage automatically, the right
status/settings area is collapsed by default, and the cumulative viewer reports
the real local daemon worker state.
Latest follow-up stabilizes the max-profile lab graph and learning handoff:
`500,000` remains a long-run budget while the UI renders a bounded `1,720` node
/ `3,421` relation representative sample; the sample now grows by replayed
frames, uses volumetric anchor-local placement, keeps the collected graph
visible during learning, and routes all chat questions through
`/api/graphrag/query` with web search selected only when the query needs it.
Current design follow-up renames the user-facing cumulative space to
`클라우드 브레인` and defines it as the future shared/public ontology layer:
local private brain first, fresh web second, Cloud Brain graph fragments as
structured fallback when search is weak or unavailable.

## Current Branch

`feature/datagate-v0`

## Last Commit

Latest local commit before this update: Clarify live learning limits and safety telemetry

## Deployment

- https://homage-alpha.vercel.app
- Current production deployment:
  https://web-1bwyui7xe-anthony-kims-projects-bc874109.vercel.app

## Relevant Files

- `apps/api/app/main.py`
- `apps/api/app/services/alpha_services.py`
- `apps/web/app/page.tsx`
- `apps/web/app/Rag3DScene.tsx`
- `apps/api/app/routers/factory.py`
- `apps/web/app/api/factory/build/start/route.ts`
- `apps/web/app/api/graphrag/query/route.ts`
- `apps/web/app/api/_alphaDemo.ts`
- `apps/api/app/routers/neuro.py`
- `apps/web/app/api/neuro/plan/route.ts`
- `apps/web/app/api/neuro/stability/route.ts`
- `apps/web/app/api/neuro/benchmark/route.ts`
- `packages/neuro_efficiency`
- `packages/knowledge_bakery/knowledge_bakery/daemon.py`
- `apps/api/app/routers/learning.py`
- `docs/RESEARCH_NEURO_EFFICIENCY.md`
- `docs/LONG_RUN_STABILITY_PLAN.md`
- `docs/HARDWARE_BENCHMARK_ADAPTATION.md`
- `docs/CODEX_GOAL_PROMPT_HOMAGE_RESEARCH.md`
- `docs/CLOUD_BRAIN_ARCHITECTURE.md`
- `packages/ontology_forge`
- `packages/rag_engine`
- `packages/guard`
- `packages/model`
- `packages/trainer`

## What Changed

- Added deterministic Alpha pipeline packages.
- Added FastAPI endpoints for Ontology, GraphRAG, Guardrail, telemetry, and Oven dry-run.
- Added unified BakeBoard Alpha UI with training loss visualization.
- Added deployable Next.js fallback API routes.
- Added Neuro-Efficiency package/API/UI for event sparsity, modular routing,
  continual/few-shot/self-supervised learning policy, compression, and estimated
  compute reduction.
- Added Sustained Learning Stability Profile with RAM/VRAM/storage watermarks,
  queue caps, graph hot-window/UI LOD policy, checkpoint cadence, and
  backpressure rules for the user's target desktop hardware.
- Added `GET/POST /api/neuro/stability` to FastAPI and the deployable Next.js
  fallback route.
- Added the BakeBoard `지속 운전 안전장치` process card and learning-volume
  targets for lite/standard/deep/max long-run profiles.
- Added `GET/POST /api/neuro/benchmark` to measure local CPU/RAM/GPU/disk at
  startup and recommend `lite` / `standard` / `deep` / `max`.
- Added the BakeBoard `시스템 벤치마크` card and `벤치마크 재측정` action.
- The actual local machine measured as `Performance desktop` and recommended
  `max`; BakeBoard auto-selected `최대` when connected to local FastAPI.
- Added open-structure RAG generation for questions like `네 구조 설명해봐`.
- Changed signal UI from `신호 경로` to `활성 노드`; orange pulsing now marks
  currently active nodes, not a fixed route.
- Added no-evidence routing so external unknown facts do not leak Homage
  architecture answers.
- Added direct target-node input for learning volume and wired it into
  stability planning plus Build Start.
- Added `∞` learning-volume mode:
  - target nodes: 500,000
  - scheduled chunks: 4,096
  - text budget: continuous
  - representative 3D render window: 2,000 nodes
  - cumulative learning timer and `학습 중지` stop control
- Updated Build Start fallback to return `alpha-continuous-harvest` and
  `training_gate.continuous: true` for infinite learning.
- Live-synapse growth now supports a rolling window so candidate nodes can keep
  accumulating while the browser renders a bounded representative graph.
- Live-synapse display now reports preserved API anchor nodes, visible new
  `live-synapse-*` nodes, and the latest new node id. Lab mode no longer folds
  live nodes into hidden history.
- 3D zoom-out is graph-size responsive instead of capped at a fixed camera
  distance; the 3D host exposes camera/node debug data for browser verification.
- FastAPI system telemetry now includes `source: local-fastapi`, RAM total/used,
  RAM available, disk free, and CPU percent when available.
- Next system telemetry fallback marks itself as `deployment-sandbox` or
  `local-next` so deployed sandbox CPU/RAM values are not confused with the
  user's PC.
- Local BakeBoard can now connect from the browser to the viewer's own
  `http://127.0.0.1:8000` FastAPI backend for local telemetry, benchmark,
  stability, and Build Start APIs.
- Production browser verification showed that HTTPS deployment pages can be
  blocked from calling an HTTP loopback backend before the request reaches
  FastAPI; the UI now explains this and recommends local web or HTTPS local
  companion for real PC measurement.
- FastAPI now serves `POST /api/factory/build/start` with the same Alpha Build
  Start contract as the Next fallback.
- Build Start responses now expose target/sample semantics:
  `target_semantics`, `representative_node_count`, `representative_edge_count`,
  `target_realized`, and `sampling_explanation`.
- Local connector GET requests no longer force CORS preflights with
  `Content-Type: application/json`; transient local API failures now keep the
  connector healthy when `/health` still succeeds.
- The UI now explains that standard `10,000` target runs start from a
  representative API anchor set; max/infinite runs can target `500,000` nodes
  while lab live nodes remain visibly appended instead of being hidden.
- Added a local cumulative-learning daemon layer that persists
  `daemon_state.json`, writes checkpoint snapshots, reports `resume_needed`
  after process/PC restart, and exposes FastAPI status/start/resume/stop/
  checkpoint endpoints.
- Split BakeBoard into `클라우드 브레인` and `실험실` workspaces. The deployed app
  treats `클라우드 브레인` as a lab viewer only; real daemon controls are local.
- Reordered the split so `실험실` is first/left and `클라우드 브레인` is a secondary
  read-only viewer; the deployed cumulative view no longer exposes direct
  start/stop/checkpoint controls.
- Simplified the visible lab process into `수집`, `학습`, and `출력`.
- Added `?workspace=daemon` / `?view=cumulative` routing for direct local
  cumulative-view links.
- Fixed two graph validity/UX issues:
  - Build Start frames no longer jump from `9` nodes to about `72%` of the
    sample on the third expansion; both FastAPI and Next fallback now use
    smoother sample progression.
  - live-synapse placement no longer drifts by an unbounded ring offset and the
    3D renderer preserves source-anchor coordinates more strongly, reducing
    detached side clusters and misleading long relation lines.
- Added truthful 3D learning-edge motion:
  - `관계 계산` compares previous and newly returned memory graph edges
  - moving orange edge particles are rendered only for new stored relation edges
    that are present in the visible graph
  - no-change runs show `학습 완료: 새 연결 변화 없음` and keep active
    edge/pulse counts at zero
  - browser verification used an uncommitted temporary cleaned document to
    confirm a real increase from 152/540 to 239/855, then removed it and rebuilt
    back to 152/540
- Folded Guardrail into the output flow:
  - RAG chat automatically calls `/api/guard/check` after `/api/graphrag/query`
  - the latest query routing keeps every user question on the same
    `/api/graphrag/query` path; conversation queries skip web evidence, fresh
    news queries select `news-rss`, and person lookup queries select
    `wikipedia`
- Max-target graph/learning follow-up:
  - FastAPI and Next Build Start graph generation now use bounded volumetric
    anchor clusters instead of unbounded rings
  - the 3D renderer normalizes source coordinates, grows into a thicker
    id-stable volume, and uses closer bounds-aware camera fitting
  - browser verification showed max Collect replay from `12` to `860` to
    `1,720` visible nodes, final cameraZ `61.2`, and `1,720` nodes /
    `3,421` relations
  - API geometry verification measured radius max `9.804`, z span `11.089`,
    and edge max `8.6`
  - `관계 계산` keeps the collected representative graph visible when the
    persistent memory graph is smaller and activates confirmed representative
    relation edges after the learning API completes
  - the learning card now separates representative graph counts from stored
    memory counts
  - local benchmark/stability refresh now uses the FastAPI benchmark in the
    same refresh cycle, showing RAM soft `22.4GB` on the local RTX 5080 /
    31.1GB RAM machine
  - production deploy succeeded and `https://homage-alpha.vercel.app` now
    points to
    `https://web-1bwyui7xe-anthony-kims-projects-bc874109.vercel.app`
  - production API max Build Start returns `1,720` nodes / `3,421` relations
    for the `500,000` long-run target
- Cloud Brain architecture added:
  - public/shared ontology graph fragments, not external LLM answers
  - virtual edges with frequency/evidence counters
  - potentiation, consolidation, decay, and pruning
  - lab fallback order: local graph -> fresh web -> Cloud Brain fragments
  - Alpha endpoint facade implemented: `/api/cloud-brain/status`, `/query`,
    `/ingest`, `/consolidate`, `/prune`
  - public cloud storage is still future; current facade is local-daemon-backed
  - the manual Guardrail checker is hidden
- Hippocampus daemon implementation added:
  - new `knowledge_bakery.learning_daemon`
  - `data/raw` `.txt`/`.md` watcher
  - moves new files to `data/cleaned`
  - runs `ontology_forge` per batch and refreshes global `data/ontology`
  - stores `synaptic_nodes`, `synaptic_edges`, `ingested_files`, and
    `learning_events` in SQLite WAL
  - repeated edges potentiate with `weight += 0.1`
  - decay/pruning deletes low-weight edges and orphan nodes
  - optional Neo4j Cypher `MERGE` mirror if env credentials exist
  - collapsed chat status shows RAG confidence, evidence count, and Guard score
- Raised the local memory graph display from a demo cap to 900 nodes and 1,800
  edges so real local memory growth is visible.
- Collapsed the right-side settings/status UI by default and shortened the
  bottom dashboard into `시스템 로그`.
- Added the Codex Desktop long-run research goal prompt document.
- Real local benchmark hardware is passed into stability recalculation.
- Infinite learning preflight/auto-stop now checks real telemetry for RAM,
  VRAM, and disk reserve pressure.
- Current Alpha learning is not random sentence learning: the system chunks
  accepted/reference text, extracts concept candidates deterministically,
  generates typed relations, and visualizes continual growth until durable graph
  mutation persistence is implemented.
- Improved dense 3D graph spacing with spread layout, collision relaxation,
  label thinning, and camera scaling.
- Added research note with SNN, neuromorphic, EWC, prototype, MAE, compression,
  and Loihi references.
- Added long-run stability note.
- Deployed and browser-tested the production app.

## Commands Run

- `pytest packages/datagate packages/ontology_forge packages/rag_engine packages/guard packages/model packages/trainer packages/neuro_efficiency apps/api -q`
- `PYTHONPATH=... python -m pytest packages/datagate packages/ontology_forge packages/rag_engine packages/guard packages/model packages/trainer packages/neuro_efficiency apps/api -q`
- `python -m compileall ...`
- `npm --workspace apps/web run build`
- local browser verification on `http://127.0.0.1:3050` with FastAPI
  `http://127.0.0.1:8042`
- `PYTHONPATH=... python -m pytest packages/knowledge_bakery/tests/test_daemon.py apps/api/tests/test_learning_daemon_api.py -q`
- `git diff --check`
- `npx vercel --prod --yes`
- `npx vercel alias set web-ffvjjolxy-anthony-kims-projects-bc874109.vercel.app homage-alpha.vercel.app`
- `npx vercel alias set web-7784z7z4w-anthony-kims-projects-bc874109.vercel.app homage-alpha.vercel.app`
- `npx vercel alias set web-dxspwpa3d-anthony-kims-projects-bc874109.vercel.app homage-alpha.vercel.app`
- Local hardware verification used FastAPI on `127.0.0.1:8002` and Next
  production server on `127.0.0.1:3025`.

## Test Results

- 60 Python tests passed with explicit package `PYTHONPATH`.
- Latest targeted verification: `npm --workspace apps/web run build` passed and
  `PYTHONPATH=... python -m pytest apps/api packages/knowledge_bakery
  packages/rag_engine -q` passed with 23 tests.
- Latest UI/browser verification:
  - final local lab link: `http://127.0.0.1:3050/?workspace=lab&api=http://127.0.0.1:8042`
  - cumulative viewer link: `http://127.0.0.1:3050/?workspace=daemon&api=http://127.0.0.1:8042`
  - no-change learning run produced active edges 0 / pulses 0
  - real temporary learning probe produced active edge keys 18 / pulse objects
    69, then was removed and memory rebuilt back to 152 nodes / 540 relations
  - RAG chat auto-Guardrail produced a collapsed status with `Guard 65점`
  - screenshots: `docs/screenshots/134-learning-edge-pulse-actual.png`,
    `135-chat-collapsed-auto-guard.png`,
    `136-daemon-readonly-viewer.png`,
    `137-final-lab-local-3050.png`
  - production alias `https://homage-alpha.vercel.app` points to
    `web-dxspwpa3d-anthony-kims-projects-bc874109.vercel.app` and was
    browser-verified for lab three-stage cards and read-only cumulative viewer
- Python compile passed.
- Frontend build passed.
- Local browser verification passed, including Neuro-Efficiency Rebalance and
  the sustained stability card with `최대` learning volume persisting after
  auto-refresh.
- Local browser verification passed for startup hardware benchmark adaptation:
  `Performance desktop`, `추천 최대`, `로컬 측정`, and Build Start at
  768 chunks / 420k chars.
- Local browser verification passed for structure answer generation and active
  node pulses with no path wording.
- Production API and browser verification passed for `네 구조 설명해봐`:
  native open-structure generation, no direct-evidence fallback copy,
  `external_llm: false`, and orange active-node pulses instead of path traces.
- Local browser verification passed for no-evidence external questions,
  `GraphRAG가 뭐야` without `읽힌 경로`, custom `1,200` target nodes, and dense
  graph rendering up to `358/360` representative nodes by DOM verification.
- Production API verification passed for no-evidence RAG and custom
  `target_nodes: 50000` Build Start scaling; production browser capture shows
  the new target-node input.
- Local API verification passed for infinite Build Start:
  `alpha-continuous-harvest`, 250,000 target nodes, 2,000 chunks, 600 visual
  node budget, and continuous Harvest/Ontology Forge states.
- Local browser verification passed for `∞` selection, continuous build start,
  cumulative elapsed learning time, candidate-node growth, 600-node render cap,
  and `학습 중지`.
- At 42 seconds, the browser showed 702 accumulated candidates while the visible
  graph stayed at `600/600`; after stopping, it preserved 1분 31초 elapsed time
  and 942 accumulated candidates.
- Production deploy succeeded and `https://homage-alpha.vercel.app` now points
  to the infinite learning version.
- Production API/browser verification passed for `∞` continuous learning:
  `alpha-continuous-harvest`, 2,000 chunks, 600 visual nodes, cumulative elapsed
  time, candidate-node growth, and stop control.
- Local actual telemetry verification passed:
  - system telemetry read 32 CPU threads, about 31.1GB RAM, about 165.5GB free
    disk, and `source: local-fastapi`
  - GPU telemetry read RTX 5080, about 15.9GB VRAM, and about 9GB VRAM currently
    used during verification
  - benchmark recommended `max`
  - 250,000-node stability plan used about 186.1GB storage reserve
  - infinite learning preflight was correctly blocked because RAM crossed the
    soft watermark
  - finite max build showed preserved anchors plus new `live-synapse-*` ids
  - responsive zoom-out reached camera distance `187.4` on a 358-node graph
- Production verification passed after redeploy:
  - system telemetry labels deployment values as `deployment-sandbox`
  - browser showed preserved anchors, visible new live nodes, summarized history,
    and Alpha boundary copy
  - zoom-out reached camera distance `134.7` on a 600-node graph
- Local FastAPI companion verification passed:
  - FastAPI factory route previously returned standard `visual_node_budget:
    210`; this has now been raised so standard `10,000` runs use
    `visual_node_budget: 480` and about `413` API anchors
  - local browser connected to `http://127.0.0.1:8000` from a separate Next
    production server
  - re-verification used fresh FastAPI on `127.0.0.1:8003` and Next production
    server on `127.0.0.1:3032`; FastAPI logs confirmed browser
    `OPTIONS/POST /api/factory/build/start` returned 200
  - standard Build Start should now show `10,000` long-run target,
    `480` visual budget, about `413` API anchors, and explicit copy explaining
    the bounded render window
  - screenshot: `docs/screenshots/117-local-fastapi-standard-sample-explained.png`
  - screenshot: `docs/screenshots/118-local-fastapi-connected-render-cap-fixed.png`
  - screenshot: `docs/screenshots/119-local-fastapi-target-sample-explanation.png`
  - screenshot: `docs/screenshots/120-production-local-http-boundary-message.png`
- 2026-06-11 update:
  - Build Start now accepts a `500,000` node long-run target in both Next.js
    fallback and local FastAPI.
  - `max` and `infinite` presets default to `500,000` nodes, `4,096` chunks,
    and a `2,000` node rolling frontier/summary render budget.
  - Live growth no longer stops after 8 demo pulses; it accumulates until the
    selected long-run target while the 3D scene renders only a bounded
    representative window.
  - Stability/benchmark planning now supports `500,000` nodes, `3,000,000`
    max relation input, a `24,000` hot graph window, and a `2,000` UI render
    budget for high-end desktop profiles.
- Deployed browser verification passed, including Neuro-Efficiency Rebalance.

## Current Blockers

- None.

## Latest 2026-06-12 Update

- Lab UI now runs as gated `수집 -> 학습 -> 출력`.
  Downstream actions stay disabled until the previous stage reaches 100%.
- The 3D GraphRAG scene now uses stable volumetric node placement and
  bounds-based camera fitting. It expands the visible volume and only moves the
  camera farther out when needed; graph updates no longer reset the camera to
  the initial close view.
- Finite Collect no longer starts client-side live-synapse growth after the API
  graph is rendered. Latest browser verification showed 653 visible nodes /
  1,295 relations, cameraZ 79.0, maxZoom 947.8, no hidden live-synapse history,
  and no `새 노드 0`.
- Greeting/conversation queries no longer route through web search or memory
  activation. `안녕` returned a clean Korean greeting with no Microsoft/Bing
  evidence and no stale active-node overlay.
- The cumulative-learning workspace is now blank until both local FastAPI and
  the actual local daemon worker are alive. With local API connected but worker
  stopped, the viewer shows `worker not alive` and no graph host.
- Current local verification links:
  - Lab: http://127.0.0.1:3055/?workspace=lab&api=http://127.0.0.1:8043
  - Cumulative viewer:
    http://127.0.0.1:3055/?workspace=daemon&api=http://127.0.0.1:8043
- Production alias now points to:
  https://web-5gu3ndmzg-anthony-kims-projects-bc874109.vercel.app
  through https://homage-alpha.vercel.app.
- Production verification confirmed the default lab screen opens to the
  step-gated `학습 과정` cards and the cumulative-learning screen remains blank
  until a real local daemon is connected.
- Latest screenshots:
  - `docs/screenshots/139-stable-volume-sequential-no-live.png`
  - `docs/screenshots/140-greeting-no-web-search.png`
  - `docs/screenshots/141-daemon-blank-until-local-worker.png`
  - `docs/screenshots/142-production-lab-stage-default.png`
  - `docs/screenshots/143-production-daemon-blank-viewer.png`

## Constraints / Non-goals

- No external paid APIs.
- No web crawling.
- No LLM judging.
- No pretrained weights.
- Homage Oven is a dry-run scaffold only.
- Neuro-Efficiency values are deterministic estimates until real traces and
  hardware profiles are persisted.
- Sustained stability is currently a planning/API/UI layer. The live ontology
  store still needs append-only graph events plus a SQLite WAL hot index before
  unattended multi-day runs.
- Infinite learning mode is currently a local/deployed Alpha runtime loop in the
  browser. It is not yet a durable background crawler and does not persist every
  live graph mutation across refreshes.
- With real local telemetry, infinite learning can refuse to start or stop
  itself before resource pressure kills the machine. The current maximum
  workload target is `500,000` nodes with a bounded `2,000` node render window.
- Hardware benchmark auto-apply requires local FastAPI. Deployed fallback cannot
  measure the viewer PC and returns `can_read_local_hardware: false`.
- Local UI can use real viewer hardware through the local FastAPI connector.
  Deployed UI remains a deterministic fallback when the browser blocks HTTPS to
  HTTP loopback calls.
- Finite Build Start modes currently fill a representative render sample rather
  than persisting the full long-run `target_nodes` budget. The append-only
  ontology event log and SQLite hot graph index are still required for true
  multi-thousand-node realization.
- No-direct-evidence architecture answers use internal Homage context for
  synthesis, but do not return it as retrieved document evidence.
- Unknown external facts are not guessed without memory evidence or Harvest
  input.

## Next 3 Actions

1. Implement the ontology event log and SQLite WAL hot graph index.
2. Persist live-synapse graph mutations and replay them as real learning events.
3. Add real Harvest source allowlists plus durable document provenance.

## What I Need From You

Review the deployed Alpha and choose whether to prioritize trace logging,
SNN experiments, or quantization calibration next.



