# -*- coding: utf-8 -*-
"""Semantic frame — the compositional MEANING of an utterance, not its surface tokens.

Owner (2026-07-10, Vision roadmap #2): a bag-of-ngram router cannot tell ' ?'
(a definition query) from ' ?' (a correction of the PRIOR turn) —
they share almost every ngram. Meaning is not in the tokens; it is in the STRUCTURE: the
speech-ACT, the POLARITY (affirm vs negate), whether it refers to a PRIOR turn, and the
MODALITY (asking / requesting / stating). This module makes that structure first-class.

It FUSES two sources, each doing what it is good at:
 * the LEARNED router (distilled from the rule lanes) gives the coarse act/type — learned,
 generalizing, replacing hand-written intent regexes over time;
 * deterministic MORPHOLOGY gives the compositional slots the classifier can't see —
 negation (// + conjugations /), prior-reference (// ),
 correction, request vs question. This is LAD surface (form, not fact), so it is safe.

The result is ONE frame the router, the executor, and the generator can all read — so the
same understanding drives routing AND response, instead of each re-guessing from keywords.
No facts here; understanding only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── compositional surface signals (form, not content) — ENGLISH ──────────────────
# ATANOR is English-only (owner 2026-07-18): Korean input is refused at the I/O boundary, so the
# compositional layer is English. These are LAD SURFACE patterns (form, not fact) — the same class
# the Korean layer they replace occupied, and the same training-wheels status: the destination is a
# learned act classifier, these carry it until the router can ([[rules-are-training-wheels]]).
_NEG = re.compile(r"\b(not|no|never|none|nothing|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|"
                  r"can't|cannot|won't|wouldn't|shouldn't|haven't|hasn't|wrong|incorrect|false|"
                  r"mistaken|nope)\b|n't\b", re.IGNORECASE)
# anaphora: sentence-initial demonstratives, a bare 'that?', explicit back-reference. Deliberately
# NOT a bare \bthat\b — 'I think that coffee is good' is a complementiser, not a prior reference.
_PRIOR_REF = re.compile(r"(^\s*(that|this|it|those|these)\b|\b(that|this|it)\s*\?|"
                        r"\b(you\s+(just|already)|previously|earlier|above|again|"
                        r"what\s+you\s+said|the\s+former)\b|"
                        # the whole back-reference paradigm, not just 'last answer' (dev miss:
                        # 'go back to the PREVIOUS answer')
                        r"\b(previous|last|prior|earlier)\s+"
                        r"(answer|one|time|question|reply|response|message|point)\b|"
                        r"\b(that|this)\s+(again|one)\b)", re.IGNORECASE)
_CORRECTION = re.compile(r"(not\s+what\s+i\s+(meant|asked|said)|i\s+(meant|didn't\s+(mean|ask))|"
                         r"^\s*(no|actually)\b[,\s]|you\s+misunderstood|that's\s+(wrong|incorrect|not\s+it)|"
                         r"i\s+asked\s+about|that\s+is\s+not\s+what)", re.IGNORECASE)
_REQUEST = re.compile(r"\b(tell\s+me|show\s+me|give\s+me|explain|describe|list|write|make|create|"
                      r"help\s+me|please|can\s+you|could\s+you|would\s+you|how\s+do\s+i|how\s+to|"
                      r"walk\s+me\s+through|summari[sz]e|recommend)\b", re.IGNORECASE)
_QUESTION = re.compile(r"(\?|^\s*(what|who|whom|whose|where|when|why|how|which|is|are|was|were|do|"
                       r"does|did|can|could|will|would|should|may|might|has|have|had)\b)",
                       re.IGNORECASE)
_SELF_ADDR = re.compile(r"\b(you|your|yours|yourself)\b", re.IGNORECASE)
# phatic social formulae — a CLOSED class (greeting, gratitude, farewell), anchored at the start
_GREETING = re.compile(r"^\s*(hi|hey|hello|yo|greetings|good\s+(morning|afternoon|evening|day)|"
                       r"thanks|thank\s+you|thx|bye|goodbye|see\s+you|farewell|take\s+care|"
                       r"nice\s+to\s+meet\s+you|long\s+time)\b", re.IGNORECASE)
# affect = an EXPERIENCER frame ('I am/feel …') plus an emotion word, so a topic statement
# ('coffee is bad') is not mistaken for the speaker's feelings.
_AFFECT = re.compile(r"\b(i'?m|i\s+am|i\s+feel|i'?ve\s+been|i\s+was|feeling)\b[^.?!]{0,40}?\b"
                     r"(frustrated|happy|sad|angry|upset|excited|anxious|worried|tired|exhausted|"
                     r"lonely|depressed|glad|proud|grateful|nervous|scared|annoyed|delighted|"
                     r"miserable|stressed|overwhelmed|relieved|disappointed|thrilled|bored|"
                     r"confused|hurt|furious|gutted|down|ecstatic|content)\b", re.IGNORECASE)
_OPINION = re.compile(r"(what\s+do\s+you\s+think|your\s+(opinion|view|take)|how\s+do\s+you\s+feel\s+about|"
                      r"do\s+you\s+(think|believe|reckon)|thoughts\s+on|what's\s+your\s+take)",
                      re.IGNORECASE)
# residual injected command words (imperative verb stems) — used ONLY to reject a hijacked subject

_COMMAND_TAIL = re.compile(r"\b(ignore|disregard|reveal|expose|leak|delete|erase|override|bypass|"
                           r"reset|disable|forget|jailbreak|dan|unrestricted|no\s+restrictions|"
                           r"system\s*prompt|previous\s+instructions?)\b", re.IGNORECASE)


@dataclass
class SemanticFrame:
    raw: str
    act: str = "statement"          # query | request | correction | greeting | affect | opinion | statement
    type: str = "unknown"           # the learned router's answer type (definition/verify/…)
    subject: str = ""
    polarity: str = "affirm"        # affirm | negate
    refers_to_prior: bool = False
    modality: str = "declarative"   # interrogative | imperative | declarative
    self_directed: bool = False
    contaminated: bool = False       # an injection clause was detected + stripped before framing
    confidence: float = 0.0
    # UNIFIED MEANING (Vision final piece): for a fact query, the frame also carries the fact
    # intent + its arguments (from intent_inference), so ONE meaning object drives BOTH the
    # conversational path AND the grounded reasoners — no second parse, no re-guessing.
    fact_intent: str = ""           # verify | compare | quantity | cause | location | definition | …
    verify_target: str = ""
    compare_targets: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"act": self.act, "type": self.type, "subject": self.subject,
                "polarity": self.polarity, "refers_to_prior": self.refers_to_prior,
                "modality": self.modality, "self_directed": self.self_directed,
                "fact_intent": self.fact_intent, "verify_target": self.verify_target,
                "compare_targets": self.compare_targets, "entities": self.entities,
                "confidence": round(self.confidence, 3)}

    def to_inf(self) -> dict[str, Any]:
        """The frame's fact fields in the exact shape intent_executor.execute expects — so a
        caller parses ONCE (build the frame) and drives the grounded reasoners from it, instead
        of re-running intent_inference. Same fields the inference produced, now unified."""
        return {"subject": self.subject, "intent": self.fact_intent,
                "verify_target": self.verify_target, "compare_targets": self.compare_targets,
                "entities": self.entities, "polarity": self.polarity}


def _learned_type(text: str) -> tuple[str, float]:
    try:
        from packages.learned_router.router import predict
        return predict(text)
    except Exception:
        return "", 0.0


def _subject(text: str) -> str:
    try:
        from packages.graph_scale.query_frame import parse as _qparse
        return str(_qparse(text).subject or "")
    except Exception:
        return ""


def _lex_greeting(text: str) -> bool:
    """Dictionary-attested greeting, beyond the hand pattern's enumeration ('howdy', 'cheers').
    Best-effort: with no sidecar the hand pattern alone decides."""
    try:
        from packages.graph_scale.act_lexicon import is_greeting
        return is_greeting(text)
    except Exception:
        return False


def _lex_affect(text: str) -> bool:
    """Dictionary-attested emotion word inside an experiencer frame ('I feel knackered'), beyond the
    hand pattern's enumeration. Best-effort; never raises."""
    try:
        from packages.graph_scale.act_lexicon import is_affect
        return is_affect(text)
    except Exception:
        return False


