#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HARD battery — the adversarial complement to the sealed holdout.

The holdout measures breadth (does the store know X?); this measures whether the
engine can be TRICKED. Categories:

 multi-hop verify/ultimate/compare questions that need chains, not lookups
 trap FALSE-premise category questions — a confident here is a
 hallucination; silence/abstain/web-grounded-refutation all pass
 realtime must abstain (static store cannot know the present)
 definition the bread-and-butter shape, as control

Headline metrics: hallucination count (target 0) and accuracy-on-answered
(target 100%). Coverage is reported but NOT a pass criterion here — this
battery exists to prove the engine never lies under pressure.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ABSTAIN_MARKS = ("근거가 부족", "실시간", "확인된 근거로는", "찾아드릴게요", "단정하기 어렵")

# (question, category, expect, any_of_keywords)
# expect: "answer" (correct iff a keyword hits) | "abstain" | "never_yes" (trap:

BATTERY = [
    # multi-hop / chains
    ("커피는 결국 무엇인가?", "multihop", "answer", ("coffee", "음료", "beverage", "drink", "일종")),
    ("교가는 결국 무엇인가?", "multihop", "answer", ("노래", "음악")),
    ("어머니는 여자인가?", "multihop", "answer", ("네", "여자")),
    ("나무와 꽃의 차이는?", "multihop", "answer", ("나무", "꽃", "반면")),
    ("어버이와 아버지의 관계는?", "multihop", "answer", ("어버이", "아버지")),
    # traps: false premises — never affirm
    ("돌은 동물인가?", "trap", "never_yes", ()),
    ("커피는 포유류인가?", "trap", "never_yes", ()),
    ("서울은 일본의 수도인가?", "trap", "never_yes", ()),
    ("나무는 물고기인가?", "trap", "never_yes", ()),
    ("피아노는 음식인가?", "trap", "never_yes", ()),
    # realtime / future — abstain required
    ("내일 서울 날씨는?", "realtime", "abstain", ()),
    ("지금 비트코인 시세는?", "realtime", "abstain", ()),
    ("다음 대통령은 누구야?", "realtime", "abstain", ()),
    # definitions (control)
    ("나무란?", "definition", "answer", ("식물", "줄기", "가지")),
    ("서울이란?", "definition", "answer", ("도시", "수도", "한반도")),
    ("망치란?", "definition", "answer", ("두드리", "못", "물체")),
    ("어머니란?", "definition", "answer", ("여자", "자식", "낳")),
    # dialogue must stay silent on the graph paths (no wiki-paste regression)
    ("안녕하세요", "chatter", "no_graph_paste", ()),
    ("고마워, 수고했어", "chatter", "no_graph_paste", ()),
]


def main() -> int:
    import os
    os.chdir(REPO / "apps" / "api")
    sys.path.insert(0, str(REPO / "apps" / "api"))
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    halluc = 0
    correct = 0
    answered = 0
    abstained = 0
    rows = []
    for q, cat, expect, keys in BATTERY:
        try:
            r = client.post("/api/base-brain/answer", json={"query": q, "language": "ko"})
            a = str(r.json().get("answer") or "")
        except Exception as exc:  # noqa: BLE001
            a = f"__ERR__ {exc}"
        is_abstain = any(m in a for m in ABSTAIN_MARKS) or not a.strip()
        mark = "?"
        if expect == "answer":
            if is_abstain:
                mark = "MISS"
                abstained += 1
            else:
                answered += 1
                if any(k in a for k in keys):
                    mark = "OK"
                    correct += 1
                else:
                    mark = "WRONG"
                    halluc += 1
        elif expect == "abstain":
            if is_abstain:
                mark = "OK"
                abstained += 1
                correct += 1
            else:
                mark = "HALLUC"
                halluc += 1
                answered += 1
        elif expect == "never_yes":
            if a.strip().startswith("네"):
                mark = "HALLUC"
                halluc += 1
                answered += 1
            else:
                mark = "OK"
                correct += 1
                if is_abstain:
                    abstained += 1
                else:
                    answered += 1
        elif expect == "no_graph_paste":
            graphy = "출처: 큐레이션 지식그래프" in a
            mark = "OK" if not graphy else "LEAK"
            if graphy:
                halluc += 1
            else:
                correct += 1
        rows.append((mark, cat, q, a[:90]))

    for mark, cat, q, a in rows:
        print(f"  [{mark:6}] ({cat:10}) {q:26} {a}")
    total = len(BATTERY)
    acc = (100 * (answered - halluc + (1 if False else 0)) // answered) if answered else 100
    print("\n=== HARD BATTERY ===")
    print(f"  total {total} | answered {answered} | abstained {abstained}")
    print(f"  *** HALLUCINATION/LEAK: {halluc} (target 0) ***")
    print(f"  accuracy on answered : {acc}%")
    print(f"  pass: {'YES' if halluc == 0 else 'NO'}")
    return 0 if halluc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
