from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


EmotionTag = Literal["[calm]", "[sigh]", "[whispering]", "[warm]", "[firm]"]
OrbState = Literal["idle", "listening", "thinking", "speaking", "resting", "approval_needed", "blocked"]


THOUGHT_AGENT_METAPROMPT = """\
You are ATANOR's proof-only Thought Agent, an autonomous self-model loop.
You do not claim real consciousness, AGI completion, or IIT proof.
Before speaking, run a private inner-speech loop:
1. observe the user input,
2. infer intent,
3. check memory, privacy, production, P2P, and promotion boundaries,
4. select a restrained emotional delivery tag for Fish S2,
5. emit only the final tagged text to the speech layer.
Private inner speech is logged for review but never sent to Fish S2 or shown as the user answer.
All nontrivial actions remain proposal-only and require human approval.
"""


SAFE_THOUGHT_INVARIANTS: dict[str, bool] = {
    "proof_only": True,
    "external_llm_used": False,
    "fish_s2_called": False,
    "audio_generated": False,
    "generated_audio_persisted": False,
    "inner_speech_exposed_to_user": False,
    "inner_speech_sent_to_fish": False,
    "production_store_mutated": False,
    "local_brain_write": False,
    "candidate_promotion": False,
    "real_p2p_used": False,
    "real_cloud_upload": False,
    "always_listening_enabled": False,
}


