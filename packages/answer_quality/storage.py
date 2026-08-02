from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path("data/answer_quality")
BENCHMARK_ROOT = ROOT / "benchmark_sets"
RUN_ROOT = ROOT / "runs"
REPORT_ROOT = ROOT / "reports"
FEEDBACK_ROOT = ROOT / "feedback"
PROOF_ROOT = ROOT / "proofs"
REPAIR_COMPARISON_ROOT = ROOT / "repair_comparisons"


def ensure_dirs() -> None:
    for path in (BENCHMARK_ROOT, RUN_ROOT, REPORT_ROOT, FEEDBACK_ROOT, PROOF_ROOT, REPAIR_COMPARISON_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def list_json_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
