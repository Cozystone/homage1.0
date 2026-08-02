# -*- coding: utf-8 -*-
"""Supplementary shallow crawl from CONCRETE category seeds — guarantees everyday
concepts (→, →, →) land in the ledger instead of waiting
for a deep BFS descent from abstract seeds that may never reach them.

Runs AFTER the broad crawl (harvest_ko_wikipedia). Appends to the same ledger;
dedup on reload merges cleanly. Depth 2 is enough: concrete category -> subcats
and direct page-members.
"""
import sys, time
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from graph_scale import wikipedia_ko_categories as wc

LOG = Path(__file__).resolve().parents[1] / "data" / "graph_scale" / "harvest_ko_wiki.log"

# concrete leaf-bearing categories: their page-members are everyday nouns
CONCRETE = (
    "과일", "채소", "음료", "자동차", "포유류", "조류", "어류", "곤충",
    "꽃", "나무", "악기", "가전제품", "의류", "가구", "무기", "항공기",
    "선박", "기계", "금속", "광물", "질병", "신체 기관", "색", "운동",
    "빵", "면류", "술", "향신료", "견과류", "유제품", "생선 요리",
    "운영 체제", "프로그래밍 언어", "스마트폰", "카메라", "시계",
    "행성", "별자리", "화폐", "보석", "문구", "완구",
)


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


if __name__ == "__main__":
    log(f"=== concrete-seed supplement: {len(CONCRETE)} seeds, depth 2 ===")
    t0 = time.time()
    res = wc.harvest_ko_categories(seeds=CONCRETE, max_depth=2, max_edges=40000,
                                   include_pages=True, pace_sec=0.4,
                                   ledger_name="wikipedia_ko_concrete_is_a.jsonl", log=log)
    log(f"=== concrete done in {int(time.time()-t0)}s -> {res} ===")
