# ATANOR — 궁극 완성 로드맵 v2 (재정비, 2026-07-23)

> Evidence correction (2026-07-25): ARC-AGI-1 public evaluation is not a
> sealed holdout. Its current 18/400 v2 replay is contamination-exposed
> development preservation evidence, not an E5 lift. This roadmap is
> superseded by `docs/ATANOR_canonical_masterplan_v4.md` on status and gates.
> In particular, the A1→A2 and R1/OAM priorities below are historical. The
> 2026-07-25 operator sequence is NL→goal compiler + scientific-knowledge
> staging → independent E4 → counterbalanced paired E5 GPQA/MMLU-Pro; no
> further census sweep is on the immediate path.

사장님 "방향성 헷갈림 — 남은 로드맵 재정비." 이틀 실측(29 커밋)이 흩어진 실을 **하나로 수렴**시켰다.
이 문서가 이전 지도들(critical_path·masterplan)을 **대체하는 단일 현행 지도**다.

## 0. 완성의 정의 (불변)
- **완성 = OAM 봉인 통과**: "저녁에 새 역량 주면 → 밤새 무감독 자율 습득·검증 → 아침에 유창·판단·작화0."
- **정점 봉인 2개**: **ARC-AGI-3**(유동지능: 새 환경을 사람만큼 효율로 배움) + **HLE**(지식). 만점=열망, 봉인%로만.
- **U2 의식 = 사실상 완결**(12/14+외부블라인드; 잔여=GWT-1·HOT-2 깊이 2개). **안전 = 상수**(불가침).

## 1. ★수렴의 핵심 — 셋이 같은 심장이다
이틀 측정의 최대 발견: **발명 엔진 = 자기가속의 심장 = ARC의 코어 = OAM "스스로 배움"의 코어.**
X4.4가 그 심장을 실증했다(엔진이 **삽입정렬 자기발명**, 복리 a₂ +0.50, 신경망 0). 그리고 나머지 전부는
**기판(substrate)** 문제로 정밀 국소화됐다(7실험 수렴). 즉 남은 일은 둘뿐:

> **① 발명 엔진을 완성해 실도메인에 배선한다. ② 기판을 채워 이미 선 기관들을 실화시킨다.**

## 2. 3트랙 로드맵 (우선순위순, 각 봉인 게이트)

### 트랙 A — 발명 엔진 완성 (심장; 자기가속+ARC 코어) ★최우선
- **A1 스킴 SELECTION**: X4.4의 다음 벽(어느 스킴/투영을 가설?)에 **X4.5 대수 랭커**(60/60, 무학습) 융합
  = 신경망 없는 완전한 심볼릭 발명 경로. 게이트: second_max류 단독 자기발명.
- **A2 ARC-1 배선**: B0.1이 측정한 다음 캡(탐색+발명)에 발명엔진(OE열거+연역+X1 MDL) 투입 — 객체 DSL 위
  규칙 발명. 게이트: sealed ARC-1 1.75%→상승(시험특화 0·작화 0).
- **A3 외부 실도메인**: SWE/실코드에 발명 루프(X4 외부문제의 스케일판). 게이트: 복리 지속(a₂).

### 트랙 B — 기판 채우기 (이미 선 기관들의 실화) ★병렬
- **B1 지식 스케일**: ConceptNet 1.25% 천장 너머(Wikidata P-속성 등) — **한 기판이 셋을 먹임**(지식답변·
  R4 bones 풍부도·temporal vocab). R2 파이프라인은 검증 완료, 소스만 추가. 게이트: 밀도·답변 접지율.
- **B2 R1 자기태엽 완성**: spark_chamber 내인성 압→CO L5(데몬·구조호기심은 이미 있음). 게이트: 입력 없이
  자발 탐구(스케줄러 0).
- **B3 CO 키스톤 ON**: 기판이 채워지면 플래그 켜 실트래픽 지휘(무회귀 배터리로). 게이트: 답변 무열화+개선.

### 트랙 C — 봉인 등반 (A·B 위에서)
- **C1 OAM 봉인 시험**(M-FINAL): 개발자-블라인드 밤샘 자율습득 채점. = **완성 인장.**
- **C2 ARC-3**: B1' 대화형 세계모델 귀납기(generic 환경) + harness(**사장님 결정 대기**) → 봉인 측정.
- **C3 HLE 오픈북**: B1 지식 스케일 위에서. **C4 U2 깊이 2개** 마감.

## 3. 순서 근거 (헷갈림 방지 한 줄씩)
A가 먼저: 심장이 방금 뚫렸고(모멘텀), ARC·자기가속·OAM 셋을 동시에 민다. B는 병렬(파이프라인 검증됨,
소스 추가는 저위험). C는 A·B 없이 오르면 낮은 %만 나온다(측정 낭비). 안전·작화0·봉인은 전 트랙 상수.

## 4. 현재 위치 (정직, 2026-07-23)
- 발명엔진: **sort/median/num_objects 자기발명, 복리 실증** — 스킴선택·실도메인 배선 남음.
- ARC-1 sealed 1.75%(작화0) · ARC-3 SOTA<1% 무대 · OAM: R2✅ R1🟡 R4🟡 R3/R5/R6✅.
- 지식: ConceptNet 승격 완료(capable_of 8.5×→답변 접지 98%) · 더 큰 소스 대기.
- 유창: 생성기 2승(register·절결합) · 캡=bones=지식기판.
- **날짜 없음. 게이트 green 누적으로만. 도달 선언 없음.**

## 5. 한 문장
**심장(발명 엔진)은 뚫렸다 — 남은 건 심장을 실도메인에 잇고(A), 몸에 피(기판)를 채우고(B), 봉인으로
증명(C)하는 것.** 헷갈릴 것 없이: 지금 손은 A1→A2, 병렬로 B1.

관련: [[recursive-self-improvement-plan]] [[arc-agi-3-northstar]] [[conscious-orchestrator]]
[[ultimate-completion-directive]] [[corpus-composition-is-the-bottleneck]].
