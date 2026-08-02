"""Local deterministic evaluation helpers for CGSR benchmark outputs.

These checks do not judge factual correctness or final answer quality.  They
only catch obvious skeleton/realizer failures so benchmark "ok" counts do not
hide malformed Korean outputs.
"""

from __future__ import annotations

import re


INTRANSITIVE_PREDICATES = {
    "태어나다",
    "재직하다",
    "물러나다",
    "알려지다",
    "발생하다",
    "존재하다",
    "성립하다",
    "살다",
}


def predicate_stem(predicate: str) -> str:
    """Return a coarse Korean predicate stem for deterministic diagnostics."""

    value = (predicate or "").strip()
    for suffix in ("합니다", "한다", "하다", "합니다.", "한다.", "하다."):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value[:-1] if value.endswith("다") else value


def classify_minimal_generation(
    case: dict[str, str],
    output: str,
    *,
    retrieval_tier: str,
) -> tuple[str, str]:
    """Classify obvious CGSR minimal-generation failures.

    The classifier is intentionally conservative.  It focuses on defects that
    are visible without external knowledge or LLM judgment.
    """

    concept = (case.get("concept") or "").strip()
    obj = (case.get("object") or "").strip()
    predicate = (case.get("predicate") or "").strip()
    stem = predicate_stem(predicate)
    if re.fullmatch(r"\d+", concept) or concept.lower() in {"svg"}:
        return "c_lexicalization_realizer", "semantic skeleton extraction supplied a noisy subject"
    if retrieval_tier != "exact":
        return "b_matching", "construction retrieval did not find an exact predicate family"
    if re.fullmatch(r"\d+", obj) and f"{obj}세" not in output and f"{obj}년" not in output:
        return "c_lexicalization_realizer", "bare numeric object needs a unit or different case frame"
    if (obj == stem or stem.startswith(obj) or obj.startswith(stem)) and re.search(rf"{re.escape(obj)}(을|를)", output):
        return "c_lexicalization_realizer", "object and predicate stem duplicate"
    if predicate in INTRANSITIVE_PREDICATES and obj and not re.search(r"(에서|로|세까지) ", output):
        return "c_lexicalization_realizer", "intransitive predicate was realized with an object"
    if re.search(r"(을|를) (태어납니다|물러납니다|알려집니다|재직합니다|발생합니다|존재합니다|성립합니다)", output):
        return "c_lexicalization_realizer", "object marker used with intransitive/passive predicate"
    return "ok", "passes bounded deterministic grammar checks"
