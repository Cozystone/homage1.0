"""Integer-columnar triple store — the high-performance, high-quality substrate for a
graph that can actually grow toward trillion scale.

Why the current path can't scale (measured 2026-07-05): the continuous learner crawls the
web one sentence at a time (~1 sentence/sec), runs an expensive NL decomposition per
sentence, and appends JSON text rows. That is ~1.3 concepts/MINUTE. Reaching 1e12 nodes at
that rate would take ~1.4 BILLION days. You cannot CRAWL to a trillion.

The physics of the fix (this module):
  1. QUALITY comes from the SOURCE, not from more scraping. Curated structured knowledge
     graphs are ALREADY (subject, predicate, object) triples, human-verified: Wikidata
     (~1.5e9 statements, CC0), ConceptNet (~3.4e7 edges), DBpedia. Ingesting those skips
     the noisy web extraction AND the per-sentence NL decomposition entirely.
  2. PERFORMANCE comes from representation. A triple store keeps a TERM DICTIONARY
     (string <-> int32/int64 id) and three parallel INTEGER columns (s, p, o). A fact is
     then 12 bytes (3x int32), not a ~200-byte JSON line — ~16x smaller, and ingest is an
     array append, not JSON serialisation + a gate. This is the standard large-KG
     compression (HDT / RDF term dictionaries).
  3. BOUNDED MEMORY: columns are flushed to disk in chunks and memmapped on open (AirLLM's
     principle, already used by splatra_turbovec.node_store) — resident RAM is only the
     pages actually touched, so a 1e9-row store opens without loading 12 GB.

Honesty: this stores CURATED triples verbatim with provenance; it never invents a fact.
Trillion on ONE machine is still not free — the term dictionary and derived-edge inference
are the next bottlenecks, and 1e12 genuinely needs the distributed Brain Link pool — but
this makes the INGEST path ~5-6 orders of magnitude faster and the storage ~16x denser,
which is the real jump from 1e4 to 1e9.
"""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    import numpy as np
    _HAVE_NP = True
except Exception:  # pragma: no cover - numpy is a dep, but degrade gracefully
    _HAVE_NP = False

_CHUNK = 1_000_000  # triples buffered in RAM before a flush

import re as _re

from .graph_paths import SHIPPED_GRAPH_ROOT, same_graph_path

# English-only containment (owner directive 2026-07-17): see add() and _lang_gate().
_HANGUL_WRITE_GATE = _re.compile(r"[가-힣]")
_CANONICAL_SHIPPED_ROOT = SHIPPED_GRAPH_ROOT


def _same_store_path(left: Path, right: Path) -> bool:
    """Compare lexical/resolved store paths without requiring either to exist."""

    return same_graph_path(left, right)


