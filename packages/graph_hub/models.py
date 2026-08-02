from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_HUB_ROOT = PROJECT_ROOT / "data" / "graph_hub"
CATALOG_PATH = GRAPH_HUB_ROOT / "catalog" / "sample_graph_hub_catalog.json"
AUDIT_PATH = GRAPH_HUB_ROOT / "audit" / "graph_hub_audit.jsonl"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_after_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_graph_hub_dirs() -> None:
    for name in [
        "catalog",
        "cartridges",
        "exported",
        "installed",
        "entitlements",
        "attachments",
        "sandbox",
        "audit",
        "proofs",
    ]:
        (GRAPH_HUB_ROOT / name).mkdir(parents=True, exist_ok=True)


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:18]}"


def checksum_payload(payload: dict[str, Any]) -> str:
    clone = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    clone.get("metadata", {}).pop("checksum", None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cartridge_path(cartridge_id: str, folder: str = "cartridges") -> Path:
    return GRAPH_HUB_ROOT / folder / f"{cartridge_id}.graphpack.json"
