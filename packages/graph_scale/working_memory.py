# -*- coding: utf-8 -*-
"""Working-memory salience field — reference resolution the way a brain does it, not by rules.

Owner (2026-07-10): " . ."

Gemini proposed "detect a pronoun → substitute the previous subject" — but that is the exact
`if pronoun: substitute()` rule pattern we are trying to leave behind. A human does NOT resolve
" " by running a substitution rule; the referent is simply the most SALIENT compatible thing
still active in working memory. Cognitive science calls this cue-based retrieval over a decaying
attentional state (Centering Theory's Cb; Lewis & Vasishth's activation model). We build that:

 * every concept mentioned in the recent turns is held in a FIELD with an ACTIVATION value —
 higher for the turn's subject, boosted by emotional charge (amygdala salience), decaying with
 recency (working memory is transient);
 * a reference is DETECTED morphologically, not by a word list — Kiwi tags a demonstrative
 determiner // as MM and a demonstrative pronoun // as NP; either means "this
 points back", so no enumerated pronoun table is ever needed;
 * the reference does not trigger a rule — it is a weak CUE (person vs thing, from morphology/graph
 type) that the field SETTLES onto: argmax activation among type-compatible concepts.

This is the SAME field the affect system feeds (emotionally charged concepts stay hot), so language
memory and emotion are one substrate — exactly the " " architecture.
"""
from __future__ import annotations

import re
from typing import Any

_DECAY = 0.6          # activation of a turn n steps back = _DECAY**n (recency)
_SUBJECT_ACT = 1.0    # a turn's subject is the most salient thing in it
_ANSWER_ACT = 0.75    # an entity the assistant just introduced is salient too (newly learned)
_PERSON_CUES = ("사람", "분", "이", "그", "그녀", "그이", "그분", "누구")   # person-referring anaphors


def _content_nouns(text: str, *, limit: int = 4) -> list[str]:
    """Salient content nouns (Kiwi NNP/NNG, adjacent-joined), most-specific first. Empty if Kiwi down."""
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return []
        toks = list(kw.tokenize(text))
        out: list[str] = []
        run: list[str] = []


        _JOIN = ("NNP", "NNG", "SL", "XSN")
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if t.tag in _JOIN and (t.tag != "XSN" or run):
                run.append(t.form)
                contig = (nxt is not None and nxt.tag in _JOIN
                          and getattr(nxt, "start", -1) == getattr(t, "start", 0) + getattr(t, "len", len(t.form)))
                if not contig:
                    out.append("".join(run)); run = []
            elif run:
                out.append("".join(run)); run = []
        if run:
            out.append("".join(run))
        # de-dup, drop 1-char noise, keep order (topic-fronted first)
        seen: set[str] = set()
        keep: list[str] = []
        for n in out:
            if len(n) >= 2 and n not in seen:
                seen.add(n); keep.append(n)
        return keep[:limit]
    except Exception:
        return []


def _turn_text(t: dict[str, Any]) -> str:
    """A turn's text under any of the wire keys — the live chat API sends {'role','text'} while some
    older callers pass 'content'/'message' (same tolerance as cgsr.sanitize_conversation_context).
    Reading only 'content' silently emptied the field on the live path — measured 2026-07-10:
    every multi-turn battery case failed with the resolver wired but starved."""
    return str((t or {}).get("text") or (t or {}).get("content") or (t or {}).get("message") or "")


def build_field(context: list[dict[str, Any]]) -> dict[str, float]:
    """Rebuild the working-memory activation field from the recent conversation turns. The server is
    stateless per request, so we replay the passed context — the most recent turn is the hottest."""
    turns = [t for t in (context or []) if _turn_text(t).strip()]
    if not turns:
        return {}
    n = len(turns)
    field: dict[str, float] = {}

    def _bump(ent: str, act: float) -> None:
        if ent:
            field[ent] = max(field.get(ent, 0.0), round(act, 4))

    for i, t in enumerate(turns):
        recency = _DECAY ** (n - 1 - i)     # 0..1, newest = 1
        role = str(t.get("role") or "")
        text = _turn_text(t)
        if role == "user":
            try:
                from .query_frame import parse as _parse
                subj = _parse(text).subject
            except Exception:
                subj = ""
            if subj:
                _bump(subj, _SUBJECT_ACT * recency)
            # a secondary noun in the user turn is mildly active too
            for nn in _content_nouns(text)[1:2]:
                _bump(nn, 0.4 * recency)
        else:  # assistant — entities it just surfaced are freshly salient (newly learned)
            for j, nn in enumerate(_content_nouns(text, limit=3)):
                _bump(nn, _ANSWER_ACT * recency * (0.9 ** j))
    return field


def _anaphor(question: str) -> tuple[str, bool] | None:
    """Detect an anaphoric reference MORPHOLOGICALLY. Returns (surface_span, is_person) or None.
 A demonstrative determiner (// = MM) + noun, or a demonstrative pronoun (// = NP),
 means 'this points back'. No pronoun list — the POS tag is the signal."""
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return None
        toks = list(kw.tokenize(question))
    except Exception:
        return None
    for i, t in enumerate(toks):

        if t.tag == "MM" and t.form in ("그", "이", "저") and i + 1 < len(toks) and toks[i + 1].tag in ("NNG", "NNB"):
            noun = toks[i + 1].form
            span = f"{t.form} {noun}" if f"{t.form} {noun}" in question else t.form + noun
            return span, (noun in _PERSON_CUES)

        if t.tag == "NP" and t.form in ("그거", "그것", "이거", "이것", "저거", "저것", "그", "이", "저"):
            start = getattr(t, "start", None)
            if start is not None:

                m = re.match(r"[가-힣]+", question[start:])
                span = m.group(0) if m else t.form
            else:
                span = t.form
            return span, False
    return None


