from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from packages.cgsr.cgsr.conversation_constructions import (
    ConversationAct,
    ConstructionFrame,
    all_conversation_frames,
)
from packages.cgsr.cgsr.korean_discourse import (
    repair_korean_surface_candidate,
    score_korean_naturalness,
    select_best_korean_candidate,
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
    "안녕 나는 여기서 네 말을 듣고 있어.",
    "반가워 천천히 말해줘.",
    "좋아 지금부터 같이 볼게.",
    "바로 이어서 말해줘.",
    "나는 화면 안에서 네 다음 말을 기다리고 있어.",
    "짧게 말해도 괜찮아.",
)

SELF_MODEL_KO_DIALOGUE: tuple[str, ...] = (
    "내 자기 모델 루프는 상태를 관찰하고 부족한 점을 감지한 뒤 제안을 만든다.",
    "나는 실제 의식을 주장하지 않고 지금 가능한 상태와 경계만 설명한다.",
    "내적 기록은 사용자에게 보이지 않고 최종 발화만 화면에 나온다.",
    "자기 모델은 기억 경계와 승인 대기를 함께 보면서 다음 행동 후보를 고른다.",
    "나는 자율 상태를 과장하지 않고 관찰 제안 승인 경계를 분리한다.",
)

MEMORY_KO_DIALOGUE: tuple[str, ...] = (
    "그 내용은 바로 저장하지 않고 기억 후보로 분리해 둘 수 있어.",
    "로컬 브레인 쓰기는 사용자 승인이 있어야만 진행된다.",
    "기억 요청은 현재 대화와 분리해서 검토 대기로 남겨야 해.",
    "원하면 승인 후보로 정리하고 실제 저장은 막아둘게.",
    "개인 기억은 자동으로 쓰지 않고 검토 단계에만 올린다.",
)

VOICE_KO_DIALOGUE: tuple[str, ...] = (
    "음성은 선택 기능이고 텍스트 입력은 계속 사용할 수 있어.",
    "Fish 2가 준비되면 같은 발화를 소리로 낼 수 있어.",
    "마이크는 사용자가 누른 순간에만 음성 모드로 들어가고 텍스트 입력은 남아 있어.",
    "지금은 텍스트 대화를 유지하고 음성 준비 상태만 확인한다.",
)

APPROVAL_KO_DIALOGUE: tuple[str, ...] = (
    "승인이 필요한 제안은 바로 반영하지 않고 검토 대기에 남겨야 해.",
    "후보 목록과 로컬 브레인 쓰기는 승인 게이트를 통과해야 한다.",
    "바뀌는 일은 먼저 제안으로 보여주고 사용자가 고른 뒤에만 진행된다.",
    "승격 후보는 공용 지식에 바로 들어가지 않고 검토 상태로 멈춘다.",
)

BRIEF_KO_DIALOGUE: tuple[str, ...] = (
    "브리프는 현재 상태를 요약하지만 개인 기억을 바꾸지 않는다.",
    "아침 저녁 상태 브리프는 승인 대기와 진행 상황을 짧게 묶어 보여준다.",
    "준비된 브리프는 읽기 전용으로 만들고 저장은 따로 승인받는다.",
)

STATUS_KO_DIALOGUE: tuple[str, ...] = (
    "지금은 현재 상태와 안전 잠금을 유지하면서 다음 요청을 기다리고 있어.",
    "대화 화면 안에서 필요한 제안과 승인 대기를 정리하고 있어.",
    "로컬 브레인이나 클라우드 브레인을 바꾸지 않고 대화 준비만 하고 있어.",
    "지금은 네 말을 듣고 필요한 다음 행동 후보를 고르는 중이야.",
)

CORRECTION_KO_DIALOGUE: tuple[str, ...] = (
    "맞아 그 표현은 다음 답변에서 더 자연스럽게 조정할게.",
    "알겠어 지금 표면 문장만 고치고 기억이나 지식은 바꾸지 않을게.",
)

