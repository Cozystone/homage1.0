from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .graph_store import DEFAULT_MEMORY_DIR, _connect_readonly, _table_exists


DEFAULT_CONTRADICTION_THRESHOLD = 0.72
DEFAULT_TRUST_PENALTY = 0.1
DEFAULT_TRUST_STORE = Path("data/network/peer_trust.json")

SYMMETRIC_RELATIONS = {
    "related",
    "relates",
    "related_to",
    "similar",
    "similar_to",
    "connected",
    "connected_to",
    "cooccurs",
    "co_occurs",
    "cooccurs_with",
}

INVERSE_RELATIONS = {
    "parent": "child",
    "child": "parent",
    "contains": "part_of",
    "part_of": "contains",
    "before": "after",
    "after": "before",
    "causes": "caused_by",
    "caused_by": "causes",
    "uses": "used_by",
    "used_by": "uses",
    "depends_on": "required_by",
    "required_by": "depends_on",
}

# Fallback kept for resilience; the live value is derived from the data sidecar
# data/ontology/relation_type_schema.jsonl (4D BLOCKER #1: functional relations
# are declared as versioned DATA, not a hand-coded code constant). If the sidecar
# is missing/unreadable, behaviour falls back to this set unchanged.
_FALLBACK_FUNCTIONAL_RELATIONS = {
    "parent",
    "child",
    "born_in",
    "located_in",
    "founded_in",
    "capital_of",
    "part_of",
}

try:
    from .relation_type_schema import functional_relations as _functional_relations
except ImportError:
    # loader module genuinely unavailable -> safe fallback
    FUNCTIONAL_RELATIONS = _FALLBACK_FUNCTIONAL_RELATIONS
else:
    # Codex review: only a MISSING/EMPTY sidecar may fall back silently (loader
    # returns an empty set -> `or _FALLBACK`). An INVALID sidecar (bad JSON,
    # forbidden instance field, invalid temporal_policy) raises here and is
    # intentionally NOT caught — schema corruption must fail loud, not be hidden.
    FUNCTIONAL_RELATIONS = _functional_relations() or _FALLBACK_FUNCTIONAL_RELATIONS


@dataclass(frozen=True)
class FragmentTriple:
    source: str
    predicate: str
    target: str
    confidence: float = 0.5


@dataclass(frozen=True)
class ContradictionFinding:
    kind: str
    source: str
    predicate: str
    target: str
    existing_source: str
    existing_predicate: str
    existing_target: str
    evidence_table: str
    evidence_strength: float
    reason: str


