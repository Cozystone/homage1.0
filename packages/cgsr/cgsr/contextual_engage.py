# -*- coding: utf-8 -*-
"""One context-aware engagement decision — NOT three separate mode-switches.

Owner's standing correction (2026-07-20): "다중턴을 실행할 때만 저 엔진을 켜는 건 규칙기반이랑 다를 게
없다. 결국 하나의 '모델'로 통합되어야 한다." He is right. The engine had THREE separate post-hoc
override branches in the answer cascade — discourse_participation, opinion_engage, conversational_engage
— each an `if <detected>: replace the answer` rule. Three mode-switches wearing one coat.

This module collapses that selection into ONE function: the model reads the FULL context (the request's
conversation, the question's shape, whether its own first answer was an abstention) and decides, in a
single place, HOW to engage — contribute to a live discussion, weigh a subjective comparison, or engage
a conversational turn it would otherwise punt on. The three existing composers are reused as generation
PRIMITIVES; what is unified is the perception+decision. It is not "an engine turned on for debates" —
it runs for every request and simply returns None when no engagement is warranted (then the normal
answer stands). That is the difference between context-awareness (always on, yields nothing when moot)
and a mode-switch (a flag that flips a second engine on).

Honest scope: this unifies the ENGAGEMENT family (the three lanes above), not the whole ~20-branch
answer cascade — full convergence onto one grounded generator is the north star, done incrementally.
Hallucination-0 is preserved: each primitive already grounds or abstains; this only chooses among them.
"""
from __future__ import annotations

from typing import Any, Callable

from .discourse_participation import parse_discussion, contribute
from .opinion_engage import compose as opinion_compose


def contextual_engage(
    question: str,
    conversation_context: list[dict] | None,
    *,
    shape: str = "",
    current_answer: str = "",
    is_abstention: bool = False,
    current_kind: str | None = None,
    language: str = "en",
    shape_engage_fn: Callable[[str, str], str] | None = None,
) -> dict[str, Any] | None:
    """The single engagement decision. Returns {answer, answer_kind, confidence} or None.

    Priority reflects specificity of the perceived context, not a hardcoded pipeline of engines:
      1. a live multi-party discussion  -> contribute a free, grounded, other-responsive turn;
      2. a subjective comparison        -> weigh the trade-off (never a fact-dump or a deflection);
      3. a conversational turn the model would otherwise abstain on -> engage by its shape.
    Each step consults REAL context; when none applies it yields None and the normal answer stands.
    """
    # 1) Perceive an ongoing discussion (the request carries Topic:/Speaker turns). Reason about the
    #    arguments actually stated; free-argument structure + hallucination gate live inside contribute.
    disc = parse_discussion(conversation_context or [])
    if disc:
        contrib = contribute(disc, turn_index=len(disc["prior_turns"]))
        if contrib:
            return {"answer": contrib, "answer_kind": "discourse_participation", "confidence": 0.6}

    # 2) Perceive a SUBJECTIVE comparison ('X better/matters more than Y'); factual comparatives are
    #    excluded inside opinion_compose, so this never overrides a real factual comparison.
    opinion = opinion_compose(question)
    if opinion and current_kind not in ("greeting", "reasoning_vm") \
            and "(sources:" not in (current_answer or "").lower():
        return {"answer": opinion, "answer_kind": "opinion_engage", "confidence": 0.6}

    # 3) A conversational turn (causal/advice/opinion/personal) the model punted on -> engage, don't
    #    dead-end. Only when the current answer is a cold abstention and nothing better already fired.
    if is_abstention and shape in ("causal", "advice", "opinion", "personal") \
            and current_kind not in ("greeting", "concept_comparison", "reasoning_vm") \
            and shape_engage_fn is not None:
        return {"answer": shape_engage_fn(shape, language),
                "answer_kind": "conversational_engage", "confidence": 0.55}

    return None
