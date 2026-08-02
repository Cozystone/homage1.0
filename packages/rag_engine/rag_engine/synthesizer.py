from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BANNED_SURFACE_SIGNATURES = (
    "payload record says",
    "raw_no_node::",
    "CONTROL_INTENT",
)

STOP_TOKENS = {"the", "and", "for", "with", "from", "this", "that", "into"}
KOREAN_QUERY_MARKERS = ("가", "나", "다", "요", "죠", "까", "근거", "문서", "검증", "어떻게", "왜", "뭐")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in str(text or "").lower():
        if char.isalnum() or char in {"-", "_"}:
            current.append(char)
        elif current:
            token = "".join(current).strip("-_")
            if token and token not in STOP_TOKENS:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).strip("-_")
        if token and token not in STOP_TOKENS:
            tokens.append(token)
    return [token for token in tokens if len(token) > 1 or token.isdigit()]


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if len(tokens) < n:
        return []
    return [tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1)]


def degeneration_metrics(text: str, evidence_docs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tokens = _tokens(text)
    bigrams = _ngrams(tokens, 2)
    trigrams = _ngrams(tokens, 3)
    unique_token_ratio = (len(set(tokens)) / len(tokens)) if tokens else 0.0
    repeated_bigram_ratio = 0.0
    repeated_trigram_ratio = 0.0
    if bigrams:
        repeated_bigram_ratio = 1.0 - (len(set(bigrams)) / len(bigrams))
    if trigrams:
        repeated_trigram_ratio = 1.0 - (len(set(trigrams)) / len(trigrams))

    source_clusters = _source_clusters(evidence_docs or [])
    unrelated_mix = False
    if len(source_clusters) > 1:
        total = sum(cluster["token_count"] for cluster in source_clusters) or 1
        top = max(cluster["token_count"] for cluster in source_clusters)
        unrelated_mix = (top / total) < 0.68

    loop_detected = repeated_bigram_ratio >= 0.34 or repeated_trigram_ratio >= 0.24
    return {
        "repeated_bigram_ratio": round(repeated_bigram_ratio, 6),
        "repeated_trigram_ratio": round(repeated_trigram_ratio, 6),
        "unique_token_ratio": round(unique_token_ratio, 6),
        "unrelated_evidence_mix": unrelated_mix,
        "loop_detected": loop_detected,
    }


def _doc_text(doc: dict[str, Any]) -> str:
    return _clean(doc.get("snippet") or doc.get("text") or doc.get("raw_text"))


def _doc_hash(doc: dict[str, Any]) -> str:
    value = _clean(doc.get("hash_key") or doc.get("node_hash"))
    if value:
        return value
    text = _doc_text(doc)
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else ""


def _doc_source_type(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata")
    if isinstance(metadata, dict):
        return _clean(metadata.get("source_type") or metadata.get("kind") or "local_memory")
    return _clean(doc.get("source_type") or "local_memory")


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text or ""))


def _query_prefers_korean(query: str) -> bool:
    return _has_hangul(query) or any(marker in query for marker in KOREAN_QUERY_MARKERS)


