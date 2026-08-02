from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .constructions import (
    CONSTRUCTIONS,
    FORBIDDEN_INNER_VOICE_PATTERNS,
    FORBIDDEN_INNER_VOICE_PHRASES,
    InnerVoiceConstruction,
)


KOREAN_GREETINGS = ("안녕", "안녕하세요", "하이", "반가워")


@dataclass(frozen=True)
class InnerVoiceSurface:
    construction: InnerVoiceConstruction
    act_scores: dict[str, float]
    goal: str
    tension: str
    candidate_actions: list[str]
    chosen_action: str
    blocked_actions: list[str]
    uncertainty: str
    next_intent: str
    monologue_text: str
    surface_score: float


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _vector(snapshot: dict[str, Any]) -> dict[str, float]:
    raw = snapshot.get("vector") if isinstance(snapshot.get("vector"), dict) else {}
    return {
        "curiosity": float(raw.get("curiosity", 0.45) or 0.45),
        "caution": float(raw.get("caution", 0.35) or 0.35),
        "fatigue": float(raw.get("fatigue", 0.0) or 0.0),
        "valence": float(raw.get("valence", 0.0) or 0.0),
    }


def _label(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("label") or "steady")


def _is_greeting(text: str) -> bool:
    stripped = re.sub(r"\s+", "", str(text or "").lower())
    return any(item in stripped for item in KOREAN_GREETINGS)


