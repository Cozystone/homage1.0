from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MEMORY_DIR = "data/memory"
DEFAULT_DB_NAME = "homage.db"


class AbstractVaultRepository(ABC):
    """Data-plane payload repository.

    Implementations must resolve only explicitly requested content hashes.
    They must never hydrate the full vault into memory at process boot.
    """

    @abstractmethod
    def resolve_payloads(self, hash_list: list[str], *, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError


def _memory_db_path(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> Path:
    path = Path(memory_dir)
    if path.suffix in {".db", ".sqlite", ".sqlite3"}:
        return path
    return path / DEFAULT_DB_NAME


def _connect_readonly(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> sqlite3.Connection | None:
    db_path = _memory_db_path(memory_dir)
    if not db_path.exists():
        return None
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return bool(row)


def _placeholders(values: Iterable[Any]) -> str:
    return ",".join("?" for _ in values)


class LocalFileSystemDriver(AbstractVaultRepository):
    """SQLite WAL-backed local Payload Vault driver."""

    def __init__(self, memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> None:
        self.memory_dir = memory_dir

    def resolve_payloads(self, hash_list: list[str], *, limit: int) -> list[dict[str, Any]]:
        keys = list(dict.fromkeys(hash_list))[: max(1, int(limit))]
        if not keys:
            return []
        conn = _connect_readonly(self.memory_dir)
        if not conn:
            return []
        try:
            if not _table_exists(conn, "payload_vault"):
                return []
            marks = _placeholders(keys)
            rows = conn.execute(
                f"""
                SELECT hash_key, raw_text, metadata_json
                FROM payload_vault
                WHERE hash_key IN ({marks})
                LIMIT ?
                """,
                (*keys, len(keys)),
            ).fetchall()
            by_hash = {str(row["hash_key"]): row for row in rows}
            resolved: list[dict[str, Any]] = []
            for key in keys:
                row = by_hash.get(key)
                if not row:
                    continue
                metadata = json.loads(str(row["metadata_json"] or "{}"))
                resolved.append(
                    {
                        "hash_key": key,
                        "raw_text": str(row["raw_text"] or ""),
                        "metadata": metadata,
                        "vault_driver": "local_sqlite_wal",
                    }
                )
            return resolved
        finally:
            conn.close()


class AmazonS3Driver(AbstractVaultRepository):
    """Future cloud-native Payload Vault driver.

    It is intentionally lazy: boto3 is imported only when AWS_MODE=true chooses
    this driver. Objects are expected to be JSON records keyed by hash.
    """

    def __init__(self, *, bucket: str | None = None, prefix: str | None = None) -> None:
        self.bucket = bucket or os.getenv("HOMAGE_S3_VAULT_BUCKET", "")
        self.prefix = (prefix or os.getenv("HOMAGE_S3_VAULT_PREFIX", "payload-vault")).strip("/")
        if not self.bucket:
            raise RuntimeError("AWS_MODE=true requires HOMAGE_S3_VAULT_BUCKET.")

    def resolve_payloads(self, hash_list: list[str], *, limit: int) -> list[dict[str, Any]]:
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("AmazonS3Driver requires boto3 in AWS_MODE.") from exc

        keys = list(dict.fromkeys(hash_list))[: max(1, int(limit))]
        client = boto3.client("s3")
        resolved: list[dict[str, Any]] = []
        for hash_key in keys:
            object_key = f"{self.prefix}/{hash_key}.json" if self.prefix else f"{hash_key}.json"
            try:
                response = client.get_object(Bucket=self.bucket, Key=object_key)
                raw = response["Body"].read().decode("utf-8")
                record = json.loads(raw)
            except Exception:
                continue
            resolved.append(
                {
                    "hash_key": hash_key,
                    "raw_text": str(record.get("raw_text") or record.get("text") or ""),
                    "metadata": dict(record.get("metadata") or {}),
                    "vault_driver": "amazon_s3",
                }
            )
        return resolved


def get_vault_repository(memory_dir: str | Path = DEFAULT_MEMORY_DIR) -> AbstractVaultRepository:
    if os.getenv("AWS_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return AmazonS3Driver()
    return LocalFileSystemDriver(memory_dir)
