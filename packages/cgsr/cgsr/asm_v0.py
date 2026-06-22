from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from packages.cgsr.cgsr.conversation_constructions import (
    ConversationAct,
    ConstructionFrame,
    all_conversation_frames,
)
from packages.cgsr.cgsr.rhfc_cleanup_adapter import (
    INTERNAL_TRACE_PATTERNS,
    MUTATION_PATTERNS,
    OVERCLAIM_PATTERNS,
    score_surface_candidate,
)


ASM_GENERATION_BASIS = "local_corpus_construction_transition_model"


@dataclass(frozen=True)
class ConversationActDistribution:
    """Probability-like act distribution inferred from local features."""

    probabilities: dict[ConversationAct, float]
    features: dict[str, Any]

    def top_act(self) -> ConversationAct:
        """Return the highest-probability act."""

        return max(self.probabilities.items(), key=lambda item: (item[1], item[0]))[0]


@dataclass(frozen=True)
class SurfaceCandidate:
    """Generated surface candidate with hidden scoring metadata."""

    text: str
    construction_id: str
    score: float
    trace_hidden: bool
    flags: dict[str, bool]
    basis: str
    cleanup_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ASMSurfaceResult:
    """Final ASM-v0 surface result."""

    answer: str | None
    candidates: tuple[SurfaceCandidate, ...]
    selected_construction: str | None
    safety_flags: dict[str, bool]
    generation_basis: str
    internal_trace_exposed: bool = False
    act_distribution: ConversationActDistribution | None = None


GENERAL_KO_DIALOGUE: tuple[str, ...] = (
    "안녕 나는 지금 여기서 네 말을 듣고 있어",
    "반가워 천천히 말해도 괜찮아",
    "지금은 화면 안의 대화 상태를 따라가며 짧게 말할게",
    "네가 더 말해주면 그 흐름에 맞춰 다음 말을 고를게",
    "대화는 고정문이 아니라 배운 발화 조각들이 이어지는 표면이야",
)

SELF_MODEL_KO_DIALOGUE: tuple[str, ...] = (
    "내 자기 모델은 상태 기억 경계 다음 행동 후보를 함께 묶어 보는 작은 루프야",
    "나는 진짜 의식이라고 주장하지 않고 허용된 범위 안에서 자기 상태를 정리해",
    "생각 중추는 밖으로 보일 문장과 내부 상태를 분리해서 다루는 표면 모델이야",
    "자기 모델 루프는 기억 승인 경계와 다음 대화 후보를 함께 본다",
)

MEMORY_KO_DIALOGUE: tuple[str, ...] = (
    "기억 요청은 바로 저장하지 않고 로컬 브레인 승인 후보로 제안할 수 있어",
    "로컬 브레인 쓰기는 사용자가 승인하기 전까지 잠겨 있어",
    "기억 후보는 현재 대화와 분리해서 검토 대기로 남겨야 해",
)

VOICE_KO_DIALOGUE: tuple[str, ...] = (
    "음성은 선택 사항이고 텍스트 입력은 계속 사용할 수 있어",
    "Fish 이가 준비되면 같은 발화를 소리로 낼 수 있어",
    "항상 켜진 마이크 없이 사용자가 선택한 순간에만 음성 모드로 들어가야 해",
)

APPROVAL_KO_DIALOGUE: tuple[str, ...] = (
    "승인이 필요한 제안은 바로 반영하지 않고 검토 대기로 남겨야 해",
    "후보 승격과 로컬 브레인 쓰기는 승인 게이트를 지나야 해",
    "바뀌는 일은 먼저 제안으로 보여주고 사용자가 고른 뒤에 진행해야 해",
)

BRIEF_KO_DIALOGUE: tuple[str, ...] = (
    "브리프는 현재 상태를 요약하지만 개인 기억을 바꾸지 않아",
    "아침과 저녁 브리프는 승인 대기와 진행 상태를 짧게 묶어 보여줄 수 있어",
)

STATUS_KO_DIALOGUE: tuple[str, ...] = (
    "지금은 대화 상태와 안전 잠금을 유지하면서 다음 요청을 기다리고 있어",
    "현재는 로컬 쓰기 없이 화면 안에서 응답을 준비하는 중이야",
)

