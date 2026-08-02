# Session Log

## 2026-06-11

- Read the PRD from `Homage1.0_PRD.md`.
- Created `docs/` and copied the PRD to `docs/Homage1.0_PRD.md`.
- Scaffolded FastAPI backend in `apps/api`.
- Scaffolded Next.js frontend in `apps/web`.
- Added mock `GET /api/pipeline/status` contract.
- Added BakeBoard dashboard cards.
- Added Next.js proxy route for local dashboard-to-backend status calls.
- Added project operating documents and README startup instructions.
- Installed Python and npm dependencies.
- Verified FastAPI compile, Next.js production build, live API status response, and live frontend HTTP 200.
- Verified the rendered BakeBoard in the in-app browser with all seven pipeline cards visible.

## 2026-06-11 — Milestone 2: DataGate core package (Claude Code)

- Read `docs/Homage1.0_PRD.md`, `PROJECT_STATE.md`, `TASK_BOARD.md`,
  `CONTEXT_CAPSULE.md`, and `HANDOFF_CLAUDE.md`.
- Implemented the DataGate core library at `packages/datagate` (per
  HANDOFF_CLAUDE.md §3–§5): `pyproject.toml` (name `datagate`, `pydantic>=2`,
  py>=3.11), `README.md`, and the `datagate/` modules `config`, `models`,
  `hashing`, `io`, `scoring`, `runner`, plus the `filters/` package
  (`base`, `min_length`, `duplicate_hash`, `special_char_ratio`,
  `link_density`, ordered `default_filters`).
- Enforced contract invariants in models: rejected ⇒ `rejection_reason` +
  `rejected_by`; accepted ⇒ `quality_score`; failed `FilterResult` ⇒ `reason`.
- Deterministic by design: sorted discovery, NFC+whitespace-collapse
  normalization, sha256 `doc_id`, no randomness/timestamps in decision paths.
  `DuplicateHashFilter` state resets per `PipelineRunner.run()`.
- Runner writes `data/cleaned/{doc_id}.txt`, `data/rejected/{doc_id}.txt`, and
  `data/metadata/documents.jsonl` (full-batch overwrite); unreadable files
  become `read_error` rejections.
- Added pytest suite (`tests/`): model validation, all four filters, scorer,
  end-to-end runner, and repeated-run determinism — 8-scenario fixture corpus.
- `pip install -e "packages/datagate[dev]"` succeeded; `pytest packages/datagate`
  → **36 passed**; confirmed `import datagate` pulls in no FastAPI.
- Updated `PROJECT_STATE.md`; created `HANDOFF_CLAUDE_CODE.md`.
- Deferred (out of scope this milestone): API router/service, pipeline-status
  stage-1 hookup, BakeBoard panel, Next.js proxy routes.

## 2026-06-11 - DataGate API/UI wiring

- Wired DataGate core into FastAPI with `/api/datagate/run` and
  `/api/datagate/status`.
- Updated `/api/pipeline/status` so DataGate reflects real run state while the
  other six stages remain mocked.
- Added Next.js DataGate proxy routes.
- Added a BakeBoard DataGate panel with Run button, polling, status summary,
  accept rate, rejection breakdown, timestamp, and error display.
- Added API tests for idle status, run completion, 409 running guard, and the
  seven-stage pipeline contract.
- Verified Python compile, `pytest packages/datagate apps/api -q`, and the
  frontend production build.
- Ran local smoke on backend `8001` and frontend `3001`; verified DataGate
  run/status, seven-stage pipeline status, Next proxy status, and BakeBoard UI
  Run button.

## 2026-06-11 - Homage1.0 Alpha end-to-end

- Implemented Ontology Forge, GraphRAG, Guardrail, telemetry, model scaffold,
  and trainer dry-run packages.
- Added FastAPI routers and services for all Alpha panels.
- Rebuilt BakeBoard into a unified single-page Alpha dashboard.
- Added deployed Next.js API fallback routes so the Vercel app works without
  local FastAPI.
- Added sample raw documents and training sample data.
- Verified 46 Python tests, Python compile, and frontend build.
- Ran local end-to-end smoke through DataGate, Ontology, GraphRAG, Guardrail,
  telemetry, Oven dry-run, pipeline status, and browser UI.
- Deployed to Vercel and verified the deployment in-browser.

## 2026-06-11 - Neuro-Efficiency research and architecture update

- Reviewed academic/professional sources for SNNs, neuromorphic software,
  continual learning, few-shot prototypes, self-supervised masking, model
  compression, and Loihi-style event hardware constraints.
- Added `docs/RESEARCH_NEURO_EFFICIENCY.md` with source links and structural
  decisions.
- Implemented `packages/neuro_efficiency`, a deterministic planning layer for
  event sparsity, modular routing, continual/few-shot/self-supervised learning
  policies, compression levers, and estimated compute reduction.
- Added FastAPI `GET/POST /api/neuro/plan`.
- Added Next.js deployed fallback route for `/api/neuro/plan`.
- Added a BakeBoard Neuro-Efficiency Layer panel and Rebalance action.
- Verified Python tests: 49 passed; compileall passed; Next production build
  passed.
- Verified local browser UI and deployed Vercel UI, including the Rebalance
  button.
- Deployed production:
  https://web-2ro6t5sdi-anthony-kims-projects-bc874109.vercel.app

## 2026-06-11 - MiroFish-inspired Korean console UI

- Inspected `666ghj/MiroFish` and the live demo at
  `https://666ghj.github.io/mirofish-demo/console/process/proj_f95898d38529`.
- Confirmed the useful UI pattern: top graph/split/workbench switcher, left
  memory graph, right process/workbench panel, and bottom system dashboard log.
- Noted MiroFish is AGPL-3.0, so no code was copied verbatim.
- Rebuilt the BakeBoard frontend in Korean as a MiroFish-inspired console:
  left ontology memory visualization, right learning-process/RAG-chat
  workbench, graph/split/workbench layout controls, and system log.
- Made RAG visible as a first-class chat workbench with evidence-backed
  responses.
- Verified `npm --workspace apps/web run build`.
- Verified local browser UI: split layout, layout switcher, and RAG chat
  response with evidence.