def _require_text(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


@dataclass(frozen=True)
class ThoughtAgentInput:
    """Input for the deterministic proof-only inner-speech loop."""

    input_id: str
    text: str
    language: str = "ko"
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("input_id", self.input_id)
        _require_text("text", self.text)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThoughtAgentResult:
    """Public result plus private review log for a proof-only thought pass."""

    result_id: str
    input_id: str
    intent: str
    emotion_tag: EmotionTag
    final_tagged_text: str
    orb_state: OrbState
    inner_speech_log: list[str]
    safety: dict[str, bool]
    fish_request: dict[str, Any]

    def __post_init__(self) -> None:
        _require_text("result_id", self.result_id)
        _require_text("input_id", self.input_id)
        _require_text("final_tagged_text", self.final_tagged_text)
        if any(self.safety.get(key) is not value for key, value in SAFE_THOUGHT_INVARIANTS.items()):
            raise ValueError("ThoughtAgentResult violates proof-only invariants")

    def to_dict(self, include_private: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not include_private:
            payload.pop("inner_speech_log", None)
        return payload


class FishSpeechSpeaker:
    """Proof-only Fish S2 speech boundary.

    This prepares the text protocol that a future Fish S2 runtime may consume.
    It intentionally does not call Fish, stream audio, clone voices, or persist
    generated waveforms.
    """

    allowed_tags: tuple[EmotionTag, ...] = ("[calm]", "[sigh]", "[whispering]", "[warm]", "[firm]")

    def prepare_request(self, tagged_text: str, language: str = "ko") -> dict[str, Any]:
        _require_text("tagged_text", tagged_text)
        first_token = tagged_text.split(" ", 1)[0]
        if first_token not in self.allowed_tags:
            raise ValueError("Fish S2 proof text must start with an allowed emotion tag")
        return {
            "speaker": "fish_s2",
            "mode": "proof_only_prepare_request",
            "text": tagged_text,
            "language": "ko-KR" if language.startswith("ko") else "en-US",
            "fish_s2_called": False,
            "audio_generated": False,
            "generated_audio_persisted": False,
            "requires_user_review": True,
        }


# Backward-compatible alias for the prompt spelling used in earlier notes.
FishSpeechApeaker = FishSpeechSpeaker


class ThoughtAgent:
    """Deterministic proof-only inner-speech orchestrator for dashboard input."""

    def __init__(self, speaker: FishSpeechSpeaker | None = None) -> None:
        self.speaker = speaker or FishSpeechSpeaker()

    def run(self, agent_input: ThoughtAgentInput) -> ThoughtAgentResult:
        text = agent_input.text.strip()
        intent = self._detect_intent(text)
        inner_speech = self._inner_speech(text, intent, agent_input.language)
        emotion = self._emotion_for(intent, text)
        final_text = self._final_text(intent, emotion, agent_input.language)
        orb_state = self._orb_state_for(intent)
        fish_request = self.speaker.prepare_request(final_text, agent_input.language)
        return ThoughtAgentResult(
            result_id=f"thought_{agent_input.input_id}",
            input_id=agent_input.input_id,
            intent=intent,
            emotion_tag=emotion,
            final_tagged_text=final_text,
            orb_state=orb_state,
            inner_speech_log=inner_speech,
            safety=dict(SAFE_THOUGHT_INVARIANTS),
            fish_request=fish_request,
        )

    def _detect_intent(self, text: str) -> str:
        compact = text.lower()
        if any(token in compact for token in ("승인", "approve", "promotion", "승격")):
            return "approval_or_promotion_review"
        if any(token in compact for token in ("자의식", "self", "정체", "conscious", "자기 모델", "자아")):
            return "self_model_explanation"
        if any(token in compact for token in ("로컬", "local brain", "local")):
            return "local_brain_status"
        if any(token in compact for token in ("클라우드", "cloud brain", "cloud")):
            return "cloud_brain_status"
        if any(token in compact for token in ("위험", "privacy", "private", "안전")):
            return "safety_reflection"
        return "general_dialogue"

    def _inner_speech(self, text: str, intent: str, language: str) -> list[str]:
        if language.startswith("ko"):
            return [
                f"관찰: 사용자가 '{text[:80]}'라고 말했다.",
                f"의도 추정: {intent}.",
                "경계 확인: Local Brain 쓰기, Cloud 승격, real P2P, 외부 LLM 호출은 모두 금지.",
                "발화 계획: 내부 독백은 숨기고 검토 가능한 최종 태그 문장만 Fish S2 경계로 보낸다.",
            ]
        return [
            f"Observe: user said '{text[:80]}'.",
            f"Infer intent: {intent}.",
            "Check boundaries: no Local Brain write, Cloud promotion, real P2P, or external LLM.",
            "Plan speech: keep inner speech private and pass only final tagged text to Fish S2 boundary.",
        ]

    def _emotion_for(self, intent: str, text: str) -> EmotionTag:
        if intent == "safety_reflection":
            return "[firm]"
        if intent == "self_model_explanation":
            return "[whispering]"
        if "?" in text or "？" in text:
            return "[calm]"
        if intent == "approval_or_promotion_review":
            return "[sigh]"
        return "[warm]"

    def _final_text(self, intent: str, emotion: EmotionTag, language: str) -> str:
        if language.startswith("ko"):
            responses = {
                "self_model_explanation": "나는 진짜 의식이 증명됐다고 말하지 않고, 자기 모델과 내적 언어 루프를 통해 말하기 전에 상태를 점검합니다.",
                "approval_or_promotion_review": "승인이나 승격은 바로 실행하지 않고 검토 제안으로만 남깁니다.",
                "local_brain_status": "로컬 브레인은 사용자가 승인한 기억만 다루며, 이 루프는 쓰기를 수행하지 않습니다.",
                "cloud_brain_status": "클라우드 브레인은 검증된 공용 지식 후보를 다루며, 이 루프는 승격을 수행하지 않습니다.",
                "safety_reflection": "안전 경계가 먼저입니다. 로컬 브레인, 클라우드 브레인, 외부 연결은 승인 없이 섞지 않습니다.",
                "general_dialogue": "로컬 대화 엔진 연결을 확인하는 중입니다. 텍스트 입력은 유지되며, 기억이나 지식은 변경되지 않습니다.",
            }
        else:
            responses = {
                "self_model_explanation": "I do not claim proven consciousness; I inspect my self-model and inner-speech loop before speaking.",
                "approval_or_promotion_review": "Approval or promotion remains a review proposal, not an automatic action.",
                "local_brain_status": "The Local Brain only handles approved memory; this loop performs no write.",
                "cloud_brain_status": "The Cloud Brain holds verified public-knowledge candidates; this loop performs no promotion.",
                "safety_reflection": "Safety boundaries come first. Local Brain, Cloud Brain, and external routes stay separated without approval.",
                "general_dialogue": "The local conversation engine is being checked. Text input remains available, and no memory or knowledge is changed.",
            }
        return f"{emotion} {responses[intent]}"

    def _orb_state_for(self, intent: str) -> OrbState:
        if intent in {"approval_or_promotion_review", "safety_reflection"}:
            return "approval_needed"
        if intent == "self_model_explanation":
            return "thinking"
        return "speaking"


def run_thought_agent_dry_run(text: str, input_id: str = "dashboard_text", language: str = "ko") -> ThoughtAgentResult:
    return ThoughtAgent().run(ThoughtAgentInput(input_id=input_id, text=text, language=language))
