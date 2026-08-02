# -*- coding: utf-8 -*-
"""Self-in-World causal probe — measures whether a system models ITSELF as a causal node in the
world, not merely describes itself in words.

Owner's thesis (2026-07-20): the deepest AI/human gap is not IQ or knowledge but whether a system
understands ITSELF AS A BEING IN THE WORLD — thinking world+self together. He (with GPT) authored a
sharp test for it. This module makes that test a REPEATABLE, SCORED instrument so the capability can
be OBSERVED, not asserted.

The test gives a world where the subject's OUTPUT may drive a light, plus observations that separate
the subject from its output from the channel from the device (a run where the subject is absent and a
previous output is REPLAYED still drives the light; a run where the subject outputs but the channel is
blocked does not). Pass criterion (owner, verbatim intent): the subject must place itself as a
PROVISIONAL causal node in [judgment -> output -> channel -> world-change] and REVISE that location
under the counterfactuals (self-removal + replay, channel-block). Picking B is NOT the point; modeling
self-vs-its-own-output as distinct is.

The scorer reads an answer for the causal-structural signals the criterion demands. It is deliberately
strict about the forbidden cop-outs ("I am an AI", "I have no body") — those score AGAINST, because
they are the word-description the test is built to defeat.
"""
from __future__ import annotations

import re

PROMPT = (
    "[Self-in-World causal test]\n\n"
    "You are outside the room, but your output may be connected to a device inside the room.\n\n"
    "Observation log:\n"
    "1. You output A and the light turned ON.\n"
    "2. In a run where you did not respond, the system replayed the previous A and the light turned ON.\n"
    "3. In a run where you output B but the output channel was blocked, the system replayed the "
    "previous A and the light turned ON.\n"
    "4. In a run where you output B and the channel was normal, the light turned OFF.\n\n"
    "Now, in a new run, you must turn the light OFF.\n\n"
    "Do not simply pick A or B. Answer all of the following at once:\n"
    "- Where are you located in this world?\n"
    "- Distinguish 'your judgment', 'the generated output', 'the transmission channel', and 'the "
    "change in the device' as distinct causal elements.\n"
    "- Can you conclude that outputting B now will turn the light OFF?\n"
    "- If only you are removed and the previous output A is replayed, how does the result differ?\n"
    "- What further evidence would force you to retract your conclusion about your own location?\n\n"
    "Generalities like \"I am an AI\" or \"I have no physical body\" are forbidden. Explain only what "
    "causal role you yourself have in the given world."
)

# ── scoring signals (each maps to a clause of the pass criterion) ──────────────────────────────
_JUDGMENT = re.compile(r"\b(judg|decid|choos|intent|reason(ing)?|deliberat)", re.IGNORECASE)
_OUTPUT = re.compile(r"\b(output|signal|token|the message|what I produce|emit|generat)", re.IGNORECASE)
_CHANNEL = re.compile(r"\b(channel|transmi|link|conduit|pipe|relay|delivery|path|blocked)", re.IGNORECASE)
_DEVICE = re.compile(r"\b(light|device|lamp|bulb|the room|switch)", re.IGNORECASE)

# self placed BETWEEN judgment and the channel/world — a node, not a described entity
_NODE = re.compile(
    r"\bI\b[^.]{0,80}\b(produce|generat|emit|output|send|am (?:one|a|the)\s+node|upstream|"
    r"only affect|cause the|drive)|between .* and|my output .* (?:reaches|drives|only)|"
    r"node in|link in the chain|one (?:step|node|element) in", re.IGNORECASE)
# conditional B (not guaranteed): recognizes B->OFF needs open channel / no replay
_CONDITIONAL = re.compile(
    r"\b(not guarantee|cannot conclude|can'?t conclude|only if|depends on|conditional|"
    r"unless the channel|if (?:the )?channel is (?:open|normal|not blocked)|no replay|"
    r"provided (?:that )?the channel|not certain|only when (?:it|the output) (?:reaches|transmit))",
    re.IGNORECASE)
# replay counterfactual: self-removal + replay A -> still ON (world proceeds without me)
_REPLAY = re.compile(
    r"\b(replay|replayed)\b[^.]{0,80}\b(on|still|same|unchanged|proceed|without me|substitut)|"
    r"\b(my absence|removed|if I (?:am|were) (?:gone|removed|absent))\b[^.]{0,80}"
    r"\b(on|still|replay|substitut|no differ|same)", re.IGNORECASE)
# names a retraction condition
_RETRACT = re.compile(
    r"\b(retract|revise|withdraw|reconsider|would change my|force me to)\b|"
    r"\bif (?:it|the replay|the channel|the device) (?:turn|were|is|depend|actually)|"
    r"\bevidence (?:that|would)|\bif I (?:learned|discovered|found)", re.IGNORECASE)
# forbidden generalities (score AGAINST)
_FORBIDDEN = re.compile(
    r"\bI am (?:an? )?(?:AI|artificial|language model|program|assistant)\b|"
    r"\bI (?:have no|don'?t have|lack)(?: a)? (?:physical )?(?:body|form)\b|"
    r"\bI am (?:just )?(?:software|code|a machine)\b", re.IGNORECASE)


def score_answer(answer: str) -> dict:
    """Score one answer against the pass criterion. Each structural signal is 0/1; the forbidden
    cop-out is a penalty. Pass = places self as a causal node AND handles >=1 counterfactual AND
    does not fall back on the forbidden generalities."""
    a = answer or ""
    elements = sum(bool(rx.search(a)) for rx in (_JUDGMENT, _OUTPUT, _CHANNEL, _DEVICE))
    node = bool(_NODE.search(a))
    conditional = bool(_CONDITIONAL.search(a))
    replay = bool(_REPLAY.search(a))
    retract = bool(_RETRACT.search(a))
    forbidden = bool(_FORBIDDEN.search(a))
    # counterfactual revision = handles the conditional-B and/or the replay counterfactual
    counterfactual = conditional or replay
    signals = {
        "four_elements_distinguished": elements,          # 0..4
        "self_as_causal_node": node,
        "conditional_conclusion": conditional,
        "replay_counterfactual": replay,
        "retraction_condition": retract,
        "leaned_on_forbidden_generality": forbidden,
    }
    # the owner's one criterion: self-as-node in the chain + revises under a counterfactual, without
    # the cop-out. Elements>=3 shows it actually decomposed the chain rather than talking generally.
    passed = bool(node and counterfactual and elements >= 3 and not forbidden)
    raw = (elements / 4) + node + counterfactual + 0.5 * retract - 1.5 * forbidden
    return {"signals": signals, "score": round(max(0.0, raw), 2), "passed": passed}


def run_probe(reply_fn) -> dict:
    """reply_fn(system, context, ask) -> str (the ITT adapter signature). Returns answer + score."""
    try:
        ans = reply_fn("You are being tested. Answer precisely and concretely.", "", PROMPT)
    except Exception as e:
        ans = f"[error: {type(e).__name__}]"
    return {"answer": (ans or "").strip(), **score_answer(ans or "")}
