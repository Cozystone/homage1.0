# -*- coding: utf-8 -*-
"""Search orchestration — the retrieval loop big-LLM RAG stacks use, done No-LLM.

Owner (2026-07-09): "tavily → → 
 ." A single blind search of the raw user question is why answers read
like pasted snippets: one query, one page, one paste. This module runs the agentic-RAG
loop (query rewriting → multi-query retrieval → corrective re-search / CRAG) but the
query GENERATION is morphology + intent, not an LLM:

 1) derive_queries — rewrite the question into 1-3 FOCUSED search strings: keep the
 base, add an attribute-focused query for quantity/attribute questions
 (" " → " "), and split comparisons
 ("A B " → A, B) so each retrieval targets one thing well.
 2) orchestrate — run every derived query, MERGE + dedupe results, compose an
 answer; if the composition is thin/None (coverage gap), do ONE corrective
 re-search on a refined query (entity + expected type) before giving up.

Everything downstream of this (relevance gate, referent resonance, grounded synthesis)
is unchanged — this only makes the RETRIEVAL smarter, so the composer has better
material to weave. No LLM, no fabrication.
"""
from __future__ import annotations

import re
from typing import Any, Callable

# Question-cue → Korean attribute search terms. This is discourse/search heuristics
# (LAD-level: how to phrase a lookup), NOT world knowledge — it never asserts a fact,
# it only helps FIND the page that has it.
_ATTR_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"몇\s*잔|하루.*마셔|하루.*괜찮|일일|하루\s*권장", ("하루 권장 섭취량", "일일 적정량")),
    (r"얼마나|얼마|거리|길이|높이|무게|크기", ("정확한 수치", "기준 값")),
    (r"며칠|얼마나 걸|기간|시간이", ("소요 기간", "걸리는 시간")),
    (r"몇\s*개|개수|수량", ("개수",)),
    (r"부작용|안 좋|해로|위험", ("부작용", "주의사항")),
    (r"효능|효과|좋은|장점", ("효능", "효과")),
    (r"방법|어떻게|하는 법|하려면", ("방법", "단계별 가이드")),
    (r"왜\b|이유|원인|어째서", ("이유", "원인")),
    (r"추천|골라|고르|어떤 게 좋", ("추천", "비교")),
)


def _clean(q: str) -> str:
    q = re.sub(r"\s+", " ", str(q or "")).strip()
    # drop trailing conversational tails that hurt search recall
    q = re.sub(r"(알려줘|말해줘|설명해줘|궁금해|좀|요)\s*[?.!]*$", "", q).strip()
    return q.rstrip("?!. ")


_STOP = {"하루", "정말", "요즘", "그냥", "진짜", "너무", "매우", "제일", "가장", "무슨",
         "어떤", "얼마", "몇", "언제", "어디", "누구", "무엇", "뭐", "왜", "어떻게"}


def _anchor(question: str) -> str:
    """The topic to hang an attribute query on. Prefer the resolved subject entity;
    else the first contentful noun of the question (particle-stripped, non-stopword)."""
    try:
        from packages.cgsr.cgsr.referent_resonance import query_subject_entity
        ent = str(query_subject_entity(question) or "").strip()
        # accept only a real short entity — reject when it's the whole question echoed
        # back (multi-word, or carrying a question/attribute cue).
        cue = re.search(r"몇|얼마|언제|어디|누구|무엇|어떻게|왜|괜찮|좋을까|배워|하는|까지", ent)
        if 2 <= len(ent) <= 12 and ent.count(" ") <= 1 and ent not in _STOP and not cue:
            return ent
    except Exception:
        pass
    for tok in re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9]{1,15}", question):
        t = re.sub(r"(은|는|이|가|을|를|랑|이랑|와|과|에서|에게|한테|으로|로|의|도|만|까지|부터)$", "", tok)
        # skip verb/adverb/connective forms — they aren't a searchable topic noun
        if re.search(r"(하면|하는|되면|해야|어야|을까|ㄹ까|으면|아서|어서|에게|처럼)$", t):
            continue
        if t.endswith(("면", "서", "고", "며", "게", "지", "데", "때", "가", "도")):
            continue
        if len(t) >= 2 and t not in _STOP:
            return t
    return ""


def _split_comparison(question: str) -> list[str]:
    """"A///vs B /" → [A, B]. Each side searched on its own retrieves a
 real definitional page instead of a thin 'A vs B' listicle."""
    m = re.search(r"([가-힣A-Za-z0-9]{2,20}?)\s*(?:이랑|랑|와|과|,|vs\.?|對|대)\s*"
                  r"([가-힣A-Za-z0-9]{2,20}?)\s*(?:중에?|가운데)?\s*(?:차이|비교|다른|뭐가|뭐부터|뭐를)", question)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        if a and b and a != b:
            return [a, b]
    return []