- Deployed and verified production:
  https://web-5rxd988wn-anthony-kims-projects-bc874109.vercel.app

## 2026-06-11 - Hybrid GraphRAG upgrade

- Reviewed Microsoft GraphRAG, Haystack, and MiroFish references for the RAG
  and visualization direction.
- Kept Homage on an internal deterministic engine instead of copying external
  code; MiroFish remains UI-structure inspiration only because it is AGPL-3.0.
- Upgraded `packages/rag_engine` from keyword matching to hybrid GraphRAG:
  document chunking, BM25-style lexical scoring, ontology node matching,
  one-hop graph expansion, phrase/coverage/graph retrieval signals, answer
  synthesis, citations, follow-up questions, and retrieval trace.
- Updated the Vercel fallback GraphRAG response to expose the same answer,
  citation, trace, and evidence-signal shape.
- Updated the Korean RAG chat UI to render synthesized answers and retrieval
  signals inside evidence cards.
- Added `docs/RAG_REFERENCE.md`.
- Verified locally in a browser at `http://127.0.0.1:3014`.
- Deployed production:
  https://web-8hayowqq4-anthony-kims-projects-bc874109.vercel.app
- `homage.vercel.app` was unavailable, so the deployment was aliased to:
  https://homage-alpha.vercel.app
- Verified the alias in-browser, including RAG chat answer rendering and
  retrieval-signal evidence cards.

## 2026-06-11 - RAG graph interaction and PRD audit

- Audited the current implementation against `docs/Homage1.0_PRD.md` and added
  `docs/PRD_ENGINE_AUDIT.md`.
- Confirmed Alpha covers DataGate, Ontology Forge, hybrid GraphRAG, Guardrail,
  telemetry, dry-run Oven, Neuro-Efficiency, and BakeBoard, while Harvest,
  Knowledge Bakery vector DB, full Homage-Core-30M training, and a separate
  Utterance Engine remain future work.
- Fixed RAG chat layout pressure by widening the workbench side in split mode,
  giving chat messages their own scroll region, widening action buttons, and
  auto-scrolling to the newest answer.
- Added interactive graph controls inspired by MiroFish-style operation:
  graph/split/workbench modes, refresh, full graph mode, node search/focus,
  zoom in/out, directional pan, pointer-drag pan, reset, and node/edge detail.
- Verified all visible buttons in the local browser: layout modes, Refresh,
  graph expand/reset/search/zoom/pan, RAG send, Guardrail check, DataGate,
  Ontology, GraphRAG open, Oven dry-run, Neuro replan, and header reset.
- Captured browser screenshots in `docs/screenshots/`.
- Verified `npm --workspace apps/web run build` and the 49-test Python suite.
- Deployed the updated UI to Vercel and re-aliased
  `https://homage-alpha.vercel.app` to the new production deployment.
- Verified the deployed alias in-browser with graph search/zoom and RAG answer
  evidence rendering.

## 2026-06-11 - Build Start and 3D GraphRAG flow

- Reviewed the Reddit discussion on LLM graph traversal for RAG and the linked
  `similarity-graph-traversal-semantic-rag-research` repository.
- Captured the design correction from the thread: semantic-similarity graphs
  are not full knowledge graphs unless Homage preserves typed entities,
  relation semantics, deduplication, and graph mutation/update history.
- Added `POST /api/factory/build/start`, an Alpha factory orchestrator that
  fetches a small allowlisted reference set, reports harvest status, emits
  typed ontology/RAG graph frames, and opens a training gate for the Homage Oven
  dry-run once enough typed nodes, edges, and evidence are visible.
- Added a Three.js `Rag3DScene` with drag rotation, wheel zoom, node selection,
  traversal highlighting, labels, and staged graph growth.
- Wired the Korean BakeBoard `Build 시작` button to switch into the 3D RAG
  memory view, show live process metrics, list harvested sources, and carry
  evidence into the RAG chat workbench.
- Added `docs/BUILD_FLOW_3D_RAG.md`.
- Verified `pytest` for all Python packages and API: 49 passed.
- Verified `npm --workspace apps/web run build`.
- Verified locally in the in-app browser with screenshots for Build Start,
  3D graph growth, drag/zoom interaction, and RAG evidence rendering.
- Deployed production:
  https://web-r27gc51la-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified the deployed alias in-browser with screenshots for Build Start, 3D
  GraphRAG growth, drag/zoom interaction, training-gate display, and RAG
  evidence rendering.

## 2026-06-11 - Compact console and continuous graph growth

- Changed the default split console from an almost even split to a 70/30 layout
  so the ontology/RAG memory graph dominates the screen while the process panel
  stays compact.
- Reduced UI density across the header, graph controls, process cards, chat
  composer, evidence cards, and system log.
- Added deterministic live-synapse growth pulses after Build Start so the 3D
  RAG graph keeps adding nodes and edges instead of stopping at the initial
  graph frames.
- Wired Learning Process buttons through a common running-state wrapper and
  direct result updates so DataGate, Ontology, GraphRAG, Guardrail, Oven, and
  Neuro actions visibly respond in the deployed fallback UI.
- Updated DataGate deployed fallback to return the completed run state instead
  of a bare running marker.
- Verified `npm --workspace apps/web run build`.
- Verified locally in-browser:
  - split ratio measured 1008px / 432px at 1440px width
  - Build Start grew from the base graph into live pulses
  - Learning Process buttons completed without errors
- Deployed production:
  https://web-2cq1iubf8-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified the deployed alias in-browser with compact 70/30 layout, live growth,
  DataGate process-button execution, and no application errors.

## 2026-06-11 - Native Homage Utterance Engine correction

- Re-read the PRD sections on role separation, Next Thought generation,
  Homage-Core, GraphRAG context bundles, and Homage Utterance Engine.
- Corrected the implementation direction away from external LLM adapters.
- Added a native Alpha utterance stage around GraphRAG:
  `intent -> concepts -> ontology path -> claim plan -> evidence -> surface text`.
- GraphRAG responses now return PMV, claim plan, active concepts, answer engine
  stages, and `external_llm: false`.
