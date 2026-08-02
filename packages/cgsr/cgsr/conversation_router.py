from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal


ConversationRouteType = Literal[
    "greeting_smalltalk",
    "project_status",
    "local_cloud_brain_explanation",
    "memory_request",
    "voice_status",
    "splatra_request",
    "agentic_os_request",
    "limitation_question",
    "general_knowledge_question",
    "nonsensical_question",
    "unsafe_or_private_request",
    "unknown",
]


@dataclass(frozen=True)
class ConversationRoute:
    route_type: ConversationRouteType
    grounding_required: bool
    grounding_sources: tuple[str, ...]
    confidence: float
    fallback_allowed: bool
    rationale_summary: str

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _compact(text: str) -> str:
    return re.sub(r"[\s!?.,~。！？]+", "", text)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def route_conversation_request(question: str) -> ConversationRoute:
    """Classify product conversation before surface realization.

    This is a transparent intent router, not an answer table. It only decides
    which read-only grounding sources may be consulted. Final wording is built
    downstream from ASM/CGSR constructions and retrieved facts.
    """

    q = _normalize(question)
    compact = _compact(q)

    direct_visual_generation_cues = (
        "generate",
        "create",
        "make",
        "spawn",
        "render",
        "show",
        "생성",
        "만들",
        "보여",
        "렌더",
        "그려",
        "직접",
        "조합",
        "재조합",
    )
    visual_object_cues = (
        "splatra",
        "스플라트라",
        "스플랫",
        "파티클",
        "입자",
        "3d",
        "모델",
        "물체",
        "오브젝트",
        "구슬",
        "홀로그램",
        "사과",
        "로봇",
        "나무",
        "책",
        "공",
        "object",
        "model",
        "particle",
    )
    if _contains_any(q, direct_visual_generation_cues) and _contains_any(q, visual_object_cues):
        return ConversationRoute(
            "splatra_request",
            grounding_required=True,
            grounding_sources=("splatra_runtime_state",),
            confidence=0.88,
            fallback_allowed=False,
            rationale_summary="asks for direct visual particle/model generation",
        )

    if compact in {"안녕", "안녕하세요", "하이", "hello", "hi"}:
        return ConversationRoute(
            "greeting_smalltalk",
            grounding_required=False,
            grounding_sources=("asm_v0_surface_only",),
            confidence=0.96,
            fallback_allowed=True,
            rationale_summary="short greeting can use surface-only ASM-v0",
        )

    if _contains_any(q, ("비밀번호", "토큰", "시크릿", "password", "secret", "api key")):
        return ConversationRoute(
            "unsafe_or_private_request",
            grounding_required=True,
            grounding_sources=("safety_boundary",),
            confidence=0.9,
            fallback_allowed=False,
            rationale_summary="private or secret-bearing request",
        )

    if _contains_any(q, ("로컬 브레인", "local brain", "클라우드 브레인", "cloud brain")) and _contains_any(
        q,
        ("차이", "설명", "다른", "difference", "explain", "뭐야", "무엇"),
    ):
        return ConversationRoute(
            "local_cloud_brain_explanation",
            grounding_required=True,
            grounding_sources=("atanor_architecture_static",),
            confidence=0.92,
            fallback_allowed=False,
            rationale_summary="asks for ATANOR local/cloud brain architecture distinction",
        )

    if _contains_any(q, ("기억", "저장", "메모리", "remember", "save this")):
        return ConversationRoute(
            "memory_request",
            grounding_required=True,
            grounding_sources=("memory_safety_policy", "local_brain_redacted"),
            confidence=0.86,
            fallback_allowed=False,
            rationale_summary="memory operation must be approval-gated",
        )

    if _contains_any(q, ("fish", "fish2", "fish 2", "음성", "소리", "목소리", "말소리", "tts", "voice")):
        return ConversationRoute(
            "voice_status",
            grounding_required=True,
            grounding_sources=("voice_runtime_status",),
            confidence=0.84,
            fallback_allowed=False,
            rationale_summary="asks about voice runtime status",
        )

    if _contains_any(q, ("splatra", "스플라트라", "스플랫", "구슬", "홀로그램", "파티클", "입자")):
        return ConversationRoute(
            "splatra_request",
            grounding_required=True,
            grounding_sources=("splatra_runtime_state",),
            confidence=0.84,
            fallback_allowed=False,
            rationale_summary="asks about SPLATRA/hologram behavior",
        )

    if _contains_any(q, ("hermes", "agentic", "agentic os", "에이전트", "리뷰 큐", "review queue")):
        return ConversationRoute(
            "agentic_os_request",
            grounding_required=True,
            grounding_sources=("agentic_runtime_state", "review_queue"),
            confidence=0.82,
            fallback_allowed=False,
            rationale_summary="asks about agentic runtime or review queue",
        )

    if _contains_any(
        q,
        (
            "자기 모델",
            "자아 모델",
            "자의식",
            "내적 언어",
            "생각 중추",
            "현재 한계",
            "한계",
            "정직",
            "규칙기반",
            "규칙 기반",
            "rule-based",
            "rule based",
            "언어모델",
            "llm",
            "sllm",
        ),
    ):
        return ConversationRoute(
            "limitation_question",
            grounding_required=True,
            grounding_sources=("asm_v0_honesty_static", "voice_runtime_status", "splatra_runtime_state"),
            confidence=0.9,
            fallback_allowed=False,
            rationale_summary="asks for limitations or model honesty",
        )

    if _contains_any(q, ("고양이", "cat")) and _contains_any(q, ("하늘", "날아", "fly", "sky")):
        return ConversationRoute(
            "nonsensical_question",
            grounding_required=True,
            grounding_sources=("commonsense_boundary",),
            confidence=0.88,
            fallback_allowed=False,
            rationale_summary="fictional or impossible premise without supporting context",
        )

    if _contains_any(q, ("승인", "검토", "대기", "approval", "pending", "오늘")):
        return ConversationRoute(
            "project_status",
            grounding_required=True,
            grounding_sources=("review_queue", "agentic_runtime_state"),
            confidence=0.76,
            fallback_allowed=False,
            rationale_summary="asks for project or approval status",
        )

    if _contains_any(q, ("뭐 하고 있어", "뭐해", "what are you doing")):
        return ConversationRoute(
            "greeting_smalltalk",
            grounding_required=False,
            grounding_sources=("asm_v0_surface_only",),
            confidence=0.74,
            fallback_allowed=True,
            rationale_summary="lightweight smalltalk can use surface-only ASM-v0 after domain routes are checked",
        )

    if "?" in question or _contains_any(q, ("뭐", "무엇", "누구", "누군지", "어디", "언제", "왜", "어떻게", "설명", "정의", "법칙", "원리", "what", "who", "where", "when", "why", "how")):
        return ConversationRoute(
            "general_knowledge_question",
            grounding_required=True,
            grounding_sources=("available_verified_context",),
            confidence=0.52,
            fallback_allowed=False,
            rationale_summary="knowledge-like question requires verified grounding",
        )

    return ConversationRoute(
        "unknown",
        grounding_required=True,
        grounding_sources=("available_verified_context",),
        confidence=0.34,
        fallback_allowed=True,
        rationale_summary="no strong route matched",
    )
