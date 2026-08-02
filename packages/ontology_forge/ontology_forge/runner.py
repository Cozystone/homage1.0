from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .entity_resolver import EntityResolver


TECH_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "data",
    "text", "docs", "document", "documents", "system", "using",
}

ACTION_HINTS = {
    "use", "uses", "using", "used",
    "build", "builds", "built",
    "create", "creates", "created",
    "extract", "extracts", "extracted",
    "retrieve", "retrieves", "retrieved",
    "traverse", "traverses", "traversed",
    "improve", "improves", "improved",
    "reduce", "reduces", "reduced",
    "require", "requires", "required",
    "contain", "contains", "contained",
    "route", "routes", "routed",
    "learn", "learns", "learned",
    "measure", "measures", "measured",
    "connect", "connects", "connected",
}

RELATION_PATTERNS = [
    (re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+is\s+a\s+([A-Z][A-Za-z0-9_-]{2,})\b"), "is_a"),
    (re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+uses\s+([A-Z][A-Za-z0-9_-]{2,})\b"), "uses"),
    (re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+improves\s+([A-Z][A-Za-z0-9_-]{2,})\b"), "improves"),
    (re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+reduces\s+([A-Z][A-Za-z0-9_-]{2,})\b"), "reduces"),
    (re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+requires\s+([A-Z][A-Za-z0-9_-]{2,})\b"), "requires"),
    (re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+contains\s+([A-Z][A-Za-z0-9_-]{2,})\b"), "contains"),
]


@dataclass
class Candidate:
    label: str
    kind: str
    doc_id: str
    context: str


@dataclass
class Node:
    id: str
    concept_id: str
    primary_name: str
    label: str
    aliases: list[str]
    type: str
    count: int
    confidence: float
    context_vector: list[float]
    evidence_doc_ids: list[str]
    resolver: dict[str, Any]


@dataclass
class Edge:
    source: str
    relation: str
    target: str
    confidence: float
    evidence_doc_ids: list[str]
    source_alias: str
    target_alias: str
    status: str = "candidate"


def _doc_files(input_dir: str) -> list[Path]:
    root = Path(input_dir)
    root.mkdir(parents=True, exist_ok=True)
    return sorted([*root.rglob("*.txt"), *root.rglob("*.md")])


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _sentence_tokens(sentence: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z가-힣][A-Za-z0-9가-힣_-]{1,}", sentence)
    return [token for token in tokens if token.lower() not in TECH_STOPWORDS][:18]


def _context_window(sentences: list[str], index: int, radius: int = 1) -> str:
    left = max(0, index - radius)
    right = min(len(sentences), index + radius + 1)
    return " ".join(sentences[left:right])


def _is_action_token(token: str) -> bool:
    lowered = token.lower().strip("-_")
    if lowered in ACTION_HINTS:
        return True
    if lowered.endswith(("ing", "ed")) and len(lowered) > 4:
        return True
    return bool(re.search(r"(사용|생성|추출|검색|검증|학습|측정|연결|확장|개선|감소|요구|라우팅)$", token))


def _node_type_for(label: str, stored_type: str) -> str:
    if stored_type == "phrase":
        return "phrase"
    if _is_action_token(label):
        return "verb"
    return stored_type


def _concepts(text: str, doc_id: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+)$", text):
        label = heading.strip(" #`*")
        if len(label) > 2:
            candidates.append(Candidate(label[:80], "heading", doc_id, heading))

    sentences = _sentences(text)
    for sentence_index, sentence in enumerate(sentences):
        context = _context_window(sentences, sentence_index)
        for token in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b|`([A-Za-z_][A-Za-z0-9_]{2,})`", sentence):
            label = token if isinstance(token, str) else token[0]
            if label and label.lower() not in TECH_STOPWORDS:
                candidates.append(Candidate(label, "concept", doc_id, context))

        words = _sentence_tokens(sentence)
        counts = Counter(word for word in words if word.lower() not in TECH_STOPWORDS)
        for word, count in counts.items():
            if count >= 2 or _is_action_token(word):
                candidates.append(Candidate(word, "verb" if _is_action_token(word) else "keyword", doc_id, context))
    return candidates


def _add_candidate(
    candidate: Candidate,
    candidate_counts: Counter[str],
    candidate_types: dict[str, str],
    candidate_docs: dict[str, set[str]],
    candidate_contexts: dict[str, list[str]],
) -> None:
    candidate_counts[candidate.label] += 1
    if candidate_types.get(candidate.label) != "concept":
        candidate_types.setdefault(candidate.label, candidate.kind)
    candidate_docs[candidate.label].add(candidate.doc_id)
    candidate_contexts[candidate.label].append(candidate.context)


def _add_sentence_structure(
    sentence: str,
    context: str,
    doc_id: str,
    candidate_counts: Counter[str],
    candidate_types: dict[str, str],
    candidate_docs: dict[str, set[str]],
    candidate_contexts: dict[str, list[str]],
    edge_docs: dict[tuple[str, str, str], set[str]],
    edge_contexts: dict[tuple[str, str, str], list[str]],
) -> None:
    tokens = _sentence_tokens(sentence)
    if len(tokens) < 2:
        return

    for token in tokens:
        _add_candidate(
            Candidate(token, "verb" if _is_action_token(token) else "keyword", doc_id, context),
            candidate_counts,
            candidate_types,
            candidate_docs,
            candidate_contexts,
        )

    for index, token in enumerate(tokens[:-1]):
        nxt = tokens[index + 1]
        phrase = f"{token} {nxt}"
        _add_candidate(Candidate(phrase, "phrase", doc_id, context), candidate_counts, candidate_types, candidate_docs, candidate_contexts)
        for edge in [
            (token, "precedes", nxt),
            (token, "forms_phrase", phrase),
            (phrase, "contains", nxt),
        ]:
            edge_docs[edge].add(doc_id)
            edge_contexts[edge].append(context)

    for index, token in enumerate(tokens):
        if not _is_action_token(token):
            continue
        left = next((tokens[left_index] for left_index in range(index - 1, -1, -1) if not _is_action_token(tokens[left_index])), None)
        right = next((tokens[right_index] for right_index in range(index + 1, len(tokens)) if not _is_action_token(tokens[right_index])), None)
        if left:
            edge_docs[(left, "does", token)].add(doc_id)
            edge_contexts[(left, "does", token)].append(context)
        if right:
            edge_docs[(token, "acts_on", right)].add(doc_id)
            edge_contexts[(token, "acts_on", right)].append(context)

    for index, token in enumerate(tokens[:12]):
        for other in tokens[index + 2 : min(len(tokens), index + 5)]:
            if token != other:
                edge_docs[(token, "co_occurs", other)].add(doc_id)
                edge_contexts[(token, "co_occurs", other)].append(context)


def _best_context(label: str, contexts: list[str]) -> str:
    if not contexts:
        return label
    contexts.sort(key=lambda item: (label.lower() not in item.lower(), len(item)))
    return contexts[0]


def run_ontology(
    input_dir: str = "data/cleaned",
    output_dir: str = "data/ontology",
    concept_db_path: str | Path | None = None,
) -> dict:
    candidate_counts: Counter[str] = Counter()
    candidate_types: dict[str, str] = {}
    candidate_docs: dict[str, set[str]] = defaultdict(set)
    candidate_contexts: dict[str, list[str]] = defaultdict(list)
    edge_docs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    edge_contexts: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    for path in _doc_files(input_dir):
        doc_id = path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        sentences = _sentences(text)
        for candidate in _concepts(text, doc_id):
            _add_candidate(candidate, candidate_counts, candidate_types, candidate_docs, candidate_contexts)

        for sentence_index, sentence in enumerate(sentences):
            context = _context_window(sentences, sentence_index)
            for pattern, relation in RELATION_PATTERNS:
                for match in pattern.finditer(sentence):
                    source_label, target_label = match.group(1), match.group(2)
                    for label in [source_label, target_label]:
                        _add_candidate(Candidate(label, "concept", doc_id, context), candidate_counts, candidate_types, candidate_docs, candidate_contexts)
                    edge_docs[(source_label, relation, target_label)].add(doc_id)
                    edge_contexts[(source_label, relation, target_label)].append(context)
            _add_sentence_structure(
                sentence,
                context,
                doc_id,
                candidate_counts,
                candidate_types,
                candidate_docs,
                candidate_contexts,
                edge_docs,
                edge_contexts,
            )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    concept_db = Path(concept_db_path) if concept_db_path else out / "canonical_concepts.sqlite3"
    resolver = EntityResolver(concept_db)
    node_by_label: dict[str, dict[str, Any]] = {}
    created = 0
    merged = 0
    try:
        with resolver.transaction() as tx:
            for label, count in candidate_counts.most_common(240):
                context = _best_context(label, candidate_contexts[label])
                resolved = tx.resolve(label, context)
                if resolved["resolution"] == "created":
                    created += 1
                else:
                    merged += 1
                node_by_label[label] = {
                    **resolved,
                    "label": resolved["primary_name"],
                    "type": _node_type_for(label, candidate_types.get(label, "concept")),
                    "count": count,
                    "evidence_doc_ids": sorted(candidate_docs[label]),
                }
        concepts = {concept["concept_id"]: concept for concept in resolver.export_concepts()}
    finally:
        resolver.close()

    nodes: list[Node] = []
    for label, resolved in node_by_label.items():
        concept = concepts.get(resolved["concept_id"], resolved)
        count = int(resolved["count"])
        nodes.append(
            Node(
                id=str(resolved["concept_id"]),
                concept_id=str(resolved["concept_id"]),
                primary_name=str(concept.get("primary_name") or resolved["primary_name"]),
                label=str(concept.get("primary_name") or resolved["primary_name"]),
                aliases=[str(item) for item in concept.get("aliases", resolved["aliases"])],
                type=str(resolved["type"]),
                count=count,
                confidence=round(min(0.95, 0.45 + count * 0.08 + len(resolved["evidence_doc_ids"]) * 0.08), 2),
                context_vector=[round(float(value), 6) for value in concept.get("context_vector", resolved["context_vector"])],
                evidence_doc_ids=list(resolved["evidence_doc_ids"]),
                resolver={
                    "strategy": "cross_lingual_contextual_entity_resolution",
                    "embedding_provider": resolver.embedding_provider.provider,
                    "similarity_threshold": resolver.similarity_threshold,
                    "last_resolution": resolved["resolution"],
                    "similarity": resolved["similarity"],
                },
            )
        )

    node_ids = {node.id for node in nodes}
    label_to_id = {label: resolved["concept_id"] for label, resolved in node_by_label.items()}
    edges: list[Edge] = []
    for (source_label, relation, target_label), docs in sorted(edge_docs.items()):
        source_id = label_to_id.get(source_label)
        target_id = label_to_id.get(target_label)
        if not source_id or not target_id or source_id not in node_ids or target_id not in node_ids:
            continue
        edges.append(
            Edge(
                source=str(source_id),
                relation=relation,
                target=str(target_id),
                confidence=round(min(0.9, 0.5 + len(docs) * 0.12), 2),
                evidence_doc_ids=sorted(docs),
                source_alias=source_label,
                target_alias=target_label,
            )
        )

    report = {
        "state": "completed",
        "input_dir": input_dir,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "output_dir": output_dir,
        "entity_resolution": {
            "strategy": "cross_lingual_contextual_entity_resolution",
            "schema": "Node(concept_id, primary_name, aliases, context_vector)",
            "edge_policy": "concept_id_to_concept_id",
            "embedding_model": resolver.embedding_provider.provider,
            "similarity_threshold": resolver.similarity_threshold,
            "ema_alpha": resolver.ema_alpha,
            "created": created,
            "merged": merged,
            "concept_db": str(concept_db),
        },
    }

    (out / "nodes.json").write_text(json.dumps([asdict(node) for node in nodes], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "edges.json").write_text(json.dumps([asdict(edge) for edge in edges], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "ontology_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"nodes": [asdict(node) for node in nodes], "edges": [asdict(edge) for edge in edges], "report": report}
