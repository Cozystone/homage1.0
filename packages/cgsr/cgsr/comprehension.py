# -*- coding: utf-8 -*-
"""Unified perception front — ONE comprehension pass every input goes through, whose output the
whole pipeline consults.

Owner (2026-07-20): "낯선 텍스트를 읽고 상황모델을 세우는 게 아니라, 정교하게 맞물려 돌아가는 통합된
모델이 처리해야 하는 것 아닌가?" Right: comprehension must not be another bolted-on module — it is
the FRONT of the one pipeline. This module composes the organs that already exist (discussion
parsing, ask extraction, format-contract reading, content-focus analysis) into a single Understanding
object built ONCE per request. Decision points downstream (the discussion contribution, the
personal-recall precondition, the final fallback's right-to-speak) consult THIS shared understanding
instead of each keyword-matching the input on its own — that is what "맞물려 돌아간다" means in code.

The Understanding also carries what was NOT understood: `substantive` (is there real content to
address) and `focus` (the content terms an answer must engage). An organ that cannot engage the focus
has no right to speak on it — the structural end of the grab-a-keyword fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .discourse_participation import parse_discussion
from .relevance_gate import _terms, extract_ask


@dataclass
class Understanding:
    question: str
    focus: set[str] = field(default_factory=set)     # content terms an answer must engage
    substantive: bool = False                        # is there real content here at all
    ask_gist: str = ""                               # what the text asks for (imperative/contract)
    format_contract: str | None = None               # explicit output format demanded, if any
    discussion: dict | None = None                   # ongoing multi-party discussion state
    long_form: bool = False                          # spec/test-sheet-shaped input (novel structure)
    deliberation_grounding: dict | None = None       # System-2 typed grounding, span-traced from THIS
    #                                                   text (None unless a supported reasoning shape
    #                                                   is fully grounded — see deliberation_extractor)

    def engages(self, answer_terms: set[str]) -> bool:
        """Does a candidate answer engage this understanding's focus at all?"""
        if not self.substantive:
            return True
        return bool(self.focus & answer_terms)


def perceive(question: str, conversation_context: list[dict] | None = None) -> Understanding:
    """The one comprehension pass. Cheap, total, never raises; built once per request."""
    q = question or ""
    focus = _terms(q)
    blob = q
    for m in (conversation_context or []):
        if isinstance(m, dict):
            blob += "\n" + str(m.get("content", ""))
    u = Understanding(
        question=q,
        focus=focus,
        substantive=len(focus) >= 3,
        ask_gist=extract_ask(blob if len(q) < 40 else q),
        discussion=_safe_discussion(conversation_context, q),
        long_form=len(blob) > 600,
    )
    low = blob.lower()
    if "return only" in low:
        u.format_contract = "return_only"
    elif "reply with exactly" in low:
        u.format_contract = "reply_exactly"
    elif "json" in low and ("{" in blob or "format" in low):
        u.format_contract = "json"
    # SITUATION-FACT EXTRACTION (System-2 bridge): if THIS text is a supported reasoning shape whose
    # every needed fact is span-traceable IN the text, attach the deliberator's typed grounding so the
    # System-2 chain can bid on the real question. A non-reasoning input (or a shape missing a fact)
    # attaches nothing — the deliberator then bids None. Grounded extraction only; never fabricates.
    try:
        from packages.situation_model.deliberation_extractor import extract_grounding
        u.deliberation_grounding = extract_grounding(blob)
    except Exception:
        u.deliberation_grounding = None
    return u


def _safe_discussion(ctx, ask: str = "") -> dict | None:
    try:
        return parse_discussion(ctx or [], ask=ask)
    except Exception:
        return None
