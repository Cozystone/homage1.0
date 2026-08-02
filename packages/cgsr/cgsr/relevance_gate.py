# -*- coding: utf-8 -*-
"""Universal answer-fit gate — the check-before-speaking organ the owner asked for.

Owner (2026-07-20): "왜 자꾸 정의를 내뱉지? 말을 내뱉기 전에 맥락 검토하는 시스템이 없나?" Measured
root cause: when no lane understands an input, the cascade's last fallback is keyword retrieval —
grab ANY token it knows ("its" in a control-task spec) and recite a definition. The engine never asks
the one question a speaker must ask before speaking: does my candidate answer actually address what
was asked?

This gate asks exactly that, for EVERY answer, at the single exit point. It is not a 21st mode-switch:
it runs on every request and passes silently when the answer fits. It adds no comprehension — it adds
the SELF-KNOWLEDGE of non-comprehension (voice-or-silence enforced globally): a strong mismatch ships
an honest comprehension-limit reply instead of confident nonsense.

General signals only (no test-specific rules):
  1. FOCUS: the ask's content terms (closed-class function words excluded — grammar, not content).
  2. ANCHOR MISMATCH: answer shares zero content terms with a substantive ask -> it answered
     something else (the "its" -> possessive-determiner case scores exactly here).
  3. PARROT: the answer's terms are almost entirely a subset of the ask's terms -> it echoed the
     input instead of answering (the personal-recall regurgitation case).
Asks with no substantive focus (greetings, chatter, arithmetic) skip the gate — nothing to mismatch.
"""
from __future__ import annotations

import re

# closed-class function words + hyper-common verbs. Grammar-status list (like the josa engine),
# not knowledge: these can never be the SUBSTANCE a real answer is about.
_FUNCTION = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "will", "would",
    "can", "could", "shall", "should", "may", "might", "must", "have", "has", "had", "not", "no",
    "yes", "it", "its", "itself", "he", "she", "they", "them", "his", "her", "their", "you", "your",
    "yours", "we", "our", "ours", "i", "me", "my", "mine", "who", "whom", "whose", "which", "what",
    "when", "where", "why", "how", "of", "in", "on", "at", "to", "from", "with", "within", "into",
    "onto", "by", "for", "as", "about", "between", "during", "before", "after", "above", "below",
    "up", "down", "out", "off", "over", "under", "again", "once", "here", "there", "all", "each",
    "few", "more", "most", "some", "any", "both", "such", "only", "own", "same", "so", "too",
    "very", "just", "also", "per", "via", "one", "two", "three", "four", "five", "several",
    "tell", "say", "said", "give", "know", "please", "let", "get", "make", "made", "use", "used",
    "using", "return", "reply", "answer", "explain", "describe", "produce", "provide", "receive",
    "following", "between", "each", "every", "while", "shown", "called",
}
_WORD = re.compile(r"[A-Za-z][A-Za-z\-']{1,}")


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")
            if len(w) > 2 and w.lower() not in _FUNCTION}


def _stem_hit(a: set[str], b: set[str]) -> int:
    """Overlap tolerant to inflection: exact hits plus 5-char-prefix hits (minimize/minimizing)."""
    exact = a & b
    pa = {w[:5] for w in a if len(w) >= 5}
    pb = {w[:5] for w in b if len(w) >= 5}
    return len(exact) + len((pa & pb)) - len({w[:5] for w in exact if len(w) >= 5} & pa & pb)


def extract_ask(text: str, n: int = 140) -> str:
    """B-v0 seed: name what the text asks for — an explicit imperative/format line when present
    ('Return only …', 'you must …', 'reply with exactly …'), else the first sentence."""
    t = " ".join((text or "").split())
    # priority: an explicit format/goal contract names the ask better than a scene-setting "you will"
    for pat in (r"return only[^.]{0,120}", r"reply with exactly[^.]{0,80}",
                r"your (?:job|objective|task) is[^.]{0,120}", r"submit[^.]{0,120}",
                r"you (?:must|are to)[^.]{0,120}", r"you will[^.]{0,120}"):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return m.group(0)[:n].rstrip(" ,.;:")
    return re.split(r"(?<=[.!?])\s", t, 1)[0][:n].rstrip(" ,.;:")


def answer_fit(question: str, answer: str, answer_kind: str | None = None) -> dict:
    """Verdict for one (ask, candidate answer). fits=True -> ship as-is. fits=False -> the caller
    must not ship it (replace with the honest comprehension-limit reply)."""
    q_terms = _terms(question)
    if len(q_terms) < 3:                       # no substantive focus (greeting/chatter/arithmetic)
        return {"fits": True, "reason": "no_substantive_focus"}
    a_all = {w.lower() for w in _WORD.findall(answer or "")}
    a_terms = _terms(answer)
    if not a_terms:
        return {"fits": True, "reason": "answer_has_no_content"}     # refusals/acks — not our call
    overlap = _stem_hit(q_terms, a_terms)
    # PARROT: nearly all answer content comes from the ask itself -> echo, not an answer
    if len(a_terms) > 12 and len(a_terms & q_terms) / len(a_terms) > 0.8:
        return {"fits": False, "reason": "parrot_echo", "overlap": overlap}
    # ANCHOR MISMATCH: substantive ask, zero content overlap -> it answered something else entirely
    if overlap == 0:
        return {"fits": False, "reason": "no_focus_overlap", "overlap": 0}
    return {"fits": True, "reason": "overlap", "overlap": overlap}


def honest_limit_reply(question: str) -> str:
    """The voice-or-silence surface: name what was read, refuse to fake it, invite a smaller ask.
    No fabrication, no filler-definition."""
    ask = extract_ask(question)
    return (f"I have to be honest: I don't understand this well enough to answer it properly. "
            f"It reads to me as asking — \"{ask}\" — and I can't yet carry that out faithfully, "
            f"so I won't cover the gap with something merely related. If you give me a smaller "
            f"piece of it, I'll tell you exactly which part I can and can't do.")
