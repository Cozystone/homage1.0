"""Sharded on-disk term dictionary — removes the 1e9-term RAM wall.

The in-RAM TermDict holds every distinct string in a Python dict. At ~1e9 unique terms that
is ~50-100 GB of RAM — the measured next bottleneck after the columnar store itself. This
backend keeps the dictionary ON DISK in N sqlite shards, so resident memory is only a
bounded hot cache, while ids stay stable and reversible.

Design (coordination-free global ids):
  - term -> shard by hash(term) % N.
  - within a shard, sqlite assigns a local rowid (1, 2, 3...).
  - global id = (rowid - 1) * N + shard_index.   (bijective; no central counter)
  - id -> term: shard = id % N, rowid = id // N + 1 — a single primary-key lookup.

A bounded in-RAM cache absorbs the hot terms during ingest (predicates and common entities
repeat constantly), so most interns never touch disk. Honest trade-off: bulk ingest through
sqlite is slower than a pure RAM dict — that is the price of unbounded vocabulary; measure,
don't guess (benchmark lives in the tests/scripts).
"""
from __future__ import annotations

import sqlite3
import threading
import zlib
from pathlib import Path

_CACHE_CAP = 1_000_000     # bounded hot-term cache (strings + ints; ~100-200MB worst case)


def _shard_of(term: str, n: int) -> int:
    # stable across runs (Python's hash() is salted per process — unusable here)
    return zlib.crc32(term.encode("utf-8")) % n


class ShardedTermDict:
    """Disk-resident string<->int dictionary in N sqlite shards. API-compatible with the
    in-RAM TermDict (intern / term / __len__ / flush) so TripleStore can swap backends."""

    def __init__(
        self,
        root: str | Path,
        n_shards: int = 16,
        *,
        read_only: bool = False,
    ):
        self.root = Path(root)
        self.read_only = read_only is True
        if self.read_only:
            if not self.root.is_dir():
                raise FileNotFoundError(
                    "read-only sharded term dictionary does not exist"
                )
        else:
            self.root.mkdir(parents=True, exist_ok=True)
        self.n = n_shards
        # check_same_thread=False: the store is BUILT in one thread (boot/warmup/learner) but
        # READ from request-handler threads. Without this, every facts_about() from a request
        # thread raised sqlite3.ProgrammingError and the whole bulk world store silently returned

        # unreachable cross-thread). A single lock serializes access — the query path is read-only
        # and lookups are microseconds, so contention is negligible; correctness over nano-latency.
        self._lock = threading.Lock()
        self._conns: list[sqlite3.Connection] = []
        for i in range(n_shards):
            shard_path = self.root / f"terms_{i:02d}.db"
            if self.read_only:
                if not shard_path.is_file():
                    raise FileNotFoundError(
                        f"read-only term shard is missing: {shard_path.name}"
                    )
                uri = f"file:{shard_path.as_posix()}?mode=ro"
                conn = sqlite3.connect(
                    uri,
                    uri=True,
                    check_same_thread=False,
                )
                conn.execute("PRAGMA query_only=ON")
            else:
                conn = sqlite3.connect(
                    str(shard_path),
                    check_same_thread=False,
                )
                conn.execute("PRAGMA journal_mode=OFF")
                conn.execute("PRAGMA synchronous=OFF")   # bulk-load posture; flush() commits
                conn.execute("PRAGMA cache_size=-8000")  # 8MB page cache per shard
                conn.execute("CREATE TABLE IF NOT EXISTS t (term TEXT PRIMARY KEY)")
            self._conns.append(conn)
        self._cache: dict[str, int] = {}
        self._len = sum(c.execute("SELECT COUNT(*) FROM t").fetchone()[0] for c in self._conns)

    def intern(self, term: str) -> int:
        cached = self._cache.get(term)
        if cached is not None:
            return cached
        shard = _shard_of(term, self.n)
        conn = self._conns[shard]
        with self._lock:
            row = conn.execute("SELECT rowid FROM t WHERE term = ?", (term,)).fetchone()
            if row is None:
                if self.read_only:
                    raise PermissionError(
                        "canonical shipped term dictionary is read-only"
                    )
                cur = conn.execute("INSERT INTO t (term) VALUES (?)", (term,))
                rowid = cur.lastrowid
                self._len += 1
            else:
                rowid = row[0]
        gid = (rowid - 1) * self.n + shard
        if len(self._cache) >= _CACHE_CAP:
            self._cache.clear()                          # simple bounded reset, no LRU cost
        self._cache[term] = gid
        return gid

    def term(self, gid: int) -> str:
        if gid < 0:
            return ""
        shard, rowid = gid % self.n, gid // self.n + 1
        with self._lock:
            row = self._conns[shard].execute("SELECT term FROM t WHERE rowid = ?", (rowid,)).fetchone()
        return row[0] if row else ""

    def lookup(self, term: str) -> int | None:
        """id for an existing term without creating it (query path)."""
        cached = self._cache.get(term)
        if cached is not None:
            return cached
        shard = _shard_of(term, self.n)
        with self._lock:
            row = self._conns[shard].execute("SELECT rowid FROM t WHERE term = ?", (term,)).fetchone()
        return (row[0] - 1) * self.n + shard if row else None

    def __len__(self) -> int:
        return self._len

    def flush(self) -> None:
        if self.read_only:
            return
        for conn in self._conns:
            conn.commit()

    def close(self) -> None:
        if not self.read_only:
            self.flush()
        for conn in self._conns:
            conn.close()
