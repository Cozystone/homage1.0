"""Minimal Korean morphology realizer for CGSR Stage 1."""

from __future__ import annotations

import re

from .models import RealizationInput
from .morphology import has_final_consonant

JONGSEONG_RIEUL = 8
JONGSEONG_BIEUP = 17


def _hangul_syllable_parts(char: str) -> tuple[int, int, int] | None:
    code = ord(char)
    if not 0xAC00 <= code <= 0xD7A3:
        return None
    offset = code - 0xAC00
    cho = offset // 588
    jung = (offset % 588) // 28
    jong = offset % 28
    return cho, jung, jong


def _compose_hangul(cho: int, jung: int, jong: int) -> str:
    return chr(0xAC00 + cho * 588 + jung * 28 + jong)


def _replace_final_consonant(word: str, jong: int) -> str:
    if not word:
        return word
    parts = _hangul_syllable_parts(word[-1])
    if parts is None:
        return word
    cho, jung, _ = parts
    return word[:-1] + _compose_hangul(cho, jung, jong)


def _drop_final_consonant(word: str) -> str:
    return _replace_final_consonant(word, 0)


def _has_final_rieul(word: str) -> bool:
    parts = _hangul_syllable_parts((word or " ")[-1])
    return bool(parts and parts[2] == JONGSEONG_RIEUL)


def attach_eomi(stem: str, formality: str = "formal") -> str:
    """Attach a small set of Korean endings to a verb/adjective stem.

    This remains a minimal morphology helper, not a content-generation rule
    system.  It only repairs common surface-form errors in deterministic
    realization.
    """

    normalized = (formality or "formal").casefold()
    if normalized in {"formal", "polite_formal"}:
        if stem.endswith("하"):
            return stem[:-1] + "합니다"
        if stem.endswith("이"):
            return stem + "ㅂ니다"
        if _has_final_rieul(stem):
            return _replace_final_consonant(stem, JONGSEONG_BIEUP) + "니다"
        if has_final_consonant(stem):
            return stem + "습니다"
        return _replace_final_consonant(stem, JONGSEONG_BIEUP) + "니다"
    if normalized in {"casual_polite", "polite"}:
        if stem.endswith("하"):
            return stem[:-1] + "해요"
        if stem.endswith("돕"):
            return stem[:-1] + "도와요"
        if stem.endswith("그렇"):
            return stem[:-2] + "그래요"
        if stem.endswith("듣"):
            return stem[:-1] + "들어요"
        if _has_final_rieul(stem):
            return _drop_final_consonant(stem) + "아요"
        return stem + ("어요" if has_final_consonant(stem) else "아요")
    if normalized == "plain":
        return stem + ("한다" if stem.endswith("하") else "다")
    raise ValueError(f"unsupported formality: {formality}")


def select_euro_ro(preceding_word: str) -> str:
    """/ allomorph — the exception a plain batchim rule misses.

 phonology: the instrumental/directional particle is '' after a vowel
 OR a (, , ), and '' after any other (, ).
 patterns with open syllables here, so a naive (with_batchim, without) split would
 wrongly emit ''. Pure morphology (LAD), not a content rule.
 """
    if not has_final_consonant(preceding_word) or _has_final_rieul(preceding_word):
        return "로"
    return "으로"


def select_josa(preceding_word: str, josa_pair: tuple[str, str]) -> str:
    """Select Korean josa by final consonant.

 ``josa_pair`` order is ``(with_final_consonant, without_final_consonant)``.
 Examples: ``("", "")``, ``("", "")``, ``("", "")``, ``("", "")``.
 The / pair is special-cased through :func:`select_euro_ro` because 
 behaves like an open syllable there (, not ).
 """

    if tuple(josa_pair) == ("으로", "로"):
        return select_euro_ro(preceding_word)
    return josa_pair[0] if has_final_consonant(preceding_word) else josa_pair[1]


def select_eomi(stem: str, formality: str = "formal") -> str:
    """Select a small Korean sentence ending.

    This Stage 1 function handles only a few common patterns.  Irregular
    conjugation is deliberately limited and reported as a known limitation.
    """

    normalized = (formality or "formal").casefold()
    if normalized in {"formal", "polite_formal"}:
        if stem.endswith("하"):
            return "합니다"
        if stem.endswith("이"):
            return "입니다"
        if _has_final_rieul(stem):
            return "ㅂ니다"
        return "습니다" if has_final_consonant(stem) else "ㅂ니다"
    if normalized in {"casual_polite", "polite"}:
        if stem.endswith("하"):
            return "해요"
        return "어요" if has_final_consonant(stem) else "아요"
    if normalized == "plain":
        if stem.endswith("하"):
            return "한다"
        return "다"
    raise ValueError(f"unsupported formality: {formality}")


def realize_simple_clause(payload: RealizationInput | dict[str, str]) -> str:
    """Realize a minimal Korean clause from concept/predicate/object slots."""

    if isinstance(payload, dict):
        item = RealizationInput(
            concept=payload["concept"],
            predicate=payload["predicate"],
            object=payload["object"],
            formality=payload.get("formality", "formal"),
        )
    else:
        item = payload
    topic = select_josa(item.concept, ("은", "는"))
    predicate = item.predicate
    predicate_lemma = predicate
    for suffix in ("한다", "하다"):
        if predicate_lemma.endswith(suffix):
            predicate_lemma = predicate_lemma[: -len(suffix)] + "하다"
            break
    subject = f"{item.concept}{topic}"
    object_phrase = ""
    if re.fullmatch(r"\d+", item.concept) and item.object in {"년", "월", "일"}:
        subject = f"{item.concept}{item.object}에는"
    elif re.fullmatch(r"\d+", item.object) and predicate_lemma == "살다":
        object_phrase = f"{item.object}세까지"
    elif re.fullmatch(r"\d{4}", item.object):
        object_phrase = f"{item.object}년에"
    elif predicate_lemma in {"태어나다", "재직하다"} and item.object:
        object_phrase = f"{item.object}에서"
    elif predicate_lemma == "물러나다" and item.object:
        object_phrase = f"{item.object}직에서" if item.object == "대통령" else f"{item.object}에서"
    elif predicate_lemma == "알려지다" and item.object:
        object_phrase = f"{item.object}{select_euro_ro(item.object)}"
    elif predicate_lemma == "대응하다" and item.object:
        object_phrase = "" if item.object == "대응" else f"{item.object}에"
    elif item.object:
        obj = select_josa(item.object, ("을", "를"))
        object_phrase = f"{item.object}{obj}"
    if predicate.endswith("한다"):
        predicate = predicate[:-2] + attach_eomi("하", item.formality)
    elif predicate.endswith("하다"):
        predicate = predicate[:-2] + attach_eomi("하", item.formality)
    elif predicate.endswith("준다"):
        predicate = attach_eomi(_drop_final_consonant(predicate[:-1]), item.formality)
    elif predicate.endswith("주다"):
        predicate = attach_eomi(predicate[:-1], item.formality)
    elif predicate.endswith("다"):
        predicate = attach_eomi(predicate[:-1], item.formality)
    if object_phrase:
        return f"{subject} {object_phrase} {predicate}."
    return f"{subject} {predicate}."
