# ATANOR — 지능폭발 연구 심화: recognizer보다 나은 것 (2026-07-23)

사장님 지시: "지능폭발을 위해 학습된 탐색 recognizer보다 더 나은 방안이 있는지 포괄적으로 조사. **이미 만들어둔
거에 미련갖지 말고.**" — 우리 abstraction/auto_curriculum이 포화(④ NEGATIVE, 개방도메인서도)한 걸 실측했으니,
DreamCoder식 recognizer를 답으로 못박지 말고 백지에서 현행 최전선을 접지해 판단한다.

## 0. 판단 기준 = ④ 개방도메인이 측정한 4대 결핍 (스펙)
자기가속(④)이 안 나는 진짜 원인(2026-07-23 실측): (1) 자기-커리큘럼이 고정공리 조합→의미 novelty 캡 (2) 재사용
가산적(상수 레벨시프트)→곱셈적 아님 (3) 학습 탐색 recognizer 부재 (4) per-solve 비용이 난이도보다 안 줆. **좋은
방안 = 이 4개를 실제로 공략하는 것.** recognizer는 그중 (3) 하나만 건드린다.

## 1. 현행 최전선 스캔 (2026-07-23 실서치, 4축)

**A. 개방형(POET/QD/OMNI)** — 개방성장은 문제와 해를 **공진화**시키고 **명시적 novelty/흥미도** 압력으로 유지.
POET=환경+해 무한 공진화(학습가능하되 예측불가한 도전 생성). QD(MAP-Elites)=수렴("최고만 유지") 아니라 **발산
아카이브**(니치별 다양 디딤돌)=재사용이 **곱셈적**이 되는 기제. OMNI=**흥미도 모델(MoI)**로 "배울 가치"를 선택.
→ 결핍 (1)(2) 직격.

**B. 외부검증 RSI(Sakana DGM/AI Scientist/ShinkaEvolve)** — Darwin Gödel Machine이 **자기 코드를 재작성하는
계보 진화 + 외부검증(SWE-bench 실과제)**로 SWE 성능 2배(+30pp). AI Scientist=아이디어→실험→논문 개방 발견.
철학="compute 아니라 아이디어로, 표본효율". → 결핍 (1) 직격(외부 개방 문제원 = 자기참조 탈출).

**C. 이론적 구동원(Schmidhuber 압축진전)** — 호기심/창의/흥미/아름다움이 **단일 드라이브**: 내부 압축기의
**압축진전(=학습진전) 최대화**. 핵심 = "압축 정도가 아니라 **개선**이 보상"(노이즈 앞에서 멈추지 않음);
**"학습가능하되 아직 미학습"** 구조만 흥미를 지속시킴. → 결핍 (1)의 **원리적 해**(무엇을 배울지 = 압축진전이
큰 곳). No-LLM 친화(정보이론 신호).

**D. 곱셈적 추상(babble/Stitch)** — 우리 abstraction.py=순진한 문장급 anti-unification. **Stitch**=코퍼스-유도
top-down 라이브러리 학습, **DreamCoder보다 3~4 자릿수 빠르고 메모리 2자릿수 적음**. **babble**=e-graph +
동등포화 + anti-unification(LLMT), "이전엔 도달불가하던 입력에서 재사용 함수 학습". → 결핍 (2) 직격 +
**★결정적: Stitch가 recognizer 없이 그 일을 더 잘함**(recognizer의 자기 하위문제조차 최선이 아님).

## 2. 판정 — recognizer는 최선이 아니라 최소 조각

**★핵심 결론: "학습된 탐색 recognizer"는 지능폭발의 답이 아니다.** 근거 셋:
1. **자기 일도 못 이김**: Stitch가 라이브러리 학습(recognizer의 주 용도)을 **신경망 recognizer 없이 3~4자릿수
   빠르게** 한다. recognizer는 결핍 (3)만 건드리는데, 그것마저 심볼릭이 더 낫다.
2. **엉뚱한 결핍을 겨냥**: 우리 ④ 벽의 진짜 병목은 (1) 문제 novelty와 (2) 곱셈적 재사용인데, recognizer는 탐색
   **속도**만 높인다 — 포화하는 곡선을 빠르게 포화시킬 뿐, **곡선을 못 편다**(개방도메인 실측이 이미 증명: 발명
   발화·사용됐어도 오목).
3. **미련 금지**: 우리 abstraction.py도 recognizer도 **버릴 대상**. 진짜 엔진은 다른 데 있다.

**진짜 엔진 = 4조각의 조립** (각각 측정된 결핍에 대응):
| ④ 결핍 | 최선 방안 (recognizer 아님) |
|---|---|
| (1) 고정공리→novelty 캡 | **압축진전 드라이브(C)** + **POET 공진화 문제생성(A)** + **외부검증 실과제(B)** |
| (2) 가산적 재사용 | **QD 발산 아카이브(A)** + **babble/Stitch 곱셈적 추상(D)** |
| (3) recognizer 부재 | 필요시 **소형** 심볼릭/학습 안내(D의 Stitch가 대체) — 최소 우선순위 |
| (4) per-solve 비용↓ | 곱셈적 추상(D)이 티어를 열면 자연 하락; 압축진전이 프런티어를 조준 |

