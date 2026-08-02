# Project State

## 2026-06-14 ATANOR 0.1.1 Deployment Candidate

Completed:

- Added Adaptive Local-Cloud Ratio Control to `rag_engine.fusion`.
- `/api/graphrag/query` now exposes `fusion_ratio` diagnostics with:
  - `local_weight`
  - `cloud_weight`
  - `local_brain_strength_score`
  - stage/reason
  - bounded Cloud Brain fragment policy
- Private/local-only queries and invalid cloud fragments force `cloud_weight = 0`.
- Low-memory and survival modes clamp Cloud Brain fragment size.
- Weighted RRF now keeps local private memory above cloud context.
- The main BakeBoard UI displays a small Local/Cloud ratio indicator in the RAG status panel.
- Bumped deploy candidate version to `0.1.1` to avoid collision with existing Partner Center `0.1.0.0` package.
- Built final local desktop artifacts:
  - `dist/ATANOR_0.1.1/ATANOR_0.1.1_x64-setup.exe`
  - `dist/ATANOR_0.1.1/ATANOR_0.1.1_x64_en-US.msi`
  - `dist/ATANOR_0.1.1/ATANOR_0.1.1.0_x64.msix`
  - `dist/ATANOR_0.1.1/ATANOR_0.1.1.0_x64.msixupload`
  - `dist/ATANOR_0.1.1/SHA256SUMS.txt`

Verification:

- `python -m py_compile ...` passed for the API/RAG/Knowledge Bakery critical files.
- `python -m pytest apps/api/tests packages/rag_engine/tests packages/model/tests -q` passed with `49 passed`.
- `npm --workspace apps/web run build` passed.
- `npm run desktop:build` completed and produced NSIS/MSI bundles.
- `scripts/build_store_msix.ps1 -SkipDesktopBuild` completed and produced `ATANOR_0.1.1.0_x64.msixupload`.

Deployment note:

- Partner Center package page is reachable for product `9PBN2HNPWQ7V`.
- Existing uploaded package remains `Homage_0.1.0.0_x64.msixupload`.
- Automated upload of the new `.msixupload` is blocked by the current browser automation surface because file input upload is not exposed and the Windows file picker did not attach the file. The old package removal marker was reverted; no destructive save was performed.

## 2026-06-13 ATANOR Rebrand State

The project identity has moved to **ATANOR**: **Architecture for Transparent
Anomy and Networked Ontology in Radical Engines**.

Completed:

- Reframed README and project documentation around ATANOR's Transparent Anomy
  philosophy: local-first, traceable, air-gapped graph inference rather than
  imitation of mainstream black-box LLM systems.
- Added `docs/ATANOR_MANIFESTO.md`.
- Renamed the main PRD and research/goal documents to ATANOR filenames.
- Updated the public-facing Next.js metadata, Tauri product names, package names,
  FastAPI title, local synthesizer identity, GraphRAG method labels, and visible
  `ATANOR RAG` / `ATANOR Oven` labels.
- Preserved core DataGate, Ontology Forge, Ghost Shell, Payload Vault, GraphRAG,
  Knowledge Bakery, and 3D RAG logic.
- Kept selected legacy strings where changing them would break Alpha installs or
  current deployment compatibility: live demo URL, GitHub repository URL,
  SQLite filenames, sidecar binary names, Store package identity, and `HOMAGE_*`
  environment-variable fallbacks.

Verification:

- `npm --workspace apps/web run build` passed.
- `python -m pytest apps/api/tests packages/rag_engine/tests packages/model/tests -q`
  passed with `44 passed`.

## Current Status

ATANOR Alpha is implemented and deployed as an interactive MVP with a
3D Ghost Shell console UI and research-backed Neuro-Efficiency Layer. The
deployment is treated as a small lab / Cloud Brain viewer; real Cloud Brain
learning is run locally through FastAPI and Knowledge Bakery today, with a
future path for governed shared public ontology fragments.

Deployment:

- https://homage-alpha.vercel.app
- Current production deployment:
  https://web-1bwyui7xe-anthony-kims-projects-bc874109.vercel.app

Latest GitHub / Desktop packaging update:

- Public repository: https://github.com/Cozystone/homage1.0
- README now presents the project as `신경망-기호 하이브리드 로컬 AI 엔진
  Homage1.0`, with a screenshot gallery, research thesis, Local Brain / Cloud
  Brain split, three-step Collect -> Learn -> Output flow, quick start, desktop
  build instructions, and suggested repository topics.
- GitHub Actions Desktop Build succeeded on tag `v0.1.0-alpha.6`.
- Produced workflow artifacts:
  - `homage-desktop-windows-latest` (`43,960,906` bytes)
  - `homage-desktop-macos-latest` (`45,757,947` bytes)
- Local Windows Tauri build is still blocked by this machine's Application
  Control Policy (`os error 4551`), so the trusted GitHub hosted runner is the
  current packaging proof.

Latest Cloud-Edge network architecture update:

- Refactored the hybrid network layer into explicit `NetworkConfig`,
  metadata-only signaling providers, and payload transports.
- Server signaling is now optional. If Supabase/AWS-style metadata discovery is
  down, local peer-directory discovery and edge payload transports can still
  run.
- Added `LocalPeerDirectorySignal` so peer discovery can work from
  `data/network/peers.json` without a central server.
- Added a payload transport contract. P2P/libp2p, WebRTC, HTTP signed-fragment
  fallback, or future Rust/Tauri transport can be swapped without changing
  resolver logic.
- Added `EdgeComputeBroker` with `/api/network/edge/status` and
  `/api/network/edge/advertise`. It reports idle edge capacity as metadata only
  and returns `local_only` when server signaling is disabled.
- `/api/network/status` now exposes the Local-First / Cloud-Assisted transition
  state while preserving the legacy `two_track_hybrid_network` field for API
  compatibility.

Latest local verification links:

- Lab: http://127.0.0.1:3056/?workspace=lab&api=http://127.0.0.1:8044
- Cloud Brain viewer: http://127.0.0.1:3056/?workspace=cloud-brain&api=http://127.0.0.1:8044

Latest Cloud Brain design update:

- User-facing `누적학습` terminology has been replaced with `클라우드 브레인`.
  Internal daemon endpoints remain for compatibility, but the product concept
  is now a shared/public ontology brain viewer and local worker surface.