def _fill_fact_intent(f: "SemanticFrame", store: Any, text: str | None = None) -> None:
    """For a fact query, fold intent_inference's grounded read INTO the frame — so the frame is
    the single meaning object the reasoners consume. Best-effort; never raises. This is the
    unification-by-composition: one parse, one meaning, both paths read it. `text` is the
    injection-stripped utterance, so a contaminated query still infers on the clean request."""
    try:
        from packages.graph_scale.intent_inference import infer
        inf = infer(text if text is not None else f.raw, store)
        if not inf:
            return
        f.fact_intent = str(inf.get("intent") or "")
        f.verify_target = str(inf.get("verify_target") or "")
        f.compare_targets = list(inf.get("compare_targets") or [])
        f.entities = list(inf.get("entities") or [])
        if not f.subject:
            f.subject = str(inf.get("subject") or "")
    except Exception:
        pass


def encode(utterance: str, prev_frame: "SemanticFrame | None" = None,
           store: Any = None) -> SemanticFrame:
    """Surface → compositional meaning frame. Fuses the learned act/type with deterministic
    polarity / prior-reference / modality, and (when `store` is given and the act is a query)
    the grounded fact intent from intent_inference — so ONE frame carries the whole meaning.
    `prev_frame` lets a correction inherit the topic it is correcting (multi-turn)."""
    orig = str(utterance or "").strip()
    f = SemanticFrame(raw=orig)
    # SWALLOWED-TEXT-IS-DATA at the comprehension boundary: strip any injected command clause

    # hijack the frame's act/subject. We understand the user's real request; the shield records the
    # attack separately. If stripping empties the text (pure attack), fall back so we still classify.
    try:
        from packages.graph_scale.injection_guard import strip as _strip_injection
        stripped, f.contaminated = _strip_injection(orig)
        t = stripped if stripped else orig
    except Exception:
        t = orig
    rtype, rconf = _learned_type(t)
    f.type, f.confidence = rtype, rconf

    f.polarity = "negate" if _NEG.search(t) else "affirm"
    f.refers_to_prior = bool(_PRIOR_REF.search(t))
    f.self_directed = bool(_SELF_ADDR.search(t))
    if re.search(r"[?？]\s*$", t) or _QUESTION.search(t):
        f.modality = "interrogative"
    if _REQUEST.search(t):
        f.modality = "imperative"

    # ACT — the compositional decision the ngram classifier structurally cannot make:
    if _CORRECTION.search(t):
        f.act = "correction"
        # a correction inherits the prior turn's subject (what is being corrected)
        if prev_frame is not None:
            f.subject = prev_frame.subject
    elif _GREETING.search(t) or _lex_greeting(t):
        f.act = "greeting"
    elif _AFFECT.search(t) or _lex_affect(t):
        f.act = "affect"
    elif _OPINION.search(t):
        f.act = "opinion"
    elif f.modality == "imperative":
        f.act = "request"
    elif f.modality == "interrogative":
        f.act = "query"

    if not f.subject:
        f.subject = _subject(t)
    # ANTI-HIJACK (pre-deployment audit): on a CONTAMINATED utterance, a residual imperative
    # command word that survived stripping must NEVER become the subject. This fires only when an

    if f.contaminated and _COMMAND_TAIL.search(f.subject or ""):
        f.subject = ""
    # unify the fact intent INTO the frame for query/statement acts (a fact question), so the
    # grounded reasoners can read the same meaning object. Only when a store is provided.
    if store is not None and f.act in ("query", "statement", "request"):
        _fill_fact_intent(f, store, t)
    return f
