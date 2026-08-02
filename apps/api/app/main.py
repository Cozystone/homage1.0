from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.services.desktop_paths import configure_desktop_data_dir


def _configure_local_package_paths() -> None:
    """Allow the monorepo API app to import local package roots without editable installs."""

    repo_root = Path(__file__).resolve().parents[3]
    packages_root = repo_root / "packages"
    if not packages_root.exists():
        return
    for package_dir in sorted(packages_root.iterdir(), reverse=True):
        has_installable_metadata = (package_dir / "pyproject.toml").exists()
        has_import_package = (package_dir / package_dir.name / "__init__.py").exists()
        if not has_installable_metadata and not has_import_package:
            continue
        package_path = str(package_dir)
        if package_path not in sys.path:
            sys.path.insert(0, package_path)


def _configure_runtime_data_dir_from_args() -> None:
    """Honor the Tauri sidecar data directory before any data services run."""

    if "--operator" in sys.argv:
        os.environ["ATANOR_OPERATOR"] = "1"
        os.environ["ATANOR_AUTO_START_DAEMON"] = "1"
        os.environ["ATANOR_AUTOSTART_DAEMON"] = "1"
        os.environ["HOMAGE_OPERATOR"] = "1"
        os.environ["HOMAGE_AUTO_START_DAEMON"] = "1"
        # Membrane: certify hallucination-0 on live answers (owner-activated 2026-07-24 after the
        # signal fix — France/basics ACCEPT with certificate, namesake pollution ABSTAINS; AUC 0.90,
        # P(accept|wrong)=0.056<=0.10, ~30% abstention). Set to "0" to deactivate (fully reversible).
        os.environ.setdefault("ATANOR_MEMBRANE_LIVE", "1")
    if "--data-dir" not in sys.argv:
        return
    try:
        index = sys.argv.index("--data-dir")
        data_dir = sys.argv[index + 1]
    except (ValueError, IndexError):
        return
    configure_desktop_data_dir(data_dir, chdir=True)


_configure_runtime_data_dir_from_args()
_configure_local_package_paths()

from app.routers.brain_sync import router as brain_sync_router
from app.routers.status_stream import router as status_stream_router
from app.routers.continuous_self import router as continuous_self_router
from app.routers.answer_quality import router as answer_quality_router
from app.routers.agentic_micro_os import router as agentic_micro_os_router
from app.routers.agora import router as agora_router
from app.routers.base_brain import router as base_brain_router
from app.routers.realcity_agent import router as realcity_agent_router
from app.routers.realcity_learning import router as realcity_learning_router
from app.routers.brain_graph import router as brain_graph_router
from app.routers.brain_link import router as brain_link_router
from app.routers.cloud_brain import router as cloud_brain_router
from app.routers.contribution import router as contribution_router
from app.routers.identity import router as identity_router
from app.routers.voice import router as voice_router
from app.routers.os_action import router as os_action_router
from app.routers.expedition import router as expedition_router
from app.routers.browser import router as browser_router
from app.routers.ops import router as ops_router
from app.routers.worm_culture import router as worm_culture_router
from app.routers.evolution import router as evolution_router
from app.routers.perception import router as perception_router
from app.routers.imagination import router as imagination_router
from app.routers.affordance import router as affordance_router
from app.routers.phone_link import router as phone_link_router
from app.routers.link_relay import router as link_relay_router
from app.routers.construction_bank import router as construction_bank_router
from app.routers.cortex import router as cortex_router
from app.routers.datagate import router as datagate_router
from app.routers.dual_brain import router as dual_brain_router
from app.routers.factory import router as factory_router
from app.routers.graph import router as graph_router
from app.routers.graph_hub import router as graph_hub_router
from app.routers.graphrag import router as graphrag_router
from app.routers.guard import router as guard_router
from app.routers.harvest import router as harvest_router
from app.routers.hybrid_network import router as hybrid_network_router
from app.routers.inner_voice import router as inner_voice_router
from app.routers.learning import router as learning_router
from app.routers.local_memory_approval import router as local_memory_approval_router
from app.routers.realtime_think import router as realtime_think_router
from app.routers.brain_graph_ask import router as brain_graph_ask_router
from app.routers.waitlist import router as waitlist_router
from app.routers.memory import router as memory_router
from app.routers.neural_emotion import router as neural_emotion_router
from app.routers.neuro import router as neuro_router
from app.routers.ontology import router as ontology_router
from app.routers.oven import router as oven_router
from app.routers.q_cortex import router as q_cortex_router
from app.routers.seed_research import router as seed_research_router
from app.routers.storage import router as storage_router
from app.routers.surface_brain import router as surface_brain_router
from app.routers.telemetry import router as telemetry_router
from app.routers.working_memory import router as working_memory_router
from app.services.alpha_services import alpha_service, telemetry_gpu
from app.services.crash_safety import create_boot_shadow_backups
from app.services.datagate_service import DataGateStatus, datagate_service
from app.services.ingestion_stream import cleaned_directory_watcher, graph_event_hub
from app.services.autonomy_run_lease_bootstrap import (
    bootstrap_autonomy_run_leases,
    shutdown_autonomy_run_lease_runners,
)
from knowledge_bakery import daemon_status as learning_daemon_status
from knowledge_bakery import start_daemon
from neuro_efficiency import build_hardware_benchmark