- Added `docs/CLOUD_BRAIN_ARCHITECTURE.md`.
- Cloud Brain is specified as a governed public graph cache, not an external
  LLM. It lends signed node/edge fragments to the lab when local memory and raw
  web search are weak, unavailable, or too noisy.
- The memory lifecycle is defined as virtual edge -> potentiation ->
  consolidation -> decay -> pruning, with local promotion gated by evidence,
  repeated use, Guardrail support, and resource safety.
- Lab integration order is now: local private graph first, fresh web when
  needed, Cloud Brain fragments only as structured fallback, then temporary
  working graph and explicit source labels.
- Added the Alpha `/api/cloud-brain/*` facade on both FastAPI and Next.js:
  status/query/consolidate are wired to the current local worker or memory
  activation path; ingest/prune are explicit dry-run/planned responses until a
  real shared public graph backend exists.
- Verified locally on `http://127.0.0.1:3057/?workspace=cloud-brain&api=http://127.0.0.1:8045`:
  the Cloud Brain viewer opens as a blank observer when the worker is not
  alive, shows `0 노드 / 0 관계`, and no longer shows the old `누적학습`
  label.
- Verification screenshot: `docs/screenshots/149-cloud-brain-local-verified.png`.
- Production verified at `https://homage-alpha.vercel.app/?workspace=cloud-brain`:
  the deployed viewer also keeps an empty graph before local API connection,
  and the `/api/cloud-brain/status` fallback now reports `0` Cloud Brain
  nodes/edges instead of demo memory counts.
- Production screenshot: `docs/screenshots/150-cloud-brain-production-verified.png`.

Latest Hippocampus implementation update:

- Added `packages/knowledge_bakery/knowledge_bakery/learning_daemon.py`.
- The local daemon now watches `data/raw` for `.txt`/`.md`, moves new files into
  `data/cleaned`, runs `ontology_forge` batch extraction, refreshes
  `data/ontology`, rebuilds GraphRAG memory, and persists synaptic state in
  SQLite WAL.
- Repeated edges use UPSERT-style potentiation:
  `weight = weight + 0.1`, `count = count + 1`.
- Added decay/pruning:
  `weight = weight * 0.95`, delete edges below threshold, then delete orphan
  synaptic nodes.
- Added `POST /api/learning/daemon/decay`; Cloud Brain non-dry-run prune now
  calls the same local decay path.
- Neo4j is optional. If `NEO4J_URI` and credentials are set, potentiation and
  decay are mirrored with Cypher `MERGE`; otherwise SQLite remains the active
  local brain.
- Reference influence: DeepKE-style knowledge extraction separation and
  ScrapeGraphAI-style document/web pipeline orchestration, without adopting
  their external LLM dependency.
- Runtime verification on local FastAPI `http://127.0.0.1:8047`: daemon is
  running, `data/raw` sample documents were ingested into `data/cleaned`, and
  SQLite WAL currently reports `99` synaptic nodes / `279` synaptic edges with
  average edge weight `0.589`.

Latest 2026-06-12 follow-up:

- Max-target Collect still treats `500,000` as a long-run storage/training
  budget, not a browser render count. The browser now receives and replays a
  bounded representative graph of `1,720` nodes / `3,421` relations.
- The factory graph generator was changed from unbounded ring placement to
  bounded anchor-local volumetric placement. Local API geometry verification for
  max runs measured radius max `9.804`, z span `11.089`, and edge max `8.6`, so
  the sample is no longer flat or spike-driven.
- The Three.js renderer now uses id-stable volume points, normalized source
  coordinates, bounds-aware camera fit, and a closer reset distance. Browser
  verification showed the final `1,720` graph at cameraZ `61.2` instead of the
  earlier too-distant `109.0`.
- Collect no longer appears as a sudden full graph jump: local browser sampling
  observed staged replay from `12` to `860` to `1,720` visible nodes.
- Local hardware benchmark refresh now wins over stale fallback state after
  FastAPI connects. The lab status shows RAM soft `22.4GB` for this
  31.1GB-RAM / RTX 5080 machine.
- `관계 계산` no longer collapses the visible graph back to the smaller stored
  memory graph. If the stored memory graph is smaller than the collected
  representative graph, the lab keeps the representative graph and lights only
  confirmed representative relations.
- The learning card now separates representative graph counts from persistent
  memory counts: browser verification showed `1,720 대표 노드`,
  `3,421 대표 관계`, `152 저장 노드`, and `540 저장 관계`.
- Query routing was verified through the same Next/FastAPI API path used by the
  UI:
  - `안녕`: `homage-conversation-router-v1`, provider `null`, evidence docs `0`.
  - `오늘 뉴스 알려줘`: `homage-graph-token-web-rag-v1`, provider `news-rss`,
    evidence docs `5`.
  - `유재석이 누구야`: `homage-graph-token-web-rag-v1`, provider `wikipedia`,
    evidence docs `5`.
- Current disk free space is below the max-profile storage reserve, so the lab
  correctly shows a safety warning for `500,000` long-run work rather than
  pretending the workstation can run that target indefinitely without freeing
  storage.
- Browser screenshots:
  - `docs/screenshots/145-lab-volumetric-fit-1720.png`
  - `docs/screenshots/146-learning-keeps-1720-graph.png`
  - `docs/screenshots/147-production-lab-volumetric-default.png`

Latest 2026-06-12 update:

- The lab flow is now gated as three explicit stages: Collect, Learn, Output.
  Collect runs to 100% before Learn is enabled; Learn runs to 100% before the
  Output/RAG path is enabled.
- The 3D graph layout uses stable id-based volumetric placement and bounds-based
  camera fitting. New renders can zoom farther out as graph volume grows, and
  the camera no longer zooms back toward the initial view when the graph source
  changes.
- Finite Collect no longer starts client-side live-synapse growth after the API
  graph is rendered. The graph shows the actual representative anchors returned
  by the build response, with no hidden replacement history.
- Greeting/conversation queries skip web search even when the web-search toggle
  is enabled. They also skip memory activation, so the graph does not pulse
  stale nodes for simple greetings.
- The Cloud Brain workspace is a read-only local worker viewer. If
  local FastAPI is connected but the daemon worker is not alive, the graph area
  stays blank and shows a waiting state instead of reusing the lab demo graph.
- Browser screenshots:
  - `docs/screenshots/139-stable-volume-sequential-no-live.png`
  - `docs/screenshots/140-greeting-no-web-search.png`
  - `docs/screenshots/141-daemon-blank-until-local-worker.png`
  - `docs/screenshots/142-production-lab-stage-default.png`
  - `docs/screenshots/143-production-daemon-blank-viewer.png`

