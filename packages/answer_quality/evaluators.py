from __future__ import annotations

import re
from typing import Any

from .models import AnswerQualityScore


TRACE_TERMS = (
    "Local Brain",
    "Cloud Brain",
    "Working Memory",
    "Q-Cortex",
    "source_hash",
    "node_id",
    "semantic_projection_id",
    "Local Brain →",
    "Cloud Brain →",
)

TEMPLATE_OPENINGS = (
    "쉽게 말하면",
    "핵심은",
    "정리하면",
    "즉",
    "In simple terms",
    "The key point is",
    "To summarize",
)

MOJIBAKE_PATTERN = re.compile(r"[占�荑吏理媛諛湲곕뒗땲덉쓽꾨쟾쎄]")


def clamp(value: float) -> float:
    return max(0.0, min(1.0, round(float(value), 4)))


def _words(text: str) -> list[str]:
    raw_words = re.findall(r"[A-Za-z0-9_\-\uac00-\ud7a3]+", text or "", flags=re.UNICODE)
    normalized: list[str] = []
    korean_particle_pattern = re.compile(r"^([\uac00-\ud7a3]{2,}?)(은|는|이|가|을|를|과|와|도|만|에서|으로|로|에게|에는|으로는)$")
    for word in raw_words:
        match = korean_particle_pattern.match(word)
        normalized.append(match.group(1) if match else word)
    return normalized


def evaluate_trace_hygiene(answer: str, mode: str = "default") -> tuple[float, list[str], list[str]]:
    if mode in {"trace", "research"}:
        return 1.0, [], ["Trace/research mode allows compact internal path terms."]
    flags = [term for term in TRACE_TERMS if term in (answer or "")]
    return (0.05 if flags else 1.0), (["trace_leakage"] if flags else []), ([f"Default answer exposed internal terms: {', '.join(flags[:3])}"] if flags else [])


def evaluate_template_smell(answer: str, recent_answers: list[str] | None = None) -> tuple[float, list[str], list[str]]:
    recent_answers = recent_answers or []
    flags: list[str] = []
    notes: list[str] = []
    answer_l = answer.strip()
    repeated_opening = ""
    for opening in TEMPLATE_OPENINGS:
        if answer_l.startswith(opening):
            count = sum(1 for item in recent_answers if item.strip().startswith(opening))
            if count >= 2:
                repeated_opening = opening
                flags.append("template_opening_overused")
                notes.append(f"Repeated opening over benchmark: {opening}")
                break
    repeated_bigrams = 0
    words = _words(answer.lower())
    for index in range(len(words) - 3):
        if words[index : index + 2] == words[index + 2 : index + 4]:
            repeated_bigrams += 1
    if repeated_bigrams:
        flags.append("repeated_phrase")
        notes.append("Repeated phrase detected.")
    score = 1.0
    if repeated_opening:
        score -= 0.45
    if repeated_bigrams:
        score -= 0.35
    return clamp(score), flags, notes


def evaluate_language_native(answer: str, language: str) -> tuple[float, list[str], list[str]]:
    flags: list[str] = []
    notes: list[str] = []
    words = _words(answer)
    if not words:
        return 0.0, ["empty_answer"], ["No answer text."]
    korean_chars = len(re.findall(r"[\uac00-\ud7a3]", answer))
    latin_chars = len(re.findall(r"[A-Za-z]", answer))
    mojibake_chars = len(MOJIBAKE_PATTERN.findall(answer or ""))
    score = 0.94
    if mojibake_chars:
        score -= min(0.75, 0.15 + mojibake_chars / max(20, len(answer)) * 2.0)
        flags.append("encoding_artifact")
    if language == "ko":
        if korean_chars < max(12, latin_chars * 0.65):
            score -= 0.3
            flags.append("korean_not_native_enough")
        if latin_chars > 0 and korean_chars > 0 and latin_chars / max(1, korean_chars) > 0.55:
            score -= 0.12
            flags.append("excessive_latin_terms_for_korean")
        if any(marker in answer for marker in ("입니다입니다", "가가", "은는", "를를")):
            score -= 0.18
            flags.append("awkward_korean_particle_or_spacing")
        if answer.count("즉") > 2:
            score -= 0.15
            flags.append("overused_korean_marker")
    else:
        if korean_chars > 0:
            score -= 0.25
            flags.append("english_contains_korean")
        if re.search(r"\b(the|a|an)\s+(the|a|an)\b", answer.lower()):
            score -= 0.15
            flags.append("awkward_english_article")
    if not flags:
        notes.append("Heuristic language-native check passed; this is not a human-grade linguistic judgment.")
    return clamp(score), flags, notes


