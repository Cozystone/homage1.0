from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


SQLITE_HEADER = b"SQLite format 3\x00"


@dataclass(frozen=True)
class ShadowBackupResult:
    source: str
    backup: str | None
    state: str
    error: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def enable_sqlite_crash_pragmas(conn: sqlite3.Connection) -> None:
    """Apply crash-resilient SQLite settings immediately after connect."""

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")


def _is_sqlite_header(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def shadow_backup_sqlite(db_path: str | Path, *, backup_path: str | Path | None = None) -> ShadowBackupResult:
    """Create a consistent `.bak` snapshot if the SQLite file currently exists."""

    source = Path(db_path)
    if not source.exists():
        return ShadowBackupResult(source=str(source), backup=None, state="skipped_missing")
    if not source.is_file():
        return ShadowBackupResult(source=str(source), backup=None, state="skipped_not_file")

    backup = Path(backup_path) if backup_path else source.with_name(f"{source.name}.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    temp = backup.with_name(f"{backup.name}.tmp-{os.getpid()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}")

    try:
        source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
        src_conn = sqlite3.connect(source_uri, uri=True, timeout=5.0)
        dst_conn = sqlite3.connect(temp, timeout=5.0)
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
            src_conn.close()
        temp.replace(backup)
        return ShadowBackupResult(source=str(source), backup=str(backup), state="completed")
    except Exception as exc:
        try:
            if _is_sqlite_header(source):
                shutil.copy2(source, temp)
                temp.replace(backup)
                return ShadowBackupResult(
                    source=str(source),
                    backup=str(backup),
                    state="completed_byte_copy_fallback",
                    error=str(exc),
                )
        except Exception as fallback_exc:
            return ShadowBackupResult(
                source=str(source),
                backup=str(backup),
                state="failed",
                error=f"{exc}; fallback={fallback_exc}",
            )
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
        return ShadowBackupResult(source=str(source), backup=str(backup), state="failed", error=str(exc))


def create_boot_shadow_backups(extra_paths: Iterable[str | Path] | None = None) -> list[dict[str, str | None]]:
    """Snapshot known durable SQLite files during FastAPI startup."""

    candidates: list[Path] = []
    try:
        from app.services.database import homage_memory_db_path

        candidates.append(homage_memory_db_path())
    except Exception:
        pass

    candidates.extend(
        [
            Path("data/memory/homage.db"),
            Path("data/memory/canonical_concepts.sqlite3"),
            Path("data/memory/homage_memory.sqlite3"),
        ]
    )
    if extra_paths:
        candidates.extend(Path(path) for path in extra_paths)

    seen: set[str] = set()
    results: list[dict[str, str | None]] = []
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        results.append(shadow_backup_sqlite(candidate).to_dict())
    return results
