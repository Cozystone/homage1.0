from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_CORTEX_ROOT = Path("data/cortex_g2")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_cortex_dirs(root: str | Path = DEFAULT_CORTEX_ROOT) -> Path:
    base = Path(root)
    (base / "crystals").mkdir(parents=True, exist_ok=True)
    (base / "proofs").mkdir(parents=True, exist_ok=True)
    return base


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: str | Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return default or {}
    return json.loads(target.read_text(encoding="utf-8"))


def append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path, limit: int = 100) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def bounded_float(value: Any, default: float = 0.0, *, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))