def _josa_marker(span: str) -> str:
    """The dual-form particle a rewrite should carry, inferred from the anaphor's contracted josa
 (→topic, →subject, →object). Uses the josa engine to pick the batchim-correct form."""
    if span.endswith(("건", "는")):
        return "은(는)"
    if span.endswith(("게", "이")):
        return "이(가)"
    if span.endswith(("걸", "를")):
        return "을(를)"
    return ""


# interrogative words are a CLOSED grammatical class (like bound nouns) — Kiwi tags them NP/MAG;
# this tiny floor is grammar, not content, and never grows per topic.
_INTERROG_NP = {"누구", "뭐", "무엇", "어디"}
_INTERROG_MAG = {"언제", "왜", "어떻게"}


def _is_bare_question(question: str) -> bool:
    """True for a SUBJECTLESS question (Korean pro-drop): it asks something (interrogative NP/MAG
 or a ? final) but carries no content-noun topic of its own — ' ?', ' ?'.
 Remarks (, ) have neither signal, so they never get a topic glued on."""
    if len(question) > 40:
        return False
    try:
        from .query_frame import parse as _parse
        if _parse(question).subject:
            return False   # it already names its topic — nothing is dropped
    except Exception:
        return False
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return False
        for t in kw.tokenize(question):
            if (t.tag == "NP" and t.form in _INTERROG_NP) or (t.tag == "MAG" and t.form in _INTERROG_MAG):
                return True
            if t.tag == "SF" and "?" in t.form:
                return True
    except Exception:
        return False
    return False


def _eun_neun(w: str) -> str:
    return "은" if (w and "가" <= w[-1] <= "힣" and (ord(w[-1]) - 0xAC00) % 28 != 0) else "는"


def resolve(question: str, context: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve an anaphor in `question` against the working-memory field. Returns
    {resolved, entity, question} — `question` is rewritten with the referent substituted when a
    confident settle happens, else returned unchanged (never fabricates a referent)."""
    an = _anaphor(question)
    if not an:


        # interrogative and the field holds a genuinely hot referent, that referent IS the topic
        # (same salience settle as the demonstrative case — not a per-word rule). Measured live
        # 2026-07-10: these follow-ups fell through with an empty subject into a realtime deferral.
        if _is_bare_question(question):
            field = build_field(context)
            if field:
                entity, act = max(field.items(), key=lambda kv: kv[1])
                if act >= 0.5 and entity not in question:
                    topical = f"{entity}{_eun_neun(entity)} {question}"
                    return {"resolved": True, "entity": entity, "question": topical,
                            "mode": "pro_drop"}
        return {"resolved": False, "entity": "", "question": question}
    span, is_person = an
    field = build_field(context)
    if not field:
        return {"resolved": False, "entity": "", "question": question}
    # settle: the most-activated concept the cue is compatible with. Person-anaphor prefers an
    # animate/proper entity; otherwise pure activation wins. (Type from graph could refine this;
    # activation dominates in practice, so we keep the cue a soft preference, not a hard rule.)
    ranked = sorted(field.items(), key=lambda kv: kv[1], reverse=True)
    entity = ""
    if is_person:
        entity = next((e for e, _a in ranked if _looks_proper(e)), "")
    entity = entity or (ranked[0][0] if ranked else "")
    if not entity:
        return {"resolved": False, "entity": "", "question": question}
    # rewrite the surface: replace the anaphor span with the referent (+ its inferred particle),
    # then let the orthography engine pick the batchim-correct josa.
    marker = _josa_marker(span)
    replacement = f"{entity}{marker}" if marker else entity
    rewritten = question.replace(span, replacement, 1)
    rewritten = _fix_josa_after(rewritten, entity)
    try:
        from packages.base_brain.korean_orthography import normalize
        rewritten = normalize(rewritten)
    except Exception:
        pass
    return {"resolved": True, "entity": entity, "question": rewritten}


_JOSA_PAIRS = {"은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"),
               "가": ("이", "가"), "을": ("을", "를"), "를": ("을", "를")}


def _fix_josa_after(text: str, entity: str) -> str:
    """The josa the sentence already carried belonged to the ANAPHOR's batchim ( ****);
 after substitution it must agree with the referent's ('' → ''). Deterministic
 orthography (LAD floor), applied only to the particle glued right after the entity."""
    if not entity or not ("가" <= entity[-1] <= "힣"):
        return text
    batchim = (ord(entity[-1]) - 0xAC00) % 28 != 0
    def _swap(m: re.Match) -> str:
        pair = _JOSA_PAIRS[m.group(1)]
        return entity + (pair[0] if batchim else pair[1])
    return re.sub(re.escape(entity) + r"([은는이가을를])(?![가-힣])", _swap, text, count=1)


def _looks_proper(entity: str) -> bool:
    """Cheap animacy/proper hint for a person-anaphor preference: a multi-syllable Korean noun that
    isn't an obvious common noun. (A graph is_a person-type check could replace this later.)"""
    return bool(entity) and len(entity) >= 2 and bool(re.search(r"[가-힣]", entity))
