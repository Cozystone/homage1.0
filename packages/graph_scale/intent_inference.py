# -*- coding: utf-8 -*-
"""Infer the TRUE subject and TRUE intent behind a question — not the surface tokens.

Owner (2026-07-09): " , ' ' '
' . ." The breakthrough is NOT a
bigger keyword→answer table; it is REASONING over structure that generalizes to sentences
we've never seen:

 1) ROLE-TYPE every content token. Closed GRAMMATICAL classes — quantity/where/when/why
 wh-words, counters (///kg), time words (/), evaluation stems (/) —
 are LAD (linguistic structure, allowed in code, NOT world knowledge). Everything else
 is typed by the GRAPH: a token that is a real concept (has an is_a, or lives in the
 trained phase space) is an ENTITY; a token that is nothing to the graph is noise.
 2) The TRUE SUBJECT is the ENTITY the modifiers orbit. Geometrically: among entity
 candidates, the one with the highest resonance-CENTRALITY in the phase space (it best
 "explains" the other concepts). Sparse geometry → fall back to topic-first position.
 3) The TRUE INTENT is COMPOSED from the role constellation, not matched from a phrase:
 entity + counter + time + ask_quantity (+ evaluation) ⇒ "safe/recommended amount";
 ask_where ⇒ location; two entities + / ⇒ compare; ask_who ⇒ identity; …

So " ?", " ?", " ?" all
infer (subject=the substance, intent=safe_quantity) from the SAME structural reasoning —
no per-sentence rule. The world-knowledge (=) comes from the graph; only the
grammatical role markers live in code, which is exactly where the LAD layer belongs.
"""
from __future__ import annotations

import re
from typing import Any

# ── LAD: closed grammatical classes (linguistic structure, not world knowledge) ──────
_WH = {
    "몇": "ask_quantity", "얼마": "ask_quantity", "얼마나": "ask_quantity",
    "어디": "ask_location", "어디서": "ask_location", "어디에": "ask_location",
    "언제": "ask_time", "왜": "ask_cause", "어째서": "ask_cause",
    "누구": "ask_identity", "누가": "ask_identity",
    "무엇": "ask_definition", "뭐": "ask_definition", "뭘": "ask_definition",
    "어떻게": "ask_method", "어떤": "ask_property",
}
# Korean counters / classifiers (bound measure nouns) — a closed class.
_UNIT = {"개", "명", "분", "잔", "병", "장", "권", "대", "마리", "알", "그루", "채", "척",
         "켤레", "송이", "인분", "스푼", "컵", "숟갈", "방울", "kg", "g", "mg", "밀리그램",
         "ml", "mL", "l", "리터", "cm", "m", "km", "원", "도", "층", "회", "번", "칼로리"}
# English counters / measure nouns — the same closed class, and just as ineligible to be the
# SUBJECT. Without these 'How many CUPS of coffee per day…' centred on 'cups', not 'coffee' —
# the measure-word form of the function-word-as-subject fault.
_UNIT |= {"cup", "cups", "glass", "glasses", "bottle", "bottles", "piece", "pieces", "slice",
          "slices", "spoon", "spoons", "teaspoon", "tablespoon", "serving", "servings",
          "portion", "portions", "item", "items", "gram", "grams", "kilogram", "kilograms",
          "pound", "pounds", "ounce", "ounces", "litre", "liter", "litres", "liters",
          "mile", "miles", "metre", "meter", "metres", "meters", "inch", "inches", "foot",
          "feet", "degree", "degrees", "percent", "calorie", "calories", "unit", "units"}
_TIME = {"하루", "이틀", "사흘", "오늘", "내일", "어제", "올해", "작년", "내년", "요즘",
         "시간", "분", "초", "주", "주일", "달", "개월", "년", "아침", "점심", "저녁", "밤", "새벽",
         # English time words are equally ineligible as the topic entity
         "day", "days", "week", "weeks", "month", "months", "year", "years", "hour", "hours",
         "minute", "minutes", "second", "seconds", "today", "tomorrow", "yesterday", "morning",
         "afternoon", "evening", "night", "tonight"}
_EVAL = ("괜찮", "좋", "나쁘", "적당", "안전", "위험", "해롭", "이롭", "낫", "나아", "충분",
         "부족", "맞", "옳", "그르")
_METHOD_MARK = ("방법", "법", "하는법", "하려면", "레시피", "만드는")
_COMPARE_MARK = ("차이", "비교", "다른", "낫", "나아", "뭐가", "vs", "대")
_FUNC = {"그", "저", "이", "것", "거", "수", "때", "중", "등", "및", "또", "좀", "정말",
         "너무", "매우", "그냥", "진짜", "제일", "가장", "까지", "부터", "정도", "관련"}
