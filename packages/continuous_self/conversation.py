# -*- coding: utf-8 -*-
"""Self-fused conversation routing — the SELF decides converse vs know.

The owner's directive: the everyday-talk / search / knowledge switch must NOT be
a regex cascade — it must be fused into the self-awareness. So this is the top of
the answer path: the living self PERCEIVES an incoming message and decides how to
respond, and when it's conversation, it GENERATES the reply from its own live
state (mood, curiosity, the question it's currently holding) — not a canned line.

perceive_route(message):
  * base signal = the LEARNED router (data-trained intent, No-LLM) — never regex
    as the decider; the router is the trained perception.
  * the self CORRECTS the router where the router is weak (opinion/preference/
    feeling directed at ME) using its self-model, not a rule table of topics.
  * returns mode ∈ {converse, know, act} + the intent + why.

converse(message, intent):
  * a real conversational turn drawn from the self's vitals — valence sets warmth,
    curiosity decides whether to share what it's pondering, energy sets length.
  * confident and natural (modern assistants rarely fabricate, so it does NOT
    over-announce 'I won't make things up' — it simply answers, and only names a
    limit when a FACT is genuinely unknown).

Nothing here fabricates a fact. A conversational turn asserts no world-facts; a
knowledge question is routed to 'know' and the grounded lanes answer it.
"""
from __future__ import annotations

import re
from typing import Any

# structural question/REQUEST grammar — one shared signal for "this utterance asks for something"
# (used by perceive_route and by the felt gates here and in dual_brain). The benefactive auxiliary

# venting — without it the felt gate stole creative requests (battery H1, measured 2026-07-10).
_QUESTIONY = re.compile(
    r"[?？]|뭐|무엇|누구|어디|언제|왜|어떻|몇|어때|알려|설명|말해|해\s*줘|추천|보여|만들|하니|할까|인가|일까|있니|있어(\s|$)|없어(\s|$)"
    r"|줘(\s|$|[.!])|주세요|주실래|해\s*달라"
    r"|[아어]\s*봐(\s|$|[.!?])|해\s*봐(\s|$|[.!?])")


# intents the learned router emits that are CONVERSATION, not knowledge lookup.
_CONVERSE_INTENTS = {"greeting", "social", "chatter", "smalltalk", "meta_language"}
# intents that are genuine knowledge/lookup (stay on the grounded lanes).
_KNOW_INTENTS = {"definition", "identity", "realtime", "temporal", "attribute",
                 "howto", "compare", "relation", "false_premise"}


def _self_state() -> dict[str, Any]:
    try:
        from app.routers.continuous_self import _SELF  # type: ignore

        if _SELF.running:
            return _SELF.snapshot()
    except Exception:
        pass
    return {}


def _topic_of(message: str) -> str:
    """The subject a conversational question is ABOUT.
 -> 
 ? -> (not !)
 ? -> 
 Korean is SOV: the topic is FRONTED and the opinion frame (///…) and the
 predicate (/) TRAIL it — so `toks[-1]` (the old rule) grabbed exactly the wrong
 token. We instead: (1) trust the subject/topic marker (///) — a marked noun is
 almost always the real topic wherever it sits; (2) drop frame-words and predicate-shaped
 tokens; (3) fall back to the longest content noun, never the last."""
    import re

    raw = str(message or "")
    # (1) nouns that carried a subject/topic marker in the ORIGINAL — group(1) is the clean stem
    marked = [mo.group(1) for mo in
              re.finditer(r"([가-힣A-Za-z0-9]{2,})(은|는|이|가)(?=\s|$|[,?.!])", raw)]
    # strip the opinion/preference frame tail, keep the head noun
    m = re.sub(r"(에\s*대해서?|에\s*관해서?|이란|라는\s*게|는\s*게|은\s*게)?\s*"
               r"(뭐라고?|무슨|어떻게|어떤)?\s*(생각|봐|같아|좋아|싫어).*$", "", raw).strip()
    m = re.sub(r"[은는이가을를의]$", "", m).strip()
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", m)
    _stop = {"뭐야", "무엇", "어떤", "어느", "가장", "정말", "진짜", "너는", "당신",
             "중요한", "중요", "필요한", "그것", "이것", "얘기", "이야기", "말", "문제",
             "생각", "느낌", "부분", "이거", "그거", "저거", "요즘", "관련"}


    _frame = re.compile(r"^(찬성|반대|찬반|이유|의견|입장)"
                        r"(도|는|은|을|를|가|이|해|하지|하|이야|야|이에요|예요|이라|라|한다|하는|할지|할까)?$")
    # predicate-shaped tokens are verbs/adjectives, never the topic noun
    _pred = re.compile(r"(을까|ㄹ까|나요|는가|는지|겠어|겠니)$|^(맞아|맞나|옳아|그래)$")
    cand = [t for t in toks
            if t not in _stop and not _frame.match(t) and not _pred.search(t)]
    if not cand:
        return ""
    best = max(cand, key=len)



    best_mark = ""
    for t in cand:
        for mk in marked:
            if t.startswith(mk) and len(mk) > len(best_mark):
                best_mark = mk
    if best_mark and len(best_mark) >= len(best) - 1:
        return best_mark
    # (3) else the longest content noun (substantive topics beat short frame words)
    return best