## Completed Alpha Scope

- DataGate API and BakeBoard integration.
- Ontology Forge deterministic concept/edge extraction.
- GraphRAG deterministic hybrid retrieval with chunk ranking, ontology
  expansion, raw graph-token answer text, citations, diagnostics, and
  retrieval trace.
- Guardrail deterministic claim support and overclaim detection.
- GPU/system telemetry with graceful fallback.
- Homage-Core-30M model scaffold and safe training dry-run trace.
- Homage Graph Token Predictor Alpha:
  - sentence/text snippets are decomposed into token transitions,
    co-occurrence edges, active concepts, and ontology paths
  - answer text is a deterministic graph walk over that token/ontology graph,
    not a polished evidence-summary template
  - metadata exposes PMV, active concepts, `answer_kind`,
    `answer_engine.diagnostics`, and `external_llm: false`
  - no external or pretrained LLM calls
- Knowledge Bakery persistent memory Alpha:
  - `packages/knowledge_bakery` writes `data/memory/homage.db` with SQLite WAL
    and `data/memory/events.jsonl` as an append-only memory event log
  - stores documents, chunks, nodes, edges, relation stats, token transitions,
    co-occurrence windows, activation events, local 3D projection rows, and
    query traces
  - builds phrase nodes and action/predicate-aware token nodes from cleaned
    text and Ontology Forge output
  - exposes `POST /api/memory/build`, `GET /api/memory/status`,
    `GET /api/memory/graph`, `POST /api/memory/activate`, and
    `GET /api/memory/drift-check`
  - GraphRAG responses now include `memory_activation` with active nodes,
    active edges, semantic skeleton, and explicit no-LLM policy flags
  - BakeBoard polls drift checks periodically and shows Knowledge Bakery as a
    process card with node, edge, transition, phrase, and drift metrics
  - local browser verification reached a 2,000-node / 4,226-edge 3D graph and
    confirmed active memory signals stay visible by retargeting to visible
    representative nodes when the true activated node is outside the render
    window
  - screenshots:
    - `docs/screenshots/124-knowledge-bakery-drift-local.png`
    - `docs/screenshots/125-large-graph-1912-nodes-local.png`
    - `docs/screenshots/126-large-graph-active-signal-local.png`
- Local Cumulative Learning daemon:
  - `packages/knowledge_bakery/knowledge_bakery/daemon.py`
  - persists `data/memory/daemon_state.json` and
    `data/memory/daemon_checkpoints/*.json`
  - exposes local state as running/stopped/failed/resume_needed without
    pretending that deployment fallback is doing long-lived learning
  - resource guard stops before disk/RAM pressure can destabilize the PC
  - `HOMAGE_AUTOSTART_DAEMON=1` can resume a previously desired-running daemon
    when FastAPI imports the package after reboot
  - FastAPI endpoints:
    - `GET /api/learning/daemon/status`
    - `POST /api/learning/daemon/start`
    - `POST /api/learning/daemon/resume`
    - `POST /api/learning/daemon/checkpoint`
    - `POST /api/learning/daemon/stop`
- BakeBoard workspace split:
  - `실험실` is now the left/first workspace and the deployed default view
  - `클라우드 브레인` shows the long-running local brain worker, runtime,
    checkpoints, resource snapshot, reboot recovery state, and Codex research
    goal prompt
  - deployment fallback renders `클라우드 브레인` as a read-only local/API
    viewer with no start/stop/checkpoint controls
  - `실험실` is simplified to the three intended stages:
    수집(문장 분해 및 GraphRAG 구축), 학습(온톨로지 생성 및 관계 계산),
    출력(자연어 입력/답변)
- Lab UI truthfulness and density cleanup:
  - right-side learning volume / local FastAPI / metric details are collapsed
    behind `설정/상태` by default so chat has more space
  - the bottom dashboard is now a shorter Korean `시스템 로그`
  - lab header status shows `준비` unless a build/action/chat generation is
    actually running
  - Cloud Brain viewer status uses the real local daemon worker state instead of
    the mock pipeline status
- Truthful 3D learning-edge signal:
  - the `학습` action compares the previous memory graph with the graph returned
    after `POST /api/memory/build`
  - moving orange edge pulses are drawn only when new stored relations are
    detected and those edges are present in the rendered graph
  - no-change learning runs show `학습 완료: 새 연결 변화 없음` and keep active
    edge/pulse counts at zero
  - the 3D host exposes active-edge and edge-pulse debug attributes for browser
    verification
- Output-stage Guardrail integration:
  - RAG answers are automatically passed through `POST /api/guard/check`
  - the old manual chat Guardrail checker is hidden
  - chat status summarizes RAG confidence, evidence count, and Guard score
- Memory graph display fix:
  - memory nodes now render up to 900 and edges up to 1,800
  - local FastAPI memory graph now displays the actual current 152-node /
    540-relation graph instead of looking capped at the demo-sized sample
- Added `docs/CODEX_GOAL_PROMPT_HOMAGE_RESEARCH.md` with the paste-ready Codex
  Desktop goal prompt and reboot protocol.
- Neuro-Efficiency Layer for event sparsity, modular routing, continual
  learning policy, few-shot prototypes, self-supervised masking, compression,
  and estimated compute reduction.
- Sustained Learning Stability Profile:
  - `GET/POST /api/neuro/stability`
  - target hardware envelope for Ryzen 9 9950X3D, RTX 5080 16GB, 32GB RAM, 1TB SSD
  - RAM/VRAM/storage watermarks, queue caps, graph hot-window policy,
    checkpoint cadence, and backpressure rules
  - BakeBoard `지속 운전 안전장치` stage with selectable learning-volume targets
- Hardware Benchmark Adaptation:
  - `GET/POST /api/neuro/benchmark`
  - startup CPU/RAM/GPU/disk probing when local FastAPI is connected
  - automatic `lite` / `standard` / `deep` / `max` learning-volume recommendation
  - ontology batch, graph hot-window, UI render, precision, microbatch, and
    checkpoint tuning payloads
  - BakeBoard `시스템 벤치마크` stage and `벤치마크 재측정` button
