from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .memory import build_memory, memory_status


DEFAULT_MEMORY_DIR = "data/memory"
DEFAULT_WATCH_DIRS = ("data/cleaned", "data/ontology")
DEFAULT_INTERVAL_SECONDS = 30
MIN_DISK_FREE_GB = 20.0
MIN_RAM_AVAILABLE_GB = 1.5

_lock = threading.RLock()
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _memory_root(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return Path(memory_dir)


def _state_path(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return _memory_root(memory_dir) / "daemon_state.json"


def _checkpoint_dir(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    return _memory_root(memory_dir) / "daemon_checkpoints"


def _default_state() -> dict[str, Any]:
    return {
        "mode": "local-daemon",
        "state": "idle",
        "desired_running": False,
        "resume_after_reboot": True,
        "resume_needed": False,
        "worker_alive": False,
        "started_at": None,
        "last_heartbeat_at": None,
        "last_tick_at": None,
        "last_checkpoint_at": None,
        "last_input_fingerprint": None,
        "last_round_action": None,
        "last_round_message": "No long-running local learner has been started.",
        "last_error": None,
        "interval_seconds": DEFAULT_INTERVAL_SECONDS,
        "total_runtime_seconds": 0,
        "total_rounds": 0,
        "learned_rounds": 0,
        "idle_rounds": 0,
        "latest_event_count": 0,
        "latest_node_count": 0,
        "latest_edge_count": 0,
        "resource_warning": None,
        "watch_dirs": list(DEFAULT_WATCH_DIRS),
        "reboot_resilience": {
            "state_file": str(_state_path()),
            "checkpoint_dir": str(_checkpoint_dir()),
            "heartbeat_interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "checkpoint_interval_seconds": 300,
            "resume_contract": "Restart local FastAPI and call /api/learning/daemon/resume; the daemon resumes from SQLite WAL, events.jsonl, and daemon_state.json.",
        },
        "llm_policy": {
            "external_llm": False,
            "local_quantized_llm": False,
            "pretrained_generation_weights": False,
        },
    }


def _read_state(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    path = _state_path(memory_dir)
    if not path.exists():
        return _default_state()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    state = _default_state()
    state.update(loaded)
    state["reboot_resilience"] = {
        **_default_state()["reboot_resilience"],
        **dict(loaded.get("reboot_resilience") or {}),
    }
    state["llm_policy"] = {
        **_default_state()["llm_policy"],
        **dict(loaded.get("llm_policy") or {}),
    }
    return state


def _write_state(state: dict[str, Any], memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> None:
    root = _memory_root(memory_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = _state_path(memory_dir)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _worker_alive() -> bool:
    return bool(_worker_thread and _worker_thread.is_alive())


def _input_fingerprint(watch_dirs: list[str] | tuple[str, ...]) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    extensions = {".txt", ".md", ".json"}
    for raw_dir in watch_dirs:
        root = Path(raw_dir)
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in extensions):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            file_count += 1
            byte_count += len(data)
            digest.update(str(path.as_posix()).encode("utf-8", errors="ignore"))
            digest.update(len(data).to_bytes(8, "big", signed=False))
            digest.update(hashlib.sha256(data).digest())
    return {
        "fingerprint": digest.hexdigest(),
        "file_count": file_count,
        "byte_count": byte_count,
        "watch_dirs": list(watch_dirs),
    }


def _resource_snapshot(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    disk = shutil.disk_usage(_memory_root(memory_dir).resolve().anchor or ".")
    snapshot: dict[str, Any] = {
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "ram_available_gb": None,
        "ram_total_gb": None,
    }
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        snapshot["ram_available_gb"] = round(memory.available / (1024**3), 2)
        snapshot["ram_total_gb"] = round(memory.total / (1024**3), 2)
    except Exception:
        pass
    return snapshot


def _resource_blocker(snapshot: dict[str, Any]) -> str | None:
    disk_free = float(snapshot.get("disk_free_gb") or 0)
    ram_available = snapshot.get("ram_available_gb")
    if disk_free < MIN_DISK_FREE_GB:
        return f"disk_free_below_{MIN_DISK_FREE_GB:g}gb"
    if ram_available is not None and float(ram_available) < MIN_RAM_AVAILABLE_GB:
        return f"ram_available_below_{MIN_RAM_AVAILABLE_GB:g}gb"
    return None


def _merge_runtime(state: dict[str, Any]) -> dict[str, Any]:
    now_ts = time.time()
    started_ts = _parse_iso(state.get("started_at"))
    if started_ts and state.get("desired_running"):
        state["total_runtime_seconds"] = max(int(now_ts - started_ts), int(state.get("total_runtime_seconds") or 0))
    return state


def _refresh_counts(state: dict[str, Any], memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    status = memory_status(str(memory_dir))
    state["latest_event_count"] = int(status.get("event_count") or 0)
    state["latest_node_count"] = int(status.get("node_count") or 0)
    state["latest_edge_count"] = int(status.get("edge_count") or 0)
    return state


def daemon_status(memory_dir: str = DEFAULT_MEMORY_DIR) -> dict[str, Any]:
    with _lock:
        state = _merge_runtime(_read_state(memory_dir))
        alive = _worker_alive()
        state["worker_alive"] = alive
        if state.get("desired_running") and not alive and state.get("state") not in {"failed"}:
            state["state"] = "resume_needed"
            state["resume_needed"] = True
            state["last_round_message"] = (
                "Local FastAPI was restarted or the daemon worker is not alive. "
                "Call resume to continue from the persisted memory store."
            )
        else:
            state["resume_needed"] = False
        state["resource_snapshot"] = _resource_snapshot(memory_dir)
        state["checkpoint_count"] = len(list(_checkpoint_dir(memory_dir).glob("*.json"))) if _checkpoint_dir(memory_dir).exists() else 0
        state["local_required"] = True
        state["deployment_policy"] = "The Vercel deployment stays a small demo; real cumulative learning runs only beside local FastAPI."
        _refresh_counts(state, memory_dir)
        return state


def daemon_checkpoint(memory_dir: str = DEFAULT_MEMORY_DIR, reason: str = "manual") -> dict[str, Any]:
    with _lock:
        root = _checkpoint_dir(memory_dir)
        root.mkdir(parents=True, exist_ok=True)
        state = _read_state(memory_dir)
        snapshot = {
            "created_at": utc_now_iso(),
            "reason": reason,
            "daemon": state,
            "memory": memory_status(memory_dir),
        }
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{reason.replace(' ', '-')[:32]}.json"
        (root / filename).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        state["last_checkpoint_at"] = snapshot["created_at"]
        state["last_checkpoint_path"] = str(root / filename)
        _write_state(state, memory_dir)
        return daemon_status(memory_dir)


def tick_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, force: bool = False) -> dict[str, Any]:
    with _lock:
        state = _read_state(memory_dir)
        snapshot = _resource_snapshot(memory_dir)
        blocker = _resource_blocker(snapshot)
        now = utc_now_iso()
        if blocker:
            state.update(
                {
                    "state": "failed",
                    "desired_running": False,
                    "last_error": blocker,
                    "resource_warning": blocker,
                    "last_heartbeat_at": now,
                    "last_round_message": "Resource guard stopped the daemon before the workstation became unstable.",
                }
            )
            _write_state(_refresh_counts(state, memory_dir), memory_dir)
            return daemon_status(memory_dir)

        watch_dirs = list(state.get("watch_dirs") or DEFAULT_WATCH_DIRS)
        fingerprint = _input_fingerprint(watch_dirs)
        memory = memory_status(memory_dir)
        needs_build = force or state.get("last_input_fingerprint") != fingerprint["fingerprint"] or memory.get("state") != "completed"
        if needs_build:
            result = build_memory(memory_dir=memory_dir)
            action = "memory_rebuilt_from_inputs"
            message = (
                f"Indexed {fingerprint['file_count']} watched files into {result.get('node_count', 0)} nodes "
                f"and {result.get('edge_count', 0)} edges."
            )
            state["learned_rounds"] = int(state.get("learned_rounds") or 0) + 1
        else:
            result = memory
            action = "heartbeat_no_new_input"
            message = "No new cleaned/ontology input changed; heartbeat and checkpoint state were preserved."
            state["idle_rounds"] = int(state.get("idle_rounds") or 0) + 1

        state.update(
            {
                "state": "running" if state.get("desired_running") else "idle",
                "last_heartbeat_at": now,
                "last_tick_at": now,
                "last_input_fingerprint": fingerprint["fingerprint"],
                "last_input_file_count": fingerprint["file_count"],
                "last_input_bytes": fingerprint["byte_count"],
                "last_round_action": action,
                "last_round_message": message,
                "last_error": None,
                "resource_warning": None,
                "total_rounds": int(state.get("total_rounds") or 0) + 1,
                "latest_event_count": int(result.get("event_count") or 0),
                "latest_node_count": int(result.get("node_count") or 0),
                "latest_edge_count": int(result.get("edge_count") or 0),
                "resource_snapshot": snapshot,
            }
        )
        _write_state(_merge_runtime(state), memory_dir)
        return daemon_status(memory_dir)


def _worker_loop(memory_dir: str, interval_seconds: int) -> None:
    while not _stop_event.is_set():
        tick_daemon(memory_dir)
        status = daemon_status(memory_dir)
        if status.get("state") == "failed":
            break
        last_checkpoint = _parse_iso(status.get("last_checkpoint_at")) or 0
        if time.time() - last_checkpoint >= 300:
            daemon_checkpoint(memory_dir, "auto")
        _stop_event.wait(interval_seconds)


def start_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, interval_seconds: int = DEFAULT_INTERVAL_SECONDS, resume: bool = True) -> dict[str, Any]:
    global _worker_thread
    interval_seconds = max(5, min(3600, int(interval_seconds or DEFAULT_INTERVAL_SECONDS)))
    with _lock:
        if _worker_alive():
            return daemon_status(memory_dir)
        state = _read_state(memory_dir)
        if not resume:
            state = _default_state()
        now = utc_now_iso()
        state.update(
            {
                "state": "running",
                "desired_running": True,
                "resume_needed": False,
                "started_at": state.get("started_at") if resume and state.get("started_at") else now,
                "last_heartbeat_at": now,
                "interval_seconds": interval_seconds,
                "last_error": None,
                "last_round_message": "Local cumulative learner is running.",
            }
        )
        state["reboot_resilience"] = {
            **state.get("reboot_resilience", {}),
            "state_file": str(_state_path(memory_dir)),
            "checkpoint_dir": str(_checkpoint_dir(memory_dir)),
            "heartbeat_interval_seconds": interval_seconds,
        }
        _write_state(state, memory_dir)
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_worker_loop, args=(memory_dir, interval_seconds), daemon=True, name="homage-learning-daemon")
        _worker_thread.start()
        return daemon_status(memory_dir)


def resume_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> dict[str, Any]:
    return start_daemon(memory_dir=memory_dir, interval_seconds=interval_seconds, resume=True)


def stop_daemon(memory_dir: str = DEFAULT_MEMORY_DIR, reason: str = "manual") -> dict[str, Any]:
    with _lock:
        _stop_event.set()
        state = _read_state(memory_dir)
        state.update(
            {
                "state": "stopped",
                "desired_running": False,
                "resume_needed": False,
                "last_heartbeat_at": utc_now_iso(),
                "last_round_message": f"Local cumulative learner stopped: {reason}.",
            }
        )
        _write_state(_merge_runtime(state), memory_dir)
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2)
    return daemon_checkpoint(memory_dir, f"stop-{reason}")


if os.environ.get("ATANOR_AUTOSTART_DAEMON") == "1" or os.environ.get("HOMAGE_AUTOSTART_DAEMON") == "1":
    saved = _read_state(DEFAULT_MEMORY_DIR)
    if saved.get("desired_running"):
        start_daemon(DEFAULT_MEMORY_DIR, int(saved.get("interval_seconds") or DEFAULT_INTERVAL_SECONDS), resume=True)