@dataclass(frozen=True)
class ConsistencyReport:
    fragment_id: str
    source_peer_id: str
    accepted: bool
    contradiction_score: float
    entropy_score: float
    threshold: float
    checked_triples: int
    contradiction_count: int
    support_count: int
    trust_after: float | None = None
    findings: list[ContradictionFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["findings"] = [asdict(finding) for finding in self.findings]
        return value


def _normalize_relation(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_") or "related_to"


def _edge_value(edge: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = edge.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _edge_confidence(edge: dict[str, Any]) -> float:
    try:
        value = float(edge.get("confidence", edge.get("weight", 0.5)))
    except (TypeError, ValueError):
        value = 0.5
    return max(0.0, min(1.0, value))


def _fragment_triples(fragment: Any) -> list[FragmentTriple]:
    triples: list[FragmentTriple] = []
    for edge in list(getattr(fragment, "edges", []) or []):
        if not isinstance(edge, dict):
            continue
        source = _edge_value(edge, ("source", "source_id", "from", "subject"))
        target = _edge_value(edge, ("target", "target_id", "to", "object"))
        predicate = _normalize_relation(_edge_value(edge, ("predicate", "relation", "type", "label")))
        if not source or not target or source == target:
            continue
        triples.append(FragmentTriple(source=source, predicate=predicate, target=target, confidence=_edge_confidence(edge)))
    return triples


def _row_strength(row: sqlite3.Row) -> float:
    confidence = float(row["confidence"] if "confidence" in row.keys() and row["confidence"] is not None else 0.5)
    weight = float(row["weight"] if "weight" in row.keys() and row["weight"] is not None else confidence)
    count = float(row["count"] if "count" in row.keys() and row["count"] is not None else 1.0)
    count_boost = min(1.0, math.log1p(max(0.0, count)) / 6.0)
    return max(0.0, min(1.0, (confidence * 0.55) + (weight * 0.3) + (count_boost * 0.15)))


def _select_rows(
    conn: sqlite3.Connection,
    table: str,
    *,
    source: str,
    predicate: str | None = None,
    target: str | None = None,
    target_not: str | None = None,
    limit: int,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, table):
        return []
    where = ["source = ?"]
    params: list[Any] = [source]
    if predicate is not None:
        where.append("relation = ?")
        params.append(predicate)
    if target is not None:
        where.append("target = ?")
        params.append(target)
    if target_not is not None:
        where.append("target != ?")
        params.append(target_not)
    params.append(limit)

    if table == "relation_stats":
        weight_expr = "p_target_given_source"
    elif table == "edges":
        weight_expr = "confidence"
    else:
        weight_expr = "weight"
    return conn.execute(
        f"""
        SELECT source, relation, target, count, confidence, {weight_expr} AS weight
        FROM {table}
        WHERE {" AND ".join(where)}
        ORDER BY confidence DESC, weight DESC, count DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()


def _finding_from_row(kind: str, triple: FragmentTriple, row: sqlite3.Row, table: str, reason: str) -> ContradictionFinding:
    return ContradictionFinding(
        kind=kind,
        source=triple.source,
        predicate=triple.predicate,
        target=triple.target,
        existing_source=str(row["source"]),
        existing_predicate=str(row["relation"]),
        existing_target=str(row["target"]),
        evidence_table=table,
        evidence_strength=_row_strength(row),
        reason=reason,
    )


def _scan_contradictions(
    conn: sqlite3.Connection,
    triple: FragmentTriple,
    *,
    per_pattern_limit: int,
) -> tuple[list[ContradictionFinding], int]:
    findings: list[ContradictionFinding] = []
    support_count = 0
    tables = ["relation_stats", "edges", "synaptic_edges"]

    inverse = INVERSE_RELATIONS.get(triple.predicate)
    for table in tables:
        if triple.predicate not in SYMMETRIC_RELATIONS:
            for row in _select_rows(
                conn,
                table,
                source=triple.target,
                predicate=triple.predicate,
                target=triple.source,
                limit=per_pattern_limit,
            ):
                findings.append(
                    _finding_from_row(
                        "inverse_same_predicate",
                        triple,
                        row,
                        table,
                        "asymmetric predicate exists in the opposite direction",
                    )
                )

        if inverse:
            support_count += len(
                _select_rows(
                    conn,
                    table,
                    source=triple.target,
                    predicate=inverse,
                    target=triple.source,
                    limit=per_pattern_limit,
                )
            )
            for row in _select_rows(
                conn,
                table,
                source=triple.source,
                predicate=inverse,
                target=triple.target,
                limit=per_pattern_limit,
            ):
                findings.append(
                    _finding_from_row(
                        "parallel_inverse_predicate",
                        triple,
                        row,
                        table,
                        "inverse predicate already links the same ordered pair",
                    )
                )

        if triple.predicate in FUNCTIONAL_RELATIONS:
            for row in _select_rows(
                conn,
                table,
                source=triple.source,
                predicate=triple.predicate,
                target_not=triple.target,
                limit=per_pattern_limit,
            ):
                findings.append(
                    _finding_from_row(
                        "functional_parallel_conflict",
                        triple,
                        row,
                        table,
                        "functional predicate already points to a different target",
                    )
                )
    return findings, support_count


def _entropy(probability: float) -> float:
    p = max(0.0, min(1.0, probability))
    if p in {0.0, 1.0}:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def _threshold(config: Any | None) -> float:
    value = getattr(config, "contradiction_threshold", None)
    if value is None:
        return DEFAULT_CONTRADICTION_THRESHOLD
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return DEFAULT_CONTRADICTION_THRESHOLD


def _trust_penalty(config: Any | None) -> float:
    value = getattr(config, "trust_penalty_on_contradiction", None)
    if value is None:
        return DEFAULT_TRUST_PENALTY
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return DEFAULT_TRUST_PENALTY


def _trust_store_path(config: Any | None) -> Path:
    value = getattr(config, "trust_store_path", None)
    return Path(value) if value else DEFAULT_TRUST_STORE


def _lower_peer_trust(peer_id: str, penalty: float, path: Path) -> float:
    if not peer_id:
        return 0.0
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        raw = {}
    current = float(raw.get(peer_id, 1.0))
    next_score = max(0.0, round(current - penalty, 6))
    raw[peer_id] = next_score
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)
    return next_score


def _verify_fragment_consistency_sync(
    fragment: Any,
    *,
    memory_dir: str | Path,
    config: Any | None,
) -> ConsistencyReport:
    triples = _fragment_triples(fragment)
    threshold = _threshold(config)
    fragment_id = str(getattr(fragment, "fragment_id", ""))
    source_peer_id = str(getattr(fragment, "source_peer_id", ""))
    if not triples:
        return ConsistencyReport(
            fragment_id=fragment_id,
            source_peer_id=source_peer_id,
            accepted=True,
            contradiction_score=0.0,
            entropy_score=0.0,
            threshold=threshold,
            checked_triples=0,
            contradiction_count=0,
            support_count=0,
        )

    conn = _connect_readonly(memory_dir)
    if conn is None:
        return ConsistencyReport(
            fragment_id=fragment_id,
            source_peer_id=source_peer_id,
            accepted=True,
            contradiction_score=0.0,
            entropy_score=0.0,
            threshold=threshold,
            checked_triples=len(triples),
            contradiction_count=0,
            support_count=0,
        )

    try:
        tier_edges = int(getattr(config, "max_edges", 2048) or 2048)
        per_pattern_limit = max(1, min(32, tier_edges // max(1, len(triples) * 8)))
        findings: list[ContradictionFinding] = []
        support_count = 0
        incoming_strength = 0.0
        for triple in triples:
            incoming_strength += max(0.05, triple.confidence)
            triple_findings, triple_support = _scan_contradictions(conn, triple, per_pattern_limit=per_pattern_limit)
            findings.extend(triple_findings)
            support_count += triple_support

        contradiction_strength = sum(finding.evidence_strength for finding in findings)
        denominator = max(0.1, incoming_strength + contradiction_strength + (support_count * 0.15))
        contradiction_score = max(0.0, min(1.0, contradiction_strength / denominator))
        accepted = contradiction_score <= threshold
        trust_after = None
        if not accepted:
            trust_after = _lower_peer_trust(source_peer_id, _trust_penalty(config), _trust_store_path(config))
        return ConsistencyReport(
            fragment_id=fragment_id,
            source_peer_id=source_peer_id,
            accepted=accepted,
            contradiction_score=round(contradiction_score, 6),
            entropy_score=round(_entropy(contradiction_score), 6),
            threshold=threshold,
            checked_triples=len(triples),
            contradiction_count=len(findings),
            support_count=support_count,
            trust_after=trust_after,
            findings=findings[:128],
        )
    finally:
        conn.close()


async def verify_fragment_consistency(
    fragment: Any,
    *,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    config: Any | None = None,
) -> ConsistencyReport:
    """Validate a graph fragment against the local ontology without MCTS.

    The check is bounded by hardware/network limits and only reads localized
    triple evidence from SQLite. It rejects high-contradiction fragments before
    they can enter working memory.
    """

    return await asyncio.to_thread(
        _verify_fragment_consistency_sync,
        fragment,
        memory_dir=memory_dir,
        config=config,
    )