- Local FastAPI companion connector:
  - local BakeBoard can connect from the browser to the viewer's own
    `http://127.0.0.1:8000` FastAPI backend
  - CORS and Private Network Access headers are enabled for localhost,
    `127.0.0.1`, and Vercel preview/production origins
  - connected clients use local telemetry, benchmark, stability, and
    `POST /api/factory/build/start` instead of deployment-sandbox fallbacks
  - production BakeBoard exposes the same connector, but browser security can
    block `https://homage-alpha.vercel.app` from calling an `http://localhost`
    backend unless an HTTPS local companion is configured
- Build Start target/sample clarification:
  - `target_nodes` is now labeled as a long-run storage/training budget
  - `graph_3d` is explicitly labeled as a bounded representative browser sample
  - standard `10,000` target runs now use a `480` node render window with
    about `413` API anchor nodes, so they can grow beyond the old `210` node /
    `427` relation visual ceiling
  - max runs accept a `500,000` node long-run target with a `2,000` node
    representative anchor budget; lab live-synapse nodes are appended visibly
    instead of being folded into hidden history
  - infinite runs now use `target_nodes: null` / `unbounded_continuous_goal`;
    the UI shows `∞` instead of a hidden 500,000-node cap and keeps new
    live-synapse nodes visible as they are added
  - graph frame growth now uses smoother 12/25/50/75/100% style progression
    instead of jumping from 9 nodes to about 72% of the sample on the third
    expansion
  - live-synapse placement now grows around existing source anchors instead of
    drifting by an unbounded ring offset, reducing detached side clusters and
    long misleading relation lines
  - local verification screenshots:
    - `docs/screenshots/132-lab-first-three-stage-anchor-growth-local.png`
    - `docs/screenshots/133-daemon-readonly-local-api-viewer.png`
  - local browser verification screenshot:
    `docs/screenshots/121-500k-max-render-cap-local.png`
- Sentence-element ontology extraction:
  - Ontology Forge now extracts sentence tokens, `verb` action nodes, `phrase`
    nodes, and measured `precedes`, `forms_phrase`, `co_occurs`, `does`, and
    `acts_on` relations instead of only noun-like concept/keyword nodes.
  - BakeBoard legend and live growth templates include `행위`, `구`, and `관계`
    node types.
- Research no-evidence behavior:
  - unknown questions such as `김안석이 누구야` now return `NO_EVIDENCE`
    diagnostics instead of a clean rule-based sentence.
  - Korean topic tokens trim simple particles for graph seeds, but weak graphs
    are allowed to expose weak output instead of hiding it.
- Active neuron-like signal fallback:
  - if matched node ids roll out of the 3D render window during sustained
    growth, the signal retargets visible live frontier / summary / traversal
    nodes so orange activation remains visible.
- Web Search / Grounding connector layer:
  - `GET/POST /api/harvest/web-search` added for provider status and search
    result ingestion.
  - Build Start accepts `web_search`, `search_query`, and
    `web_search_provider`, then folds web result URLs into Harvest docs.
  - RAG query accepts `web_search`; when local graph evidence is weak, Homage
    reads raw search snippets as graph-token training samples and still reports
    `external_llm: false`.
  - Raw-result provider hooks: `static`, `brave`, `serper`, and `tavily`.
  - Microsoft Grounding with Bing is exposed as a metadata/status connector for
    future Foundry-agent mode because it returns agent/model responses rather
    than raw evidence chunks for the native Homage path.
  - Web search connector note: `docs/WEB_SEARCH_CONNECTORS.md`.
- Native RAG open-structure generation:
  - structure/self-description questions such as `네 구조 설명해봐` generate a
    native answer even when no direct document evidence is retrieved
  - internal architecture context is used for synthesis but not returned as
    document evidence
  - active-signal UI now shows pulsing active nodes instead of a path-like
    signal trace
- MiroFish-inspired BakeBoard console:
  - top graph/split/workbench layout switcher
  - left ontology-memory graph visualization
  - right learning process or RAG chat workbench
  - bottom system dashboard log
- Next.js API fallback layer so deployed BakeBoard works without local FastAPI.
- Research note: `docs/RESEARCH_NEURO_EFFICIENCY.md`.
- UI reference note: `docs/UI_REFERENCE_MIROFISH.md`.
- RAG reference note: `docs/RAG_REFERENCE.md`.
- PRD engine audit: `docs/PRD_ENGINE_AUDIT.md`.
- Build Start Alpha flow:
  - `POST /api/factory/build/start`
  - allowlisted web reference harvest
  - typed ontology/RAG graph frames
  - Three.js 3D GraphRAG traversal visualization
  - Alpha training gate before Homage Oven dry-run handoff
  - evidence snippets carried into the RAG chat workbench
  - continuous live-synapse growth pulses after Build Start
- Build flow note: `docs/BUILD_FLOW_3D_RAG.md`.
- Long-run stability note: `docs/LONG_RUN_STABILITY_PLAN.md`.
- Hardware benchmark note: `docs/HARDWARE_BENCHMARK_ADAPTATION.md`.
- Independent native model revision note:
  `docs/HOMAGE_INDEPENDENT_MODEL_REVISION_V1.md`

## Verification

- Latest volumetric graph / staged learning / adaptive web routing verification:
  - `npm --workspace apps/web run build` passed.
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 69 tests.
  - local FastAPI `http://127.0.0.1:8044` and local Next production server
    `http://127.0.0.1:3056` returned HTTP 200 and were browser-tested.
  - max Collect replay showed `12 -> 860 -> 1,720` visible nodes; final graph
    was `1,720` nodes / `3,421` relations, cameraZ `61.2`, maxZoom `733.8`.
  - local API geometry check for max representative graph: radius max `9.804`,
    z span `11.089`, edge max `8.6`.
  - local benchmark/stability refresh showed RTX 5080, 31.1GB RAM, 32 CPU
    threads, `max` recommendation, and RAM soft `22.4GB`.
  - max run safety warning is expected on this machine because free disk
    `~162GB` is below the max-profile reserve `186.1GB`.
  - learning stage kept the `1,720` representative graph visible and activated
    `18` confirmed representative relation edges instead of collapsing to the
    smaller `152`-node stored memory graph.
  - learning card now displays both representative graph and stored-memory
    counts: `1,720 대표 노드`, `3,421 대표 관계`, `152 저장 노드`,
    `540 저장 관계`.
  - query API verification:
    - `안녕`: conversation router, no web provider, `0` evidence docs.
    - `오늘 뉴스 알려줘`: web graph-token predictor, `news-rss`, `5` evidence docs.
    - `유재석이 누구야`: web graph-token predictor, `wikipedia`, `5` evidence docs.
  - production deploy succeeded:
    `https://web-1bwyui7xe-anthony-kims-projects-bc874109.vercel.app`
  - `https://homage-alpha.vercel.app` now points to that deployment.
  - production browser verification passed for lab-first default view, fallback
    process cards, visible `수집 시작`, and nonblank 3D graph.
  - production API verification for max Build Start returned `500,000` target,
    `2,000` visual budget, and `1,720` nodes / `3,421` relations.
  - screenshots:
    - `docs/screenshots/145-lab-volumetric-fit-1720.png`
    - `docs/screenshots/146-learning-keeps-1720-graph.png`
    - `docs/screenshots/147-production-lab-volumetric-default.png`
