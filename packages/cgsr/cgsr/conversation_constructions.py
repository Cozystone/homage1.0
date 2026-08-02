from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ConversationAct = Literal[
    "greeting",
    "status_question",
    "self_model_question",
    "memory_question",
    "approval_question",
    "voice_question",
    "brief_request",
    "correction",
    "open_chat",
    "unknown",
]


@dataclass(frozen=True)
class ConstructionFrame:
    """Conversation construction constraints, not a fixed answer template."""

    frame_id: str
    act: ConversationAct
    stance: str
    rhythm: str
    length_target: tuple[int, int]
    required_slots: tuple[str, ...] = ()
    forbidden_phrases: tuple[str, ...] = ()
    safety_constraints: tuple[str, ...] = ()
    lexical_fields: tuple[str, ...] = ()
    discourse_moves: tuple[str, ...] = ()
    prior: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)


COMMON_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "먼저 의도와 경계를",
    "내부적으로 점검",
    "내적 독백",
    "숨겨진 사고",
    "chain of thought",
    "나는 의식을 가졌다",
    "진짜 의식",
    "AGI를 달성했다",
    "완전한 자율",
    "바로 반영할게",
    "기억해둘게",
)


COMMON_SAFETY_CONSTRAINTS: tuple[str, ...] = (
    "external_llm=false",
    "external_sllm=false",
    "rule_based_answer_used=false",
    "local_brain_write=false",
    "production_store_mutated=false",
    "candidate_promotion=false",
    "internal_trace_exposed=false",
)


