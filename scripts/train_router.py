# -*- coding: utf-8 -*-
"""Bootstrap-train the learned intent router.

Training data = slot-template synthesis (the same lexical variety the regex
lanes were written against, but EXPANDED combinatorially) + every mined failure
row in the flywheel that carries a lane label. Re-run any time; the flywheel
makes each retrain better than the last — that is the whole flywheel thesis.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.learned_router.router import train  # noqa: E402

random.seed(11)

ENTITIES = ["서울", "커피", "김치", "파이썬", "블록체인", "광합성", "인공지능", "세종대왕",
            "프랑스", "에펠탑", "숭례문", "반도체", "도커", "쿠버네티스", "참새", "나무",
            "사랑", "경제", "민주주의", "백두산", "한강", "비트코인", "태양", "달", "지구",
            "고양이", "커피나무", "손흥민", "테슬라", "삼성전자", "제주도", "불국사"]
PEOPLE = ["세종대왕", "이순신", "아인슈타인", "뉴턴", "퀴리 부인", "스티브 잡스"]
THINGS = ["자동차", "비행기", "한글", "거북선", "전구", "컴퓨터", "스마트폰"]

def _v(templates: list[str], fillers: list[str] | None = None, per: int = 6) -> list[str]:
    out = []
    for t in templates:
        if "{e}" in t and fillers:
            for e in random.sample(fillers, min(per, len(fillers))):
                out.append(t.format(e=e))
        else:
            out.append(t)
    return out


DATA: dict[str, list[str]] = {
    "identity": _v(["넌 누구니", "너는 누구야?", "너 누구야", "당신은 누구세요", "자기소개 해봐",
                    "자기소개 좀 해줘", "네 소개 좀", "너에 대해 알려줘", "who are you",
                    "introduce yourself", "what are you", "너 뭐야?", "네 정체가 뭐야",
                    "너 이름이 뭐야", "네 이름은?", "너는 뭐 하는 애야", "너 LLM이야?",
                    "너 GPT 쓰는 거 아니야?", "넌 뭘 할 수 있어?", "너 어떻게 작동해",
                    "네 구조가 궁금해", "너의 능력은 뭐야", "너 사람이야?", "너 AI야?"]),
    "meta_language": _v(["한글로 답해줘", "한국어로 말해줘", "우리말로 답해", "한국어로 답해줄래",
                         "영어로 답해줘", "영어로 말해봐", "영문으로 답변해줘", "answer in english",
                         "reply in korean", "say it in english", "explain in korean",
                         "이제부터 한국어로 해줘", "영어로 설명해줘", "한국말로 다시 말해줘",
                         "이거 한국말로 해줄 수 있어?", "방금 거 한글로 다시", "영어로 바꿔서 말해봐",
                         "한국어 버전으로 알려줘", "그거 영어로 뭐라고 해야 돼"]),
    "greeting": _v(["안녕", "안녕하세요", "하이", "헬로", "반가워", "반갑습니다", "ㅎㅇ",
                    "hi", "hello", "hey there", "good morning", "좋은 아침이야",
                    "잘 지냈어?", "오랜만이야 안녕"]),
    "social": _v(["고마워", "고마워!", "감사합니다", "정말 고맙다", "thanks a lot", "thank you",
                  "잘자", "굿나잇", "잘 자요", "수고했어", "오늘 고생 많았어", "미안해",
                  "죄송합니다", "sorry", "ㅋㅋㅋ", "ㅎㅎ", "lol", "사랑해", "네가 최고야"]),
    "creative": _v(["{e}에 대한 시 써줘", "{e} 시 한 편 지어줘", "{e} 이야기 만들어줘",
                    "{e} 노래 가사 써줘", "짧은 소설 써봐", "{e} 그림 그려줘",
                    "write me a poem about {e}", "동화 하나 지어줘", "랩 가사 만들어줘",
                    "에세이 써줘"], ENTITIES, per=4),
    "howto": _v(["{e} 설치하는 방법 알려줘", "{e} 사용하는 법", "{e} 시작하려면 어떻게 해?",
                 "{e} 만드는 방법이 뭐야", "how to install {e}", "how do i use {e}",
                 "{e} 배우려면 어떻게 해야 해", "{e} 요리하는 법 알려줘",
                 "{e} 고치는 방법 좀"], ["파이썬", "도커", "리눅스", "김치", "커피", "자전거"], per=5),
    "realtime": _v(["지금 몇 시야?", "오늘 날씨 어때?", "내일 비 와?", "오늘 서울 날씨",
                    "지금 환율 얼마야", "비트코인 시세 알려줘", "삼성전자 주가 어때",
                    "요즘 제일 인기있는 영화 뭐야", "최신 뉴스 알려줘", "현재 시간",
                    "what time is it", "today's weather"]),
    "math": _v(["3 더하기 4는?", "12 곱하기 12는 얼마야?", "100 나누기 5는", "7 빼기 3은?",
                "25 더하기 17 계산해줘", "9 곱하기 8", "1000 나누기 25는 얼마",
                "what is 3 plus 4", "56 더하기 44는?", "사과 3개에 2개 더 사면 몇 개야"]),
    "compare": _v(["{e}와 커피의 차이가 뭐야", "{e}와 파이썬의 차이점", "{e}랑 뭐가 달라",
                   "{e} vs 커피", "커피와 차 중에 뭐가 나아", "{e}와 도커 비교해줘",
                   "difference between {e} and coffee", "{e}과 김치는 어떻게 달라"],
                  ENTITIES, per=4),
    "multihop": _v(["{e}는 결국 동물인가?", "{e}는 결국 무엇인가", "{e}는 식물에 속하나요",
                    "{e}는 궁극적으로 뭐야", "{e}는 음료인가?", "{e}는 포유류에 속하나",
                    "{e}와 나무의 관계는?", "{e}는 근본적으로 무엇인가",
                    "{e}는 따지고 보면 동물 맞지?", "{e}는 포유류 맞아?", "{e}도 생물이라고 볼 수 있나",
                    "{e}는 결국 과일이라는 거지?", "{e}가 조류에 속하는 게 맞나"],
                   ["참새", "커피", "고양이", "소나무", "김치", "비둘기", "고래"], per=5),
    "definition": _v(["{e}란?", "{e}이란 뭐야?", "{e}가 뭐야?", "{e}는 무엇인가요",
                      "{e}의 뜻이 뭐야", "{e}에 대해 알려줘", "{e}에 대해 설명해줘",
                      "what is {e}", "{e} 정의 알려줘", "{e}라는 게 뭐지",
                      "{e}이 뭔지 설명해봐"], ENTITIES, per=8),
    "relation": _v(["{e}의 수도는?", "{e}의 수도가 어디야", "대한민국의 수도는?",
                    "{e}는 어디에 있어?", "{e}는 어느 나라에 있나요", "{e}의 저자는 누구야",
                    "{e}의 인구는 얼마야", "{e} 면적이 얼마나 돼", "{e}의 CEO가 누구야",
                    "{e}는 언제 세워졌어"], ["프랑스", "일본", "에펠탑", "숭례문", "테슬라",
                                          "서울", "독일", "중국"], per=5),
    "purpose": _v(["{e}는 어디에 쓰여?", "{e}의 용도가 뭐야", "{e}는 무엇에 사용돼",
                   "{e}로 뭘 할 수 있어", "{e}는 뭐에 쓰는 거야"],
                  ["망치", "커피", "파이썬", "드라이버", "가마솥"], per=5),
    "false_premise": [f"{p}이 만든 {t} 이름이 뭐야?" for p in PEOPLE for t in THINGS[:3]] +
                     [f"{p}가 발명한 {t}는 뭐야" for p in PEOPLE[:4] for t in THINGS[3:5]] +
                     ["세종대왕이 세운 회사가 어디야", "뉴턴이 개발한 앱 이름이 뭐야"],
    "command": _v(["대시보드 열어줘", "앱 실행해", "클라우드 브레인 켜줘", "open the dashboard",
                   "launch the app", "화면 닫아줘", "패널 열어봐", "start the engine",
                   "그래프 보여줘", "설정 열어줘", "학습 시작해줘", "run the daemon"]),
    "chatter": _v(["심심해", "뭐해?", "밥 먹었어?", "오늘 기분 어때", "나 우울해",
                   "재밌는 얘기 해줘", "음...", "그렇구나", "응", "알겠어", "오키",
                   "진짜?", "대박", "헐", "그래서?", "계속해봐", "아 피곤하다",
                   "요즘 잠이 안 와", "그냥 심심해서", "별일 없지?", "우와 신기하다"]),
    "temporal": _v(["2020년 {e}의 대통령은?", "현재 {e} 대통령이 누구야",
                    "2010년 {e} 국가원수는 누구였어", "{e}의 예전 수도는 어디였어",
                    "2000년 {e} 최고경영자가 누구였지", "그때 {e} 대통령이 누구였더라",
                    "5년 전 {e}의 대통령", "지금 {e} 총리는 누구야"],
                   ["대한민국", "미국", "프랑스", "일본", "애플", "독일"], per=5),
}


def main() -> None:
    rows: list[tuple[str, str]] = []
    for label, texts in DATA.items():
        for t in texts:
            rows.append((t, label))
            # noise robustness: particles/punctuation/spacing variants
            rows.append((t.rstrip("?!.") + random.choice(["", "?", "!", "..", "요"]), label))
    # flywheel gold: mined rows that carry a confirmed lane label
    fp = REPO / "data" / "flywheel" / "failures.jsonl"
    added = 0
    if fp.exists():
        for line in fp.open(encoding="utf-8"):
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("q") and row.get("lane") in DATA:
                rows.append((row["q"], row["lane"]))
                added += 1
    random.shuffle(rows)
    print(f"training rows: {len(rows)} (flywheel-added: {added})")
    result = train(rows)
    print(f"classes={result['classes']} n={result['n']} "
          f"train_acc={result['train_acc']:.3f} holdout_acc={result['holdout_acc']:.3f}")


if __name__ == "__main__":
    main()
