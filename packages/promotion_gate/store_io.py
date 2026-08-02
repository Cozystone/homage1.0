from __future__ import annotations

import json
from pathlib import Path
import hashlib
from typing import Any, Iterable


STORE_FILES = {
    "concept": "concepts.jsonl",
    "relation": "relations.jsonl",
    "evidence": "evidence.jsonl",
    "case_frame": "case_frames.jsonl",
}


def read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(payload)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def load_store_rows(store_path: Path | str, *, limit_per_kind: int | None = None) -> dict[str, list[dict[str, Any]]]:
    root = Path(store_path)
    return {kind: read_jsonl(root / filename, limit=limit_per_kind) for kind, filename in STORE_FILES.items()}


def read_manifest(store_path: Path | str) -> dict[str, Any]:
    """Read a store manifest without modifying the store."""

    path = Path(store_path) / "manifest.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def manifest_hash(store_path: Path | str) -> str:
    """Return the SHA256 of manifest.json, or an empty string when absent."""

    path = Path(store_path) / "manifest.json"
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def store_counts(store_path: Path | str) -> dict[str, int]:
    """Return manifest counts when available, falling back to bounded file counts."""

    manifest = read_manifest(store_path)
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    resolved: dict[str, int] = {}
    for kind, filename in STORE_FILES.items():
        manifest_key = f"{kind}s" if kind != "evidence" else "evidence"
        if kind == "case_frame":
            manifest_key = "case_frames"
        value = counts.get(manifest_key)
        if isinstance(value, int):
            resolved[kind] = value
            continue
        path = Path(store_path) / filename
        if not path.exists():
            resolved[kind] = 0
            continue
        with path.open("r", encoding="utf-8-sig") as handle:
            resolved[kind] = sum(1 for line in handle if line.strip())
    return resolved


def dedupe_key(row: dict[str, Any], fallback_fields: Iterable[str]) -> str:
    value = row.get("dedupe_key")
    if value:
        return str(value)
    for field in fallback_fields:
        if row.get(field):
            return str(row[field])
    return ""


def dedupe_keys(rows: list[dict[str, Any]], fallback_fields: Iterable[str]) -> set[str]:
    return {key for row in rows if (key := dedupe_key(row, fallback_fields))}