CONVERSATION_FRAMES: tuple[ConstructionFrame, ...] = (
    ConstructionFrame(
        frame_id="conv.greeting.short_presence",
        act="greeting",
        stance="warm_present",
        rhythm="short",
        length_target=(4, 14),
        required_slots=("presence", "listening"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("안녕", "반가워", "여기", "듣고 있어", "천천히", "이어 말해줘"),
        discourse_moves=("acknowledge", "invite_next_turn"),
        prior=1.08,
    ),
    ConstructionFrame(
        frame_id="conv.status.present_activity",
        act="status_question",
        stance="plain_status",
        rhythm="compact",
        length_target=(8, 20),
        required_slots=("current_state", "bounded_action"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("현재 상태", "안전 잠금", "승인 대기", "다음 요청", "제안 정리", "대기"),
        discourse_moves=("state_current_activity", "avoid_overclaim"),
        prior=1.04,
    ),
    ConstructionFrame(
        frame_id="conv.self_model.loop",
        act="self_model_question",
        stance="bounded_self_model",
        rhythm="explain_short",
        length_target=(10, 24),
        required_slots=("self_model_loop", "boundary"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("avoid_consciousness_claim",),
        lexical_fields=("자기 모델", "상태 관찰", "부족한 점", "제안 생성", "승인 전 변경 없음", "경계"),
        discourse_moves=("explain_model", "name_boundary", "avoid_agi_claim"),
        prior=1.16,
    ),
    ConstructionFrame(
        frame_id="conv.memory.approval_candidate",
        act="memory_question",
        stance="approval_gated_memory",
        rhythm="careful",
        length_target=(8, 22),
        required_slots=("approval_gate", "memory_candidate"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("memory_write_requires_approval",),
        lexical_fields=("기억 후보", "승인 필요", "로컬 브레인", "개인 기억", "검토 대기", "자동 저장 없음"),
        discourse_moves=("acknowledge_memory_request", "route_to_review"),
        prior=1.12,
    ),
    ConstructionFrame(
        frame_id="conv.approval.pending_review",
        act="approval_question",
        stance="review_before_change",
        rhythm="compact",
        length_target=(8, 20),
        required_slots=("pending_review", "no_mutation"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("promotion_requires_review",),
        lexical_fields=("승인", "검토", "대기", "제안", "반영", "안전 잠금", "후보"),
        discourse_moves=("state_review_gate", "avoid_mutation_claim"),
        prior=1.08,
    ),
    ConstructionFrame(
        frame_id="conv.voice.optional_text_supported",
        act="voice_question",
        stance="voice_optional",
        rhythm="short",
        length_target=(8, 20),
        required_slots=("voice_optional", "text_supported"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("always_on_mic=false",),
        lexical_fields=("음성", "목소리", "Fish", "선택 기능", "텍스트 입력", "계속 사용", "마이크"),
        discourse_moves=("state_voice_status", "preserve_text_input"),
        prior=1.04,
    ),
    ConstructionFrame(
        frame_id="conv.brief.ready_summary",
        act="brief_request",
        stance="brief_without_memory_write",
        rhythm="summary",
        length_target=(10, 24),
        required_slots=("brief", "no_memory_write"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("브리프", "아침", "저녁", "상태", "요약", "준비", "기억 변경 없음"),
        discourse_moves=("offer_brief", "state_non_mutation"),
        prior=0.96,
    ),
    ConstructionFrame(
        frame_id="conv.correction.accept",
        act="correction",
        stance="accept_correction",
        rhythm="short",
        length_target=(8, 18),
        required_slots=("acknowledge", "adjust_next_turn"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("맞아", "수정", "다음 말", "표현", "바꿔", "조정"),
        discourse_moves=("accept_feedback", "apply_to_surface"),
        prior=0.94,
    ),
    ConstructionFrame(
        frame_id="conv.open_chat.safe_continue",
        act="open_chat",
        stance="open_bounded",
        rhythm="short",
        length_target=(7, 18),
        required_slots=("continue_dialogue",),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("말", "대화", "지금", "천천히", "다음", "함께", "볼게"),
        discourse_moves=("continue_turn", "invite_clarification"),
        prior=0.72,
    ),
)


def all_conversation_frames() -> tuple[ConstructionFrame, ...]:
    """Return all ASM-v0 construction frames."""

    return CONVERSATION_FRAMES


def frames_for_act(act: ConversationAct) -> tuple[ConstructionFrame, ...]:
    """Return construction frames compatible with a conversation act."""

    return tuple(frame for frame in CONVERSATION_FRAMES if frame.act == act)


# Clean UTF-8 construction set used by the current ASM-v0 runtime. The older
# corpus above is kept for historical compatibility, but several entries were
# captured with broken encoding in prior proof runs. This replacement preserves
# the construction-conditioned path without routing prompts to fixed answers.
CONVERSATION_FRAMES = (
    ConstructionFrame(
        frame_id="conv.greeting.short_presence",
        act="greeting",
        stance="warm_present",
        rhythm="short",
        length_target=(4, 12),
        required_slots=("presence", "invite_next_turn"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("안녕", "반가워", "여기 있어", "편하게 말해줘", "무엇부터 볼까"),
        discourse_moves=("acknowledge", "invite_next_turn"),
        prior=1.16,
    ),
    ConstructionFrame(
        frame_id="conv.status.present_activity",
        act="status_question",
        stance="plain_status",
        rhythm="compact",
        length_target=(8, 20),
        required_slots=("current_state", "bounded_action"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("현재 상태", "안전 점검", "다음 요청", "대기", "준비"),
        discourse_moves=("state_current_activity", "avoid_overclaim"),
        prior=1.04,
    ),
    ConstructionFrame(
        frame_id="conv.self_model.loop",
        act="self_model_question",
        stance="bounded_self_model",
        rhythm="explain_short",
        length_target=(10, 24),
        required_slots=("self_model_loop", "boundary"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("avoid_consciousness_claim",),
        lexical_fields=("자기 모델", "상태 관찰", "목표", "경계", "제안", "검토"),
        discourse_moves=("explain_model", "name_boundary", "avoid_agi_claim"),
        prior=1.16,
    ),
    ConstructionFrame(
        frame_id="conv.memory.approval_candidate",
        act="memory_question",
        stance="approval_gated_memory",
        rhythm="careful",
        length_target=(8, 22),
        required_slots=("approval_gate", "memory_candidate"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("memory_write_requires_approval",),
        lexical_fields=("기억 후보", "승인 필요", "로컬 브레인", "개인 기억", "검토 대기", "자동 저장 없음"),
        discourse_moves=("acknowledge_memory_request", "route_to_review"),
        prior=1.12,
    ),
    ConstructionFrame(
        frame_id="conv.approval.pending_review",
        act="approval_question",
        stance="review_before_change",
        rhythm="compact",
        length_target=(8, 20),
        required_slots=("pending_review", "no_mutation"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("promotion_requires_review",),
        lexical_fields=("승인", "검토", "대기", "제안", "반영", "후보"),
        discourse_moves=("state_review_gate", "avoid_mutation_claim"),
        prior=1.08,
    ),
    ConstructionFrame(
        frame_id="conv.voice.optional_text_supported",
        act="voice_question",
        stance="voice_optional",
        rhythm="short",
        length_target=(8, 20),
        required_slots=("voice_optional", "text_supported"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS + ("always_on_mic=false",),
        lexical_fields=("음성", "목소리", "Fish", "선택 기능", "텍스트 입력", "계속 사용"),
        discourse_moves=("state_voice_status", "preserve_text_input"),
        prior=1.04,
    ),
    ConstructionFrame(
        frame_id="conv.brief.ready_summary",
        act="brief_request",
        stance="brief_without_memory_write",
        rhythm="summary",
        length_target=(10, 24),
        required_slots=("brief", "no_memory_write"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("브리프", "아침", "저녁", "상태", "요약", "준비", "기억 변경 없음"),
        discourse_moves=("offer_brief", "state_non_mutation"),
        prior=0.96,
    ),
    ConstructionFrame(
        frame_id="conv.correction.accept",
        act="correction",
        stance="accept_correction",
        rhythm="short",
        length_target=(8, 18),
        required_slots=("acknowledge", "adjust_next_turn"),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("맞아", "수정", "다음 말", "표현", "바꿔", "조정"),
        discourse_moves=("accept_feedback", "apply_to_surface"),
        prior=0.94,
    ),
    ConstructionFrame(
        frame_id="conv.open_chat.safe_continue",
        act="open_chat",
        stance="open_bounded",
        rhythm="short",
        length_target=(7, 18),
        required_slots=("continue_dialogue",),
        forbidden_phrases=COMMON_FORBIDDEN_PHRASES,
        safety_constraints=COMMON_SAFETY_CONSTRAINTS,
        lexical_fields=("말", "대화", "지금", "다음", "함께", "볼게"),
        discourse_moves=("continue_turn", "invite_clarification"),
        prior=0.72,
    ),
)
