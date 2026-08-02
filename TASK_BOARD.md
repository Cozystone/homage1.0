# Task Board

## Done

- [x] Repo skeleton and shared docs.
- [x] FastAPI backend and Next.js BakeBoard.
- [x] Seven-stage pipeline status endpoint.
- [x] DataGate core package and tests.
- [x] DataGate API/UI wiring.
- [x] Ontology Forge MVP.
- [x] GraphRAG MVP.
- [x] Hybrid GraphRAG answer/citation/trace upgrade.
- [x] Guardrail MVP.
- [x] Telemetry / GPU Monitor MVP.
- [x] Homage-Core model scaffold.
- [x] Homage Oven dry-run scaffold with loss trace.
- [x] Unified BakeBoard Alpha UI.
- [x] Vercel deployable Next API fallback.
- [x] Local tests/build/browser verification.
- [x] Deployed browser verification.
- [x] Research-backed Neuro-Efficiency Layer package/API/UI.
- [x] Neuro-efficiency research note with academic/professional sources.
- [x] MiroFish-inspired console UI with ontology memory graph and RAG chat.
- [x] Interactive RAG graph controls: search, zoom, pan, drag, reset, detail.
- [x] PRD engine audit against current Alpha implementation.
- [x] Build Start Alpha orchestrator with reference harvest and training gate.
- [x] Three.js 3D GraphRAG traversal view with staged graph growth, zoom,
      rotation, and node selection.
- [x] Browser screenshots for Build Start, 3D graph growth, graph controls, and
      RAG evidence rendering.
- [x] Compact 70/30 console layout with smaller controls and cards.
- [x] Continuous live-synapse graph growth after Build Start.
- [x] Learning Process buttons now show running state and update card results
      immediately in deployed fallback mode.
- [x] Split BakeBoard into `클라우드 브레인` and `실험실` workspaces.
- [x] Add local cumulative-learning daemon status/start/resume/checkpoint/stop
      APIs with reboot-safe state and checkpoints.
- [x] Keep deployed build as a lab viewer/demo for the daemon area.
- [x] Add Codex Desktop long-run research goal prompt document.
- [x] Make `실험실` the first/default workspace and reduce the lab process UI to
      `수집 / 학습 / 출력`.
- [x] Convert `클라우드 브레인` into a read-only local/API viewer with no direct daemon
      controls in the deployed UI.
- [x] Smooth graph-frame growth and anchor live-synapse placement to avoid
      misleading third-step bursts and detached visual clusters.
- [x] Show learning-edge motion only when `POST /api/memory/build` actually
      stores new visible relations.
- [x] Fold Guardrail into the output stage as an automatic answer check instead
      of a separate manual chat control.
- [x] Collapse right-side settings/status blocks by default so RAG chat has
      more usable space.
- [x] Make `클라우드 브레인` status truthful: read-only viewer, no daemon controls, and
      no fake running state when the local worker is stopped.

- [x] Gate the lab workflow into explicit `수집 -> 학습 -> 출력` stages with
      per-stage progress and disabled downstream actions until the previous
      stage reaches 100%.
- [x] Rework the 3D GraphRAG placement/camera logic so dense graphs expand in a
      stable volume, auto-fit by bounds, and do not snap back to the initial
      camera distance after graph updates.
- [x] Stop finite lab builds from pretending to keep learning through
      client-side live-synapse growth after Collect completes.
- [x] Keep greeting/conversation answers out of web search and memory
      activation so simple greetings produce a clean native reply and no stale
      graph signal.
- [x] Keep the cumulative-learning graph blank until local FastAPI and the
      actual daemon worker are alive.
- [x] Rework max-profile factory graph generation into bounded volumetric
      anchor clusters so the `500,000` long-run target renders as a stable
      `1,720`-node representative 3D sample instead of a flat/spiky burst.
- [x] Replay Build Start graph frames progressively and tune camera fit so max
      Collect grows `12 -> 860 -> 1,720` without snapping back to the initial
      view or zooming too far out.
- [x] Keep the collected representative graph visible during `학습` when the
      persistent memory graph is smaller, and activate only confirmed
      representative relation edges after the learning API completes.
- [x] Split the learning card metrics into representative graph counts and
      stored-memory counts.
- [x] Refresh local benchmark/stability state from FastAPI in the same cycle so
      RAM/VRAM watermarks reflect the viewer's actual PC instead of stale
      fallback values.
- [x] Route all chat questions through `/api/graphrag/query`; conversation
      queries skip web evidence, fresh/news queries use `news-rss`, and person
      lookup queries use `wikipedia` when web search is needed.
- [x] Add Cloud Brain architecture specification for public/shared ontology
      fragments, virtual-edge potentiation, consolidation, decay, pruning,
      lazy loading, and lab fallback when web search is weak.
- [x] Rename the user-facing cumulative-learning workspace to
      `클라우드 브레인` while keeping internal daemon routes compatible.
- [x] Add Alpha `/api/cloud-brain/status`, `/api/cloud-brain/query`,
      `/api/cloud-brain/ingest`, `/api/cloud-brain/consolidate`, and
      `/api/cloud-brain/prune` facade endpoints in FastAPI and Next.js.
- [x] Add Hippocampus continuous learning daemon:
      `data/raw` watcher, ontology_forge ingestion, SQLite WAL synaptic graph,
      UPSERT potentiation, decay/pruning, checkpointing, and optional Neo4j
      mirror.
- [x] Add `POST /api/learning/daemon/decay` and wire Cloud Brain prune to the
      local decay path when not dry-run.

## Next

- [ ] Add Cloud Brain source labels in RAG responses so users can distinguish
      local private memory, fresh web, and public ontology fragments.
- [ ] Replace the Alpha Cloud Brain facade storage with a governed shared
      public graph backend.
- [ ] Persist run history.
- [ ] Persist Build Start graph frames and source provenance.
- [ ] Persist live-synapse growth pulses as durable learning events.
- [ ] Promote learning-edge pulse diagnostics into a persistent graph mutation
      timeline once the append-only ontology event log is implemented.
- [ ] Add governed background Harvest queue feeding the local daemon.
- [ ] Add a native graph-memory decoder evaluation harness.
- [ ] Replace allowlisted reference fetch with governed Harvest connectors.
- [ ] Add document-level metadata browsing.
- [ ] Add graph mutation timeline and replay.
- [ ] Replace the temporary lab live-synapse visualization with durable
      append-only graph event replay from the local daemon.
- [ ] Add tokenizer trainer MVP.
- [ ] Persist and evaluate real DataGate/GraphRAG traces.
- [ ] Implement Knowledge Bakery vector index and evidence store.
- [ ] Split deterministic answer synthesis into Homage Utterance Engine.
- [ ] Run a small SpikingJelly SNN experiment against Homage event traces.
- [ ] Calibrate 8-bit quantization for Guardrail and GraphRAG outputs.
- [ ] Replace deterministic SVG memory layout with interactive force graph.
- [ ] Revisit npm audit advisories.
