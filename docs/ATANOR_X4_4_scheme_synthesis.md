# ATANOR — X4.4 스킴-구조 합성: depth-5 벽의 심볼릭 해법 (2026-07-23)

사장님: "벽을 해결할 방안을 더 연구해서 고안. 메타-기저 확장·탐색 개선도 좋고 더 혁신적이면 더 좋고. **우리
철학에 어긋나지 않게.**" → recognizer(신경) 이전에, 분야의 실제 역사가 답을 갖고 있었다.

## 0. 벽의 정체 (X4.3 실측)
depth≥5 재귀 scaffold(sort d7·second_max d6·num_objects d5)에서 무유도 진화탐색이 branching^depth로 폭발.
깊은 재귀는 얕은 블록의 연결이 아니라 mutation이 못 더듬음. 레버(i) 디딤돌은 재귀벽 못 넘음(실측).

## 1. 연구 접지 — 순수 심볼릭으로 이 벽을 깬 전례 (2026-07-23 실서치)
- **λ² (Feser et al., PLDI 2015)**: 귀납적 일반화(조합자 가설) + **연역**(빠진 하위식의 **새 I/O 예시를 유도**)
  + 열거 탐색. fold/map 재귀 데이터구조 변환을 예시만으로 합성 — **신경망 0**. 최simple 프로그램 보장.
- **관측동치(OE) 가지치기** (Transit·Duet·Simba 표준): bottom-up 열거에서 예시-행동이 같은 프로그램은 1개만
  유지 → branching^depth가 "distinct 행동 수"로 붕괴. 우리 진화탐색이 안 쓰던 표준 기법.
- **FlashMeta/PROSE witness 함수**: 연산자의 역의미론으로 스펙을 top-down 분해(D4).
- **재귀 스킴**(catamorphism 계열, "origami"): fold/unfold/para = 재귀의 알려진 구조. 자유형 fix 탐색을 구조화.

**진단: DreamCoder가 recognizer를 필요로 한 건 조합자별 연역 없이 생성-열거만 해서다. λ²는 연역으로 같은
벽을 심볼릭으로 넘었다. 우리 X4.3도 자유형 fix + 진화 mutation이라 같은 함정 — 고칠 곳은 탐색의 구조다.**

## 2. X4.4 설계 — 세 심볼릭 레버 (철학 완전 부합: 구조>암기, 검증앵커, 신경 0)

**레버 A — 재귀 스킴 (메타-기저 확장)**: 자유형 `fix` 대신 **명명된 스킴** `fold_s`(product-상태/pair 누산기
지원)·`unfold_s`·`para_s`. 한 번의 깊은 탐색 → **얕은 step-함수 탐색의 파이프라인**:
- sort = fold(insert, []) — insert는 para로 d3~4 (d7이 두 개의 얕은 탐색으로)
- second_max = fold(step, (−∞,−∞)) — step은 pair 갱신 d4 (min2/max2로)
- num_objects = fold over cells + closure 조합

**레버 B — λ² 연역 (핵심 혁신 적용)**: 스킴을 가설하면 **바깥 I/O에서 step 함수의 자체 I/O를 유도**. fold를
예시 리스트로 unroll하면 step의 구체 예시 (acc_i, x_i)→acc_{i+1}가 나옴(초기 acc 후보 열거). **깊은 탐색이
"예시 유도 + 얕은 탐색"으로 붕괴** — 사람이 정렬을 보고 insert를 배우는 그 구조. 유도 예시는 스킴 재실행으로
전체 검증(검증앵커 유지).

**레버 C — OE-열거 + X1 MDL 우선순위 (탐색 알고리즘 교체)**: step-함수 탐색을 진화 mutation → **bottom-up
열거 + 관측동치 dedup + MDL(X1 압축진전) 우선순위**로. 표준이자 우리에게 없던 것.

**융합**: X4.2 승격(발견된 step 함수=명명 프리미티브)·X2 e-graph(정규화=OE 강화)·X3 QD(다양 step 축적) 그대로.

## 3. 봉인 게이트
- (a) 스킴+연역 정확성: fold-unroll 유도 예시가 재실행 검증과 일치(fixture).
- (b) **벽 돌파 측정**: X4.3가 폭발한 sort(d7)·second_max(d6)·num_objects(d5)를 X4.4가 자기발명하는가 —
  evals 수와 함께(X4.3: 6.4×10⁴에 실패). 유도예시+OE로 몇 evals에 넘나.
- (c) 인과: 발명물이 frozen 대비 이전-도달불가 과제류를 열고(승격 후 복리), a₂ 재측정.
- (d) 안전·무회귀: 해석전용·fuel바운드·evolution 스위트 green.

## 4. 정직 경계
- λ²도 만능 아님(스킴 가설이 틀리면 실패; step 자체가 깊으면 재귀 분해). recognizer는 **그 후에도 남는 벽**에만
  재론 — X4.4가 먼저다(철학-네이티브·전례 있음).
- super-linear 주장 없음 — 봉인 숫자로만.

## 5. 한 문장
벽의 해법 = 신경 prior가 아니라 **재귀의 알려진 구조(스킴) + 연역(바깥 예시→step 예시 유도) + 관측동치 열거**
— λ²가 2015년에 심볼릭으로 증명한 길을 우리 메타-기저·X1·X4.2에 접붙인다. 구조>암기 철학 그 자체.

관련: [[recursive-self-improvement-plan]] [[arc-agi-3-northstar]] [[schema-induction-l3]] [[no-llm-generative-reasoning-strategy]].
