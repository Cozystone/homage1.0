from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "data",
    "text",
    "document",
    "documents",
    "system",
    "using",
}

SCHEMA_VERSION = 1
VECTOR_SOURCE = "local_relation_projection_v1"
GHOST_VECTOR_SOURCE = "ghost_shell_content_addressed_v1"
AUTO_FLUSH_FRAGMENT_COUNT = 50
AUTO_FLUSH_SECONDS = 180.0
ACTION_HINTS = {
    "use",
    "uses",
    "used",
    "build",
    "builds",
    "built",
    "learn",
    "learns",
    "learning",
    "retrieve",
    "retrieves",
    "verify",
    "verifies",
    "generate",
    "generates",
    "connect",
    "connects",
}


@dataclass
class BuildPaths:
    memory_dir: Path
    db_path: Path
    event_path: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _paths(memory_dir: str | Path = "data/memory") -> BuildPaths:
    root = Path(memory_dir)
    return BuildPaths(root, root / "homage.db", root / "events.jsonl")


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
        elif current:
            token = "".join(current).strip("-_")
            if token and token not in STOPWORDS:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).strip("-_")
        if token and token not in STOPWORDS:
            tokens.append(token)
    return [token for token in tokens if len(token) > 1 or token.isdigit()]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|[\r\n]+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _chunk_text(text: str, max_tokens: int = 90, overlap_sentences: int = 1) -> list[str]:
    sentences = _sentences(text)
    if not sentences:
        return [text[:900]] if text.strip() else []
    chunks: list[str] = []
    window: list[str] = []
    window_tokens = 0
    for sentence in sentences:
        count = len(_tokens(sentence))
        if window and window_tokens + count > max_tokens:
            chunks.append(" ".join(window))
            window = window[-overlap_sentences:] if overlap_sentences else []
            window_tokens = sum(len(_tokens(item)) for item in window)
        window.append(sentence)
        window_tokens += count
    if window:
        chunks.append(" ".join(window))
    return chunks


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", label.strip()).strip("-").lower()
    return cleaned[:96] or "node"


def _node_type_for_token(token: str) -> str:
    lowered = token.lower()
    if lowered in ACTION_HINTS or lowered.endswith(("ing", "ed")):
        return "predicate"
    if any(char.isdigit() for char in token):
        return "quantity"
    if "-" in token or "_" in token:
        return "compound"
    return "token"


def _phrase_node_id(left: str, right: str) -> str:
    return f"phrase-{_slug(f'{left} {right}')}"


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _hash_unit(value: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).digest()
    integer = int.from_bytes(digest[:8], "big")
    return (integer / ((1 << 64) - 1)) * 2 - 1


def _content_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8", errors="ignore")).hexdigest()


def _source_type_for_path(path: Path) -> str:
    lowered = path.as_posix().lower()
    return "self_corpus" if "self_corpus" in lowered else "local_corpus"


