from __future__ import annotations

import re
from typing import Any, Sequence, TypeVar


T = TypeVar("T")

AWKWARD_KOREAN_FRAGMENTS: tuple[str, ...] = (
    "상태 대화 상태",
    "기억 경계 다음",
    "여기 듣고 있어",
    "대기 제안 반영",
    "먼저 의도와 경계를",
    "내부적으로 점검",
    "내적 독백",
    "숨겨진 사고",
    "출력이 차단된",
)

NATURAL_ENDINGS: tuple[str, ...] = ("어.", "요.", "다.", "해.", "게.", "야.", "죠.", "까?")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9가-힣]+", str(text or ""))


def detect_awkward_korean_markers(text: str) -> list[str]:
    """Return deterministic markers that make a Korean surface feel unnatural."""

    surface = re.sub(r"\s+", " ", str(text or "").strip())
    markers: list[str] = []
    for fragment in AWKWARD_KOREAN_FRAGMENTS:
        if fragment in surface:
            markers.append(f"awkward_fragment:{fragment}")

    tokens = _tokens(surface)
    repeated = {token for token in tokens if len(token) >= 2 and tokens.count(token) >= 2}
    for token in sorted(repeated):
        if token in {"상태", "기억", "후보", "대화", "경계", "요청"}:
            markers.append(f"repeated_noun:{token}")

    technical = {"generation_basis", "source_hash", "chain", "trace", "scratchpad"}
    if any(item.lower() in surface.lower() for item in technical):
        markers.append("technical_internal_wording")
    if len(tokens) > 24:
        markers.append("too_long_for_dashboard")
    if re.search(r"(한다|된다|있다)\s+(한다|된다|있다)", surface):
        markers.append("stacked_predicate")
    return markers


def score_korean_naturalness(text: str) -> float:
    """Score short user-facing Korean without calling any language model."""

    surface = re.sub(r"\s+", " ", str(text or "").strip())
    if not surface:
        return 0.0
    tokens = _tokens(surface)
    score = 0.62
    hangul_chars = len(re.findall(r"[가-힣]", surface))
    latin_chars = len(re.findall(r"[A-Za-z]", surface))
    if hangul_chars >= max(4, latin_chars):
        score += 0.12
    if 5 <= len(tokens) <= 18:
        score += 0.12
    elif len(tokens) <= 24:
        score += 0.04
    if surface.endswith(NATURAL_ENDINGS):
        score += 0.08
    if any(word in surface for word in ("승인", "후보", "검토")):
        score += 0.03
    if any(word in surface for word in ("텍스트", "음성", "선택")):
        score += 0.03
    score -= 0.08 * len(detect_awkward_korean_markers(surface))
    return round(max(0.0, min(1.0, score)), 4)


def repair_korean_surface_candidate(text: str, construction: Any | None = None, context: dict[str, Any] | None = None) -> str:
    """Repair a generated candidate at discourse level without prompt templates.

    Repairs are text-quality constraints over an already generated candidate:
    they do not map a user prompt to a fixed answer.
    """

    del construction, context
    surface = re.sub(r"\s+", " ", str(text or "").strip())
    replacements = {
        "상태 대화 상태": "현재 상태",
        "기억 경계 다음 대화 후보": "무엇을 기억할지와 다음 행동 후보",
        "자기 모델 루프는 기억 경계 다음 대화 후보를 함께 본다": "자기 모델 루프는 상태를 보고 필요한 제안을 고른다",
        "여기 듣고 있어": "여기서 듣고 있어",
        "대기 제안 반영 안전 잠금 후보 목록과 로컬 브레인 쓰기는 승인 검토 상태로": "승인이 필요한 제안은 검토 대기에 남겨야 해",
        "먼저 의도와 경계를 내부적으로 점검했습니다": "지금 바로 들었어",
        "내부적으로 점검했습니다": "확인했어",
        "기억해둘게": "기억 후보로 제안할 수 있어",
        "저장할게": "승인 후보로 남길 수 있어",
        "바로 반영할게": "승인 뒤에만 반영할 수 있어",
        "승격할게": "승격 후보로 남길 수 있어",
    }
    for before, after in replacements.items():
        surface = surface.replace(before, after)

    surface = re.sub(r"\b(상태)\s+\1\b", r"\1", surface)
    surface = re.sub(r"\b(기억)\s+\1\b", r"\1", surface)
    surface = re.sub(r"\b(후보)\s+\1\b", r"\1", surface)
    surface = re.sub(r"\s+([.!?])", r"\1", surface)
    surface = re.sub(r"\s+", " ", surface).strip()
    if surface and not surface.endswith((".", "?", "!")):
        surface = f"{surface}."
    return surface


