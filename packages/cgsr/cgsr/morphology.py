"""Korean morphology wrapper for CGSR Stage 1."""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from .models import Morpheme


def has_final_consonant(text: str) -> bool:
    """Return whether the last Hangul syllable has jongseong."""

    ascii_match = re.search(r"([A-Za-z0-9][A-Za-z0-9-]*)\s*$", text or "")
    if ascii_match:
        token = ascii_match.group(1).strip("-")
        if token:
            upper_final_with_batchim = {"F", "L", "M", "N", "R"}
            if token.isupper() and token[-1] in upper_final_with_batchim:
                return True
            if token.isupper():
                return False
            lowered = token.casefold()
            open_suffixes = ("s", "x", "t", "p", "k", "ch", "sh", "er", "or", "y", "w")
            if lowered.endswith(open_suffixes):
                return False
            return lowered[-1] not in {"a", "e", "i", "o", "u"}

    for char in reversed(text or ""):
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            return ((code - 0xAC00) % 28) != 0
        if char.isalnum():
            return char[-1:].lower() not in {"a", "e", "i", "o", "u"}
    return False


@lru_cache(maxsize=1)
def _kiwi() -> Any:
    """RETIRED (owner 2026-07-18, BINDING ' . Kiwi '): ATANOR is
 English-only; Korean input is refused at the I/O boundary, so this CGSR Korean-morphology lane
 never runs on a user turn. Always returns None — `analyze()` falls back to its regex path and the
 Korean construction/josa induction it fed is dead. Kept as a null seam so callers are untouched."""
    return None


def analyzer_status() -> dict[str, Any]:
    """Return installed analyzer metadata."""

    try:
        import kiwipiepy

        version = getattr(kiwipiepy, "__version__", "unknown")
    except Exception:
        version = None
    return {
        "analyzer": "kiwipiepy" if _kiwi() is not None else "fallback_regex",
        "kiwipiepy_version": version,
        "content_generation": False,
        "usage": "morphology_only",
    }


def analyze(sentence: str) -> list[Morpheme]:
    """Analyze a Korean sentence into morphemes.

    Kiwi is used only to expose morphology/POS signals for construction
    induction and josa/eomi realization.  It is not used to choose factual
    answer content.
    """

    kiwi = _kiwi()
    if kiwi is None:
        return _fallback_analyze(sentence)
    tokens = kiwi.tokenize(sentence)
    rows: list[Morpheme] = []
    for token in tokens:
        form = str(getattr(token, "form", ""))
        tag = str(getattr(token, "tag", "UNKNOWN"))
        start = int(getattr(token, "start", 0) or 0)
        length = int(getattr(token, "len", len(form)) or len(form))
        rows.append(Morpheme(form=form, tag=tag, start=start, length=length, has_final_consonant=has_final_consonant(form)))
    return rows


def lemmatize_predicate(text: str) -> str:
    """Return a deterministic Korean predicate lemma when morphology allows it.

    Kiwi is used only as a morphology tool.  This function does not choose
    answer content; it normalizes an already supplied predicate so CGSR can
    compare construction predicates without treating conjugation variants as
    different verbs.
    """

    value = str(text or "").strip()
    if not value:
        return ""
    if value.endswith("지다"):
        return value
    kiwi = _kiwi()
    if kiwi is None:
        return _fallback_predicate_lemma(value)

    tokens = list(kiwi.tokenize(value))
    for idx, token in enumerate(tokens):
        form = str(getattr(token, "form", ""))
        tag = str(getattr(token, "tag", ""))
        if tag in {"XSV", "XSA"} and idx > 0:
            previous = str(getattr(tokens[idx - 1], "form", ""))
            if previous:
                return previous + "하다"
        if tag.startswith(("VV", "VA")):
            if form == "보이" and any(str(getattr(row, "form", "")) == "주" and str(getattr(row, "tag", "")).startswith("VX") for row in tokens[idx + 1 :]):
                return "보여주다"
            return form + "다"
    return _fallback_predicate_lemma(value)


def _fallback_predicate_lemma(value: str) -> str:
    """Small fallback for environments without Kiwi."""

    for suffix in ("합니다", "한다", "하는", "함"):
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)] + "하다"
    return value


def _fallback_analyze(sentence: str) -> list[Morpheme]:
    parts = [part for part in sentence.replace(".", " .").replace(",", " ,").split() if part]
    return [
        Morpheme(
            form=part,
            tag="PUNCT" if part in {".", ","} else "TOKEN",
            start=0,
            length=len(part),
            has_final_consonant=has_final_consonant(part),
        )
        for part in parts
    ]
