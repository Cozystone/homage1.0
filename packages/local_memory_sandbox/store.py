from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


COLLECTIONS = (
    "preferences",
    "personal_facts",
    "project_context",
    "corrections",
    "task_goals",
    "relationships",
    "sensitive_hold",
)

REAL_LOCAL_BRAIN_MARKERS = (
    "data/memory",
    "data\\memory",
    "homage.db",
    "homage_memory.sqlite3",
    "canonical_concepts.sqlite3",
)


def _resolved(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def is_safe_sandbox_path(path: Path | str) -> bool:
    resolved = _resolved(path)
    text = str(resolved).lower()
    if any(marker in text for marker in REAL_LOCAL_BRAIN_MARKERS):
        return False
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved.relative_to(temp_root)
        return True
    except ValueError:
        return "local_memory_sandbox" in text or "atanor_local_memory_sandbox" in text


def ensure_sandbox_path(path: Path | str) -> Path:
    resolved = _resolved(path)
    if not is_safe_sandbox_path(resolved):
        raise ValueError(f"refusing non-sandbox Local Brain path: {resolved}")
    return resolved


def list_collections(path: Path | str) -> list[str]:
    ensure_sandbox_path(path)
    return list(COLLECTIONS)


def init_sandbox_store(path: Path | str) -> Path:
    root = ensure_sandbox_path(path)
    root.mkdir(parents=True, exist_ok=True)
    for collection in COLLECTIONS:
        target = root / f"{collection}.json"
        if not target.exists():
            target.write_text("[]\n", encoding="utf-8")
    return root


def _collection_path(path: Path | str, collection: str) -> Path:
    if collection not in COLLECTIONS:
        raise ValueError(f"unknown sandbox collection: {collection}")
    return ensure_sandbox_path(path) / f"{collection}.json"


def read_collection(path: Path | str, collection: str) -> list[dict[str, Any]]:
    init_sandbox_store(path)
    payload = json.loads(_collection_path(path, collection).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{collection} is not a JSON list")
    return [dict(item) for item in payload if isinstance(item, dict)]


def _reject_raw_sensitive_or_voice(item: dict[str, Any]) -> None:
    sensitivity = str(item.get("sensitivity") or "")
    source_type = str(item.get("source_type") or "")
    raw_text = str(item.get("raw_text") or item.get("raw_transcript") or "")
    summary = str(item.get("normalized_summary") or item.get("summary") or "")
    if sensitivity in {"sensitive", "secret"} and raw_text:
        raise ValueError("raw sensitive text cannot be written to sandbox store")
    if source_type == "voice_transcript" and raw_text:
        raise ValueError("raw voice transcript cannot be written to sandbox store")
    if "voice transcript:" in summary.lower():
        raise ValueError("raw voice transcript marker cannot be written to sandbox store")


def write_collection(path: Path | str, collection: str, item: dict[str, Any]) -> None:
    init_sandbox_store(path)
    _reject_raw_sensitive_or_voice(item)
    target = _collection_path(path, collection)
    payload = read_collection(path, collection)
    payload.append(dict(item))
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def compute_store_hash(path: Path | str) -> str:
    root = init_sandbox_store(path)
    digest = hashlib.sha256()
    for collection in COLLECTIONS:
        target = root / f"{collection}.json"
        digest.update(collection.encode("utf-8"))
        digest.update(b"\0")
        digest.update(target.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
