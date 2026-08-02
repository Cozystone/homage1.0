from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from app.services.crash_safety import enable_sqlite_crash_pragmas
from app.services.desktop_paths import configure_desktop_data_dir, resolve_data_path


def homage_memory_db_path() -> Path:
    """Resolve the desktop-safe SQLite path.

    The install directory must be treated as read-only/replaceable because
    Tauri updates can overwrite it. All durable state lives under the OS
    application data directory or the explicit ATANOR_DATA_DIR/HOMAGE_DATA_DIR override.
    """

    root = configure_desktop_data_dir(os.getenv("ATANOR_DATA_DIR", os.getenv("HOMAGE_DATA_DIR")), chdir=False)
    return root / "data" / "memory" / "homage_memory.sqlite3"


def connect_homage_memory() -> sqlite3.Connection:
    path = homage_memory_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    enable_sqlite_crash_pragmas(conn)
    return conn


def resolve_appdata_file(*parts: str) -> Path:
    return resolve_data_path(*parts)