- Latest truthful learning-signal / compact UI verification:
  - `npm --workspace apps/web run build` passed.
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 69 tests.
  - local FastAPI `http://127.0.0.1:8042` and local Next production server
    `http://127.0.0.1:3050` were browser-tested directly.
  - no-change `관계 계산` run: 152 nodes / 540 relations, active edges 0,
    edge pulses 0, and `학습 완료: 새 연결 변화 없음`.
  - temporary new-input probe run: 152 -> 239 nodes, 540 -> 855 relations,
    active edge keys 18, rendered pulse objects 69, and
    `학습 연결 확정`.
  - after deleting the probe and rebuilding, local memory restored to 152 nodes
    / 540 relations with active edges 0 and pulses 0.
  - `RAG 채팅` auto-ran Guardrail; `GraphRAG가 뭐야?` updated collapsed status
    to `근거 5 · Guard 65점` with no manual checker visible.
  - `?workspace=daemon&api=http://127.0.0.1:8042` is read-only, shows no
    start/build controls, and reports `stopped · worker not alive`.
  - production deploy succeeded:
    `https://web-dxspwpa3d-anthony-kims-projects-bc874109.vercel.app`
  - `https://homage-alpha.vercel.app` now points to that deployment and was
    browser-verified for three lab process cards, no manual Guardrail checker,
    and read-only cumulative viewer state.
  - screenshots:
    - `docs/screenshots/134-learning-edge-pulse-actual.png`
    - `docs/screenshots/135-chat-collapsed-auto-guard.png`
    - `docs/screenshots/136-daemon-readonly-viewer.png`
    - `docs/screenshots/137-final-lab-local-3050.png`
- Latest UI cleanup/local viewer verification:
  - `npm --workspace apps/web run build` passed.
  - `PYTHONPATH=... python -m pytest apps/api packages/knowledge_bakery packages/rag_engine -q`
    passed: 23 tests.
  - local FastAPI on `http://127.0.0.1:8042` and Next production server on
    `http://127.0.0.1:3043` verified:
    `실험실` first/default, `단계 3`, process cards `수집/학습/출력`,
    `?workspace=daemon&api=http://127.0.0.1:8042` opens the read-only
    cumulative viewer, no daemon controls are exposed, `관계 계산` succeeds,
    and `질문 보내기` switches to RAG chat without an error banner.
  - production deploy succeeded:
    `https://web-lvgtobjb6-anthony-kims-projects-bc874109.vercel.app`
  - `https://homage-alpha.vercel.app` now points to that deployment and was
    browser-verified for lab default, three process cards, and read-only
    cumulative viewer.
- Python editable package install passed for all Alpha packages including
  `packages/neuro_efficiency`.
- `pytest packages/datagate packages/ontology_forge packages/rag_engine packages/guard packages/model packages/trainer packages/neuro_efficiency apps/api -q` passed: 49 tests.
- Python compile check passed for backend and packages.
- `npm --workspace apps/web run build` passed.
- Latest graph-token predictor verification:
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 64 tests.
  - `npm --workspace apps/web run build` passed.
  - local FastAPI direct smoke on `http://127.0.0.1:8010/api/graphrag/query`
    returned `homage-graph-token-rag-v1`, `answer_kind:
    graph_token_prediction`, `prediction_basis:
    ontology_token_transition_graph`, `graph_path_count: 3`, and
    `external_llm: false`.
  - local Next production server on `http://127.0.0.1:3030` rendered the RAG
    chat workbench; a browser query for `유재석이 누구야` showed `생성 방식
    graph_token_prediction`, `웹 검색 wikipedia`, evidence cards, and raw
    graph-walk text rather than a polished template answer.
  - production deploy succeeded:
    `https://web-es9v4o6xc-anthony-kims-projects-bc874109.vercel.app`
  - `https://homage-alpha.vercel.app` now points to that deployment.
  - production API smoke returned `homage-graph-token-web-rag-v1`,
    `answer_kind: graph_token_prediction`, provider `wikipedia`,
    `prediction_basis: ontology_token_transition_graph`, and `external_llm:
    false`.
  - screenshot:
    - `docs/screenshots/123-graph-token-predictor-ui-local.png`
- Latest local verification for the unbounded/no-node/sentence-element update:
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 63 tests.
  - `npm --workspace apps/web run build` passed.
  - `POST /api/factory/build/start` with `learning_volume: infinite` returned
    `target_nodes: null`, `target_semantics: unbounded_continuous_goal`,
    `continuous: true`, `visual_node_budget: 2000`, and `chunk_count: 4096`.
  - local browser verification on `http://localhost:3010` passed for `∞`
    selection, unbounded Build Start growth, Korean no-node RAG answer, and
    visible orange active-node signal over rolling 3D graph growth.
  - screenshot:
    - `docs/screenshots/122-infinite-no-node-signal-local.png`
- Web Search / Grounding connector verification:
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 64 tests.
  - `npm --workspace apps/web run build` passed with `/api/harvest/web-search`
    included in the Next route manifest.
  - `POST /api/harvest/web-search` returned static provider results, provider
    status, and Bing display query URL.
  - `POST /api/graphrag/query` with `web_search: true` returned
    `homage-graph-token-web-rag-v1`, search evidence docs, citations,
    `web_search` metadata, graph-token diagnostics, and `external_llm: false`.
  - Fresh/current/news queries now auto-enable web search. Local smoke for a
    Korean "today news" query returned `homage-graph-token-web-rag-v1`,
    provider `news-rss`, 5 evidence docs, `external_llm: false`, and no
    `raw_no_node::` marker.
  - Person/knowledge lookup queries now auto-enable web search. Local smoke for
    a Korean celebrity lookup returned provider `wikipedia`, not `static`,
    removed provider-count template text from the answer, kept
    `external_llm: false`, and returned no `raw_no_node::` marker.
  - Production smoke on `https://homage-alpha.vercel.app/api/graphrag/query`
    for the same fresh-news query returned status 200, provider `news-rss`, 5
    evidence docs, `external_llm: false`, and no `raw_no_node::` marker.
  - Production smoke for the Korean celebrity lookup returned status 200,
    provider `wikipedia`, 5 evidence docs, no provider-count template text,
    `external_llm: false`, and no `raw_no_node::` marker.
  - `POST /api/factory/build/start` with `web_search: true` folded search
    results into `harvest_docs` with `search_provider`, `search_query`, and
    `bing_query_url` metadata.
  - local browser verification confirmed the BakeBoard web-search toggle is
    visible and enabled by default.
