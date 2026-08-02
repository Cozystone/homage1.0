# -*- coding: utf-8 -*-
"""Engagement cascade — structurally eliminate the DEAD-END abstention.

Owner directive (2026-07-09): when a user asks an AI expecting an answer and
gets a bare '', it's a letdown. Make that structurally impossible.

The distinction that keeps this honest (BINDING — see the honesty memory): we
never fabricate a fact to fill the gap. We eliminate the DEAD-END, not the
truthfulness. Every hard-miss is instead turned into a SUBSTANTIVE, forward-
moving engagement built only from what the graph really holds:

 1. nearest VERIFIED concept (soft_resolve) — 'no direct fact, but the closest
 verified concept in the graph is X (shared type …), and X is …';
 2. RELATED facts around the best subject — offer what we DO know near it;
 3. shape-aware conversational engagement for genuinely open questions;
 4. always a forward cue (it will verify on the live web / learn this) —
 never a shrug.

So the answer is honest (grounded=False, engaged=True, fabricated_facts=False)
but never a wall. This is the omni-engage law applied to the FACTUAL-miss path,
reusing the existing soft-context and shape-engage pieces rather than new ones."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable


_ADVERBS = re.compile(r"^(자세히|자세하게|정확히|간단히|쉽게|빨리|자세|간략히|대략)$")

# Pronouns / interjections / grammatical fragments that must never be DEFINED as a subject


_LOW_CONTENT_SUBJ = {
    "우리", "저희", "너", "넌", "너희", "네가", "니가", "너가", "저", "제", "제가", "내", "나",
    "그", "이", "저것", "그것", "이것", "저거", "그거", "이거", "얘", "걔", "쟤",
    "얘기", "아", "어", "음", "왜", "뭐", "무슨", "무엇", "누구", "어디", "언제", "지금",
    "방금", "여기", "거기", "저기", "것", "게", "거", "때",
}


def _topic_first_noun(query: str) -> str:
    """The TOPIC is the FIRST content noun (Korean is topic-first): " 
 ?" is about , not . Strip particles; drop wh-words, adverbs, and
 adjective/verb forms (////) that are never a topic."""
# ONE function-word list, shared with the lexicon lane rather than kept as a second, smaller copy
# that drifts. This list was 28 words and missed the ones that actually bit: 'like', 'look',
# 'better', 'different'. Measured 2026-07-17: "What does a polar bear look like?" answered
# "like is a kind of kind. like relates to unlike." — the extractor took the function word as the
# topic. A function word is how a question is asked; it is never what it is about.
try:
    from packages.graph_scale.lexicon_lane import _FUNCTION_WORDS as _LEX_FUNCTION_WORDS
except Exception:  # pragma: no cover - keep the lane usable if the cartridge module moves
    _LEX_FUNCTION_WORDS = frozenset()
_EN_STOP = set(_LEX_FUNCTION_WORDS) | {
    "tell", "me", "about", "the", "a", "an", "of", "on", "what", "who", "is",
    "are", "do", "does", "how", "why", "can", "could", "please", "give", "show",
    "explain", "and", "or", "to", "for", "in", "with", "regarding",
    # measured topic-thieves: each one was answered as if it were the subject
    "like", "look", "looks", "better", "best", "different", "difference", "compare",
    "want", "need", "get", "make", "start", "learn", "help", "work", "use", "mean",
}


def _topic_first_noun(query: str) -> str:
    """The TOPIC is the FIRST content noun (Korean is topic-first): " 
 ?" is about , not . Strip particles; drop wh-words, adverbs, and
 adjective/verb forms (////) that are never a topic."""
    for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", query):
        t = re.sub(r"(으로부터|이라는|에서는|이랑|랑|까지|부터|마다|에게|한테|은|는|이|가|을|를|의|란|이란|에|에서|으로|로|와|과)$", "", t)
        if not t or _ADVERBS.match(t) or t.lower() in _EN_STOP:
            continue
        if re.match(r"^(뭐|무엇|누구|어디|언제|왜|어떻게|얼마|알려|설명|신비|힘|추천|방법|정도)", t):
            continue
        if re.search(r"(다|해|줘|워|셔|았|었|였|랐|겠|돼|여요|어요)$", t):   # verb/adjective forms
            continue
        return t
    return ""


def _clarify_engage(query: str, language: str) -> dict[str, Any]:
    """Honest clarify when there is no real subject (a predicate/pronoun-only utterance whose
    referent we can't resolve). NOT a fabricated definition, NOT the web-hedge meta-template.
    Demonstrative-aware and lightly varied so it doesn't read as one fixed line."""
    demonstrative = bool(re.search(r"(이거|그거|저거|이건|그건|저건|여기|거기|저기|이래|그래|방금|아까|저게|이게)", query))
    seed = int(hashlib.md5(query.strip().encode("utf-8")).hexdigest(), 16)
    if language == "en":
        opts = (["I want to help, but I'm not sure what you're referring to — could you say which thing you mean?"]
                if demonstrative else
                ["Could you say a bit more about what you'd like to know?"])
        ans = opts[seed % len(opts)]
    else:
        if demonstrative:
            opts = ["무엇을 말씀하시는지 짚어주시면 바로 봐드릴게요 — ‘그거/이거’가 가리키는 게 뭘까요?",
                    "어떤 걸 말씀하시는 건지 한 가지만 더 알려주시면, 이어서 답해드릴게요.",
                    "제가 지금 그 대상을 못 잡았어요. 무엇을 두고 하신 말인지 알려주시겠어요?"]
        else:
            opts = ["무엇에 대해 궁금하신지 조금만 더 구체적으로 말씀해 주시겠어요?",
                    "어떤 걸 여쭤보시는 건지 한 가지만 짚어주시면 바로 답해드릴게요."]
        ans = opts[seed % len(opts)]
    return {"answer": ans, "answer_kind": "clarify", "engaged": True, "grounded": False,
            "confidence": 0.3, "reasoning_certificate": {
                "derivation_kind": "clarification", "anchor_concept": None, "steps": [],
                "evidence_concepts": [], "confidence": 0.3, "confidence_basis": "no_resolvable_subject",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False}}}