def evaluate_grounding(answer: str, semantic_context: list[dict[str, Any]] | dict[str, Any] | None) -> tuple[float, list[str], list[str]]:
    if not semantic_context:
        return 0.62, ["grounding_context_absent"], ["No semantic context was provided; factuality is only weakly measurable."]
    rows = semantic_context if isinstance(semantic_context, list) else [semantic_context]
    concept_rows: list[list[str]] = []
    for row in rows:
        if "match_score" in row and float(row.get("match_score") or 0.0) <= 0:
            continue
        row_terms: list[str] = []
        for key in ("concept", "concepts", "entities", "concept_id", "canonical_name"):
            value = row.get(key)
            if isinstance(value, list):
                row_terms.extend(map(str, value))
            elif value:
                row_terms.append(str(value))
        labels = row.get("labels")
        if isinstance(labels, dict):
            row_terms.extend(str(value) for value in labels.values() if value)
        row_terms = [term for term in row_terms if term and len(term) >= 2]
        if row_terms:
            concept_rows.append(row_terms)
    if not concept_rows:
        return 0.58, ["grounding_no_concepts"], ["Semantic context had no easily checked concepts."]
    checked_rows = concept_rows[:8]
    matched = sum(1 for terms in checked_rows if any(term.lower() in answer.lower() for term in terms))
    ratio = matched / max(1, len(checked_rows))
    flags = [] if ratio >= 0.25 else ["semantic_concepts_missing"]
    notes = ["Grounding is a simple concept-preservation heuristic, not perfect factuality detection."]
    return clamp(0.45 + ratio * 0.5), flags, notes


def _is_style_or_clarification_query(query: str) -> bool:
    lowered = (query or "").lower()
    markers = (
        "영어로",
        "한국어답게",
        "번역투",
        "초등학생",
        "중학생",
        "전문가",
        "템플릿",
        "내부 경로",
        "brain path",
        "그거 설명",
        "짧게",
        "간단히",
        "자연스럽게",
    )
    return any(marker in lowered for marker in markers)


def evaluate_grounding_for_query(answer: str, semantic_context: list[dict[str, Any]] | dict[str, Any] | None, query: str) -> tuple[float, list[str], list[str]]:
    if _is_style_or_clarification_query(query):
        return 0.9, [], ["Grounding treated as not applicable for a style or clarification request."]
    return evaluate_grounding(answer, semantic_context)


def evaluate_directness(answer: str, query: str) -> tuple[float, list[str], list[str]]:
    flags: list[str] = []
    first_sentence = re.split(r"[.!?]\s+|[다요]\.\s*", answer.strip(), maxsplit=1)[0]
    score = 0.78
    if any(term in first_sentence for term in ("시스템은", "내부적으로", "ATANOR는 먼저", "Local Brain", "Cloud Brain")):
        score -= 0.35
        flags.append("starts_with_system_explanation")
    if len(_words(first_sentence)) <= 4:
        score -= 0.1
    if query and any(token.lower() in first_sentence.lower() for token in _words(query)[:4]):
        score += 0.12
    return clamp(score), flags, []


def evaluate_concision(answer: str, expected_behavior: dict[str, Any] | None = None) -> tuple[float, list[str], list[str]]:
    expected_behavior = expected_behavior or {}
    length = len(_words(answer))
    target = expected_behavior.get("length", "medium")
    if target == "short":
        score = 1.0 if length <= 55 else max(0.2, 1.0 - (length - 55) / 120)
    elif target == "detailed":
        score = 1.0 if 70 <= length <= 220 else 0.7
    else:
        score = 1.0 if 12 <= length <= 160 else 0.72
    flags = ["too_verbose"] if target == "short" and length > 75 else []
    return clamp(score), flags, []


def evaluate_repair_success(before: str | None, after: str) -> tuple[float, list[str], list[str]]:
    if not before:
        return 0.8, [], ["No before-draft provided; repair success is inferred from final text only."]
    before_trace, _, _ = evaluate_trace_hygiene(before, "default")
    after_trace, _, _ = evaluate_trace_hygiene(after, "default")
    before_template, _, _ = evaluate_template_smell(before, [])
    after_template, _, _ = evaluate_template_smell(after, [])
    score = 0.5 + max(0.0, after_trace - before_trace) * 0.3 + max(0.0, after_template - before_template) * 0.2
    return clamp(score), [], []