StageState = Literal["idle", "running", "warning", "complete"]


class PipelineStage(BaseModel):
    id: str
    name: str
    state: StageState
    progress: int
    summary: str
    metric_label: str
    metric_value: str


class PipelineStatus(BaseModel):
    generated_at: datetime
    system_state: str
    stages: list[PipelineStage]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # GC tuning: the graph aggregators churn thousands of short-lived dicts per poll, so the
    # cyclic collector fired often and its pauses showed up as periodic ~0.5-1s latency
    # spikes on otherwise ~30ms endpoints. freeze() moves the large permanent startup object
    # set out of the generations GC scans, and higher thresholds collect less often — both
    # shrink each pause. (Not a leak: freeze only excludes already-live long-lived objects.)
    import gc as _gc
    _gc.collect()
    _gc.freeze()
    _gc.set_threshold(50_000, 500, 500)
    autonomy_run_lease_bootstrap = bootstrap_autonomy_run_leases()
    _app.state.autonomy_run_lease_bootstrap = (
        autonomy_run_lease_bootstrap.public_status()
    )
    create_boot_shadow_backups()
    try:
        skip_benchmark = os.getenv("ATANOR_SKIP_STARTUP_BENCHMARK", os.getenv("HOMAGE_SKIP_STARTUP_BENCHMARK")) == "1"
        build_hardware_benchmark({"run_probes": not skip_benchmark})
    except Exception:
        pass
    cleaned_directory_watcher.start()
    if os.getenv("ATANOR_AUTO_START_DAEMON", os.getenv("ATANOR_AUTOSTART_DAEMON", os.getenv("HOMAGE_AUTO_START_DAEMON"))) == "1":
        start_daemon(interval_seconds=30, resume=True)
    # Infinite cumulative learning loop — on by default so the cloud/surface graph
    # keeps growing from real public sentences. Disable with ATANOR_AUTO_LEARN=0.
    if os.getenv("ATANOR_AUTO_LEARN", "1") != "0":
        try:
            from app.routers.cloud_brain import cloud_brain_continuous_start

            cloud_brain_continuous_start()
        except Exception:  # pragma: no cover - never block startup
            pass
    # A1 cold-boot warmup (ultimate battery: the FIRST real question paid ~15.5s because the
    # answer pack + TripleStore + Kiwi all lazy-load on first touch). Pay that cost HERE, off
    # the request path, in a background thread — the user's first question then runs warm.
    def _warmup() -> None:
        import time as _time
        try:
            _time.sleep(2.0)   # let the server finish binding first
            t0 = _time.time()
            from packages.base_brain.pack_loader import get_semantic_context, load_base_brain_pack
            get_semantic_context("서울", load_base_brain_pack())   # pack + concept index
            try:
                from packages.graph_scale import answer_bridge
                answer_bridge.answer_from_triples("서울은 무엇인가요")   # TripleStore + TermDict
            except Exception:
                pass
            try:
                from packages.graph_scale.query_frame import parse as _qf_parse
                _qf_parse("대한민국의 수도는 어디야?")
            except Exception:
                pass
            try:
                from packages.continuous_self.thought_language import realize_thought
                realize_thought("learning_active", {"topic": "지식"}, None)
            except Exception:
                pass
            try:
                # 2M-triple Kaikki cartridge index build is ~7.6s on first lookup — pay it here
                # at boot, not on the user's first definition query (it inflated the battery mean
                # and caused 9-25s cold answers). After this, cartridge lookups are ~0ms.
                from packages.graph_scale import lexicon_lane as _lex
                _lex.lookup("서울", "ko")
            except Exception:
                pass
            print(f"[warmup] answer path warmed in {_time.time()-t0:.1f}s", flush=True)
        except Exception as exc:  # pragma: no cover — warmup must never hurt boot
            print(f"[warmup] skipped: {exc}", flush=True)
        finally:
            # release the learners' boot grace — cold-load is done, they may ramp up now
            try:
                from packages.graph_scale.load_signal import mark_warmup_done
                mark_warmup_done()
            except Exception:
                pass

    import threading as _threading
    _threading.Thread(target=_warmup, name="a1-warmup", daemon=True).start()
    await graph_event_hub.publish_snapshot(event_type="graph_snapshot", trigger="api_startup", limit=5000)
    try:
        yield
    finally:
        _app.state.autonomy_run_lease_bootstrap = (
            shutdown_autonomy_run_lease_runners(
                autonomy_run_lease_bootstrap
            )
        )
        await cleaned_directory_watcher.stop()


