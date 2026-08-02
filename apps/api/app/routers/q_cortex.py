from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.q_cortex import optimize_roadmap, optimize_salience_workspace, resolve_evidence_conflicts, sample_creative_paths
from packages.q_cortex.adapters import optional_solver_backends
from packages.q_cortex.models import honesty_flags
from packages.q_cortex.proof import write_q_cortex_optimizer_proof
from packages.q_cortex.storage import DEFAULT_Q_CORTEX_ROOT, get_run, list_runs, read_jsonl


router = APIRouter(prefix="/api/q-cortex", tags=["q-cortex"])


class SalienceOptimizeRequest(BaseModel):
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    max_nodes: int = Field(default=128, ge=1, le=512)
    max_edges: int = Field(default=256, ge=0, le=1024)
    seed: int = 42
    solver: str = "simulated_annealing"


class EvidenceResolveRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=240)
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    max_evidence: int = Field(default=12, ge=1, le=128)
    seed: int = 42
    solver: str = "simulated_annealing"


class CreativeSampleRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    candidate_paths: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "far_walk"
    max_paths: int = Field(default=8, ge=1, le=64)
    seed: int = 42
    solver: str = "simulated_annealing"


class PlanningOptimizeRequest(BaseModel):
    steps: list[dict[str, Any]] = Field(default_factory=list)
    max_steps: int = Field(default=4, ge=1, le=32)
    budget_points: int = Field(default=100, ge=1, le=10000)
    seed: int = 42
    solver: str = "simulated_annealing"


def _standard_flags() -> dict[str, Any]:
    return {
        **honesty_flags(),
        "final_answer_generation_claimed": False,
        "real_quantum_hardware_claimed": False,
        "quantum_speedup_claimed": False,
    }



# ~64% of engine CPU — every dashboard poll read_text()+json-parsed salience_runs.jsonl (measured
# 1.007 GB!) four times over just to COUNT lines, and list_runs globbed a 100k-file dir. Two fixes:
#   (a) _jsonl_count: newline count in binary chunks, incremental on append-only growth — never
#       parses JSON, re-reads only the appended tail;
#   (b) a short TTL cache on the whole payload so rapid polls cost ~0.
# (The 1GB write-side growth is a separate finding — per-turn salience payloads are too fat.)
_COUNT_CACHE: dict[str, tuple[float, int, int]] = {}   # path -> (mtime, size, line_count)
_STATUS_TTL: dict[str, Any] = {"at": 0.0, "payload": None}


def _jsonl_count(path: Path) -> int:
    try:
        st = path.stat()
    except OSError:
        return 0
    prev = _COUNT_CACHE.get(str(path))
    if prev and prev[0] == st.st_mtime and prev[1] == st.st_size:
        return prev[2]
    count, start = 0, 0
    if prev and st.st_size >= prev[1]:
        count, start = prev[2], prev[1]                 # append-only: count only the new tail
    with path.open("rb") as fh:
        fh.seek(start)
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            count += chunk.count(b"\n")
    _COUNT_CACHE[str(path)] = (st.st_mtime, st.st_size, count)
    return count


_RUNS_DIR_CACHE: dict[str, Any] = {"mtime": None, "runs": []}


def _cached_list_runs(root: Path, limit: int = 50) -> list[dict[str, Any]]:
    """list_runs re-globbed a ~100k-file dir on every call — py-spy showed the stat() storm at
    37% CPU even behind the TTL. The runs dir mtime changes when a run is added, so glob only then."""
    runs_dir = root / "runs"
    try:
        mtime = runs_dir.stat().st_mtime
    except OSError:
        return []
    if _RUNS_DIR_CACHE["mtime"] == mtime:
        return _RUNS_DIR_CACHE["runs"]
    runs = list_runs(limit=limit)
    _RUNS_DIR_CACHE.update({"mtime": mtime, "runs": runs})
    return runs


@router.get("/status")
def q_cortex_status() -> dict[str, Any]:
    import time as _time
    cached = _STATUS_TTL["payload"]
    if cached is not None and _time.time() - _STATUS_TTL["at"] < 2.5:
        return cached
    root = Path(DEFAULT_Q_CORTEX_ROOT)
    runs = _cached_list_runs(root, limit=50)
    last_run = runs[-1] if runs else None
    payload = {
        "state": "active",
        "architecture": "Q-Cortex Optimizer",
        "label": "Quantum-inspired Cortex Routing",
        "solver_mode": "classical_local",
        "optional_backends": optional_solver_backends(),
        "run_count": len(runs),
        "last_run": last_run,
        "artifacts": {
            # same numbers the read_jsonl(limit=1000) version showed, without parsing a byte of JSON
            "salience_runs": min(_jsonl_count(root / "salience_runs.jsonl"), 1000),
            "evidence_runs": min(_jsonl_count(root / "evidence_runs.jsonl"), 1000),
            "creative_runs": min(_jsonl_count(root / "creative_runs.jsonl"), 1000),
            "planning_runs": min(_jsonl_count(root / "planning_runs.jsonl"), 1000),
        },
        "claims": {
            "quantum_inspired_optimization": True,
            "real_quantum_hardware": False,
            "quantum_speedup": False,
            "consciousness": False,
            "llm_replacement": False,
        },
        **_standard_flags(),
    }
    _STATUS_TTL.update({"at": _time.time(), "payload": payload})
    return payload


@router.post("/salience/optimize")
def q_cortex_salience(request: SalienceOptimizeRequest) -> dict[str, Any]:
    return {
        **optimize_salience_workspace(
            request.candidates,
            max_nodes=request.max_nodes,
            max_edges=request.max_edges,
            seed=request.seed,
            solver=request.solver,
        ),
        **_standard_flags(),
    }


@router.post("/evidence/resolve")
def q_cortex_evidence(request: EvidenceResolveRequest) -> dict[str, Any]:
    return {
        **resolve_evidence_conflicts(
            request.claim_id,
            request.evidence_items,
            max_evidence=request.max_evidence,
            seed=request.seed,
            solver=request.solver,
        ),
        **_standard_flags(),
    }


@router.post("/creative/sample")
def q_cortex_creative(request: CreativeSampleRequest) -> dict[str, Any]:
    return {
        **sample_creative_paths(
            request.prompt,
            request.candidate_paths,
            mode=request.mode,
            max_paths=request.max_paths,
            seed=request.seed,
            solver=request.solver,
        ),
        **_standard_flags(),
    }


@router.post("/planning/optimize")
def q_cortex_planning(request: PlanningOptimizeRequest) -> dict[str, Any]:
    return {
        **optimize_roadmap(
            request.steps,
            max_steps=request.max_steps,
            budget_points=request.budget_points,
            seed=request.seed,
            solver=request.solver,
        ),
        **_standard_flags(),
    }


@router.get("/runs")
def q_cortex_runs(limit: int = 50) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 200))
    return {"runs": list_runs(limit=bounded_limit), "count": len(list_runs(limit=bounded_limit)), **_standard_flags()}


@router.get("/runs/{run_id}")
def q_cortex_run(run_id: str) -> dict[str, Any]:
    result = get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="q_cortex_run_not_found")
    return {**result, **_standard_flags()}


@router.post("/proof")
def q_cortex_proof() -> dict[str, Any]:
    return {**write_q_cortex_optimizer_proof(), **_standard_flags()}
