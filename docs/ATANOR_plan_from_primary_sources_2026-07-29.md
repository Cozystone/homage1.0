# 원문에서 다시 뽑은 계획 (2026-07-29)

앞선 `ATANOR_breakthrough_order_2026-07-29.md`는 **메모리 색인**에서 뽑았고 세 항목 중 셋이 낡아
있었다. 이 문서는 **1차 문서만** 읽고 다시 뽑는다. 근거 파일을 항목마다 적는다.

---

## 0. 축이 이미 옮겨갔다 — 이게 가장 큰 정정

`ATANOR_axis_v7_learned_substrate_2026-07-29.md` §0:

> *"There is no measured mechanism by which merging code produces generality... The axis moves. Not
> 'make the organs share implementations' but **'make the OBJECTS share a space, and let operations
> be transformations of that space.'**"*

**v6(코드 통합)는 v7(학습된 기판)로 대체됐다.** 그리고 v7이 근거로 제시하는 실측:

```
vsa_reasoning/fhrr_core.py : "per-symbol unit-phasor atom, DETERMINISTIC HASH SEED"
                             "Deterministic (seeded), NO TRAINING"
기판에 올라온 기관: 135 중 5
```

**모든 개념의 벡터가 그 이름의 해시다.** 똑같이 행동하는 두 개념이 직교 벡터를 받고, 철자만 닮은
두 개념이 유사 벡터를 받는다. **기하가 행동 정보를 0만큼 담고 있으므로 아무것도 그리로 이동할 수 없다.**

내가 오늘 확립한 판별-계열 추상은 v6 G2의 잔여 질문에 답한 것이고 — 유효하지만 — **축의 본류가 아니다.**

---

## 1. E5는 이미 한 번 측정됐다. 결과: REGRESSED

`axis_v7` §10 — *"the first frozen-domain transfer measurement this project has taken."*

```
                    baseline    now       verdict
coverage            0.2619      0.3690    improved  (+41%)
correct            20          28         improved  (+8)
abstention_rate     0.7381      0.6310    improved
accuracy_on_placed  0.9091      0.9032    REGRESSED (-0.006)
wrong               2           3         REGRESSED (+1)

GATE: REGRESSED       E4+ 증거 여전히 0
```

**"transfer was observed, the gate was not passed."** 아홉 개가 새로 판정됐고 그중 여덟이 맞았다
(정밀도 8/9). 게이트가 REGRESSED를 낸 것은 사전등록 서명이 *"coverage 상승 + accuracy 유지"*였고
accuracy가 떨어졌기 때문이다.

**그리고 봉인 자체에 결함이 있다고 문서가 스스로 적어놨다:**

> *"With `tolerance=0.0`, any coverage increase that is not perfectly precise reads REGRESSED...
> this seal is structurally hostile to the very improvement it was written to detect. That is a real
> fault in how I registered it — **a threshold registered without knowing the measurement's natural
> variance.**"*

그리고 **고치지 않았다**, 옳게도:

> *"Re-cutting a seal after seeing the result is what `freeze`'s refusal-to-overwrite exists to
> prevent... A tolerance that admits this trade would have to be registered on a NEW seal, before its
> first reading, and **the decision to do that is the operator's.**"*

**→ 여기가 지금 사장님 결정을 기다리는 유일한 지점이다.**

---

## 2. 순서 (원문 근거 있음)

### ① 새 봉인의 허용오차를 **데이터에서** 재고, 등록 여부를 결정 — 결정은 사장님
- **근거**: `axis_v7` §10 "the decision to do that is the operator's"
- **내가 할 수 있는 것**: 허용오차를 *고르지* 않고, 재현 실행으로 accuracy_on_placed의 **자연 변동폭**을
  실측한다. 그러면 새 봉인의 tolerance가 선택이 아니라 측정에서 나온다 — 오늘 사후분석 교정 2번
  ("측정된 널에 등록")의 요구 그대로.
- **내가 할 수 없는 것**: 그 봉인을 잘라 붙이는 것. 결과를 본 뒤 봉인을 다시 자르는 것을 막는 규칙이
  나에게 불리할 때도 똑같이 적용된다.
- **돌파 판정**: 새 봉인이 등록되고, 그 첫 읽기에서 게이트가 통과하거나 왜 아닌지가 나온다.

### ② 도메인 B의 라벨 결함 수리
- **근거**: `axis_v7` §10 "Route (b) is blocked, and the blocker is a defect in how I built B" —
  세 오답이 전부 **B의 라벨이 틀린 것**이었다(Deposition은 painting이 맞고 B는 literary work,
  Traveler는 literary work가 맞고 B는 video game).
