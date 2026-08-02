"""LAD morphology layer — the ONE home for Korean surface-form rules.

Chronic class #5: / rules (/, /, /, /, particle tails) kept being
re-implemented per module (answer_bridge, pack_loader, neighborhood, realizers), each copy a
fresh chance for the same bug. This module is the canonical implementation; new code imports
from here, existing modules delegate.

Scope discipline: this is the LAD/surface layer — HOW Korean attaches particles. It never
holds world knowledge (hard rule: knowledge goes to the graph, not code)."""
from __future__ import annotations

__all__ = [
    "has_batchim", "topic", "subject", "object_", "eu_ro", "JOSA_TAILS", "strip_josa",
]


def has_batchim(label: str) -> bool:
    """True if the last Hangul syllable has a final consonant ()."""
    chars = [c for c in label if "가" <= c <= "힣"]
    if not chars:
        return False
    return (ord(chars[-1]) - 0xAC00) % 28 != 0


def topic(label: str) -> str:
    """label + / (topic marker)."""
    return f"{label}{'은' if has_batchim(label) else '는'}"


def subject(label: str) -> str:
    """label + / (subject marker)."""
    return f"{label}{'이' if has_batchim(label) else '가'}"


def object_(label: str) -> str:
    """label + / (object marker)."""
    return f"{label}{'을' if has_batchim(label) else '를'}"


def eu_ro(label: str) -> str:
    """label + / (directional/instrumental). -final takes (), other 
 take (... no wait →? has → ), open syllable takes ."""
    chars = [c for c in label if "가" <= c <= "힣"]
    if not chars:
        return f"{label}로"
    code = (ord(chars[-1]) - 0xAC00) % 28
    if code == 0 or code == 8:
        return f"{label}로"
    return f"{label}으로"


# Particle/ending tails that may follow a noun (used by boundary matching and tail
# stripping). Bounded closed-class list — morphology, not knowledge.
JOSA_TAILS = frozenset({
    "이", "가", "은", "는", "을", "를", "의", "에", "에서", "에게", "으로", "로", "와", "과",
    "도", "만", "이나", "나", "부터", "까지", "처럼", "보다", "란", "이란", "라는", "이라는",
    "요", "이요", "야", "이야", "인가", "인가요", "일까", "일까요", "입니다", "이에요", "예요",
})

_STRIP_ORDER = sorted(JOSA_TAILS, key=len, reverse=True)


def strip_josa(token: str) -> str:
    """Remove ONE trailing particle if present (longest first): -> ."""
    for tail in _STRIP_ORDER:
        if token.endswith(tail) and len(token) > len(tail) + 1:
            return token[: -len(tail)]
    return token