- Added graph color-legend intent handling so "색깔별 노드 의미" answers from
  the current ontology/RAG graph instead of falling through to generic evidence
  search.
- Verified locally with browser screenshots:
  - `docs/screenshots/84-native-cause-answer-local.png`
  - `docs/screenshots/85-native-legend-answer-local.png`
- Added chat send locking while an answer is generating to prevent slower
  GraphRAG responses from overwriting later local graph-inspection status.
- Redeployed production:
  https://web-bpxui7tde-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified production API responses for native GraphRAG and color legend
  answers with `external_llm: false`.

## 2026-06-11 - Sustained learning stability profile

- Added a target-hardware stability planner for Ryzen 9 9950X3D, RTX 5080
  16GB, 32GB RAM, and 1TB SSD.
- Added `GET/POST /api/neuro/stability` in FastAPI and the deployable Next.js
  fallback API route.
- Added queue caps, RAM/VRAM/storage watermarks, graph hot-window sizing,
  UI render budgets, checkpoint cadence, and backpressure policy.
- Added the BakeBoard `지속 운전 안전장치` process card and made learning-volume
  presets recalculate stability targets:
  - lite: 3,000 nodes / 9,000 edges / 12h
  - standard: 10,000 nodes / 40,000 edges / 72h
  - deep: 25,000 nodes / 100,000 edges / 168h
  - max: 50,000 nodes / 240,000 edges / 168h
- Fixed an auto-refresh bug where the stability card could revert from the
  selected learning volume back to the default profile.
- Tightened the stability summary card layout to avoid cramped text in the
  70/30 split view.
- Added `docs/LONG_RUN_STABILITY_PLAN.md`.
- Verified:
  - `python -m compileall packages\neuro_efficiency apps\api\app`
  - `python -m pytest packages\neuro_efficiency apps\api -q`: 11 passed
  - full Alpha Python suite with explicit `PYTHONPATH`: 55 passed
  - `npm --workspace apps/web run build`
  - local in-app browser at `http://127.0.0.1:3024`
- Deployed production:
  https://web-i1wdnz9bk-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified production `GET/POST /api/neuro/stability`.
- Verified production browser UI with the `최대` sustained-stability profile.
- Captured screenshots:
  - `docs/screenshots/88-sustained-stability-local.png`
  - `docs/screenshots/89-sustained-stability-max-local.png`
  - `docs/screenshots/90-sustained-stability-final-local.png`
  - `docs/screenshots/91-sustained-stability-production.png`
  - `docs/screenshots/92-sustained-stability-production-card.png`
  - `docs/screenshots/93-sustained-stability-production-card-visible.png`

## 2026-06-11 - Hardware benchmark adaptation

- Added `build_hardware_benchmark` to `packages/neuro_efficiency`.
- Added `GET/POST /api/neuro/benchmark` to FastAPI.
- Added a deployable Next.js fallback route at `/api/neuro/benchmark`.
- The local benchmark reads CPU thread count, RAM, GPU/VRAM through
  `nvidia-smi`, workspace disk capacity/free space, a short CPU loop probe, and
  a short disk write probe.
- Added tolerance so OS-reported 31GB RAM / 15.9GB VRAM is treated as the
  intended 32GB / 16GB hardware class.
- Added the BakeBoard `시스템 벤치마크` process card, startup benchmark run, and
  `벤치마크 재측정` button.
- Auto-apply now changes learning volume only when
  `can_read_local_hardware: true`, so Vercel fallback does not pretend to
  measure the user's actual PC.
- Verified the actual local machine:
  - profile: `Performance desktop`
  - recommendation: `max`
  - CPU threads: 32
  - RAM: about 31.1GB
  - GPU: NVIDIA GeForce RTX 5080
  - VRAM: about 15.9GB
  - disk write probe: about 900MB/s to 1GB/s in verification runs
- Verified locally with FastAPI on `127.0.0.1:8002` and Next production server
  on `127.0.0.1:3025`.
- Browser verification confirmed `최대` was automatically selected and Build
  Start prepared 768 chunks / 420k chars.
- Deployed production:
  https://web-ovsyv6i2f-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified production `GET /api/neuro/benchmark` returns `source:
  server-fallback` and `can_read_local_hardware: false`.
- Verified production browser UI shows fallback benchmark labeling instead of
  pretending to measure the viewer PC.
- Captured screenshot:
  - `docs/screenshots/94-hardware-benchmark-local.png`
  - `docs/screenshots/95-hardware-benchmark-production.png`

## 2026-06-11 - Active node signal and open structure answer

- Changed the RAG signal visualization from a path-like trace to active node
  pulses.
- The overlay now says `활성 노드` instead of `신호 경로`.
- Active GraphRAG nodes pulse orange while relation lines stay subdued, so the
  visualization reads more like momentary brain activation than route finding.
- Added internal architecture synthesis context for no-direct-evidence answers.
- `네 구조 설명해봐` now generates a native Homage architecture answer instead
  of saying the question is not directly connected to current evidence.
- Internal architecture context is used only for synthesis; returned
  `evidence_docs` and `citations` remain empty when no retrieved document chunk
  supports the answer.
- Added a regression test for structure questions without direct evidence.
- Verified:
  - `python -m compileall packages\rag_engine apps\api\app`
  - full Alpha Python suite with explicit `PYTHONPATH`: 59 passed
  - `npm --workspace apps/web run build`
  - local browser at `http://127.0.0.1:3026`
- Deployed production:
  https://web-ffvjjolxy-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified production API and browser UI:
  - `POST /api/graphrag/query` returns
    `homage-native-open-structure-v1`
  - `external_llm` remains `false`
  - no direct-evidence fallback text appears for `네 구조 설명해봐`
  - active node signal appears as orange pulsing nodes, not a path trace
- Captured screenshots:
  - `docs/screenshots/96-structure-answer-active-nodes-local.png`
  - `docs/screenshots/97-active-node-pulses-local.png`
  - `docs/screenshots/98-structure-answer-no-path-local.png`
  - `docs/screenshots/99-active-node-pulses-no-path-local.png`
  - `docs/screenshots/100-structure-answer-production.png`
  - `docs/screenshots/101-active-node-pulses-production.png`