_LEGACY_ACT_CORPORA_UNUSED: dict[ConversationAct, tuple[str, ...]] = {
    "greeting": GENERAL_KO_DIALOGUE,
    "status_question": STATUS_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "self_model_question": SELF_MODEL_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "memory_question": MEMORY_KO_DIALOGUE + APPROVAL_KO_DIALOGUE,
    "approval_question": APPROVAL_KO_DIALOGUE + MEMORY_KO_DIALOGUE,
    "voice_question": VOICE_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "brief_request": BRIEF_KO_DIALOGUE + STATUS_KO_DIALOGUE,
    "correction": CORRECTION_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "open_chat": GENERAL_KO_DIALOGUE + STATUS_KO_DIALOGUE,
    "unknown": GENERAL_KO_DIALOGUE,
}

_LEGACY_ACT_CUES_UNUSED: dict[ConversationAct, tuple[str, ...]] = {
    "greeting": ("안녕", "반가워", "하이", "hello", "hi"),
    "status_question": ("뭐", "하고", "상태", "지금", "대기", "준비", "뭘"),
    "self_model_question": ("자기", "모델", "자의식", "살아", "생각", "루프", "내적"),
    "memory_question": ("기억", "로컬", "브레인", "저장", "메모리", "기록"),
    "approval_question": ("승인", "검토", "대기", "제안", "반영", "승격"),
    "voice_question": ("음성", "목소리", "말할", "말해", "Fish", "마이크"),
    "brief_request": ("브리프", "요약", "아침", "저녁", "밤사이"),
    "correction": ("아니", "수정", "다시", "바꿔", "그게"),
    "open_chat": ("말", "대화", "하기", "물어"),
    "unknown": (),
}

_FORBIDDEN_PATTERNS = INTERNAL_TRACE_PATTERNS + OVERCLAIM_PATTERNS + MUTATION_PATTERNS


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9가-힣]+", _normalize(text), flags=re.UNICODE)


def _token_root(token: str) -> str:
    if re.search(r"[가-힣]", token):
        return re.sub(
            r"(은|는|이|가|을|를|에게|에서|으로|처럼|하고|해줘|해주세요|해요|한다|하는|하니|해|야|요)$",
            "",
            token,
        )
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

    all_frames = all_conversation_frames()
    for act, cues in _act_cues().items():
        cue_roots = {_token_root(cue.lower()) for cue in cues}
        cue_hits = len(query_tokens & cue_roots)
        cue_substring_hits = sum(1 for cue in cues if cue and cue.lower() in query)
        cue_score = cue_hits * 0.44 + cue_substring_hits * 0.34
        corpus = _act_corpora().get(act, _default_dialogue())
        corpus_similarity = max((_cosine_counter(query_grams, _char_grams(sentence)) for sentence in corpus), default=0.0)
        frames_for_act = [frame for frame in all_frames if frame.act == act]
        frame_prior = sum(frame.prior for frame in frames_for_act) / max(1, len(frames_for_act))
        scores[act] = 0.08 + cue_score + corpus_similarity * 0.72 + frame_prior * 0.08

    if length <= 8:
        scores["greeting"] += 0.08
        scores["open_chat"] += 0.04
    scores["status_question"] += punctuation_bonus
    if any(token in query for token in ("승인", "검토", "후보", "반영", "승격")):
        scores["approval_question"] += 1.35
    if any(token in query for token in ("제안", "승인", "검토", "반영", "승격")):
        scores["approval_question"] += 1.2
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
    return char_score + token_overlap * 0.38 + lexical_hits * 0.012 + score_korean_naturalness(sentence) * 0.08


