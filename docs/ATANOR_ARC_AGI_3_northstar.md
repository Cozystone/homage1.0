# ATANOR — ARC-AGI-3 만점 북극성 (순수피지컬, 시험특화 아님) (2026-07-23)

> Evidence correction (2026-07-25): the local ARC-AGI-1 public evaluation
> split is contamination-exposed development material, not a sealed holdout.
> Candidate code includes evaluation-informed task targeting. The current v2
> preservation receipt replays 18/400 with zero wrong fires, but this does not
> prove generalization or ARC-AGI-3 progress. Any older "sealed ARC-1" wording
> below is historical and superseded by the canonical master plan.
> ARC-AGI-3 remains a G7 north star and background evaluation program, not the
> immediate build sequence. The 2026-07-25 operator path is NL→goal compiler +
> scientific-knowledge staging → E4 → paired E5 GPQA/MMLU-Pro.

사장님: "ARC-AGI-3 벤치마크 만점을 목표로. 항상 그랬듯 시험특화가 아니라 **순수피지컬을 올려서** 고득점."
= HLE와 같은 정점 북극성 + 봉인-홀드아웃 독트린. 이 문서가 정직한 능력 경로다.

## 0. ARC-AGI-3 실체 (2026-07-23 실조사, 정확)
- **대화형(interactive) 추론 벤치**(ARC Prize, Chollet). 비디오게임식 환경 **150+**, 레벨 **1000+**. 정적
  그리드(ARC-1/2)가 아님.
- 에이전트가 **지시 없이** 환경을 탐색해 **규칙(mechanics) 발견 → 목표 즉석 추론 → 세계모델 구축 →
  연속학습**. 채점 = **기술습득 효율**(레벨 클리어 행동 수 ÷ 사람 상위중앙값 기준). 100% = 모든 게임을
  사람만큼 효율적으로 클리어.
- **SOTA(2026-03): 프런티어 LLM <1%**(Gemini 3.1 0.37·GPT-5.4 0.26·Opus 4.6 0.25·Grok 0). **사람 100%.**
  프리뷰 최고 12.58%(Tufa Labs). = **크리스탈라이즈드 지식이 안 통하는 유동지능 시험.**

## 1. ★왜 ATANOR에 완벽한 북극성인가
- **철학 일치**: ARC-3 = "지능은 아는 양이 아니라 **새것을 배우는 효율**"(Chollet). 이건 ATANOR 테제
  ([[structure-over-memorization]]·[[english-core-architecture]]·No-LLM) **그 자체**.
- **LLM 0% = 우리 차별화 지점**: 암기가 안 통하니, 구조로 배우는 우리 접근이 정직하게 겨룰 무대.
- **오늘밤 지은 것이 코어**: **X1 압축진전 드라이브 = 기술습득 효율 구동기 그 자체**(Schmidhuber: 학습진전
  최대화 = 최소 행동으로 규칙 습득). 폭발엔진(X1-X4)=추상 발명·습득효율 = ARC의 심장.
- **전 기관 통합 과녁**: ARC-3는 지각+세계모델+목표추론+계획+습득효율+연속학습을 한 번에 요구 = **CO
  (의식 오케스트레이터)가 전 기관을 대화형 학습으로 지휘하는 궁극 시험**. [[conscious-orchestrator]]의 외부 과녁.

## 2. 우리 자산 (실측) & 의존성
- ✅ **ARC-1 로컬 보유**: `data/arc_agi/ARC-AGI-master/data/evaluation/*.json`(정적 그리드 abstraction 과제)
  + `packages/arc_agi/solver.py`. = 추상발명 능력의 **로컬 측정 프록시**(정적 반쪽).
- ✗ **ARC-3 대화형 환경 미보유**: 150+ 게임 환경은 ARC Prize harness/API 필요 = **외부 의존성**(사장님
  제공 or fetch 결정). → 그때까진 **generic 대화형 환경을 우리가 만들어** 일반 능력 구축·측정.

