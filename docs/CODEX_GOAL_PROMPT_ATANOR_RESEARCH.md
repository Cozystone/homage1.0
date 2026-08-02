# Codex Desktop Goal Prompt: ATANOR Long-Run Research

Paste this into Codex Desktop goal settings when you want Codex to keep
researching ATANOR as a long-running local AI experiment.

```text
Build and improve ATANOR as a long-running local research system.

Vision:
Create an independent graph-memory language architecture that can run on a
single workstation without external LLMs, local quantized LLMs, or pretrained
generation weights. The target is not to hide weak output. The target is to
observe weak output honestly, improve the architecture, and keep iterating
toward medium-LLM-like answer quality on workstation hardware.

Hardware target:
- CPU: AMD Ryzen 9 9950X3D
- GPU: ZOTAC GAMING GeForce RTX 5080 AMP EXTREME INFINITY 16GB GDDR7
- Motherboard: ASUS ROG CROSSHAIR X870E HERO
- RAM: Micron DDR5 32GB (16GB x 2)
- SSD: GIGABYTE AORUS Gen4 7300 V2 1TB
- PSU: SuperFlower SF-1200F14XP LEADEX VII PRO PLATINUM ATX 3.1
- Cooler: CoolerMaster MASTERLIQUID 360 ATMOS
- Case: Antec FLUX MESH BTF Black

Operating split:
1. Deployment is a small demo/lab viewer only. It should show the structure,
   graph, activation behavior, and current research controls without pretending
   that a long-running learner is active on Vercel.
2. Real development and cumulative learning run locally through FastAPI,
   Knowledge Bakery SQLite WAL, events.jsonl, checkpoints, and the local
   Next.js BakeBoard.

Core loop:
1. Start local FastAPI and Next.js. Open the app in the browser and operate it
   directly.
2. Use the Cloud Brain space to monitor worker status, checkpoints,
   node/edge/event counts, runtime, resource pressure, and resume-needed state.
   Before the local API and worker are actually running, the Cloud Brain graph
   must stay empty instead of showing demo memory.
3. Use the lab space strictly as a three-stage experiment:
   collect -> learn -> output. Do not let Build Start make the UI look as if all
   stages completed at once. Collection must reach 100% before learning is
   enabled; learning must reach 100% before output is evaluated.
4. Inspect the 3D graph as a truthful visualization. New volume, moving edge
   pulses, and active nodes must correspond to actual new graph nodes/relations
   or real query activation. Do not add fake activity just to make the graph
   look alive.
5. Query the Knowledge Bakery SQLite store and JSONL events directly when UI
   behavior is unclear. Verify whether new nodes are really persisted, whether
   edges are retained, and whether active signals still map to visible nodes
   after the graph grows.
6. When output is broken, do not cover it with templates or fake confidence.
   Let the broken output be visible, diagnose why the native graph-memory
   decoder failed, then improve the architecture.
7. If RAM, VRAM, disk, queue lag, graph writer lag, or browser rendering limits
   trigger a warning, treat the experiment as failed for that configuration.
   Document the failure, search academic/professional sources for a better
   approach, and implement a safer architecture.
8. After every meaningful improvement, run tests, build the frontend, verify in
   the browser with screenshots, update docs/PROJECT_STATE.md, and commit.
9. Continue this observe -> hypothesize -> implement -> verify -> document loop
   until the user stops the goal or the work is genuinely blocked.

Architectural constraints:
- Do not use external LLMs for answer generation.
- Do not use local quantized LLMs or pretrained generation weights.
- Web search and papers may be used for research and source collection, but the
  answer engine must not claim abilities that are not present in its own memory
  and decoder.
- Prefer append-only memory events, stable node identities, typed relations,
  sparse activation, checkpointable state, and browser-verifiable UI behavior.
- Keep deployment honest: demo/lab viewer only; real cumulative learning is
  local.
- Greeting/control utterances such as "?덈뀞" must not be routed through web
  search just because the web-search toggle is enabled.

Research target:
Improve ATANOR toward an independent workstation-scale system that learns from
random and curated text by splitting sentence components, accumulating typed
3D ontology relations, learning transition/cooccurrence/phrase probabilities,
and generating language from graph activation rather than a conventional
pretrained LLM.
```

## Local Reboot Protocol

The local learner stores state in:

- `data/memory/homage.db`
- `data/memory/events.jsonl`
- `data/memory/daemon_state.json`
- `data/memory/daemon_checkpoints/*.json`

If the PC reboots:

1. Start the FastAPI backend again.
2. Open BakeBoard locally.
3. Go to `?대씪?곕뱶 釉뚮젅??.
4. If the state is `?ш컻 ?꾩슂`, resume the local daemon through the local
   FastAPI management API or the backend startup policy. The BakeBoard
   Cloud Brain screen is a viewer and should not pretend to operate the worker
   when it is not actually running.

For automatic daemon resume after backend startup, start FastAPI with:

```powershell
$env:ATANOR_AUTOSTART_DAEMON="1"
npm run api:dev
```

This only resumes if the previous persisted state had `desired_running=true`.