## 2026-06-11 - No-evidence RAG and custom node target

- Split no-direct-evidence RAG behavior:
  - Homage/self-structure questions still use internal architecture context.
  - External unknown facts now return a no-evidence native answer instead of
    leaking the Homage architecture explanation.
- Removed `읽힌 경로` from generated GraphRAG answer text; the chat now says
  active node signal instead.
- Added regression coverage for unknown external entity questions.
- Added a direct `목표 노드` number input beside the learning-volume presets.
- Sent `target_nodes` to stability planning and Build Start.
- Build Start now scales chunk budget, text budget, and representative node
  budget from the custom target-node count.
- Increased representative graph generation and made generated ids unique
  across repeated topic waves.
- Improved 3D RAG spacing with deterministic spread layout, collision
  relaxation, label thinning for dense graphs, and graph-size camera scaling.
- Verified locally:
  - `python -m pytest packages\rag_engine -q`: 6 passed
  - full Alpha Python suite with explicit `PYTHONPATH`: 60 passed
  - `npm --workspace apps/web run build`
  - local browser at `http://127.0.0.1:3027`
- Browser verification:
  - `GraphRAG가 뭐야` answered without `읽힌 경로`
  - `유재석이 누구야` returned no-evidence memory coverage text with
    `external LLM` disabled wording
  - `1,200` target nodes produced a larger representative graph
  - max target-node stress reached `358/360` representative nodes and
    `358 nodes / 739 relations` by DOM verification
  - WebGL full screenshot capture timed out at the 358-node state; saved
    screenshots cover the visible 48, 73, 221, and 257 node states
- Deployed production:
  https://web-7784z7z4w-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified production API:
  - `유재석이 누구야` returns `homage-native-no-evidence-v1`
  - `external_llm` remains `false`
  - no Homage architecture leak or `읽힌 경로` text appears
  - `target_nodes: 50000` returns visual budget 360, 310 base nodes, 609 edges,
    and 2000 chunks
- Production browser verification confirmed the new `목표 노드` input is visible.
  In-app browser text entry on production was blocked by the browser virtual
  clipboard extension, so production interaction was verified through API plus
  visible UI capture.
- Captured screenshots:
  - `docs/screenshots/102-custom-node-target-local.png`
  - `docs/screenshots/103-rag-no-evidence-local.png`
  - `docs/screenshots/104-large-graph-spacing-local.png`
  - `docs/screenshots/105-large-graph-final-local.png`
  - `docs/screenshots/108-production-node-target-visible.png`

## 2026-06-11 - Infinite learning mode

- Added an `∞` learning-volume preset beside 가볍게/표준/깊게/최대.
- `∞` mode maps to 250,000 target ontology nodes, 2,000 scheduled chunks,
  continuous text budget, and a 600-node representative 3D graph window.
- Updated `POST /api/factory/build/start` so `∞` returns
  `alpha-continuous-harvest`, marks Harvest and Ontology Forge as running, and
  exposes `training_gate.continuous: true`.
- Added cumulative learning time in the UI and changed Build Start into a
  `학습 중지` control while continuous learning is active.
- Changed live-synapse growth to support a rolling visual window: candidate
  nodes keep accumulating, while the rendered 3D graph stays capped so the
  browser can handle long sessions.
- Clarified the Alpha learning model: it does not learn from random sentences;
  it chunks accepted/reference text, extracts concept candidates, generates
  typed relations, and currently visualizes continual growth deterministically
  until durable graph-event persistence is added.
- Verified:
  - `npm --workspace apps/web run build`
  - full Alpha Python suite with explicit `PYTHONPATH`: 60 passed
  - `git diff --check`
  - local API `POST /api/factory/build/start` with `learning_volume: infinite`
  - local browser at `http://127.0.0.1:3028`
- Browser verification:
  - `∞` selection changed the target-node input to `250000`
  - continuous build showed `∞ 지속 학습`, elapsed time, collection rounds, and
    candidate-node accumulation
  - after 42 seconds, visible graph stayed at `600/600` representative nodes
    while candidates reached `702`
  - stopping changed the header back to `빌드 시작` and preserved the stopped
    elapsed state
- Deployed production:
  https://web-96k7ncdo7-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Verified production API and browser UI:
  - `learning_volume: infinite` returned `alpha-continuous-harvest`
  - production browser showed `∞ 지속 학습 0분 19초`, 12 collection rounds,
    588 accumulated candidate nodes, and the `학습 중지` stop control
- Captured screenshots:
  - `docs/screenshots/109-infinite-learning-selected-local.png`
  - `docs/screenshots/110-infinite-learning-running-local.png`
  - `docs/screenshots/111-infinite-learning-stopped-local.png`
  - `docs/screenshots/112-infinite-learning-production.png`

## 2026-06-11 - Reality boundary, adaptive zoom, and safety stop

- Audited whether infinite learning was real data flow or visual simulation.
- Confirmed the current Alpha boundary:
  - harvested references and base 3D anchor graph come from API results
  - `live-synapse-*` nodes are deterministic client-side growth events
  - old live events can be summarized by `live-summary-*` nodes when the render
    window is full
  - durable crawler, graph event log, and real training updates remain future
    work
- Added UI telemetry to show:
  - preserved API anchor node count
  - visible new live node count
  - summarized history count
  - latest new live node id
  - hidden event count caused by render LOD
- Removed the old fixed 3D zoom-out ceiling and replaced it with graph-size
  responsive camera limits.
- Added `data-camera-z`, `data-max-zoom`, and `data-node-count` on the 3D host
  so browser verification can confirm camera range numerically.
- Extended local FastAPI system telemetry with RAM total/used/available,
  disk free, and source labels.
- Extended Next telemetry fallback with explicit `deployment-sandbox` /
  `local-next` source labels so production CPU/RAM numbers are not mistaken for
  the viewer PC.
- Wired real local benchmark hardware into stability recalculation.
- Added infinite-learning preflight/auto-stop checks for RAM, VRAM, and disk
  reserve pressure when real telemetry is available.
