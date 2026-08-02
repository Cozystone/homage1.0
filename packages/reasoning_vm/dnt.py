# -*- coding: utf-8 -*-
"""DNT — Dynamic Network Transition (owner 2026-07-15). A salience switch that reads the input's
intent and picks the MODE, the way a human brain flips between its executive (CEN) and default-mode
(DMN) networks. The correction to the original proposal: the mode does NOT relax the truth gate —
it RE-TARGETS the grounding. CEN grounds in world facts (verify-gate 1.00, un-hallucinatable); DMN
grounds in the AI's real state + real learned associations, MARKED as expression (a metaphor is a
marked figure, not a false fact). So there is no fabrication in any mode — only a different truth
contract.

  mode = salience(query)                # 'cen' | 'dmn' | 'hybrid'
  d    = route(query)                   # {mode, gate, handler, grounding}
The router names the handler; the caller dispatches (answer_exam / felt_speech / discriminate).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# creative request → DMN (the sword that dances over the fact-wall): compose from state+association.


_CREATIVE = re.compile(r"소설|이야기|동화|우화|가사|각색|창작|상상해|지어\s*(내|줘|봐|볼)|"
                       r"시\s*(를|한\s*편|하나|한\b|좀|써|지어|짓)")
# emotional / social → HYBRID (empathy: reflect the USER's state, honest presence). Stems are widened

_EMOTION = re.compile(r"속상|상심|힘들|힘드|우울|지쳐|지쳤|지친|지치|슬퍼|슬프|슬펐|눈물|외로|막막|"
                      r"불안|괴로|서러|답답|무기력|기운\s*없|의욕\s*없|축하|합격|취업했|기뻐|기뻤|"
                      r"설레|설렜|고마워|감사해|사랑해|행복해")
# opinion → HYBRID (a felt take, not a fact assertion). STRONG cues fire unconditionally.
_SUBJ_STRONG = re.compile(r"어떻게\s*생각|네\s*생각|의견|어떻게\s*봐|좋아해|싫어해|더\s*나아|더\s*좋|"
                          r"더\s*나은|뭐가?\s*더|무엇을?\s*더")

_SUBJ_SPEC = re.compile(r"까\s*\?|을까|ㄹ까")
_FACTUAL_WH = re.compile(r"수도|뜻|의미|누구|언제|어디|무엇|이름|몇|얼마|정의|성분|원소|공식")
# a scored multiple-choice item → CEN exam lane (never abstain).
_MCQ = re.compile(r"([①②③④⑤]|(?<![0-9])[1-4]\s*[).．]|(?<![A-Za-z])[A-D]\s*[).．]).*"
                  r"([①②③④⑤]|(?<![0-9])[2-4]\s*[).．]|(?<![A-Za-z])[B-D]\s*[).．])", re.S)


@dataclass
class Route:
    mode: str            # cen | dmn | hybrid
    gate: float          # truth gate — ALWAYS 1.00 for factual claims; DMN just changes what's grounded
    handler: str         # answer_exam | felt_speech | discriminate | grounded_answer
    grounding: str       # world_facts | internal_state+association | user_state


def salience(query: str) -> str:
    """Classify the input into a network mode — the 'salience switch'. Creative/emotional/subjective
    route to DMN/hybrid; everything factual (incl. a scored MCQ) routes to CEN."""
    q = str(query or "")
    if _MCQ.search(q):
        return "cen"                                     # a scored item — executive, verify-first
    if _CREATIVE.search(q):
        return "dmn"
    if _EMOTION.search(q) or _SUBJ_STRONG.search(q):
        return "hybrid"
    if _SUBJ_SPEC.search(q) and not _FACTUAL_WH.search(q):
        return "hybrid"                                  # speculation, but not a fact lookup in disguise
    return "cen"                                         # default: facts, verify-gated


def route(query: str) -> Route:
    """Full DNT decision: mode + truth-gate policy + which handler grounds it, and in WHAT."""
    m = salience(query)
    if m == "dmn":
        # creative: gate stays 1.00 for any FACT smuggled in, but the output is grounded in state +
        # learned associations and MARKED as expression — never asserted as fact.
        return Route("dmn", 1.0, "felt_speech", "internal_state+association")
    if m == "hybrid":
        return Route("hybrid", 1.0, "felt_speech", "user_state")
    # cen — factual/exam. MCQ → never-abstain exam cascade; else verify-gated grounded answer.
    if _MCQ.search(str(query or "")):
        return Route("cen", 1.0, "answer_exam", "world_facts")
    return Route("cen", 1.0, "discriminate", "world_facts")