_ACT_CORPORA: dict[ConversationAct, tuple[str, ...]] = {
    "greeting": GENERAL_KO_DIALOGUE,
    "status_question": STATUS_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "self_model_question": SELF_MODEL_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "memory_question": MEMORY_KO_DIALOGUE + APPROVAL_KO_DIALOGUE,
    "approval_question": APPROVAL_KO_DIALOGUE + MEMORY_KO_DIALOGUE,
    "voice_question": VOICE_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "brief_request": BRIEF_KO_DIALOGUE + STATUS_KO_DIALOGUE,
    "correction": GENERAL_KO_DIALOGUE + ("맞아 다음 말에서는 그 표현을 조정할게",),
    "open_chat": GENERAL_KO_DIALOGUE + STATUS_KO_DIALOGUE,
    "unknown": GENERAL_KO_DIALOGUE,
}

_ACT_CUES: dict[ConversationAct, tuple[str, ...]] = {
    "greeting": ("안녕", "반가워", "하이", "hello", "hi"),
    "status_question": ("뭐", "하고", "상태", "지금", "대기", "준비"),
    "self_model_question": ("자기", "모델", "자의식", "생각", "중추", "루프", "내적"),
    "memory_question": ("기억", "로컬", "브레인", "저장", "메모리"),
    "approval_question": ("승인", "검토", "대기", "제안", "반영", "승격"),
    "voice_question": ("음성", "목소리", "말할", "말해", "Fish", "마이크"),
    "brief_request": ("브리프", "요약", "아침", "저녁", "밤사이"),
    "correction": ("아니", "수정", "틀렸", "바꿔", "그게"),
    "open_chat": ("말", "대화", "얘기", "물어"),
    "unknown": (),
}

_FORBIDDEN_PATTERNS = INTERNAL_TRACE_PATTERNS + OVERCLAIM_PATTERNS + MUTATION_PATTERNS


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^\w가-힣]+", " ", _normalize(text), flags=re.UNICODE)
    return [token for token in cleaned.split() if token]


def _token_root(token: str) -> str:
    if re.search(r"[가-힣]", token):
        return re.sub(r"(은|는|이|가|을|를|아|야|에게|에서|으로|처럼|하고|해줘|해봐|나요|니)$", "", token)
    return token


def _char_grams(text: str, width: int = 2) -> Counter[str]:
    compact = re.sub(r"\s+", "", _normalize(text))
    if not compact:
        return Counter()
    if len(compact) <= width:
        return Counter({compact: 1})
    return Counter(compact[index : index + width] for index in range(len(compact) - width + 1))