def _best_subject(query: str) -> str:

    m = re.search(r"([가-힣A-Za-z0-9]{2,})\s*(?:에 대해|에 관해|에 대하여|에 관하여|란|이란)", query)
    if m:
        return m.group(1)
    # English "(tell me) about/on/of the X" — the topic follows the preposition.
    m2 = re.search(r"\b(?:about|regarding|on|of)\s+(?:the\s+|a\s+|an\s+)?([A-Za-z][A-Za-z]+)", query, re.I)
    if m2 and m2.group(1).lower() not in _EN_STOP:
        return m2.group(1)
    topic = _topic_first_noun(query)
    try:
        from .query_frame import parse as _parse
        s = _parse(query).subject

        # usually the attribute, not the topic. Accept it only when it's a clean noun AND
        # not preceded by the topic noun; otherwise the topic-first noun wins.
        if s and not _ADVERBS.match(s) and not re.search(r"(아|어|지|해|줘|워|았|었|겠|돼)$", s):
            if topic and topic != s and 0 <= query.find(topic) < query.find(s):
                return topic
            return s
    except Exception:
        pass
    if topic:
        return topic
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", query)
    return max(toks, key=len) if toks else query.strip()


def _batchim(word: str) -> bool:
    """True if the last Korean syllable has a final consonant () — for josa choice."""
    w = re.sub(r"[)\]\"'\s]+$", "", str(word or ""))
    if not w or not ("가" <= w[-1] <= "힣"):
        return True
    return (ord(w[-1]) - 0xAC00) % 28 != 0


def _eun(w: str) -> str:
    return f"{w}은" if _batchim(w) else f"{w}는"


def _euro(w: str) -> str:
    return f"{w}으로" if _batchim(w) else f"{w}로"


def _ieyo(w: str) -> str:
    return "이에요" if _batchim(w) else "예요"


def _bigrams(s: str) -> set[str]:
    t = re.sub(r"[^가-힣a-z0-9]", "", str(s).lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}