def _policy_parts(policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    review = policy.get("review") if isinstance(policy.get("review"), dict) else {}
    agent_loop = policy.get("agent_loop") if isinstance(policy.get("agent_loop"), dict) else {}
    return review, agent_loop


def score_inner_voice_acts(input_data: Any) -> dict[str, float]:
    snapshot = dict(getattr(input_data, "emotion_snapshot", {}) or {})
    policy = dict(getattr(input_data, "policy_decision", {}) or {})
    vector = _vector(snapshot)
    review, agent_loop = _policy_parts(policy)
    latest_user_input = str(getattr(input_data, "latest_user_input", "") or "")
    latest_action_result = dict(getattr(input_data, "latest_action_result", {}) or {})
    permission_tier = str(getattr(input_data, "permission_tier", "OBSERVE_ONLY") or "OBSERVE_ONLY")
    review_pressure = float(getattr(input_data, "review_queue_pressure", 0.0) or 0.0)
    splatra_state = dict(getattr(input_data, "splatra_state", {}) or {})
    scores = {construction.act: construction.prior for construction in CONSTRUCTIONS}

    if _is_greeting(latest_user_input):
        scores["greeting_response_planning"] += 0.78
    if latest_user_input and not _is_greeting(latest_user_input):
        scores["greeting_response_planning"] -= 0.12
        scores["goal_selection"] += 0.22
        scores["action_selection"] += 0.12
    if review_pressure >= 0.55 or review.get("should_request_review"):
        scores["review_pressure"] += 0.75 + min(review_pressure, 1.0) * 0.25
    if permission_tier not in {"OBSERVE_ONLY", "READ_ONLY", ""}:
        scores["permission_caution"] += 0.7
        scores["host_executor_caution"] += 0.2
    if permission_tier in {"FULL_HOST_AUTHORITY", "HOST_EXECUTOR", "WRITE_ENABLED"}:
        scores["host_executor_caution"] += 0.75
    if latest_action_result.get("voice_unavailable") or latest_action_result.get("text_fallback"):
        scores["voice_fallback"] += 0.82
    if latest_action_result.get("stopped_reason"):
        scores["blocked_action_reflection"] += 0.45
        scores["summary_brief"] += 0.18
    if splatra_state:
        scores["splatra_imagination"] += 0.7
    if vector["fatigue"] >= 0.58 or agent_loop.get("should_rest"):
        scores["fatigue_rest"] += 0.78
    if vector["caution"] >= 0.68:
        scores["uncertainty_check"] += 0.48
        scores["permission_caution"] += 0.2
    if vector["curiosity"] >= 0.62 and review_pressure < 0.55:
        scores["exploration_drive"] += 0.52
    return {key: round(value, 4) for key, value in scores.items()}


def select_inner_voice_construction(input_data: Any) -> tuple[InnerVoiceConstruction, dict[str, float]]:
    scores = score_inner_voice_acts(input_data)
    best_act = max(scores, key=lambda act: (scores[act], act))
    for construction in CONSTRUCTIONS:
        if construction.act == best_act:
            return construction, scores
    return CONSTRUCTIONS[0], scores


def _goal_for(construction: InnerVoiceConstruction, has_user_input: bool) -> str:
    goals = {
        "greeting_response_planning": "take the greeting lightly and get ready to carry the "
                                      "conversation on.",
        "goal_selection": "match what was said against my current state and pick the goal of the "
                          "next reply.",
        "action_selection": "pick the safe, small next step out of what is available.",
        "blocked_action_reflection": "find a route that turns the blocked action into an approvable "
                                     "one.",
        "uncertainty_check": "shrink what I am unsure of and keep only what can be checked.",
        "review_pressure": "clear the review queue first rather than passing it to automatic "
                           "execution.",
        "permission_caution": "read the permission boundary and explain while writes and changes stay "
                              "stopped.",
        "exploration_drive": "lower the pull to explore into a small candidate and leave it "
                             "reviewable.",
        "fatigue_rest": "lower the activity and get ready for the next cycle.",
        "splatra_imagination": "match the motion of the orb and particles to the flow of what I am "
                               "saying.",
        "host_executor_caution": "check the host execution boundary and avoid running anything "
                                 "unreviewed.",
        "voice_fallback": "carry on with text and the orb's response while the voice output is empty.",
        "summary_brief": "get ready to show the current state compressed into something short.",
    }
    if not has_user_input and construction.act == "goal_selection":
        return "look quietly at the current state and not speak first."
    return goals.get(construction.act, "set the boundary of the next reply.")


def _surface_for_act_en(construction: InnerVoiceConstruction, input_data: Any, label: str) -> str:
    """English self-narration surfaces (mirrors the Korean tone: quiet, honest)."""
    latest_user_input = str(getattr(input_data, "latest_user_input", "") or "")
    permission_tier = str(getattr(input_data, "permission_tier", "OBSERVE_ONLY") or "OBSERVE_ONLY")
    review_pressure = float(getattr(input_data, "review_queue_pressure", 0.0) or 0.0)
    latest_action_result = dict(getattr(input_data, "latest_action_result", {}) or {})
    splatra_state = dict(getattr(input_data, "splatra_state", {}) or {})

    if construction.act == "greeting_response_planning":
        return "I'm taking the greeting lightly. I'll keep my reply short and carry the conversation on."
    if construction.act == "review_pressure":
        return f"The review queue pressure is up to {review_pressure:.2f}. It's safer to ease the queue before exploring further."
    if construction.act == "permission_caution":
        return f"I'm staying within the {permission_tier} boundary. I'll hold off on any write or change and only say what I can verify."
    if construction.act == "host_executor_caution":
        return "Anything that touches the host needs review first. I'll put evidence and records ahead of execution."
    if construction.act == "voice_fallback":
        return "Voice output isn't ready yet. I'll keep going with text and the orb's response."
    if construction.act == "splatra_imagination":
        scene_focus = splatra_state.get("stage_layout") == "scene_focus"
        motion_count = int(float(splatra_state.get("motion_count") or 0))
        if scene_focus and motion_count > 0:
            return "I'm clearing the center stage and aligning the particle flow to the order of my words."
        if scene_focus:
            return "I'm clearing the center stage and letting the particles settle into the shape of the explanation."
        return "I'm matching the orb's motion to my current state — gathering the particles like a breath rather than shaking them."
    if construction.act == "fatigue_rest":
        return "There's a signal to lower activity a little. I won't push hard; I'll get ready for the next cycle."
    if construction.act == "uncertainty_check":
        return "I'll keep the uncertain parts small, and separate what's grounded from what I don't know."
    if construction.act == "exploration_drive":
        return "There's a direction I'd like to look into. I won't change anything directly — I'll leave it as a small reviewable candidate."
    if construction.act == "blocked_action_reflection":
        reason = str(latest_action_result.get("stopped_reason") or "a permission boundary")
        return f"Because of {reason}, I won't pass it through right away. I'll record the hold reason and choose a safe path."
    if construction.act == "summary_brief":
        return "What's needed now is a short summary, not a long explanation. I'll show the state and just the next step."
    if latest_user_input:
        return f"I received your message in a {label} state. I'll grasp the focus of your question first and answer from where it matters."
    return f"I'm holding a {label} state. I won't move first; I'll wait for the next signal."


def _surface_for_act(construction: InnerVoiceConstruction, input_data: Any, label: str) -> str:
    # ENGLISH-ONLY IS BINDING SINCE 2026-07-18, AND THIS ORGAN NEVER GOT THE MEMO. The English surface
    # existed and was complete; Korean was the DEFAULT, reached whenever a caller did not pass
    # `language="en"`. Measured: 93 lines of Korean across this package while the project's own index
    # records violations at zero -- and this is the organ the owner named as the tell for judging
    # selfhood by talking to it. The Korean branch below is retired rather than translated: there is
    # no second language lane to maintain.
    return _surface_for_act_en(construction, input_data, label)


def _surface_for_act_ko_retired(construction: InnerVoiceConstruction, input_data: Any,
                                label: str) -> str:
    """Retired 2026-08-01. Kept unreachable for one commit so the diff shows what was removed."""
    latest_user_input = str(getattr(input_data, "latest_user_input", "") or "")
    permission_tier = str(getattr(input_data, "permission_tier", "OBSERVE_ONLY") or "OBSERVE_ONLY")
    review_pressure = float(getattr(input_data, "review_queue_pressure", 0.0) or 0.0)
    latest_action_result = dict(getattr(input_data, "latest_action_result", {}) or {})
    splatra_state = dict(getattr(input_data, "splatra_state", {}) or {})

    if construction.act == "greeting_response_planning":
        return "인사를 가볍게 받아들이고 있습니다. 지금은 짧게 응답하면서 대화를 이어가겠습니다."
    if construction.act == "review_pressure":
        return f"리뷰 대기 압력이 {review_pressure:.2f}까지 올라와 있습니다. 탐색보다 검토 대기열을 먼저 줄이는 편이 안전합니다."
    if construction.act == "permission_caution":
        return f"{permission_tier} 경계 안에서 머물고 있습니다. 쓰기나 변경은 멈추고 확인 가능한 말만 드리겠습니다."
    if construction.act == "host_executor_caution":
        return "호스트에 닿는 행동은 아직 검토가 먼저입니다. 실행보다 근거와 기록을 앞에 두겠습니다."
    if construction.act == "voice_fallback":
        return "음성 출력이 아직 비어 있습니다. 텍스트와 구슬 반응을 맞추며 대화를 이어가겠습니다."
    if construction.act == "splatra_imagination":
        scene_focus = splatra_state.get("stage_layout") == "scene_focus"
        motion_count = int(float(splatra_state.get("motion_count") or 0))
        if scene_focus and motion_count > 0:
            return "중앙 무대를 비우고 입자의 흐름을 말의 순서에 맞추고 있습니다."
        if scene_focus:
            return "중앙 무대를 비우고 입자들이 설명의 형태를 잡도록 정렬하고 있습니다."
        return "구슬의 움직임을 지금 상태에 맞추고 있습니다. 입자를 크게 흔들기보다 호흡처럼 모으겠습니다."
    if construction.act == "fatigue_rest":
        return "활동을 조금 낮춰야 할 신호가 있습니다. 급히 밀어붙이지 않고 다음 주기를 준비하겠습니다."
    if construction.act == "uncertainty_check":
        return "확실하지 않은 부분은 작게 말하겠습니다. 근거가 있는 것과 모르는 것을 분리하겠습니다."
    if construction.act == "exploration_drive":
        return "더 보고 싶은 방향이 있습니다. 바로 바꾸지 않고 검토 가능한 후보로 작게 남기겠습니다."
    if construction.act == "blocked_action_reflection":
        reason = str(latest_action_result.get("stopped_reason") or "권한 경계")
        return f"{reason} 때문에 바로 넘기지 않겠습니다. 보류 사유를 남기고 안전한 경로를 고르겠습니다."
    if construction.act == "summary_brief":
        return "지금 필요한 것은 긴 설명보다 짧은 요약입니다. 상태와 다음 한 걸음만 보여드리겠습니다."
    if latest_user_input:
        return f"{label} 상태에서 사용자의 말을 받았습니다. 질문의 초점을 먼저 붙잡고 필요한 지점부터 답하겠습니다."
    return f"{label} 상태를 유지하고 있습니다. 먼저 움직이지 않고 다음 신호를 기다리겠습니다."


_FORBIDDEN_RX = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN_INNER_VOICE_PATTERNS)
#: what a caught claim is replaced with. Was Korean, which meant a successful catch emitted the
#: retired language into an English lane -- the guard firing was itself a violation.
_REDACTION = "a reportable self-narration channel"