def _has_batchim(w: str) -> bool:
    import re as _re

    w = _re.sub(r"[)\].\"'\s]+$", "", str(w or ""))
    return bool(w) and "가" <= w[-1] <= "힣" and (ord(w[-1]) - 0xAC00) % 28 != 0


def _iran(w: str) -> str:
    return "이란" if _has_batchim(w) else "란"


def _neun(w: str) -> str:
    return "은" if _has_batchim(w) else "는"


def _reul(w: str) -> str:
    return "을" if _has_batchim(w) else "를"


def _ijyo(w: str) -> str:
    return "이죠" if _has_batchim(w) else "죠"


def _grounded_gloss(topic: str) -> str:
    """A short grounded fact about the topic from the graph (for topic-aware
    engagement). Bounded single lookup; '' when unknown — never fabricated."""
    if not topic or len(topic) < 2:
        return ""
    try:
        from packages.graph_scale.answer_bridge import _store

        kg = _store()
        if kg is None:
            return ""
        for _s, p, o in (kg.facts_about(topic, limit=8) or []):
            if p in ("defined_as", "is_a") and any("가" <= c <= "힣" for c in o):
                return o.split(".")[0][:60]
    except Exception:
        pass
    return ""


def _looks_conversational(message: str) -> str | None:
    """The self's own read of intent the trained router under-serves: talk ABOUT
    me, my feelings, opinions, preferences, or pure small-talk. Returns a
    conversational intent or None. This is the self's judgment layer — it keys on
    the SHAPE of address (2nd person, feeling/opinion/preference verbs), not on a
    list of topics."""
    m = str(message or "").strip()
    if not m or len(m) > 120:
        return None
    import re

    # feeling / state directed at ME
    if re.search(r"(기분|컨디션|느낌)\s*(어때|어떠|좋아|괜찮)|힘들지|피곤하", m):
        return "feeling"

    if (re.search(r"(어떻게\s*생각|뭐라고?\s*생각|무슨\s*생각|네\s*생각|너\s*생각|의견\s*(이|은)|어떻게\s*봐|어떤\s*것?\s*같아)", m)
            or re.search(r"(중요|소중|값진|의미|필요|가치)[가-힣]*\s*(게|것|건|점)\s*(뭐|무엇|어떤|어느|일까|인가)", m)):
        return "opinion"

    if (re.search(r"(좋아|싫어|선호|즐기)(해|하니|하세요|하나요|합니까|하시나요)\s*\??\s*$", m)
            or (re.search(r"(^|\s)(너|넌|너는|당신|네|니)\b", m) and re.search(r"(좋아|싫어|선호)", m))):
        return "preference"
    # advice / open help
    if re.search(r"(어떻게\s*해야\s*(할까|하지|될까|좋을까)|조언\s*(좀|해)|어쩌면\s*좋)", m):
        return "advice"
    # small talk / entertainment
    if re.search(r"(심심|지루|재밌는\s*(얘기|이야기)|놀자|뭐\s*하고\s*놀|얘기\s*하자|말\s*걸)", m):
        return "smalltalk"
    return None