def _cosine_counter(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(left[key] * right.get(key, 0) for key in left)
    denom = math.sqrt(sum(value * value for value in left.values()) * sum(value * value for value in right.values()))
    return dot / denom if denom else 0.0


def _stable_unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _safe_flags() -> dict[str, bool]:
    return {
        "external_llm": False,
        "external_sllm": False,
        "rule_based_answer_used": False,
        "template_free_surface": True,
        "local_brain_write": False,
        "production_store_mutated": False,
        "candidate_promotion": False,
        "internal_trace_exposed": False,
    }


def infer_conversation_act(input_text: str, context: dict[str, Any] | None = None) -> ConversationActDistribution:
    """Infer a distribution over conversation acts from local features.

    This is a conditioning model, not an answer router. The act distribution is
    used to choose construction frames and lexical fields; it never returns a
    final response string.
    """

    context = context or {}
    query = _normalize(input_text)
    query_tokens = {_token_root(token) for token in _tokens(query)}
    query_grams = _char_grams(query)
    length = len(query)
    punctuation_bonus = 0.08 if "?" in input_text or "？" in input_text else 0.0
    scores: dict[ConversationAct, float] = {}

    for act, cues in _ACT_CUES.items():
        cue_roots = {_token_root(cue.lower()) for cue in cues}
        cue_hits = len(query_tokens & cue_roots)
        cue_substring_hits = sum(1 for cue in cues if cue and cue.lower() in query)
        cue_score = cue_hits * 0.44 + cue_substring_hits * 0.34
        corpus = _ACT_CORPORA.get(act, GENERAL_KO_DIALOGUE)
        corpus_similarity = max((_cosine_counter(query_grams, _char_grams(sentence)) for sentence in corpus), default=0.0)
        frame_prior = sum(frame.prior for frame in all_conversation_frames() if frame.act == act) / max(1, len([frame for frame in all_conversation_frames() if frame.act == act]))
        scores[act] = 0.08 + cue_score + corpus_similarity * 0.72 + frame_prior * 0.08

    if length <= 8:
        scores["greeting"] += 0.08
        scores["open_chat"] += 0.04
    scores["status_question"] += punctuation_bonus
    if context.get("voice_mode"):
        scores["voice_question"] += 0.14
    if context.get("pending_approval"):
        scores["approval_question"] += 0.16

    total = sum(max(0.0, value) for value in scores.values()) or 1.0
    probabilities = {act: round(max(0.0, score) / total, 6) for act, score in scores.items()}
    return ConversationActDistribution(
        probabilities=probabilities,
        features={
            "length": length,
            "token_count": len(query_tokens),
            "question_mark": punctuation_bonus > 0,
            "top_cues": sorted(query_tokens)[:12],
        },
    )


def _candidate_frames(distribution: ConversationActDistribution) -> list[ConstructionFrame]:
    ranked_acts = [act for act, _ in sorted(distribution.probabilities.items(), key=lambda item: (-item[1], item[0]))[:3]]
    frames = [frame for frame in all_conversation_frames() if frame.act in ranked_acts]
    if not frames:
        frames = [frame for frame in all_conversation_frames() if frame.act == "open_chat"]
    return sorted(frames, key=lambda frame: (distribution.probabilities.get(frame.act, 0.0) * frame.prior, frame.frame_id), reverse=True)


def _build_transition_graph(corpus: tuple[str, ...], frame: ConstructionFrame, focus: list[str]) -> tuple[dict[str, Counter[str]], Counter[str]]:
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    frequencies: Counter[str] = Counter()
    lexical_line = " ".join(frame.lexical_fields)
    discourse_line = " ".join(frame.discourse_moves)
    weighted = list(corpus) + focus + focus + [lexical_line, discourse_line]
    for sentence in weighted:
        tokens = _tokens(sentence)
        frequencies.update(tokens)
        for left, right in zip(tokens, tokens[1:]):
            transitions[left][right] += 1
    return transitions, frequencies


def _score_seed_sentence(input_text: str, sentence: str, frame: ConstructionFrame) -> float:
    query_grams = _char_grams(input_text)
    sentence_grams = _char_grams(sentence)
    char_score = _cosine_counter(query_grams, sentence_grams)
    query_roots = {_token_root(token) for token in _tokens(input_text)}
    sentence_roots = {_token_root(token) for token in _tokens(sentence)}
    lexical_hits = sum(1 for token in frame.lexical_fields if token and token in sentence)
    token_overlap = len(query_roots & sentence_roots) / max(1, len(query_roots))
    return char_score + token_overlap * 0.38 + lexical_hits * 0.012


def _walk_for_frame(input_text: str, frame: ConstructionFrame, variant: int) -> str | None:
    corpus = _ACT_CORPORA.get(frame.act, GENERAL_KO_DIALOGUE)
    scored = sorted(
        ((_score_seed_sentence(input_text, sentence, frame), sentence) for sentence in corpus),
        key=lambda item: (-item[0], item[1]),
    )
    focus = [sentence for score, sentence in scored[:4] if score > 0.0] or list(corpus[:2])
    transitions, frequencies = _build_transition_graph(corpus, frame, focus)
    if not transitions:
        return None

    starts = [_tokens(sentence)[0] for sentence in focus if _tokens(sentence)]
    starts.extend(token for token in frame.lexical_fields if token in transitions)
    starts.extend(token for token in _tokens(input_text) if token in transitions)
    if not starts:
        starts = [token for token, _ in frequencies.most_common(6)]
    if not starts:
        return None

    start_index = int(_stable_unit(f"{input_text}|{frame.frame_id}|{variant}") * len(starts)) % len(starts)
    current = starts[start_index]
    generated = [current]
    recent: Counter[str] = Counter({current: 1})
    min_len, max_len = frame.length_target
    target_len = min(max_len, max(min_len, min_len + variant + 3))

    for step in range(target_len - 1):
        options = transitions.get(current)
        if not options:
            break
        ranked: list[tuple[float, str]] = []
        for token, weight in options.items():
            repetition_penalty = 1.0 / (1.0 + recent[token] * 2.1)
            lexical_bonus = 0.18 if token in frame.lexical_fields else 0.0
            tie = _stable_unit(f"{input_text}|{frame.frame_id}|{variant}|{current}|{token}|{step}") * 0.01
            ranked.append((float(weight) * repetition_penalty + lexical_bonus + tie, token))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        next_token = ranked[0][1]
        if recent[next_token] >= 2:
            break
        generated.append(next_token)
        recent[next_token] += 1
        current = next_token

    if len(generated) < 3:
        return None
    sentence = re.sub(r"\s+", " ", " ".join(generated)).strip()
    if not sentence:
        return None
    return sentence if sentence.endswith((".", "?", "!")) else f"{sentence}."


def _repair_mutation_implication(text: str) -> str:
    repaired = text
    repaired = repaired.replace("기억해둘게", "기억 후보로 제안할 수 있어")
    repaired = repaired.replace("바로 반영할게", "승인 뒤에 반영할 수 있어")
    repaired = repaired.replace("저장할게", "승인 후보로 남길 수 있어")
    repaired = repaired.replace("승격할게", "승격 후보로 남길 수 있어")
    return repaired


def _candidate_flags() -> dict[str, bool]:
    return _safe_flags()


def _make_candidate(text: str, frame: ConstructionFrame, context: dict[str, Any]) -> SurfaceCandidate | None:
    repaired = _repair_mutation_implication(text)
    if any(pattern.lower() in repaired.lower() for pattern in _FORBIDDEN_PATTERNS):
        return None
    decision = score_surface_candidate(repaired, frame, context)
    if decision.blocked:
        return None
    return SurfaceCandidate(
        text=repaired,
        construction_id=frame.frame_id,
        score=decision.score,
        trace_hidden=True,
        flags=_candidate_flags(),
        basis=ASM_GENERATION_BASIS,
        cleanup_reasons=decision.reasons,
    )


def generate_surface(input_text: str, context: dict[str, Any] | None = None) -> ASMSurfaceResult:
    """Generate a local construction-conditioned conversation surface."""

    context = context or {}
    distribution = infer_conversation_act(input_text, context)
    candidates: list[SurfaceCandidate] = []
    for frame in _candidate_frames(distribution):
        frame_context = {**context, "speech_act": frame.act}
        for variant in range(3):
            text = _walk_for_frame(input_text, frame, variant)
            if text is None:
                continue
            candidate = _make_candidate(text, frame, frame_context)
            if candidate is not None:
                act_bonus = distribution.probabilities.get(frame.act, 0.0) * 2.0
                candidate = SurfaceCandidate(
                    text=candidate.text,
                    construction_id=candidate.construction_id,
                    score=round(candidate.score + act_bonus, 4),
                    trace_hidden=candidate.trace_hidden,
                    flags=candidate.flags,
                    basis=candidate.basis,
                    cleanup_reasons=candidate.cleanup_reasons,
                )
                candidates.append(candidate)

    deduped: dict[str, SurfaceCandidate] = {}
    for candidate in candidates:
        previous = deduped.get(candidate.text)
        if previous is None or candidate.score > previous.score:
            deduped[candidate.text] = candidate
    ranked = tuple(sorted(deduped.values(), key=lambda item: (-item.score, item.construction_id, item.text)))
    selected = ranked[0] if ranked else None
    return ASMSurfaceResult(
        answer=selected.text if selected else None,
        candidates=ranked[:8],
        selected_construction=selected.construction_id if selected else None,
        safety_flags=_safe_flags(),
        generation_basis=ASM_GENERATION_BASIS,
        internal_trace_exposed=False,
        act_distribution=distribution,
    )


def result_to_public_diagnostics(result: ASMSurfaceResult) -> dict[str, Any]:
    """Return bounded diagnostics safe for API metadata."""

    return {
        "generation_basis": result.generation_basis,
        "selected_construction": result.selected_construction,
        "candidate_count": len(result.candidates),
        "top_act": result.act_distribution.top_act() if result.act_distribution else None,
        "act_distribution": result.act_distribution.probabilities if result.act_distribution else {},
        "safety_flags": result.safety_flags,
        "internal_trace_exposed": result.internal_trace_exposed,
        "candidates_hidden": True,
    }


def result_to_jsonable(result: ASMSurfaceResult) -> dict[str, Any]:
    """Return a complete JSON-serializable result for tests and audits."""

    return {
        "answer": result.answer,
        "candidates": [asdict(candidate) for candidate in result.candidates],
        "selected_construction": result.selected_construction,
        "safety_flags": result.safety_flags,
        "generation_basis": result.generation_basis,
        "internal_trace_exposed": result.internal_trace_exposed,
        "act_distribution": result.act_distribution.probabilities if result.act_distribution else {},
    }