- MiroFish repo and live demo were inspected; code was not copied because the
  source license is AGPL-3.0.
- Local API smoke passed:
  - DataGate completed on sample raw docs.
  - Ontology Forge created 11 nodes and 4 edges.
  - GraphRAG returned synthesized answer text, citations, evidence, trace, and
    confidence.
  - Guardrail returned claim support and guard score.
  - GPU telemetry returned real data or fallback.
  - Homage Oven dry-run returned loss trace and checkpoint manifest.
  - `/api/neuro/plan` returned the Homage Neuro-Efficiency Layer plan.
  - `/api/pipeline/status` returned 7 stages.
- Local browser verification passed for the split console UI, ontology memory
  graph, layout switcher, RAG chat, synthesized answer, and retrieval-signal
  evidence cards.
- Local browser verification also passed for graph search, zoom in/out,
  directional pan, pointer drag pan, graph reset, graph/split/workbench layout
  modes, process action buttons, RAG send, Guardrail check, Refresh, and header
  reset.
- Vercel production deploy succeeded.
- `homage.vercel.app` was already in use; production is aliased to
  `https://homage-alpha.vercel.app`.
- Deployed browser verification passed for the split console UI, ontology
  memory graph, layout switcher, RAG chat, evidence-backed response, and
  `/api/neuro/plan`.
- Latest deployed alias verification passed for graph search/zoom and
  auto-scrolled RAG answer evidence rendering.
- Local browser verification passed for `Build 시작`, reference harvest
  reporting, staged 3D GraphRAG growth, drag rotation, wheel zoom, nonblank
  canvas screenshot inspection, training-gate display, and RAG evidence cards.
- `POST /api/factory/build/start` is included in the Next.js production build.
- Latest Vercel production deploy succeeded and `https://homage-alpha.vercel.app`
  now points to the Build Start / 3D GraphRAG version.
- Deployed browser verification passed for `Build 시작`, 3D GraphRAG canvas
  rendering, drag/zoom interaction, training-gate display, and RAG evidence
  cards.
- Compact console verification passed:
  - split layout is now 70/30, measured as 1008px / 432px at 1440px width
  - UI density was reduced across header, graph controls, process cards, chat,
    and system log
  - Build Start continues adding live-synapse nodes after the initial graph
    frames
  - Learning Process buttons show running state, update their cards directly,
    and were verified locally and on the deployed alias
  - Latest production deploy is aliased to `https://homage-alpha.vercel.app`
- Homage Graph Token Predictor verification passed:
  - local API and browser answered GraphRAG questions with
    `homage-graph-token-rag-v1`
  - color legend questions route to `homage-graph-legend-v1` with no evidence
    card fallback
  - answer metadata includes PMV, active concepts, answer kind, graph-token
    diagnostics, predictor stages, and `external_llm: false`
  - production API at `https://homage-alpha.vercel.app` returned the same
    graph-token predictor metadata after redeploy
- Sustained Learning Stability verification passed:
  - `python -m compileall packages\neuro_efficiency apps\api\app` passed
  - `python -m pytest packages\neuro_efficiency apps\api -q` passed: 11 tests
  - full Alpha Python suite passed with explicit `PYTHONPATH`: 55 tests
  - `npm --workspace apps/web run build` passed
  - local browser verification passed for the `지속 운전 안전장치` process card,
    learning-volume `최대` selection, `안정성 계산` button, and persistence after
    the 10-second auto-refresh interval
  - production deploy succeeded and `https://homage-alpha.vercel.app` now
    points to the sustained stability version
  - production API verification passed for `GET/POST /api/neuro/stability`
  - production browser verification passed for the `최대` stability profile card
  - screenshots:
    - `docs/screenshots/88-sustained-stability-local.png`
    - `docs/screenshots/89-sustained-stability-max-local.png`
    - `docs/screenshots/90-sustained-stability-final-local.png`
    - `docs/screenshots/91-sustained-stability-production.png`
    - `docs/screenshots/92-sustained-stability-production-card.png`
    - `docs/screenshots/93-sustained-stability-production-card-visible.png`
- Hardware Benchmark Adaptation verification passed:
  - actual local benchmark read this machine as `Performance desktop`
  - measured local API recommended `max`
  - local API returned RTX 5080, about 15.9GB VRAM, about 31.1GB RAM, 32 CPU threads
  - local browser verification passed with FastAPI on `127.0.0.1:8002` and
    Next production server on `127.0.0.1:3025`
  - BakeBoard automatically selected `최대` and showed 768 chunks / 420k chars
    for Build Start
  - `벤치마크 재측정` completed from the UI
  - production API verification passed for `GET /api/neuro/benchmark` with
    `source: server-fallback` and `can_read_local_hardware: false`
  - production browser verification passed for fallback benchmark labeling
  - screenshot:
    - `docs/screenshots/94-hardware-benchmark-local.png`
    - `docs/screenshots/95-hardware-benchmark-production.png`
- Graph-token RAG open-structure verification passed:
  - `네 구조 설명해봐` now returns a generated Homage architecture answer
  - no direct-evidence fallback text is shown
  - internal architecture context is exposed as internal training samples for
    graph-token prediction rather than hidden polished prose
  - signal overlay changed from `신호 경로` to `활성 노드`
  - local browser verification showed nodes pulsing orange without path text
  - production API at `https://homage-alpha.vercel.app/api/graphrag/query`
    returns `homage-graph-token-rag-v1`, `external_llm: false`,
    internal training samples, and no direct-evidence fallback copy for the
    same structure question
  - production browser verification passed for generated structure answers,
    70/30 split layout, and orange active-node pulses without path wording
  - screenshots:
    - `docs/screenshots/96-structure-answer-active-nodes-local.png`
    - `docs/screenshots/97-active-node-pulses-local.png`
    - `docs/screenshots/98-structure-answer-no-path-local.png`
    - `docs/screenshots/99-active-node-pulses-no-path-local.png`
    - `docs/screenshots/100-structure-answer-production.png`
    - `docs/screenshots/101-active-node-pulses-production.png`
