# -*- coding: utf-8 -*-
"""Build the browser-local mini-ATANOR knowledge pack for the landing page.

The landing's chat demo becomes a REAL engine: this script exports a compact
slice of the live curated triple store (the same store the full engine answers
from) to apps/landing/assets/mini_brain.json. The in-page JS engine answers by
deterministic graph lookup — GPU 0, network 0 after load, no LLM — which is
the product claim demonstrated literally.

" mini " = rerun this script (it
reads whatever the live store holds now) and redeploy the landing.

Run: python scripts/build_mini_brain.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "apps" / "landing" / "assets" / "mini_brain.json"

# Export scope (a BUILD choice, not answer logic): common countries + the
# curated demo concepts. The answers themselves come from the live store.
SEED_COUNTRIES = [
    "대한민국", "일본", "중국", "미국", "영국", "프랑스", "독일", "이탈리아", "스페인",
    "캐나다", "호주", "브라질", "인도", "러시아", "멕시코", "인도네시아", "베트남",
    "태국", "필리핀", "튀르키예", "이집트", "네덜란드", "스위스", "스웨덴", "노르웨이",
    "핀란드", "덴마크", "폴란드", "오스트리아", "벨기에", "포르투갈", "그리스",
    "아르헨티나", "칠레", "뉴질랜드", "싱가포르", "말레이시아", "몽골", "우크라이나",
    "이스라엘", "사우디아라비아", "이란", "이라크", "파키스탄", "방글라데시",
    "남아프리카 공화국", "나이지리아", "케냐", "모로코", "콜롬비아", "페루", "쿠바",
    "체코", "헝가리", "루마니아", "아일랜드", "아이슬란드", "북한",
]
SEED_CONCEPTS = [
    "인공지능", "커피", "에스프레소", "카페인", "컴퓨터", "인터넷", "쿠버네티스",
    "지식 그래프", "온톨로지", "중력", "광합성", "빛의 속도", "만유인력의 법칙",
    "피타고라스의 정리", "물", "산소", "태양", "달", "지구", "화성",
]
KEEP_RELATIONS = {
    "capital", "country", "located_in", "author", "defined_as", "is_a",
    "used_for", "인구", "면적", "설립", "수도", "통화", "언어", "대륙",
}
REL_KO = {
    "capital": "수도", "country": "나라", "located_in": "위치", "author": "저자",
    "defined_as": "정의", "is_a": "종류", "used_for": "용도",
}


def main() -> None:
    from packages.graph_scale.answer_bridge import _store

    store = _store()
    if store is None:
        raise SystemExit("triple store unavailable — run from the demo worktree with the store built")

    triples: list[list[str]] = []
    concepts: dict[str, str] = {}
    def_rows: dict[str, list[str]] = {}
    seen: set[tuple[str, str, str]] = set()
    seeds = SEED_COUNTRIES + SEED_CONCEPTS
    for seed in seeds:
        try:
            rows = store.facts_about(seed) or []
        except Exception:
            continue
        for row in rows:
            try:
                s, p, o = str(row[0]), str(row[1]), str(row[2])
            except Exception:
                continue

            # 299,792,458 m/s value past 90 chars — the flagship answer was
            # being filtered out of its own demo); relation values stay short
            _cap = 220 if p == "defined_as" else 90
            if p not in KEEP_RELATIONS or not o or len(o) > _cap:
                continue
            key = (s, p, o)
            if key in seen:
                continue
            seen.add(key)
            triples.append([s, p, o])
            # collect Korean definitions per subject; the pick happens after the
            # scan (curated order first, truncated prefixes skipped) — longest-

            # (the same polysemy trap the bridge fixed: curated order carries
            # the common sense first)
            if p == "defined_as" and len(o) >= 6 and any("가" <= ch <= "힣" for ch in o):
                def_rows.setdefault(s, []).append(o)

    # pick each subject's definition: CURATED ORDER (common sense first), but a
    # definition that is a strict prefix of a later, longer one is a truncation

    for s, defs in def_rows.items():
        chosen = None
        for d in defs:
            if any(d != d2 and d2.startswith(d) for d2 in defs):
                continue  # truncated prefix of a fuller sentence
            chosen = d
            break
        concepts[s] = chosen or defs[0]

    # web-verified facts the engine LEARNED (web_fact_memory carries the source

    # mini: those answers were always web-lane, never local-store rows, so the
    # pack must carry the engine's verified web memory or the landing's own

    try:
        wfm = json.loads((ROOT / "runtime" / "local_brain" / "web_fact_memory.json")
                         .read_text(encoding="utf-8"))
        items = wfm if isinstance(wfm, list) else wfm.get("facts") or list(wfm.values())
        for x in items:
            subj = str(x.get("subject") or "").strip()
            val = str(x.get("value") or "").strip()
            if (subj and 2 <= len(subj) <= 24 and val and len(val) >= 20
                    and any("가" <= ch <= "힣" for ch in val) and subj not in concepts):
                # long web memories keep their FIRST sentences up to ~240 chars —

                if len(val) > 240:
                    cut = val[:240]
                    dot = cut.rfind(". ")
                    val = (cut[: dot + 1] if dot >= 60 else cut).strip()
                concepts[subj] = val

                if subj == "빛의 속력":
                    concepts.setdefault("빛의 속도", val)
    except Exception:
        pass

    # curated demo concept descriptions (the same pack the demo answers use)
    try:
        from packages.base_brain.zero_user_answer import KO_DESCRIPTIONS

        for cid, desc in KO_DESCRIPTIONS.items():
            label = str(cid).replace("_", " ")
            if label not in concepts and desc:
                concepts[label] = str(desc)[:160]
    except Exception:
        pass

    pack = {
        "version": 1,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "curated triple store (live engine snapshot)",
        "counts": {"triples": len(triples), "concepts": len(concepts)},
        "rel_ko": REL_KO,
        "concepts": concepts,
        "triples": triples,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"mini_brain.json: {len(triples)} triples, {len(concepts)} concepts, "
          f"{OUT.stat().st_size / 1024:.1f} KB -> {OUT}")


if __name__ == "__main__":
    main()
