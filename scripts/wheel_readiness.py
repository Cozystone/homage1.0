# -*- coding: utf-8 -*-
"""Training-wheel readiness — WHEN can each regex lane come off?

Owner (2026-07-11): " ." A regex conversational lane is a TEACHER; the
learned router is the student. A wheel is safe to remove once the router classifies that lane's
intent as well as the regex does. This report makes that measurable per wheel, from two signals:

 1. REAL TRAFFIC (flywheel.router_readiness): router-vs-gold agreement on logged live turns —
 the honest, in-distribution measure. Grows as the engine is used.
 2. PROBE SET (below): the router run on held-out paraphrases of each lane's trigger, so we get
 an immediate signal even before traffic accumulates.

Verdict per wheel: REMOVABLE (router ≥ 0.85 on the probes AND real agreement ≥ promote bar) or
KEEP (still the teacher). Run: python scripts/wheel_readiness.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# held-out paraphrases per rule lane → the intent the router SHOULD predict. Kept small and
# UNSEEN (not the exact regex strings) so this measures generalisation, not memorisation.
_PROBES: dict[str, list[str]] = {
    "advice": ["요즘 통 잠이 안 오는데 어쩌면 좋을까요", "살이 자꾸 찌는데 어떡하죠",
               "집중이 안 돼서 고민이야 방법 없을까", "자꾸 미루게 되는데 어떻게 고치지"],
    "cause": ["커피 너무 많이 마시면 몸에 어떻게 돼?", "잠을 안 자면 무슨 일이 생겨",
              "술 자주 마시면 어떻게 되나요", "왜 물가가 오른 거야"],
    "opinion": ["인공지능이 인간을 넘어설까?", "이 선택이 맞다고 봐?",
                "재택근무가 정말 좋은 걸까", "그게 꼭 필요하다고 생각해?"],
    "smalltalk": ["심심한데 재밌는 얘기 없어?", "그냥 너랑 수다 떨고 싶어",
                  "오늘 좀 지루하다", "우리 아무 얘기나 하자"],
    "greeting": ["안녕 반가워", "하이 뭐해", "좋은 아침이야", "잘 지냈어?"],
    "affect": ["오늘따라 마음이 좀 무겁네", "너무 속상한 일이 있었어",
               "요즘 너무 지쳐", "기분이 좋지 않아"],
}


def _probe_scores() -> dict[str, dict]:
    try:
        from packages.learned_router import predict, router_available
    except Exception as exc:  # pragma: no cover
        return {"_error": f"router import failed: {exc}"}
    if not router_available():
        return {"_error": "learned router model not available (train it first)"}
    out: dict[str, dict] = {}
    for intent, qs in _PROBES.items():
        hits = 0
        rows = []
        for q in qs:
            pred, conf = predict(q)
            ok = (pred == intent)
            hits += int(ok)
            rows.append({"q": q, "pred": pred, "conf": round(float(conf), 2), "ok": ok})
        out[intent] = {"rate": round(hits / max(1, len(qs)), 2), "n": len(qs), "rows": rows}
    return out


def main() -> None:
    print("=== 보조바퀴 제거 준비도 (wheel readiness) ===\n")
    # 1) real-traffic agreement (in-distribution)
    try:
        from packages.flywheel.self_improvement import router_readiness
        rr = router_readiness()
        print(f"[실트래픽] 표본 {rr['samples']} · 라우터-정답 일치 {rr['agreement']*100:.0f}% "
              f"· 승격바 {rr['promote_at']*100:.0f}%")
        print(f"  판정: {rr['verdict']}")
        if rr.get("weakest_intents"):
            weak = ", ".join(f"{k}={v['rate']*100:.0f}%" for k, v in rr["weakest_intents"])
            print(f"  약한 의도: {weak}")
    except Exception as exc:
        print(f"[실트래픽] 측정 실패: {exc}")
    # 1b) LANE-DISTILLED candidate (the RIGHT readiness number): the production router's label
    # space is fact-shaped (definition/relation/…), so it scores ~0% on conversational lanes and
    # UNDER-states readiness. The distilled candidate learns the LANE labels — its holdout is the
    # honest "how close to removing the rules" measure.
    try:
        from packages.flywheel.self_improvement import distill_router
        dr = distill_router()
        if dr.get("trained"):
            ho = dr.get("holdout_acc", 0)
            bar = 0.85
            print(f"\n[레인-증류 후보] {dr['trained']}턴 · {dr['lanes']}개 레인 · 홀드아웃 {ho*100:.0f}% "
                  f"(떼기 바 {bar*100:.0f}%)")
            print(f"  판정: {'후보가 규칙을 대체할 준비 근접 — 승격 검토' if ho >= bar else f'홀드아웃 {ho*100:.0f}% — 트래픽/증류 더 쌓으면 바 돌파'}")
        else:
            print(f"\n[레인-증류 후보] 미훈련: {dr.get('reason') or dr.get('error')}")
    except Exception as exc:
        print(f"\n[레인-증류 후보] 실패: {exc}")
    # 2) probe-set generalisation (immediate signal)
    print("\n[프로브] 각 레인 미학습 패러프레이즈에 대한 라우터 정확도:")
    ps = _probe_scores()
    if "_error" in ps:
        print(f"  {ps['_error']}")
    else:
        for intent, d in sorted(ps.items(), key=lambda kv: kv[1]["rate"], reverse=True):
            verdict = "REMOVABLE ✅" if d["rate"] >= 0.85 else ("근접" if d["rate"] >= 0.6 else "KEEP")
            print(f"  {intent:10s} {d['rate']*100:3.0f}%  ({d['n']}개)  → {verdict}")
    print("\n규칙 = 교사, 라우터 = 학생. REMOVABLE이면 해당 레인 정규식을 라우터로 교체 가능.")
    print("살찌우기: distill_router()로 라우터 재훈련 → 이 스코어가 오름 → 규칙 삭제.")


if __name__ == "__main__":
    main()
