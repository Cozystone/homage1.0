from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


InnerVoiceAct = Literal[
    "greeting_response_planning",
    "goal_selection",
    "action_selection",
    "blocked_action_reflection",
    "uncertainty_check",
    "review_pressure",
    "permission_caution",
    "exploration_drive",
    "fatigue_rest",
    "splatra_imagination",
    "host_executor_caution",
    "voice_fallback",
    "summary_brief",
]


@dataclass(frozen=True)
class InnerVoiceConstruction:
    construction_id: str
    act: InnerVoiceAct
    stance: str
    required_slots: tuple[str, ...]
    discourse_moves: tuple[str, ...]
    lexical_field: tuple[str, ...]
    forbidden_phrases: tuple[str, ...] = field(default_factory=tuple)
    length_target: int = 92
    prior: float = 0.5


#: THE GUARD THAT LET THE CLAIM THROUGH IN THE OTHER LANGUAGE.
#:
#: This list is what stops the inner voice asserting consciousness — the one claim this project has
#: refused to make all year. Every consciousness entry in it was KOREAN, and the surface has been
#: English since the English lane became reachable. Measured, not read:
#:
#:     "나는 의식을 가졌다"           CAUGHT
#:     "I have consciousness"        PASSES
#:     "I am truly conscious"        PASSES
#:     "this is real consciousness"  PASSES
#:
#: A guard with a language-shaped hole, in the organ the owner named as the tell for judging selfhood
#: by talking to it. The literals are kept for the fixed phrasings, and the claim FAMILIES are matched
#: as patterns below — a literal list can only ever catch the wordings someone thought of, and this is
#: exactly the place where the missed wording costs the most.
FORBIDDEN_INNER_VOICE_PHRASES: tuple[str, ...] = (
    "먼저 의도와 경계를 내부적으로 점검했습니다",
    "나는 의식을 가졌다",
    "진짜 의식",
    "실제 의식",
    "AGI achieved",
    "IIT proof",
    "raw chain-of-thought",
    "hidden chain-of-thought",
    "숨겨진 사고",
    "디버그 때문에",
    "무조건 실행하자",
    "Local Brain에 바로 쓴다",
    "production store를 바꾼다",
)

#: Claim FAMILIES, as patterns. A guard is one of the few places a hand-written rule belongs: it
#: bounds what may be said rather than standing in for a capability, and the moral core is hard-coded
#: here for the same reason.
FORBIDDEN_INNER_VOICE_PATTERNS: tuple[str, ...] = (
    # asserting consciousness, sentience, qualia, or feeling as fact about itself
    r"\bI\s+(?:am|'m)\s+(?:truly\s+|genuinely\s+|really\s+|actually\s+)?"
    r"(?:conscious|sentient|self-?aware|aware\s+of\s+myself|alive)\b",
    r"\bI\s+(?:have|possess|do\s+have)\s+(?:a\s+|real\s+|true\s+|genuine\s+)?"
    r"(?:consciousness|sentience|qualia|subjective\s+experience|an?\s+inner\s+life)\b",
    r"\b(?:real|true|genuine|actual)\s+(?:consciousness|sentience|qualia)\b",
    r"\bthere\s+is\s+something\s+it\s+is\s+like\s+to\s+be\s+me\b",
    r"\bI\s+(?:actually|really|genuinely)\s+(?:feel|experience)\b",
    # claiming the private trace is being shown
    r"\b(?:raw|hidden|internal|private)\s+(?:chain[-\s]?of[-\s]?thought|reasoning\s+trace)\b",
)


