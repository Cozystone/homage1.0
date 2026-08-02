from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal


ConversationRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ConversationContextTurn:
    role: ConversationRole
    text: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ConversationContextPacket:
    current_question: str
    contextual_query: str
    turns: tuple[ConversationContextTurn, ...]
    followup_detected: bool
    focus_terms: tuple[str, ...]
    focus_source: str
    resolution_strategy: str
    used_for_learning: bool
    local_brain_write: bool
    production_store_mutated: bool
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "turns": [turn.to_dict() for turn in self.turns],
        }


_SECRET_RE = re.compile(
    r"(api[_ -]?key|secret|password|token|sk-[a-zA-Z0-9_-]{12,}|bearer\s+[a-zA-Z0-9._-]{12,})",
    re.IGNORECASE,
)

_FOLLOWUP_RE = re.compile(
    r"(^|\s)(그|그거|그건|그게|그걸|그 법칙|그 원리|이거|이건|저거|그것|이것|"
    r"that|it|this|those|they|them)\b|"
    r"(왜\s+그래|왜\s+그런|더\s+자세|이어\s*서|계속|좀\s+더|예시|"
    r"why\s+does|why\s+is|how\s+does|tell\s+me\s+more|more\s+detail|continue)",
    re.IGNORECASE,
)

# A turn that RETRACTS a prior assertion (Magnum A6 correction, 2026-07-19). The retracted turn
# carries the FALSE claim, so it must be dropped from the compacted query, not folded in.
_CORRECTION_RE = re.compile(
    r"\b(no,|no\s+that|that'?s\s+wrong|that\s+is\s+wrong|forget\s+(?:that|it)|i\s+was\s+wrong|"
    r"you'?re\s+wrong|scratch\s+that|not\s+right|actually,?\s+no|that'?s\s+(?:not\s+right|incorrect)|"
    r"incorrect)\b",
    re.IGNORECASE,
)
# An explicit RETURN-TO-TOPIC cue after a distractor (Magnum A6 persistence, 2026-07-19). The
# pronoun must resolve to the ESTABLISHED subject, not the intervening distractor turn.
_RETURN_RE = re.compile(
    r"\b(going\s+back|back\s+to|getting\s+back|returning\s+to|as\s+i\s+was\s+saying|anyway,?\s)",
    re.IGNORECASE,
)


def _strip_correction(text: str) -> str:
    cleaned = _CORRECTION_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .!?,-—–")
    return cleaned or text


def _first_user_text(turns: "tuple[ConversationContextTurn, ...]") -> str:
    for turn in turns:
        if turn.role == "user":
            return turn.text
    return ""

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "what",
    "why",
    "how",
    "does",
    "about",
    "explain",
    "tell",
    "more",
    "detail",
    "please",
    "이",
    "그",
    "저",
    "것",
    "거",
    "좀",
    "더",
    "왜",
    "어떻게",
    "뭐",
    "무엇",
    "대해",
    "대한",
    "관해",
    "관한",
    "설명",
    "해줘",
    "해주세요",
    "알려줘",
}


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    if _SECRET_RE.search(text):
        return ""
    return text[:limit]


def _tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'-]*|[가-힣A-Za-z0-9]{2,}", value)


def _term_root(token: str) -> str:
    if re.search(r"[가-힣]", token):
        return re.sub(r"(은|는|이|가|을|를|에|에서|으로|에게|처럼|하고|의|도|만|해줘|해주세요)$", "", token)
    return token.lower()


def _extract_focus_terms(turns: tuple[ConversationContextTurn, ...], *, limit: int = 8) -> tuple[str, ...]:
    terms: list[str] = []
    for turn in reversed(turns):
        if turn.role != "user":
            continue
        for token in _tokens(turn.text):
            root = _term_root(token)
            if len(root) < 2 or root.lower() in _STOPWORDS:
                continue
            if root not in terms:
                terms.append(root)
        if terms:
            break
    return tuple(terms[:limit])


def _last_user_text(turns: tuple[ConversationContextTurn, ...]) -> str:
    for turn in reversed(turns):
        if turn.role == "user":
            return turn.text
    return ""


def _topic_phrase(text: str) -> str:
    topic = re.sub(r"\s+", " ", text).strip(" .!?。！？")
    topic = re.sub(
        r"^(explain|tell me about|what is|what are|describe|define)\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(
        r"\s*(에\s*대해|에\s*대한|에\s*관해|에\s*관한)?\s*"
        r"(설명해줘|설명해 주세요|알려줘|알려 주세요|말해줘|말해 주세요|설명|정의해줘|정의)\s*$",
        "",
        topic,
    )
    return topic.strip(" .!?。！？") or text.strip(" .!?。！？")


