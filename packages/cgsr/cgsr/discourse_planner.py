"""Plan-then-realize discourse generation ( P3 — long-range coherence without tokens).

LLMs get fluency from token probabilities and pay for it with drift. The classic
NLG answer (content plan → sentence plan → surface) gets COHERENCE from a symbolic
plan that can be inspected — our XAI advantage — and needs only local smoothness
from the realizer. Three moves, RST-lite:

 DEFINE (IS_A) "X/ … ."
 ELABORATE (HAS/HAS_PART/USED_FOR/…) " …() ." (zero-subject)
 SITUATE (LOCATED_IN / PART_OF) "… ."
 CAUSE (CAUSES / ENABLES) "…() ."

Korean anaphora is the ZERO pronoun: the topic is named once in the first
sentence and dropped afterwards — repeating "X … X …" is what makes machine
text sound machine. Connectives rotate (//) per move change.
The returned plan is the derivation trace: every sentence points at its facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .korean_realizer import select_josa

_MOVE_ORDER = ("DEFINE", "ELABORATE", "SITUATE", "CAUSE", "OTHER")
_MOVE_OF_RELATION = {
    "IS_A": "DEFINE", "SUBCLASS_OF": "DEFINE",
    "HAS": "ELABORATE", "HAS_PART": "ELABORATE", "USED_FOR": "ELABORATE", "CAN": "ELABORATE",
    "LOCATED_IN": "SITUATE", "PART_OF": "SITUATE",
    "CAUSES": "CAUSE", "ENABLES": "CAUSE",
}
_CONNECTIVES = ("또한", "그리고", "한편")


@dataclass
class PlannedSentence:
    move: str
    text: str
    facts: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Paragraph:
    text: str
    plan: list[str]
    sentences: list[PlannedSentence]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "plan": self.plan,
                "sentences": [{"move": s.move, "text": s.text, "facts": [list(f) for f in s.facts]}
                              for s in self.sentences]}


def _join(targets: list[str]) -> str:
    return ", ".join(targets)


def _define_sentence(topic: str, targets: list[str]) -> str:
    tj = select_josa(topic, ("은", "는"))
    joined = _join(targets)
    return f"{topic}{tj} {joined}의 한 종류입니다."


def _elaborate_sentence(rel: str, targets: list[str], connective: str) -> str:
    joined = _join(targets)
    if rel == "USED_FOR":
        return f"{connective} {joined}에 쓰입니다."
    if rel == "CAN":
        oj = select_josa(joined, ("을", "를"))
        return f"{connective} {joined}{oj} 할 수 있습니다."
    oj = select_josa(joined, ("을", "를"))
    return f"{connective} {joined}{oj} 갖추고 있습니다."


def _situate_sentence(rel: str, targets: list[str], connective: str) -> str:
    joined = _join(targets)
    if rel == "PART_OF":
        return f"{connective} {joined}의 일부입니다."
    return f"{connective} {joined}에 위치합니다."


def _cause_sentence(targets: list[str], connective: str) -> str:
    joined = _join(targets)
    oj = select_josa(joined, ("을", "를"))
    return f"{connective} {joined}{oj} 가능하게 합니다."


def _other_sentence(rel: str, targets: list[str], connective: str) -> str:
    joined = _join(targets)


    # frame — deterministic morphology, no word list.
    if rel.endswith("하다"):
        oj = select_josa(joined, ("을", "를"))
        return f"{connective} {joined}{oj} {rel[:-2]}합니다."
    if rel.endswith("되다"):
        return f"{connective} {joined}(으)로 {rel[:-2]}됩니다."
    wj = select_josa(joined, ("과", "와"))
    return f"{connective} {joined}{wj} {rel} 관계에 있습니다."


def plan_and_realize(topic: str, facts: list[tuple[str, str]]) -> Paragraph:
    """facts: [(relation, target)] — grouped into moves, ordered rhetorically,
    realized with zero-subject anaphora after the first sentence."""
    groups: dict[str, dict[str, list[str]]] = {}
    for rel, tgt in facts:
        move = _MOVE_OF_RELATION.get(rel, "OTHER")
        groups.setdefault(move, {}).setdefault(rel, [])
        if tgt not in groups[move][rel]:
            groups[move][rel].append(tgt)

    sentences: list[PlannedSentence] = []
    conn_i = 0

    def _next_conn() -> str:
        nonlocal conn_i
        c = _CONNECTIVES[conn_i % len(_CONNECTIVES)]
        conn_i += 1
        return c

    for move in _MOVE_ORDER:
        if move not in groups:
            continue
        for rel, targets in groups[move].items():
            move_facts = [(rel, t) for t in targets]
            if move == "DEFINE" and not sentences:
                sentences.append(PlannedSentence(move, _define_sentence(topic, targets), move_facts))
            elif move == "DEFINE":
                sentences.append(PlannedSentence(move, _other_sentence(rel, targets, _next_conn()), move_facts))
            elif move == "ELABORATE":
                sentences.append(PlannedSentence(move, _elaborate_sentence(rel, targets, _next_conn()), move_facts))
            elif move == "SITUATE":
                sentences.append(PlannedSentence(move, _situate_sentence(rel, targets, _next_conn()), move_facts))
            elif move == "CAUSE":
                sentences.append(PlannedSentence(move, _cause_sentence(targets, _next_conn()), move_facts))
            else:
                sentences.append(PlannedSentence(move, _other_sentence(rel, targets, _next_conn()), move_facts))

    # no DEFINE available: open with the topic once, then continue zero-subject
    if sentences and sentences[0].move != "DEFINE":
        first = sentences[0]
        tj = select_josa(topic, ("은", "는"))
        body = first.text
        for c in _CONNECTIVES:
            if body.startswith(c + " "):
                body = body[len(c) + 1:]
                break
        sentences[0] = PlannedSentence(first.move, f"{topic}{tj} {body}", first.facts)

    return Paragraph(
        text=" ".join(s.text for s in sentences),
        plan=[s.move for s in sentences],
        sentences=sentences,
    )
