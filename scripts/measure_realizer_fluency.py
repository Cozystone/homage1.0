# -*- coding: utf-8 -*-
"""C4 gate measurement: did the learned realizer kill the dictionary tone while holding grounding?

Measures the FINAL_PLAN C4 done-gate proxies on a battery of multi-fact answers — template
enumeration (the 0.60-flat scaffold) vs the learned fusion now live in grounded_generation:
 - sentences per answer (enumeration = N separate sentences; fusion = 1 flowing sentence)
 - enumeration markers (// — the dictionary tell; must reach 0)
 - learned fusion markers (///… — mined from real prose)
 - grounding preserved (every fact survives — the hard gate; must stay 100%)
No claim — a receipt. Run: python scripts/measure_realizer_fluency.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.base_brain.grounded_generation import synthesize          # noqa: E402
from packages.base_brain.learned_realizer import grounding_ok            # noqa: E402

# a diverse battery (person / place / org / concept / thing), bare + self-subjected descriptions
BATTERY = [
    ("애플이 뭐야", [
        {"name": "애플", "description": "미국 캘리포니아에 본사를 둔 다국적 기술 회사"},
        {"name": "애플", "description": "소비자 가전과 소프트웨어와 서비스로 잘 알려져 있다"},
        {"name": "애플", "description": "1976년에 스티브 잡스 등이 설립하였다"}]),
    ("세종대왕은?", [
        {"name": "세종대왕", "description": "조선의 제4대 국왕으로 즉위하였다"},
        {"name": "세종대왕", "description": "훈민정음을 창제하여 반포하였다"},
        {"name": "세종대왕", "description": "과학과 예술과 국방을 크게 발전시켰다"}]),
    ("광합성이란", [
        {"name": "광합성", "description": "식물이 빛 에너지를 화학 에너지로 바꾸는 과정"},
        {"name": "광합성", "description": "이산화탄소와 물로 포도당을 만들어 낸다"},
        {"name": "광합성", "description": "부산물로 산소를 방출한다"}]),
    ("에베레스트 산", [
        {"name": "에베레스트", "description": "히말라야산맥에 있는 지구에서 가장 높은 산"},
        {"name": "에베레스트", "description": "높이가 해발 8,848미터에 이른다"},
        {"name": "에베레스트", "description": "네팔과 중국의 국경에 걸쳐 있다"}]),
    ("커피", [
        {"name": "커피", "description": "커피나무 열매의 씨앗을 볶아 만든 음료"},
        {"name": "커피", "description": "카페인을 함유하여 각성 효과를 준다"}]),
]

_ENUM = ("먼저", "또한", "끝으로")
_FUSE = ("이며", "이자", "이고", "으며", "면서")


def _sentences(a: str) -> int:
    return sum(a.count(p) for p in (". ", ".", "요.", "다.")) or a.count(".")


def main() -> int:
    tot = {"n": 0, "sent_fusion": 0, "sent_template_est": 0, "enum": 0, "fuse": 0, "grounded": 0}
    print("=== C4 realizer fluency gate (live synthesize, learned fusion) ===\n")
    for q, facts in BATTERY:
        r = synthesize(q, facts, "ko")
        if not r:
            continue
        a = r["answer"]
        mode = r["reasoning_certificate"].get("discourse_mode")
        # strip the opener sentence (framing scaffold) to score the BODY the realizer produced
        body = a.split(". ", 1)[-1] if ". " in a else a
        n_sent = body.rstrip(".").count(".") + 1
        has_enum = any(m in a for m in _ENUM)
        n_fuse = sum(a.count(m) for m in _FUSE)
        # grounding is measured on the facts the realizer was actually GIVEN (post length/dedup
        # filter) — did fusion preserve its input, the honest hard-gate question.
        used = [f["description"] for f in r.get("facts_used", facts)]
        grounded = grounding_ok(a, used)
        tot["n"] += 1
        tot["sent_fusion"] += n_sent
        tot["sent_template_est"] += len(facts)          # template = one sentence per fact
        tot["enum"] += 1 if has_enum else 0
        tot["fuse"] += n_fuse
        tot["grounded"] += 1 if grounded else 0
        print(f"[{q}] mode={mode} body_sentences={n_sent} enum_markers={has_enum} "
              f"fuse_markers={n_fuse} grounded={grounded}")
        print(f"    {body[:120]}")
    n = max(1, tot["n"])
    print("\n=== TOTAL (n=%d) ===" % tot["n"])
    print(f"  body sentences/answer:  template≈{tot['sent_template_est']/n:.2f}  →  fusion {tot['sent_fusion']/n:.2f}")
    print(f"  enumeration answers:    {tot['enum']}/{tot['n']}   (dictionary tone; target 0)")
    print(f"  learned fuse markers:   {tot['fuse']} total across {tot['n']} answers")
    print(f"  grounding preserved:    {tot['grounded']}/{tot['n']}   (HARD GATE; must be {tot['n']}/{tot['n']})")
    ok = tot["enum"] == 0 and tot["grounded"] == tot["n"] and tot["sent_fusion"] < tot["sent_template_est"]
    print(f"\n  C4 gate (enum=0 AND grounding=100% AND fewer sentences): {'PASS' if ok else 'not yet'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