app = FastAPI(
    title="ATANOR API",
    description="ATANOR local-first Ghost Shell and Payload Vault API.",
    version="0.1.0",
    lifespan=lifespan,
)

# Explicit allow-list of the real deployed frontends + local dev/companion origins. Codex
# audit P0: the previous `https://.*\.vercel\.app` regex let ANY vercel-hosted page make
# credentialed calls to a local engine — a CSRF surface. Extra production origins go through
# ATANOR_EXTRA_CORS_ORIGINS (comma-separated) instead of a wildcard.
_CORS_ORIGINS = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:3030", "http://127.0.0.1:3030",
    "http://localhost:3022", "http://127.0.0.1:3022",
    "tauri://localhost", "asset://localhost",
    "http://tauri.localhost", "https://tauri.localhost", "null",
    "https://atanor-alpha.vercel.app", "https://homage-alpha.vercel.app",
]
_CORS_ORIGINS += [o.strip() for o in os.environ.get("ATANOR_EXTRA_CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # localhost/tauri only — NO open cross-site wildcard (the vercel wildcard was removed).
    allow_origin_regex=r"http://localhost:\d+|http://127\.0\.0\.1:\d+|tauri://.*|asset://.*|https?://.*\.tauri\.localhost",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_browser_local_companion(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

app.include_router(datagate_router)
app.include_router(answer_quality_router)
app.include_router(agentic_micro_os_router)
app.include_router(agora_router)
app.include_router(base_brain_router)
app.include_router(brain_graph_router)
app.include_router(brain_link_router)
app.include_router(harvest_router)
app.include_router(hybrid_network_router)
app.include_router(inner_voice_router)
app.include_router(brain_sync_router)
app.include_router(status_stream_router)
app.include_router(continuous_self_router)
app.include_router(learning_router)
app.include_router(local_memory_approval_router)
app.include_router(realtime_think_router)
app.include_router(brain_graph_ask_router)
app.include_router(cloud_brain_router)
app.include_router(voice_router)
app.include_router(waitlist_router)
app.include_router(os_action_router)
app.include_router(expedition_router)
app.include_router(perception_router)
app.include_router(imagination_router)
app.include_router(affordance_router)
app.include_router(browser_router)
app.include_router(ops_router)
app.include_router(worm_culture_router)
app.include_router(evolution_router)
app.include_router(phone_link_router)
app.include_router(link_relay_router)
app.include_router(contribution_router)
app.include_router(identity_router)
app.include_router(construction_bank_router)
app.include_router(cortex_router)
app.include_router(dual_brain_router)
app.include_router(factory_router)
app.include_router(graph_router)
app.include_router(graph_hub_router)
app.include_router(ontology_router)
app.include_router(graphrag_router)
app.include_router(guard_router)
app.include_router(memory_router)
app.include_router(neural_emotion_router)
app.include_router(working_memory_router)
app.include_router(neuro_router)
app.include_router(q_cortex_router)
app.include_router(seed_research_router)
app.include_router(storage_router)
app.include_router(surface_brain_router)
app.include_router(telemetry_router)
app.include_router(oven_router)
app.include_router(realcity_agent_router)
app.include_router(realcity_learning_router)


def datagate_stage(status: DataGateStatus) -> PipelineStage:
    state_map: dict[str, StageState] = {
        "idle": "idle",
        "running": "running",
        "completed": "complete",
        "failed": "warning",
    }
    if status.state == "idle":
        progress = 0
        metric_value = "not run"
        summary = "Ready to score source quality, deduplicate, and filter unsafe inputs."
    elif status.state == "running":
        progress = 50
        metric_value = "running"
        summary = "DataGate is processing local raw documents."
    elif status.state == "completed":
        progress = 100
        metric_value = f"{status.accepted}/{status.total} accepted"
        summary = "Latest DataGate run completed with deterministic document partitioning."
    else:
        progress = 100
        metric_value = "failed"
        summary = status.error or "Latest DataGate run failed."

    return PipelineStage(
        id="datagate",
        name="DataGate",
        state=state_map[status.state],
        progress=progress,
        summary=summary,
        metric_label="quality gate",
        metric_value=metric_value,
    )


def alpha_stage(
    stage_id: str,
    name: str,
    status: dict,
    idle_summary: str,
    done_summary: str,
    metric_label: str,
    metric_value: str,
) -> PipelineStage:
    state = status.get("state", "idle")
    stage_state: StageState = (
        "running" if state == "running" else "complete" if state == "completed" else "warning" if state == "failed" else "idle"
    )
    return PipelineStage(
        id=stage_id,
        name=name,
        state=stage_state,
        progress=100 if state == "completed" else 50 if state == "running" else 0 if state == "idle" else 100,
        summary=done_summary if state == "completed" else status.get("error") or idle_summary,
        metric_label=metric_label,
        metric_value=metric_value,
    )


def harvest_stage() -> PipelineStage:
    raw_dir = Path(os.environ.get("ATANOR_RAW_DIR", os.environ.get("HOMAGE_RAW_DIR", "data/raw")))
    cleaned_dir = Path(os.environ.get("ATANOR_CLEANED_DIR", os.environ.get("HOMAGE_CLEANED_DIR", "data/cleaned")))
    raw_files = [path for ext in ("*.txt", "*.md") for path in raw_dir.rglob(ext)] if raw_dir.exists() else []
    cleaned_files = [path for ext in ("*.txt", "*.md") for path in cleaned_dir.rglob(ext)] if cleaned_dir.exists() else []
    daemon = learning_daemon_status()
    worker_alive = bool(daemon.get("worker_alive"))
    queued = len(raw_files)
    processed = len(cleaned_files)
    state: StageState = "running" if worker_alive else "warning" if daemon.get("desired_running") else "idle"
    if worker_alive and queued == 0:
        summary = "Continuous ingestion stream is awake and waiting for payloads."
        progress = 1
    elif worker_alive:
        summary = "Continuous ingestion stream is ingesting raw payload files."
        progress = 50
    else:
        summary = "Continuous ingestion stream is not alive; self-healing daemon status should restart it."
        progress = 0
    return PipelineStage(
        id="harvest",
        name="Harvest",
        state=state,
        progress=progress,
        summary=summary,
        metric_label="stream",
        metric_value=f"{queued} queued / {processed} vaulted",
    )


def _git_sha() -> str:
    """Commit the RUNNING process was started from — read once at import. The chronic
    ops-drift bug is a live server silently serving pre-fix code; exposing the SHA makes
    'is the running code current?' a one-request check instead of a guess."""
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        git = root / ".git"
        if git.is_file():   # worktree: .git is a pointer file 'gitdir: <path>'
            git = Path(git.read_text(encoding="utf-8").split(":", 1)[1].strip())
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            ref_file = git / ref
            if not ref_file.exists() and (git / "commondir").exists():
                common = (git / (git / "commondir").read_text(encoding="utf-8").strip()).resolve()
                ref_file = common / ref
            return ref_file.read_text(encoding="utf-8").strip()[:12]
        return head[:12]
    except Exception:
        return "unknown"


_STARTED_SHA = _git_sha()
_STARTED_AT = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "git_sha": _STARTED_SHA, "started_at": _STARTED_AT}


# ── memory diagnostics (ops tool) ─────────────────────────────────────────────
# The engine has lived in a watchdog kill-loop (RSS runs past 12288MB in minutes;
# see data/watchdog.log). tracemalloc pinpoints the allocating file:line so the
# eater is measured, not guessed. Local engine only (:8502 binds 127.0.0.1).
@app.post("/debug/mem/start")
def mem_trace_start() -> dict:
    import tracemalloc
    if not tracemalloc.is_tracing():
        tracemalloc.start(15)
    return {"tracing": True}


@app.get("/debug/mem/top")
def mem_trace_top(limit: int = 20) -> dict:
    import tracemalloc
    if not tracemalloc.is_tracing():
        return {"tracing": False, "top": []}
    snap = tracemalloc.take_snapshot()
    stats = snap.statistics("traceback")
    top = []
    for st in stats[:limit]:
        frames = [f"{f.filename.split('atanor demo')[-1].split('ATANOR DEMO')[-1]}:{f.lineno}"
                  for f in st.traceback[-4:]]
        top.append({"size_mb": round(st.size / (1024 * 1024), 1), "count": st.count,
                    "trace": " <- ".join(reversed(frames))})
    cur, peak = tracemalloc.get_traced_memory()
    return {"tracing": True, "traced_mb": round(cur / 1048576, 1),
            "peak_mb": round(peak / 1048576, 1), "top": top}


@app.get("/api/pipeline/status", response_model=PipelineStatus)
def pipeline_status() -> PipelineStatus:
    datagate_status = datagate_service.status()
    ontology_status = alpha_service.ontology_status()
    graphrag_status = alpha_service.graphrag_status()
    guard_status = alpha_service.guard_status()
    memory_status = alpha_service.memory_status()
    oven_status = alpha_service.oven_status()
    gpu_status = telemetry_gpu()
    stages = [
        harvest_stage(),
        datagate_stage(datagate_status),
        alpha_stage(
            "ontology-forge",
            "Ontology Forge",
            ontology_status,
            "Ready to extract concept nodes and relation edges from cleaned documents.",
            "Ontology graph files are available for GraphRAG.",
            "graph",
            f"{ontology_status.get('node_count', 0)} nodes / {ontology_status.get('edge_count', 0)} edges",
        ),
        alpha_stage(
            "atanor-oven",
            "ATANOR Oven",
            oven_status,
            "Training scaffold is ready for a safe dry-run.",
            "Dry-run produced a loss trace and checkpoint manifest.",
            "last loss",
            str(oven_status.get("last_loss") or "not run"),
        ),
        alpha_stage(
            "graphrag",
            "GraphRAG",
            graphrag_status,
            "Ready to retrieve evidence from cleaned docs and ontology graph.",
            "Latest query produced an inspectable evidence bundle.",
            "confidence",
            str(graphrag_status.get("confidence") or 0),
        ),
        alpha_stage(
            "knowledge-bakery",
            "Knowledge Bakery",
            memory_status,
            "Ready to persist sentence components, token transitions, phrase nodes, and local 3D vectors.",
            "Local append-only memory store and activation index are available.",
            "memory",
            f"{memory_status.get('node_count', 0)} nodes / {memory_status.get('transition_count', 0)} transitions",
        ),
        alpha_stage(
            "guardrail",
            "Guardrail",
            guard_status,
            "Ready to check draft claims against evidence and ontology.",
            "Latest guard report is available.",
            "guard score",
            str(guard_status.get("overall_guard_score") or 0),
        ),
        PipelineStage(
            id="gpu-monitor",
            name="GPU Monitor",
            state="complete" if gpu_status.get("available") else "warning",
            progress=100 if gpu_status.get("available") else 35,
            summary=gpu_status.get("message") or "Local GPU telemetry is available.",
            metric_label="vram",
            metric_value=(
                f"{gpu_status.get('vram_used', 0)} / {gpu_status.get('vram_total', 0)} MB"
                if gpu_status.get("available")
                else "fallback"
            ),
        ),
    ]
    return PipelineStatus(
        generated_at=datetime.now(timezone.utc),
        system_state="alpha_active",
        stages=stages,
    )
