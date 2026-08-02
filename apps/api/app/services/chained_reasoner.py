"""Deterministic chained (2-hop) reasoning — no LLM.

Beyond single comparisons, some questions need a *chain*: " ?"
= France → its capital (Paris) → Paris's population. This module resolves a
relation from one article (hop 1), then looks up an attribute of the resulting
entity (hop 2), citing both sources. v1 relation = /capital; the chained
attribute reuses the comparison reasoner's population/area extractors. Abstains
(returns None) whenever a hop can't be resolved — never guesses.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.comparison_reasoner import (
    _extract_area_km2,
    _extract_population,
    _josa,
    _lookup,
)


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().strip("?!.。")


# Relation hop-1 extractors: pull the related entity (e.g. the capital) from the
# base entity's article prose.
_CAPITAL_PATTERNS = (
    r"수도는\s*([가-힣A-Za-z][가-힣A-Za-z·]{1,12}?)(?:이다|입니다|이며|로|[,.\s(])",
    r"수도(?:이자|인)\s*(?:최대\s*도시인?\s*)?([가-힣A-Za-z][가-힣A-Za-z·]{1,12})",
    r"capital\s+(?:and\s+largest\s+city\s+)?(?:is|of\s+\w+\s+is)?\s*,?\s*([A-Z][A-Za-z·-]{2,20})",
)


def _extract_capital(text: str) -> str | None:
    for pat in _CAPITAL_PATTERNS:
        m = re.search(pat, str(text or ""))
        if m:
            cap = _strip(m.group(1)).rstrip("의는은이가")
            # reject obvious non-names that slipped through
            if cap and cap not in {"최대", "도시", "the", "a"} and len(cap) >= 2:
                return cap
    return None


_RELATIONS = {"capital": {"label_ko": "수도", "extract": _extract_capital}}
_CHAIN_ATTRS = {"인구": ("population", _extract_population), "면적": ("area_km2", _extract_area_km2)}


def detect_chain(question: str) -> dict[str, Any] | None:
    """Return {base, relation, attribute} for a 2-hop chain, or None.

 " ?" -> base=, relation=capital, attribute=population.
 " ?" -> base=, relation=capital, attribute=None.
 """
    q = _strip(question)

    m = re.search(r"^(.+?)(?:의)?\s*수도(?:\s*(?:의)?\s*(인구|면적|넓이))?\s*(?:는|가|은|이)?\s*(?:어디|얼마|뭐|무엇|몇)?", q)
    if m and m.group(1):
        base = _strip(m.group(1)).rstrip("의는은이가")
        if base and "수도" not in base:
            attr = m.group(2)
            attr = "면적" if attr == "넓이" else attr
            return {"base": base, "relation": "capital", "attribute": attr}
    # English: "population of the capital of France"
    m = re.search(r"capital\s+of\s+([A-Za-z][\w .'-]+)", q, re.IGNORECASE)
    if m:
        base = _strip(m.group(1))
        attr = "인구" if re.search(r"population", q, re.IGNORECASE) else "면적" if re.search(r"area", q, re.IGNORECASE) else None
        return {"base": base, "relation": "capital", "attribute": attr}
    return None


def answer_chain(question: str, language: str = "ko") -> dict[str, Any] | None:
    plan = detect_chain(question)
    if not plan:
        return None
    base_src = _lookup(plan["base"], language)
    if not base_src:
        return None
    related = _RELATIONS[plan["relation"]]["extract"](base_src["snippet"])
    if not related:
        return None  # hop 1 failed → abstain

    base_title = base_src["title"]
    rel_label = _RELATIONS[plan["relation"]]["label_ko"]
    is_ko = language == "ko"


    if not plan["attribute"]:
        if is_ko:
            answer = f"{base_title}의 {rel_label}는 {related}입니다. (출처: {base_title} 위키백과)"
        else:
            answer = f"The {plan['relation']} of {base_title} is {related}. (source: {base_title} Wikipedia)"
        steps = [
            {"type": "retrieve", "source": base_src["url"], "fact": f"{base_title}: {rel_label}={related}"},
        ]
        return _result(answer, steps, [base_src["url"]], related, base_src["url"], 0.8)


    attr_key, extractor = _CHAIN_ATTRS[plan["attribute"]]
    rel_src = _lookup(related, language)
    if not rel_src:
        return None
    value = extractor(rel_src["snippet"])
    if value is None:
        return None  # hop 2 failed → abstain

    if plan["attribute"] == "인구":
        val_str = f"약 {value:,.0f}명" if is_ko else f"about {value:,.0f} people"
    else:
        val_str = f"{value:,.0f}km²" if is_ko else f"{value:,.0f} km²"
    if is_ko:
        rel_eun = _josa(related, "은", "는")
        answer = (
            f"{base_title}의 {rel_label}는 {related}이고, {related}{rel_eun} {plan['attribute']}이 {val_str}입니다. "
            f"(출처: {base_title}, {related} 위키백과)"
        )
    else:
        answer = f"The capital of {base_title} is {related}, and {related}'s {attr_key} is {val_str}. (sources: {base_title}, {related} Wikipedia)"
    steps = [
        {"type": "retrieve", "source": base_src["url"], "fact": f"{base_title}: {rel_label}={related}"},
        {"type": "retrieve", "source": rel_src["url"], "fact": f"{related}: {attr_key}={value}"},
        {"type": "chain", "fact": f"{base_title} → {related} → {attr_key}"},
    ]
    return _result(answer, steps, [base_src["url"], rel_src["url"]], related, rel_src["url"], 0.78)


def _result(answer: str, steps: list, sources: list, anchor: str, source_url: str, conf: float) -> dict[str, Any]:
    return {
        "answer": answer,
        "reasoning_certificate": {
            "derivation_kind": "deterministic_chained_reasoning",
            "anchor_concept": {"id": anchor, "label": anchor, "match": "chain"},
            "steps": steps,
            "evidence_concepts": sources,
            "confidence": conf,
            "confidence_basis": "multi_source_chain",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "evidence_grounded": True, "multi_hop": True},
        },
        "confidence": conf,
        "sources": sources,
        "source_url": source_url,
        "source_title": anchor,
    }