def _sentences(text: str) -> list[str]:
    cleaned = _clean(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", cleaned)
    return [part.strip(" -•\t") for part in parts if len(part.strip()) >= 12]


def _sentence_overlap(query: str, sentence: str) -> float:
    query_tokens = set(_tokens(query))
    sentence_tokens = set(_tokens(sentence))
    if not query_tokens or not sentence_tokens:
        return 0.0
    lexical = len(query_tokens & sentence_tokens) / max(1, len(query_tokens))
    if "graphrag" in sentence.lower() and "graphrag" in query.lower():
        lexical += 0.5
    if ("근거" in query or "evidence" in query.lower()) and ("근거" in sentence or "evidence" in sentence.lower()):
        lexical += 0.35
    if ("검증" in query or "verify" in query.lower()) and ("검증" in sentence or "guard" in sentence.lower() or "check" in sentence.lower()):
        lexical += 0.35
    return lexical


def _compact_hash_label(value: Any) -> str:
    text = _clean(value)
    if len(text) >= 48 and re.fullmatch(r"[0-9a-fA-F]{32,}#?\w*", text):
        return f"{text[:8]}..."
    return text[:80]


def _doc_cluster_key(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata")
    if isinstance(metadata, dict):
        path = _clean(metadata.get("path") or metadata.get("doc_id") or metadata.get("chunk_id"))
        if path:
            return path.split("#", 1)[0]
    return _clean(doc.get("doc_id") or doc.get("path") or doc.get("chunk_id") or _doc_hash(doc)[:12])


def _temporal_weight(doc: dict[str, Any]) -> float:
    temporal = doc.get("temporal")
    if isinstance(temporal, dict):
        return float(temporal.get("combined_weight") or temporal.get("weight") or doc.get("score") or 0.0)
    return float(doc.get("temporal_weight") or doc.get("score") or 0.0)


def _source_clusters(evidence_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for doc in evidence_docs:
        text = _doc_text(doc)
        tokens = _tokens(text)
        if not tokens:
            continue
        key = _doc_cluster_key(doc)
        cluster = clusters.setdefault(
            key,
            {
                "cluster_id": key,
                "source_type": _doc_source_type(doc),
                "doc_count": 0,
                "token_count": 0,
                "score": 0.0,
                "hashes": [],
            },
        )
        cluster["doc_count"] += 1
        cluster["token_count"] += len(tokens)
        cluster["score"] += float(doc.get("score") or 0.0) + _temporal_weight(doc) * 0.2
        doc_hash = _doc_hash(doc)
        if doc_hash:
            cluster["hashes"].append(doc_hash)
    result = list(clusters.values())
    result.sort(key=lambda item: (-float(item["score"]), -int(item["token_count"]), str(item["cluster_id"])))
    return result


def _dominant_cluster(evidence_docs: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    clusters = _source_clusters(evidence_docs)
    if not clusters:
        return None, [], []
    dominant = clusters[0]["cluster_id"]
    dominant_docs = [doc for doc in evidence_docs if _doc_cluster_key(doc) == dominant]
    return str(dominant), dominant_docs, clusters


@dataclass
class CandidateScore:
    token: str
    score: float
    transition_probability: float
    edge_cooccurrence_weight: float
    concept_proximity: float
    evidence_locality: float
    source_type_priority: float
    loop_penalty: float
    temporal_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "score": round(self.score, 6),
            "transition_probability": round(self.transition_probability, 6),
            "edge_cooccurrence_weight": round(self.edge_cooccurrence_weight, 6),
            "concept_proximity": round(self.concept_proximity, 6),
            "evidence_locality": round(self.evidence_locality, 6),
            "source_type_priority": round(self.source_type_priority, 6),
            "loop_penalty": round(self.loop_penalty, 6),
            "temporal_weight": round(self.temporal_weight, 6),
        }


class NativeGraphTokenDecoder:
    """Experimental graph-token decoder.

    This is deliberately not a language-model facade. It exposes the raw token
    sequence selected from local evidence, graph paths, and transition counts.
    """

    name = "ATANOR NativeGraphTokenDecoder"

    def decode(
        self,
        query: str,
        evidence_docs: list[dict[str, Any]],
        matched_nodes: list[dict[str, Any]] | None = None,
        matched_edges: list[dict[str, Any]] | None = None,
        graph_paths: list[list[str]] | None = None,
        *,
        max_tokens: int = 72,
    ) -> dict[str, Any]:
        matched_nodes = matched_nodes or []
        matched_edges = matched_edges or []
        graph_paths = graph_paths or []
        query_tokens = _tokens(query)
        dominant_cluster, local_docs, source_clusters = _dominant_cluster(evidence_docs)
        selected_docs = local_docs or evidence_docs
        evidence_tokens = self._evidence_tokens(selected_docs)
        surface_forms = self._surface_forms(selected_docs)
        token_counts = Counter(evidence_tokens)
        transition_counts = self._transition_counts(evidence_tokens)
        cooccurrence = self._cooccurrence_counts(evidence_tokens, window=5)
        graph_tokens = self._graph_tokens(matched_nodes, matched_edges, graph_paths)
        output: list[str] = []
        decoder_scores: list[dict[str, Any]] = []

        current = self._seed_token(query_tokens, evidence_tokens, token_counts)
        if current:
            output.append(current)

        stop_reason = "max_tokens"
        while len(output) < max_tokens:
            score = self._best_next(
                current=current,
                query_tokens=query_tokens,
                generated=output,
                token_counts=token_counts,
                transition_counts=transition_counts,
                cooccurrence=cooccurrence,
                graph_tokens=graph_tokens,
                selected_docs=selected_docs,
            )
            if score is None:
                stop_reason = "no_candidate"
                break
            decoder_scores.append(score.to_dict())
            if score.loop_penalty >= 0.72 and len(output) >= 4:
                stop_reason = "loop_risk"
                break
            output.append(score.token)
            current = score.token
            if len(output) >= 8:
                metrics = degeneration_metrics(" ".join(output), selected_docs)
                if metrics["loop_detected"]:
                    stop_reason = "loop_risk"
                    break

        if not output:
            output = query_tokens[: max(1, min(12, len(query_tokens)))]
            stop_reason = "no_evidence_tokens"

        raw_answer = self._surface(output, surface_forms)
        if self._is_cloud_evidence_verbatim(raw_answer, selected_docs) and len(output) > 4:
            output = output[:-1]
            raw_answer = self._surface(output, surface_forms)
            stop_reason = f"{stop_reason}_cloud_evidence_guard"
        degeneration = degeneration_metrics(raw_answer, selected_docs)
        failed_quality = (
            not evidence_tokens
            or degeneration["loop_detected"]
            or degeneration["unique_token_ratio"] < 0.34
            or degeneration["unrelated_evidence_mix"]
            or len(_tokens(raw_answer)) < 2
        )
        return {
            "raw_answer": raw_answer,
            "decoder_scores": decoder_scores[-32:],
            "source_clusters": source_clusters,
            "dominant_source_cluster": dominant_cluster,
            "native_stop_reason": stop_reason,
            "degeneration": degeneration,
            "native_generation_failed_quality_check": failed_quality,
            "selected_evidence_count": len(selected_docs),
        }

    def _evidence_tokens(self, docs: list[dict[str, Any]]) -> list[str]:
        tokens: list[str] = []
        ordered = sorted(docs, key=lambda doc: (-_temporal_weight(doc), -float(doc.get("score") or 0.0), _doc_hash(doc)))
        for doc in ordered:
            tokens.extend(_tokens(_doc_text(doc))[:180])
        return tokens

    def _surface_forms(self, docs: list[dict[str, Any]]) -> dict[str, str]:
        surfaces: dict[str, str] = {}
        ordered = sorted(docs, key=lambda doc: (-_temporal_weight(doc), -float(doc.get("score") or 0.0), _doc_hash(doc)))
        for doc in ordered:
            for match in re.finditer(r"[\w\-\uac00-\ud7a3]+", _doc_text(doc), flags=re.UNICODE):
                surface = match.group(0).strip("-_")
                if not surface:
                    continue
                key = surface.lower()
                if (len(key) > 1 or key.isdigit()) and key not in STOP_TOKENS and key not in surfaces:
                    surfaces[key] = surface
        return surfaces

    def _transition_counts(self, tokens: list[str]) -> Counter[tuple[str, str]]:
        return Counter(zip(tokens, tokens[1:]))

    def _cooccurrence_counts(self, tokens: list[str], *, window: int) -> Counter[tuple[str, str]]:
        counts: Counter[tuple[str, str]] = Counter()
        for index, source in enumerate(tokens):
            for target in tokens[index + 1 : index + 1 + window]:
                if source != target:
                    counts[(source, target)] += 1
        return counts

    def _graph_tokens(
        self,
        matched_nodes: list[dict[str, Any]],
        matched_edges: list[dict[str, Any]],
        graph_paths: list[list[str]],
    ) -> set[str]:
        values: list[str] = []
        for node in matched_nodes:
            values.append(_clean(node.get("label") or node.get("id") or node.get("node_hash")))
        for edge in matched_edges:
            values.extend([_clean(edge.get("source") or edge.get("source_hash")), _clean(edge.get("target") or edge.get("target_hash"))])
            values.append(_clean(edge.get("relation")))
        for path in graph_paths:
            values.extend(_clean(part) for part in path)
        result: set[str] = set()
        for value in values:
            result.update(_tokens(value))
        return result

    def _seed_token(self, query_tokens: list[str], evidence_tokens: list[str], token_counts: Counter[str]) -> str | None:
        for token in query_tokens:
            if token in token_counts:
                return token
        if evidence_tokens:
            return max(set(evidence_tokens), key=lambda token: (token_counts[token], -evidence_tokens.index(token), token))
        return query_tokens[0] if query_tokens else None

    def _best_next(
        self,
        *,
        current: str | None,
        query_tokens: list[str],
        generated: list[str],
        token_counts: Counter[str],
        transition_counts: Counter[tuple[str, str]],
        cooccurrence: Counter[tuple[str, str]],
        graph_tokens: set[str],
        selected_docs: list[dict[str, Any]],
    ) -> CandidateScore | None:
        if not token_counts:
            return None
        total_transitions = sum(count for (source, _target), count in transition_counts.items() if source == current) or 1
        total_tokens = sum(token_counts.values()) or 1
        temporal = max([_temporal_weight(doc) for doc in selected_docs] or [0.0])
        source_priority = 0.14 if any(_doc_source_type(doc) == "self_corpus" for doc in selected_docs) else 0.0
        candidates: list[CandidateScore] = []
        candidate_tokens: set[str]
        if current:
            transition_targets = {target for source, target in transition_counts if source == current}
            if transition_targets:
                candidate_tokens = transition_targets
            elif len(generated) < 8:
                candidate_tokens = {target for source, target in cooccurrence if source == current}
            else:
                return None
        else:
            candidate_tokens = set(token_counts)
        for token in candidate_tokens:
            transition_probability = transition_counts.get((current or "", token), 0) / total_transitions
            edge_weight = cooccurrence.get((current or "", token), 0) / max(1, token_counts.get(current or "", 1))
            concept_proximity = 0.18 if token in graph_tokens else 0.0
            if token in query_tokens:
                concept_proximity += 0.08
            evidence_locality = token_counts[token] / total_tokens
            repeat_count = generated.count(token)
            repeated_bigram = len(generated) >= 1 and generated[-1] == token
            repeated_recent_window = token in generated[-6:]
            self_loop_pressure = 0.12 if current and token != current and transition_counts.get((current, current), 0) else 0.0
            loop_penalty = min(
                1.45,
                repeat_count * 0.34
                + (0.55 if repeated_bigram else 0.0)
                + (0.18 if repeated_recent_window else 0.0)
                + (0.42 if repeat_count >= 2 else 0.0)
                + self_loop_pressure,
            )
            score = (
                transition_probability * 0.42
                + min(1.0, edge_weight) * 0.18
                + concept_proximity
                + evidence_locality * 0.18
                + source_priority
                + min(0.35, temporal * 0.08)
                - loop_penalty
            )
            candidates.append(
                CandidateScore(
                    token=token,
                    score=score,
                    transition_probability=transition_probability,
                    edge_cooccurrence_weight=min(1.0, edge_weight),
                    concept_proximity=concept_proximity,
                    evidence_locality=evidence_locality,
                    source_type_priority=source_priority,
                    loop_penalty=loop_penalty,
                    temporal_weight=temporal,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.token))
        if not candidates:
            return None
        return candidates[0]

    def _surface(self, tokens: list[str], surface_forms: dict[str, str] | None = None) -> str:
        surface_forms = surface_forms or {}
        text = " ".join(surface_forms.get(token, token) for token in tokens).strip()
        for signature in BANNED_SURFACE_SIGNATURES:
            text = text.replace(signature, "")
        return re.sub(r"\s{2,}", " ", text).strip()

    def _is_cloud_evidence_verbatim(self, answer: str, selected_docs: list[dict[str, Any]]) -> bool:
        if not answer or not selected_docs or not all(_doc_source_type(doc) == "cloud_brain" for doc in selected_docs):
            return False
        normalized_answer = re.sub(r"[\W_]+", " ", answer.lower()).strip()
        for doc in selected_docs:
            normalized_doc = re.sub(r"[\W_]+", " ", _doc_text(doc).lower()).strip()
            if normalized_doc and normalized_doc in normalized_answer:
                return True
        return False


def _trace_path(memory_dir: str | Path = "data/memory") -> Path:
    root = Path(memory_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / "generation_traces.jsonl"


def save_generation_trace(trace: dict[str, Any], memory_dir: str | Path = "data/memory") -> Path:
    path = _trace_path(memory_dir)
    record = {"created_at": utc_now_iso(), **trace}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def record_user_correction(
    query: str,
    bad_answer: str,
    user_correction: str,
    *,
    accepted: bool = True,
    memory_dir: str | Path = "data/memory",
) -> Path:
    path = Path(memory_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / "corrections.jsonl"
    record = {
        "created_at": utc_now_iso(),
        "query": query,
        "bad_answer": bad_answer,
        "user_correction": user_correction,
        "accepted": bool(accepted),
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return target


class LocalSynthesizer:
    """Compatibility wrapper around the native graph-token decoder."""

    engine_name = "ATANOR NativeGraphTokenDecoder"

    def __init__(self, decoder: NativeGraphTokenDecoder | None = None) -> None:
        self.decoder = decoder or NativeGraphTokenDecoder()

    def synthesize(
        self,
        query: str,
        evidence_docs: list[dict[str, Any]],
        matched_nodes: list[dict[str, Any]] | None = None,
        matched_edges: list[dict[str, Any]] | None = None,
        graph_paths: list[list[str]] | None = None,
        *,
        memory_dir: str | Path = "data/memory",
    ) -> dict[str, Any]:
        matched_nodes = matched_nodes or []
        matched_edges = matched_edges or []
        graph_paths = graph_paths or []
        decoded = self.decoder.decode(query, evidence_docs, matched_nodes, matched_edges, graph_paths)
        raw_answer = decoded["raw_answer"]
        quality_guarded = bool(decoded["native_generation_failed_quality_check"])
        answer = raw_answer
        diagnostics = {
            "answer_kind": "native_graph_token_generation",
            "native_generation_failed_quality_check": decoded["native_generation_failed_quality_check"],
            "quality_guarded_surface": False,
            "degeneration": decoded["degeneration"],
            "training_feedback_recorded": True,
            "source_clusters": decoded["source_clusters"],
            "dominant_source_cluster": decoded["dominant_source_cluster"],
            "native_stop_reason": decoded["native_stop_reason"],
            "selected_evidence_count": decoded["selected_evidence_count"],
            "outbound_http_calls": 0,
            "network_barrier": "sealed_for_generation",
            "banned_surface_signatures": [signature for signature in BANNED_SURFACE_SIGNATURES if signature in answer],
        }
        trace = {
            "query": query,
            "raw_answer": raw_answer,
            "surfaced_answer": answer,
            "evidence_used": [_doc_hash(doc) for doc in evidence_docs],
            "graph_paths": graph_paths,
            "decoder_scores": decoded["decoder_scores"],
            "degeneration_metrics": decoded["degeneration"],
            "source_clusters": decoded["source_clusters"],
            "native_stop_reason": decoded["native_stop_reason"],
            "user_feedback": None,
        }
        trace_path = save_generation_trace(trace, memory_dir)
        diagnostics["generation_trace_path"] = str(trace_path)
        return {
            "answer": answer,
            "raw_native_output": raw_answer,
            "pmv": {
                "topic": (_tokens(query) or [query.strip() or "query"])[0],
                "stance": "research_native_generation",
                "answer_goal": "emit native graph-token output without cosmetic replacement",
                "required_evidence": bool(evidence_docs),
            },
            "claim_plan": [],
            "active_concepts": self._active_concepts(query, evidence_docs, matched_nodes),
            "answer_kind": "native_graph_token_generation",
            "native_generation_failed_quality_check": decoded["native_generation_failed_quality_check"],
            "degeneration": decoded["degeneration"],
            "training_feedback_recorded": True,
            "native_stop_reason": decoded["native_stop_reason"],
            "source_clusters": decoded["source_clusters"],
            "decoder_scores": decoded["decoder_scores"],
            "answer_engine": {
                "name": self.engine_name,
                "mode": "native-graph-token-alpha",
                "external_llm": False,
                "cloud_ai_provider": None,
                "network_barrier": "sealed_for_generation",
                "surface_generation": "native_graph_token_generation",
                "prediction_basis": "token_transition_edge_cooccurrence_graph_path",
                "pretrained_generation_weights": False,
                "canned_identity_response": False,
                "template_fallback": False,
                "stages": [
                    "query",
                    "ghost_topology_hash_search",
                    "payload_vault_disk_fetch",
                    "source_cluster_selection",
                    "native_graph_token_decode",
                    "degeneration_scoring",
                    "raw_native_surface",
                    "generation_trace_append",
                    "output_local_synthesized_text",
                ],
                "diagnostics": diagnostics,
            },
        }

    def _active_concepts(
        self,
        query: str,
        evidence_docs: list[dict[str, Any]],
        matched_nodes: list[dict[str, Any]],
    ) -> list[str]:
        concepts: list[str] = []
        for node in matched_nodes:
            label = _clean(node.get("label") or node.get("primary_name") or node.get("id"))
            if label and label not in concepts:
                concepts.append(label)
        for doc in evidence_docs:
            metadata = doc.get("metadata")
            if isinstance(metadata, dict):
                for key in ("legacy_id", "doc_id", "chunk_id"):
                    value = _clean(metadata.get(key))
                    if value and value not in concepts:
                        concepts.append(value)
        for token, _count in Counter(_tokens(query)).most_common(4):
            if token not in concepts:
                concepts.append(token)
        return concepts[:8]

    def _korean_evidence_surface(
        self,
        query: str,
        evidence_docs: list[dict[str, Any]],
        matched_nodes: list[dict[str, Any]],
        matched_edges: list[dict[str, Any]],
        graph_paths: list[list[str]],
        raw_answer: str,
    ) -> str:
        return _clean(raw_answer)
        sentences = self._ranked_evidence_sentences(query, evidence_docs)
        edge_phrases = self._edge_phrases(matched_edges)
        path_phrases = self._path_phrases(graph_paths)
        labels = [
            _clean(node.get("label") or node.get("primary_name") or node.get("id") or node.get("node_hash"))
            for node in matched_nodes[:5]
        ]
        labels = [label for label in labels if label]
        asks_graphrag = "graphrag" in query.lower() or "근거" in query or "검증" in query

        if sentences:
            body = " ".join(sentences[:2])
            if asks_graphrag:
                tail = (
                    "즉, ATANOR는 먼저 Ghost Shell에서 질문과 가까운 개념 해시와 관계선을 찾고, "
                    "그 해시가 가리키는 Payload Vault 문서를 필요한 만큼만 가져옵니다. "
                    "답변은 이 문서 조각과 활성 그래프 경로가 서로 맞는지 확인한 뒤 만들어지며, "
                    "근거가 약하면 확신을 낮추고 품질 보호 상태로 기록합니다."
                )
            else:
                tail = "이 답변은 검색된 Payload Vault 문맥과 활성 그래프 경로만 사용해 구성했습니다."
            if edge_phrases:
                tail += f" 활성 관계는 {', '.join(edge_phrases[:2])}입니다."
            return f"로컬 메모리에서 검색된 근거를 기준으로 답하면, {body} {tail}".strip()

        if edge_phrases or path_phrases or labels:
            concept_text = ", ".join(labels[:4]) if labels else "질문과 가까운 개념"
            relation_text = "; ".join(edge_phrases[:3] or path_phrases[:2])
            return (
                f"현재 Payload Vault에서 충분한 문장 근거는 찾지 못했지만, Ghost Shell은 {concept_text}를 활성화했습니다. "
                f"확인된 관계 경로는 {relation_text or '아직 희박합니다'}. "
                "따라서 이 답변은 확정 지식이 아니라 로컬 그래프의 현재 연결 상태를 낮은 확신으로 요약한 것입니다."
            )

        clean_raw = _clean(raw_answer)
        if clean_raw:
            return f"로컬 생성기가 충분한 근거 문장을 찾지 못했습니다. 원시 생성 출력은 다음과 같습니다: {clean_raw}"
        return "로컬 메모리에서 이 질문에 답할 만큼의 근거 문서나 그래프 경로를 찾지 못했습니다."

        sentences = self._ranked_evidence_sentences(query, evidence_docs)
        edge_phrases = self._edge_phrases(matched_edges)
        path_phrases = self._path_phrases(graph_paths)
        labels = [
            _clean(node.get("label") or node.get("primary_name") or node.get("id") or node.get("node_hash"))
            for node in matched_nodes[:5]
        ]
        labels = [label for label in labels if label]

        if sentences:
            lead = "로컬 메모리에서 검색된 근거를 기준으로 답하면, "
            body = " ".join(sentences[:2])
            if "graphrag" in query.lower() or "근거" in query or "검증" in query:
                tail = (
                    "즉 ATANOR는 먼저 Ghost Shell에서 질문과 가까운 개념 해시와 관계를 찾고, "
                    "그 해시에 연결된 Payload Vault 문서를 읽은 뒤, 생성 문장이 해당 근거와 맞는지 검증 신호를 계산합니다."
                )
            else:
                tail = "이 답변은 검색된 Payload Vault 문맥과 활성 그래프 경로만 사용했습니다."
            if edge_phrases:
                tail += f" 활성 관계는 {', '.join(edge_phrases[:2])}입니다."
            return f"{lead}{body} {tail}".strip()

        if edge_phrases or path_phrases or labels:
            concept_text = ", ".join(labels[:4]) if labels else "질문과 가까운 개념"
            relation_text = "; ".join(edge_phrases[:3] or path_phrases[:2])
            return (
                f"현재 로컬 Payload Vault에서 충분한 문장 근거는 찾지 못했지만, Ghost Shell은 {concept_text}를 활성화했습니다. "
                f"확인된 관계 경로는 {relation_text or '아직 희박합니다'}입니다. "
                "따라서 이 답변은 확정 지식이 아니라 로컬 그래프의 현재 연결 상태를 기준으로 한 낮은 신뢰도 응답입니다."
            )

        clean_raw = _clean(raw_answer)
        if clean_raw:
            return f"로컬 생성기가 충분한 근거 문장을 찾지 못했습니다. 원시 생성 출력은 다음과 같습니다: {clean_raw}"
        return "로컬 메모리에서 이 질문을 답할 만큼의 근거 문서나 그래프 경로를 찾지 못했습니다."

    def _english_evidence_surface(
        self,
        query: str,
        evidence_docs: list[dict[str, Any]],
        matched_nodes: list[dict[str, Any]],
        matched_edges: list[dict[str, Any]],
        graph_paths: list[list[str]],
        raw_answer: str,
    ) -> str:
        return _clean(raw_answer)
        sentences = self._ranked_evidence_sentences(query, evidence_docs)
        if sentences:
            return " ".join(sentences[:3])
        edge_phrases = self._edge_phrases(matched_edges)
        if edge_phrases:
            return f"The local Ghost Shell found related graph paths: {'; '.join(edge_phrases[:3])}. Payload evidence is still sparse, so confidence is low."
        return _clean(raw_answer) or "The local memory does not yet contain enough evidence for this question."
