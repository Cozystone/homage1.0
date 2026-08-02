from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neuro_efficiency.hardware_adapter import build_runtime_config, prime_runtime_config
from neuro_efficiency.stability import build_sustained_run_plan


def build_hardware_benchmark(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Measure the host enough to tune ATANOR Alpha workload knobs.

    This is intentionally a short startup probe, not a stress benchmark. It
    reads stable hardware facts, runs small CPU/disk probes when requested, and
    converts the result into ontology and training limits that keep the machine
    responsive during long runs.
    """

    payload = profile or {}
    run_probes = bool(payload.get("run_probes", True))
    hardware = _collect_hardware_snapshot(payload.get("hardware_profile"))
    probes = _run_quick_probes(run_probes)
    recommendation = _recommend_profile(hardware, probes)
    runtime_profile = {
        "ram_gb": hardware.get("ram_gb"),
        "vram_gb": hardware.get("vram_gb"),
        "gpu_name": hardware.get("gpu"),
        "ram_available_gb": hardware.get("ram_available_gb"),
        "ram_os_overhead_gb": hardware.get("ram_os_overhead_gb"),
        "vram_available_gb": hardware.get("vram_available_gb"),
        "vram_used_gb": hardware.get("vram_used_gb"),
        "cpu_ops_per_ms": probes.get("cpu_indexing_ops_per_ms"),
        "viewport_10k_frame_ms": probes.get("viewport_10k_frame_ms"),
    }
    elastic_runtime = prime_runtime_config(runtime_profile)
    stability = build_sustained_run_plan(
        {
            "hardware_profile": recommendation["hardware_profile"],
            **recommendation["stability_payload"],
        }
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "local-hardware-probe",
        "can_read_local_hardware": True,
        "profile_name": recommendation["profile_name"],
        "confidence": recommendation["confidence"],
        "hardware_profile": recommendation["hardware_profile"],
        "probes": probes,
        "execution_tier": recommendation["execution_tier"],
        "execution_tier_label": recommendation["execution_tier_label"],
        "max_chunk_nodes": recommendation["max_chunk_nodes"],
        "continuous_threading_enabled": recommendation["continuous_threading_enabled"],
        "heavy_edge_mesh_enabled": recommendation["heavy_edge_mesh_enabled"],
        "recommended_learning_volume": recommendation["learning_volume"],
        "recommended_stability_payload": recommendation["stability_payload"],
        "ontology_tuning": {
            "datagate_batch_docs": stability["queue_policy"]["datagate_batch_docs"],
            "ontology_delta_chunks": stability["queue_policy"]["ontology_delta_chunks"],
            "node_write_batch": stability["queue_policy"]["node_write_batch"],
            "edge_write_batch": stability["queue_policy"]["edge_write_batch"],
            "hot_window_nodes": stability["graph_policy"]["hot_window_nodes"],
            "hot_window_edges": stability["graph_policy"]["hot_window_edges"],
            "ui_render_nodes": stability["graph_policy"]["ui_render_nodes"],
            "storage_model": stability["graph_policy"]["storage_model"],
        },
        "training_tuning": {
            "precision": recommendation["precision"],
            "microbatch_tokens": recommendation["microbatch_tokens"],
            "gradient_accumulation": recommendation["gradient_accumulation"],
            "rag_query_concurrency": stability["queue_policy"]["rag_query_concurrency"],
            "checkpoint_interval_minutes": stability["checkpoint_policy"]["training_checkpoint_interval_minutes"],
            "checkpoint_keep_last": stability["checkpoint_policy"]["checkpoint_keep_last"],
        },
        "runtime_envelope": stability["runtime_envelope"],
        "elastic_runtime": elastic_runtime.as_dict(),
        "backpressure_policy": stability["backpressure_policy"],
        "adjustment_policy": {
            "auto_apply_when_source": "local-hardware-probe",
            "reason": recommendation["reason"],
            "rerun_trigger": "operator request or hardware profile change",
        },
    }


def _collect_hardware_snapshot(override: Any = None) -> dict[str, Any]:
    disk = shutil.disk_usage(".")
    ram = _read_ram_snapshot()
    snapshot: dict[str, Any] = {
        "cpu": platform.processor() or platform.machine() or "Unknown CPU",
        "cpu_logical": os.cpu_count() or 1,
        "cpu_physical": None,
        "ram_gb": ram.get("ram_gb"),
        "ram_available_gb": ram.get("ram_available_gb"),
        "ram_os_overhead_gb": ram.get("ram_os_overhead_gb"),
        "gpu": "Unavailable",
        "vram_gb": 0,
        "vram_available_gb": None,
        "vram_used_gb": None,
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "platform": platform.platform(),
    }
    snapshot.update(_read_gpu_snapshot())
    if isinstance(override, dict):
        snapshot.update(override)
    if not snapshot.get("ram_gb"):
        snapshot["ram_gb"] = 16
    snapshot["ram_gb"] = _normalize_capacity(_float(snapshot.get("ram_gb"), 16))
    if snapshot.get("vram_gb") is not None:
        snapshot["vram_gb"] = _normalize_capacity(_float(snapshot.get("vram_gb"), 0))
    return snapshot


def _normalize_capacity(value: float) -> float:
    if 15.5 <= value < 16:
        return 16.0
    if 31.0 <= value < 32:
        return 32.0
    if 63.0 <= value < 64:
        return 64.0
    return round(value, 2)


def _read_ram_snapshot() -> dict[str, float | None]:
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        total = round(memory.total / (1024**3), 2)
        available = round(memory.available / (1024**3), 2)
        return {
            "ram_gb": _normalize_capacity(total),
            "ram_available_gb": available,
            "ram_os_overhead_gb": round(max(0.0, total - available), 2),
        }
    except Exception:
        return {"ram_gb": None, "ram_available_gb": None, "ram_os_overhead_gb": None}


def _read_gpu_snapshot() -> dict[str, Any]:
    command = shutil.which("nvidia-smi")
    if not command:
        return {}
    try:
        output = subprocess.check_output(
            [
                command,
                "--query-gpu=name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        ).strip().splitlines()[0]
        name, mem_total, mem_used, mem_free = [part.strip() for part in output.split(",", 3)]
        return {
            "gpu": name,
            "vram_gb": _normalize_capacity(round(float(mem_total) / 1024, 2)),
            "vram_used_gb": round(float(mem_used) / 1024, 2),
            "vram_available_gb": round(float(mem_free) / 1024, 2),
        }
    except Exception:
        return {}


def _run_quick_probes(run_probes: bool) -> dict[str, Any]:
    if not run_probes:
        return {
            "ran": False,
            "cpu_loop_score": None,
            "cpu_indexing_ops_per_ms": None,
            "viewport_10k_frame_ms": None,
            "disk_write_mb_s": None,
            "duration_ms": 0,
            "notes": ["probe skipped by request"],
        }

    start = time.perf_counter()
    cpu_probe = _cpu_indexing_probe(seconds=1.0)
    viewport_frame_ms = _viewport_10k_frame_probe()
    disk_score = _disk_write_score()
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "ran": True,
        "cpu_loop_score": int(cpu_probe["ops_per_second"]),
        "cpu_indexing_ops_per_ms": cpu_probe["ops_per_ms"],
        "viewport_10k_frame_ms": viewport_frame_ms,
        "disk_write_mb_s": disk_score,
        "duration_ms": duration_ms,
        "notes": ["forza-style 1s dry-run indexing probe; backend instanced viewport proxy; not a thermal stress test"],
    }


def _cpu_indexing_probe(seconds: float = 1.0) -> dict[str, float]:
    start = time.perf_counter()
    deadline = start + max(0.1, seconds)
    value = 0x345678
    iterations = 0
    while time.perf_counter() < deadline:
        for index in range(2048):
            value = ((value * 1_664_525) + index + 1_013_904_223) & 0xFFFFFFFF
            value ^= value >> 13
        iterations += 2048
    elapsed = max(0.001, time.perf_counter() - start)
    return {
        "ops_per_second": round(iterations / elapsed, 2),
        "ops_per_ms": round(iterations / elapsed / 1000, 3),
        "checksum": float(value & 0xFFFF),
    }


def _viewport_10k_frame_probe() -> float:
    """CPU-side proxy for updating 10k instanced matrices/colors in one frame."""

    count = 10_000
    positions = [0.0] * (count * 3)
    colors = [0.0] * (count * 3)
    start = time.perf_counter()
    for index in range(count):
        base = index * 3
        phase = (index % 997) / 997
        positions[base] = phase * 2.0 - 1.0
        positions[base + 1] = ((index * 17) % 991) / 991 - 0.5
        positions[base + 2] = ((index * 31) % 983) / 983 - 0.5
        colors[base] = 1.0 if index % 23 == 0 else 0.16
        colors[base + 1] = 0.33 if index % 23 == 0 else 0.16
        colors[base + 2] = 0.0 if index % 23 == 0 else 0.16
    elapsed = max(0.001, time.perf_counter() - start)
    return round(elapsed * 1000, 3)


def _disk_write_score() -> float | None:
    block = b"homage-benchmark\n" * 4096
    target_mb = 8
    try:
        with tempfile.NamedTemporaryFile(prefix="homage-bench-", suffix=".bin", dir=Path("."), delete=False) as handle:
            path = Path(handle.name)
            start = time.perf_counter()
            for _ in range(max(1, int((target_mb * 1024 * 1024) / len(block)))):
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
            elapsed = max(0.001, time.perf_counter() - start)
        path.unlink(missing_ok=True)
        return round(target_mb / elapsed, 1)
    except Exception:
        return None


def _recommend_profile(hardware: dict[str, Any], probes: dict[str, Any]) -> dict[str, Any]:
    ram_gb = _float(hardware.get("ram_gb"), 16)
    vram_gb = _float(hardware.get("vram_gb"), 0)
    cpu_logical = _int(hardware.get("cpu_logical"), 4)
    disk_free_gb = _float(hardware.get("disk_free_gb"), 0)
    cpu_ops_per_ms = _float(probes.get("cpu_indexing_ops_per_ms"), 0)
    disk_score = _float(probes.get("disk_write_mb_s"), 0)
    runtime = build_runtime_config(
        {
            "ram_gb": ram_gb,
            "vram_gb": vram_gb,
            "gpu_name": hardware.get("gpu"),
            "ram_available_gb": hardware.get("ram_available_gb"),
            "ram_os_overhead_gb": hardware.get("ram_os_overhead_gb"),
            "vram_available_gb": hardware.get("vram_available_gb"),
            "vram_used_gb": hardware.get("vram_used_gb"),
            "cpu_ops_per_ms": cpu_ops_per_ms or None,
            "viewport_10k_frame_ms": probes.get("viewport_10k_frame_ms"),
        }
    )

    if runtime.tier in {"tier_s", "tier_1_m"}:
        volume = "max"
        payload = {"target_nodes": 500_000, "target_edges": 2_400_000, "duration_hours": 168}
        microbatch_tokens = 1536 if runtime.tier == "tier_s" else 1280
        accumulation = 8
        profile_name = runtime.tier_label
    elif runtime.tier == "tier_1_s":
        volume = "deep"
        payload = {"target_nodes": 120_000, "target_edges": 480_000, "duration_hours": 168}
        microbatch_tokens = 1024
        accumulation = 8
        profile_name = runtime.tier_label
    elif runtime.tier == "tier_2_a":
        volume = "standard"
        payload = {"target_nodes": 50_000, "target_edges": 200_000, "duration_hours": 72}
        microbatch_tokens = 512
        accumulation = 4
        profile_name = runtime.tier_label
    elif runtime.tier == "tier_2_e":
        volume = "standard"
        payload = {"target_nodes": 20_000, "target_edges": 80_000, "duration_hours": 72}
        microbatch_tokens = 384
        accumulation = 3
        profile_name = runtime.tier_label
    else:
        volume = "lite"
        payload = {"target_nodes": 3_000, "target_edges": 9_000, "duration_hours": 12}
        microbatch_tokens = 256
        accumulation = 2
        profile_name = runtime.tier_label

    precision = "bf16-preferred" if vram_gb >= 12 else "fp16-lite" if vram_gb >= 8 else "int8-cpu-safe"
    confidence = "high" if hardware.get("ram_gb") and probes.get("ran") else "medium"
    reason = (
        f"{runtime.tier_label}: RAM {ram_gb}GB, VRAM {vram_gb}GB, "
        f"available RAM {hardware.get('ram_available_gb') or 'n/a'}GB, "
        f"available VRAM {hardware.get('vram_available_gb') or 'n/a'}GB, "
        f"CPU ops/ms {cpu_ops_per_ms or 'n/a'}, disk {disk_score or 'n/a'} MB/s"
    )
    return {
        "profile_name": profile_name,
        "confidence": confidence,
        "execution_tier": runtime.tier,
        "execution_tier_label": runtime.tier_label,
        "max_chunk_nodes": runtime.max_chunk_nodes,
        "continuous_threading_enabled": runtime.continuous_threading_enabled,
        "heavy_edge_mesh_enabled": runtime.heavy_edge_mesh_enabled,
        "learning_volume": volume,
        "stability_payload": payload,
        "hardware_profile": {
            "cpu": hardware.get("cpu") or "Unknown CPU",
            "gpu": hardware.get("gpu") or "Unavailable",
            "vram_gb": vram_gb,
            "vram_available_gb": _float(hardware.get("vram_available_gb"), 0),
            "vram_used_gb": _float(hardware.get("vram_used_gb"), 0),
            "ram_gb": ram_gb,
            "ram_available_gb": _float(hardware.get("ram_available_gb"), 0),
            "ram_os_overhead_gb": _float(hardware.get("ram_os_overhead_gb"), 0),
            "storage": hardware.get("storage") or "Local workspace disk",
            "storage_gb": _float(hardware.get("storage_gb") or hardware.get("disk_total_gb"), 1000),
            "cpu_logical": cpu_logical,
            "disk_free_gb": disk_free_gb,
            "platform": hardware.get("platform"),
        },
        "precision": precision,
        "microbatch_tokens": microbatch_tokens,
        "gradient_accumulation": accumulation,
        "reason": reason,
    }


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
