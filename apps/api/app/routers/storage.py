from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter


router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("/cleanup-plan")
def cleanup_plan() -> dict[str, Any]:
    safe_targets = [
        ("logs", Path("logs")),
        ("generated proof files", Path("data") / "surface_brain" / "proofs"),
        ("old reset backups", Path("data") / "backups"),
        ("browser screenshots", Path("data") / "screenshots"),
        ("temporary build cache", Path("apps") / "web" / ".next" / "cache"),
    ]
    estimated_reclaim_gb = sum(_directory_size_gb(path) for _, path in safe_targets if path.exists())
    return {
        "safe_to_delete": [label for label, _ in safe_targets],
        "requires_compaction": [
            "semantic_growth_shards",
            "cloud_brain proof store",
            "memory events",
        ],
        "must_not_delete": [
            "payload vault",
            "local memory db",
            "verified fragment store",
            "checkpoints",
        ],
        "estimated_reclaim_gb": round(estimated_reclaim_gb, 3),
        "policy": {
            "auto_delete": False,
            "operator_approval_required": True,
            "private_data_protected": True,
        },
    }


def _directory_size_gb(path: Path) -> float:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except OSError:
        return 0.0
    return total / (1024**3)
