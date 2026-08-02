from __future__ import annotations

import sqlite3

from app.services.crash_safety import enable_sqlite_crash_pragmas, shadow_backup_sqlite


def test_shadow_backup_sqlite_creates_recoverable_bak(tmp_path) -> None:
    db_path = tmp_path / "homage.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE memory(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO memory(key, value) VALUES ('node', 'safe')")
    conn.commit()
    conn.close()

    result = shadow_backup_sqlite(db_path)

    assert result.state == "completed"
    assert result.backup == str(db_path.with_name("homage.db.bak"))
    backup = sqlite3.connect(result.backup)
    try:
        row = backup.execute("SELECT value FROM memory WHERE key = 'node'").fetchone()
    finally:
        backup.close()
    assert row[0] == "safe"


def test_enable_sqlite_crash_pragmas_enables_wal(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "homage.db")
    try:
        enable_sqlite_crash_pragmas(conn)
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    finally:
        conn.close()

    assert journal_mode.lower() == "wal"
    assert synchronous == 1
