"""Deterministic multi-hop comparison reasoning — no LLM.

A first step beyond single-fact grounding: questions like " 
 ?" require retrieve(A) → retrieve(B) → compare. This module
detects such comparisons, pulls each entity's public summary (Wikipedia), extracts
a comparable number, and decides deterministically — citing both sources. If it
cannot extract a comparable value for both, it returns None (abstains), never a
guess.

v1 supports YEAR-based comparisons (born first / older / younger / /
), which have the cleanest extraction. The attribute table is extensible.
"""

from __future__ import annotations

import re
from typing import Any

from urllib.parse import quote

from app.services.web_search import wikipedia_search, _wiki_get_json

# Separators between the two compared entities.
_SEP = r"(?:\s*(?:와|과|랑|이랑|하고|,|vs\.?|對|대)\s*|\s+or\s+|\s+vs\.?\s+)"

# Comparison cue → (attribute, direction). direction "min" = the smaller number
# wins the superlative ("born first" → smaller year); "max" = larger wins.
_YEAR_MIN = ("birth_year", "min")   # older / born first
_YEAR_MAX = ("birth_year", "max")   # younger / born later
_HEIGHT_MAX = ("height_m", "max")   # taller / higher (more metres)
_HEIGHT_MIN = ("height_m", "min")   # lower / shorter
_COMPARISON_CUES: tuple[tuple[str, tuple[str, str]], ...] = (
    (r"먼저\s*태어|나이\s*많|연상|더\s*나이|older|elder|born\s+first|born\s+earlier", _YEAR_MIN),
    (r"나중에\s*태어|나이\s*적|연하|더\s*어리|younger|born\s+later", _YEAR_MAX),


    (r"인구\s*(?:가\s*)?(?:더\s*)?많|더\s*많은\s*인구|larger\s+population|more\s+populous", ("population", "max")),
    (r"인구\s*(?:가\s*)?(?:더\s*)?적|fewer\s+people|smaller\s+population|less\s+populous", ("population", "min")),
    (r"면적\s*(?:이\s*)?(?:더\s*)?넓|더\s*넓|larger\s+area|bigger\s+area", ("area_km2", "max")),
    (r"면적\s*(?:이\s*)?(?:더\s*)?좁|더\s*좁|smaller\s+area", ("area_km2", "min")),
    (r"더\s*높|더\s*커|키\s*가?\s*(?:더\s*)?큰|taller|higher", _HEIGHT_MAX),
    (r"더\s*낮|더\s*작|shorter|lower", _HEIGHT_MIN),
)

# Which question-word range marks a comparison.
_COMPARE_QWORD = r"(누가|누구가|뭐가|무엇이|어느\s*것이|어느\s*게|which|who)"


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().strip("?!.。")


def _josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """Pick the right Korean particle by whether ``word`` ends in a final consonant."""
    word = str(word or "")
    if not word:
        return without_batchim
    last = word[-1]
    if "가" <= last <= "힣":
        return with_batchim if (ord(last) - 0xAC00) % 28 else without_batchim
    return without_batchim  # non-Hangul tail → default to the no-batchim form


def detect_comparison(question: str) -> dict[str, Any] | None:
    """Return {a, b, attribute, direction} for a two-entity comparison, or None."""
    q = _strip(question)
    cue = next((attr for pat, attr in _COMPARISON_CUES if re.search(pat, q, re.IGNORECASE)), None)
    if not cue:
        return None
    attribute, direction = cue

    ko = re.search(r"^(.*?)" + _SEP + r"(.+?)\s*중(?:에서|에)?\b", q)
    if ko:
        a, b = _strip(ko.group(1)), _strip(ko.group(2))
        if a and b and a.lower() != b.lower():
            return {"a": a, "b": b, "attribute": attribute, "direction": direction}
    # "which is older, A or B" / "is A or B older" (English) — entities after qword/or.
    en = re.search(r"(?:which|who)\b.*?[,:]?\s*([A-Za-z][\w .'-]+?)\s+or\s+([A-Za-z][\w .'-]+)$", q, re.IGNORECASE)
    if en:
        a, b = _strip(en.group(1)), _strip(en.group(2))
        if a and b and a.lower() != b.lower():
            return {"a": a, "b": b, "attribute": attribute, "direction": direction}
    return None