def derive_queries(question: str, language: str = "ko", *, max_queries: int = 3) -> list[str]:
    """Rewrite the user question into up to `max_queries` focused search strings."""
    base = _clean(question)
    if not base:
        return []
    out: list[str] = []
    # English-core: for "PROPERTY of ENTITY" (capital of South Korea), search the ENTITY (+property)
    # FIRST — the raw phrase retrieves the property's own page ("Capital punishment"), the wrong
    # referent. The peeled subject targets the entity's page where the property value lives.
    try:
        from packages.cgsr.cgsr.referent_resonance import query_subject_entity
        subj = query_subject_entity(question)
        m = re.match(r"^(?:the\s+)?([A-Za-z][A-Za-z ]*?)\s+of\s+.+$", base.strip(), re.I)
        prop = m.group(1).strip() if m else ""
        if subj and subj.lower() != base.lower() and len(subj) >= 2:
            if prop and prop.lower() not in subj.lower():
                out.append(f"{subj} {prop}".strip())        # entity + attribute → answer sentence
            out.append(subj)                                 # entity page (fallback)
    except Exception:
        pass
    if base not in out:
        out.append(base)
    anchor = _anchor(question)

    # attribute-focused query: entity + the attribute the question is really asking for.
    # Only when we have a real topic noun — appending an attribute to the whole question

    if len(anchor) >= 2:
        for pat, terms in _ATTR_CUES:
            if re.search(pat, question):
                for t in terms[:1]:
                    cand = f"{anchor} {t}".strip()
                    if cand and cand not in out:
                        out.append(cand)
                break

    # comparison decomposition: search each side separately
    for side in _split_comparison(question):
        if side not in out:
            out.append(side)

    return out[:max_queries]