- RAG no-evidence and custom learning target verification passed:
  - `GraphRAG가 뭐야` no longer prints `읽힌 경로`; answer text uses active
    node signal wording instead
  - external unknown questions such as `유재석이 누구야` no longer leak the
    Homage architecture explanation
  - no-evidence answers state that the current memory has no verified document
    evidence and that external LLM/general-knowledge guessing is disabled
  - learning-volume controls now include a direct target-node input
  - `target_nodes` flows into `/api/neuro/stability` and
    `/api/factory/build/start`
  - Build Start scales chunk budget, text budget, and representative 3D graph
    budget from the selected target-node count
  - 3D graph rendering now applies deterministic spread layout, short
    collision relaxation, label thinning, and camera distance scaling
  - local browser verification passed for `1,200` target nodes, no-evidence
    RAG chat, and large graph rendering
  - production deploy succeeded and `https://homage-alpha.vercel.app` now
    points to the no-evidence/custom-target build
  - production API verification passed for no-evidence RAG and
    `target_nodes: 50000` Build Start scaling
  - production browser verification confirmed the new `목표 노드` input is
    visible; in-app browser text entry was blocked by its virtual clipboard
    extension, so production interaction was verified through API plus visible
    UI capture
  - stress DOM verification reached `358/360` representative nodes and
    `358 nodes / 739 relations`; WebGL full screenshot capture timed out at
    that size, so saved screenshots cover the 48, 73, 221, and 257 node
    visual states
  - screenshots:
    - `docs/screenshots/102-custom-node-target-local.png`
    - `docs/screenshots/103-rag-no-evidence-local.png`
    - `docs/screenshots/104-large-graph-spacing-local.png`
    - `docs/screenshots/105-large-graph-final-local.png`
    - `docs/screenshots/108-production-node-target-visible.png`
- Infinite learning mode verification passed:
  - learning-volume controls now include an `∞` preset
  - `∞` mode sets the target to 250,000 ontology nodes, 2,000 scheduled chunks,
    continuous text budget, and a 600-node representative 3D render window
  - `POST /api/factory/build/start` returns `alpha-continuous-harvest`,
    `training_gate.continuous: true`, and keeps Harvest/Ontology Forge marked
    as running for continuous builds
  - local browser verification passed for selecting `∞`, starting continuous
    learning, showing cumulative elapsed learning time, growing candidate nodes,
    capping the visible 3D graph at `600/600` representative nodes, and stopping
    the loop with the `학습 중지` button
  - local DOM verification reached `942` accumulated candidate nodes while the
    visible 3D graph stayed capped at 600 representative nodes
  - production API verification passed at `https://homage-alpha.vercel.app`
    with `alpha-continuous-harvest`, 2,000 chunks, and a 600-node visual budget
  - production browser verification passed for `∞` selection, Build Start,
    cumulative elapsed time, candidate-node growth, and stop control
  - current Alpha learning is not random sentence learning: accepted/reference
    text is chunked, concept candidates are extracted deterministically, typed
    relations are generated, and the live-synapse UI simulates continual
    ontology growth until persistent graph events are implemented
  - screenshots:
    - `docs/screenshots/109-infinite-learning-selected-local.png`
    - `docs/screenshots/110-infinite-learning-running-local.png`
    - `docs/screenshots/111-infinite-learning-stopped-local.png`
    - `docs/screenshots/112-infinite-learning-production.png`
- Reality boundary, adaptive zoom, and safety-stop verification passed:
  - FastAPI system telemetry now returns `source: local-fastapi`, RAM total,
    RAM used, disk free, and disk used values; Next fallback marks itself as
    `deployment-sandbox` or `local-next`
  - local API measured this machine as 32 CPU threads, about 31.1GB RAM,
    RTX 5080 with about 15.9GB VRAM, about 165.5GB free disk, and recommended
    `max`
  - with the actual hardware profile applied to a 250,000-node workload,
    storage reserve recalculated to about 186.1GB and UI render budget stayed
    at 600 representative nodes
  - local browser verification correctly blocked infinite learning preflight
    because live RAM usage crossed the soft watermark; the UI showed the reason
    instead of silently starting a risky run
  - the 3D graph now reports preserved API anchor nodes, visible newly generated
    `live-synapse-*` nodes, summarized history nodes, and the latest new node id
  - responsive 3D zoom-out no longer has the old fixed `34` camera-distance
    ceiling; local browser verification reached camera distance `187.4` with a
    dynamic max of `198.9` for a 358-node graph
  - production browser verification showed `deployment-sandbox` labeling,
    preserved anchors, visible new live nodes, summarized history, and zoom-out
    camera distance `134.7` on a 600-node render window
  - screenshots:
    - `docs/screenshots/113-local-safety-preflight-block.png`
    - `docs/screenshots/114-local-anchor-new-node-trace.png`
    - `docs/screenshots/115-responsive-zoom-out-local.png`
    - `docs/screenshots/116-production-live-summary-zoom.png`
- Local FastAPI companion / representative-sample verification passed:
  - local FastAPI `POST /api/factory/build/start` mirrors the Next fallback
    Build Start contract
  - standard `10,000` target returns `visual_node_budget: 210`,
    `representative_node_count: 181`, and `target_realized: false`
  - local browser verification connected BakeBoard to `http://127.0.0.1:8000`
    from a separate Next production server
  - fixed the local connector so GET requests no longer force unnecessary CORS
    preflights with `Content-Type: application/json`
  - re-verified with fresh FastAPI on `127.0.0.1:8003` and Next production
    server on `127.0.0.1:3032`; FastAPI logs confirmed browser
    `OPTIONS/POST /api/factory/build/start` returned 200
  - the UI now shows `10,000` as the long-run target, `210/210` as the
    representative render sample, `181` as API anchors, and explains that the
    visible cap is not the completed long-run ontology
  - screenshot:
    - `docs/screenshots/117-local-fastapi-standard-sample-explained.png`
    - `docs/screenshots/118-local-fastapi-connected-render-cap-fixed.png`
    - `docs/screenshots/119-local-fastapi-target-sample-explanation.png`
    - `docs/screenshots/120-production-local-http-boundary-message.png`

