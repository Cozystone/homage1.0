# -*- coding: utf-8 -*-
"""C3 gate measurement: does verify-gated discrimination answer FACTUAL MCQ correctly against the
LIVE world-pack store, and ABSTAIN (never guess) elsewhere? A receipt, not a claim.

Routes a factual-MCQ battery through discriminate() with a Q-id-resolving facts_about over the
world pack. Reports, over questions the graph COVERS: answered accuracy (must beat 0.25 guess) and
that uncovered/conceptual questions ABSTAIN rather than bluff. Run:
  python scripts/measure_discrimination.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.graph_scale.triple_store import TripleStore          # noqa: E402
from packages.reasoning_vm.discrimination import discriminate      # noqa: E402

_Q = re.compile(r"^Q\d+$")
_ST = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full",
                  dict_backend="sharded", write_src=False)
_QCACHE: dict[str, str] = {}


def _qlabel(qid: str) -> str:
    if qid in _QCACHE:
        return _QCACHE[qid]
    lab = next((o for (s, p, o) in _ST.facts_about(qid, limit=6) if p == "qlabel"), qid)
    _QCACHE[qid] = lab
    return lab


def facts_about(subject: str):
    """(s, p, o) triples with Q-id objects resolved to their labels (world-pack schema)."""
    out = []
    for (s, p, o) in _ST.facts_about(subject, limit=40):
        out.append((s, p, _qlabel(o) if _Q.match(str(o)) else o))
    return out


# factual MCQ battery: capitals the partial covers (correct + 3 plausible distractors) + a couple
# conceptual stems that MUST abstain (no factual relation → honest silence, not a guess).
BATTERY = [
    ("독일의 수도는 어디인가?", {"A": "베를린", "B": "파리", "C": "런던", "D": "마드리드"}, "A"),
    ("미국의 수도는 어디인가?", {"A": "뉴욕", "B": "워싱턴 D.C.", "C": "로스앤젤레스", "D": "시카고"}, "B"),
    ("이탈리아의 수도는?", {"A": "밀라노", "B": "베네치아", "C": "로마", "D": "나폴리"}, "C"),
    ("베트남의 수도는 어디인가?", {"A": "호찌민", "B": "다낭", "C": "후에", "D": "하노이"}, "D"),
    ("태국의 수도는?", {"A": "방콕", "B": "치앙마이", "C": "푸껫", "D": "파타야"}, "A"),
    # conceptual — must ABSTAIN (no factual cue / not a graph lookup)
    ("광합성에 대한 설명으로 옳은 것은?", {"A": "a", "B": "b", "C": "c", "D": "d"}, "?"),
    ("다음 중 리더십의 핵심 요소로 가장 적절한 것은?", {"A": "a", "B": "b", "C": "c", "D": "d"}, "?"),
]


def main() -> int:
    covered = correct = answered = abstained_conceptual = 0
    print("=== C3 discrimination gate (live world-pack store) ===\n")
    for stem, choices, gold in BATTERY:
        v = discriminate(stem, choices, facts_about)
        conceptual = gold == "?"
        if v.status == "GROUNDED":
            answered += 1
            hit = v.choice_key == gold
            if not conceptual:
                covered += 1
                correct += 1 if hit else 0
            mark = "✓" if hit else ("✗ (should abstain!)" if conceptual else "✗")
            print(f"[{stem[:34]:34}] GROUNDED → {v.choice_key} {mark}")
        else:
            if conceptual:
                abstained_conceptual += 1
            print(f"[{stem[:34]:34}] ABSTAIN   ({v.basis[:46]})")
    n_fact = sum(1 for _s, _c, g in BATTERY if g != "?")
    n_conc = sum(1 for _s, _c, g in BATTERY if g == "?")
    print(f"\n=== TOTAL ===")
    print(f"  factual answered/covered: {covered}/{n_fact}   answered_acc: "
          f"{(correct / covered) if covered else float('nan'):.2f}  (guess 0.25)")
    print(f"  conceptual abstained:     {abstained_conceptual}/{n_conc}  (must be {n_conc}/{n_conc} — no bluff)")
    ok = covered >= 1 and correct == covered and abstained_conceptual == n_conc
    print(f"\n  C3 gate (factual correct + conceptual abstains): {'PASS' if ok else 'not yet'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