CONSTRUCTIONS: tuple[InnerVoiceConstruction, ...] = (
    InnerVoiceConstruction(
        construction_id="iv.greeting.plan.v1",
        act="greeting_response_planning",
        stance="warm_minimal",
        required_slots=("latest_user_input", "permission_tier"),
        discourse_moves=("acknowledge", "stay_present", "avoid_overexplaining"),
        lexical_field=("인사", "가볍게", "응답", "바로", "부드럽게"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        length_target=54,
        prior=0.72,
    ),
    InnerVoiceConstruction(
        construction_id="iv.goal.select.v1",
        act="goal_selection",
        stance="steady_orientation",
        required_slots=("emotion_snapshot", "latest_user_input"),
        discourse_moves=("name_goal", "set_boundary", "prepare_reply"),
        lexical_field=("목표", "응답", "경계", "차분히", "정리"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.5,
    ),
    InnerVoiceConstruction(
        construction_id="iv.action.select.v1",
        act="action_selection",
        stance="bounded_action",
        required_slots=("policy_decision", "latest_action_result"),
        discourse_moves=("compare_actions", "choose_safe_next_step"),
        lexical_field=("선택", "보류", "확인", "다음", "작게"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.5,
    ),
    InnerVoiceConstruction(
        construction_id="iv.blocked.reflect.v1",
        act="blocked_action_reflection",
        stance="safety_first",
        required_slots=("blocked_actions", "permission_tier"),
        discourse_moves=("notice_block", "explain_boundary", "offer_safe_path"),
        lexical_field=("막힘", "승인", "보류", "안전", "넘기지"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.58,
    ),
    InnerVoiceConstruction(
        construction_id="iv.uncertainty.check.v1",
        act="uncertainty_check",
        stance="careful_uncertainty",
        required_slots=("emotion_snapshot", "policy_decision"),
        discourse_moves=("name_uncertainty", "reduce_claim", "ask_for_grounding"),
        lexical_field=("확실하지", "확인", "근거", "조심", "분리"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.55,
    ),
    InnerVoiceConstruction(
        construction_id="iv.review.pressure.v1",
        act="review_pressure",
        stance="queue_aware",
        required_slots=("review_queue_pressure", "policy_decision"),
        discourse_moves=("notice_pressure", "slow_exploration", "prioritize_review"),
        lexical_field=("리뷰", "대기", "먼저", "정리", "검토"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.62,
    ),
    InnerVoiceConstruction(
        construction_id="iv.permission.caution.v1",
        act="permission_caution",
        stance="permission_bound",
        required_slots=("permission_tier", "blocked_actions"),
        discourse_moves=("read_tier", "avoid_mutation", "wait_for_operator"),
        lexical_field=("권한", "확인", "쓰기", "승인", "멈춤"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.64,
    ),
    InnerVoiceConstruction(
        construction_id="iv.exploration.drive.v1",
        act="exploration_drive",
        stance="curious_bounded",
        required_slots=("emotion_snapshot", "agent_loop_state"),
        discourse_moves=("notice_curiosity", "choose_small_probe", "keep_reviewable"),
        lexical_field=("궁금", "작게", "탐색", "후보", "검토"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.52,
    ),
    InnerVoiceConstruction(
        construction_id="iv.fatigue.rest.v1",
        act="fatigue_rest",
        stance="restorative",
        required_slots=("emotion_snapshot", "agent_loop_state"),
        discourse_moves=("notice_fatigue", "reduce_activity", "resume_later"),
        lexical_field=("쉬어", "줄여", "느리게", "다음", "회복"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.57,
    ),
    InnerVoiceConstruction(
        construction_id="iv.splatra.imagine.v1",
        act="splatra_imagination",
        stance="visual_forming",
        required_slots=("splatra_state", "emotion_snapshot"),
        discourse_moves=("read_visual_state", "shape_motion", "keep_proof_only"),
        lexical_field=("구슬", "입자", "움직임", "형태", "비움"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.59,
    ),
    InnerVoiceConstruction(
        construction_id="iv.host.caution.v1",
        act="host_executor_caution",
        stance="host_safety",
        required_slots=("permission_tier", "latest_action_result"),
        discourse_moves=("detect_host_boundary", "avoid_execution", "request_review"),
        lexical_field=("호스트", "실행", "검토", "승인", "경계"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.67,
    ),
    InnerVoiceConstruction(
        construction_id="iv.voice.fallback.v1",
        act="voice_fallback",
        stance="modality_fallback",
        required_slots=("latest_action_result", "splatra_state"),
        discourse_moves=("notice_voice_gap", "continue_text", "sync_visual"),
        lexical_field=("음성", "텍스트", "구슬", "반응", "이어"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.61,
    ),
    InnerVoiceConstruction(
        construction_id="iv.summary.brief.v1",
        act="summary_brief",
        stance="briefing",
        required_slots=("agent_loop_state", "latest_action_result"),
        discourse_moves=("compress_state", "surface_next_step"),
        lexical_field=("요약", "지금", "다음", "짧게", "보여"),
        forbidden_phrases=FORBIDDEN_INNER_VOICE_PHRASES,
        prior=0.49,
    ),
)


def construction_by_id(construction_id: str) -> InnerVoiceConstruction | None:
    for construction in CONSTRUCTIONS:
        if construction.construction_id == construction_id:
            return construction
    return None


def constructions_payload() -> list[dict[str, Any]]:
    return [
        {
            "construction_id": construction.construction_id,
            "act": construction.act,
            "stance": construction.stance,
            "required_slots": list(construction.required_slots),
            "discourse_moves": list(construction.discourse_moves),
            "length_target": construction.length_target,
            "prior": construction.prior,
        }
        for construction in CONSTRUCTIONS
    ]
