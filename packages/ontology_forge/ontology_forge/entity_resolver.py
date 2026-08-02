from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


BGE_M3_MODEL_NAME = "BAAI/bge-m3"
DEFAULT_VECTOR_DIM = 96
DEFAULT_SIMILARITY_THRESHOLD = 0.88
DEFAULT_EMA_ALPHA = 0.12


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _json_list(value: str | None) -> list[Any]:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


class ContextualEmbeddingProvider:
    """BGE-m3 first, deterministic contextual fallback second.

    The fallback keeps local tests and offline installs functional. The caller
    passes a marked entity plus its sentence/window, so polysemy changes the
    vector without collapsing every entity in the same sentence into one node.
    """

    def __init__(self, model_name: str | None = None, dimension: int = DEFAULT_VECTOR_DIM) -> None:
        self.model_name = model_name or os.getenv("HOMAGE_EMBEDDING_MODEL") or BGE_M3_MODEL_NAME
        self.dimension = max(32, int(os.getenv("HOMAGE_FALLBACK_EMBED_DIM", str(dimension))))
        self.provider = "deterministic-context-hash"
        self._model: Any | None = None
        self._load_optional_model()

    def _load_optional_model(self) -> None:
        if os.getenv("HOMAGE_DISABLE_BGE_M3", "").lower() in {"1", "true", "yes"}:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name)
            self.provider = f"sentence-transformers:{self.model_name}"
            return
        except Exception:
            pass
        try:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore

            self._model = BGEM3FlagModel(self.model_name, use_fp16=False)
            self.provider = f"flag-embedding:{self.model_name}"
        except Exception:
            self._model = None

    def embed(self, context_text: str) -> list[float]:
        text = " ".join(context_text.strip().split())
        if not text:
            text = "empty-context"
        if self._model is not None:
            if self.provider.startswith("sentence-transformers"):
                vector = self._model.encode([text], normalize_embeddings=True)[0]
                return [float(value) for value in vector]
            output = self._model.encode([text], return_dense=True)
            vector = output["dense_vecs"][0]
            return _normalize([float(value) for value in vector])
        return self._fallback_embed(text)

    def _fallback_embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        lowered = text.lower()
        tokens = [token for token in lowered.replace("\n", " ").split(" ") if token]
        features: list[str] = []
        features.extend(tokens)
        features.extend(f"{left}->{right}" for left, right in zip(tokens, tokens[1:]))
        for token in tokens:
            if len(token) >= 3:
                features.extend(token[index : index + 3] for index in range(len(token) - 2))
        for feature in features or [lowered]:
            digest = hashlib.blake2b(feature.encode("utf-8", errors="ignore"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)


@dataclass
class ConceptRecord:
    concept_id: str
    primary_name: str
    aliases: list[str]
    context_vector: list[float]
    count: int
    created_at: str
    updated_at: str


class EntityResolver:
    def __init__(
        self,
        db_path: str | Path,
        *,
        embedding_provider: ContextualEmbeddingProvider | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ema_alpha: float = DEFAULT_EMA_ALPHA,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider or ContextualEmbeddingProvider()
        self.similarity_threshold = float(os.getenv("HOMAGE_ENTITY_SIMILARITY", similarity_threshold))
        self.ema_alpha = max(0.01, min(0.5, float(os.getenv("HOMAGE_ENTITY_EMA_ALPHA", ema_alpha))))
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()
        self._cache = self._load_cache()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator["EntityResolver"]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self
            self.conn.commit()
            self._cache = self._load_cache()
        except Exception:
            self.conn.rollback()
            raise

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS concepts (
              concept_id TEXT PRIMARY KEY,
              primary_name TEXT NOT NULL,
              aliases_json TEXT NOT NULL,
              context_vector_json TEXT NOT NULL,
              count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS concept_aliases (
              alias_key TEXT NOT NULL,
              concept_id TEXT NOT NULL,
              alias TEXT NOT NULL,
              PRIMARY KEY(alias_key, concept_id),
              FOREIGN KEY(concept_id) REFERENCES concepts(concept_id)
            );
            CREATE INDEX IF NOT EXISTS idx_concept_aliases_key ON concept_aliases(alias_key);
            """
        )
        self.conn.commit()

    def _load_cache(self) -> list[ConceptRecord]:
        rows = self.conn.execute(
            """
            SELECT concept_id, primary_name, aliases_json, context_vector_json, count, created_at, updated_at
            FROM concepts
            ORDER BY updated_at DESC
            """
        ).fetchall()
        records: list[ConceptRecord] = []
        for row in rows:
            records.append(
                ConceptRecord(
                    concept_id=str(row["concept_id"]),
                    primary_name=str(row["primary_name"]),
                    aliases=[str(item) for item in _json_list(row["aliases_json"])],
                    context_vector=[float(item) for item in _json_list(row["context_vector_json"])],
                    count=int(row["count"] or 0),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
            )
        return records

    @staticmethod
    def alias_key(alias: str) -> str:
        return " ".join(alias.lower().strip().split())

    def _best_match(self, raw_name: str, vector: list[float]) -> tuple[ConceptRecord | None, float]:
        alias_key = self.alias_key(raw_name)
        alias_matches = self.conn.execute(
            """
            SELECT concept_id FROM concept_aliases
            WHERE alias_key = ?
            LIMIT 32
            """,
            (alias_key,),
        ).fetchall()
        preferred_ids = {str(row["concept_id"]) for row in alias_matches}
        deterministic_fallback = self.embedding_provider.provider == "deterministic-context-hash"
        best: ConceptRecord | None = None
        best_score = 0.0
        for record in self._cache:
            if deterministic_fallback and record.concept_id not in preferred_ids:
                continue
            score = cosine_similarity(vector, record.context_vector)
            if record.concept_id in preferred_ids:
                score += 0.04
            if score > best_score:
                best = record
                best_score = score
        return best, best_score

    def resolve(self, raw_name: str, context_text: str, *, preferred_name: str | None = None) -> dict[str, Any]:
        name = " ".join(raw_name.strip().split())
        if not name:
            raise ValueError("raw_name must not be empty")
        marked_context = f"ENTITY: {name}\nCONTEXT: {context_text}"
        contextual_vector = self.embedding_provider.embed(marked_context)
        match, score = self._best_match(name, contextual_vector)
        if match and score >= self.similarity_threshold:
            return self._merge(match, name, contextual_vector, score)
        return self._create(preferred_name or name, name, contextual_vector)

    def _merge(self, record: ConceptRecord, alias: str, vector: list[float], score: float) -> dict[str, Any]:
        now = utc_now_iso()
        aliases = list(dict.fromkeys([*record.aliases, alias]))
        old_weight = 1.0 - self.ema_alpha
        merged_vector = _normalize([
            old_weight * old + self.ema_alpha * new
            for old, new in zip(record.context_vector, vector)
        ])
        count = record.count + 1
        self.conn.execute(
            """
            UPDATE concepts
            SET aliases_json = ?, context_vector_json = ?, count = ?, updated_at = ?
            WHERE concept_id = ?
            """,
            (
                json.dumps(aliases, ensure_ascii=False),
                json.dumps(merged_vector),
                count,
                now,
                record.concept_id,
            ),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO concept_aliases(alias_key, concept_id, alias)
            VALUES (?, ?, ?)
            """,
            (self.alias_key(alias), record.concept_id, alias),
        )
        record.aliases = aliases
        record.context_vector = merged_vector
        record.count = count
        record.updated_at = now
        return {
            "concept_id": record.concept_id,
            "primary_name": record.primary_name,
            "aliases": aliases,
            "context_vector": merged_vector,
            "resolution": "merged",
            "similarity": round(score, 5),
        }

    def _create(self, primary_name: str, alias: str, vector: list[float]) -> dict[str, Any]:
        now = utc_now_iso()
        concept_id = str(uuid.uuid4())
        aliases = [alias]
        self.conn.execute(
            """
            INSERT INTO concepts(concept_id, primary_name, aliases_json, context_vector_json, count, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                concept_id,
                primary_name,
                json.dumps(aliases, ensure_ascii=False),
                json.dumps(vector),
                now,
                now,
            ),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO concept_aliases(alias_key, concept_id, alias)
            VALUES (?, ?, ?)
            """,
            (self.alias_key(alias), concept_id, alias),
        )
        record = ConceptRecord(concept_id, primary_name, aliases, vector, 1, now, now)
        self._cache.append(record)
        return {
            "concept_id": concept_id,
            "primary_name": primary_name,
            "aliases": aliases,
            "context_vector": vector,
            "resolution": "created",
            "similarity": 0.0,
        }

    def export_concepts(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT concept_id, primary_name, aliases_json, context_vector_json, count, created_at, updated_at
            FROM concepts
            ORDER BY count DESC, primary_name ASC
            """
        ).fetchall()
        return [
            {
                "concept_id": str(row["concept_id"]),
                "primary_name": str(row["primary_name"]),
                "aliases": [str(item) for item in _json_list(row["aliases_json"])],
                "context_vector": [float(item) for item in _json_list(row["context_vector_json"])],
                "count": int(row["count"] or 0),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        ]
