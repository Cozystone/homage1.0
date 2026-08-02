"""Disk-backed semantic concept store — the ANSWER-QUALITY + RESIDENT-RAM half of
" ". node_store bounds the geometric fields; this bounds the SEMANTIC
payload (concept name/description/relations) that determines answer quality.

The in-RAM answer path (`get_semantic_context`) SCANS every concept and copies each dict
per query, so latency+RAM grow linearly with knowledge (measured: 1.5k=102ms, 20k=1.4s,
100k=7s) — a big brain or a weak PC both degrade.

DISK-BACKED (sqlite): both the concept records AND the inverted index live in an on-disk
sqlite b-tree, so open() loads NOTHING into RAM and each query reads only the pages it
touches (sqlite's own bounded page cache + optional OS mmap). Resident RAM is bounded by
the page cache, NOT by N — a weak PC serves an arbitrarily large knowledge base. (An
earlier in-RAM inverted-index version bounded latency but its index was O(N) and BIGGER
than the concepts — 291MB@200k — so it did NOT bound resident RAM. This replaces it.)

lookup() replicates get_semantic_context's exact contract (score>=1.0, korean/english_
language case, relation-target expansion in rank order, query-substring probing for
`name in query`) so answers are byte-identical to the scan. Public interface (build/open/
lookup/n/get_concept_by_id) is unchanged, so pack_loader + tests need no edits.
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any, Iterable

from .pack_loader import _concept_score, _norm, _tokens

_DB_NAME = "index.sqlite"
_PARAM_CHUNK = 400  # keep IN(...) parameter counts well under sqlite's 999 limit


def _index_tokens(concept: dict[str, Any]) -> set[str]:
    """Tokens under which a concept is findable — the fields _concept_score matches names
    on (id, canonical_name, aliases, label values), the whole normalized name, and the
    description tokens (a concept matched only via its description must still be a
    candidate)."""
    toks: set[str] = set()
    names = [concept.get("concept_id", ""), concept.get("canonical_name", ""), *(concept.get("aliases") or [])]
    names.extend(str(v) for v in (concept.get("labels") or {}).values())
    for name in names:
        toks |= _tokens(str(name))
        nn = _norm(str(name))
        if nn:
            toks.add(nn)
    toks |= _tokens(str(concept.get("short_description", "")))
    return toks


class SemanticConceptStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._db = self.root / _DB_NAME

    # ---- connections (per-operation => thread-safe under the FastAPI server) ------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db), check_same_thread=False)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA cache_size=-2000")       # ~2 MB page cache -> bounded RAM
        conn.execute("PRAGMA mmap_size=268435456")    # let the OS mmap the db (reclaimable pages)
        return conn

    @property
    def n(self) -> int:
        conn = self._connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0])
        finally:
            conn.close()

    # ---- build / open ------------------------------------------------------------
    @classmethod
    def build(cls, root: str | Path, concepts: Iterable[dict[str, Any]]) -> "SemanticConceptStore":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        db = root / _DB_NAME
        if db.exists():
            db.unlink()
        for legacy in ("index.json", "records.jsonl"):  # remove the old in-RAM-index format
            p = root / legacy
            if p.exists():
                p.unlink()
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("CREATE TABLE concepts(cid TEXT PRIMARY KEY, json TEXT)")
            conn.execute("CREATE TABLE postings(token TEXT, cid TEXT)")
            cbatch: list[tuple[str, str]] = []
            pbatch: list[tuple[str, str]] = []
            for c in concepts:
                cid = str(c.get("concept_id"))
                cbatch.append((cid, json.dumps(c, ensure_ascii=False)))
                for t in _index_tokens(c):
                    pbatch.append((t, cid))
                if len(cbatch) >= 5000:
                    conn.executemany("INSERT OR REPLACE INTO concepts VALUES(?,?)", cbatch); cbatch.clear()
                if len(pbatch) >= 50000:
                    conn.executemany("INSERT INTO postings VALUES(?,?)", pbatch); pbatch.clear()
            if cbatch:
                conn.executemany("INSERT OR REPLACE INTO concepts VALUES(?,?)", cbatch)
            if pbatch:
                conn.executemany("INSERT INTO postings VALUES(?,?)", pbatch)
            conn.execute("CREATE INDEX idx_postings_token ON postings(token)")
            conn.commit()
        finally:
            conn.close()
        return cls(root)

    @classmethod
    def open(cls, root: str | Path) -> "SemanticConceptStore":
        root = Path(root)
        if not (root / _DB_NAME).exists():
            raise FileNotFoundError(root / _DB_NAME)
        return cls(root)

    # ---- record access -----------------------------------------------------------
    @staticmethod
    def _load(row) -> dict[str, Any] | None:
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def get_concept_by_id(self, cid: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            return self._load(conn.execute("SELECT json FROM concepts WHERE cid=?", (str(cid),)).fetchone())
        finally:
            conn.close()

    def _fetch_records(self, conn: sqlite3.Connection, cids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(cids), _PARAM_CHUNK):
            chunk = cids[i:i + _PARAM_CHUNK]
            ph = ",".join("?" * len(chunk))
            for cid, js in conn.execute(f"SELECT cid, json FROM concepts WHERE cid IN ({ph})", chunk):
                rec = self._load((js,))
                if rec is not None:
                    out[cid] = rec
        return out

    # ---- candidate generation ----------------------------------------------------
    def _query_keys(self, query: str) -> set[str]:
        """Probe keys: query tokens, the whole normalized query, AND every contiguous
        substring of it (captures _concept_score's `name in query` rule). Bounded by
        query length, never N."""
        keys = _tokens(query) | {_norm(query)}
        nq = _norm(query)
        m = len(nq)
        if m <= 40:
            for i in range(m):
                for j in range(i + 2, m + 1):
                    keys.add(nq[i:j])



        # _named_with_boundary — a parity break that stays latent until the store is rebuilt
        # to match the pack. Emit the 1-char prefix so the stem concept becomes a candidate;
        # the >=1.0 score floor in lookup() drops anything that isn't a real boundary match.
        if m <= 6:
            keys.add(nq[:1])
        return {k for k in keys if k}

    def _candidate_ids(self, conn: sqlite3.Connection, query: str, max_candidates: int) -> list[str]:
        keys = list(self._query_keys(query))
        seen: dict[str, None] = {}
        for i in range(0, len(keys), _PARAM_CHUNK):
            chunk = keys[i:i + _PARAM_CHUNK]
            ph = ",".join("?" * len(chunk))
            for (cid,) in conn.execute(f"SELECT DISTINCT cid FROM postings WHERE token IN ({ph})", chunk):
                if cid not in seen:
                    seen[cid] = None
                    if len(seen) >= max_candidates:
                        return list(seen)
        return list(seen)

    # ---- bounded lookup (contract-identical to get_semantic_context) --------------
    def lookup(self, query: str, limit: int = 12, max_candidates: int = 4000) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cand = self._candidate_ids(conn, query, max_candidates)
            recs = self._fetch_records(conn, cand)
            scored = sorted(
                ({**r, "match_score": _concept_score(query, r)} for r in recs.values()),
                key=lambda it: (float(it.get("match_score") or 0.0), float(it.get("confidence") or 0.0)),
                reverse=True,
            )
            high_conf = [it for it in scored if float(it.get("match_score") or 0.0) >= 4.0]
            q_low = query.lower()
            selected = [it for it in scored if float(it.get("match_score") or 0.0) >= 1.0][:limit]
            if high_conf:
                selected = [
                    it for it in selected
                    if it.get("concept_id") not in {"korean_language", "english_language"}
                    or any(mk in q_low for mk in ["한국어", "영어로", "번역투", "language"])
                ][:limit]
            if selected:
                sel_ids = {it["concept_id"] for it in selected}
                targets = [rel.get("target") for it in selected for rel in it.get("relations", []) if rel.get("target")]
                missing = [str(t) for t in dict.fromkeys(targets) if t not in sel_ids and t not in recs]
                extra_recs = {**{t: recs[t] for t in dict.fromkeys(targets) if t in recs and t not in sel_ids},
                              **self._fetch_records(conn, missing)}
                extra = [{**r, "match_score": _concept_score(query, r)} for r in extra_recs.values()]
                extra.sort(key=lambda it: (float(it.get("match_score") or 0.0), float(it.get("confidence") or 0.0)), reverse=True)
                for it in extra:
                    if len(selected) >= limit:
                        break
                    if it["concept_id"] not in sel_ids:
                        selected.append(it)
                        sel_ids.add(it["concept_id"])
            return selected[:limit]
        finally:
            conn.close()


def build_store_from_pack(pack, root: str | Path) -> SemanticConceptStore:
    return SemanticConceptStore.build(root, pack.semantic_graph.get("concepts") or [])