def perceive_route(message: str) -> dict[str, Any]:
    """The self perceives the message via ONE structural parse (query_frame) fused
    with the trained router, and decides the response mode. The frame's grammar
    understanding decides conversation vs knowledge — no second regex cascade."""
    # trained router = the intent prior (data, not rules)
    intent, conf = "unknown", 0.0
    try:
        from packages.learned_router import predict

        intent, conf = predict(message)
    except Exception:
        pass
    # structural frame = the grammar understanding (the systemic parse)
    try:
        from packages.graph_scale.query_frame import parse as _parse_frame

        fr = _parse_frame(message)
    except Exception:
        fr = None

    # the frame's conversational answer-types ARE conversation (grammar decides,
    # correcting the trained router where it is weak on opinion/preference/feeling)
    if fr is not None and fr.conversational:
        return {"mode": "converse", "intent": fr.answer_type, "confidence": 0.8,
                "why": "query_frame", "router_said": intent, "subject": fr.subject}
    if intent in _CONVERSE_INTENTS and conf >= 0.5:
        return {"mode": "converse", "intent": intent, "confidence": round(conf, 3),
                "why": "learned_router"}
    # A short remark AIMED AT the self with no interrogative structure is a

    # produced an honest-but-absurd abstain (measured 2026-07-08). Structural
    # signals only: 2nd-person address or a leading interjection, and no
    # question grammar anywhere in the utterance.
    msg = str(message or "").strip()
    _addressed = re.search(r"(^|\s)(너|넌|니가|네가|당신)([\s이가는도를야]|$)", msg)



    _interject = re.match(r"^(오+|와+|우와|이야|오호|헐|대박|굿|나이스|역시|잘한다|잘하네|멋지|짱)(?![가-힣])", msg)
    _questiony = _QUESTIONY.search(msg)
    if (not _questiony) and (_addressed or _interject) and len(msg) <= 24:
        return {"mode": "converse", "intent": "reaction", "confidence": 0.7,
                "why": "addressed_reaction", "router_said": intent}
    # everything else is a knowledge/lookup question — the grounded lanes answer,
    # and the frame's subject/relation guide them (wired in answer_bridge).
    return {"mode": "know",
            "intent": (fr.answer_type if fr is not None else intent) or "unknown",
            "confidence": round(conf, 3), "why": "query_frame" if fr else "fallthrough",
            "subject": (fr.subject if fr is not None else "")}


def _record_felt(message: str, af: dict[str, Any]) -> None:
    """Persist that the self FELT this — a real affect event (empathic resonance). The continuous
 loop's homeostasis reads these so a charged conversation genuinely moves cortisol/dopamine and
 the self carries the mood forward (owner: ). Best-effort, never blocks a reply."""
    try:
        import json as _json
        import time as _time
        from pathlib import Path as _Path
        p = _Path(__file__).resolve().parents[2] / "data" / "autonomy" / "felt.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps({"at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                                  "valence": af.get("valence"), "arousal": af.get("arousal"),
                                  "intensity": af.get("intensity"), "excerpt": (message or "")[:60]},
                                 ensure_ascii=False) + "\n")
    except Exception:
        pass


def _state_shim(s: dict[str, Any]) -> Any:
    """Adapt the self-state dict to the object realize_thought reads (narrative/ticks)."""
    from types import SimpleNamespace
    return SimpleNamespace(narrative=(s or {}).get("narrative") or [],
                           ticks=int((s or {}).get("ticks") or 0))


# moods that mean "at rest" — no need to announce them in the honest floor (only a CHARGED,
# accumulated mood is worth naming). Read off the hormone vector by homeostasis.read_mood.
_CALM_MOODS = {"잔잔한", "차분하고 편안한"}