_EN_FUNC = {"tell", "me", "about", "the", "a", "an", "of", "on", "what", "who", "is",
            "are", "do", "does", "how", "why", "where", "when", "can", "could", "please",
            "give", "show", "explain", "and", "or", "to", "for", "in", "with", "i", "you",
            "regarding", "much", "many", "long"}
_EN_WH = {"what": "ask_definition", "who": "ask_identity", "where": "ask_location",
          "when": "ask_time", "why": "ask_cause", "how": "ask_method"}


_COPULA = re.compile(r"(이에요|예요|이야|이니|이냐|인가|인지|야|냐|니|임|다)$")
# UNAMBIGUOUS particles — always safe to strip.
_PARTICLE = re.compile(r"(으로부터|이라는|에서는|이랑|랑|까지|부터|마다|에게|한테|께서|은|는|을|를|의|란|이란|에서|에|으로|로|와|과|도|만)$")


_SUBJ_PARTICLE = re.compile(r"^(.+?)(이|가)$")


_ADJ_VERB = re.compile(r"(다|해|줘|워|셔|았|었|였|랐|겠|돼|냐|여|러|료|을까|나요|가요|어야|아야|이야|해요|어요)$")


def _strip(tok: str, store: Any = None) -> str:
    t = _PARTICLE.sub("", tok)


    m = _SUBJ_PARTICLE.match(t)
    if m and _graph_type(m.group(1), store) and not _graph_type(t, store):
        t = m.group(1)


    base = _COPULA.sub("", t)
    if base != t and (base in _WH or base in ("누구", "뭐", "무엇", "얼마", "어디", "언제")):
        return base
    return t


def _is_unit(t: str) -> bool:
    return t in _UNIT or bool(re.fullmatch(r"\d+(개|명|잔|병|알|kg|g|mg|ml|mL|cm|km|원|도|층|회|번)", t))


def _is_eval(t: str) -> bool:
    return any(t.startswith(e) for e in _EVAL)


def _graph_type(token: str, store: Any) -> str | None:
    """Type a token by the GRAPH: its is_a super-type mapped to a coarse class, or —
    if it's a concept at all (in the phase space) — a generic entity. None = the graph
    knows nothing (a closed-class or noise token)."""
    try:
        for _s, p, o in (store.facts_about(token, limit=8) or []) if store else []:
            if p == "is_a":
                o = str(o)
                if re.search(r"사람|인물|person|가수|배우|선수|작가|정치인", o, re.I):
                    return "person"
                if re.search(r"도시|장소|지역|국가|시\b|군\b|구\b|place|city|country|산|강", o, re.I):
                    return "place"
                if re.search(r"회사|기업|조직|단체|organization|company|팀", o, re.I):
                    return "org"
                return "entity"
    except Exception:
        pass
    try:
        from . import clean_space
        if clean_space.has(token):
            return "entity"
    except Exception:
        pass
    return None


def role_of(token: str, store: Any) -> str:
    """The semantic ROLE of a token: a grammatical role (LAD) or a graph-typed entity."""
    t = _strip(token, store)
    if not t:
        return "function"
    # WH BEFORE FUNCTION. A wh-word IS a function word grammatically, but it is the one that
    # carries the INTENT, so it must be mapped to its ask_* role before the function filter can
    # drop it. Measured 2026-07-18: every English wh-word ('where/when/why/how/what/who') sits in
    # _EN_FUNC, so this check ran too late and _EN_WH was dead code — the whole English wh lane
    # never fired and every English wh-question fell through to 'definition' ('Where is Paris?').
    if t in _WH:
        return _WH[t]
    if t.lower() in _EN_WH:
        return _EN_WH[t.lower()]
    if t in _FUNC or t.lower() in _EN_FUNC:
        return "function"
    if _is_unit(t):
        return "unit"
    if t in _TIME:
        return "time"
    if _is_eval(t):
        return "evaluation"
    gt = _graph_type(t, store)
    if gt:
        return gt
    # unknown content word with an adjective/verb tail → predicate, not a topic
    if _ADJ_VERB.search(t) and len(t) <= 4:
        return "predicate"
    return "entity?"        # unknown noun — a weak entity candidate


_ENTITY_ROLES = {"entity", "entity?", "person", "place", "org"}


def _centrality(cand: str, others: list[str]) -> float:
    """How well `cand` explains the other concepts — summed phase-space resonance. The
    subject is the semantic centre of mass. Returns -1 when the geometry can't see it."""
    try:
        from . import clean_space
        vals = [clean_space.resonance(cand, o) for o in others]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else -1.0
    except Exception:
        return -1.0