def _followup_phrase(text: str) -> str:
    followup = re.sub(r"\s+", " ", text).strip(" .!?。！？")
    followup = re.sub(
        r"^(그건|그게|그거는|그거|그것은|그것|이건|이게|이거는|이거|저건|저게|저거는|저거)\s*",
        "",
        followup,
    )
    followup = re.sub(r"^(that|it|this|those|they|them)\s+", "", followup, flags=re.IGNORECASE)
    return followup.strip(" .!?。！？") or text.strip(" .!?。！？")


# function words that do NOT count as a self-contained subject — if a short question has any token
# beyond these, it names its own topic and must not be treated as a follow-up (2026-07-19).
_FUNCTION = _STOPWORDS | {"is", "are", "was", "were", "be", "my", "your", "do", "did", "a", "an",
                          "of", "on", "in", "at", "i", "me", "to", "s", "name", "which", "who",
                          "where", "when"}


def _is_followup(current: str, turns: tuple[ConversationContextTurn, ...]) -> bool:
    if not turns:
        return False
    text = current.strip()
    if not text:
        return False
    if _FOLLOWUP_RE.search(text):
        return True
    # A SHORT question is a follow-up ONLY if it is an anaphoric fragment — it carries no content noun
    # of its own. "What is my job?" / "What is gravity?" name their own subject and are self-contained,
    # so they must NOT borrow (and get glued to) the previous turn's topic. This false-follow-up glue
    # was making a distractor turn hijack the answer ("What is my job?" -> answered about a preceding
    # "Name a primary color."). Only bare fragments ("why?", "more detail?") fall through.
    if any(t.lower() not in _FUNCTION and len(t) > 1 for t in _tokens(text)):
        return False
    token_count = len(_tokens(text))
    return token_count <= 4 and any(mark in text for mark in ("?", "？", "요", "까"))


def _build_contextual_query(current: str, turns: tuple[ConversationContextTurn, ...]) -> tuple[str, bool, tuple[str, ...], str, str]:
    focus_terms = _extract_focus_terms(turns)
    followup = _is_followup(current, turns)
    if not turns:
        return current, False, (), "none", "current_question_only"

    # CORRECTION first (before followup compaction): the current turn retracts a prior claim, which
    # would otherwise be folded into the query (and echoed). Drop it — the correction turn names the
    # subject itself, so answer the cleaned question alone.
    if _CORRECTION_RE.search(current):
        cleaned = _strip_correction(current)
        return cleaned[:900], False, focus_terms, "correction", "retracted_prior_dropped"

    previous_user = _last_user_text(turns)

    # RETURN-TO-TOPIC after a distractor: resolve the pronoun to the FIRST established subject, not
    # the intervening distractor turn.
    if followup and _RETURN_RE.search(current):
        first_user = _first_user_text(turns)
        if first_user and first_user != previous_user:
            query = f"{_topic_phrase(first_user)} {_followup_phrase(current)}".strip()
            return query[:900], True, focus_terms, "first_user_turn", "return_to_established_topic"

    if followup and previous_user:
        query = f"{_topic_phrase(previous_user)} {_followup_phrase(current)}".strip()
        return query[:900], True, focus_terms, "latest_user_turn", "anaphora_resolved_to_latest_user_topic"

    recent_user_turns = [turn.text for turn in turns if turn.role == "user"][-2:]
    if recent_user_turns:
        query = " ".join([*recent_user_turns, current]).strip()
        return query[:1100], False, focus_terms, "recent_user_turns", "recent_user_context_compacted"

    return current, False, focus_terms, "none", "current_question_only"


def _coerce_role(value: Any) -> ConversationRole | None:
    role = str(value or "").strip().lower()
    if role in {"user", "human"}:
        return "user"
    if role in {"assistant", "atanor", "ai"}:
        return "assistant"
    return None


def sanitize_conversation_context(raw_turns: Any, *, max_turns: int = 6) -> tuple[ConversationContextTurn, ...]:
    if not isinstance(raw_turns, list):
        return ()
    turns: list[ConversationContextTurn] = []
    for raw in raw_turns[-max_turns:]:
        if not isinstance(raw, dict):
            continue
        role = _coerce_role(raw.get("role"))
        text = _clean_text(raw.get("text") or raw.get("content") or raw.get("message"))
        if role is None or not text:
            continue
        if turns and turns[-1].role == role and turns[-1].text == text:
            continue
        turns.append(ConversationContextTurn(role=role, text=text))
    return tuple(turns)


def build_conversation_context(current_question: str, raw_turns: Any) -> ConversationContextPacket:
    current = _clean_text(current_question, limit=320)
    turns = sanitize_conversation_context(raw_turns)
    contextual_query, followup, focus_terms, focus_source, resolution_strategy = _build_contextual_query(current, turns)
    return ConversationContextPacket(
        current_question=current,
        contextual_query=contextual_query,
        turns=turns,
        followup_detected=followup,
        focus_terms=focus_terms,
        focus_source=focus_source,
        resolution_strategy=resolution_strategy,
        used_for_learning=False,
        local_brain_write=False,
        production_store_mutated=False,
        basis="volatile_request_context_only_no_memory_write",
    )