- **효과**: 라벨이 맞으면 accuracy_on_placed의 분모가 정직해지고, ①의 재봉인 없이도 route (b)가 열린다.
- **돌파 판정**: B의 라벨을 원 출처로 재검증하고, 정정 뒤 baseline을 다시 읽는다. **B를 편집하는 것이
  아니라 B의 정답지를 고치는 것**이므로 봉인 규칙과 충돌하지 않는다 — 다만 이것도 사전등록이 필요하다.

### ③ v7의 본류: 기판 벡터를 **이름 해시에서 행동 학습으로**
- **근거**: `axis_v7` §1. 지금 벡터는 이름 해시라 행동 정보 0.
- **효과**: 이게 v7 가설의 전부다. 성공하면 "객체가 공간을 공유"가 실물이 되고, 실패하면 v7이 죽는다.
- **오늘 나온 벽돌 하나**: `decisive_kind`가 그래프 개체와 연속 속도 히스토그램을 **같은 함수로**
  채점했고, 신호 있는 곳(kind, coverage 1.000)에서 판정하고 없는 곳(role, coverage 0.000)에서
  **전부 기권**했다. *"one rule spanning two modalities, which is less than fusion and is not nothing."*
- **돌파 판정**: 학습된 벡터에서, 같은 행동을 하는 두 개념의 코사인이 이름-해시 대비 유의하게 높다.
  대조군 = 현재의 해시 기판.

### ④ 융합 시험대 — Realcity는 탈락
- **근거**: `axis_v7` §12 *"It says **Realcity cannot be the testbed for it**"* — 물리↔기호 결합이
  `zone(dist) → role pool`뿐이고 상한 0.275, 기호 쪽은 그래프 없는 역할 문자열.
- **필요 조건(문서가 명시)**: *"objects that are simultaneously graph entities with real predicate
  behaviour AND things with trajectories."*
- **상태**: 그런 시험대가 **없다.** CARLA/City Sample 물체는 그래프에 없고, 그래프 개체는 궤적이 없다.
- **돌파 판정**: 두 조건을 동시에 만족하는 시험대를 하나 만들거나 찾는다. 이게 ③보다 먼저 필요할 수 있다.

### ⑤ 벤치마크
- ①~③ 뒤. **지식-MCQ는 No-LLM으로 못 이긴다는 실측이 이미 있다** — 기대치를 거기 두지 않는다.

---

## 3. 오늘(2026-07-29) 이 세션이 더한 것 — 위 순서와의 관계

| 항목 | 상태 | 위 순서와의 관계 |
|---|---|---|
| **M1 conformal 증명서** | GREEN (α=0.10, 오류 0.89%, 상한 1.07%, 기권 31%) | 로드맵 v3 국면 M. **자가진화 해제의 문** |
| **자기검사 게이트** | 권한 획득 (5/5 차단, 2/2 통과) | 승격 승인의 자동화. 오늘 실제로 내 버그 2개 차단 |
| **판별-계열 추상** | 확립 (재현 정확, 대조군 상회) | v6 G2의 잔여 질문에 답. **v7 본류는 아님** |
| **시각 손잡이** | 지속·위치 ✓, 정체 약함(갤러리 15.5%) | 위 ④의 부품이 될 수 있음 |
| **물체 발견** | 보류(코퍼스 부적합) | ④가 풀리면 같이 풀림 |

---

## 4. 내가 반복한 실수, 계획 수립에서

세 항목 중 셋이 낡았고 원인이 같다: **색인을 읽고 원문을 끝까지 안 읽었다.** 세션 내내
"데이터 확인 전에 알고리즘 측정"을 세 번 진단해 놓고, 계획에서 같은 형태를 세 번 더 했다.

**규칙으로 승격한다: 계획의 각 항목은 1차 문서의 줄을 근거로 달고, 그 문서의 끝까지 읽은 뒤에만 오른다.**
이 문서의 모든 항목에 근거 파일과 인용이 붙어 있는 이유다.

---

## 5. 주장하지 않는 것

E5가 곧 통과할 것. 봉인 재등록이 옳은 결정이라는 것(사장님 몫). v7이 성립할 것.
융합 시험대가 존재한다는 것. 오늘 더한 셋이 E4+ 증거라는 것 — **E4+ 증거는 여전히 0이다.**