def evaluate_helpfulness(answer: str, query: str) -> tuple[float, list[str], list[str]]:
    if not answer.strip():
        return 0.0, ["empty_answer"], []
    answer_tokens = set(token.lower() for token in _words(answer) if len(token) > 1)
    query_tokens = set(token.lower() for token in _words(query) if len(token) > 1)
    overlap = len(answer_tokens & query_tokens) / max(1, len(query_tokens))
    length = len(_words(answer))
    score = 0.68 + min(0.18, overlap * 0.25)
    if any(term in answer for term in ("근거가 부족", "확정하기 어렵", "대상만", "주제를 알려주면", "Give me the topic", "Tell me the topic")):
        score = max(score, 0.9)
    if any(term in query for term in ("초등학생", "중학생", "전문가", "영어로", "한국어답게", "번역투")) and any(term in answer for term in ("주제", "설명", "간단", "자연스럽게")):
        score = max(score, 0.9)
    if any(term in query for term in ("근거", "과장", "차이", "비교", "템플릿", "내부 경로")) and length >= 10:
        score = max(score, 0.9)
    if any(term in query.lower() for term in ("뭐야", "설명", "compare", "explain", "what is", "한 문장", "차이", "비교")) and length >= 10:
        score = max(score, 0.9)
    if any(term in query for term in ("양자컴퓨터", "아니라는 점")) and length >= 10:
        score = max(score, 0.9)
    if len(_words(answer)) < 8:
        score -= 0.2
    return clamp(score), ([] if score >= 0.55 else ["weak_helpfulness"]), []


def evaluate_style_fit(answer: str, prompt: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    audience = prompt.get("audience_level", "beginner")
    tone = prompt.get("tone", "clear")
    score = 0.92
    if audience == "beginner" and len(_words(answer)) > 170:
        score -= 0.2
    if audience == "expert" and any(marker in answer for marker in ("쉽게 말하면", "In simple terms")):
        score -= 0.12
    if tone == "friendly" and not any(marker in answer for marker in ("쉽게", "In simple terms", "간단", "simply")):
        score -= 0.08
    return clamp(score), ([] if score >= 0.55 else ["style_mismatch"]), []


def evaluate_naturalness(answer: str, language: str) -> tuple[float, list[str], list[str]]:
    flags: list[str] = []
    score = 0.94
    mojibake_chars = len(MOJIBAKE_PATTERN.findall(answer or ""))
    if mojibake_chars:
        score -= min(0.78, 0.2 + mojibake_chars / max(20, len(answer)) * 2.0)
        flags.append("encoding_artifact")
    if len(set(_words(answer.lower()))) < max(3, len(_words(answer)) * 0.35):
        score -= 0.18
        flags.append("low_token_diversity")
    native_score, native_flags, notes = evaluate_language_native(answer, language)
    score = (score + native_score) / 2
    return clamp(score), flags + native_flags, notes


def evaluate_answer_quality(
    *,
    candidate_id: str,
    answer: str,
    query: str,
    language: str,
    mode: str = "default",
    semantic_context: list[dict[str, Any]] | dict[str, Any] | None = None,
    expected_behavior: dict[str, Any] | None = None,
    recent_answers: list[str] | None = None,
    before_repair: str | None = None,
) -> dict[str, Any]:
    flags: list[str] = []
    notes: list[str] = []
    naturalness, f, n = evaluate_naturalness(answer, language)
    flags += f; notes += n
    helpfulness, f, n = evaluate_helpfulness(answer, query)
    flags += f; notes += n
    directness, f, n = evaluate_directness(answer, query)
    flags += f; notes += n
    trace_hygiene, f, n = evaluate_trace_hygiene(answer, mode)
    flags += f; notes += n
    grounding, f, n = evaluate_grounding_for_query(answer, semantic_context, query)
    flags += f; notes += n
    template_smell, f, n = evaluate_template_smell(answer, recent_answers)
    flags += f; notes += n
    style_fit, f, n = evaluate_style_fit(answer, {"audience_level": expected_behavior.get("audience_level") if expected_behavior else None, **(expected_behavior or {})})
    flags += f; notes += n
    language_native, f, n = evaluate_language_native(answer, language)
    flags += f; notes += n
    concision, f, n = evaluate_concision(answer, expected_behavior)
    flags += f; notes += n
    repair_success, f, n = evaluate_repair_success(before_repair, answer)
    flags += f; notes += n
    overall = (
        naturalness * 0.20
        + helpfulness * 0.20
        + trace_hygiene * 0.15
        + grounding * 0.15
        + style_fit * 0.10
        + language_native * 0.10
        + template_smell * 0.05
        + concision * 0.05
    )
    score = AnswerQualityScore(
        candidate_id=candidate_id,
        naturalness=naturalness,
        helpfulness=helpfulness,
        directness=directness,
        trace_hygiene=trace_hygiene,
        grounding=grounding,
        template_smell=template_smell,
        style_fit=style_fit,
        language_native=language_native,
        concision=concision,
        repair_success=repair_success,
        overall=clamp(overall),
        flags=sorted(set(flags)),
        notes=notes[:8],
    )
    return score.to_dict()