## Known Limitations

- Alpha does not use external or pretrained LLMs. The new Homage Utterance
  Engine is a native Alpha generator around GraphRAG context bundles, while
  Homage-Core remains a shape/training scaffold rather than a trained decoder
  that can freely sample language.
- Build Start is an Alpha orchestrator. It fetches a small allowlisted reference
  set and uses curated reference snippets for the UI/training-gate trace; it is
  not broad autonomous crawling or real model training yet.
- Deployed Vercel app uses deterministic demo fallback API routes.
- Local FastAPI run state is in-memory and single-process.
- DataGate is full-batch overwrite only.
- Ontology extraction is regex/rule-based and intentionally simple.
- Homage Oven dry-run is a scaffold, not production training.
- Neuro-Efficiency values are deterministic estimates until real event traces,
  model update logs, and hardware profiles are persisted.
- The ontology-memory graph is a deterministic UI visualization, not a full
  force-directed runtime graph engine yet, but it now supports zoom, pan,
  drag, search focus, node detail, reset, and full-screen graph mode.
- PRD audit confirms Alpha is not yet the full final engine: broad Harvest
  crawling, stronger local vector learning, summary-tree compaction, real
  Homage-Core from-scratch training, and a separate native decoder remain
  future work.
- The 3D GraphRAG visual is a live client-side visualization of the Alpha
  graph/traversal contract; persistent vector storage, graph mutation history,
  and real continual-training events remain future work.
- Live-synapse growth is currently a deterministic client-side Alpha simulation
  of continual learning. It visually proves the growth loop, but persistent
  graph mutation storage and real training updates are still next milestones.
- `∞` learning mode runs continuously in the browser until stopped and keeps the
  3D render bounded with a rolling representative window. It does not yet run a
  durable background crawler or persist every graph mutation across refreshes.
- The UI now labels that boundary: harvested/API anchor graphs are real Alpha
  API output, while `live-synapse-*` nodes are client-side growth events until
  the append-only ontology event log exists.
- When real local telemetry is available, infinite learning can be preflight
  blocked or auto-stopped on RAM, VRAM, or disk reserve pressure.
- Sustained stability is currently an enforceable planning/API/UI layer. The
  live ontology store still needs to move from JSON snapshots to append-only
  graph events plus a SQLite WAL hot index before very long unattended runs.
- Hardware benchmark auto-apply requires the local FastAPI backend. The Vercel
  fallback route cannot read the viewer's actual PC and marks itself as
  `can_read_local_hardware: false`.
- Local BakeBoard can use real viewer hardware after the user starts local
  FastAPI and connects it through the UI. Deployed BakeBoard remains in
  deterministic fallback mode in browsers that block HTTPS pages from calling
  HTTP loopback APIs.
- Standard/deep/max Build Start modes now accumulate live growth toward the
  long-run `target_nodes` budget and can target `500,000` nodes, but the
  durable realization of every mutation across refreshes still requires the
  planned append-only ontology event log and SQLite hot graph index.
- External facts that are not present in memory are not guessed. The Alpha
  native engine returns a no-evidence answer and asks for Harvest/Build Start
  input instead.
- npm audit still reports dependency advisories; no force fix applied.

## Next Recommended Milestone

1. Route Build Start and live-synapse growth into the Knowledge Bakery event
   log instead of keeping those growth pulses client-side.
2. Persist Alpha run history and Build Start graph frames with SQLite.
3. Persist live-synapse graph mutations and replay them as a real learning
   event stream.
4. Add a real Harvest connector with source allowlists, robots policy, and
   deduped document provenance.
5. Replace the deterministic local projection with PPMI/random-indexing or
   graph-walk vectors trained only on the local memory event log.
6. Add the first native decoder endpoint with unsupported-token diagnostics.

## Distribution Update - Windows/macOS Public Release Tracks

- Windows public distribution should move to Microsoft Store MSIX as the
  primary route so Microsoft can re-sign the package and reduce SmartScreen /
  Smart App Control friction for first-time users.
- Windows EXE/MSI remains useful for local development and power-user testing,
  but the current self-signed certificate tooling is explicitly dev-only.
- macOS distribution is now planned as two parallel tracks:
  - Developer ID signed + notarized DMG for the full local-first Homage desktop
    runtime, including the FastAPI sidecar, local networking, file watching, and
    Payload Vault behavior.
  - Mac App Store candidate packaging for a future sandboxed consumer-facing
    build, likely with reduced operator capabilities or user-selected file
    access.
- Added macOS Tauri distribution configs:
  - `src-tauri/tauri.macos.conf.json`
  - `src-tauri/tauri.appstore.conf.json`
  - `src-tauri/Entitlements.plist`
  - `src-tauri/Entitlements.appstore.plist`
  - `src-tauri/Info.macos.plist`
  - `src-tauri/Info.appstore.plist`
- Added macOS release helpers:
  - `scripts/macos/preflight.sh`
  - `scripts/macos/verify_bundle.sh`
  - `scripts/macos/package_appstore_pkg.sh`
  - `.github/workflows/macos-distribution.yml`
- Added `docs/DESKTOP_DISTRIBUTION_STRATEGY.md` to explain the public trust
  model across Windows, macOS, and Linux.

## Windows Store MSIX Update - 2026-06-13

- Reserved Microsoft Partner Center product name `Homage`.
- Store product ID: `9PBN2HNPWQ7V`.
- Captured Store package identity:
  - `Package/Identity/Name`: `AnseokKim.Homage`
  - `Package/Identity/Publisher`: `CN=BAE07AF0-E1EB-4107-96CD-CACBEBF82C23`
  - `PublisherDisplayName`: `Anseok Kim`
  - `PFN`: `AnseokKim.Homage_ram6gtk9ph338`
- Added Store MSIX packaging inputs:
  - `packaging/windows-msix/store-identity.json`
  - `packaging/windows-msix/AppxManifest.xml.template`
  - `scripts/build_store_msix.ps1`
  - package script `npm run store:msix`
- Generated current Store upload artifacts:
  - `dist-artifacts/windows-store/Homage_0.1.0.0_x64.msix`
  - `dist-artifacts/windows-store/Homage_0.1.0.0_x64.msixupload`
- Known submission risk: Homage is a packaged Win32/Tauri desktop app and
  declares `runFullTrust`; Partner Center may require restricted capability
  approval during package validation.