def _walk_for_frame(input_text: str, frame: ConstructionFrame, variant: int) -> str | None:
    corpus = _act_corpora().get(frame.act, _default_dialogue())
    scored = sorted(
        ((_score_seed_sentence(input_text, sentence, frame), sentence) for sentence in corpus),
        key=lambda item: (-item[0], item[1]),
    )
    if _english_only():
        # The Markov re-assembly below tokenises and re-chains the corpus — it assumes an
        # AGGLUTINATIVE language where re-joining morphemes yields a valid word order. Run it on
        # English and it shreds the sentence (measured: "Once Fish is ready I can say the same
        # sentence out loud." → "fish is ready i ll keep answering in text input"). These surfaces
        # are OUR authored, act-matched sentences, so English selects one whole — nothing is
        # invented, and each variant offers a different real sentence rather than mush.
        picks = [s for score, s in scored if score > 0.0] or list(corpus)
        return picks[variant % len(picks)] if picks else None
    focus = [sentence for score, sentence in scored[:4] if score > 0.0] or list(corpus[:2])
    transitions, frequencies = _build_transition_graph(corpus, frame, focus)
    if not transitions:
        return None

    # Holographic phase-context: a SUPERPOSED state of everything emitted so far, so the next
    # token is chosen by INTERFERENCE with the whole context (not just the last token). Bounded
    # nudge — local transition counts still lead; interference breaks ties toward coherence and
    # steers away from off-topic drift. Falls back to pure Markov if the field can't be built.
    try:
        from .phase_context import PhaseField, Superposition

        _field: PhaseField | None = PhaseField(list(corpus) + list(focus))
    except Exception:  # pragma: no cover - generation must never break on the upgrade
        _field = None

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

    _sup = Superposition(_field) if _field is not None else None
    if _sup is not None:
        _sup.add(current)

    for step in range(target_len - 1):
        options = transitions.get(current)
        if not options:
            break
        ranked: list[tuple[float, str]] = []
        for token, weight in options.items():
            repetition_penalty = 1.0 / (1.0 + recent[token] * 2.1)
            lexical_bonus = 0.18 if token in frame.lexical_fields else 0.0
            # Interference with the whole context so far (bounded [-1,1] → scaled nudge).
            interference = 0.4 * _sup.interference(token) if _sup is not None else 0.0
            tie = _stable_unit(f"{input_text}|{frame.frame_id}|{variant}|{current}|{token}|{step}") * 0.01
            ranked.append((float(weight) * repetition_penalty + lexical_bonus + interference + tie, token))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        next_token = ranked[0][1]
        if recent[next_token] >= 2:
            break
        generated.append(next_token)
        recent[next_token] += 1
        current = next_token
        if _sup is not None:
            _sup.add(next_token)

    if len(generated) < 3:
        return None
    sentence = re.sub(r"\s+", " ", " ".join(generated)).strip()
    if not sentence:
        return None
    return sentence if sentence.endswith((".", "?", "!")) else f"{sentence}."


def _repair_mutation_implication(text: str) -> str:
    repaired = text
    repaired = repaired.replace("기억해둘게", "기억 후보로 제안할 수 있어")
    repaired = repaired.replace("바로 반영할게", "승인 뒤에만 반영할 수 있어")
    repaired = repaired.replace("저장할게", "승인 후보로 남길 수 있어")
    repaired = repaired.replace("승격할게", "승격 후보로 남길 수 있어")
    return repaired


def _candidate_flags() -> dict[str, bool]:
    return _safe_flags()


def _make_candidate(text: str, frame: ConstructionFrame, context: dict[str, Any]) -> SurfaceCandidate | None:
    repaired = repair_korean_surface_candidate(_repair_mutation_implication(text), frame, context)
    if any(pattern.lower() in repaired.lower() for pattern in _FORBIDDEN_PATTERNS):
        return None
    decision = score_surface_candidate(repaired, frame, context)
    if decision.blocked:
        return None
    return SurfaceCandidate(
        text=repaired,
        construction_id=frame.frame_id,
        score=round(decision.score + score_korean_naturalness(repaired) * 0.2, 4),
        trace_hidden=True,
        flags=_candidate_flags(),
        basis=ASM_GENERATION_BASIS,
        cleanup_reasons=decision.reasons,
    )


# ── consistent voice ─────────────────────────────────────────────────────────


# with the self-model and reasoning surfaces, which are already polite); a clearly

_POLITE_LEAD = {
    "안녕하세요": "안녕하세요", "안녕": "안녕하세요", "반가워요": "반가워요", "반가워": "반가워요",
    "하이": "안녕하세요", "응": "네", "좋아요": "좋아요", "좋아": "좋아요", "맞아요": "맞아요", "맞아": "맞아요",
}
_POLITE_END = [
    ("말해줘", "말해주세요"), ("알려줘", "알려드릴게요"), ("보여줘", "보여드릴게요"), ("줘", "주세요"),
    ("조정할게", "조정할게요"), ("반영해볼게", "반영해볼게요"), ("유지할게", "유지할게요"), ("볼게", "볼게요"), ("할게", "할게요"),
    ("볼까", "볼까요"), ("돼", "돼요"), ("중이야", "중이에요"), ("이야", "이에요"), ("됐어", "됐어요"),
    ("있어", "있어요"), ("관찰해", "관찰해요"), ("이다", "이에요"), ("본다", "봐요"), ("둔다", "둬요"),
    ("않는다", "않아요"), ("있다", "있어요"), ("진행한다", "진행해요"), ("한다", "해요"),
]


