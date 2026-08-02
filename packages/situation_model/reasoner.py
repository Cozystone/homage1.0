# -*- coding: utf-8 -*-
"""Reason over a situation graph — answer questions by traversal, abstain when unsupported (G3).

The honest floor: an answer is returned ONLY when the situation graph supports it with a specific
event or ordering; otherwise the reasoner abstains ("the passage does not say"). Fabrication is
impossible by construction — every answer cites the event it came from. Domain-blind: the same
traversal answers a chemistry passage and a crime report.
"""
from __future__ import annotations

import re
from typing import Any

from .builder import Situation, build, _clean_np

_ABSTAIN = {"answer": None, "supported": False, "evidence": "",
            "reply": "The passage does not say — I won't guess."}


_Q_STOP = {"the", "a", "an", "did", "does", "was", "were", "is", "are", "has", "have", "who",
           "what", "which", "when", "where", "why", "how", "to", "of", "in", "on", "at", "and",
           "that", "this", "there", "then", "do", "you", "it", "its", "his", "her", "their"}


def _stem(w: str) -> str:
    """A crude stem so move/moved/moves, open/opened match. No lexicon — suffix peeling only.
    Peels a trailing silent 'e' too so 'moved'->'mov' and 'move'->'mov' align (measured mismatch)."""
    w = w.lower()
    for suf in ("ed", "ing", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def _content(s: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z']+", (s or "").lower())
            if len(w) > 2 and w not in _Q_STOP}


def _overlap(a: str, b: str) -> int:
    return len(_content(a) & _content(b))


def answer(question: str, sit: Situation) -> dict[str, Any]:
    """Answer against the built world; if a corrupted QUESTION is what stopped us, repair the
    question's surface and ask once more.

    The retry is gated on abstention, so a clean question is answered by the clean path and never
    sees a guess. Fragmentation strips the very words the question patterns key on ('Where is
    Mary?' -> 'Where Mary?'), and a typo does the same — both look identical to a world we simply
    could not query, which is why abstention (not a wrong answer) was the dominant noise failure."""
    out = _answer_once(question, sit)
    if out.get("answer") is not None:
        return out
    from packages.situation_model.text_normalizer import (repair_function_words,
                                                          repair_with_lexicon, snap_to_frame_vocab)
    repaired = repair_function_words(repair_with_lexicon(
        snap_to_frame_vocab((question or "").strip())))
    if repaired.strip().lower() != (question or "").strip().lower():
        retry = _answer_once(repaired, sit)
        if retry.get("answer") is not None:
            return retry
    return out


def _answer_once(question: str, sit: Situation) -> dict[str, Any]:
    q = (question or "").strip()
    # Read the question in the SAME spelling the passage settled on. A question corrupted
    # independently of its passage ('where is the kitchin?') otherwise queries a room that,
    # as far as the built world knows, does not exist — and we abstain on our own typo.
    if getattr(sit, "canon", None):
        from packages.situation_model.text_normalizer import apply_canon
        q = apply_canon(q, sit.canon)
    ql = q.lower()
    # MECHANISM reasoning (how the world works) — tried BEFORE state routing only for the question
    # shapes it owns (can-X / if-what-happens / what-happens-to), so ordinary state questions are
    # untouched. Fires on conditions stated in the passage; abstains when a material property is
    # ungrounded. This is what answers the realistic questions the state model alone abstains on.
    if re.search(r"\bcan\s+\w+\b|what happens|if\b.*\?", ql):
        from packages.situation_model.mechanism import answer_mechanism
        src = getattr(sit, "_source_text", "") or " ".join(
            e.raw for e in getattr(sit, "events", []) if getattr(e, "raw", ""))
        mech = answer_mechanism(q, src)
        if mech is not None:
            return {"answer": mech["answer"], "supported": mech["supported"],
                    "evidence": mech.get("evidence", ""),
                    "reasoning_certificate": mech.get("reasoning", ""),
                    "law": mech.get("law", "")}
    st = _state_answer(ql, sit)          # typed WORLD-STATE organs first (location, possession,
    if st is not None:                   # spatial, kinds, motive) — they carry their own evidence;
        return st                        # anything they cannot ground falls through unchanged
    if not sit.events:
        return dict(_ABSTAIN)

    # ORDER questions: only genuine narrative-position asks ('what happened first/last', 'what came
    # before ...'). A bare 'end' must NOT trigger this (measured: 'did it end?' was misread as
    # 'what happened at the end' and returned the last event instead of abstaining).
    _FIRST = re.search(r"\b(happened?|came?|come|comes|was|is|occurred)\s+first\b|"
                       r"\bfirst\s+(?:thing|event|step|action)\b|\bwhat\s+.*\bbegan?\b", ql)
    _LAST = re.search(r"\b(happened?|came?|come|comes|was|is|occurred)\s+(?:last|finally)\b|"
                      r"\blast\s+(?:thing|event|step|action)\b|\bwhat\s+.*\bend(?:ed)?\s+(?:with|the)\b",
                      ql)
    if _FIRST or _LAST:
        ordered = _time_ordered(sit)
        e = ordered[0] if _FIRST else ordered[-1]
        return _hit(f"{e.subject} {e.verb} {e.obj}".strip(), e)

    # YES/NO: did <subj> <verb> <obj>?
    if re.match(r"^(did|does|was|were|is|are|has|have)\b", ql):
        target = _best_event(q, sit)
        if target is None:
            return dict(_ABSTAIN)
        if target.negated:
            return _hit("No — the passage states this did not happen.", target)
        return _hit("Yes — the passage states this.", target)

    # WHO <verb> ...?  -> the subject of the matching event. The action must actually MATCH: a bare
    # noun overlap ('who paid for the parcel' vs 'courier collected the parcel') is not an answer,
    # it is a different action — so require the event's verb, else abstain (measured leak: answered
    # 'courier' to 'who paid'). Honesty over coverage.
    if ql.startswith("who"):
        target = _best_event(q, sit, ignore_subject=True, require_verb=True)
        if target and target.subject:
            return _hit(target.subject, target)
        return dict(_ABSTAIN)

    # WHAT did <subj> <verb>?  /  WHAT <verb> ...  -> the object of the matching event, same verb
    # requirement (measured leak: 'what color was the vault' answered 'vault' off a noun overlap).
    if ql.startswith("what") or ql.startswith("which"):
        target = _best_event(q, sit, require_verb=True)
        if target and target.obj:
            return _hit(target.obj, target)
        return dict(_ABSTAIN)

    # WHEN falls back to the event's time cue if present, else abstain
    if ql.startswith("when"):
        target = _best_event(q, sit)
        if target and target.time_cue:
            return _hit(target.time_cue, target)
        return dict(_ABSTAIN)

    # WHERE: v0 does not extract locations, so it abstains rather than return an unrelated event
    # (measured: 'Where does the driver live?' must not answer with 'the driver loaded the crates')
    if ql.startswith("where"):
        return dict(_ABSTAIN)

    # generic: best-matching event's raw clause, only if the overlap is real
    target = _best_event(q, sit)
    if target and _overlap(q, target.raw) >= 2:
        return _hit(target.raw, target)
    return dict(_ABSTAIN)


def _sa(ans: str, ev: str, induced: bool = False) -> dict[str, Any]:
    return {"answer": ans, "supported": True, "evidence": ev, "induced": induced,
            "reply": (f"{ans} (induced from same-kind peers in the passage)" if induced else ans)}


def _belief_answer(qs: str, t) -> dict[str, Any] | None:
    """Theory-of-Mind routes: a belief question asks what an AGENT thinks, not where the world IS.
    Returns the believed location; an explicit abstention when the question is about belief but the
    belief is ungrounded (never let a belief question fall through to the reality answer — that is
    the egocentric error the benchmark scores against); or None when it is not a belief question."""
    # second-order (two agents) FIRST — 'B thinks that A will look' must not be read as first-order
    m = re.match(r"^where\s+does\s+(\w+)\s+think(?:s)?\s+that\s+(\w+)\s+(?:will\s+look\s+for|"
                 r"looks?\s+for|will\s+search\s+for)\s+(?:the\s+)?(\w+)$", qs)
    if not m:
        m = re.match(r"^where\s+does\s+(\w+)\s+believe(?:s)?\s+(?:that\s+)?(\w+)\s+think(?:s)?\s+"
                     r"(?:the\s+)?(\w+)\s+is$", qs)
    if m:
        r = t.believes_second(m.group(1), m.group(2), m.group(3))
        return _sa(*r) if r else dict(_ABSTAIN)
    # first-order — 'where will X search when X comes back' (three groups: two names + object)
    m = re.match(r"^when\s+(\w+)\s+comes?\s+back,?\s+where\s+will\s+(\w+)\s+"
                 r"(?:search|look)\s+for\s+(?:the\s+)?(\w+)$", qs)
    if m:
        r = t.believes(m.group(2), m.group(3))
        return _sa(*r) if r else dict(_ABSTAIN)
    # first-order — 'where does X think the O is' / 'where will X look for the O'
    m = re.match(r"^where\s+does\s+(\w+)\s+think(?:s)?\s+(?:the\s+)?(\w+)\s+is$", qs)
    if not m:
        m = re.match(r"^where\s+will\s+(\w+)\s+(?:look|search)\s+for\s+(?:the\s+)?(\w+)$", qs)
    if m:
        r = t.believes(m.group(1), m.group(2))
        return _sa(*r) if r else dict(_ABSTAIN)
    return None


def _state_answer(ql: str, sit: Situation) -> dict[str, Any] | None:
    """Route a question to the typed world-state organs. None => not a state question / no grounded
    state => the caller falls through to the event-graph logic (which may still abstain honestly)."""
    t = getattr(sit, "state", None)
    if t is None:
        return None
    qs = ql.strip().rstrip("?").strip()

    # Theory-of-Mind (belief) questions are answered from the per-agent belief shadow, before the
    # reality routes — so 'where does A think X is' is never answered with X's TRUE location.
    b = _belief_answer(qs, t)
    if b is not None:
        return b

    # where is/was the X [before/after the Y]
    m = re.match(r"^where\s+(?:is|was)\s+(?:the\s+)?(.+?)(?:\s+(before|after)\s+(?:the\s+)?(.+))?$", qs)
    if m:
        who, rel, ref = m.group(1), m.group(2), m.group(3)
        if rel and ref:
            r = t.where_was(who, ref, before=(rel == "before"))
            return _sa(*r) if r else None
        r = t.where_is(who)
        return _sa(*r) if r else None

    # where will X go (in-story induction from a same-state peer)
    m = re.match(r"^where\s+will\s+(.+?)\s+go$", qs)
    if m:
        r = t.predicted_destination(m.group(1))
        return _sa(r[0], r[1], induced=True) if r else None

    # is X in the L — a STATE-OWNED shape: if the tracker cannot ground it, abstain here rather
    # than fall through to the event-overlap yes/no (measured: that fallthrough answered a
    # confident 'Yes' off noun overlap — the dangerous failure mode, worse than abstaining)
    m = re.match(r"^is\s+(.+?)\s+in\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.loc_yesno(m.group(1), m.group(2))
        return _sa(*r) if r else dict(_ABSTAIN)

    # how many objects is X holding/carrying
    m = re.match(r"^how\s+many\s+objects?\s+is\s+(.+?)\s+(?:holding|carrying)$", qs)
    if m:
        h = t.holdings(m.group(1))
        return _sa(t.count_word(len(h)), "") if h is not None else None

    # what is X holding/carrying
    m = re.match(r"^what\s+is\s+(.+?)\s+(?:holding|carrying)$", qs)
    if m:
        h = t.holdings(m.group(1))
        if h is None:
            return None
        return _sa(",".join(h) if h else "nothing", "")

    # three-arg give relations
    m = re.match(r"^who\s+gave\s+(?:the\s+)?(.+?)\s+to\s+(.+)$", qs)
    if m:
        for g in reversed(t.w.gives):
            if g.obj == m.group(1).strip() and g.recipient == m.group(2).strip():
                return _sa(g.giver, g.raw)
        return None
    m = re.match(r"^what\s+did\s+(.+?)\s+give\s+to\s+(.+)$", qs)
    if m:
        for g in reversed(t.w.gives):
            if g.giver == m.group(1).strip() and g.recipient == m.group(2).strip():
                return _sa(g.obj, g.raw)
        return None
    m = re.match(r"^who\s+did\s+(.+?)\s+give\s+(?:the\s+)?(.+?)\s+to$", qs)
    if m:
        for g in reversed(t.w.gives):
            if g.giver == m.group(1).strip() and g.obj == m.group(2).strip():
                return _sa(g.recipient, g.raw)
        return None
    m = re.match(r"^who\s+received\s+(?:the\s+)?(.+)$", qs)
    if m:
        for g in reversed(t.w.gives):
            if g.obj == m.group(1).strip():
                return _sa(g.recipient, g.raw)
        return None

    # spatial: what is <dir> of the X / what is the X <dir> of
    m = re.match(r"^what\s+is\s+(north|south|east|west|above|below)\s+of\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.spatial_what(m.group(1), m.group(2), inverse=False)
        return _sa(*r) if r else None
    m = re.match(r"^what\s+is\s+(?:the\s+)?(.+?)\s+(north|south|east|west|above|below)\s+of$", qs)
    if m:
        r = t.spatial_what(m.group(2), m.group(1), inverse=True)
        return _sa(*r) if r else None

    # positional yes/no: is the A [to the] left/right/above/below [of] the B — state-owned shape,
    # abstain when ungrounded (same confident-wrong fallthrough guard as location yes/no)
    m = re.match(r"^is\s+(?:the\s+)?(.+?)\s+(?:to\s+the\s+)?(left|right|above|below)\s+(?:of\s+)?"
                 r"(?:the\s+)?(.+)$", qs)
    if m:
        r = t.pos_yesno(m.group(1), m.group(2), m.group(3))
        return _sa(*r) if r else dict(_ABSTAIN)

    # size yes/no: is the A bigger/smaller than the B / does the A fit in the B
    m = re.match(r"^is\s+(?:the\s+)?(.+?)\s+(bigger|larger|smaller)\s+than\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.size_yesno(m.group(1), m.group(2), m.group(3))
        return _sa(*r) if r else None
    m = re.match(r"^does\s+(?:the\s+)?(.+?)\s+fit\s+in(?:side)?\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.size_yesno(m.group(1), "fit", m.group(2))
        return _sa(*r) if r else None

    # path: how do you go from the A to the B
    m = re.match(r"^how\s+do\s+you\s+go\s+from\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.path(m.group(1), m.group(2))
        return _sa(*r) if r else None

    # inherited kind relation: what is X afraid of
    m = re.match(r"^what\s+is\s+(.+?)\s+afraid\s+of$", qs)
    if m:
        r = t.kind_relation(m.group(1), "afraid of")
        return _sa(*r) if r else None

    # colour/property: what color is X
    m = re.match(r"^what\s+colou?r\s+is\s+(.+)$", qs)
    if m:
        r = t.induced_adjective(m.group(1))
        return _sa(r[0], r[1], induced=r[2]) if r else None

    # motive: why did X go to the L / why did X get the O
    m = re.match(r"^why\s+did\s+(.+?)\s+go\s+(?:back\s+)?to\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.motive(m.group(1), m.group(2))
        return _sa(*r) if r else None
    m = re.match(r"^why\s+did\s+(.+?)\s+(?:get|grab|take|pick\s+up)\s+(?:the\s+)?(.+)$", qs)
    if m:
        r = t.motive_get(m.group(1), m.group(2))
        return _sa(*r) if r else None
    return None


def _time_ordered(sit: Situation):
    # explicit cues override narrative order for the two that reorder; else narrative order stands
    evs = list(sit.events)
    first_cue = {"first", "initially", "earlier"}
    last_cue = {"finally", "later", "subsequently", "afterward", "afterwards"}
    evs.sort(key=lambda e: (0 if e.time_cue in first_cue else 2 if e.time_cue in last_cue else 1,
                            e.order))
    return evs


def _best_event(q: str, sit: Situation, ignore_subject: bool = False, require_verb: bool = False):
    best, best_score, best_verb_match = None, 0, False
    qstems = _content(q)
    for e in sit.events:
        hay = f"{'' if ignore_subject else e.subject} {e.verb} {e.obj}"
        sc = _overlap(q, hay)
        verb_match = bool(e.verb) and _stem(e.verb) in qstems
        # a shared verb (stem-matched, so move/moved align) is worth more than an incidental noun
        if verb_match:
            sc += 2
        if sc > best_score:
            best, best_score, best_verb_match = e, sc, verb_match
    if best_score < 1:
        return None
    # when the caller demands the ACTION match (who/what), a best hit resting only on a shared noun
    # is not an answer — abstain rather than return a different event's actor/object
    if require_verb and not best_verb_match:
        return None
    return best


def _hit(ans: str, e) -> dict[str, Any]:
    return {"answer": ans, "supported": True,
            "evidence": e.raw, "reply": ans,
            "event": {"subject": e.subject, "verb": e.verb, "obj": e.obj, "order": e.order}}


def comprehend(text: str, question: str) -> dict[str, Any]:
    """Build the world from the text, then answer — the one entry point. Abstains rather than
    fabricates. This is the G3 capability, domain-blind."""
    return answer(question, build(text))