- Verified local actual hardware:
  - 32 CPU threads
  - about 31.1GB RAM
  - RTX 5080 with about 15.9GB VRAM
  - about 165.5GB free disk
  - benchmark recommendation: `max`
  - 250,000-node stability reserve: about 186.1GB
- Browser verification:
  - local FastAPI + local Next showed `actual PC` telemetry
  - infinite learning was preflight-blocked because RAM crossed soft watermark
  - finite max build showed `310` preserved anchors and newly generated
    `live-synapse-*` ids
  - repeated zoom-out reached camera distance `187.4`, above the previous fixed
    limit of `34`
- Deployed production:
  https://web-plao78fl2-anthony-kims-projects-bc874109.vercel.app
- Re-aliased production to:
  https://homage-alpha.vercel.app
- Production verification:
  - `/api/telemetry/system` returned `source: deployment-sandbox`
  - benchmark fallback remained `can_read_local_hardware: false`
  - infinite build still returned `alpha-continuous-harvest`
  - browser showed preserved anchors, visible new live nodes, summarized
    history, and `Alpha boundary` copy
  - production zoom-out reached camera distance `134.7` on a 600-node view
- Verified:
  - `npm --workspace apps/web run build`
  - full Alpha Python suite with explicit `PYTHONPATH`: 60 passed
  - `python -m compileall apps\api\app packages\neuro_efficiency`
- Captured screenshots:
  - `docs/screenshots/113-local-safety-preflight-block.png`
  - `docs/screenshots/114-local-anchor-new-node-trace.png`
  - `docs/screenshots/115-responsive-zoom-out-local.png`
  - `docs/screenshots/116-production-live-summary-zoom.png`

## 2026-06-11 - Local FastAPI companion and target/sample clarity

- Investigated why `lite` with a 3,000-node target showed about 115 nodes and
  why `standard` with a 10,000-node target stopped around 210 nodes / 427
  relations.
- Confirmed the cause: `target_nodes` was being treated as a long-run storage
  and training budget, while the 3D UI intentionally renders a bounded
  representative sample. For standard, the visual budget is
  `round(sqrt(10000) * 2.1) = 210`; relations grow to about 427 after visible
  live-synapse pulses fill that render window.
- Added FastAPI `POST /api/factory/build/start` so the local backend can serve
  Build Start directly instead of relying on the Next.js fallback route.
- Added target/sample metadata to Build Start responses:
  `target_semantics`, `representative_node_count`, `representative_edge_count`,
  `target_realized`, and `sampling_explanation`.
- Added CORS and Private Network Access support for localhost, `127.0.0.1`, and
  Vercel origins. Local BakeBoard can connect directly to the user's own
  `http://127.0.0.1:8000` FastAPI.
- Production browser verification showed that modern browsers can still block
  `https://homage-alpha.vercel.app` from calling an `http://localhost` backend
  before the request reaches FastAPI. The UI now explains that real PC
  measurement should use local web + local FastAPI unless an HTTPS local
  companion is configured.
- Added a BakeBoard local FastAPI connector control with URL entry, connect,
  reconnect, disconnect, and saved local URL behavior.
- Routed benchmark, telemetry, stability, and Build Start calls through local
  FastAPI when connected, with Vercel fallback still available when disconnected.
- Fixed a browser-side local connector bug where GET requests unnecessarily sent
  `Content-Type: application/json`, forcing many parallel CORS preflights and
  intermittently dropping the local backend state to `Failed to fetch`.
- Local GET requests now avoid custom headers, and transient local API failures
  keep the connector marked healthy when `/health` still succeeds.
- Updated the UI labels from `target` wording to `long-run target` wording and
  added explicit copy explaining that `graph_3d` is a representative browser
  sample, not the full target realization.
- Added regression tests for the FastAPI factory route, including the standard
  `10,000 -> 210 visual budget / 181 API anchors / target_realized false`
  behavior.
- Verified local browser behavior with FastAPI on `127.0.0.1:8000` and a Next
  production server on `127.0.0.1:3031`.
- Re-verified with fresh FastAPI on `127.0.0.1:8003` and Next production server
  on `127.0.0.1:3032`; FastAPI logs confirmed browser
  `OPTIONS/POST /api/factory/build/start` returned 200.
- Captured screenshot:
  - `docs/screenshots/117-local-fastapi-standard-sample-explained.png`
  - `docs/screenshots/118-local-fastapi-connected-render-cap-fixed.png`
  - `docs/screenshots/119-local-fastapi-target-sample-explanation.png`
  - `docs/screenshots/120-production-local-http-boundary-message.png`

## 2026-06-11 - 500k long-run target and larger rolling graph window

- Raised Build Start long-run `target_nodes` ceiling from `250,000` to
  `500,000` in both the Next.js fallback route and the local FastAPI route.
- Changed the `max` and `infinite` learning presets to default to `500,000`
  nodes, `4,096` chunks, and a `2,000` node representative render window.
- Increased standard `10,000` runs from the old `210` render cap to a `480`
  node window with about `413` API anchor nodes.
- Changed live growth from a fixed 8-pulse demo stop to a target-driven loop:
  it now keeps accumulating until the selected long-run target is reached,
  while the 3D canvas keeps only a rolling frontier plus summary nodes visible.
- Removed the finite graph-mode freeze that previously capped graph inspection
  around two pulses.
- Raised stability and benchmark planning to accept `500,000` nodes and up to
  `3,000,000` relations, with a `24,000` node hot window and `2,000` node UI
  render budget for 500k workloads.
- Optimized the Three.js scene for larger representative graphs by skipping
  pairwise collision passes above 600 nodes, reducing sphere segments, thinning
  halos, and sampling dense edge sets.
- Browser verification on local Next dev (`http://localhost:3010`) confirmed
  `최대` sets the input to `500000`, Build Start reaches `2000/2000`
  representative nodes, the 3D host reports `nodeCount: 2000`, and the overlay
  shows summary bundles plus hidden live history.
- Captured screenshot:
  - `docs/screenshots/121-500k-max-render-cap-local.png`

## 2026-06-12 - Local cumulative-learning daemon and lab-viewer deployment split