def select_best_korean_candidate(candidates: Sequence[T]) -> T | None:
    """Select the best candidate with naturalness as a secondary criterion."""

    if not candidates:
        return None

    def key(candidate: T) -> tuple[float, float, str]:
        text = str(getattr(candidate, "text", ""))
        score = float(getattr(candidate, "score", 0.0))
        return (score + score_korean_naturalness(text) * 0.28, -len(detect_awkward_korean_markers(text)), text)

    return max(candidates, key=key)


AWKWARD_KOREAN_FRAGMENTS = (
    "여기서 듣고 있어 천천히 말해줘",
    "여기서 듣고 있어",
    "천천히 말해줘",
    "먼저 의도와 경계를",
    "내부적으로 점검",
    "chain of thought",
    "scratchpad",
    "진짜 의식",
    "실제 의식",
)

NATURAL_ENDINGS = ("어.", "요.", "줘.", "볼까?", "할까?", "좋아.", "응.", "반가워.")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9가-힣]+", str(text or ""))


def detect_awkward_korean_markers(text: str) -> list[str]:
    """Return deterministic markers that make a Korean surface feel unnatural."""

    surface = re.sub(r"\s+", " ", str(text or "").strip())
    markers: list[str] = []
    for fragment in AWKWARD_KOREAN_FRAGMENTS:
        if fragment in surface:
            markers.append(f"awkward_fragment:{fragment}")
    tokens = _tokens(surface)
    repeated = {token for token in tokens if len(token) >= 2 and tokens.count(token) >= 2}
    for token in sorted(repeated):
        if token in {"상태", "기억", "후보", "경계", "요청", "말해줘"}:
            markers.append(f"repeated_noun:{token}")
    technical = {"generation_basis", "source_hash", "trace", "scratchpad", "internal"}
    if any(item.lower() in surface.lower() for item in technical):
        markers.append("technical_internal_wording")
    if len(tokens) > 24:
        markers.append("too_long_for_dashboard")
    if "합니다 합니다" in surface or "습니다 습니다" in surface:
        markers.append("stacked_predicate")
    if surface.startswith("먼저 ") and "점검" in surface:
        markers.append("overly_instructional_greeting")
    return markers


def score_korean_naturalness(text: str) -> float:
    """Score short user-facing Korean without calling any language model."""

    surface = re.sub(r"\s+", " ", str(text or "").strip())
    if not surface:
        return 0.0
    tokens = _tokens(surface)
    score = 0.62
    hangul_chars = len(re.findall(r"[가-힣]", surface))
    latin_chars = len(re.findall(r"[A-Za-z]", surface))
    if hangul_chars >= max(4, latin_chars):
        score += 0.12
    if 2 <= len(tokens) <= 10:
        score += 0.16
    elif 11 <= len(tokens) <= 18:
        score += 0.1
    elif len(tokens) <= 24:
        score += 0.03
    if surface.endswith(NATURAL_ENDINGS):
        score += 0.08
    if any(word in surface for word in ("안녕", "반가워", "응", "좋아")):
        score += 0.04
    if any(word in surface for word in ("승인", "후보", "검토")):
        score += 0.02
    score -= 0.1 * len(detect_awkward_korean_markers(surface))
    return round(max(0.0, min(1.0, score)), 4)


def repair_korean_surface_candidate(text: str, construction: Any | None = None, context: dict[str, Any] | None = None) -> str:
    """Repair a generated candidate at discourse level without prompt templates."""

    del construction, context
    surface = re.sub(r"\s+", " ", str(text or "").strip())
    replacements = {
        "여기서 듣고 있어 천천히 말해줘": "안녕. 나 여기 있어.",
        "먼저 의도와 경계를 내부적으로 점검했습니다": "안녕. 편하게 말해줘.",
        "내부적으로 점검했습니다": "확인했어.",
        "안녕 편하게 말해줘 무엇부터 볼까": "안녕. 편하게 말해줘.",
        "안녕 나 여기 있어 편하게 말해줘 무엇부터 볼까": "안녕. 나 여기 있어.",
        "안녕 나 여기 있어 편하게 말해줘 무엇부터": "안녕. 나 여기 있어.",
        "안녕 편하게 말해줘 무엇부터": "안녕. 편하게 말해줘.",
        "좋아 지금 이야기해도 돼": "좋아. 지금 이야기해도 돼.",
    }
    for before, after in replacements.items():
        surface = surface.replace(before, after)
    surface = re.sub(r"\b(상태|기억|후보|경계)\s+\1\b", r"\1", surface)
    surface = re.sub(r"\s+([.!?])", r"\1", surface)
    surface = re.sub(r"\.{2,}", ".", surface)
    surface = re.sub(r"\s+", " ", surface).strip()
    if surface and not surface.endswith((".", "?", "!")):
        surface = f"{surface}."
    return surface