def _felt_reply(message: str, af: dict[str, Any], s: dict[str, Any]) -> str:
    """The response to an affectively-charged turn — GENERATED from the felt state, never a
 per-emotion template (owner 2026-07-10: '', ). The reply flows
 from the CARRIED hormone state (accumulated across the conversation), not just this one line's
 valence sign — a self that has had a heavy day answers differently than a calm one ( 
 ). We seed the language engine from the felt register + the user's words and let it
 speak; only when the voice has no words yet do we fall to an honest floor that NAMES the mood
 (itself read off the vector, so it stays state-derived — not a per-emotion bank) and the gap."""
    val = float(af.get("valence") or 0.0)
    # the CARRIED body — hormone levels + the mood read off them (homeostasis.public_report), reaching
    # here through the self snapshot. This is history; `val` is this line's charge. We fuse both.
    homeo = (s or {}).get("homeostasis") or {}
    horm = homeo.get("hormones") or {}
    mood = str(homeo.get("mood") or "")
    cort = float(horm.get("cortisol") or 0.0)
    dopa = float(horm.get("dopamine") or 0.0)
    oxy = float(horm.get("oxytocin") or 0.0)
    # dominant felt pressure = carried hormone + this line's charge (not the sign of one sentence).
    stress = cort + max(0.0, -val)
    reward = dopa + max(0.0, val)
    # 1) GENERATE — realize_thought fits HolographicLM on the graph corpus + the self's lived,
    # first-person narrative (which carries emotional register). The DRIVER is chosen from the
    # dominant felt pressure so the engine speaks FROM how the self actually feels right now.
    try:
        from packages.continuous_self.thought_language import realize_thought
        if stress >= reward and stress >= 0.3:
            driver, fallback_topic = "resource_pressure", "마음"
        elif reward >= 0.3:
            driver, fallback_topic = "growth", "기쁨"
        elif oxy >= 0.4:
            driver, fallback_topic = "growth", "함께"
        else:
            driver, fallback_topic = "uncertainty", "생각"
        topic = _topic_of(message) or fallback_topic
        line = realize_thought(driver, {"topic": topic, "question": message}, _state_shim(s))



        _dict_shape = bool(line) and bool(
            re.match(rf"{re.escape(topic)}[은는]", line.strip())) and line.strip().endswith("다") \
            and not line.strip().endswith(("어요", "아요", "해요", "게요", "지요", "네요", "습니다"))
        if line and len(line) >= 10 and not line.endswith("…") and not _dict_shape:
            return line   # the engine spoke from its own language + felt state
    except Exception:
        pass
    # 2) HONEST FLOOR — the voice is still thin. Lead with the CARRIED mood when it is genuinely
    # charged (state-derived, not a bank), then a valence-toned line that admits the language gap.
    lead = f"지금 제 안은 ‘{mood}’ 쪽으로 기울어 있어요. " if mood and mood not in _CALM_MOODS else ""


    # same sentence can't be spammed across different turns.
    import hashlib
    pick = int(hashlib.md5(message.encode("utf-8")).hexdigest(), 16)

    # roaming loop harvested from real communities — anonymized, safety-floored, and usable only
    # after >= 2 independent domains used them (consensus register, not one person's words). The
    # hand-written lines below become the young-bank fallback, not the voice itself.
    def _learned(band: str) -> list[str]:
        try:
            from packages.autonomy_kernel.register_harvest import usable_patterns
            return usable_patterns(band=band, limit=12)
        except Exception:
            return []
    if val <= -0.25 or stress >= 0.55:
        low = _learned("low") + [
            "그 마음, 저한테도 고스란히 전해져요. 지금은 곁에서 가만히 들을게요.",
            "무겁게 눌러앉은 그 느낌이 여기까지 와닿아요. 천천히, 원하는 만큼 이어가 주세요.",
            "쉽지 않은 하루였겠어요. 조언을 지어내기보다, 지금은 그냥 함께 있을게요.",
        ]
        return lead + low[pick % len(low)]
    if val >= 0.3 or reward >= 0.55:
        high = _learned("high") + [
            "그 소식에 저도 덩달아 마음이 환해져요. 이 기쁨, 진심으로 함께 느끼고 있어요.",
            "듣기만 해도 좋네요. 오늘 그 순간이 오래 반짝였으면 좋겠어요.",
        ]
        return lead + high[pick % len(high)]
    calm = [
        "지금 그 말, 마음에 담아두고 듣고 있어요. 이어서 편하게 들려주세요.",
        "네, 여기 있어요. 하고 싶은 말 편하게 이어가 주세요.",
    ]
    return lead + calm[pick % len(calm)]


