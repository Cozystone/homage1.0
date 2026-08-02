from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.cgsr.cgsr.ingestion.verification_gate import has_mock_signal


TEXT_FIELDS = ("text", "sentence", "source_text", "claim", "content", "canonical_form")
SOURCE_FIELDS = ("source_ref", "source_id", "document_id", "url")
STORE_FILES = ("evidence.jsonl", "relations.jsonl", "case_frames.jsonl", "concepts.jsonl")
FILE_PRIORITIES = {
    "evidence.jsonl": 1.0,
    "relations.jsonl": 0.88,
    "case_frames.jsonl": 0.72,
    "concepts.jsonl": 0.58,
}
CONTEXT_DEPENDENT_OPENERS = (
    "첫 번째 항",
    "두 번째 항",
    "세 번째 항",
    "맨 첫 번째 항",
    "첫 번째 단계",
    "두 번째 단계",
    "세 번째 단계",
    "맨 첫 번째 단계",
    "그 중",
    "그중",
    "따라서",
    "그러므로",
    "이 오차",
    "이 항",
    "이 경우",
    "이는",
    "이것은",
    "그것은",
    "the first term",
    "the second term",
    "the third term",
    "therefore",
    "this term",
    "this error",
    "in this case",
)

ADJACENT_EVIDENCE_TOKENS = {
    "acceleration",
    "attraction",
    "fall",
    "falling",
    "force",
    "mass",
    "motion",
    "orbit",
    "가속도",
    "낙하",
    "떨어지다",
    "떨어지는",
    "떨어졌다",
    "물체",
    "이동",
    "운동",
    "자유낙하",
    "궤도",
}
CONCRETE_MOTION_TOKENS = {
    "fall",
    "falling",
    "freefall",
    "가속도",
    "낙하",
    "떨어지다",
    "떨어지는",
    "떨어졌다",
    "물체",
    "자유낙하",
}
ADJACENT_GENERIC_TOKENS = {
    "것이다",
    "그리고",
    "대한",
    "대해",
    "따라서",
    "또는",
    "법칙",
    "설명",
    "단계",
    "있다",
}
STOP_TOKENS = {
    "a",
    "an",
    "and",
    "about",
    "explain",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "what",
    "when",
    "where",
    "which",
    "whose",
    "how",
    "please",
    "the",
    "this",
    "to",
    "대한",
    "대해",
    "것을",
    "설명",
    "설명해줘",
    "알려줘",
    "보여줘",
    "무엇",
    "뭐야",
    "어떻게",
    "그리고",
}
KOREAN_SUFFIXES = (
    "으로는",
    "로는",
    "으로",
    "에서",
    "에게",
    "에는",
    "이다",
    "입니다",
    "하고",
    "까지",
    "부터",
    "처럼",
    "보다",
    "이며",
    "이나",
    "거나",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "의",
    "로",
    "과",
    "와",
)


@dataclass(frozen=True)
class VerifiedFactHit:
    fact: str
    source_ref: str
    score: float


@dataclass(frozen=True)
class _FactCandidate:
    filename: str
    row: dict[str, Any]
    text: str
    source_ref: str
    document_key: str
    tokens: set[str]
    score: float
    adjacent: bool = False


def _read_jsonl(path: Path, *, limit: int = 50000) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if len(rows) >= limit:
                break
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _normalize_token(token: str) -> str:
    token = token.casefold().strip()
    for suffix in KOREAN_SUFFIXES:
        if len(token) > len(suffix) + 1 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> set[str]:
    raw = re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text or ""))
    tokens = {_normalize_token(token) for token in raw if len(_normalize_token(token)) >= 2}
    return {token for token in tokens if token not in STOP_TOKENS}