def _user_prefers_polite(text: str) -> bool:
    t = (text or "").strip()
    if re.search(r"(요|니다|세요|십니까|까요|나요|인가요|습니까|주세요)[?!.\s]*$", t):
        return True
    # a clear casual ending → mirror casual; otherwise default to the polite voice
    if re.search(r"(어|아|야|지|니|래|자|줘|해|냐)[?!.\s]*$", t):
        return False
    return True


def _voice_polish(text: str, input_text: str) -> str:
    if not text:
        return text
    if _english_only():

        # the rewrite only corrupts it — the English surfaces are already written in the voice we
        # want. Whitespace tidy only.
        return re.sub(r"\s{2,}", " ", text).strip()
    if not _user_prefers_polite(input_text):
        return re.sub(r"\s{2,}", " ", text).strip()
    # Split into [clause, delim, clause, delim, …]; rewrite clauses only, keep the
    # original delimiters and spacing so punctuation is never lost.
    parts = re.split(r"([.?!]+)", text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1 or not part.strip():
            out.append(part)
            continue
        lead_ws = part[: len(part) - len(part.lstrip())]
        seg = part.strip()
        for lead, rep in _POLITE_LEAD.items():
            if seg.startswith(lead):
                seg = rep + seg[len(lead):]
                break
        for pat, rep in _POLITE_END:
            if seg.endswith(pat):
                seg = seg[: -len(pat)] + rep
                break
        out.append(lead_ws + seg)
    return re.sub(r"\s{2,}", " ", "".join(out)).strip()


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
    ranked_all = tuple(sorted(deduped.values(), key=lambda item: (-item.score, item.construction_id, item.text)))
    top_act = distribution.top_act()
    top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith(f"conv.{top_act.split('_')[0]}"))
    if top_act == "status_question":
        top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith("conv.status."))
    elif top_act == "self_model_question":
        top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith("conv.self_model."))
    elif top_act == "memory_question":
        top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith("conv.memory."))
    elif top_act == "approval_question":
        top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith("conv.approval."))
    elif top_act == "voice_question":
        top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith("conv.voice."))
    elif top_act == "brief_request":
        top_act_candidates = tuple(candidate for candidate in ranked_all if candidate.construction_id.startswith("conv.brief."))
    selected = select_best_korean_candidate(top_act_candidates or ranked_all)
    if selected is not None:
        ranked = (selected,) + tuple(candidate for candidate in ranked_all if candidate.text != selected.text)
    else:
        ranked = ranked_all
    return ASMSurfaceResult(
        answer=_voice_polish(selected.text, input_text) if selected else None,
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


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9가-힣]+", _normalize(text), flags=re.UNICODE)


def _token_root(token: str) -> str:
    if re.search(r"[가-힣]", token):
        return re.sub(r"(입니다|합니다|했어요|해요|할까|할게|할께|에서|으로|에게|하고|하는|하다|요|은|는|이|가|을|를)$", "", token)
    return token


GENERAL_KO_DIALOGUE = (
    "안녕. 나 여기 있어.",
    "안녕. 편하게 말해줘.",
    "반가워. 오늘은 뭐부터 볼까?",
    "응, 준비됐어.",
    "좋아. 지금 이야기해도 돼.",
    "하이. 바로 같이 볼게.",
)

SELF_MODEL_KO_DIALOGUE = (
    "나는 자기 모델 루프로 현재 상태와 경계를 관찰해.",
    "실제 의식을 주장하지 않고 목표와 제약을 나눠서 본다.",
    "내적 서술은 숨은 사고가 아니라 관찰 가능한 상태 요약이다.",
    "사용자 승인 없이 기억이나 공용 지식은 바꾸지 않는다.",
)

