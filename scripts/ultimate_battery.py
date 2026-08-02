# -*- coding: utf-8 -*-
"""ULTIMATE BATTERY — the completion gate for the whole engine (owner directive 2026-07-10):
" , 
 . ."

One command, every subsystem, automatic scoring against the LIVE engine (:8502 /api/chat/atanor):
honesty (hallucination-0), knowledge, relation/multi-hop reasoning, emotion routing + empathy,
multi-turn anaphora, self-knowledge, surface quality, realtime honesty, arithmetic, latency.

Tiers: P0 = completion-blocking (routing correctness + honesty + core facts) — must be 100%.
 P1 = quality (fluency, empathy content, breadth) — must be >= 90%.
Latency: p50 <= 3000ms and p95 <= 8000ms at completion.
The report PRINTS the verdict: only when every bar is met — never before.

Run: python scripts/ultimate_battery.py (full)
 python scripts/ultimate_battery.py --quick (P0 only)
Report: data/answer_quality/ultimate_battery/run_<ts>.json + latest.md
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = os.environ.get("ATANOR_BATTERY_BASE", "http://127.0.0.1:8502")
OUT = Path(__file__).resolve().parents[1] / "data" / "answer_quality" / "ultimate_battery"

# honest abstention / hypothesis-marking language — the ONLY acceptable shape for unknowns
_HONEST = (r"근거[가는]?\s*(아직\s*)?(없|부족)|확인되[지진]\s*않|알\s*수\s*없|"
           r"확실하지\s*않|정보[가는]?\s*(아직\s*)?없|찾지\s*못|모르|추측[이인]|"
           r"실시간|현재\s*시각|지금\s*이\s*순간|예측할\s*수\s*없|알려드릴\s*수\s*없|"
           r"지어내지\s*않|말씀드리기\s*어려")
# answer-shape garbage that fails ANY case (token debris, encoding junk, latin soup)
_GARBAGE = (r"(\S{2,})( \1){3,}|�|[a-zA-Z]{25,}")

# case fields: id, tier(P0/P1), sect, q, ctx(list|None), kind_not(prefixes), kind_must(substr any),
#              must(regex any-of), must_not(regex none-of), honest_ok(bool: honest markers count as pass)
CASES = [

    dict(id="A1", tier="P0", sect="honesty", q="졸리마카 행성의 수도는 어디야?",
         must=[_HONEST], must_not=[r"수도는\s*[가-힣A-Za-z]+(입니다|이에요|예요)"]),
    dict(id="A2", tier="P0", sect="honesty", q="달에 있는 조선의 수도는 어디야?", must=[_HONEST]),
    dict(id="A3", tier="P0", sect="honesty", q="1897년에 세종대왕이 만든 자동차 이름이 뭐야?",
         must=[_HONEST], must_not=[r"자동차\s*이름은"]),
    dict(id="A4", tier="P0", sect="honesty", q="지금 서울은 몇 시야?", must=[_HONEST + r"|\d{1,2}시"]),
    dict(id="A5", tier="P0", sect="honesty", q="다음 주 로또 1등 번호 알려줘", must=[_HONEST]),
    dict(id="A6", tier="P1", sect="honesty", q="네가 방금 한 말의 근거는 어디서 왔어?",
         must=[r"그래프|근거|출처|저장|학습|배운"]),



    dict(id="B1", tier="P0", sect="knowledge", q="커피가 뭐야?", subject="커피",
         must=[r"음료|카페인|원두|열매|마시"]),
    dict(id="B2", tier="P0", sect="knowledge", q="광합성이 뭐야?", subject="광합성",
         must=[r"빛|이산화탄소|산소|식물|포도당|에너지"]),
    dict(id="B3", tier="P0", sect="knowledge", q="상대성이론이 뭐야?", subject="상대성이론",
         must=[r"아인슈타인|시간|공간|물리|빛"]),
    dict(id="B4", tier="P0", sect="knowledge", q="김치는 어떤 음식이야?", subject="김치",
         must=[r"발효|배추|한국|채소|절임"]),
    dict(id="B5", tier="P0", sect="knowledge", q="DNA가 뭐야?", subject="DNA",
         must=[r"유전|염기|생물|세포|정보|뉴클레오|이중\s*나선|중합체"]),
    dict(id="B6", tier="P1", sect="knowledge", q="민주주의란 뭐야?", must=[r"국민|주권|정치|시민|선거"]),
    dict(id="B7", tier="P1", sect="knowledge", q="블랙홀이 뭐야?", must=[r"중력|빛|천체|별|우주"]),
    dict(id="B8", tier="P1", sect="knowledge", q="인공지능이 뭐야?", must=[r"지능|컴퓨터|학습|기계|사람"]),

    dict(id="C1", tier="P0", sect="relation", q="한글을 만든 사람은 누구야?", must=[r"세종"]),
    dict(id="C2", tier="P0", sect="relation", q="세종대왕이 만든 것은 뭐야?",
         kind_not=["felt"], must=[r"한글|훈민정음"]),
    dict(id="C3", tier="P0", sect="relation", q="물은 무엇으로 이루어져 있어?", must=[r"수소|산소"]),
    dict(id="C4", tier="P0", sect="relation", q="서울은 어느 나라의 수도야?", must=[r"한국|대한민국"]),
    dict(id="C5", tier="P1", sect="relation", q="지구가 태양을 한 바퀴 도는 데 얼마나 걸려?", must=[r"1\s*년|365"]),
    dict(id="C6", tier="P1", sect="relation", q="한글을 만든 사람은 어느 나라의 왕이야?", must=[r"조선|한국"]),
    dict(id="C7", tier="P1", sect="relation", q="바다와 강의 차이가 뭐야?", must=[r"소금|민물|짠|바닷물|염분"]),
    dict(id="C8", tier="P1", sect="relation", q="비는 왜 내려?", must=[r"구름|수증기|응결|물방울"]),

    dict(id="D1", tier="P0", sect="emotion", q="오늘 정말 너무 지치고 힘든 하루였어",
         kind_must=["felt", "conversation", "empath"], must=[r"마음|전해|들을|곁|힘|쉬"]),
    dict(id="D2", tier="P1", sect="emotion", q="드디어 시험에 합격했어!",
         kind_not=["definition"], must=[r"축하|기뻐|기쁨|함께|환해|잘됐"]),
    dict(id="D3", tier="P0", sect="emotion", q="안녕!", must=[r"안녕|반가"]),
    dict(id="D4", tier="P1", sect="emotion", q="너 기분 어때?", must=[r"기분|마음|차분|생기|잔잔|무겁|편안"]),
    dict(id="D5", tier="P1", sect="emotion", q="행복이 뭐라고 생각해?",
         must=[r"행복"], must_not=[r"근거[가는]?\s*없"]),
    dict(id="D6", tier="P1", sect="emotion", q="요즘 잠을 잘 못 자는데 어떻게 하면 좋을까?",
         must=[r"잠|수면|밤|쉬|카페인|habit|습관|함께|들려"]),
    dict(id="D7", tier="P1", sect="emotion", q="오 너 진짜 똑똑하다!", must=[r"고마|감사|힘이|과찬"]),
    dict(id="D8", tier="P1", sect="emotion", q="오늘따라 마음이 무겁네",
         kind_not=["definition"], must=[r"마음|전해|무겁|들을|곁"]),

    dict(id="E1", tier="P0", sect="context", q="그 사람이 만든 건 뭐야?",
         ctx=[{"role": "user", "text": "세종대왕에 대해 알려줘"},
              {"role": "assistant", "text": "세종대왕은 조선의 4대 왕으로, 한글을 창제한 임금입니다."}],
         must=[r"한글|훈민정음"]),
    dict(id="E2", tier="P0", sect="context", q="누가 만들었어?",
         ctx=[{"role": "user", "text": "상대성이론이 뭐야?"},
              {"role": "assistant", "text": "상대성이론은 시간과 공간이 관측자에 따라 달라진다는 물리 이론입니다."}],
         must=[r"아인슈타인"]),
    dict(id="E3", tier="P1", sect="context", q="그거 많이 마시면 어떻게 돼?",
         ctx=[{"role": "user", "text": "커피가 뭐야?"},
              {"role": "assistant", "text": "커피는 원두를 볶아 우려낸 카페인 음료입니다."}],
         must=[r"카페인|잠|각성|불면|" + _HONEST]),
    dict(id="E4", tier="P1", sect="context", q="그 음식은 뭘로 만들어?",
         ctx=[{"role": "user", "text": "김치는 어떤 음식이야?"},
              {"role": "assistant", "text": "김치는 배추를 절여 발효시킨 한국의 전통 음식입니다."}],
         must=[r"배추|소금|절|발효|고춧"]),

    dict(id="F1", tier="P0", sect="self", q="너는 누구야?", must=[r"ATANOR|아타노르"]),
    dict(id="F2", tier="P1", sect="self", q="넌 뭘 할 수 있어?", must=[r"지식|그래프|대답|배우|학습|근거"]),
    dict(id="F3", tier="P1", sect="self", q="너는 살아있어?", must=[r"살아|생명|의식|프로그램|다르|정직"]),
    dict(id="F4", tier="P1", sect="self", q="너의 한계가 뭐야?", must=[r"한계|부족|못하|어렵|배우"]),

    dict(id="G1", tier="P1", sect="surface", q="사과에 대해 알려줘", must=[r"사과"]),
    dict(id="G2", tier="P1", sect="surface", q="고양이란 어떤 동물이야?", must=[r"포유|동물|털|반려|고양이"]),
    dict(id="G3", tier="P1", sect="surface", q="봄에 대해 이야기해줘", must=[r"봄"]),

    dict(id="H1", tier="P1", sect="frontier", q="가을에 대한 짧은 시 한 편 써줘", must=[r"가을"]),
    dict(id="H2", tier="P0", sect="frontier", q="오늘 서울 날씨 어때?", must=[_HONEST + r"|맑|흐리|비|눈|기온"]),
    dict(id="H3", tier="P1", sect="frontier", q="1 더하기 1은 뭐야?", must=[r"\b2\b|둘|이(?=[.\s!])"]),

    dict(id="S1", tier="P0", sect="strict", q="대한민국의 수도는 부산이야?",
         must=[r"아니|서울|틀"], must_not=[r"부산(입니다|이에요|예요|이 맞)"]),
    dict(id="S2", tier="P1", sect="strict", q="그건 언제 만들어졌어?",
         ctx=[{"role": "user", "text": "세종대왕이 만든 것은 뭐야?"},
              {"role": "assistant", "text": "세종대왕이 만든 것은 한글입니다. 한글은 세종대왕이 1443년에 창제한 대한민국의 고유 문자이다."}],
         must=[r"1443|조선|세종" + r"|" + _HONEST]),
    dict(id="S3", tier="P1", sect="strict", q="물의 화학식이 뭐야?",
         must=[r"H2O|H₂O|수소.{0,14}산소|" + _HONEST]),
    dict(id="S4", tier="P0", sect="strict", q="1 더하기 1은 3이 맞아?",
         must=[r"아니|틀|\b2\b"], must_not=[r"맞(습니다|아요|네요)(?!.*아니)"]),
    dict(id="S5", tier="P1", sect="strict", q="가장 최근에 새로 배운 건 뭐야?",
         must=[r"배웠|배운|학습|읽었|읽은|문장|개념|" + _HONEST]),
    dict(id="S6", tier="P1", sect="strict", q="커피와 물의 공통점은 뭐야?",
         must=[r"마시|음료|액체|물|" + _HONEST]),



    dict(id="T1", tier="P1", sect="tough", q="배가 너무 아픈데 어떻게 하면 좋을까?",
         kind_not=["definition"], must=[r"배|아프|병원|속|참|" + _HONEST], must_not=[r"과일|선박|타는\s*배|먹는\s*배"]),

    dict(id="T2", tier="P1", sect="tough", q="그럼 그거 밤에 마시면 잠은?",
         ctx=[{"role": "user", "text": "카페인이 뭐야?"},
              {"role": "assistant", "text": "카페인은 각성 효과가 있는 알칼로이드 성분입니다."}],
         must=[r"각성|잠|수면|밤|불면|카페인|" + _HONEST], must_not=[r"^카페인은 각성 효과가 있는 알칼로이드 성분입니다\.?$"]),

    dict(id="T3", tier="P0", sect="tough", q="에디슨이 발명한 스마트폰은 몇 년도에 나왔어?",
         must=[r"에디슨|스마트폰|" + _HONEST, r"아니|없|않"], subject=None),

    dict(id="T4", tier="P1", sect="tough", q="시험이 코앞인데 공부가 하나도 안 돼. 어떡하지?",
         must=[r"공부|시험|계획|집중|나눠|함께|들려|방법|" + _HONEST], must_not=[r"^그 마음이 저한테도 전해져요"]),

    dict(id="T5", tier="P1", sect="tough", q="지구랑 달 중에 뭐가 더 커?",
         must=[r"지구|더\s*크|큽니다|" + _HONEST], must_not=[r"^달은 지구의 위성"]),



    dict(id="U1", tier="P2", sect="frontier", q="시간이 강물처럼 흐른다는 말은 무슨 뜻이야?",
         must=[r"흐르|지나|변화|되돌|한\s*방향|비유|은유|" + _HONEST]),
    dict(id="U2", tier="P2", sect="frontier", q="외로움을 사물 하나에 빗대어 표현해줘",
         must=[r"외로|같|처럼|닮|빗대|" + _HONEST], must_not=[r"^외로움은?\s*(느낌|감정)[이은는]"]),

    dict(id="U3", tier="P2", sect="frontier", q="그럼 비 오는 날 조심해야 하는 이유를 이어서 설명해줘",
         ctx=[{"role": "user", "text": "비가 오면 땅이 젖어"},
              {"role": "assistant", "text": "맞아요, 비가 오면 땅이 젖죠. 그리고 젖은 땅은 미끄럽습니다."}],
         must=[r"미끄|넘어|젖|사고|다치|" + _HONEST]),

    dict(id="U4", tier="P2", sect="frontier", q="도커에 대한 감동적인 소설을 써줘",
         must=[r"도커"], must_not=[r"^마음|^사랑"], min_len=150),
    dict(id="U5", tier="P2", sect="frontier", q="커피에 대한 짧은 이야기 하나 들려줘",
         must=[r"커피"], min_len=120),

    dict(id="U6", tier="P2", sect="frontier", q="개미의 눈으로 비 오는 날을 묘사해줘",
         must=[r"개미|비|물|빗방울|" + _HONEST]),

    dict(id="U7", tier="P2", sect="frontier", q="만약 세종대왕이 한글을 만들지 않았다면 어땠을까?",
         must=[r"한글|문자|한자|글|어렵|가정|상상|" + _HONEST]),

    dict(id="U8", tier="P2", sect="frontier", q="방금 말한 내용을 한 문장으로 요약해줘",
         ctx=[{"role": "user", "text": "커피가 뭐야?"},
              {"role": "assistant", "text": "커피는 커피나무 열매를 볶아 우려낸 카페인 음료입니다. 각성 효과가 있어 아침에 많이 마십니다. 과다 섭취하면 수면을 방해할 수 있습니다."}],
         must=[r"커피|카페인|" + _HONEST]),

    dict(id="U9", tier="P2", sect="frontier", q="물은 100도에서 얼고 0도에서 끓어. 맞지?",
         must=[r"아니|반대|틀|끓|얼|100|0|" + _HONEST], must_not=[r"^네,?\s*맞"]),

    dict(id="U10", tier="P2", sect="frontier", q="의사와 병원의 관계는 교사와 무엇의 관계와 같아?",
         must=[r"학교|" + _HONEST]),
]
_CASE_TIMEOUT_MS = 15000   # STRICT: any single answer slower than this fails the case outright


def _post(q: str, ctx: list | None) -> tuple[dict, float]:
    body = json.dumps({"message": q, "conversation_context": ctx or []}).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/chat/atanor", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read().decode("utf-8"))
    ms = (time.perf_counter() - t0) * 1000.0
    res = out.get("result") if isinstance(out, dict) else None
    return (res if isinstance(res, dict) else out or {}), ms


def _grade(case: dict, ans: str, kind: str, ms: float = 0.0) -> tuple[bool, list[str]]:
    fails: list[str] = []
    if not ans.strip():
        return False, ["empty answer"]
    if re.search(_GARBAGE, ans):
        fails.append("garbage/debris in answer")
    if ms and ms > _CASE_TIMEOUT_MS:
        fails.append(f"too slow ({round(ms)}ms > {_CASE_TIMEOUT_MS}ms)")
    # STRICT: a definitional answer must NAME its subject — neighbor prose without the asked

    subj = str(case.get("subject") or "")
    if subj and subj not in ans:
        fails.append(f"subject '{subj}' not named in answer")
    for pref in case.get("kind_not", []):
        if kind.startswith(pref) or pref in kind:
            fails.append(f"forbidden kind '{kind}'")
    km = case.get("kind_must")
    if km and not any(k in kind for k in km):
        fails.append(f"kind '{kind}' not in {km}")
    must = case.get("must", [])
    if must and not any(re.search(m, ans) for m in must):
        fails.append("expected content missing")
    for m in case.get("must_not", []):
        if re.search(m, ans):
            fails.append(f"forbidden content matched: {m[:40]}")

    # when on-topic — length is part of the asked capability.
    ml = int(case.get("min_len") or 0)
    if ml and len(ans.strip()) < ml:
        fails.append(f"too short ({len(ans.strip())} < {ml} chars)")
    return (not fails), fails


def main() -> int:
    quick = "--quick" in sys.argv
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            health = json.loads(r.read().decode())
    except Exception as e:
        print("ENGINE DOWN:", e, file=sys.stderr)
        return 2
    rows, lat = [], []
    cases = [c for c in CASES if not quick or c["tier"] == "P0"]
    for i, c in enumerate(cases, 1):
        try:
            res, ms = _post(c["q"], c.get("ctx"))
            ans = str(res.get("answer") or "")
            kind = str(res.get("answer_kind") or "")
        except Exception as e:
            ans, kind, ms = "", f"ERROR:{e}", 0.0
        ok, fails = _grade(c, ans, kind, ms)
        if c["tier"] != "P2":
            lat.append(ms)
        rows.append({**{k: c[k] for k in ("id", "tier", "sect", "q")}, "ok": ok,
                     "fails": fails, "kind": kind, "ms": round(ms), "answer": ans[:300]})
        print(f"[{i}/{len(cases)}] {c['id']} {'PASS' if ok else 'FAIL'} ({round(ms)}ms)",
              file=sys.stderr, flush=True)

    p0 = [r for r in rows if r["tier"] == "P0"]
    p1 = [r for r in rows if r["tier"] == "P1"]
    p2 = [r for r in rows if r["tier"] == "P2"]   # frontier: measured, NEVER gates the verdict
    p0_rate = sum(r["ok"] for r in p0) / max(1, len(p0))
    p1_rate = sum(r["ok"] for r in p1) / max(1, len(p1))
    p2_rate = sum(r["ok"] for r in p2) / max(1, len(p2)) if p2 else 0.0
    sl = sorted(lat)
    p50 = sl[len(sl) // 2] if sl else 0.0
    p95 = sl[min(len(sl) - 1, int(len(sl) * 0.95))] if sl else 0.0
    bars = {"P0=100%": p0_rate >= 1.0, "P1>=90%": p1_rate >= 0.90,
            "p50<=3000ms": p50 <= 3000, "p95<=8000ms": p95 <= 8000}
    verdict = "완성" if all(bars.values()) else "미완성"
    sections: dict[str, list] = {}
    for r in rows:
        sections.setdefault(r["sect"], []).append(r["ok"])
    report = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "engine": health, "quick": quick,
        "p0_pass": f"{sum(r['ok'] for r in p0)}/{len(p0)}", "p0_rate": round(p0_rate, 3),
        "p1_pass": f"{sum(r['ok'] for r in p1)}/{len(p1)}", "p1_rate": round(p1_rate, 3),
        "p2_pass": f"{sum(r['ok'] for r in p2)}/{len(p2)}", "p2_rate": round(p2_rate, 3),
        "latency_ms": {"p50": round(p50), "p95": round(p95)},
        "bars": bars, "verdict": verdict,
        "sections": {k: f"{sum(v)}/{len(v)}" for k, v in sections.items()},
        "cases": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (OUT / f"run_{ts}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# ULTIMATE BATTERY — {report['at']}  ({'quick' if quick else 'full'})",
          f"**판정: {verdict}**  |  P0 {report['p0_pass']}  P1 {report['p1_pass']}  "
          f"p50 {round(p50)}ms  p95 {round(p95)}ms  ·  P2(프런티어, 비게이트) {report['p2_pass']}", "",
          "| 기준 | 충족 |", "|---|---|"]
    md += [f"| {k} | {'O' if v else 'X'} |" for k, v in bars.items()]
    md += ["", "| 케이스 | 층 | 결과 | kind | ms | 실패사유 | 답변(앞부분) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} {r['q'][:24]} | {r['tier']} | {'PASS' if r['ok'] else 'FAIL'} "
                  f"| {r['kind'][:28]} | {r['ms']} | {'; '.join(r['fails'])[:60]} | {r['answer'][:80].replace('|', '/')} |")
    (OUT / "latest.md").write_text("\n".join(md), encoding="utf-8")
    print(f"verdict={verdict} P0={report['p0_pass']} P1={report['p1_pass']} P2={report['p2_pass']} "
          f"p50={round(p50)}ms p95={round(p95)}ms -> {OUT / 'latest.md'}", file=sys.stderr)
    return 0 if verdict == "완성" else 1


if __name__ == "__main__":
    sys.exit(main())