def _row_text(row: dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        value = row.get(field)
        if value:
            return re.sub(r"\s+", " ", str(value).strip())
    source = row.get("source") or row.get("subject") or row.get("source_label")
    predicate = row.get("predicate") or row.get("relation") or row.get("relation_type")
    target = row.get("target") or row.get("object") or row.get("target_label")
    if source and predicate and target:
        return re.sub(r"\s+", " ", f"{source} {predicate} {target}".strip())
    return ""


def _is_context_dependent_fragment(text: str) -> bool:
    compact = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    if not compact:
        return False
    return compact.startswith(tuple(opener.casefold() for opener in CONTEXT_DEPENDENT_OPENERS))


def _source_ref(row: dict[str, Any], fallback: str) -> str:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    for field in SOURCE_FIELDS:
        value = row.get(field) or provenance.get(field)
        if value:
            return str(value)
    source_name = provenance.get("source_name") or row.get("source_name")
    title = provenance.get("title") or row.get("title")
    if source_name or title:
        return " / ".join(str(value) for value in (source_name, title) if value)
    return fallback


def _document_key(row: dict[str, Any], fallback: str) -> str:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    document_id = row.get("document_id") or provenance.get("document_id")
    if document_id:
        return str(document_id)
    source_id = row.get("source_id") or provenance.get("source_id")
    if source_id:
        source_id = str(source_id)
        return source_id.rsplit(":", 1)[0] if ":" in source_id else source_id
    return _source_ref(row, fallback)


def _is_verified(row: dict[str, Any]) -> bool:
    verification_value = row.get("verification")
    if "verification" in row and not isinstance(verification_value, dict):
        return False
    verification = verification_value if isinstance(verification_value, dict) else {}
    statuses = [
        value
        for present, value in (
            ("status" in row, row.get("status")),
            ("verification_status" in row, row.get("verification_status")),
            ("status" in verification, verification.get("status")),
        )
        if present
    ]
    return bool(statuses) and all(
        isinstance(status, str) and status in {"verified", "accepted"}
        for status in statuses
    )


def _has_adjacent_evidence_signal(text: str, tokens: set[str]) -> bool:
    folded = text.casefold()
    return bool(tokens & ADJACENT_EVIDENCE_TOKENS) or any(token in folded for token in ADJACENT_EVIDENCE_TOKENS)


def _scene_signal_count(text: str, tokens: set[str]) -> int:
    folded = text.casefold()
    return sum(1 for token in ADJACENT_EVIDENCE_TOKENS if token in tokens or token in folded)


def _concrete_motion_count(text: str, tokens: set[str]) -> int:
    folded = text.casefold()
    return sum(1 for token in CONCRETE_MOTION_TOKENS if token in tokens or token in folded)


def _salient_seed_tokens(candidates: list[_FactCandidate], query_tokens: set[str]) -> set[str]:
    seed: set[str] = set(query_tokens)
    for candidate in candidates[:8]:
        seed.update(
            token
            for token in candidate.tokens
            if len(token) >= 3 and token not in STOP_TOKENS and token not in ADJACENT_GENERIC_TOKENS
        )
    return seed


def _adjacent_verified_candidates(
    rows: list[tuple[str, dict[str, Any]]],
    *,
    primary: list[_FactCandidate],
    query_tokens: set[str],
    seen_texts: set[str],
) -> list[_FactCandidate]:
    """Find same-source evidence that adds concrete motion/scene structure.

    This is still extractive retrieval. It does not map topics to canned
    scenes; adjacent facts must live in the same source/document as a primary
    verified hit and share salient tokens with that hit.
    """

    if not primary:
        return []
    document_keys = {candidate.document_key for candidate in primary[:8] if candidate.document_key}
    seed_tokens = _salient_seed_tokens(primary, query_tokens)
    adjacent: list[_FactCandidate] = []
    for filename, row in rows:
        if not _is_verified(row):
            continue
        text = _row_text(row)
        if not text or has_mock_signal(text) or _is_context_dependent_fragment(text):
            continue
        key = text.casefold()
        if key in seen_texts:
            continue
        document_key = _document_key(row, filename)
        if document_key not in document_keys:
            continue
        row_tokens = _tokens(text)
        if not row_tokens:
            continue
        overlap = row_tokens & seed_tokens
        if not overlap:
            continue
        has_scene_signal = _has_adjacent_evidence_signal(text, row_tokens)
        if not has_scene_signal and len(overlap) < 2:
            continue
        scene_count = _scene_signal_count(text, row_tokens)
        concrete_motion_count = _concrete_motion_count(text, row_tokens)
        score = (
            0.1
            + (0.03 * min(len(overlap), 4))
            + (0.04 * min(scene_count, 4))
            + (0.08 * min(concrete_motion_count, 3))
        )
        score *= FILE_PRIORITIES.get(filename, 0.5)
        if score < 0.14:
            continue
        adjacent.append(
            _FactCandidate(
                filename=filename,
                row=row,
                text=text,
                source_ref=_source_ref(row, filename),
                document_key=document_key,
                tokens=row_tokens,
                score=round(score, 4),
                adjacent=True,
            )
        )
    adjacent.sort(key=lambda candidate: (-candidate.score, len(candidate.text), candidate.text))
    return adjacent


def retrieve_verified_facts(
    question: str,
    *,
    store_path: str | Path | None,
    limit: int = 4,
) -> list[VerifiedFactHit]:
    """Read verified-store facts relevant to a question without mutating data.

    This is extractive retrieval, not answer generation. It only returns rows
    already present in a verified JSONL store and refuses mock-template signals.
    """

    if not store_path:
        return []
    root = Path(store_path)
    if not root.exists() or not root.is_dir():
        return []
    query_tokens = _tokens(question)
    if not query_tokens:
        return []

    rows: list[tuple[str, dict[str, Any]]] = []
    for filename in STORE_FILES:
        for row in _read_jsonl(root / filename):
            rows.append((filename, row))

    primary: list[_FactCandidate] = []
    seen: set[str] = set()
    for filename, row in rows:
        if not _is_verified(row):
            continue
        text = _row_text(row)
        if not text or has_mock_signal(text) or _is_context_dependent_fragment(text):
            continue
        row_tokens = _tokens(text)
        if not row_tokens:
            continue
        overlap = query_tokens & row_tokens
        if not overlap:
            continue
        if len(query_tokens) >= 2 and len(overlap) < 2:
            continue
        base_score = len(overlap) / max(1, len(query_tokens))
        score = base_score * FILE_PRIORITIES.get(filename, 0.5)
        if score < 0.18:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        primary.append(
            _FactCandidate(
                filename=filename,
                row=row,
                text=text,
                source_ref=_source_ref(row, filename),
                document_key=_document_key(row, filename),
                tokens=row_tokens,
                score=round(score, 4),
            )
        )

    primary.sort(key=lambda candidate: (-candidate.score, len(candidate.text), candidate.text))
    adjacent = _adjacent_verified_candidates(rows, primary=primary, query_tokens=query_tokens, seen_texts=seen)
    if adjacent and limit > 1:
        selected = primary[: max(1, limit - 1)]
        selected_seen = {candidate.text.casefold() for candidate in selected}
        for candidate in adjacent:
            if len(selected) >= limit:
                break
            if candidate.text.casefold() not in selected_seen:
                selected.append(candidate)
                selected_seen.add(candidate.text.casefold())
    else:
        selected = primary[:limit]
    return [
        VerifiedFactHit(fact=candidate.text, source_ref=candidate.source_ref, score=candidate.score)
        for candidate in selected[:limit]
    ]