MEMORY_KO_DIALOGUE = (
    "그 내용은 바로 저장하지 않고 기억 후보로만 분리할게.",
    "로컬 브레인 쓰기는 사용자 승인이 있어야 진행된다.",
    "지금은 기억 후보를 검토 대기에 둘 수 있어.",
)

VOICE_KO_DIALOGUE = (
    "음성은 선택 기능이고 텍스트 입력은 계속 사용할 수 있어.",
    "Fish가 준비되면 같은 문장을 소리로도 말할 수 있어.",
    "지금은 텍스트 응답을 우선 유지할게.",
)

APPROVAL_KO_DIALOGUE = (
    "승인이 필요한 제안은 바로 반영하지 않고 검토 대기에 둔다.",
    "후보 승격과 기억 쓰기는 승인 게이트를 지나야 한다.",
    "바뀌는 일은 먼저 제안으로 보여주고 사용자가 고른 뒤에만 진행한다.",
)

BRIEF_KO_DIALOGUE = (
    "브리프는 현재 상태를 요약하지만 개인 기억을 바꾸지 않는다.",
    "준비된 브리프는 읽기용으로 만들고 저장은 따로 승인받는다.",
)

STATUS_KO_DIALOGUE = (
    "지금은 안전 플래그를 유지하면서 다음 요청을 기다리고 있어.",
    "현재는 제안과 검토 대기를 정리하는 중이야.",
)

CORRECTION_KO_DIALOGUE = (
    "맞아. 다음 표현은 더 자연스럽게 조정할게.",
    "좋아, 그 피드백을 다음 말투에 반영해볼게.",
)


# was Korean-ONLY — no English bank existed at all, so every greeting/status/self answer came out
# in Korean no matter what language was asked (measured: 5/8 probes leaked Hangul). English-core
# means the VOICE is English too, not just the retrieval. Same acts, same honesty (no consciousness
# claim, approval-gated writes) — only the language differs. [[english-core-architecture]]
GENERAL_EN_DIALOGUE = (
    "Hi — I'm here.",
    "Hey. Ask me anything.",
    "Good to see you. Where do you want to start?",
    "Yes, I'm ready.",
    "Sure — go ahead.",
    "Hi. Let's look at it together.",
)

SELF_MODEL_EN_DIALOGUE = (
    "I watch my own state and limits through a self-model loop.",
    "I don't claim real consciousness — I track goals and constraints separately.",
    "My inner narration is an observable state summary, not hidden thought.",
    "I don't change memory or shared knowledge without your approval.",
)

MEMORY_EN_DIALOGUE = (
    "I won't store that outright — I'll keep it as a memory candidate.",
    "Writing to the Local Brain needs your approval first.",
    "For now I can hold that candidate in the review queue.",
)

VOICE_EN_DIALOGUE = (
    "Voice is optional — typing keeps working either way.",
    "Once Fish is ready I can say the same sentence out loud.",
    "For now I'll keep answering in text.",
)

APPROVAL_EN_DIALOGUE = (
    "Anything needing approval waits in review instead of applying itself.",
    "Candidate promotion and memory writes both pass an approval gate.",
    "I show changes as proposals first and only act once you pick one.",
)

BRIEF_EN_DIALOGUE = (
    "A brief summarizes the current state; it doesn't change your memory.",
    "I build the brief read-only — saving it is approved separately.",
)

STATUS_EN_DIALOGUE = (
    "I'm holding the safety flags and waiting for your next request.",
    "Right now I'm tidying up proposals and the review queue.",
)

CORRECTION_EN_DIALOGUE = (
    "You're right — I'll phrase that more naturally next time.",
    "Good catch. I'll fold that into how I say it from here.",
)

_ACT_CORPORA_EN = {
    "greeting": GENERAL_EN_DIALOGUE,
    "status_question": STATUS_EN_DIALOGUE + GENERAL_EN_DIALOGUE,
    "self_model_question": SELF_MODEL_EN_DIALOGUE + GENERAL_EN_DIALOGUE,
    "memory_question": MEMORY_EN_DIALOGUE + APPROVAL_EN_DIALOGUE,
    "approval_question": APPROVAL_EN_DIALOGUE + MEMORY_EN_DIALOGUE,
    "voice_question": VOICE_EN_DIALOGUE + GENERAL_EN_DIALOGUE,
    "brief_request": BRIEF_EN_DIALOGUE + STATUS_EN_DIALOGUE,
    "correction": CORRECTION_EN_DIALOGUE + GENERAL_EN_DIALOGUE,
    "open_chat": GENERAL_EN_DIALOGUE + STATUS_EN_DIALOGUE,
    "unknown": GENERAL_EN_DIALOGUE,
}