class TermDict:
    """String <-> integer id, append-only, persisted. IDs are assigned in first-seen order
    so they are stable across a run. For 1e9+ distinct terms the dict itself becomes the
    bottleneck (that is a later, distributed problem); up to ~1e8 a Python dict is fine."""

    def __init__(self, path: Path, *, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only is True
        self._s2i: dict[str, int] = {}
        self._i2s: list[str] = []
        if self.path.exists():
            for line in self.path.open(encoding="utf-8"):
                term = line.rstrip("\n")
                if term or not self._i2s:  # allow empty-string term only at id 0 if present
                    self._i2s.append(term)
                    self._s2i[term] = len(self._i2s) - 1
        self._flushed = len(self._i2s)

    def intern(self, term: str) -> int:
        i = self._s2i.get(term)
        if i is None:
            if self.read_only:
                raise PermissionError(
                    "canonical shipped term dictionary is read-only"
                )
            i = len(self._i2s)
            self._i2s.append(term)
            self._s2i[term] = i
        return i

    def term(self, i: int) -> str:
        return self._i2s[i] if 0 <= i < len(self._i2s) else ""

    def lookup(self, term: str) -> int | None:
        """id for an existing term without creating it (query path)."""
        return self._s2i.get(term)

    def __len__(self) -> int:
        return len(self._i2s)

    def flush(self) -> None:
        if len(self._i2s) == self._flushed:
            return
        if self.read_only:
            raise PermissionError(
                "canonical shipped term dictionary is read-only"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for term in self._i2s[self._flushed:]:
                fh.write(term.replace("\n", " ") + "\n")
        self._flushed = len(self._i2s)


class TripleStore:
    """Append-only integer-columnar (s, p, o) triple store with a term dictionary,
    exact de-dup, and bounded-memory flush. High-throughput bulk ingest of structured
    facts; memmap scan for query. Binary columns (int32) => 12 bytes/triple on disk."""

    _MAGIC = b"ATTRPL01"

    def __init__(
        self,
        root: str | Path,
        dict_backend: str = "ram",
        *,
        write_src: bool = True,
        read_only: bool | None = None,
    ):
        """dict_backend: 'ram' (fast, vocabulary must fit memory) or 'sharded' (sqlite
        shards on disk — bounded RAM at any vocabulary size, slower ingest). A store
        remembers its backend in meta.json so reopen picks the right one automatically.

        write_src: emit the per-triple provenance sidecar (src.col, one int32/triple). Default
        True (every existing caller unchanged). A PROPHETA world-graph pack sets it False —
        Wikidata's provenance is uniform (source = Wikidata), so per-triple src is pure overhead
        (measured 3.9 B/triple, ~15% of the pack); reads already tolerate a missing src.col."""
        self.root = Path(root)
        inferred_read_only = _same_store_path(
            self.root,
            _CANONICAL_SHIPPED_ROOT,
        )
        self._read_only = (
            inferred_read_only if read_only is None else read_only is True
        )
        if self._read_only:
            if not self.root.is_dir():
                raise FileNotFoundError(
                    "canonical shipped store is unavailable and cannot be "
                    "created by TripleStore"
                )
        else:
            self.root.mkdir(parents=True, exist_ok=True)
        meta_path = self.root / "meta.json"
        if meta_path.exists():
            try:
                stored = json.loads(meta_path.read_text(encoding="utf-8")).get("dict_backend")
                if stored:
                    dict_backend = stored
            except Exception:
                pass
        self.dict_backend = dict_backend
        if dict_backend == "sharded":
            from .sharded_term_dict import ShardedTermDict

            self.terms = ShardedTermDict(
                self.root / "term_shards",
                read_only=self._read_only,
            )
        else:
            self.terms = TermDict(
                self.root / "terms.txt",
                read_only=self._read_only,
            )
        self._write_src = bool(write_src)
        self._buf_s: list[int] = []
        self._buf_p: list[int] = []
        self._buf_o: list[int] = []
        self._buf_src: list[int] = []
        self._seen: set[int] = set()          # dedupe hash of (s,p,o)
        # facts_about LRU (2026-07-13 latency surgery): one answer calls facts_about ~11x; a
        # bounded cache collapses exact repeats + hot subjects across turns. Versioned on the
        # s.col byte size (grows when ANY process appends — the learner daemon writes the same
        # store) + the tombstone signature, so a stale read can never survive a store change.
        self._fa_cache: dict[tuple, tuple] = {}
        self._count = self._read_count()
        # The reopened count came from meta.json and is already persisted. If
        # this marker is left unset, the first read-only facts_about() calls
        # flush(), mistakes the loaded count for a pending write, and rewrites
        # an identical meta.json. That mtime mutation invalidates sealed
        # before/after evaluation inventories.
        self._meta_count_written = self._count
        try:
            self._index_ts = json.loads((self.root / "meta.json").read_text(encoding="utf-8")).get("index_ts")
        except Exception:
            self._index_ts = None
        # DEDUPE IS SESSION-SCOPED, NOT STORE-SCOPED. `_seen` starts empty and only ever holds
        # what THIS instance added, so add() cannot tell a genuinely new triple from one that has
        # been on disk since 2026. (An earlier comment here claimed the set was "rebuilt from an
        # existing store"; no such rebuild was ever implemented, and the claim cost real time
        # 2026-07-17 — it makes re-running an ingest look idempotent when it would in fact append
        # a duplicate of every row it already wrote.)
        # So: any backfill against an already-ingested dump MUST diff against the store itself
        # (see scripts/backfill_kaikki_glosses.py) and must not lean on this flag.
        self._dedupe_enabled = True
        # language containment marker — see add() and _lang_gate(). Checked once here (add() is
        # the 740k/s hot path; a stat per call would gut it) and refreshed whenever a read path
        # notices the sidecar appear.
        self._contained = (self.root / "lang_gate.col").exists()

    def close(self) -> None:
        """Close dictionary handles; safe for read-only evaluation snapshots."""
        close = getattr(self.terms, "close", None)
        if callable(close):
            close()

    # ---- provenance sidecar (optional, per source) --------------------------------
    def _read_count(self) -> int:
        meta = self.root / "meta.json"
        if meta.exists():
            try:
                return int(json.loads(meta.read_text(encoding="utf-8")).get("count") or 0)
            except Exception:
                return 0
        return 0

    def _require_writable(self, operation: str) -> None:
        if self._read_only:
            raise PermissionError(
                f"{operation} refused: canonical shipped graph is read-only; "
                "use the signed candidate promotion boundary"
            )

    def _write_meta(self, extra: dict[str, Any] | None = None) -> None:
        self._require_writable("metadata write")
        meta = {"count": self._count, "terms": len(self.terms), "format": "int32_columnar_spo",
                "dict_backend": self.dict_backend}
        # index_ts must SURVIVE unrelated meta writes — losing it silently rolled
        # readers back to a stale index generation (measured: 5M-row tail scans)
        if getattr(self, "_index_ts", None):
            meta["index_ts"] = self._index_ts
        # turbo audit-debt flags must survive unrelated writes too (same bug
        # class): a query-path flush between ingest and sweep must not erase
        # the pending-audit marker
        try:
            prev = json.loads((self.root / "meta.json").read_text(encoding="utf-8"))
            for k in ("turbo_audit_pending", "turbo_last_batch",
                      "last_audit_removed", "last_audit_at"):
                if k in prev:
                    meta[k] = prev[k]
        except Exception:
            pass
        if extra:
            meta.update(extra)
        (self.root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _tri_key(self, s: int, p: int, o: int) -> int:
        # 21-bit-ish mix; exact within int range for de-dup within a run
        return (s * 1_000_003 + p) * 1_000_003 + o

    # ---- provenance registry: every fact knows WHERE it came from -----------------

    # Row-level int id -> a small registry line 'name|url_pattern'. Patterns may hold
    # {s}, resolved with the row's subject (per-entity DBpedia/wiktionary links without
    # interning millions of URL strings). id 0 = the pre-provenance legacy tier.

    def _sources(self) -> list[str]:
        if not hasattr(self, "_src_list"):
            path = self.root / "sources.txt"
            self._src_list = ["curated:legacy|"]
            if path.exists():
                lines = [ln.rstrip("\n") for ln in path.open(encoding="utf-8") if ln.strip()]
                if lines:
                    self._src_list = lines
            self._src_ids = {line: i for i, line in enumerate(self._src_list)}
        return self._src_list

    def intern_source(self, name: str, url_pattern: str = "") -> int:
        self._require_writable("source interning")
        line = f"{name}|{url_pattern}"
        self._sources()
        i = self._src_ids.get(line)
        if i is None:
            i = len(self._src_list)
            self._src_list.append(line)
            self._src_ids[line] = i
            # the registry is tiny — rewrite whole (keeps line order == ids)
            (self.root / "sources.txt").write_text(
                "\n".join(self._src_list) + "\n", encoding="utf-8")
        return i

    def source_of(self, row_src_id: int, subject: str) -> tuple[str, str]:
        """(name, resolved_url) for a row's source id."""
        srcs = self._sources()
        line = srcs[row_src_id] if 0 <= row_src_id < len(srcs) else srcs[0]
        name, _, pattern = line.partition("|")
        import urllib.parse as _up
        url = pattern.replace("{s}", _up.quote(subject.replace(" ", "_"))) if pattern else ""
        return name, url

    def _backfill_src(self) -> None:
        """src.col must have EXACTLY one int32 per existing (s) row, or every source
        id is shifted. Rows written before provenance existed are the legacy tier
        (id 0). Pads/creates src.col to match s.col length, then it stays in lockstep."""
        self._require_writable("source backfill")
        src_path = self.root / "src.col"
        s_path = self.root / "s.col"
        if not s_path.exists():
            return
        s_rows = s_path.stat().st_size // 4
        src_rows = (src_path.stat().st_size // 4) if src_path.exists() else 0
        missing = s_rows - src_rows
        if missing <= 0:
            return
        block = bytes(4 * 1_000_000)  # zero => legacy tier
        with src_path.open("ab") as fh:
            remaining = missing * 4
            while remaining > 0:
                fh.write(block[: min(len(block), remaining)])
                remaining -= len(block)

    def add(self, subject: str, predicate: str, obj: str, source: int | None = None) -> bool:
        """Intern the three terms and buffer the triple. Returns True if it was NEW
        (deduped). `source` is an intern_source() id. Flushes every _CHUNK triples.

        ENGLISH-ONLY WRITE GATE (owner directive 2026-07-17): a store under language
        containment — i.e. one whose root carries lang_gate.col — refuses any triple touching
        Hangul. The sidecar is the containment marker, not an env flag: the read gate promises
        "rows past my end are English by contract", and this is the write side of that same
        contract. Stores WITHOUT the sidecar (test fixtures, a future Korean store) behave as
        before — containment travels with the artifact that declares it. Korean re-entry later
        = delete lang_gate.col; both gates disarm together."""
        self._require_writable("triple add")
        if self._contained and (_HANGUL_WRITE_GATE.search(subject)
                                or _HANGUL_WRITE_GATE.search(obj)
                                or _HANGUL_WRITE_GATE.search(predicate)):
            return False
        s = self.terms.intern(subject)
        p = self.terms.intern(predicate)
        o = self.terms.intern(obj)
        if self._dedupe_enabled:
            k = self._tri_key(s, p, o)
            if k in self._seen:
                return False
            self._seen.add(k)
        self._buf_s.append(s)
        self._buf_p.append(p)
        self._buf_o.append(o)
        self._buf_src.append(int(source or 0))
        self._count += 1
        if len(self._buf_s) >= _CHUNK:
            self.flush()
        return True

    def bulk_ingest(self, triples: Iterable[tuple[str, str, str]],
                    source: int | None = None) -> dict[str, int]:
        """Ingest an iterable of (s, p, o) triples at high throughput. Returns counts."""
        self._require_writable("bulk ingest")
        added = seen = 0
        for s, p, o in triples:
            if s and p and o:
                if self.add(s, p, o, source=source):
                    added += 1
                else:
                    seen += 1
        self.flush()
        return {"added": added, "duplicates": seen, "total": self._count, "terms": len(self.terms)}

    def add_interned_batch(self, s_ids, p_id: int, o_ids, source: int = 0,
                           dedupe: bool = True) -> int:
        """TURBO WRITE (learning-acceleration finish): append many triples whose terms are ALREADY
        interned (int ids) — e.g. the deductive closure works in int space, so re-interning each
        via add() (string→id, per-triple Python loop, ~740k/s) is pure waste. This appends the int
        columns in ONE numpy write per column, lifting the write ceiling toward disk-I/O bound.
        `p_id` is a single predicate id (closures are per-relation). Returns rows written."""
        self._require_writable("interned batch add")
        if not _HAVE_NP:
            n = 0
            for s, o in zip(list(s_ids), list(o_ids)):
                if self.add(self.terms.term(int(s)), self.terms.term(int(p_id)),
                            self.terms.term(int(o)), source=source):
                    n += 1
            return n
        s_arr = np.asarray(s_ids, dtype="<i4").ravel()
        o_arr = np.asarray(o_ids, dtype="<i4").ravel()
        if s_arr.size == 0:
            return 0
        if dedupe and self._dedupe_enabled:
            keep = np.ones(s_arr.size, dtype=bool)
            for i in range(s_arr.size):
                k = self._tri_key(int(s_arr[i]), int(p_id), int(o_arr[i]))
                if k in self._seen:
                    keep[i] = False
                else:
                    self._seen.add(k)
            s_arr, o_arr = s_arr[keep], o_arr[keep]
            if s_arr.size == 0:
                return 0
        p_arr = np.full(s_arr.shape, int(p_id), dtype="<i4")
        src_arr = np.full(s_arr.shape, int(source), dtype="<i4")
        self.flush()  # drain any buffered per-triple adds first, so column order stays correct
        self.terms.flush()
        for name, arr in (("s", s_arr), ("p", p_arr), ("o", o_arr), ("src", src_arr)):
            with (self.root / f"{name}.col").open("ab") as fh:
                fh.write(arr.tobytes())
        self._count += int(s_arr.size)
        self._meta_count_written = self._count
        self._write_meta()
        return int(s_arr.size)

    def flush(self) -> None:
        if self._read_only:
            if self._buf_s or self._buf_p or self._buf_o or self._buf_src:
                self._require_writable("buffer flush")
            return
        if not self._buf_s:
            # query-path flush: nothing buffered — rewriting meta.json here cost
            # ~13ms of DISK WRITE per lookup (measured; it also invalidated every
            # mtime-keyed cache). Only touch disk when the count actually moved.
            if getattr(self, "_meta_count_written", None) != self._count:
                self.terms.flush()
                self._write_meta()
                self._meta_count_written = self._count
            return
        self.terms.flush()
        # append raw little-endian int32 columns (one file per column)
        self._meta_count_written = self._count
        _cols = [("s", self._buf_s), ("p", self._buf_p), ("o", self._buf_o)]
        if self._write_src:                       # world-graph packs skip the provenance sidecar
            self._backfill_src()
            _cols.append(("src", self._buf_src))
        for name, buf in _cols:
            with (self.root / f"{name}.col").open("ab") as fh:
                if _HAVE_NP:
                    fh.write(np.asarray(buf, dtype="<i4").tobytes())
                else:
                    fh.write(struct.pack(f"<{len(buf)}i", *buf))
        self._buf_s.clear(); self._buf_p.clear(); self._buf_o.clear(); self._buf_src.clear()
        self._write_meta()

    def __len__(self) -> int:
        return self._count

    # ---- query (memmap, bounded) ---------------------------------------------------
    def open_columns(self):
        if not _HAVE_NP:
            raise RuntimeError("numpy required for memmap scan")
        cols = {}
        for name in ("s", "p", "o"):
            path = self.root / f"{name}.col"
            n = (path.stat().st_size // 4) if path.exists() else 0
            cols[name] = np.memmap(str(path), dtype="<i4", mode="r", shape=(n,)) if n else np.zeros(0, "<i4")
        return cols

    # ---- subject index (the trillion-scale lever) -------------------------------
    # A full-column scan per lookup is O(n): fine at 500k, seconds at 100M, dead at
    # 1T. The sidecar index (stable argsort of s.col) makes it O(log n) and stays
    # correct THROUGH appends — rows past the indexed prefix are tail-scanned, so
    # ingest never blocks queries; rebuild_index() folds the tail in when convenient.

    def rebuild_index(self) -> int:
        self._require_writable("index rebuild")
        if not _HAVE_NP:
            return 0
        import time as _time

        self.flush()
        cols = self.open_columns()
        s_col = cols["s"]
        perm = np.argsort(s_col, kind="stable").astype("<i8")
        # VERSIONED files: a live engine memmaps the old generation, and Windows
        # refuses to overwrite a mapped file (EINVAL, measured) — so each rebuild
        # writes a new generation and points meta at it; readers switch on reload,
        # stale generations are unlinked when nothing holds them anymore.
        ts = int(_time.time())
        self._index_ts = ts
        np.save(str(self.root / f"s.perm.{ts}.npy"), perm)
        np.save(str(self.root / f"s.sorted.{ts}.npy"), np.asarray(s_col)[perm].astype("<i4"))
        self._write_meta({"index_ts": ts})
        self._idx_cache = None
        for old in self.root.glob("s.perm.*.npy"):
            if old.name != f"s.perm.{ts}.npy":
                try:
                    old.unlink()
                    (self.root / old.name.replace("s.perm", "s.sorted")).unlink(missing_ok=True)
                except Exception:
                    pass  # still mapped by a live reader — next rebuild retries
        return len(perm)

    def _index(self):
        meta = self.root / "meta.json"
        try:
            msig = meta.stat().st_mtime_ns
            cached_ts = getattr(self, "_meta_ts_cache", None)
            if cached_ts is not None and cached_ts[0] == msig:
                ts = cached_ts[1]
            else:
                ts = json.loads(meta.read_text(encoding="utf-8")).get("index_ts")
                self._meta_ts_cache = (msig, ts)
        except Exception:
            ts = None
        perm_p = self.root / (f"s.perm.{ts}.npy" if ts else "s.perm.npy")
        sort_p = self.root / (f"s.sorted.{ts}.npy" if ts else "s.sorted.npy")
        if not perm_p.exists() or not sort_p.exists():
            return None
        sig = (perm_p.name, perm_p.stat().st_mtime_ns, perm_p.stat().st_size)
        cached = getattr(self, "_idx_cache", None)
        if cached is not None and cached[0] == sig:
            return cached[1]
        try:
            pair = (np.load(str(perm_p), mmap_mode="r"), np.load(str(sort_p), mmap_mode="r"))
        except Exception:
            return None
        self._idx_cache = (sig, pair)
        return pair

    def _subject_rows(self, sid: int, s_col) -> "np.ndarray":
        pair = self._index()
        if pair is None:
            return np.nonzero(s_col == sid)[0]
        perm, ssorted = pair
        # needle must match the column dtype: a Python int promotes the WHOLE
        # memmapped array to int64 (a 24MB copy per call, measured 30ms) —
        # cast the needle, not the column
        needle = np.asarray(sid, dtype=ssorted.dtype)
        lo = int(np.searchsorted(ssorted, needle, "left"))
        hi = int(np.searchsorted(ssorted, needle, "right"))
        # stable argsort already preserves original row order within equal keys —
        # re-sorting a hub subject's 1e4+ rows cost 7ms/call (profiled); a view is free
        head = perm[lo:hi]
        n_indexed = len(perm)
        if len(s_col) > n_indexed:
            tail = np.nonzero(s_col[n_indexed:] == sid)[0] + n_indexed
            if len(tail):
                return np.concatenate([head, tail])
        return head

    def retract(self, subject: str, predicate: str, obj: str, reason: str = "") -> None:
        """Append an audit-logged tombstone without silently deleting a row."""
        self._require_writable("triple retraction")
        """Audit-logged tombstone — the store stays append-only; a retraction is itself
        an event, never a silent delete. facts_about filters tombstoned triples."""
        import json as _json
        import time as _time
        with (self.root / "retractions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps({"s": subject, "p": predicate, "o": obj, "reason": reason,
                                  "ts": _time.strftime("%Y-%m-%dT%H:%M:%S")},
                                 ensure_ascii=False) + "\n")
        self._tombstones_sig = None  # force reload

    def _tombstones(self) -> set[tuple[str, str, str]]:
        import json as _json
        path = self.root / "retractions.jsonl"
        if not path.exists():
            return set()
        sig = path.stat().st_mtime
        if getattr(self, "_tombstones_sig", None) != sig:
            out: set[tuple[str, str, str]] = set()
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(line)
                    out.add((r["s"], r["p"], r["o"]))
                except Exception:
                    continue
            self._tombstones_cache = out
            self._tombstones_sig = sig
        return self._tombstones_cache

    def _facts_about_raw(self, subject: str, limit: int = 20,
                         preds: tuple[str, ...] | None = None) -> list[tuple[str, str, str]]:
        """All stored (s, p, o) with this subject — a bounded memmap scan, no full load.
        `preds` filters BY PREDICATE BEFORE the limit: at millions of rows a subject's
        first N edges are whatever relation floods the store (measured: derived
        located_in buried is_a for 'dog'), so relation-seeking callers must say so."""
        self.flush()
        sid = self.terms.lookup(subject)
        if sid is None and subject != subject.lower():
            # curated KG dumps (ConceptNet URIs) store English terms lowercase;
            # a query surface gives 'Colobus' — fold case rather than miss the fact
            subject = subject.lower()
            sid = self.terms.lookup(subject)
        if sid is None:
            return []
        cols = self.open_columns()
        out: list[tuple[str, str, str]] = []
        s, p, o = cols["s"], cols["p"], cols["o"]
        idx = self._subject_rows(sid, s) if len(s) else []
        if preds is not None and len(idx):
            pids = [self.terms.lookup(x) for x in preds]
            pids_arr = np.array([x for x in pids if x is not None], dtype=p.dtype)
            if len(pids_arr) == 0:
                return []
            # hub subjects have 1e4+ rows post-closure — gather/filter in CHUNKS
            # and stop at the limit instead of touching every row (measured 14ms
            # for a full gather at 13M rows; sub-ms chunked)
            kept: list[int] = []
            for start in range(0, len(idx), 2048):
                chunk = idx[start:start + 2048]
                hits = chunk[np.isin(p[chunk], pids_arr)]
                # verdict INSIDE the chunk loop: on a junk-heavy hub the first `limit`
                # rows are all verdict-0, and filtering after the stop would return
                # nothing while the real parents sit deeper in the row list
                hits = self._verdict_keep(hits, p)
                kept.extend(int(i) for i in hits)
                if len(kept) >= limit:
                    break
            idx = kept
        elif len(idx):
            idx = self._verdict_keep(idx, p)
        for i in idx[:limit]:
            out.append((subject, self.terms.term(int(p[i])), self.terms.term(int(o[i]))))
        return out

    # ---- is_a verdict sidecar (evidence annotation, never deletion) ---------------------------
    # MEASURED 2026-07-17: 19.6M of this store's 26.9M rows are src=0 is_a, and 17.1M of the
    # EN-EN ones are asserted by NO source on disk AND derivable from NO evidenced edge (98% of a
    # 3000-row sample; e.g. 'adobe lily is_a housing' — the hypernym of 'adobe'). They are the
    # residue of a buggy bulk write, and they are what poisons every is_a walk (crocodile: 388
    # parents, ~4 real). At this scale tombstones are mechanically impossible (a 17M-line jsonl
    # loaded as a RAM set) and a rebuild violates the no-reset doctrine — so the fix is a VERDICT
    # SIDECAR: one uint8 per row (0=no evidence, 1=source-asserted/out-of-scope, 2=derivable from
    # evidenced base). Rows never change; delete isa_verdict.col and behavior fully reverts.
    # Readers drop is_a rows with verdict 0. Built by scripts/build_isa_verdict.py.
    def _isa_verdict(self):
        path = self.root / "isa_verdict.col"
        try:
            sig = path.stat().st_mtime
        except OSError:
            self._verdict_sig, self._verdict = None, None
            return None
        if getattr(self, "_verdict_sig", None) != sig:
            n = path.stat().st_size
            self._verdict = np.memmap(str(path), dtype=np.uint8, mode="r", shape=(n,)) if n else None
            self._verdict_sig = sig
        return self._verdict

    # ---- language gate sidecar (English-only containment, never deletion) ---------------------


    # knowledge and no-reset forbids burning it — but every read through the store API skips
    # them. Same reversible mechanism as the verdict sidecar: one uint8 per row (1 = subject or
    # object contains Hangul), built by scripts/build_lang_gate.py; delete lang_gate.col and the
    # Korean lane is back byte-identical. Gating READS here (not per-lane) is the single-exit-
    # gate doctrine: four different lanes were each hand-filtering Hangul before this.
    def _lang_gate(self):
        path = self.root / "lang_gate.col"
        try:
            sig = path.stat().st_mtime
        except OSError:
            self._langgate_sig, self._langgate = None, None
            self._contained = False
            return None
        if getattr(self, "_langgate_sig", None) != sig:
            n = path.stat().st_size
            self._langgate = np.memmap(str(path), dtype=np.uint8, mode="r", shape=(n,)) if n else None
            self._langgate_sig = sig
        self._contained = True   # a gate that exists arms the write side too (see add())
        return self._langgate

    def _verdict_keep(self, rows, p_col):
        """Filter row indices: keep only is_a rows the sidecar marks 1 (source-asserted, or out
 of judging scope). Rows past the sidecar's end (appended after the build — they carry
 real provenance now) are kept.

 VERDICT 2 IS RETIRED (measured 2026-07-17, second pass). The sidecar's build reasoned
 that a row derivable from the evidenced base in <=3 hops is legitimate transitive
 closure. It is not. ConceptNet nodes are word STRINGS, not senses, so closure leaks
 across senses at every polysemous hub. The leak is exact and reproducible:

 part is_a tune <- a real ConceptNet edge (a musical 'part' IS a tune)
 part in-degree 122 <- so every subject that reaches 'part' inherits 'tune'

 and the damage is what you would predict from that:
 abalone -> tune, slave, word, syntagma, section (all verdict 2)
 car -> organism, performance, chemical process (all verdict 2)
 african elephant -> person, design, emblem (all verdict 2)
 Random 12-subject sample: 34 sourced parents vs 186 derived, the derived majority junk.

 Retiring it costs almost nothing, because ConceptNet already asserts the chains it has:
 paddlefish verdict-1 = ganoid, fish, vertebrate, animal, organism, creature
 Inheritance that is real is usually SOURCED; what only closure could reach is usually
 the leak. crocodile drops to its two sourced parents (reptile, crocodilian reptile),
 which is a better answer than adding animal/organism/living thing anyway.

 This is with its exception removed. Verdict 2 WAS the exception, and the
 junk came in through exactly it — =, as the charter says. Store-wide this
 quarantines 283,446 more rows and leaves 363,866 sourced ones answering. Korean rows
 carry verdict 1 (out of judging scope) and are untouched: is_a still answers.
 """
        import numpy as _np
        arr = _np.asarray(rows)
        if not len(arr):
            return arr
        bad = _np.zeros(len(arr), dtype=bool)
        verdict = self._isa_verdict()
        if verdict is not None:
            isa = self.terms.lookup("is_a")
            if isa is not None:
                in_range = arr < len(verdict)
                if in_range.any():
                    sel = arr[in_range]
                    bad[in_range] |= (p_col[sel] == isa) & (verdict[sel] != 1)
        # language containment: any-predicate, both directions. Rows past the gate's end were
        # appended after the build — add() refuses Hangul now, so they are English by contract.
        gate = self._lang_gate()
        if gate is not None:
            in_range = arr < len(gate)
            if in_range.any():
                sel = arr[in_range]
                bad[in_range] |= gate[sel] == 1
        return arr[~bad]

    def _store_version(self) -> tuple:
        """Cheap change-signal: the s.col byte size (bumps when any process appends) + the
        pending buffer length + the tombstone signature. One stat, no data load."""
        try:
            sz = (self.root / "s.col").stat().st_size
        except OSError:
            sz = 0
        return (sz, len(self._buf_s), getattr(self, "_tombstones_sig", None),
                getattr(self, "_verdict_sig", None), getattr(self, "_langgate_sig", None))

    def facts_about(self, subject: str, limit: int = 20,
                    preds: tuple[str, ...] | None = None) -> list[tuple[str, str, str]]:
        self._tombstones()  # refresh _tombstones_sig so the version reflects retractions
        self._isa_verdict()  # refresh sidecar sigs BEFORE versioning — a gate file that appeared
        self._lang_gate()    # between calls must invalidate the cache on THIS call, not the next
        ver = self._store_version()
        key = (subject, limit, preds)
        hit = self._fa_cache.get(key)
        if hit is not None and hit[0] == ver:
            return hit[1]
        tomb = self._tombstones()
        out = [f for f in self._facts_about_raw(subject, limit=limit, preds=preds)
               if f not in tomb]
        if len(self._fa_cache) >= 2048:      # bounded: drop all rather than track LRU order
            self._fa_cache.clear()
        self._fa_cache[key] = (ver, out)
        return out

    def facts_with_sources(self, subject: str, limit: int = 20,
                           preds: tuple[str, ...] | None = None
                           ) -> list[tuple[str, str, str, str, str]]:
        """facts_about + per-row provenance: (s, p, o, source_name, source_url).
 : the answer layer cites these instead of a generic store name."""
        tomb = self._tombstones()
        self.flush()
        sid = self.terms.lookup(subject)
        if sid is None and subject != subject.lower():
            subject = subject.lower()
            sid = self.terms.lookup(subject)
        if sid is None:
            return []
        cols = self.open_columns()
        s_col, p, o = cols["s"], cols["p"], cols["o"]
        src_path = self.root / "src.col"
        src = None
        if src_path.exists():
            n = src_path.stat().st_size // 4
            src = np.memmap(str(src_path), dtype="<i4", mode="r", shape=(n,)) if n else None
        idx = self._subject_rows(sid, s_col) if len(s_col) else []
        if preds is not None and len(idx):
            pids = [self.terms.lookup(x) for x in preds]
            pids_arr = np.array([x for x in pids if x is not None], dtype=p.dtype)
            if len(pids_arr) == 0:
                return []
            kept: list[int] = []
            for start in range(0, len(idx), 2048):
                chunk = idx[start:start + 2048]
                hits = chunk[np.isin(p[chunk], pids_arr)]
                hits = self._verdict_keep(hits, p)   # same in-loop verdict as _facts_about_raw
                kept.extend(int(i) for i in hits)
                if len(kept) >= limit:
                    break
            idx = kept
        elif len(idx):
            idx = self._verdict_keep(idx, p)
        out: list[tuple[str, str, str, str, str]] = []
        for i in list(idx)[:limit]:
            i = int(i)
            row = (subject, self.terms.term(int(p[i])), self.terms.term(int(o[i])))
            if row in tomb:
                continue
            sid_row = int(src[i]) if src is not None and i < len(src) else 0
            name, url = self.source_of(sid_row, subject)
            out.append((*row, name, url))
        return out

    def disk_bytes(self) -> int:
        total = 0
        for f in ("s.col", "p.col", "o.col", "terms.txt"):
            path = self.root / f
            if path.exists():
                total += path.stat().st_size
        return total
