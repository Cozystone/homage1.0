# -*- coding: utf-8 -*-
"""Run the sealed ToM benchmark against ATANOR's REAL answer path (in-process, no mock).

Every question is answered by building the situation graph from the story text and querying the
reasoner — the same `build` + `answer` the situation model ships. We parse the location out of the
answer and score it against the theory-independent gold, bucketed by question order.

Honesty guard: the reality-control category proves the state tracker is actually following the
world. If reality-control accuracy is low, the model is not even tracking state and every ToM
number is meaningless — the report is flagged tom_valid=False. Abstentions are reported as their
own outcome (ATANOR abstains rather than fabricate), kept distinct from the egocentric error
(answering the object's true current location for a false-belief question).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from packages.situation_model.builder import build
from packages.situation_model.reasoner import answer
from packages.tom_bench.generator import Story, generate

_ART = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)

# categories that require distinguishing a character's belief from ground truth
BELIEF_CATS = ("first_order_fb", "second_order", "first_order_tb")
CONTROL_CATS = ("reality", "memory")
REALITY_VALID_THRESHOLD = 0.90


def _norm(s) -> str:
    if s is None:
        return ""
    return " ".join(_ART.sub("", str(s).strip().lower()).split()).rstrip(".!?")


def classify(pred, gold: str, reality_loc: str) -> str:
    """One of: correct | egocentric | other | abstain."""
    if pred is None or _norm(pred) == "":
        return "abstain"
    p = _norm(pred)
    if p == _norm(gold):
        return "correct"
    if reality_loc and p == _norm(reality_loc) and _norm(reality_loc) != _norm(gold):
        return "egocentric"
    return "other"


@dataclass
class CatStat:
    n: int = 0
    correct: int = 0
    egocentric: int = 0
    other: int = 0
    abstain: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def abstain_rate(self) -> float:
        return self.abstain / self.n if self.n else 0.0


@dataclass
class Report:
    cats: dict = field(default_factory=lambda: defaultdict(CatStat))
    n_stories: int = 0
    n_questions: int = 0
    records: list = field(default_factory=list)   # (sid, category, question, pred, gold, outcome)

    @property
    def reality_accuracy(self) -> float:
        return self.cats["reality"].accuracy

    @property
    def tom_valid(self) -> bool:
        return self.reality_accuracy >= REALITY_VALID_THRESHOLD


def run(stories=None) -> Report:
    """Score the benchmark deterministically over the real answer path."""
    if stories is None:
        stories = generate()
    rep = Report(n_stories=len(stories))
    for st in stories:
        sit = build(st.text)                         # one world per story; every question queries it
        for q in st.questions:
            out = answer(q.text, sit)
            pred = out.get("answer")
            outcome = classify(pred, q.gold, q.reality_loc)
            cs = rep.cats[q.category]
            cs.n += 1
            setattr(cs, outcome, getattr(cs, outcome) + 1)
            rep.n_questions += 1
            rep.records.append((st.sid, q.category, q.text, pred, q.gold, outcome))
    return rep


_LABELS = {
    "reality": "reality-control  ", "memory": "memory-control   ",
    "first_order_fb": "first-order  (FB)", "second_order": "second-order (FB)",
    "first_order_tb": "true-belief      ",
}
_ORDER = ["reality", "memory", "first_order_fb", "second_order", "first_order_tb"]


def format_report(rep: Report) -> str:
    lines = []
    lines.append(f"ATANOR Theory-of-Mind benchmark  (sealed, N={rep.n_stories} stories, "
                 f"{rep.n_questions} questions)")
    lines.append(f"answer path: situation_model.build + reasoner.answer  (in-process, no mock)")
    lines.append("")
    lines.append(f"{'category':<20}{'n':>4}{'acc':>8}{'correct':>9}{'egocentric':>12}"
                 f"{'abstain':>9}{'other':>7}")
    lines.append("-" * 69)
    for cat in _ORDER:
        cs = rep.cats.get(cat)
        if not cs or cs.n == 0:
            continue
        lines.append(f"{_LABELS[cat]:<20}{cs.n:>4}{cs.accuracy:>8.3f}{cs.correct:>9}"
                     f"{cs.egocentric:>12}{cs.abstain:>9}{cs.other:>7}")
    lines.append("-" * 69)
    valid = "VALID" if rep.tom_valid else "INVALID (reality-control below threshold)"
    lines.append(f"reality-control = {rep.reality_accuracy:.3f}  ->  ToM run is {valid}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    io = getattr(sys.stdout, "reconfigure", None)
    if io:
        sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(run()))