- Added a local Knowledge Bakery daemon state layer:
  - `packages/knowledge_bakery/knowledge_bakery/daemon.py`
  - persistent `data/memory/daemon_state.json`
  - persistent `data/memory/daemon_checkpoints/*.json`
  - status/start/resume/stop/checkpoint/tick helpers
  - resource guard for low disk/RAM before long local runs destabilize the PC
- Added FastAPI endpoints:
  - `GET /api/learning/daemon/status`
  - `POST /api/learning/daemon/start`
  - `POST /api/learning/daemon/resume`
  - `POST /api/learning/daemon/checkpoint`
  - `POST /api/learning/daemon/stop`
  - `POST /api/learning/daemon/tick`
- Added deployable Next.js fallback routes for the daemon endpoints. The
  fallback explicitly returns `mode: deployment-demo` and `local_required: true`
  so Vercel stays an honest lab viewer, not a fake long-running learner.
- Split BakeBoard into two workspaces:
  - `누적학습`: local long-running learner status, runtime, node/edge/event
    counts, checkpoint state, reboot recovery, and Codex research prompt
  - `실험실`: existing Build Start, GraphRAG, Guardrail, and structure demo
    workbench
- Added `docs/CODEX_GOAL_PROMPT_HOMAGE_RESEARCH.md` with a paste-ready Codex
  Desktop goal prompt for indefinite research/monitoring.
- Updated README, PROJECT_STATE, and TASK_BOARD with the deployment/demo versus
  local-development boundary.
- Verified targeted daemon/API tests and Next production build.

## 2026-06-12 - Lab graph growth and greeting surface fix

- Removed the lab graph rolling-window behavior that made new nodes appear to
  replace the lower part of the 3D graph.
- `buildLiveGrowth` now appends all live `live-synapse-*` nodes directly to the
  visible graph for the lab workspace; it no longer creates `live-summary-*`
  nodes or hidden history.
- Updated active-signal fallback so it retargets to recent live nodes and
  traversal nodes, not summary nodes.
- Changed greeting/thanks routing so users no longer see:
  `CONTROL_INTENT kind=greeting retrieval=skipped answer_surface=disabled`.
- Greeting now returns a short native conversation surface while still marking
  `external_llm: false`.
- Verified with local browser: after Build Start the 3D host reached 1,768
  visible nodes with 48 newly appended live nodes and no `live-summary` DOM.
- Verified with local browser that `안녕` returns a Korean greeting sentence and
  no longer exposes `CONTROL_INTENT`.
- Screenshot:
  - `docs/screenshots/131-lab-growth-no-hidden-greeting-fixed.png`

## 2026-06-12 - Lab-first UI cleanup and graph growth validity fix

- Reordered the workspace switcher so `실험실` is first/left and remains the
  deployed default, with `누적학습` as the secondary observer view.
- Converted the `누적학습` workspace into a read-only local/API viewer:
  top-level Build Start and learning-volume controls are hidden there, and the
  old start/resume/checkpoint/stop button row is replaced by an observation
  notice.
- Simplified the lab process panel to the intended three-stage structure:
  `수집`, `학습`, `출력`.
- Added URL workspace selection so `?workspace=daemon` opens the cumulative
  learning viewer directly.
- Investigated the detached graph-cluster issue:
  - live growth previously used an unbounded `0.3 * ring` x-offset, so new
    batches slowly drifted away from the core while still drawing relation
    lines back to anchor nodes
  - large graph rendering also over-weighted a generic spherical spread, which
    could visually separate connected nodes
- Fixed live-synapse placement to grow around existing source anchors and
  adjusted 3D spread weighting so original anchor coordinates are preserved
  more strongly in dense graphs.
- Investigated the suspicious third expansion:
  - the old graph frame sequence was `2 -> 5 -> 9 -> ~72% -> 100%`, so the
    third visible expansion was a display-sample jump, not a valid burst of
    learned structure
  - Build Start frame generation now progresses through smoother
    `12/25/50/75/100%` sample frames in both local FastAPI and deployed
    Next.js fallback.
- Verification:
  - `npm --workspace apps/web run build`
  - `PYTHONPATH=... python -m pytest apps/api packages/knowledge_bakery packages/rag_engine -q`
  - local browser on `http://127.0.0.1:3043` with FastAPI
    `http://127.0.0.1:8042`
  - deployed `https://homage-alpha.vercel.app` verified:
    default `실험실`, three process cards, and read-only `누적학습` viewer
  - screenshots:
    - `docs/screenshots/132-lab-first-three-stage-anchor-growth-local.png`
    - `docs/screenshots/133-daemon-readonly-local-api-viewer.png`

## 2026-06-12 - Truthful learning signal, auto Guardrail, and compact lab UI

- Added real connectivity-learning motion in the 3D GraphRAG scene:
  - active relation lines now draw small orange pulses moving along the edge
  - the pulses are created only for `activeEdgeKeys` that match rendered graph
    edges
  - the 3D host exposes `data-active-edge-count` and `data-edge-pulse-count`
    for browser verification
- Changed the `학습` process action so it compares the previous memory graph
  with the graph returned after `POST /api/memory/build`.
  - if the backend reports more relations and the UI can see newly stored
    edges, the graph shows `학습 연결 확정`
  - if no stored relation changed, the graph shows `학습 완료: 새 연결 변화 없음`
    and no moving edge signal is drawn
- Fixed the local memory graph display cap that made real memory growth look
  stuck:
  - memory nodes now render up to 900 instead of 12
  - memory edges now render up to 1,800 instead of 18
  - local FastAPI verification shows the current memory graph as 152 nodes /
    540 relations instead of the fallback/demo-sized sample
- Folded Guardrail into the `출력` stage:
  - `POST /api/graphrag/query` answers are automatically passed to
    `POST /api/guard/check`
  - the manual Guardrail textarea/button is no longer shown in the chat panel
  - the collapsed chat status summarizes RAG confidence, evidence count, and
    Guard score
- Collapsed the right-side learning/settings/status block behind `설정/상태`
  by default, leaving more vertical room for RAG chat.
- Made header state truthful:
  - lab mode says `준비` unless a build/action/chat generation is actually
    running
  - cumulative viewer uses the daemon's actual worker state instead of the mock
    pipeline state