## 3. 순수피지컬 능력 분해 — ARC-3를 무엇이 푸나
| 능력 | ARC-3에서 하는 일 | 우리 기관 |
|---|---|---|
| 지각 | 게임 상태(그리드) 구조화 | perception·situation_model |
| **대화형 세계모델 귀납** | (상태,행동,다음상태)서 규칙 귀납 | **폭발엔진 귀납루프**(프로그램=전이규칙)·mechanism·transition-graph |
| 목표 추론 | 지시 없이 "진전=무엇"을 관찰서 추론 | intent inference·curiosity(내인성 압) |
| 효율 계획 | 학습 세계모델+목표로 최소행동 계획 | DELIBERATOR·양방향 탐색 |
| **습득 효율** | 최소 탐색행동으로 규칙 습득 | **X1 압축진전 드라이브** |
| 연속학습 | 레벨/환경 간 추상 이월 | X2 e-graph·X3 QD 아카이브 |
| 체화/행동 | 행동→결과 감각운동 | embodiment 신체스키마(M0/M1 SAC) |

★ **통합 통찰**: **폭발엔진 = ARC의 코어**. ARC-1 = 폭발엔진의 정적 그리드 적용. ARC-3 = 그 위에 **대화형
세계모델 귀납 + 탐색 + 목표추론**의 agentic 층을 얹은 것. 즉 ARC-3 = 폭발엔진+CO+지각+체화의 **궁극 통합**.

## 4. 시험특화 금지 규율 (BINDING, 사장님 "순수피지컬")
- **ARC 과제로 학습 금지.** 일반 능력(세계모델 귀납·효율탐색·목표추론)을 **generic 환경**서 구축.
- **봉인 홀드아웃**: ARC-3 private 환경(및 ARC-1 evaluation)은 **개발 중 절대 미접촉**, 최종 측정만.
- **ARC 하드코딩 금지**(특정 게임 규칙·색·격자 특수화 0). 측정 = 행동수÷사람 baseline(그들의 지표 그대로).
- HLE와 동급 정직: 만점 도달 선언 없이 **봉인 기술습득효율 % 누적**으로만.

## 5. 계층 빌드 (각 봉인 게이트·순수피지컬)
- **B0 — ARC-1 추상발명 (로컬, 폭발엔진 적용)**: 정적 그리드 과제를 폭발엔진(X1 압축진전+X2/X3 추상)으로
  귀납. 게이트: sealed ARC-1 evaluation에서 **시험특화 없이** 정답률 측정(현 SOTA 맥락서 정직). = 추상발명
  반쪽의 로컬 실증.
- **B1 — generic 대화형 세계모델 귀납기**: (상태,행동,다음상태) 관측서 전이규칙 귀납, **sample-efficient
  (X1이 최소 탐색행동으로)**. generic 그리드 게임(우리가 만든, ARC 아님)서 봉인 측정: **규칙 습득에 필요한
  행동 수**(=ARC-3 지표 프록시).
- **B2 — 목표 추론 + 효율 계획**: 관찰서 진전신호 추론 + 학습 세계모델로 DELIBERATOR 최소행동 계획.
- **B3 — CO 오케스트레이션**: 지각+세계모델+목표+계획을 대화형 학습 폐루프로 CO가 지휘(자기태엽 L5).
- **B4 — ARC-3 harness 통합**: 환경 접근 확보시, 봉인 private 환경서 기술습득효율(행동÷사람) 측정.

## 6. 정직한 천장
- **만점 = 열망 정점**(SOTA<1%·최고 12.58%). HLE처럼 도달 선언 없이 측정 진전만. 지어낸 점수 0.
- ARC-3 harness 접근 = 의존성(사장님 결정). 그 전엔 generic 환경 + ARC-1로 능력 구축·측정.
- 이건 **새 큰 트랙**(대화형 agent)이나 **테제 완벽 정합** — 우리가 옳게 지으면 LLM 0% 무대서 차별화.

## 7. 한 문장
ARC-AGI-3 = **"지시 없이 새 환경을 사람만큼 효율적으로 배우는" 유동지능 시험**이자 ATANOR 테제의 외부
정점. 순수피지컬 경로 = **폭발엔진(습득효율 X1+추상 X2/X3)을 코어로, 대화형 세계모델 귀납+목표추론+효율계획을
CO가 지휘** — 시험특화 0, 봉인 홀드아웃으로만. 로컬 ARC-1로 추상반쪽 착수, generic 환경으로 대화형반쪽,
harness 확보시 정식 측정.

관련: [[conscious-orchestrator]] [[recursive-self-improvement-plan]] [[intelligence-explosion 문서=docs/ATANOR_intelligence_explosion_research.md]]
[[structure-over-memorization]] [[benchmark-empirical-verdict]] [[track-e-embodiment-promoted]] [[deliberator-system2]].
