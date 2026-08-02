from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any


DEFAULT_Q_CORTEX_ROOT = Path("data/q_cortex")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dirs(root: str | Path = DEFAULT_Q_CORTEX_ROOT) -> Path:
    base = Path(root)
    for name in ("runs", "proofs"):
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path, limit: int = 100) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


_MAX_JSONL_MB = float(os.environ.get("ATANOR_QCORTEX_MAX_MB", "64"))
_RUNS_KEEP = int(os.environ.get("ATANOR_QCORTEX_RUNS_KEEP", "5000"))


def _rotate_if_fat(path: Path) -> None:
    """Bounded run logs (owner 2026-07-17 ): salience_runs.jsonl had grown to 1.007 GB
 and solver_traces to 645 MB — every poll/parse of them was the engine's top CPU sink. These are
 optimizer traces, not knowledge: keep the recent window, rotate the rest to .1 (kept, not lost)."""
    try:
        if path.exists() and path.stat().st_size > _MAX_JSONL_MB * 1024 * 1024:
            old = path.with_suffix(path.suffix + ".1")
            old.unlink(missing_ok=True)
            path.rename(old)
    except OSError:
        pass


def _prune_runs_dir(runs_dir: Path) -> None:
    """The runs dir had grown past 100k one-file-per-run JSONs — each status glob was a stat storm.
    Keep the newest _RUNS_KEEP; called rarely (1% of records) so the prune itself stays cheap."""
    try:
        entries = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        for stale in entries[:-_RUNS_KEEP]:
            stale.unlink(missing_ok=True)
    except OSError:
        pass


def record_run(result: dict[str, Any], filename: str) -> None:
    root = ensure_dirs()
    write_json(root / "runs" / f"{result['run_id']}.json", result)
    if random.random() < 0.01:
        _prune_runs_dir(root / "runs")
    _rotate_if_fat(root / filename)
    _rotate_if_fat(root / "solver_traces.jsonl")
    append_jsonl(root / filename, {**result, "recorded_at": now_iso()})
    append_jsonl(root / "solver_traces.jsonl", {
        "run_id": result["run_id"],
        "problem_type": result["problem_type"],
        "solver_name": result["solver_name"],
        "objective_value": result["objective_value"],
        "trace": result.get("trace", {}),
        "recorded_at": now_iso(),
    })


def list_runs(limit: int = 100) -> list[dict[str, Any]]:
    root = ensure_dirs()
    # the runs dir holds hundreds of thousands of files; parse ONLY the newest `limit`
    # (this endpoint is polled — json-decoding every file allocated ~100MB per poll and
    # fed the engine's memory kill-loop, tracemalloc-measured 2026-07-10)
    newest = sorted((root / "runs").glob("*.json"), key=lambda item: item.stat().st_mtime)[-limit:]
    rows: list[dict[str, Any]] = []
    for path in newest:
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return rows


def get_run(run_id: str) -> dict[str, Any] | None:
    path = ensure_dirs() / "runs" / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