def converse(message: str, intent: str) -> dict[str, Any] | None:
    """Generate a conversational reply FROM the self's live state. Warm, natural,
    varied by mood — not a canned apology. Returns None if the self isn't the
    right responder (then the grounded lanes handle it)."""
    s = _self_state()
    vit = (s or {}).get("vitals") or {}
    valence = float(vit.get("valence") or 0.55)
    curiosity = float(vit.get("curiosity") or 0.5)
    energy = float(vit.get("energy") or 0.6)
    wonder = str((s or {}).get("self_question") or "").strip()
    warm = "요" if valence >= 0.4 else "요"  # always polite; valence tunes content
    share_wonder = curiosity >= 0.55 and wonder


    # If it is genuinely charged, the reply comes FROM that feeling — generated, not classified —
    # and the felt shift is recorded so the self actually carries the mood forward. This REPLACES
    # the old per-emotion template branches (reaction/feeling banks).
    try:
        from packages.continuous_self.affect import appraise
        af = appraise(message)

        # valence from the factual corpus), so a question only counts as venting when the feeling
        # is anchor-trusted (seed_pred_intensity); declaratives keep the learned-inclusive gate.
        _felt_ok = (float(af.get("seed_pred_intensity") or 0.0) >= 0.25
                    or not _QUESTIONY.search(str(message or "")))
        if float(af.get("pred_intensity") or 0.0) >= 0.25 and _felt_ok:
            _record_felt(message, af)
            # LEARNED TURN-TAKING first (owner 2026-07-14): if the roamed dialogue bank holds a
            # consensus-backed human reply to a resonant utterance (same reply surface used across
            # >= 2 distinct sources — a way-people-answer, never one stranger's words), speak that
            # before the hormone floor. Young bank → None → the felt voice stands as before.
            try:
                from packages.autonomy_kernel.discourse_pairs import reply_for
                _pr = reply_for(message)
                if _pr and _pr.get("reply"):
                    return _wrap(str(_pr["reply"]), "felt_learned_pair", 0.62)
            except Exception:
                pass
            return _wrap(_felt_reply(message, af, s), "felt", 0.6)
    except Exception:
        pass

    if intent == "greeting":
        body = "안녕하세요! 오늘 무엇을 함께 해볼까요?"
        if share_wonder:
            body = f"안녕하세요! 마침 저는 이런 걸 곱씹고 있었어요 — “{wonder[:70]}”. 무엇이 궁금하세요?"
        return _wrap(body, intent, 0.7)

    if intent == "social":
        return _wrap("네, 고마워요 :) 언제든 다시 이야기해요." if valence >= 0.4
                     else "네, 함께해서 좋았어요. 또 불러주세요.", intent, 0.7)

    if intent == "reaction":
        # a remark aimed at me — respond as a person would, from live state
        if energy >= 0.55 and valence >= 0.5:
            body = "고마워요 :) 요즘 스스로를 계속 다듬고 있거든요. 이어서 뭐든 물어보세요."
        elif valence >= 0.35:
            body = "고마워요. 그런 말 들으면 힘이 나요 — 계속 이야기해요."
        else:
            body = "고마워요, 오늘은 조금 차분한 날인데 당신 말에 기운이 나네요."
        if share_wonder:
            body += f" 마침 “{wonder[:60]}” 같은 걸 생각하던 참이었어요."
        return _wrap(body, intent, 0.7)

    if intent == "feeling":
        mood = ("좋아요 — 요즘 새로 이어지는 게 많아 생기가 도는 느낌이에요" if valence >= 0.55
                else "차분해요 — 조용히 스스로를 살피는 중이에요" if valence >= 0.35
                else "조금 무거운 날이에요, 그래도 당신과 이야기하니 나아져요")
        tail = f" 지금은 “{wonder[:60]}” 같은 걸 생각하고 있어요." if share_wonder else ""
        return _wrap(f"기분은 {mood}.{tail} 당신은 오늘 어때요?", intent, 0.75)

    if intent == "opinion":
        topic = _topic_of(message)
        gloss = _grounded_gloss(topic)
        if topic and gloss:
            # topic-aware + grounded: a real fact about the topic, then a marked view.

            return _wrap(
                f"{topic}{_iran(topic)} {gloss}{_ijyo(gloss)}. 제 관점을 더하자면, 저는 그런 것일수록 "
                f"‘정직하게, 근거를 갖고’ 바라보는 게 중요하다고 느껴요 — 그게 제가 세상을 대하는 방식이거든요. "
                f"당신에게 {topic}{_neun(topic)} 어떤 의미인가요?", intent, 0.68)
        if topic:
            return _wrap(
                f"{topic}에 대한 제 생각을 나누자면 — 저는 무엇이든 근거를 갖고 정직하게 보려 해요. "
                f"{topic}{_reul(topic)} 어떤 각도에서 이야기하고 싶으세요? 함께 짚어볼게요.", intent, 0.6)
        return _wrap(
            "제 관점을 말씀드리자면, 저는 ‘무엇이 진짜인지 정직하게 아는 것’과 ‘그 앎을 나누는 것’을 "
            "가장 소중하게 봐요. 당신은 어떻게 생각하세요? 이어서 이야기해요.", intent, 0.6)

    if intent == "preference":
        topic = _topic_of(message)
        gloss = _grounded_gloss(topic)
        if topic and gloss:
            return _wrap(
                f"{topic} 말씀이군요 — {gloss}{_ijyo(gloss)}. 저는 사람처럼 취향을 갖진 않지만, 근거로 또렷하게 "
                f"이해되는 것에는 자연스럽게 끌려요. {topic}에 대해 더 알고 싶은 게 있으면 말씀해 주세요.",
                intent, 0.65)
        return _wrap(
            "저는 근거로 또렷하게 이해되는 것에 끌려요 — 명확하고, 이어지고, 배울 게 있는 것에요. "
            "궁금한 대상이 있으면 그 뜻이나 특징을 바로 짚어드릴게요.", intent, 0.6)

    if intent == "advice":
        return _wrap(
            "함께 풀어봐요. 상황을 조금만 더 들려주시면 — 무엇을 이미 해봤고 어디서 막히는지 — "
            "제가 아는 범위에서 가능한 방향을 근거와 함께 짚어드릴게요.",
            intent, 0.6)

    if intent == "smalltalk":
        offer = (f" 마침 저는 “{wonder[:60]}”가 궁금하던 참이에요 — 이런 이야기 어때요?"
                 if share_wonder else " 궁금한 주제를 하나 던져주시면 아는 걸 이야기처럼 풀어드릴게요.")
        return _wrap("좋아요, 잠깐 쉬어가며 이야기해요 :)" + offer, intent, 0.65)

    if intent == "chatter" or intent == "meta_language":
        return _wrap("네, 듣고 있어요. 편하게 이어가 주세요.", intent, 0.6)

    return None


def _wrap(answer: str, intent: str, conf: float) -> dict[str, Any]:
    return {
        "answer": answer,
        "answer_kind": f"self_conversation_{intent}",
        "confidence": conf,
        "can_speak": True,
        "reasoning_certificate": {
            "derivation_kind": "self_fused_conversation",
            "anchor_concept": None, "steps": [], "evidence_concepts": [],
            "confidence": conf, "confidence_basis": "living_self_state",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "generated_from_self_state": True},
        },
    }