def _is_english(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z .'\-]*", str(s or "").strip()))


def _relevant(subject: str, obj: str) -> bool:
    """Semantic relevance filter (owner: ): drop a related fact whose
 object doesn't RESONATE with the subject in the clean phase space — that's how the
 polysemy noise ( → 'hypocaust') gets silenced. Unknown objects get benefit of the
 doubt (kept); only a confidently-LOW resonance is rejected."""
    try:
        from . import clean_space
        r = clean_space.resonance(subject, obj)
        if r is not None and r < 0.35:
            return False
    except Exception:
        pass
    return True


def _phrase(subject: str, p: str, o: str, ko: bool) -> str:
    if not ko:
        verb = {"is_a": "is a kind of", "capital": "has the capital",
                "located_in": "is located in", "part_of": "is part of"}.get(p, "relates to")
        return f"{subject} {verb} {o}"
    if p == "is_a":
        return f"{_eun(subject)} {o}의 한 종류예요"
    if p == "capital":
        return f"{subject}의 수도는 {o}{_ieyo(o)}"
    if p == "located_in":
        return f"{_eun(subject)} {o}에 있어요"
    if p == "part_of":
        return f"{_eun(subject)} {o}의 일부예요"
    if p in ("인구", "면적"):
        return f"{subject}의 {p}은 {o}{_ieyo(o)}"
    if p == "defined_as":
        return f"{_eun(subject)} {o}" + ("" if o.endswith(("다", "요", ".", "음", "함")) else _ieyo(o))
    return f"{_eun(subject)} {_euro(o)} 이어져 있어요"


def _fact_sentences(store: Any, subject: str, language: str, query: str = "") -> list[str]:
    """Natural Korean sentences for what the graph really holds around the subject —
 relevance-filtered + SENSE-DISAMBIGUATED. A polysemous subject (=sky/God/root,
 =apple/apology) has several defined_as senses; dumping ALL of them wrecks the
 answer. So we score each fact by how well it fits the QUERY CONTEXT (shared words +
 phase-space resonance) and keep only the SINGLE best-fitting definition, plus the
 other relation facts. Context-driven sense selection, No-LLM."""
    try:
        rows = store.facts_about(subject, limit=16) or []
    except Exception:
        return []
    ko = language == "ko"
    q_words = {w for w in re.findall(r"[가-힣A-Za-z]{2,}", str(query)) if w != subject}
    cands: list[tuple[float, str, str]] = []          # (context_score, p, o)
    obj_bgs: list[set[str]] = []
    for _s, p, o in rows:
        o = str(o or "").strip()
        if p in ("alias", "sense") or not o or len(o) > 80:
            continue
        if ko and _is_english(o) and not _is_english(subject) and p in ("defined_as", "alias"):
            continue
        if not _relevant(subject, o):
            continue
        bg = _bigrams(o)
        if any(len(bg & c) / max(1, min(len(bg), len(c))) > 0.7 for c in obj_bgs):
            continue
        obj_bgs.append(bg)
        # CONTEXT SCORE: shared content words with the query pick the right SENSE

        o_words = set(re.findall(r"[가-힣A-Za-z]{2,}", o))
        score = 2.0 * len(q_words & o_words) + (0.5 if p == "is_a" else 0.0)
        try:
            from . import clean_space
            for qw in list(q_words)[:4]:
                r = clean_space.resonance(subject, qw)
                if r is not None and r > 0.5 and qw in o_words:
                    score += 1.0
        except Exception:
            pass
        cands.append((score, p, o))

    # SELECT: at most ONE definition (the best-fitting sense) + other relation facts.
    cands.sort(key=lambda c: -c[0])
    out: list[str] = []
    used_def = False
    for _score, p, o in cands:
        if p == "defined_as":
            if used_def:
                continue                       # one sense only — no polysemy dump
            used_def = True
        out.append(_phrase(subject, p, o, ko))
        if len(out) >= 4:
            break
    return out


def engage(query: str, language: str = "ko", *, store: Any = None) -> dict[str, Any] | None:
    """Build a substantive, honest, non-dead-end response for a hard-miss query.
    Returns an answer dict (grounded=False, engaged=True) or None only if the
    engine is truly empty. NEVER fabricates a fact."""
    # INFER the true central subject + intent (intent_inference) instead of grabbing a

    # the intent is a safe-quantity ask. Fall back to the heuristic only if inference is empty.
    # UNIFIED MEANING (plumbing, 2026-07-10): build the ONE SemanticFrame — it carries the
    # conversational act AND (via intent_inference, folded in) the fact intent + arguments — and
    # drive the grounded executor from it. One parse, one meaning object. Falls back to a direct
    # infer if the frame is unavailable, so behavior is identical, never worse.
    subject, _intent, _inf = "", "definition", {}
    try:
        from .semantic_frame import encode as _fencode
        _frame = _fencode(query, store=store)
        _inf = _frame.to_inf()
        subject, _intent = _frame.subject or "", _frame.fact_intent or "definition"
    except Exception:
        try:
            from .intent_inference import infer
            _inf = infer(query, store) or {}
            subject, _intent = _inf.get("subject") or "", _inf.get("intent") or "definition"
        except Exception:
            pass
    if not subject:
        subject = _best_subject(query)
    # MORPHEME GUARD (owner 2026-07-10): never let a pronoun/adverb/predicate fragment survive as

    # the same Kiwi-backed noun check; if it's not a real content noun, there is no subject.
    if subject:
        try:
            from .query_frame import _ok_noun
            if not _ok_noun(subject):
                subject = ""
        except Exception:
            pass
    # NO real subject AND no specific fact-intent to pursue → an honest clarify, NOT a definition of


    _intent_kind = str((_inf or {}).get("intent") or "definition")
    if not subject and _intent_kind in ("definition", "", "entity"):
        return _clarify_engage(query, language)
    # EXECUTE the intent against the graph FIRST (verification via is_a traversal,
    # identity, location) — a targeted REASONED answer that follows the inferred intent,
    # instead of a generic definition. Returns None → fall through to engagement.
    if store is not None and _inf:
        try:
            from .intent_executor import execute as _exec
            _ex = _exec(query, _inf, store)
            if _ex and str(_ex.get("answer") or "").strip():
                _ex.setdefault("engaged", True)
                return _ex
        except Exception:
            pass
    parts: list[str] = []
    used_soft = None
    hypothesis = None

    if store is not None:



        # a 'rel: obj' list. Every fact stays verbatim — only the connective flow is



        # object noun's definition is off-topic — skip it and let the advice engagement carry
        # the answer, so we don't open with an irrelevant dictionary line.
        _howto = str(_intent or "") == "method"
        # LOW-CONTENT SUBJECT guard (owner 2026-07-10 diverse test): when the extracted subject


        # lead — the shape/cue engagement carries the reply instead of a dictionary line.
        _lowsubj = subject in _LOW_CONTENT_SUBJ
        _facts = [] if (_howto or _lowsubj) else _fact_sentences(store, subject, language, query)
        if _facts:

            # the verified facts; if it can't, they stand plainly. Honesty is the grounding, not a phrase.
            woven = None
            if len(_facts) >= 2:
                try:
                    from packages.base_brain.grounded_generation import synthesize
                    syn = synthesize(query, [{"name": None, "description": s} for s in _facts],
                                     language, min_facts=2, max_facts=4, include_opener=False)
                    woven = str((syn or {}).get("answer") or "").strip()
                except Exception:
                    woven = None
            body = woven or (". ".join(_facts) + ".")
            if body:
                parts.append(body)
        # 2) nearest verified concept (soft, explicitly framed AS a neighbor)
        try:
            from .soft_resolve import soft_context_line
            sc = soft_context_line(store, subject, language)
            if sc and sc.get("text"):
                parts.append(sc["text"])
                used_soft = sc.get("neighbor")
        except Exception:
            pass

    # 2.5) NEXT-FACT PREDICTION — the reasoned guess instead of the dead-end.
    # When the store holds no explicit fact, the trained phase geometry proposes
    # the most probable MISSING edge and we speak it HEDGED (source-tagged as a

    # Never a fabricated fact: it is labeled a hypothesis with a model score.
    try:
        from . import fact_prediction as _fp
        # DUAL-SPACE gate: a prediction from the CLEAN ConceptNet geometry is
        # speakable (trusted=True); one from the noisy store stays gated behind
        # ENGAGE_ENABLED (still garbage). Truth>coverage, but clean is trustworthy.
        ph = _fp.mint_predicted_fact(subject, store=store, language=language)
        if ph and ph.get("text") and (ph.get("trusted") or getattr(_fp, "ENGAGE_ENABLED", False)):
            parts.append(ph["text"])
            hypothesis = ph["prediction"]
    except Exception:
        pass

    # 3) shape-aware conversational engagement (opinion/advice/open questions)
    try:
        from packages.base_brain.zero_user_answer import _question_shape, _shape_engage
        shp = _question_shape(query)
        if shp and shp != "factual":
            se = _shape_engage(shp, language)
            if se:
                parts.append(se)
    except Exception:
        pass

    # 4) forward cue — INTENT-AWARE: acknowledge what was really asked (the inferred

    # question's true aim even when it can't fully answer offline.
    _INTENT_CUE_KO = {
        "safe_quantity": "적정 섭취량·권장 한도는 실시간 웹으로 근거를 찾아 정확히 알려드릴게요.",
        "quantity": "정확한 수치는 실시간 웹으로 확인해 알려드릴게요.",
        "location": "정확한 위치는 실시간 웹으로 확인해 드릴게요.",
        "time": "정확한 시점은 실시간 웹으로 확인해 드릴게요.",
        "cause": "그 원인은 실시간 웹으로 근거를 모아 짚어드릴게요.",
        "method": "단계별 방법은 실시간 웹으로 근거를 찾아 정리해 드릴게요.",
        "compare": "둘의 차이는 실시간 웹으로 각각 확인해 비교해 드릴게요.",
    }
    if language == "ko":
        cue = _INTENT_CUE_KO.get(_intent) or (
            f"‘{subject}’은(는) 지금 실시간 웹으로 교차 확인해 이어서 답하고, 배운 것은 그래프에 남깁니다."
            if not parts else
            "더 궁금하시면 실시간 웹 검증으로 더 깊이 파고들 수 있어요.")
    else:
        cue = (f"I'll verify '{subject}' on the live web and continue, keeping what I learn in the graph."
               if not parts else "Ask me to dig deeper and I'll verify it live on the web.")
    # DEDUP the web-hedge (owner 2026-07-10 fluency): a shape-engage part may already have


    # only add the cue when nothing has hedged toward the web yet.
    already_webhedged = any(("웹" in p or "web" in p.lower()) for p in parts if p)
    if not already_webhedged:
        parts.append(cue)

    # each engagement fragment is its own sentence — terminate it so they don't run

    def _term(p: str) -> str:
        p = p.strip()
        return p if not p or re.search(r"[.!?。…]$", p) else p + "."
    text = " ".join(_term(p) for p in parts if p.strip()).strip()
    if not text:
        return None
    steps = [{"type": "engagement", "fact": p} for p in parts]
    if hypothesis:
        steps.append({"type": "predicted_hypothesis", "triple": hypothesis,
                      "source": "predicted_hypothesis"})
    return {
        "answer": text,
        "reasoning_certificate": {
            "derivation_kind": "engagement_no_dead_end",
            "anchor_concept": {"label": subject},
            "steps": steps,
            "evidence_concepts": [subject] + ([used_soft] if used_soft else []),
            "confidence": 0.3,
            "confidence_basis": "no direct grounded fact — engaged with nearest "
                                "verified context" + (", plus a labeled phase-space "
                                "hypothesis (not a confirmed fact)" if hypothesis else "")
                                + " and a live-web path; nothing fabricated",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": bool(hypothesis), "engaged": True,
                           "hypothesis": bool(hypothesis)},
        },
        "confidence": 0.3,
        "answer_kind": "engagement_no_dead_end",
        "grounded": False,
        "engaged": True,
        "hypothesis": hypothesis,
    }
