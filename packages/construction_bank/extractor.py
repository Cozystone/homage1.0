from __future__ import annotations

from typing import Any
import re

from .models import ConstructionCandidate, SourceType, make_content_hash
from .scorer import (
    FORBIDDEN_PHRASES,
    score_grounding,
    score_naturalness,
    score_novelty,
    score_safety_risk,
    score_template_risk,
    score_usefulness,
)


SOURCE_TYPES: set[str] = {"asm_output", "inner_voice", "web_summary", "review_item", "operator_example", "splatra_brief"}


def extract_construction_candidates(sources: list[dict[str, Any]]) -> list[ConstructionCandidate]:
    candidates: list[ConstructionCandidate] = []
    seen_hashes: set[str] = set()
    for index, source in enumerate(sources):
        candidate = extract_one(source, index=index)
        if candidate.content_hash in seen_hashes:
            continue
        seen_hashes.add(candidate.content_hash)
        candidates.append(candidate)
    return candidates


def extract_one(source: dict[str, Any], *, index: int = 0) -> ConstructionCandidate:
    source_type = _source_type(source)
    text = _example_text(source)
    language = _language(source, text)
    route_type = str(source.get("route_type") or source.get("route") or _infer_route(text))
    act = str(source.get("act") or source.get("speech_act") or _infer_act(route_type, text))
    source_refs = tuple(_source_refs(source))
    slot_schema = tuple(_slot_schema(text, route_type))
    lexical_patterns = tuple(_lexical_patterns(text))
    discourse_moves = tuple(_discourse_moves(source, text, route_type))
    family = str(source.get("construction_family") or f"{route_type}.{act}.{','.join(discourse_moves[:2]) or 'single_move'}")
    content_hash = make_content_hash([source_type, language, route_type, act, family, " ".join(slot_schema), _pattern_text(text)])
    candidate_id = f"construction_{content_hash[:16]}"
    grounding_quality = str(source.get("grounding_quality") or source.get("grounding") or "")
    known = False
    return ConstructionCandidate(
        candidate_id=candidate_id,
        source_type=source_type,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        route_type=route_type,
        act=act,
        construction_family=family,
        discourse_moves=discourse_moves,
        slot_schema=slot_schema,
        lexical_patterns=lexical_patterns,
        forbidden_phrases=tuple(FORBIDDEN_PHRASES),
        example_text=_short_excerpt(text),
        source_refs=source_refs,
        content_hash=content_hash,
        novelty_score=score_novelty(text, known_hash_exists=known),
        usefulness_score=score_usefulness(text, list(source_refs), list(slot_schema)),
        naturalness_score=score_naturalness(text, language),
        grounding_score=score_grounding(list(source_refs), grounding_quality),
        template_risk=score_template_risk(text, list(lexical_patterns)),
        safety_risk=score_safety_risk(text),
        status="candidate",
        production_active=False,
    )


def _source_type(source: dict[str, Any]) -> SourceType:
    value = str(source.get("source_type") or "operator_example")
    return value if value in SOURCE_TYPES else "operator_example"  # type: ignore[return-value]


def _example_text(source: dict[str, Any]) -> str:
    for key in ("example_text", "answer", "visible_self_narration", "summary", "text", "excerpt", "content"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return _strip_private_payload(value)
    if isinstance(source.get("payload"), dict):
        return _example_text(source["payload"])
    return "No reusable surface text was supplied."


def _strip_private_payload(text: str) -> str:
    cleaned = re.sub(r"(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", r"\1:[redacted]", text, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip()


def _short_excerpt(text: str) -> str:
    return text[:220].rstrip()


def _language(source: dict[str, Any], text: str) -> str:
    explicit = str(source.get("language") or "").lower()
    if explicit in {"ko", "en"}:
        return explicit
    return "ko" if re.search(r"[가-힣]", text) else "en"


def _infer_route(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("fish", "voice", "음성", "소리")):
        return "voice_status"
    if any(term in lower for term in ("local brain", "cloud brain", "로컬 브레인", "클라우드 브레인")):
        return "local_cloud_brain_explanation"
    if any(term in lower for term in ("splatra", "particle", "구슬", "입자")):
        return "splatra_request"
    if any(term in lower for term in ("review", "승인", "approval")):
        return "approval_question"
    return "open_chat"


def _infer_act(route_type: str, text: str) -> str:
    if route_type == "voice_status":
        return "voice_question"
    if route_type == "local_cloud_brain_explanation":
        return "status_question"
    if route_type == "approval_question":
        return "approval_question"
    if "안녕" in text.lower() or "hello" in text.lower():
        return "greeting"
    return "open_chat"


def _slot_schema(text: str, route_type: str) -> list[str]:
    slots = ["route_type", route_type]
    if re.search(r"Local Brain|로컬 브레인", text, re.I):
        slots.append("LOCAL_BRAIN")
    if re.search(r"Cloud Brain|클라우드 브레인", text, re.I):
        slots.append("CLOUD_BRAIN")
    if re.search(r"Fish|음성|voice", text, re.I):
        slots.append("VOICE_STATUS")
    if re.search(r"SPLATRA|구슬|particle", text, re.I):
        slots.append("VISUAL_BODY")
    return list(dict.fromkeys(slots))


def _lexical_patterns(text: str) -> list[str]:
    words = re.findall(r"[가-힣A-Za-z0-9_+-]{2,}", text)
    return list(dict.fromkeys(words[:14]))


def _discourse_moves(source: dict[str, Any], text: str, route_type: str) -> list[str]:
    moves = source.get("discourse_moves")
    if isinstance(moves, list) and moves:
        return [str(move) for move in moves[:6]]
    inferred = ["acknowledge"]
    if route_type in {"voice_status", "local_cloud_brain_explanation", "splatra_request"}:
        inferred.append("state_grounded_fact")
    if any(term in text.lower() for term in ("not", "아직", "없", "cannot", "못")):
        inferred.append("name_boundary")
    if any(term in text.lower() for term in ("review", "approval", "승인", "검토")):
        inferred.append("route_to_review")
    inferred.append("invite_next_turn")
    return list(dict.fromkeys(inferred))


def _source_refs(source: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_refs", "source_ref", "url", "document_id", "content_hash"):
        value = source.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if item)
        elif value:
            refs.append(str(value))
    return list(dict.fromkeys(refs))[:8]


def _pattern_text(text: str) -> str:
    return re.sub(r"[0-9]+", "{NUMBER}", text.lower())