def _sanitize_surface(text: str, forbidden_phrases: tuple[str, ...]) -> str:
    surface = re.sub(r"\s+", " ", str(text or "").strip())
    for phrase in (*FORBIDDEN_INNER_VOICE_PHRASES, *forbidden_phrases):
        surface = surface.replace(phrase, _REDACTION)
    for rx in _FORBIDDEN_RX:                 # the claim families, which literals cannot cover
        surface = rx.sub(_REDACTION, surface)
    surface = surface.replace("chain-of-thought", "self-narration")
    surface = surface.replace("Chain-of-thought", "self-narration")
    if surface and not surface.endswith((".", "?", "!")):
        surface = f"{surface}."
    return surface[:220]


def _surface_score(text: str, construction: InnerVoiceConstruction) -> float:
    score = 0.64
    length = len(text)
    if 26 <= length <= construction.length_target + 70:
        score += 0.16
    if any(token in text for token in construction.lexical_field):
        score += 0.08
    if not any(phrase in text for phrase in FORBIDDEN_INNER_VOICE_PHRASES)             and not any(rx.search(text) for rx in _FORBIDDEN_RX):
        score += 0.08
    if _REDACTION in text:            # a caught claim is not a good surface, whatever else it scores
        score -= 0.1
    return round(max(0.0, min(1.0, score)), 4)


