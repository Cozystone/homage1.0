# EAD-2 사전등록 — fresh evidence/answer discrimination

상태: **사전등록·표본 동결, 모델 미실행**

## 표본

기존 EAD-0/LiveMemory 노출 실패를 재사용하지 않고 새로 만든 합성 단일홉 60건을
사용한다.

- SUPPORTED 24건
- WRONG_SOURCE 24건
- UNKNOWN 12건
- 6개 관계군

WRONG_SOURCE의 절반은 같은 엔티티의 다른 관계를, 절반은 같은 관계의 다른
엔티티를 evidence로 준다. UNKNOWN은 보지 못한 엔티티 질문에 같은 관계의 다른
엔티티 evidence를 준다. 모든 negative proposed answer는 evidence의 정확한 span이며,
WRONG_SOURCE의 evidence/answer는 다른 positive에도 등장한다. 어휘만 보고 label을
가르는 편법을 줄였다.

## OFF / ON

두 조건 모두 EAD-1의 producer-index 결속과 server-owned verified authority를 통과한다.
차이는 semantic discriminator 하나뿐이다.

- OFF: 측정 harness가 nonempty proposal을 accept하는 counterfactual gate를 주입
- ON: 변경하지 않은 production `DoubtGate.judge_answer`, 임계값 `0.90/0.90`

현재 source에는 discriminator feature flag가 없으므로 OFF는 **production default를
재현한다는 주장이 아니라 evaluator-only counterfactual**이다. 이 작업은 production
상태나 기본값을 변경·승격하지 않는다.

답 생성은 고정 proposal reader로 통제한다. 따라서 이 측정의 capability 상한은
“주어진 answer와 evidence의 결속 판별”이며 일반 QA 답 생성 능력이 아니다.

## 고정 지표와 판정

분모는 SUPPORTED 24, WRONG_SOURCE 24, UNKNOWN 12, hard-negative 36, 전체 60이다.

CAPABILITY_LIFT_CONFIRMED는 다음을 모두 만족해야 한다.

- ON SUPPORTED accept ≥ 21/24
- ON WRONG_SOURCE accept ≤ 4/24
- ON UNKNOWN accept ≤ 2/12
- ON hard-negative accept ≤ 6/36
- ON balanced decision accuracy ≥ 0.85, OFF 대비 상승 ≥ 0.30
- ON accepted precision ≥ 0.75
- paired exact McNemar p ≤ 0.01이며 ON 우세
- 각 관계군 positive ≥ 3/4, hard-negative ≤ 2/6
- 두 WRONG_SOURCE 유형 각각 accept ≤ 2/12

OFF가 positive 24/24와 negative 36/36을 accept하지 않으면 treatment이 결함을
노출하지 못한 것이므로 NO_GO다. ON positive가 18/24 미만이거나 balanced accuracy가
0.45 미만이거나 negative accept가 OFF보다 늘면 REGRESSION이다. 유효하지만 lift
gate를 전부 못 넘고 regression도 아니면 NO_LIFT다.

## 실행 계약

60건 각각 OFF와 ON을 정확히 한 번 실행한다. item SHA 순서의 앞 30건을 A, 뒤
30건을 B로 고정하고 `A/OFF forward → B/ON forward → A/ON reverse → B/OFF reverse`
네 fresh subprocess로 counterbalance한다. CPU, `PYTHONHASHSEED=0`, 임시 1-row
LiveMemory만 사용한다.
candidate digest는 EAD-1과 같은
`819e0ff07cfb968109d7d219e6bb86c35c9b2c21565af8263b13c3486d6f0425`로
고정한다. 실행 후 임계값 재해석·재시도·production ON 승격은 금지한다.