def orchestrate(
    question: str,
    *,
    language: str = "ko",
    search_fn: Callable[[str, int], list[dict[str, Any]]] | None = None,
    compose_fn: Callable[..., dict[str, Any] | None] | None = None,
    top_k: int = 6,
    deep: bool = False,
) -> dict[str, Any] | None:
    """Multi-query retrieval + corrective re-search, then compose. Returns the composed
    answer dict (with `queries_used`/`rounds` added) or None on an honest miss."""
    if search_fn is None or compose_fn is None:
        from .web_search import compose_web_answer
        search_fn = search_fn or _default_search
        compose_fn = compose_fn or compose_web_answer

    queries = derive_queries(question, language, max_queries=3 if deep else 2)
    if not queries:
        return None

    def _gather(qs: list[str]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in qs:
            for row in (search_fn(q, top_k) or []):
                key = str(row.get("url") or row.get("title") or "")[:200]
                if key and key in seen:
                    continue
                seen.add(key)
                merged.append(row)
        return merged

    rows = _gather(queries)
    used = list(queries)
    composed = _compose(compose_fn, question, rows, language) if rows else None

    # CORRECTIVE re-search (CRAG): the first pass didn't cover the question. Refine once
    # on entity + expected answer type, then re-compose against the widened evidence.
    if not composed:
        try:
            from packages.cgsr.cgsr.referent_resonance import query_expected_type
            ent = _entity(question)
            exp = str(query_expected_type(question) or "").strip()
            refine = " ".join(t for t in (ent, exp, "설명") if t) or _clean(question)
        except Exception:
            refine = _clean(question) + " 정의"
        if refine and refine not in used:
            more = search_fn(refine, top_k) or []
            if more:
                rows = _dedupe(rows + more)
                used.append(refine)
                composed = _compose(compose_fn, question, rows, language)

    if not composed:
        return None
    composed["queries_used"] = used
    composed["rounds"] = 2 if len(used) > len(queries) else 1
    return composed


def _compose(compose_fn: Callable[..., dict[str, Any] | None], question: str,
             rows: list[dict[str, Any]], language: str) -> dict[str, Any] | None:
    """Compose an answer. First try the definitional composer (great for 'what is X');
 if it abstains (open/multi-aspect question), fall to the open-question composer that
 gathers topically-relevant facts and WEAVES them (+) instead of demanding one
 sentence carry the whole query."""
    try:
        got = compose_fn(question, rows, language=language, allow_partial=True)
    except TypeError:
        got = compose_fn(question, rows, language=language)
    if got and str(got.get("answer") or "").strip():
        return got
    return compose_open_answer(question, rows, language=language)


_Q_WORDS = {"무엇", "뭐", "뭐야", "왜", "어떻게", "어때", "언제", "어디", "누구", "얼마",
            "얼마나", "몇", "어떤", "무슨", "괜찮아", "괜찮", "좋을까", "좋아", "해야",
            "하나", "가능", "될까", "있어", "있나", "인가", "일까", "까지", "부터", "정도"}


def _content_terms(question: str) -> list[str]:
    """The query's real content nouns — question/function words stripped — used to score
 sentence relevance for an open question (where the answer never echoes ' ')."""
    from .web_search import _lookup_terms, _normalize_lookup_query
    terms: list[str] = []
    for t in _lookup_terms(_normalize_lookup_query(question)):
        s = re.sub(r"(은|는|이|가|을|를|랑|와|과|에서|에게|한테|으로|로|의|도|만|까지|부터)$", "", t)
        if len(s) >= 2 and s not in _Q_WORDS and not re.search(r"(아|어|까|나|니|게|자)$", s):
            terms.append(s)
    return terms


def _defish(s: str) -> bool:
    """A definitional sentence — kept as the answer's anchor even on an anchor-only match."""
    return bool(re.search(r"(이다|입니다|말한다|뜻한다|일종|음료)\s*\.?$", str(s).strip()))


def compose_open_answer(question: str, rows: list[dict[str, Any]], *,
                        language: str = "ko", max_facts: int = 4) -> dict[str, Any] | None:
    """Open-question composition: gather clean sentences that are ON-TOPIC (mention the
    anchor or share a content term), pick the most informative non-redundant few, and
    WEAVE them with the grounded-constrained generator so the answer flows. Every fact
    stays verbatim (hallucination-safe). Returns {answer, sources, ...} or None."""
    from .web_search import _clean_web_snippet, _is_fluff_sentence, _split_sentences
    anchor = _anchor(question).lower()
    terms = _content_terms(question)
    if not anchor and not terms:
        return None

    def _bigrams(s: str) -> set[str]:
        t = re.sub(r"[^가-힣a-z0-9]", "", s.lower())
        return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}

    scored: list[tuple[float, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in rows[:10]:
        for sent in _split_sentences(_clean_web_snippet(str(row.get("snippet") or ""))):
            if _is_fluff_sentence(sent) or not (18 <= len(sent) <= 300):
                continue
            norm = re.sub(r"\s+", "", sent)[:50]
            if norm in seen:
                continue
            low = sent.lower()
            hits = sum(1 for t in terms if t.lower() in low)
            has_anchor = bool(anchor and anchor in low)
            # an ANSWER-SIGNAL: a guideline/quantity clause is likely the actual answer to


            answer_sig = bool(re.search(r"(권장|섭취|한도|이하|이내|적정|제한|주의|부작용|효과"
                                        r"|해야|하는 것이 좋|\d\s*(mg|밀리그램|잔|시간|분|개|%))", sent))

            # on-topic — require the anchor WITH another query term, OR two terms, OR a
            # definitional anchor, OR an answer-signal sharing ≥1 term. Drops bio/list debris.
            on_topic = ((has_anchor and hits >= 1) or hits >= 2 or (has_anchor and _defish(sent))
                        or (answer_sig and (has_anchor or hits >= 1)))
            if not on_topic:
                continue  # relevance gate — never absorb an off-topic sentence
            if re.search(r"(출신|소속|취미|특기|데뷔|성우|배우|멤버|출연)", sent) and not answer_sig:
                continue  # biographical/list debris that slipped the term filter
            seen.add(norm)
            score = (1.0 if has_anchor else 0.0) + hits * 1.2 + (1.5 if answer_sig else 0.0)
            scored.append((score, sent, row))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])

    picked: list[tuple[str, dict[str, Any]]] = []
    chosen_bg: list[set[str]] = []
    for _, sent, row in scored:
        bg = _bigrams(sent)
        if any(len(bg & c) / max(1, len(bg)) > 0.55 for c in chosen_bg):
            continue
        picked.append((sent, row))
        chosen_bg.append(bg)
        if len(picked) >= max_facts:
            break
    # require the topic to actually appear somewhere, else abstain (stay on-referent)
    if anchor and not any(anchor in s.lower() for s, _ in picked):
        return None
    if len(picked) < 2:
        return None

    try:
        from packages.base_brain.grounded_generation import synthesize
        facts = [{"name": None, "description": s} for s, _ in picked]
        syn = synthesize(question, facts, language, min_facts=2, max_facts=max_facts)
        answer = str((syn or {}).get("answer") or "").strip()
    except Exception:
        answer = ""
    if not answer:
        answer = " ".join(s for s, _ in picked)
    sources = []
    for _, row in picked:
        title = str(row.get("title") or "").strip()
        if title and title not in sources:
            sources.append(title)
    return {"answer": answer, "sources": sources[:3], "follow_ups": [],
            "answer_kind": "grounded_synthesis"}


def _default_search(query: str, count: int) -> list[dict[str, Any]]:
    """Provider-robust retrieval: open web (DuckDuckGo) first for attribute/how-to
    queries, plus Wikipedia so a definitional anchor is always available. Whichever
    provider is reachable in this environment contributes — the composer filters."""
    from .web_search import general_web_search
    rows: list[dict[str, Any]] = []
    try:
        rows.extend(general_web_search(query, count) or [])
    except Exception:
        pass
    if len(rows) < 2:
        try:
            from .web_search import wikipedia_search
            rows.extend(wikipedia_search(query, count) or [])
        except Exception:
            pass
    return rows


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for row in rows:
        key = str(row.get("url") or row.get("title") or "")[:200]
        if key and key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
