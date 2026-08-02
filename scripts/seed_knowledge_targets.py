# -*- coding: utf-8 -*-
"""Phase 1-3: mass-run the knowledge learner unattended.

Seeds the abstain queue with high-value subjects (things real users ask a
Korean assistant about). The EXISTING daemon machinery does the rest — the
abstain drain fetches definitions ( first), the v2 knowledge learner
gathers attributed web evidence, and fetch_profile adds Wikidata attributes.
Nothing new to trust: every landing passes the same judge/consensus gates."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale import abstain_queue  # noqa: E402

# high-value subjects: geography, institutions, science, tech, culture, history —
# the head of the real question distribution for a Korean assistant.
TARGETS = [

    "한강", "백두산", "설악산", "독도", "판문점", "경주", "전주", "여수", "인천공항",
    "남산타워", "해운대", "석굴암", "창덕궁", "덕수궁", "종묘",

    "광합성", "중력", "전자", "원자", "유전자", "단백질", "바이러스", "백신", "항생제",
    "블랙홀", "은하", "태양계", "지진", "태풍", "장마",

    "반도체", "인공지능", "블록체인", "클라우드 컴퓨팅", "양자컴퓨터", "5G", "GPS",
    "리튬이온 배터리", "전기차", "드론", "메타버스",

    "민주주의", "삼권분립", "헌법", "국회", "대법원", "중앙은행", "인플레이션",
    "환율", "주식", "부동산", "연금",

    "훈민정음", "임진왜란", "삼일운동", "한국전쟁", "고려청자", "판소리", "탈춤",
    "한복", "김장", "설날", "추석",

    "비빔밥", "불고기", "냉면", "떡볶이", "삼겹살", "막걸리", "소주",
]


def main() -> None:
    added = 0
    for t in TARGETS:
        try:
            # record_abstain extracts knowledge terms from a query — feed the
            # canonical definitional question so the term lands with a real query
            terms = abstain_queue.record_abstain(f"{t}이란?")
            if terms:
                added += 1
        except Exception:
            continue
    print(f"seeded {added}/{len(TARGETS)} targets into the abstain queue")
    print("the continuous daemon drains them automatically "
          "(ATANOR_ABSTAIN_FEED_EVERY ticks); each drained term also triggers "
          "the v2 web-evidence learner + Wikidata profile fetch")


if __name__ == "__main__":
    main()
