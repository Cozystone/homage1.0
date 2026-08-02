from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DEFAULT_HARDWARE = {
    "cpu": "AMD Ryzen 9 9950X3D",
    "gpu": "ZOTAC GAMING GeForce RTX 5080 AMP EXTREME INFINITY",
    "vram_gb": 16,
    "motherboard": "ASUS ROG CROSSHAIR X870E HERO",
    "ram_gb": 32,
    "storage": "GIGABYTE AORUS Gen4 7300 V2",
    "storage_gb": 1000,
    "psu": "SuperFlower SF-1200F14XP LEADEX VII PRO PLATINUM ATX 3.1",
    "cooler": "CoolerMaster MASTERLIQUID 360 ATMOS",
    "case": "Antec FLUX MESH BTF Black",
}


def build_sustained_run_plan(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plan long-running ATANOR jobs for one high-end desktop box.

    The plan intentionally treats RAM, VRAM, and graph write amplification as
    hard constraints. CPU/GPU throughput can be high on the target hardware, but
    long-running ontology growth fails first when queues, full-graph JSON loads,
    or rendering are allowed to grow without backpressure.
    """

    payload = profile or {}
    hardware = DEFAULT_HARDWARE | dict(payload.get("hardware_profile") or {})
    ram_gb = _bounded_float(hardware.get("ram_gb"), default=32, minimum=8, maximum=512)
    vram_gb = _bounded_float(hardware.get("vram_gb"), default=16, minimum=4, maximum=192)
    storage_gb = _bounded_float(hardware.get("storage_gb"), default=1000, minimum=128, maximum=16_000)
    disk_free_gb = _bounded_float(
        hardware.get("disk_free_gb", payload.get("disk_free_gb")),
        default=storage_gb,
        minimum=0,
        maximum=storage_gb,
    )
    target_nodes = _bounded_int(payload.get("target_nodes"), default=10_000, minimum=1_000, maximum=500_000)
    target_edges = _bounded_int(payload.get("target_edges"), default=max(30_000, target_nodes * 4), minimum=2_000, maximum=3_000_000)
    duration_hours = _bounded_int(payload.get("duration_hours"), default=72, minimum=1, maximum=720)

    ram_soft = round(ram_gb * 0.72, 1)
    ram_hard = round(ram_gb * 0.86, 1)
    vram_soft = round(vram_gb * 0.74, 1)
    vram_hard = round(vram_gb * 0.9, 1)
    storage_reserve = round(max(120, storage_gb * 0.2), 1)
    graph_budget_gb = round(max(80, storage_gb - storage_reserve - 120), 1)
    disk_budget = build_disk_budget_state(
        disk_total_gb=storage_gb,
        disk_free_gb=disk_free_gb,
        desired_reserve_gb=storage_reserve,
        current_growth_budget_gb=min(graph_budget_gb, max(0.0, disk_free_gb - 20.0)),
        projected_growth_gb=min(graph_budget_gb, max(1.0, target_edges / 1_000_000 * 0.35)),
    )
    disk_status = str(disk_budget["status"])
    if disk_status == "critical":
        node_write_batch = 0
        edge_write_batch = 0
    elif disk_status == "constrained":
        node_write_batch = 200
        edge_write_batch = 800
    elif disk_status == "caution":
        node_write_batch = 500
        edge_write_batch = 1_500
    else:
        node_write_batch = 500
        edge_write_batch = 2_000

    hot_window_nodes = min(max(2_048, target_nodes // 10), 24_000)
    hot_window_edges = min(max(12_000, hot_window_nodes * 8), 240_000)
    render_nodes = min(2_000, max(240, hot_window_nodes // 8))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_name": "ATANOR Sustained Learning Profile",
        "hardware_profile": hardware,
        "target_workload": {
            "duration_hours": duration_hours,
            "target_nodes": target_nodes,
            "target_edges": target_edges,
            "expected_relation_density": round(target_edges / max(1, target_nodes), 2),
        },
        "runtime_envelope": {
            "ram_soft_gb": ram_soft,
            "ram_hard_gb": ram_hard,
            "vram_soft_gb": vram_soft,
            "vram_hard_gb": vram_hard,
            "storage_reserve_gb": storage_reserve,
            "graph_store_budget_gb": graph_budget_gb,
            "disk_budget": disk_budget,
            "checkpoint_ring_gb": round(min(160, max(48, storage_gb * 0.08)), 1),
            "thermal_policy": {
                "gpu_action": "pause training batches before VRAM pressure; keep graph writes on CPU",
                "cpu_action": "throttle harvest and ontology extraction before sustained thermal saturation",
            },
        },
        "queue_policy": {
            "harvest_pending_cap": min(4_096, max(512, target_nodes // 4)),
            "datagate_batch_docs": 64 if ram_gb < 64 else 128,
            "ontology_delta_chunks": 256 if ram_gb < 64 else 512,
            "node_write_batch": node_write_batch,
            "edge_write_batch": edge_write_batch,
            "rag_query_concurrency": 2,
            "training_microbatch_policy": "bf16/8-bit where safe, gradient accumulation, activation checkpointing, never full-corpus in VRAM",
        },
        "graph_policy": {
            "storage_model": "append-only graph event log + SQLite WAL hot index + periodic compacted snapshots",
            "identity_model": "stable normalized node ids; merge duplicate labels before writing edges",
            "edge_model": "one edge row per typed relation with evidence_count, confidence, status, and last_seen_at",
            "hot_window_nodes": hot_window_nodes,
            "hot_window_edges": hot_window_edges,
            "ui_render_nodes": render_nodes,
            "ui_render_strategy": "LOD sampling: render active frontier, top-confidence anchors, and community summaries only",
            "compaction_trigger": {
                "event_log_mb": 512,
                "edge_duplication_ratio": 1.35,
                "ram_soft_gb": ram_soft,
            },
        },
        "checkpoint_policy": {
            "run_state_interval_minutes": 5,
            "ontology_snapshot_interval_minutes": 20,
            "training_checkpoint_interval_minutes": 15,
            "checkpoint_keep_last": 8,
            "resume_contract": "all stages are idempotent by run_id, document_id, chunk_id, node_id, and edge key",
        },
        "backpressure_policy": [
            {
                "condition": "RAM >= soft watermark",
                "action": "pause harvest, flush ontology batches, compact hot graph window, keep RAG read-only",
            },
            {
                "condition": "VRAM >= soft watermark",
                "action": "pause ATANOR Oven batches, keep DataGate/Ontology on CPU, lower microbatch size",
            },
            {
                "condition": "graph writer lag > 2 batches",
                "action": "stop creating new relations; only merge known nodes until writer catches up",
            },
            {
                "condition": "disk free < hard minimum",
                "action": "pause growth, keep graph read-only, allow checkpoint, require operator review",
            },
            {
                "condition": "disk free < soft minimum",
                "action": "slow growth, recommend compaction, prevent new large ingestion",
            },
            {
                "condition": "disk free < desired large-growth reserve",
                "action": "normal UI allowed; run large Cloud Brain growth in conservative mode",
            },
        ],
        "implementation_notes": [
            "Do not keep nodes.json/edges.json as the source of truth once the graph exceeds Alpha scale.",
            "Use JSON exports only as snapshots; the live ontology must be event-sourced and paginated.",
            "Training should consume sampled context bundles, not the full ontology graph.",
            "The UI should never render every node; thousands of nodes require LOD and search-first navigation.",
        ],
    }


def build_disk_budget_state(
    *,
    disk_total_gb: float,
    disk_free_gb: float,
    hard_min_free_gb: float | None = None,
    soft_min_free_gb: float | None = None,
    desired_reserve_gb: float | None = None,
    current_growth_budget_gb: float | None = None,
    projected_growth_gb: float | None = None,
) -> dict[str, Any]:
    """Classify disk pressure without treating desired reserve as a hard failure.

    The desired reserve is a planning target for large graph growth. The hard
    and soft minima are the actual safety gates that protect the local store.
    """

    total = max(1.0, float(disk_total_gb))
    free = max(0.0, min(float(disk_free_gb), total))
    hard_min = round(float(hard_min_free_gb) if hard_min_free_gb is not None else min(20.0, max(10.0, total * 0.02)), 1)
    soft_min = round(float(soft_min_free_gb) if soft_min_free_gb is not None else min(50.0, max(30.0, total * 0.05)), 1)
    desired = round(float(desired_reserve_gb) if desired_reserve_gb is not None else max(120.0, total * 0.2), 1)
    current_budget = round(
        max(0.0, float(current_growth_budget_gb) if current_growth_budget_gb is not None else max(0.0, free - soft_min)),
        1,
    )
    projected = None if projected_growth_gb is None else round(max(0.0, float(projected_growth_gb)), 1)

    if free < hard_min:
        status = "critical"
        action = "pause_growth"
        message = f"Disk free: {free:.1f}GB. Growth is paused to protect the local store."
    elif free < soft_min:
        status = "constrained"
        action = "compact"
        message = f"Disk free: {free:.1f}GB. Growth is slowed and compaction is recommended."
    elif free < desired:
        status = "caution"
        action = "slow_growth"
        message = (
            f"Disk free: {free:.1f}GB. Normal operation is safe. "
            "Large Cloud Brain growth reserve is not met, so growth runs in conservative mode."
        )
    else:
        status = "safe"
        action = "normal"
        message = f"Disk free: {free:.1f}GB. Normal operation and selected growth mode are within budget."

    return {
        "disk_total_gb": round(total, 1),
        "disk_free_gb": round(free, 1),
        "hard_min_free_gb": hard_min,
        "soft_min_free_gb": soft_min,
        "desired_reserve_gb": desired,
        "current_growth_budget_gb": current_budget,
        "projected_growth_gb": projected,
        "status": status,
        "action": action,
        "message": message,
    }


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