- Reduced the bottom log into a shorter Korean `시스템 로그` strip.
- Verified in the browser with local FastAPI on `http://127.0.0.1:8042` and a
  fresh Next production server on `http://127.0.0.1:3050`.
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 69 tests
  - `npm --workspace apps/web run build` passed
  - no-change learning run: 152 nodes / 540 relations, active edges 0, pulses 0
  - real new-input learning probe: 152 -> 239 nodes, 540 -> 855 relations,
    active edge keys 18, rendered pulse objects 69
  - after removing the probe document and rebuilding: restored to 152 nodes /
    540 relations, active edges 0, pulses 0
  - chat auto-Guardrail: `GraphRAG가 뭐야?` updated the collapsed status to
    `근거 5 · Guard 65점` without showing the old manual checker
  - cumulative viewer: read-only, no start/build buttons, `stopped · worker not
    alive`, 152 nodes / 540 relations
- Deployed to Vercel production:
  - `https://web-dxspwpa3d-anthony-kims-projects-bc874109.vercel.app`
  - `https://homage-alpha.vercel.app` alias updated successfully
  - production browser verification passed for lab three-stage cards, collapsed
    status, hidden manual Guardrail checker, and read-only cumulative viewer
  - Captured screenshots:
  - `docs/screenshots/134-learning-edge-pulse-actual.png`
  - `docs/screenshots/135-chat-collapsed-auto-guard.png`
  - `docs/screenshots/136-daemon-readonly-viewer.png`
  - `docs/screenshots/137-final-lab-local-3050.png`

## 2026-06-12 - Stable volumetric 3D graph and step-gated lab flow

- Reworked the 3D GraphRAG scene so dense graphs expand in a stable volume:
  node placement now uses id-stable shell coordinates, the camera fits to
  rendered graph bounds, zoom-out limits scale much farther, and graph updates
  no longer snap the camera back toward the initial view.
- Changed the lab flow from one Build Start action into explicit
  `수집 -> 학습 -> 출력` stages:
  - `수집` shows progress to 100% and then unlocks `학습`
  - `학습` shows progress to 100% and then unlocks `출력`
  - `출력` is the RAG/Guardrail path after learning is complete
- Finite `수집` now stops at the actual representative graph returned by the
  API. It no longer starts client-side live-synapse growth after completion, so
  the graph does not pretend to keep learning in the demo flow.
- Fixed greeting/conversation behavior:
  - `안녕` skips web search even when the web-search toggle is on
  - the FastAPI service skips memory activation for conversation-router results
  - the frontend clears stale active-node signals for greeting/conversation
    responses
- Updated the cumulative-learning workspace so it remains a blank read-only
  viewer until local FastAPI and the actual daemon worker are alive.
- Updated `docs/CODEX_GOAL_PROMPT_HOMAGE_RESEARCH.md` to reflect the current
  research loop: local daemon for real cumulative learning, lab as a gated
  experiment surface, no fake visual activity, and direct DB/event-log
  verification.
- Verification:
  - `npm --workspace apps/web run build` passed.
  - targeted API/RAG tests passed: 7 tests.
  - local FastAPI ran on `http://127.0.0.1:8043`.
  - local Next production ran on `http://127.0.0.1:3055`.
  - browser-tested lab link:
    `http://127.0.0.1:3055/?workspace=lab&api=http://127.0.0.1:8043`.
  - browser-tested cumulative viewer link:
    `http://127.0.0.1:3055/?workspace=daemon&api=http://127.0.0.1:8043`.
  - `수집` verification: 653 nodes / 1,295 relations rendered, cameraZ 79.0,
    maxZoom 947.8, active edges 0, pulses 0, no `live-synapse`, no `새 노드 0`.
  - `학습` verification: output stage unlocked after learning completed; no
    relation-change pulse was drawn when no new visible stored relation existed.
  - `안녕` chat verification: clean Korean greeting, no `web-static`,
    Microsoft/Bing evidence, or stale graph signal.
  - daemon viewer verification: graph host absent and waiting text shown because
    local API was connected but `worker not alive`.
- Production deployment:
  - deployed `https://web-5gu3ndmzg-anthony-kims-projects-bc874109.vercel.app`
  - re-aliased `https://homage-alpha.vercel.app` to that deployment
  - production lab verification: first screen is `학습 과정`, shows the three
    process cards, and exposes `수집 시작`
  - production cumulative viewer verification: graph host absent, no `수집 시작`
    button, and the screen says local API is not connected so the graph remains
    blank
  - Captured screenshots:
  - `docs/screenshots/139-stable-volume-sequential-no-live.png`
  - `docs/screenshots/140-greeting-no-web-search.png`
  - `docs/screenshots/141-daemon-blank-until-local-worker.png`
  - `docs/screenshots/142-production-lab-stage-default.png`
  - `docs/screenshots/143-production-daemon-blank-viewer.png`

## 2026-06-12 - Max representative graph volume and adaptive query routing

- Reworked max-profile graph generation in both FastAPI and Next fallback:
  bounded anchor-local volume offsets replaced unbounded ring expansion, and
  same-anchor relation chaining reduced detached side clusters and long
  misleading relation lines.
- Tuned the Three.js 3D renderer:
  - id-stable volumetric placement with normalized source coordinates
  - closer bounds-aware camera fit
  - reset respects the last fit distance
  - oversized camera distances shrink back when the graph bounds permit it
- Fixed local benchmark/stability refresh ordering so local FastAPI hardware
  readings overwrite stale fallback state. Browser verification now shows RAM
  soft `22.4GB` for the local RTX 5080 / 31.1GB RAM machine.
- Changed `관계 계산` so it does not collapse the visible collected
  representative graph back to the smaller persistent memory graph. When memory
  storage is smaller, the lab keeps the `graph_3d` representative sample and
  activates confirmed representative relation edges only after the learning API
  completes.
- Updated the learning card to separate representative graph counts from stored
  memory counts.
