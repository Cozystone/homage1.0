from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SURFACE_ROOT = Path("data/surface_brain")
CLOUD_ROOT = Path("data/cloud_brain")


def ensure_dirs() -> None:
    for path in (
        CLOUD_ROOT / "semantic",
        CLOUD_ROOT / "surface",
        CLOUD_ROOT / "dual_projection_runs",
        SURFACE_ROOT / "proofs",
        SURFACE_ROOT / "traces",
        SURFACE_ROOT / "repair_candidates",
        SURFACE_ROOT / "repair_runs",
        SURFACE_ROOT / "review_queue",
        SURFACE_ROOT / "production_rules",
        SURFACE_ROOT / "rule_audit",
        SURFACE_ROOT / "rejected_rules",
        SURFACE_ROOT / "archived_rules",
    ):
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


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