def _extract_birth_year(summary: str) -> int | None:
    """First plausible year in a bio lead is the birth year ("…(1879 3…", "…(14
 March 1879 –…")."""
    head = str(summary or "")[:240]


    years = [int(y) for y in re.findall(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)", head)]
    plausible = [y for y in years if 1000 <= y <= 2100]
    return plausible[0] if plausible else None


def _extract_height_m(summary: str) -> float | None:
    """Largest metre value in the summary ("8,848 m", "828m", " 555")."""
    head = str(summary or "")
    vals: list[float] = []
    for raw in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(?:m|미터|meters?|metres?)(?![A-Za-z])", head, re.IGNORECASE):
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        if 1 <= v <= 20000:  # mountains/buildings; excludes stray years (no "m" suffix anyway)
            vals.append(v)
    return max(vals) if vals else None


def _extract_population(summary: str) -> float | None:
    """Population near an /population mention, honoring Korean (1e4)/(1e8)."""
    for m in re.finditer(r"(?:인구|population)[^0-9]{0,15}(\d[\d,]*(?:\.\d+)?)\s*(억|만)?", str(summary or ""), re.IGNORECASE):
        try:
            num = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = m.group(2)
        num *= 1e8 if unit == "억" else 1e4 if unit == "만" else 1.0
        if 100 <= num <= 2e9:
            return num
    return None


def _ko_to_float(raw: str) -> float | None:
    """Parse a number that may use the Korean (1e4) myriad: "37 7,973" ->
 377973, "605.21" -> 605.21."""
    s = str(raw or "").replace(",", "").strip()
    m = re.match(r"(\d+(?:\.\d+)?)\s*만\s*(\d+)?$", s)
    if m:
        val = float(m.group(1)) * 1e4
        if m.group(2):
            val += float(m.group(2))
        return val
    try:
        return float(s)
    except ValueError:
        return None


def _extract_area_km2(summary: str) -> float | None:
    """Area in km² (" 605.21 km²", "37 7,973km²", "1,234 km2")."""
    vals: list[float] = []
    for raw in re.findall(r"((?:\d[\d,]*\s*만\s*)?\d[\d,]*(?:\.\d+)?)\s*(?:km²|km2|제곱\s*킬로미터|square\s+kilomet)", str(summary or ""), re.IGNORECASE):
        v = _ko_to_float(raw)
        if v is not None and 0.1 <= v <= 2e8:
            vals.append(v)
    return max(vals) if vals else None


_ATTRIBUTE_EXTRACTORS = {
    "birth_year": _extract_birth_year,
    "height_m": _extract_height_m,
    "population": _extract_population,
    "area_km2": _extract_area_km2,
}


def _rich_extract(title: str, language: str) -> str:
    """Bounded full-article plaintext (lead + early sections) where prose facts
 like / live — richer than the one-sentence search snippet."""
    host = "ko.wikipedia.org" if language == "ko" else "en.wikipedia.org"
    slug = quote(title.replace(" ", "_"), safe="")
    url = (
        f"https://{host}/w/api.php?action=query&prop=extracts&explaintext=1&exintro=0"
        f"&format=json&redirects=1&titles={slug}"
    )
    try:
        body = _wiki_get_json(url)
    except Exception:  # pragma: no cover - network
        return ""
    for page in ((body.get("query", {}) or {}).get("pages", {}) or {}).values():
        extract = str(page.get("extract") or "").strip()
        if extract:
            return extract[:2400]
    return ""


def _lookup(entity: str, language: str = "ko") -> dict[str, Any] | None:
    try:
        rows = wikipedia_search(entity, count=2)
    except Exception:  # pragma: no cover - network
        return None
    for row in rows or []:
        snippet = str(row.get("snippet") or "")
        if len(snippet) >= 30:
            title = str(row.get("title") or entity)
            # Prefer the richer article prose for attribute extraction; fall back
            # to the short snippet if the fetch yields nothing.
            text = _rich_extract(title, language) or snippet
            return {"title": title, "snippet": text, "url": str(row.get("url") or "")}
    return None


def answer_comparison(question: str, language: str = "ko") -> dict[str, Any] | None:
    """Answer a two-entity comparison from two real lookups, or None (abstain)."""
    plan = detect_comparison(question)
    if not plan:
        return None
    extractor = _ATTRIBUTE_EXTRACTORS.get(plan["attribute"])
    if not extractor:
        return None
    src_a, src_b = _lookup(plan["a"], language), _lookup(plan["b"], language)
    if not src_a or not src_b:
        return None
    val_a, val_b = extractor(src_a["snippet"]), extractor(src_b["snippet"])
    if val_a is None or val_b is None or val_a == val_b:
        return None  # can't compare → abstain, never guess

    winner_is_a = (val_a < val_b) if plan["direction"] == "min" else (val_a > val_b)
    win, lose = (src_a, src_b) if winner_is_a else (src_b, src_a)
    win_val, lose_val = (val_a, val_b) if winner_is_a else (val_b, val_a)
    is_ko = language == "ko"

    if plan["attribute"] == "birth_year":
        if is_ko:
            win_ga = _josa(win["title"], "이", "가")
            win_eun = _josa(win["title"], "은", "는")
            lose_eun = _josa(lose["title"], "은", "는")
            when_phrase = "먼저예요" if plan["direction"] == "min" else "나중이에요"
            answer = (
                f"{win['title']}{win_ga} 더 {when_phrase} {win['title']}{win_eun} {win_val}년생, "
                f"{lose['title']}{lose_eun} {lose_val}년생이에요. (출처: {win['title']}, {lose['title']} 위키백과)"
            )
        else:
            rel = "earlier" if plan["direction"] == "min" else "later"
            answer = f"{win['title']} was born {rel} ({win_val}) than {lose['title']} ({lose_val}). (sources: {win['title']}, {lose['title']} Wikipedia)"
    elif plan["attribute"] == "height_m":
        if is_ko:
            win_ga = _josa(win["title"], "이", "가")
            win_eun = _josa(win["title"], "은", "는")
            lose_eun = _josa(lose["title"], "은", "는")
            adj = "높아요" if plan["direction"] == "max" else "낮아요"
            answer = (
                f"{win['title']}{win_ga} 더 {adj} {win['title']}{win_eun} {win_val:g}m, "
                f"{lose['title']}{lose_eun} {lose_val:g}m예요. (출처: {win['title']}, {lose['title']} 위키백과)"
            )
        else:
            rel = "higher" if plan["direction"] == "max" else "lower"
            answer = f"{win['title']} is {rel} ({win_val:g} m) than {lose['title']} ({lose_val:g} m). (sources: {win['title']}, {lose['title']} Wikipedia)"
    elif plan["attribute"] in {"population", "area_km2"}:
        is_pop = plan["attribute"] == "population"
        if is_ko:
            win_ga = _josa(win["title"], "이", "가")
            win_eun = _josa(win["title"], "은", "는")
            lose_eun = _josa(lose["title"], "은", "는")
            if is_pop:
                adj = "인구가 더 많아요" if plan["direction"] == "max" else "인구가 더 적어요"
                answer = f"{win['title']}{win_ga} {adj} {win['title']}{win_eun} 약 {win_val:,.0f}명, {lose['title']}{lose_eun} 약 {lose_val:,.0f}명이에요. (출처: {win['title']}, {lose['title']} 위키백과)"
            else:
                adj = "면적이 더 넓어요" if plan["direction"] == "max" else "면적이 더 좁아요"
                answer = f"{win['title']}{win_ga} {adj} {win['title']}{win_eun} {win_val:,.0f}km², {lose['title']}{lose_eun} {lose_val:,.0f}km²예요. (출처: {win['title']}, {lose['title']} 위키백과)"
        else:
            unit = "people" if is_pop else "km²"
            rel = "more" if plan["direction"] == "max" else "fewer"
            answer = f"{win['title']} has {rel} ({win_val:,.0f} {unit}) than {lose['title']} ({lose_val:,.0f} {unit}). (sources: {win['title']}, {lose['title']} Wikipedia)"
    else:  # pragma: no cover - unknown attribute
        return None

    certificate = {
        "derivation_kind": "deterministic_comparison_reasoning",
        "anchor_concept": {"id": win["title"], "label": win["title"], "match": "comparison"},
        "steps": [
            {"type": "retrieve", "source": src_a["url"], "fact": f"{src_a['title']}: {plan['attribute']}={val_a}"},
            {"type": "retrieve", "source": src_b["url"], "fact": f"{src_b['title']}: {plan['attribute']}={val_b}"},
            {"type": "compare", "fact": f"{plan['attribute']} {plan['direction']} → {win['title']}"},
        ],
        "evidence_concepts": [src_a["url"], src_b["url"]],
        "confidence": 0.8,
        "confidence_basis": "two_source_deterministic_compare",
        "guarantees": {"external_llm": False, "fabricated_facts": False, "evidence_grounded": True, "multi_hop": True},
    }
    return {
        "answer": answer,
        "reasoning_certificate": certificate,
        "confidence": 0.8,
        "sources": [src_a["url"], src_b["url"]],
        "source_url": win["url"],
        "source_title": win["title"],
    }