- Verification:
  - `npm --workspace apps/web run build` passed.
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 69 tests.
  - `git diff --check` passed.
  - local FastAPI ran on `http://127.0.0.1:8044`.
  - local Next production ran on `http://127.0.0.1:3056`.
  - browser-tested lab link:
    `http://127.0.0.1:3056/?workspace=lab&api=http://127.0.0.1:8044`.
  - Collect replay sampled `12 -> 860 -> 1,720` nodes; final graph was
    `1,720` nodes / `3,421` relations with cameraZ `61.2`.
  - API graph geometry for max target measured radius max `9.804`, z span
    `11.089`, and edge max `8.6`.
  - Learning stayed on `1,720` nodes and showed
    `학습 관계 확인: 대표 그래프 관계 18개를 활성화했습니다.`
  - The learning card showed `1,720 대표 노드`, `3,421 대표 관계`,
    `152 저장 노드`, and `540 저장 관계`.
  - Query API verification through the same Next/FastAPI route used by chat:
    `안녕` -> conversation router / no web provider / 0 docs;
    `오늘 뉴스 알려줘` -> `news-rss` / 5 docs;
    `유재석이 누구야` -> `wikipedia` / 5 docs.
  - The max-profile safety warning is valid on this machine because free disk
    is about `162GB`, below the computed `186.1GB` reserve.
- Production deployment:
  - deployed `https://web-1bwyui7xe-anthony-kims-projects-bc874109.vercel.app`
  - re-aliased `https://homage-alpha.vercel.app` to that deployment
  - production browser verification passed for lab-first default view, fallback
    process cards, visible `수집 시작`, and nonblank 3D graph
  - production API max Build Start returned `500,000` target, `2,000` visual
    budget, and `1,720` nodes / `3,421` relations
  - Captured screenshots:
  - `docs/screenshots/145-lab-volumetric-fit-1720.png`
  - `docs/screenshots/146-learning-keeps-1720-graph.png`
  - `docs/screenshots/147-production-lab-volumetric-default.png`

## 2026-06-12 - Cloud Brain shared ontology design

- Renamed the user-facing `누적학습` workspace to `클라우드 브레인`.
  Internal `/api/learning/daemon/*` endpoints remain compatible for the current
  Alpha worker/state files.
- Added `?workspace=cloud`, `?workspace=cloud-brain`, and `?workspace=cloudbrain`
  as aliases for the Cloud Brain viewer.
- Updated the deployed fallback state copy so Vercel is described as a small
  Cloud Brain viewer, not a long-running worker.
- Added `docs/CLOUD_BRAIN_ARCHITECTURE.md` with the shared/public ontology
  design:
  - local private brain vs Cloud Brain vs lab working memory
  - virtual edge creation from web/Cloud Brain evidence
  - potentiation, consolidation, decay, and pruning lifecycle
  - lazy loading / mmap / hot-window resource strategy
  - lab fallback order: local memory -> fresh web -> Cloud Brain fragments
  - `/api/cloud-brain/*` facade contract
- Added Alpha Cloud Brain API facades in FastAPI and Next.js:
  - `GET /api/cloud-brain/status`
  - `POST /api/cloud-brain/query`
  - `POST /api/cloud-brain/ingest`
  - `POST /api/cloud-brain/consolidate`
  - `POST /api/cloud-brain/prune`
- The facade is intentionally honest: status/query/consolidate use the current
  local daemon and memory activation path, while public ingest/prune return
  dry-run/planned metadata until a real shared graph backend exists.
- Verified FastAPI on `http://127.0.0.1:8045/api/cloud-brain/status` and
  `/api/cloud-brain/query`; an empty local worker returns `0` counts and
  `no_memory` fragments instead of fake graph data.
- Verified the Cloud Brain UI in the in-app browser at
  `http://127.0.0.1:3057/?workspace=cloud-brain&api=http://127.0.0.1:8045`;
  saved `docs/screenshots/149-cloud-brain-local-verified.png`.
- Verified production at `https://homage-alpha.vercel.app/?workspace=cloud-brain`;
  saved `docs/screenshots/150-cloud-brain-production-verified.png`.
- Tightened the deployed `/api/cloud-brain/status` and `/api/cloud-brain/query`
  fallback so Cloud Brain viewer APIs return `0` counts and empty fragments
  until a local worker or shared backend is connected.
- Updated README, Project State, Task Board, Context Capsule, and Codex research
  prompt references to use Cloud Brain terminology.

## 2026-06-12 - Hippocampus continuous learning daemon

- Reviewed DeepKE and ScrapeGraphAI at a technical level:
  - DeepKE informs the separation of entity/relation/attribute extraction.
  - ScrapeGraphAI informs graph-shaped document/web pipeline orchestration.
  - Homage keeps external LLM generation disabled.
- Added `packages/knowledge_bakery/knowledge_bakery/learning_daemon.py`.
- Rewired `knowledge_bakery.__init__` so existing daemon APIs now use the new
  Hippocampus implementation.
- Added raw ingestion:
  - watches `data/raw` for `.txt` and `.md`
  - moves stable files into `data/cleaned`
  - runs `ontology_forge` on the new-file batch
  - refreshes global `data/ontology`
  - rebuilds local GraphRAG memory
- Added synaptic persistence tables in SQLite WAL:
  `synaptic_nodes`, `synaptic_edges`, `ingested_files`, and `learning_events`.
- Added potentiation:
  repeated edge UPSERTs increment `weight` by `0.1` and increment `count`.
- Added decay/pruning:
  `run_synaptic_decay` multiplies weights by a decay factor and deletes weak
  edges plus orphan nodes.
- Added optional Neo4j mirroring using Cypher `MERGE` when `NEO4J_URI` and
  credentials are configured.
- Added `POST /api/learning/daemon/decay` and wired non-dry-run Cloud Brain
  prune to the local decay path.
- Added regression tests proving raw ingestion, potentiation, decay/pruning,
  daemon API status/checkpoint, and Cloud Brain facade behavior.
- Verified locally with FastAPI on `http://127.0.0.1:8047`: started the daemon,
  forced one ingestion tick, moved the two sample raw documents into
  `data/cleaned`, and confirmed `99` synaptic nodes / `279` synaptic edges in
  SQLite WAL.