def infer(query: str, store: Any = None) -> dict[str, Any]:
    """Infer (true subject, true intent) from the role constellation. Returns a dict with
    a human-readable reasoning trace — the inference is explainable, not a black box."""
    raw = re.findall(r"[가-힣A-Za-z0-9]{1,}", str(query or ""))
    roles: list[tuple[str, str]] = []
    for tok in raw:
        r = role_of(tok, store)
        if r != "function":
            roles.append((_strip(tok, store), r))

    entities = [t for t, r in roles if r in _ENTITY_ROLES]
    others = [t for t, _r in roles]


    # topic, which the role classifier does. Use it as the strong prior; the role constellation
    # then only refines INTENT. If Kiwi says there is no subject, there is none (don't resurrect a
    # pronoun). Fall back to the role-based entity only when query_frame yields nothing (English,
    # or Kiwi down).
    qf_subject = ""
    try:
        import re as _re
        if _re.search(r"[가-힣]", str(query or "")):
            from .query_frame import parse as _qfp
            qf_subject = _qfp(query).subject or ""
            # empty from a Korean question with real entities = predicate/pronoun-only → keep empty
    except Exception:
        qf_subject = ""
    # SUBJECT: morpheme subject wins; else topic-first role prior. Phase-space resonance-centrality
    # only disambiguates among real in-geometry entities when morphology gave nothing.
    subject = qf_subject or (entities[0] if entities else "")
    # MEASURED AND REVERTED (2026-07-18): an English head-first genitive rule here ('population OF
    # Seoul' -> Seoul) fixed that one case but broke four others (quantity/wh-role/comparison
    # composition), because overriding the morpheme subject with the post-'of' noun is wrong
    # whenever the 'of' phrase is a measure or a complement. Net regression 1 -> 5 failures, so the
    # rule is NOT applied; 'population of X' picking the attribute stays a known, measured gap.
    if not qf_subject and len(entities) >= 2:
        try:
            from . import clean_space
            in_geo = [e for e in entities if clean_space.has(e)]
            if len(in_geo) >= 2:
                scored = [(e, _centrality(e, [o for o in others if o != e])) for e in in_geo]
                best = max(s for _e, s in scored)
                if best >= 0:
                    subject = next(e for e, s in scored if s == best)
        except Exception:
            pass

    rset = {r for _t, r in roles}
    has_unit = "unit" in rset
    has_time = "time" in rset
    has_eval = "evaluation" in rset
    q = str(query)


    # answered by is_a traversal, not a definition). Detect it structurally: TOPIC + COMP
    # + a copula-question ending. Capture the compared category so the executor can reason.
    verify_target = ""
    mv = re.search(r"([가-힣A-Za-z]{2,})(?:은|는|이|가)\s*([가-힣A-Za-z]{1,8}?)"
                   r"(?:이야|야|인가요|인가|맞아|맞나|맞지|맞니|니|냐)\s*\??\s*$", q)
    # ENGLISH verification is subject-auxiliary INVERSION, not a copula ending: 'Is a whale a
    # fish?' / 'Was Rome an empire?'. Without this the English lane read them as definitions and —
    # worse — took the auxiliary as the subject ('Was Rome an empire?' -> subject 'Was'), the
    # function-word-as-subject fault in its English form.
    mv_en = re.match(r"\s*(?:is|are|was|were)\s+(?:an?\s+|the\s+)?([A-Za-z][A-Za-z'\- ]{1,30}?)\s+"
                     r"(?:an?\s+|the\s+)?([A-Za-z][A-Za-z'\-]{1,20})\s*\??\s*$", q, re.IGNORECASE)

    # INTENT: composed from the constellation, most-specific first. VERIFICATION only when

    if mv and not any(r.startswith("ask_") for r in rset) and mv.group(2) not in _WH:
        intent = "verify"
        subject = mv.group(1)
        verify_target = mv.group(2)
    elif mv_en and not any(r.startswith("ask_") for r in rset):
        intent = "verify"
        subject = mv_en.group(1).strip()
        verify_target = mv_en.group(2).strip()
    elif "ask_quantity" in rset or has_unit:
        intent = "safe_quantity" if has_eval else "quantity"
    elif "ask_location" in rset:
        intent = "location"
    elif "ask_time" in rset:
        intent = "time"
    elif "ask_cause" in rset:
        intent = "cause"
    elif "ask_method" in rset or any(m in q for m in _METHOD_MARK):
        intent = "method"
    elif len(entities) >= 2 and any(m in q for m in _COMPARE_MARK):
        intent = "compare"
    elif "ask_identity" in rset:
        intent = "identity"
    elif has_eval and "ask_definition" not in rset:
        intent = "evaluate"
    elif "ask_definition" in rset or "ask_property" in rset:
        intent = "definition"
    else:
        intent = "definition"

    trace = (f"토큰 역할={roles}; 실체후보={entities}; 중심대상={subject!r} "
             f"(공명 중심성); 역할군={sorted(rset)} → 의도={intent}")
    return {
        "subject": subject,
        "intent": intent,
        "entities": entities,
        "roles": roles,
        "verify_target": verify_target,
        "compare_targets": entities[:2] if intent == "compare" else [],
        "trace": trace,
        "confidence": round(0.5 + 0.1 * len(entities) + (0.2 if subject else 0), 3),
    }