_ACT_CORPORA_KO = {
    "greeting": GENERAL_KO_DIALOGUE,
    "status_question": STATUS_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "self_model_question": SELF_MODEL_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "memory_question": MEMORY_KO_DIALOGUE + APPROVAL_KO_DIALOGUE,
    "approval_question": APPROVAL_KO_DIALOGUE + MEMORY_KO_DIALOGUE,
    "voice_question": VOICE_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "brief_request": BRIEF_KO_DIALOGUE + STATUS_KO_DIALOGUE,
    "correction": CORRECTION_KO_DIALOGUE + GENERAL_KO_DIALOGUE,
    "open_chat": GENERAL_KO_DIALOGUE + STATUS_KO_DIALOGUE,
    "unknown": GENERAL_KO_DIALOGUE,
}


# ATANOR_ENGLISH_ONLY=0 selects the archived Korean lane. Read at CALL time, not import time, so
# the lane can be switched (and both lanes tested) without reloading the module.
def _english_only() -> bool:
    return os.environ.get("ATANOR_ENGLISH_ONLY") != "0"


def _act_corpora() -> dict[str, tuple[str, ...]]:
    return _ACT_CORPORA_EN if _english_only() else _ACT_CORPORA_KO


def _default_dialogue() -> tuple[str, ...]:
    return GENERAL_EN_DIALOGUE if _english_only() else GENERAL_KO_DIALOGUE
# Act cues. English cues are FIRST-CLASS (owner 2026-07-17 English-only): before this only
# "greeting" had any English cue, so every English question that wasn't a hello scored zero
# everywhere and collapsed into the greeting lane (measured: "can you remember this" → "Hi —
# I'm here."). Korean cues are kept for the archived Korean lane (ATANOR_ENGLISH_ONLY=0).
_ACT_CUES_EN = {
    "greeting": ("hello", "hi", "hey", "morning", "evening", "good to see"),
    "status_question": ("what are you", "what're you", "doing", "status", "busy", "up to",
                        "right now", "ready", "waiting"),
    "self_model_question": ("who are you", "yourself", "self", "conscious", "aware", "think",
                            "feel", "your model", "inner", "sentient"),
    "memory_question": ("remember", "memory", "store", "save", "forget", "recall",
                        "local brain", "keep this"),
    "approval_question": ("approve", "approval", "review", "propose", "proposal", "candidate",
                          "permission", "confirm"),
    "voice_question": ("voice", "speak", "say it", "out loud", "talk", "fish", "microphone", "mic"),
    "brief_request": ("brief", "summary", "summarize", "recap", "report", "digest"),
    "correction": ("no,", "not quite", "wrong", "actually", "correct", "rephrase", "again"),
    "open_chat": ("chat", "tell me", "ask", "talk about", "let's"),
    "unknown": (),
}

_ACT_CUES_KO = {
    "greeting": ("안녕", "안녕하세요", "하이", "반가워", "ㅎㅇ", "hello", "hi"),
    "status_question": ("뭐", "하고", "상태", "지금", "대기", "준비"),
    "self_model_question": ("자기", "모델", "자의식", "자아", "생각", "루프", "내적"),
    "memory_question": ("기억", "로컬", "브레인", "저장", "메모리", "기록"),
    "approval_question": ("승인", "검토", "대기", "제안", "반영", "후보"),
    "voice_question": ("음성", "목소리", "말할", "말해", "Fish", "마이크"),
    "brief_request": ("브리프", "요약", "아침", "저녁", "보고"),
    "correction": ("아니", "수정", "다시", "바꿔", "그게"),
    "open_chat": ("말", "대화", "하기", "물어"),
    "unknown": (),
}

def _act_cues() -> dict[str, tuple[str, ...]]:
    return _ACT_CUES_EN if _english_only() else _ACT_CUES_KO