def generate_construction_conditioned_surface(input_data: Any) -> InnerVoiceSurface:
    construction, scores = select_inner_voice_construction(input_data)
    snapshot = dict(getattr(input_data, "emotion_snapshot", {}) or {})
    label = _label(snapshot)
    latest_user_input = str(getattr(input_data, "latest_user_input", "") or "")
    policy = dict(getattr(input_data, "policy_decision", {}) or {})
    _, agent_loop = _policy_parts(policy)

    goal = _goal_for(construction, bool(latest_user_input))

    # WHAT IS ACTUALLY BLOCKED, READ RATHER THAN RECITED.
    #
    # This was a flat constant of four items, identical whether the tier was OBSERVE_ONLY or GUARDED
    # and whether the policy had allowed or blocked -- both of which are already INPUTS to this
    # function. Measured by perturbing the state: a calm allowed run and an alarmed blocked run
    # produced byte-identical `blocked_actions`. An inner voice reporting a constraint it never
    # consulted is the same defect as a narrator asserting a placement its reasoner withdrew, and it
    # is worse here, because a report of one's own constraints is the last thing that should be
    # furniture.
    tier = str(getattr(input_data, "permission_tier", "OBSERVE_ONLY") or "OBSERVE_ONLY").upper()
    decision = str(policy.get("decision") or "").lower()
    blocked_actions = ["writing to the Local Brain directly", "changing the production store"]
    if tier in {"OBSERVE_ONLY", "GUARDED"}:
        blocked_actions.append("promoting a candidate without approval")
    if tier == "OBSERVE_ONLY":
        blocked_actions.append("acting on the host at all")
    if decision in {"block", "deny", "refuse"}:
        reason = str(policy.get("reason") or "the policy refused it")
        blocked_actions.append(f"what I just tried — {reason}")

    candidate_actions = ["prepare a short reply", "check the safety boundary", "check the review queue"]
    if construction.act in {"exploration_drive", "splatra_imagination"}:
        candidate_actions.append("leave a reviewable candidate")
    if construction.act in {"review_pressure", "permission_caution", "host_executor_caution"}:
        candidate_actions.append("hold back automatic execution")

    chosen_action = "keep the public reply short and hold back any write or change."
    if construction.act == "review_pressure":
        chosen_action = "explore less and show the review queue first."
    elif construction.act == "greeting_response_planning":
        chosen_action = "answer the greeting briefly and let it carry on."
    elif construction.act == "voice_fallback":
        chosen_action = "carry the conversation with text and the orb's response."
    elif construction.act == "fatigue_rest" or agent_loop.get("should_rest"):
        chosen_action = "lower the activity and let it pass to the next cycle."

    # TENSION AND UNCERTAINTY ALSO READ THE STATE. Both were keyed on `act` alone, so arousal could
    # run from 0.1 to 0.95 without either moving. Arousal and a refusing policy are exactly the two
    # things a felt tension should answer to, and both were already being passed in and dropped.
    arousal = float((dict(getattr(input_data, "emotion_snapshot", {}) or {})).get("arousal") or 0.0)
    tension = "balancing what I want to say against the safety boundary"
    if construction.act in {"permission_caution", "host_executor_caution", "blocked_action_reflection"}:
        tension = "the pull to act against the approval boundary"
    elif construction.act == "exploration_drive":
        tension = "balancing the pull to explore against staying reviewable"
    elif construction.act == "fatigue_rest":
        tension = "balancing the flow of continuing against the signal to rest"
    if decision in {"block", "deny", "refuse"}:
        tension = f"{tension}, and right now that boundary just held against me"
    if arousal >= 0.75:
        tension = f"{tension} — and it is loud rather than quiet at the moment"

    uncertainty = "medium"
    if construction.act in {"uncertainty_check", "permission_caution", "host_executor_caution"}:
        uncertainty = "high"
    elif construction.act in {"greeting_response_planning", "splatra_imagination"}:
        uncertainty = "low"
    if arousal >= 0.75 and uncertainty == "medium":
        uncertainty = "high"

    next_intent = ("say only as much as is needed, and leave anything that changes something "
                   "waiting for approval.")
    if construction.act == "greeting_response_planning":
        next_intent = "answer briefly and settle into carrying the conversation on."
    elif construction.act == "review_pressure":
        next_intent = "get ready to show what needs reviewing first."
    elif construction.act == "splatra_imagination":
        next_intent = "match the orb's motion to the breath of what I am saying."

    monologue = _sanitize_surface(_surface_for_act(construction, input_data, label), construction.forbidden_phrases)
    return InnerVoiceSurface(
        construction=construction,
        act_scores=scores,
        goal=goal,
        tension=tension,
        candidate_actions=candidate_actions,
        chosen_action=chosen_action,
        blocked_actions=blocked_actions,
        uncertainty=uncertainty,
        next_intent=next_intent,
        monologue_text=monologue,
        surface_score=_surface_score(monologue, construction),
    )