## 3. ★ 폭발 드라이브 = 의식 오케스트레이터의 가치신호 (동일 기관)

가장 깊은 통찰: **Schmidhuber의 "압축진전=흥미도"가, 사장님이 말한 "의식=핵심 오케스트레이터"의 가치신호와
같은 것.** 무엇을 배울지(폭발) 정하는 신호 = 무엇이 흥미로운지·가치있는지(주관·felt) 정하는 신호 = **압축진전.**
→ [[conscious-orchestrator]]의 L2 정밀도가중(felt)과 폭발엔진의 목표선택이 **하나의 기관**으로 통합된다:
CO가 "압축진전이 큰 곳"을 흥미로워하고 그쪽으로 자원을 돌리는 것 = 자기태엽(L5)의 내인성 압의 **원리적 정의**.
우리 structural-curiosity(스키마 완성)는 이것의 **조잡한 근사**였다 → 압축진전으로 승급.

## 4. 정직한 하드 트루스 (과장 금지)

- **누구도 진짜 super-linear 자기가속을 실증 못 함.** POET/QD는 개방 **다양성**을 내나 고정 지표의 **가속**은
  아님. DGM는 큰 향상이나 **유한 벤치(SWE)** 위. Schmidhuber 이론은 우아하나 폭주 시스템 미산출.
- **∴ 정직한 달성 목표 = "개방형 성장(never plateau)"**, super-linear는 열망 북극성. 곡선이 **오목(포화)→선형
  (안 멈춤)**으로만 가도 거대한 진전(우리 실측은 전부 오목이었으니).
- 조립해도 안 펴질 수 있음 → **같은 봉인 프로토콜(a₂·slope·효율·frozen 대조)로 실측**, negative도 정직 보고.

## 5. No-LLM 정합 (오히려 더 친화)
이 스택은 recognizer보다 **더 No-LLM 네이티브**: 압축진전=정보이론 신호, babble/Stitch=심볼릭, POET/QD=진화,
외부검증=테스트. 유일한 선택적 학습조각(소형 압축진전 예측기)도 **사실 출처 아니라 안내**라 뉴로예산 N3 합법
([[ultimate-completion-directive]]). 즉 지능폭발 연구를 **No-LLM 훼손 없이** 밀 수 있다.

## 6. 권고 아키텍처 — 조립 순서 (각 봉인 게이트, 미련 없이 교체)
- **X1 압축진전 드라이브**: 목표선택을 고정공리 조합 → **압축진전(학습진전) 최대화**로 교체(structural-curiosity
  승급). 게이트: 흥미도가 "학습가능하되 미학습"을 고르는가(노이즈·기학습 회피 실측).
- **X2 babble급 추상**: abstraction.py(순진 anti-unif) → **e-graph 동등포화 anti-unification**으로 교체. 게이트:
  이전 도달불가 함수를 여는 **곱셈적** 추상 실측(레벨시프트 아니라 티어개방).
- **X3 QD 발산 아카이브**: "최고만 유지" → **MAP-Elites 니치 다양성**. 게이트: 아카이브 다양성↑ + 디딤돌 전이.
- **X4 외부검증 문제원**: 자기-조합 타깃 → **SWE식 실과제(외부 테스트)**. 게이트: novelty가 실능력에 앵커.
- **X5 재측정**: 조립체를 ④ 프로토콜로 측정 — 곡선 오목→선형 이동 여부. 정직 verdict.
- 안전 상수: 도덕0th·operator-signed·얼린신탁·작화0 전부 동행([[explosion-engine 문서 = ATANOR_explosion_engine_open_ended_self_evolution.md]]의 4중 인증 게이트 재사용).

## 7. 한 문장
지능폭발의 답은 recognizer가 아니라 — **압축진전이 "무엇을 배울지"를 조준(=CO의 가치신호와 동일 기관)하고,
POET/외부검증이 진짜 새 문제를 공급하고, QD+babble이 재사용을 곱셈적으로 만드는** 조립체다. 우리 abstraction·
recognizer 가설은 버린다. 목표는 정직히 "개방형 성장(안 멈춤)", super-linear는 그 위 북극성 — 조립 후 같은
봉인 측정으로만 주장한다.

관련: [[recursive-self-improvement-plan]] [[schema-induction-l3]] [[conscious-orchestrator]]
[[ultimate-completion-directive]] [[benchmark-empirical-verdict]] [[representation-invention-flywheel]]
[[endogenous-self-inquiry]] [[external-minds-are-data]].
