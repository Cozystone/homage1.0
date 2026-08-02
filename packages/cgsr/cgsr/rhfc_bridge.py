"""CGSR-to-RHFC bridge for controlled construction retrieval.

This module is the first CGSR caller of RHFC.  It does not modify RHFC state or
surface_brain; it only uses RHFC's public hypervector and sharded cleanup-memory
interfaces to store vetted construction families.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
import time
from typing import Any, Iterable

import numpy as np

from .morphology import lemmatize_predicate
from .query_skeleton import canonical_query_tokens

try:  # pragma: no cover - exercised in environments where rhfc is installed
    from rhfc import HashShardRouter, HyperVector, ShardedCleanupMemory, bundle, random_bipolar
    from rhfc.compression import CompressionSpec, compress_hypervector
    from rhfc.hypervector import cosine_similarity
except ModuleNotFoundError:  # local monorepo checkout without package install
    RHFC_ROOT = Path(__file__).resolve().parents[2] / "rhfc"
    if str(RHFC_ROOT) not in sys.path:
        sys.path.insert(0, str(RHFC_ROOT))
    from rhfc import HashShardRouter, HyperVector, ShardedCleanupMemory, bundle, random_bipolar
    from rhfc.compression import CompressionSpec, compress_hypervector
    from rhfc.hypervector import cosine_similarity

DIMENSION = 512
PRECISION = "int8"


@dataclass(frozen=True)
class ConstructionRhfcRecord:
    """A construction row encoded for RHFC cleanup memory."""

    family_id: str
    canonical_form: str
    metadata: dict[str, Any]
    vector: HyperVector
    compressed_bytes: int


@dataclass
class ConstructionRhfcStore:
    """Stored CGSR constructions plus RHFC sharded cleanup memory."""

    memory: ShardedCleanupMemory
    records: list[ConstructionRhfcRecord]
    build_ms: float
    logical_storage_bytes: int

    def retrieve_by_vector(self, query: HyperVector, *, query_all_shards: bool = True) -> dict[str, Any]:
        """Recall the closest stored construction for a query vector."""

        started = time.perf_counter()
        result = self.memory.recall_with_metadata(query, query_all_shards=query_all_shards)
        return {
            "family_id": result.metadata.get("family_id"),
            "canonical_form": result.metadata.get("canonical_form"),
            "score": round(result.score, 6),
            "shard_id": result.shard_id,
            "pattern_index": result.pattern_index,
            "queried_shards": result.queried_shards,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 4),
            "metadata": result.metadata,
        }

    def rank_by_vector(
        self,
        query: HyperVector,
        *,
        limit: int = 5,
        predicate: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return bounded nearest construction candidates by cosine score.

        RHFC cleanup memory gives a top-1 recall result.  CGSR needs a small
        top-k view so checked retrieval can abstain when the top candidate is
        predicate-incompatible or the score margin is too narrow.
        """

        rows = []
        normalized_predicate = normalize_predicate(predicate or "")
        for record in self.records:
            record_predicate = predicate_from_canonical(record.canonical_form)
            if normalized_predicate and record_predicate != normalized_predicate:
                continue
            rows.append(
                {
                    "family_id": record.family_id,
                    "canonical_form": record.canonical_form,
                    "score": float(cosine_similarity(query, record.vector)),
                    "metadata": record.metadata,
                }
            )
        rows.sort(key=lambda item: item["score"], reverse=True)
        return [
            {
                **row,
                "score": round(row["score"], 6),
                "predicate": predicate_from_canonical(row["canonical_form"]),
            }
            for row in rows[: max(1, limit)]
        ]

    def retrieve_skeleton(self, skeleton: dict[str, str]) -> dict[str, Any]:
        """Encode a semantic skeleton and recall the nearest construction."""

        return self.retrieve_by_vector(encode_query_skeleton(skeleton), query_all_shards=True)

    def predicate_inventory(self) -> set[str]:
        """Return normalized predicates present in stored constructions."""

        return {
            token.removeprefix("PREDICATE:")
            for record in self.records
            for token in record.canonical_form.split()
            if token.startswith("PREDICATE:")
        }

    def retrieve_skeleton_checked(
        self,
        skeleton: dict[str, str],
        *,
        min_margin: float = 0.0,
        require_argument_roles: bool = True,
    ) -> dict[str, Any]:
        """Recall only when predicate and broad argument roles are compatible.

        This prevents a missing predicate from returning a confident but
        semantically unrelated construction.
        """

        predicate = normalize_predicate(skeleton.get("predicate", ""))
        if predicate and predicate not in self.predicate_inventory():
            return {
                "matched": False,
                "reason": "predicate_not_in_rhfc_store",
                "query_predicate": predicate,
                "canonical_form": None,
                "family_id": None,
                "score": 0.0,
                "margin": 0.0,
                "top_candidates": [],
                "latency_ms": 0.0,
            }
        started = time.perf_counter()
        query_vector = encode_query_skeleton(skeleton)
        ranked = self.rank_by_vector(query_vector, limit=3)
        if not ranked:
            return {
                "matched": False,
                "reason": "empty_rhfc_store",
                "query_predicate": predicate,
                "canonical_form": None,
                "family_id": None,
                "score": 0.0,
                "margin": 0.0,
                "top_candidates": [],
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 4),
            }
        top = ranked[0]
        second_score = ranked[1]["score"] if len(ranked) > 1 else 0.0
        margin = round(float(top["score"]) - float(second_score), 6)
        if predicate and top["predicate"] != predicate:
            predicate_ranked = self.rank_by_vector(query_vector, limit=len(self.records), predicate=predicate)
            for candidate in predicate_ranked:
                candidate_argument_check = argument_compatibility(skeleton, candidate["canonical_form"])
                if require_argument_roles and not candidate_argument_check["compatible"]:
                    continue
                result = dict(candidate)
                result["matched"] = True
                result["reason"] = "predicate_constrained_recall_checked"
                result["query_predicate"] = predicate
                result["retrieved_predicate"] = candidate["predicate"]
                result["margin"] = margin
                result["argument_check"] = candidate_argument_check
                result["top_candidates"] = ranked
                result["predicate_candidates_considered"] = len(predicate_ranked)
                result["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 4)
                return result
            best_same_predicate = predicate_ranked[0] if predicate_ranked else None
            argument_check = (
                argument_compatibility(skeleton, best_same_predicate["canonical_form"])
                if best_same_predicate
                else None
            )
            return {
                "matched": False,
                "reason": "argument_role_mismatch_abstain" if best_same_predicate else "predicate_mismatch_abstain",
                "query_predicate": predicate,
                "canonical_form": best_same_predicate["canonical_form"] if best_same_predicate else top["canonical_form"],
                "family_id": best_same_predicate["family_id"] if best_same_predicate else top["family_id"],
                "score": best_same_predicate["score"] if best_same_predicate else top["score"],
                "retrieved_predicate": predicate if best_same_predicate else top["predicate"],
                "margin": margin,
                "argument_check": argument_check,
                "top_candidates": ranked,
                "predicate_candidates_considered": len(predicate_ranked),
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 4),
            }
        argument_check = argument_compatibility(skeleton, top["canonical_form"])
        if require_argument_roles and not argument_check["compatible"]:
            return {
                "matched": False,
                "reason": "argument_role_mismatch_abstain",
                "query_predicate": predicate,
                "canonical_form": top["canonical_form"],
                "family_id": top["family_id"],
                "score": top["score"],
                "retrieved_predicate": top["predicate"],
                "margin": margin,
                "argument_check": argument_check,
                "top_candidates": ranked,
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 4),
            }
        if margin < min_margin:
            return {
                "matched": False,
                "reason": "low_margin_abstain",
                "query_predicate": predicate,
                "canonical_form": top["canonical_form"],
                "family_id": top["family_id"],
                "score": top["score"],
                "retrieved_predicate": top["predicate"],
                "margin": margin,
                "top_candidates": ranked,
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 4),
            }
        result = dict(top)
        result["matched"] = True
        result["reason"] = "rhfc_recall_checked"
        result["query_predicate"] = predicate
        result["retrieved_predicate"] = top["predicate"]
        result["margin"] = margin
        result["argument_check"] = argument_check
        result["top_candidates"] = ranked
        result["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 4)
        return result

    def storage_metrics(self) -> dict[str, Any]:
        """Return measured construction store costs."""

        float_matrix_bytes = sum(record.vector.values.nbytes for record in self.records)
        return {
            "record_count": len(self.records),
            "dimension": DIMENSION,
            "precision": PRECISION,
            "logical_int8_bytes": self.logical_storage_bytes,
            "logical_int8_kib": round(self.logical_storage_bytes / 1024, 4),
            "runtime_vector_bytes": int(float_matrix_bytes),
            "runtime_vector_kib": round(float_matrix_bytes / 1024, 4),
            "shard_counts": self.memory.shard_counts(),
            "build_ms": round(self.build_ms, 4),
        }


def _seed_for_token(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def _token_vector(token: str) -> HyperVector:
    return random_bipolar(DIMENSION, seed=_seed_for_token(token))


def _canonical_tokens(canonical_form: str) -> list[str]:
    return [token for token in str(canonical_form or "").split() if token.strip()]


def normalize_predicate(predicate: str) -> str:
    """Normalize a Korean predicate to a small dictionary form."""

    return lemmatize_predicate(str(predicate or "").strip())


def predicate_from_canonical(canonical_form: str) -> str:
    """Extract a normalized predicate token from a canonical construction."""

    for token in str(canonical_form or "").split():
        if token.startswith("PREDICATE:"):
            return normalize_predicate(token.removeprefix("PREDICATE:"))
    return ""


def argument_roles_from_canonical(canonical_form: str) -> set[str]:
    """Extract broad case-role markers from a canonical construction."""

    roles: set[str] = set()
    for token in str(canonical_form or "").split():
        if token in {"TOPIC", "SUBJ", "OBJ"}:
            roles.add(token)
        elif token.startswith("ADVL:"):
            roles.add("ADVL")
    return roles


def query_argument_roles(skeleton: dict[str, str]) -> set[str]:
    """Infer broad query argument roles from the current meaning skeleton.

    The Stage 3.1 skeleton format does not preserve exact Korean case particles.
    We therefore infer only broad roles: a concept supplies an unspecified
    argument, and an object supplies an object-like dependent that can match OBJ
    or ADVL in construction frames.
    """

    case_roles = skeleton.get("case_roles")
    if isinstance(case_roles, list) and case_roles:
        roles = set()
        for row in case_roles:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "")
            marker = str(row.get("marker") or "")
            if role in {"SUBJ", "TOPIC", "OBJ"}:
                roles.add(role)
            elif role == "ADVL":
                roles.add(f"ADVL:{marker}" if marker else "ADVL")
        return roles
    roles: set[str] = set()
    if str(skeleton.get("concept") or "").strip():
        roles.add("ANY_ARGUMENT")
    if str(skeleton.get("object") or "").strip():
        roles.add("OBJECT_DEP")
    return roles


def argument_compatibility(skeleton: dict[str, str], canonical_form: str) -> dict[str, Any]:
    """Check broad case-role compatibility between query and construction."""

    query_roles = query_argument_roles(skeleton)
    construction_roles = argument_roles_from_canonical(canonical_form)
    construction_tokens = set(str(canonical_form or "").split())
    exact_roles = {role for role in query_roles if role in {"TOPIC", "SUBJ", "OBJ"} or role.startswith("ADVL")}
    if exact_roles:
        def _role_ok(role: str) -> bool:
            if role in {"TOPIC", "SUBJ"}:
                return bool(construction_roles & {"TOPIC", "SUBJ"})
            if role == "OBJ":
                return "OBJ" in construction_roles
            if role.startswith("ADVL:"):
                return role in construction_tokens
            if role == "ADVL":
                return "ADVL" in construction_roles
            return False

        role_results = {role: _role_ok(role) for role in sorted(exact_roles)}
        compatible = all(role_results.values())
        return {
            "compatible": compatible,
            "query_roles": sorted(query_roles),
            "construction_roles": sorted(construction_roles),
            "construction_tokens": sorted(construction_tokens),
            "role_results": role_results,
            "topic_compatible": role_results.get("TOPIC", role_results.get("SUBJ", True)),
            "object_dependent_compatible": role_results.get("OBJ", True) and all(
                value for role, value in role_results.items() if role.startswith("ADVL")
            ),
            "strict_exact_match": compatible,
        }
    topic_ok = "ANY_ARGUMENT" not in query_roles or bool(construction_roles & {"TOPIC", "SUBJ", "OBJ", "ADVL"})
    object_ok = "OBJECT_DEP" not in query_roles or bool(construction_roles & {"OBJ", "ADVL"})
    return {
        "compatible": bool(topic_ok and object_ok),
        "query_roles": sorted(query_roles),
        "construction_roles": sorted(construction_roles),
        "topic_compatible": topic_ok,
        "object_dependent_compatible": object_ok,
        "strict_exact_match": bool(
            ("ANY_ARGUMENT" not in query_roles or bool(construction_roles & {"TOPIC", "SUBJ"}))
            and ("OBJECT_DEP" not in query_roles or "OBJ" in construction_roles)
        ),
    }


def _head(text: str) -> str:
    tokens = [token for token in str(text or "").split() if token.strip()]
    return tokens[-1] if tokens else ""


def encode_canonical_form(canonical_form: str) -> HyperVector:
    """Encode a construction canonical form into a deterministic hypervector."""

    tokens = _canonical_tokens(canonical_form)
    if not tokens:
        tokens = ["EMPTY_CONSTRUCTION"]
    vectors = [_token_vector(f"CGSR::{token}") for token in tokens]
    vectors.extend(
        _token_vector(f"CGSR::ORDER::{left}>{right}")
        for left, right in zip(tokens, tokens[1:])
    )
    vectors.append(_token_vector("CGSR::CONSTRUCTION"))
    return bundle(vectors).bipolarized()


def encode_construction(family: dict[str, Any]) -> HyperVector:
    """Encode one strict candidate family based on its canonical form."""

    row = family.get("row") if isinstance(family, dict) else None
    canonical = str((row or family).get("canonical_form") or "")
    return encode_canonical_form(canonical)


def encode_query_skeleton(skeleton: dict[str, str]) -> HyperVector:
    """Encode a meaning skeleton into the same construction space."""

    predicate = normalize_predicate(skeleton.get("predicate", ""))
    tokens = canonical_query_tokens(skeleton)
    if not tokens:
        tokens = ["TOPIC", "OBJ"]
    if "case_roles" not in skeleton:
        obj_head = _head(skeleton.get("object", ""))
        if obj_head:
            tokens.append(f"HEAD:{obj_head}")
    if predicate:
        tokens.append(f"PREDICATE:{predicate}")
    return bundle([_token_vector(f"CGSR::{token}") for token in tokens] + [_token_vector("CGSR::CONSTRUCTION")]).bipolarized()


def _metadata_for_family(family: dict[str, Any]) -> dict[str, Any]:
    row = dict(family.get("row") or {})
    return {
        "family_id": family.get("family_id") or row.get("family_id"),
        "canonical_form": row.get("canonical_form"),
        "priority_score": family.get("priority_score"),
        "member_count": row.get("member_count"),
        "sample_examples": row.get("sample_examples", [])[:2],
    }


def store_constructions(families: Iterable[dict[str, Any]], *, shard_count: int = 4) -> ConstructionRhfcStore:
    """Store vetted CGSR construction families in RHFC sharded cleanup memory."""

    started = time.perf_counter()
    rows = list(families)
    memory = ShardedCleanupMemory(
        dim=DIMENSION,
        router=HashShardRouter(shard_count=max(1, shard_count), metadata_key="family_id"),
        max_patterns_per_shard=2048,
    )
    spec = CompressionSpec(dim=DIMENSION, precision=PRECISION)
    records: list[ConstructionRhfcRecord] = []
    logical_storage_bytes = 0
    for family in rows:
        vector = encode_construction(family)
        compressed = compress_hypervector(vector, spec)
        metadata = _metadata_for_family(family)
        memory.store(vector, metadata)
        compressed_bytes = int(compressed.nbytes)
        logical_storage_bytes += compressed_bytes
        records.append(
            ConstructionRhfcRecord(
                family_id=str(metadata["family_id"]),
                canonical_form=str(metadata["canonical_form"]),
                metadata=metadata,
                vector=vector,
                compressed_bytes=compressed_bytes,
            )
        )
    return ConstructionRhfcStore(
        memory=memory,
        records=records,
        build_ms=(time.perf_counter() - started) * 1000.0,
        logical_storage_bytes=logical_storage_bytes,
    )


def exact_recall_accuracy(store: ConstructionRhfcStore) -> dict[str, Any]:
    """Measure whether stored canonical vectors recall themselves."""

    mistakes = []
    scores = []
    for record in store.records:
        result = store.retrieve_by_vector(record.vector)
        scores.append(float(result["score"]))
        if result["family_id"] != record.family_id:
            mistakes.append(
                {
                    "expected": record.family_id,
                    "actual": result["family_id"],
                    "expected_canonical": record.canonical_form,
                    "actual_canonical": result["canonical_form"],
                    "score": result["score"],
                }
            )
    return {
        "total": len(store.records),
        "correct": len(store.records) - len(mistakes),
        "accuracy": round((len(store.records) - len(mistakes)) / max(1, len(store.records)), 4),
        "min_score": round(min(scores), 6) if scores else None,
        "mean_score": round(float(np.mean(scores)), 6) if scores else None,
        "confusions": mistakes[:20],
    }


def near_duplicate_pairs(records: list[ConstructionRhfcRecord], *, limit: int = 10) -> list[tuple[ConstructionRhfcRecord, ConstructionRhfcRecord]]:
    """Return similar-but-distinct construction pairs by shared predicate."""

    by_predicate: dict[str, list[ConstructionRhfcRecord]] = {}
    for record in records:
        predicate = next((token for token in record.canonical_form.split() if token.startswith("PREDICATE:")), "")
        if predicate:
            by_predicate.setdefault(predicate, []).append(record)
    pairs = []
    for rows in by_predicate.values():
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=lambda item: item.canonical_form)
        for left, right in zip(rows, rows[1:]):
            if left.canonical_form != right.canonical_form:
                pairs.append((left, right))
            if len(pairs) >= limit:
                return pairs
    return pairs


def check_near_duplicate_confusion(store: ConstructionRhfcStore, *, limit: int = 10) -> dict[str, Any]:
    """Check whether near-duplicate construction pairs confuse exact RHFC recall."""

    cases = []
    confusion_count = 0
    for left, right in near_duplicate_pairs(store.records, limit=limit):
        left_result = store.retrieve_by_vector(left.vector)
        right_result = store.retrieve_by_vector(right.vector)
        pair_confused = left_result["family_id"] != left.family_id or right_result["family_id"] != right.family_id
        confusion_count += int(pair_confused)
        cases.append(
            {
                "left": left.canonical_form,
                "right": right.canonical_form,
                "cosine": round(cosine_similarity(left.vector, right.vector), 6),
                "left_recall": left_result,
                "right_recall": right_result,
                "confused": pair_confused,
            }
        )
    return {
        "pair_count": len(cases),
        "confusion_count": confusion_count,
        "confusion_rate": round(confusion_count / max(1, len(cases)), 4),
        "cases": cases,
    }