def _projection(node_id: str, degree: int, count: int) -> tuple[float, float, float]:
    scale = 1.0 + math.log1p(max(1, degree + count)) * 0.42
    return (
        round(_hash_unit(node_id, "x") * scale, 5),
        round(_hash_unit(node_id, "y") * scale, 5),
        round(_hash_unit(node_id, "z") * scale, 5),
    )


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return bool(row)


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
          doc_id TEXT PRIMARY KEY,
          path TEXT NOT NULL,
          byte_count INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
          chunk_id TEXT PRIMARY KEY,
          doc_id TEXT NOT NULL,
          text TEXT NOT NULL,
          token_count INTEGER NOT NULL,
          FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
        );
        CREATE TABLE IF NOT EXISTS memory_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_type TEXT NOT NULL,
          subject_id TEXT,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes (
          node_id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          type TEXT NOT NULL,
          count INTEGER NOT NULL,
          confidence REAL NOT NULL,
          evidence_doc_ids TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edges (
          edge_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          relation TEXT NOT NULL,
          target TEXT NOT NULL,
          confidence REAL NOT NULL,
          count INTEGER NOT NULL,
          evidence_doc_ids TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS relation_stats (
          source TEXT NOT NULL,
          relation TEXT NOT NULL,
          target TEXT NOT NULL,
          count INTEGER NOT NULL,
          p_target_given_source REAL NOT NULL,
          p_relation_given_source_target REAL NOT NULL,
          recency_weight REAL NOT NULL,
          source_quality_weight REAL NOT NULL,
          activation_weight REAL NOT NULL,
          confidence REAL NOT NULL,
          PRIMARY KEY(source, relation, target)
        );
        CREATE TABLE IF NOT EXISTS token_transitions (
          source TEXT NOT NULL,
          target TEXT NOT NULL,
          count INTEGER NOT NULL,
          probability REAL NOT NULL,
          PRIMARY KEY(source, target)
        );
        CREATE TABLE IF NOT EXISTS cooccurrence_windows (
          source TEXT NOT NULL,
          target TEXT NOT NULL,
          count INTEGER NOT NULL,
          probability REAL NOT NULL,
          PRIMARY KEY(source, target)
        );
        CREATE TABLE IF NOT EXISTS activation_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          query TEXT NOT NULL,
          node_id TEXT NOT NULL,
          score REAL NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vector_rows (
          node_id TEXT PRIMARY KEY,
          dim0 REAL NOT NULL,
          dim1 REAL NOT NULL,
          dim2 REAL NOT NULL,
          vector_source TEXT NOT NULL,
          trained_on_events INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS query_traces (
          trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
          query TEXT NOT NULL,
          result_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payload_vault (
          hash_key TEXT PRIMARY KEY,
          raw_text TEXT NOT NULL,
          metadata_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ghost_nodes (
          node_hash TEXT PRIMARY KEY,
          dim0 REAL NOT NULL,
          dim1 REAL NOT NULL,
          dim2 REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ghost_edges (
          source_hash TEXT NOT NULL,
          target_hash TEXT NOT NULL,
          weight REAL NOT NULL,
          PRIMARY KEY(source_hash, target_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
        CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
        CREATE INDEX IF NOT EXISTS idx_activation_query ON activation_events(query);
        CREATE INDEX IF NOT EXISTS idx_ghost_edges_source ON ghost_edges(source_hash);
        CREATE INDEX IF NOT EXISTS idx_ghost_edges_target ON ghost_edges(target_hash);
        """
    )
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("schema_version", str(SCHEMA_VERSION)))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("llm_policy", "no_external_no_local_quantized_no_pretrained"))


def _mark_append_only_projection(conn: sqlite3.Connection) -> None:
    # ATANOR memory is append-only by contract. This function is intentionally
    # retained as a compatibility hook for older callers, but it must never
    # erase projection, Ghost Shell, or Payload Vault tables during ingestion.
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("append_only_projection", "true"))


def _write_event(event_file, conn: sqlite3.Connection, event_type: str, subject_id: str | None, payload: dict[str, Any]) -> None:
    created_at = utc_now_iso()
    record = {
        "event_type": event_type,
        "subject_id": subject_id,
        "payload": payload,
        "created_at": created_at,
    }
    event_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    conn.execute(
        "INSERT INTO memory_events(event_type, subject_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (event_type, subject_id, json.dumps(payload, ensure_ascii=False), created_at),
    )


def _upsert_payload_vault(conn: sqlite3.Connection, hash_key: str, raw_text: str, metadata: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO payload_vault(hash_key, raw_text, metadata_json)
        VALUES (?, ?, ?)
        ON CONFLICT(hash_key) DO UPDATE SET
          raw_text = excluded.raw_text,
          metadata_json = excluded.metadata_json
        """,
        (hash_key, raw_text, json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
    )


def _upsert_ghost_node(conn: sqlite3.Connection, node_hash: str, projection: tuple[float, float, float]) -> None:
    conn.execute(
        """
        INSERT INTO ghost_nodes(node_hash, dim0, dim1, dim2)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(node_hash) DO UPDATE SET
          dim0 = excluded.dim0,
          dim1 = excluded.dim1,
          dim2 = excluded.dim2
        """,
        (node_hash, projection[0], projection[1], projection[2]),
    )


def _upsert_ghost_edge(conn: sqlite3.Connection, source_hash: str, target_hash: str, weight: float) -> None:
    if source_hash == target_hash:
        return
    conn.execute(
        """
        INSERT INTO ghost_edges(source_hash, target_hash, weight)
        VALUES (?, ?, ?)
        ON CONFLICT(source_hash, target_hash) DO UPDATE SET
          weight = MAX(ghost_edges.weight, excluded.weight)
        """,
        (source_hash, target_hash, round(max(0.0, float(weight)), 6)),
    )


class _AutoFlush:
    def __init__(self, conn: sqlite3.Connection, *, max_fragments: int = AUTO_FLUSH_FRAGMENT_COUNT, max_seconds: float = AUTO_FLUSH_SECONDS) -> None:
        self.conn = conn
        self.max_fragments = max(1, int(max_fragments))
        self.max_seconds = max(1.0, float(max_seconds))
        self.pending = 0
        self.last_flush = time.monotonic()

    def mark(self, fragments: int = 1) -> None:
        self.pending += max(1, int(fragments))
        now = time.monotonic()
        if self.pending >= self.max_fragments or now - self.last_flush >= self.max_seconds:
            self.flush()

    def flush(self) -> None:
        if self.pending <= 0:
            return
        self.conn.commit()
        self.pending = 0
        self.last_flush = time.monotonic()


def build_memory(
    cleaned_dir: str = "data/cleaned",
    ontology_dir: str = "data/ontology",
    memory_dir: str = "data/memory",
) -> dict[str, Any]:
    paths = _paths(memory_dir)
    paths.memory_dir.mkdir(parents=True, exist_ok=True)
    conn = _connect(paths.db_path)
    _init_schema(conn)
    _mark_append_only_projection(conn)

    documents = sorted([*Path(cleaned_dir).rglob("*.txt"), *Path(cleaned_dir).rglob("*.md")])
    ontology_root = Path(ontology_dir)
    ontology_nodes = _read_json(ontology_root / "nodes.json", [])
    ontology_edges = _read_json(ontology_root / "edges.json", [])
    node_counts: Counter[str] = Counter()
    node_meta: dict[str, dict[str, Any]] = {}
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    edge_docs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    transitions: Counter[tuple[str, str]] = Counter()
    cooccurs: Counter[tuple[str, str]] = Counter()
    ghost_payloads: dict[str, tuple[str, dict[str, Any]]] = {}
    ghost_edge_counts: Counter[tuple[str, str]] = Counter()
    doc_source_types: dict[str, str] = {}
    source_totals: Counter[str] = Counter()
    pair_totals: Counter[tuple[str, str]] = Counter()
    flush = _AutoFlush(conn)

    with paths.event_path.open("a", encoding="utf-8") as event_file:
        for node in ontology_nodes:
            node_id = str(node.get("id") or _slug(str(node.get("label") or "")))
            label = str(node.get("label") or node_id)
            count = int(node.get("count") or 1)
            node_counts[node_id] += count
            node_meta[node_id] = {
                "label": label,
                "type": str(node.get("type") or "concept"),
                "confidence": float(node.get("confidence") or 0.55),
                "evidence_doc_ids": list(node.get("evidence_doc_ids") or []),
            }
            node_hash = _content_hash(label)
            ghost_payloads[node_hash] = (
                label,
                {
                    "kind": "ontology_node",
                    "legacy_id": node_id,
                    "type": node_meta[node_id]["type"],
                    "evidence_doc_ids": node_meta[node_id]["evidence_doc_ids"],
                },
            )
            _write_event(event_file, conn, "node_imported", node_id, node_meta[node_id])
            flush.mark()

        for edge in ontology_edges:
            source = str(edge.get("source") or "")
            relation = str(edge.get("relation") or "relates")
            target = str(edge.get("target") or "")
            if not source or not target:
                continue
            key = (source, relation, target)
            docs = set(str(doc) for doc in edge.get("evidence_doc_ids") or [])
            edge_counts[key] += max(1, len(docs))
            edge_docs[key].update(docs)
            source_totals[source] += max(1, len(docs))
            pair_totals[(source, target)] += max(1, len(docs))
            _write_event(event_file, conn, "edge_imported", f"{source}:{relation}:{target}", dict(edge))
            flush.mark()

        for path in documents:
            doc_id = path.stem
            source_type = _source_type_for_path(path)
            doc_source_types[doc_id] = source_type
            text = path.read_text(encoding="utf-8", errors="ignore")
            conn.execute(
                """
                INSERT INTO documents(doc_id, path, byte_count, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                  path = excluded.path,
                  byte_count = excluded.byte_count
                """,
                (doc_id, str(path), len(text.encode("utf-8")), utc_now_iso()),
            )
            _write_event(
                event_file,
                conn,
                "document_imported",
                doc_id,
                {"path": str(path), "byte_count": len(text.encode("utf-8")), "source_type": source_type},
            )
            flush.mark()
            for chunk_index, chunk in enumerate(_chunk_text(text) or [text[:900]]):
                tokens = _tokens(chunk)
                if not tokens:
                    continue
                chunk_id = f"{doc_id}#{chunk_index + 1}"
                conn.execute(
                    """
                    INSERT INTO chunks(chunk_id, doc_id, text, token_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                      doc_id = excluded.doc_id,
                      text = excluded.text,
                      token_count = excluded.token_count
                    """,
                    (chunk_id, doc_id, chunk, len(tokens)),
                )
                chunk_hash = _content_hash(chunk)
                ghost_payloads[chunk_hash] = (
                    chunk,
                    {
                        "kind": "chunk",
                        "doc_id": doc_id,
                        "chunk_id": chunk_id,
                        "path": str(path),
                        "token_count": len(tokens),
                        "source_type": source_type,
                    },
                )
                _write_event(event_file, conn, "chunk_indexed", chunk_id, {"doc_id": doc_id, "token_count": len(tokens)})
                flush.mark()
                for token in tokens:
                    node_id = _slug(token)
                    node_counts[node_id] += 1
                    node_meta.setdefault(
                        node_id,
                        {
                            "label": token,
                            "type": _node_type_for_token(token),
                            "confidence": 0.5,
                            "evidence_doc_ids": [],
                        },
                    )
                    if doc_id not in node_meta[node_id]["evidence_doc_ids"]:
                        node_meta[node_id]["evidence_doc_ids"].append(doc_id)
                    token_hash = _content_hash(token)
                    ghost_payloads[token_hash] = (
                        token,
                        {
                            "kind": "token",
                            "legacy_id": node_id,
                            "type": _node_type_for_token(token),
                            "doc_id": doc_id,
                            "source_type": source_type,
                        },
                    )
                    ghost_edge_counts[(token_hash, chunk_hash)] += 1
                for left, right in zip(tokens, tokens[1:]):
                    left_id = _slug(left)
                    right_id = _slug(right)
                    phrase_id = _phrase_node_id(left, right)
                    phrase_label = f"{left} {right}"
                    phrase_hash = _content_hash(phrase_label)
                    left_hash = _content_hash(left)
                    right_hash = _content_hash(right)
                    ghost_payloads[phrase_hash] = (
                        phrase_label,
                        {
                            "kind": "phrase",
                            "legacy_id": phrase_id,
                            "type": "phrase",
                            "doc_id": doc_id,
                            "source_type": source_type,
                        },
                    )
                    ghost_edge_counts[(left_hash, right_hash)] += 1
                    ghost_edge_counts[(left_hash, phrase_hash)] += 1
                    ghost_edge_counts[(phrase_hash, right_hash)] += 1
                    ghost_edge_counts[(phrase_hash, chunk_hash)] += 1
                    node_counts[phrase_id] += 1
                    node_meta.setdefault(
                        phrase_id,
                        {
                            "label": phrase_label,
                            "type": "phrase",
                            "confidence": 0.53,
                            "evidence_doc_ids": [],
                        },
                    )
                    if doc_id not in node_meta[phrase_id]["evidence_doc_ids"]:
                        node_meta[phrase_id]["evidence_doc_ids"].append(doc_id)
                    transitions[(left_id, right_id)] += 1
                    for key in [
                        (left_id, "precedes", right_id),
                        (left_id, "forms_phrase", phrase_id),
                        (phrase_id, "continues_as", right_id),
                    ]:
                        edge_counts[key] += 1
                        edge_docs[key].add(doc_id)
                        source_totals[key[0]] += 1
                        pair_totals[(key[0], key[2])] += 1
                for index, left in enumerate(tokens):
                    for right in tokens[index + 1 : index + 6]:
                        if left == right:
                            continue
                        left_id = _slug(left)
                        right_id = _slug(right)
                        left_hash = _content_hash(left)
                        right_hash = _content_hash(right)
                        ghost_edge_counts[(left_hash, right_hash)] += 1
                        cooccurs[(left_id, right_id)] += 1
                        key = (left_id, "co_occurs", right_id)
                        edge_counts[key] += 1
                        edge_docs[key].add(doc_id)
                        source_totals[left_id] += 1
                        pair_totals[(left_id, right_id)] += 1

    node_hashes: dict[str, str] = {}
    for node_id, count in node_counts.items():
        meta = node_meta.get(node_id, {"label": node_id, "type": "token", "confidence": 0.5, "evidence_doc_ids": []})
        label = str(meta.get("label") or node_id)
        node_hash = _content_hash(label)
        node_hashes[node_id] = node_hash
        evidence_doc_ids = sorted(set(str(doc) for doc in meta.get("evidence_doc_ids") or []))
        evidence_source_types = sorted({doc_source_types.get(str(doc), "local_corpus") for doc in evidence_doc_ids})
        ghost_payloads[node_hash] = (
            label,
            {
                "kind": "node",
                "legacy_id": node_id,
                "type": str(meta.get("type") or "token"),
                "count": int(count),
                "evidence_doc_ids": evidence_doc_ids,
                "source_type": evidence_source_types[0] if len(evidence_source_types) == 1 else ("mixed" if evidence_source_types else "local_corpus"),
                "source_types": evidence_source_types,
            },
        )
        confidence = min(0.98, float(meta.get("confidence") or 0.5) + math.log1p(count) * 0.035)
        conn.execute(
            """
            INSERT INTO nodes(node_id, label, type, count, confidence, evidence_doc_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
              label = excluded.label,
              type = excluded.type,
              count = MAX(nodes.count, excluded.count),
              confidence = MAX(nodes.confidence, excluded.confidence),
              evidence_doc_ids = excluded.evidence_doc_ids
            """,
            (
                node_id,
                label,
                str(meta.get("type") or "token"),
                int(count),
                round(confidence, 4),
                json.dumps(sorted(set(str(doc) for doc in meta.get("evidence_doc_ids") or [])), ensure_ascii=False),
            ),
        )
        flush.mark()

    for (source, relation, target), count in edge_counts.items():
        source_total = max(1, source_totals[source])
        pair_total = max(1, pair_totals[(source, target)])
        confidence = min(0.96, 0.42 + math.log1p(count) * 0.09 + len(edge_docs[(source, relation, target)]) * 0.03)
        source_hash = node_hashes.get(source)
        target_hash = node_hashes.get(target)
        if source_hash and target_hash:
            ghost_edge_counts[(source_hash, target_hash)] += int(count)
        conn.execute(
            """
            INSERT INTO edges(edge_id, source, relation, target, confidence, count, evidence_doc_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
              source = excluded.source,
              relation = excluded.relation,
              target = excluded.target,
              confidence = MAX(edges.confidence, excluded.confidence),
              count = MAX(edges.count, excluded.count),
              evidence_doc_ids = excluded.evidence_doc_ids
            """,
            (
                f"{source}:{relation}:{target}",
                source,
                relation,
                target,
                round(confidence, 4),
                int(count),
                json.dumps(sorted(edge_docs[(source, relation, target)]), ensure_ascii=False),
            ),
        )
        conn.execute(
            """
            INSERT INTO relation_stats(
              source, relation, target, count, p_target_given_source,
              p_relation_given_source_target, recency_weight, source_quality_weight,
              activation_weight, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, relation, target) DO UPDATE SET
              count = MAX(relation_stats.count, excluded.count),
              p_target_given_source = excluded.p_target_given_source,
              p_relation_given_source_target = excluded.p_relation_given_source_target,
              recency_weight = excluded.recency_weight,
              source_quality_weight = excluded.source_quality_weight,
              activation_weight = excluded.activation_weight,
              confidence = MAX(relation_stats.confidence, excluded.confidence)
            """,
            (
                source,
                relation,
                target,
                int(count),
                round(count / source_total, 6),
                round(count / pair_total, 6),
                1.0,
                1.0,
                1.0,
                round(confidence, 4),
            ),
        )
        flush.mark()

    transition_totals: Counter[str] = Counter()
    cooccur_totals: Counter[str] = Counter()
    for (source, _target), count in transitions.items():
        transition_totals[source] += count
    for (source, _target), count in cooccurs.items():
        cooccur_totals[source] += count
    for (source, target), count in transitions.items():
        conn.execute(
            """
            INSERT INTO token_transitions(source, target, count, probability)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, target) DO UPDATE SET
              count = MAX(token_transitions.count, excluded.count),
              probability = excluded.probability
            """,
            (source, target, int(count), round(count / max(1, transition_totals[source]), 6)),
        )
        flush.mark()
    for (source, target), count in cooccurs.items():
        conn.execute(
            """
            INSERT INTO cooccurrence_windows(source, target, count, probability)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, target) DO UPDATE SET
              count = MAX(cooccurrence_windows.count, excluded.count),
              probability = excluded.probability
            """,
            (source, target, int(count), round(count / max(1, cooccur_totals[source]), 6)),
        )
        flush.mark()

    degree_counts: Counter[str] = Counter()
    for source, _relation, target in edge_counts:
        degree_counts[source] += 1
        degree_counts[target] += 1
    event_count = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
    for node_id, count in node_counts.items():
        x, y, z = _projection(node_id, degree_counts[node_id], count)
        conn.execute(
            """
            INSERT INTO vector_rows(node_id, dim0, dim1, dim2, vector_source, trained_on_events)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
              dim0 = excluded.dim0,
              dim1 = excluded.dim1,
              dim2 = excluded.dim2,
              vector_source = excluded.vector_source,
              trained_on_events = MAX(vector_rows.trained_on_events, excluded.trained_on_events)
            """,
            (node_id, x, y, z, VECTOR_SOURCE, event_count),
        )
        flush.mark()

    ghost_degrees: Counter[str] = Counter()
    for (source_hash, target_hash), count in ghost_edge_counts.items():
        ghost_degrees[source_hash] += count
        ghost_degrees[target_hash] += count

    for hash_key, (raw_text, metadata) in ghost_payloads.items():
        count_hint = int(metadata.get("count") or metadata.get("token_count") or ghost_degrees[hash_key] or 1)
        _upsert_payload_vault(conn, hash_key, raw_text, metadata)
        _upsert_ghost_node(conn, hash_key, _projection(hash_key, ghost_degrees[hash_key], count_hint))
        flush.mark()

    for (source_hash, target_hash), count in ghost_edge_counts.items():
        source_total = max(1, ghost_degrees[source_hash])
        weight = min(1.0, max(0.0001, count / source_total))
        _upsert_ghost_edge(conn, source_hash, target_hash, weight)
        flush.mark()

    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("built_at", utc_now_iso()))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("ghost_shell", "active"))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("ghost_vector_source", GHOST_VECTOR_SOURCE))
    flush.flush()
    conn.commit()
    status = memory_status(memory_dir)
    conn.close()
    return {
        **status,
        "state": "completed",
        "db_path": str(paths.db_path),
        "event_log_path": str(paths.event_path),
        "llm_policy": {
            "external_llm": False,
            "local_quantized_llm": False,
            "pretrained_generation_weights": False,
        },
    }


def memory_status(memory_dir: str = "data/memory") -> dict[str, Any]:
    paths = _paths(memory_dir)
    if not paths.db_path.exists():
        return {
            "state": "idle",
            "db_path": str(paths.db_path),
            "event_log_path": str(paths.event_path),
            "document_count": 0,
            "chunk_count": 0,
            "node_count": 0,
            "edge_count": 0,
            "event_count": 0,
            "vector_count": 0,
            "transition_count": 0,
            "cooccurrence_count": 0,
            "phrase_count": 0,
            "predicate_count": 0,
            "ghost_hash_count": 0,
            "ghost_edge_count": 0,
            "payload_vault_count": 0,
            "ghost_shell": {"system_state": "GHOST SHELL EMPTY"},
            "built_at": None,
        }
    conn = _connect(paths.db_path)
    has_ghost_nodes = _table_exists(conn, "ghost_nodes")
    has_ghost_edges = _table_exists(conn, "ghost_edges")
    has_payload_vault = _table_exists(conn, "payload_vault")
    counts = {
        "document_count": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunk_count": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "node_count": conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
        "edge_count": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "event_count": conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0],
        "vector_count": conn.execute("SELECT COUNT(*) FROM vector_rows").fetchone()[0],
        "transition_count": conn.execute("SELECT COUNT(*) FROM token_transitions").fetchone()[0],
        "cooccurrence_count": conn.execute("SELECT COUNT(*) FROM cooccurrence_windows").fetchone()[0],
        "phrase_count": conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'phrase'").fetchone()[0],
        "predicate_count": conn.execute("SELECT COUNT(*) FROM nodes WHERE type IN ('predicate', 'verb')").fetchone()[0],
        "ghost_hash_count": conn.execute("SELECT COUNT(*) FROM ghost_nodes").fetchone()[0] if has_ghost_nodes else 0,
        "ghost_edge_count": conn.execute("SELECT COUNT(*) FROM ghost_edges").fetchone()[0] if has_ghost_edges else 0,
        "payload_vault_count": conn.execute("SELECT COUNT(*) FROM payload_vault").fetchone()[0] if has_payload_vault else 0,
    }
    built = conn.execute("SELECT value FROM meta WHERE key = 'built_at'").fetchone()
    conn.close()
    return {
        "state": "completed" if counts["event_count"] else "idle",
        "db_path": str(paths.db_path),
        "event_log_path": str(paths.event_path),
        "built_at": built["value"] if built else None,
        "vector_source": VECTOR_SOURCE if counts["vector_count"] else None,
        "ghost_shell": {
            "system_state": "GHOST SHELL ACTIVE" if counts["ghost_hash_count"] else "GHOST SHELL EMPTY",
            "control_plane_hashes": counts["ghost_hash_count"],
            "control_plane_edges": counts["ghost_edge_count"],
            "payload_vault_records": counts["payload_vault_count"],
            "control_plane": f"Loaded {counts['ghost_hash_count']} Schematic Hashes (Memory: Minimal)",
            "data_plane": "Vaulting Payloads to Edge Storage",
        },
        **counts,
    }


def export_graph(memory_dir: str = "data/memory", limit: int = 600) -> dict[str, Any]:
    paths = _paths(memory_dir)
    if not paths.db_path.exists():
        return {"nodes": [], "edges": [], "status": memory_status(memory_dir)}
    conn = _connect(paths.db_path)
    if _table_exists(conn, "ghost_nodes") and conn.execute("SELECT COUNT(*) FROM ghost_nodes").fetchone()[0] > 0:
        node_rows = conn.execute(
            """
            SELECT node_hash, dim0, dim1, dim2
            FROM ghost_nodes
            ORDER BY node_hash ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        visible_ids = {row["node_hash"] for row in node_rows}
        edge_rows = conn.execute(
            """
            SELECT source_hash, target_hash, weight
            FROM ghost_edges
            ORDER BY weight DESC
            LIMIT ?
            """,
            (limit * 4,),
        ).fetchall()
        status = memory_status(memory_dir)
        conn.close()
        nodes = [
            {
                "id": row["node_hash"],
                "node_hash": row["node_hash"],
                "label": f"ghost:{str(row['node_hash'])[:12]}",
                "type": "ghost_hash",
                "count": 1,
                "confidence": 0.5,
                "x": row["dim0"],
                "y": row["dim1"],
                "z": row["dim2"],
                "projection_source": GHOST_VECTOR_SOURCE,
                "payload_resolved": False,
            }
            for row in node_rows
        ]
        edges = [
            {
                "source": row["source_hash"],
                "target": row["target_hash"],
                "weight": row["weight"],
            }
            for row in edge_rows
            if row["source_hash"] in visible_ids and row["target_hash"] in visible_ids
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "status": status,
            "source": "ghost_topology_control_plane",
            "ghost_shell": status.get("ghost_shell"),
        }
    node_rows = conn.execute(
        """
        SELECT n.node_id, n.label, n.type, n.count, n.confidence, v.dim0, v.dim1, v.dim2
        FROM nodes n
        LEFT JOIN vector_rows v ON v.node_id = n.node_id
        ORDER BY n.count DESC, n.node_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    visible_ids = {row["node_id"] for row in node_rows}
    edge_rows = conn.execute(
        """
        SELECT source, relation, target, confidence, count
        FROM edges
        ORDER BY count DESC, confidence DESC
        LIMIT ?
        """,
        (limit * 4,),
    ).fetchall()
    conn.close()
    nodes = [
        {
            "id": row["node_id"],
            "label": row["label"],
            "type": row["type"],
            "count": row["count"],
            "confidence": row["confidence"],
            "x": row["dim0"],
            "y": row["dim1"],
            "z": row["dim2"],
            "projection_source": VECTOR_SOURCE if row["dim0"] is not None else "fallback_layout",
        }
        for row in node_rows
    ]
    edges = [
        {
            "source": row["source"],
            "relation": row["relation"],
            "target": row["target"],
            "confidence": row["confidence"],
            "count": row["count"],
        }
        for row in edge_rows
        if row["source"] in visible_ids and row["target"] in visible_ids
    ]
    return {"nodes": nodes, "edges": edges, "status": memory_status(memory_dir)}


def _seed_nodes(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    terms = _tokens(query)
    rows: list[sqlite3.Row] = []
    seen: set[str] = set()
    for term in terms:
        slug = _slug(term)
        candidates = conn.execute(
            """
            SELECT node_id, label, type, count, confidence
            FROM nodes
            WHERE node_id = ? OR lower(label) LIKE ?
            ORDER BY count DESC, confidence DESC
            LIMIT 8
            """,
            (slug, f"%{term.lower()}%"),
        ).fetchall()
        for row in candidates:
            if row["node_id"] not in seen:
                rows.append(row)
                seen.add(row["node_id"])
    if rows:
        return rows[:12]
    return conn.execute(
        "SELECT node_id, label, type, count, confidence FROM nodes ORDER BY count DESC, confidence DESC LIMIT 6"
    ).fetchall()


def activate_memory(query: str, memory_dir: str = "data/memory", max_nodes: int = 40, max_depth: int = 3) -> dict[str, Any]:
    paths = _paths(memory_dir)
    if not paths.db_path.exists():
        return {
            "query": query,
            "state": "no_memory",
            "active_nodes": [],
            "active_edges": [],
            "semantic_skeleton": [],
            "drift_report": drift_check(memory_dir),
        }
    conn = _connect(paths.db_path)
    seeds = _seed_nodes(conn, query)
    scores: dict[str, float] = {row["node_id"]: 1.0 + min(0.7, float(row["confidence"])) for row in seeds}
    frontier = [(row["node_id"], scores[row["node_id"]], 0) for row in seeds]
    active_edges: dict[tuple[str, str, str], float] = {}

    while frontier:
        node_id, base_score, depth = frontier.pop(0)
        if depth >= max_depth or len(scores) >= max_nodes * 2:
            continue
        rows = conn.execute(
            """
            SELECT rs.source, rs.relation, rs.target, rs.count, rs.p_target_given_source, rs.confidence, n.label, n.type
            FROM relation_stats rs
            JOIN nodes n ON n.node_id = rs.target
            WHERE rs.source = ?
            ORDER BY rs.confidence DESC, rs.p_target_given_source DESC, rs.count DESC
            LIMIT 12
            """,
            (node_id,),
        ).fetchall()
        for row in rows:
            edge_score = base_score * (0.35 + float(row["confidence"])) * (0.25 + float(row["p_target_given_source"]))
            edge_score = edge_score / (1 + depth * 0.65)
            key = (row["source"], row["relation"], row["target"])
            active_edges[key] = max(active_edges.get(key, 0.0), edge_score)
            if edge_score > scores.get(row["target"], 0.0):
                scores[row["target"]] = edge_score
                frontier.append((row["target"], edge_score, depth + 1))

    top_ids = [node_id for node_id, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:max_nodes]]
    if not top_ids:
        conn.close()
        return {"query": query, "state": "empty", "active_nodes": [], "active_edges": [], "semantic_skeleton": []}

    placeholders = ",".join("?" for _ in top_ids)
    node_rows = conn.execute(
        f"""
        SELECT n.node_id, n.label, n.type, n.count, n.confidence, v.dim0, v.dim1, v.dim2
        FROM nodes n LEFT JOIN vector_rows v ON v.node_id = n.node_id
        WHERE n.node_id IN ({placeholders})
        """,
        top_ids,
    ).fetchall()
    node_by_id = {row["node_id"]: row for row in node_rows}
    active_nodes = [
        {
            "id": node_id,
            "label": node_by_id[node_id]["label"],
            "type": node_by_id[node_id]["type"],
            "activation_score": round(scores[node_id], 5),
            "confidence": node_by_id[node_id]["confidence"],
            "projection_3d": [node_by_id[node_id]["dim0"], node_by_id[node_id]["dim1"], node_by_id[node_id]["dim2"]],
        }
        for node_id in top_ids
        if node_id in node_by_id
    ]
    active_id_set = {node["id"] for node in active_nodes}
    active_edge_list = [
        {
            "source": source,
            "relation": relation,
            "target": target,
            "activation_score": round(score, 5),
        }
        for (source, relation, target), score in sorted(active_edges.items(), key=lambda item: -item[1])
        if source in active_id_set and target in active_id_set
    ][: max_nodes * 2]
    skeleton = [
        {"role": "seed" if index < len(seeds) else "activated", "node": node["id"], "label": node["label"], "score": node["activation_score"]}
        for index, node in enumerate(active_nodes[:12])
    ]
    created_at = utc_now_iso()
    for node in active_nodes[:24]:
        conn.execute(
            "INSERT INTO activation_events(query, node_id, score, created_at) VALUES (?, ?, ?, ?)",
            (query, node["id"], node["activation_score"], created_at),
        )
    result = {
        "query": query,
        "state": "completed",
        "seed_nodes": [row["node_id"] for row in seeds],
        "active_nodes": active_nodes,
        "active_edges": active_edge_list,
        "semantic_skeleton": skeleton,
        "activation_policy": {
            "max_nodes": max_nodes,
            "max_depth": max_depth,
            "external_llm": False,
            "local_quantized_llm": False,
            "pretrained_generation_weights": False,
        },
        "drift_report": drift_check(memory_dir),
    }
    conn.execute(
        "INSERT INTO query_traces(query, result_json, created_at) VALUES (?, ?, ?)",
        (query, json.dumps(result, ensure_ascii=False), created_at),
    )
    conn.commit()
    conn.close()
    return result


def drift_check(memory_dir: str = "data/memory") -> dict[str, Any]:
    status = memory_status(memory_dir)
    violations: list[str] = []
    warnings: list[str] = []
    if status["state"] != "completed":
        violations.append("memory_not_built")
    if status.get("event_count", 0) <= 0:
        violations.append("no_memory_events")
    if status.get("node_count", 0) > 0 and status.get("vector_count", 0) <= 0:
        violations.append("missing_local_vectors")
    if status.get("node_count", 0) > 0 and status.get("transition_count", 0) <= 0:
        violations.append("missing_token_transition_graph")
    if status.get("edge_count", 0) > 0 and not Path(status["event_log_path"]).exists():
        violations.append("missing_event_log")
    if 0 < status.get("node_count", 0) < 10:
        warnings.append("memory_too_small_for_generation")
    if status.get("node_count", 0) >= 10 and status.get("phrase_count", 0) <= 0:
        warnings.append("missing_phrase_nodes")
    if status.get("node_count", 0) >= 10 and status.get("predicate_count", 0) <= 0:
        warnings.append("predicate_nodes_not_detected")
    report = {
        "state": "failed" if violations else "warning" if warnings else "passed",
        "checked_at": utc_now_iso(),
        "next_check_seconds": 60,
        "violations": violations,
        "warnings": warnings,
        "constraints": {
            "external_llm": False,
            "local_quantized_llm": False,
            "pretrained_generation_weights": False,
            "template_only_answers": False,
        },
        "status": status,
    }
    return report
