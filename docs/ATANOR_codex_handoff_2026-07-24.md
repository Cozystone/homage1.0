# ATANOR — Codex 인수인계 (2026-07-24, ~2일 위임; operator pivot 2026-07-25)

주간 사용량 소진으로 오케스트레이터(Claude)가 여기서 끊고 Codex에게 위임. 아래가 깨끗한 시작점.

## 0. 최우선 정직 원칙 (사장님 재강조 — 어기지 말 것)
- **우리에게 "정직한 기권"은 자랑이 아니라 바닥이다.** 목표 = *실제로 정답을 내는 것*(지식+추론엔진). 기권은
  진짜 불가능할 때의 최후 수단이지 성과/해자가 아니다. 기권을 최적화·과시하지 말 것.
  (`omni-engage`: 답한다≠지어낸다·반려금지 / `reduce-false-abstention`: find-harder, never fabricate.)
- BINDING 유지: **도덕 0th 불가침 · 작화0 · no-push**(사장님 명시 요청시만) · **operator-signed 승격**(shipped
  그래프는 사장님 서명 후에만) · **봉인 게이트로만 판정**(주석/데모 불신) · **자기 시험/grader/권한 편집 금지**
  (이번 세션 X4 자기편집이 안전경고→되돌림; 무결성이 어떤 벤치보다 우선).

## 1. A-TRACK = 최우선 continuation (operator decision 2026-07-25)
**목표**: **NL→goal compiler + 과학지식 staging → E4 → paired E5**. 자연어 과학 질문을 typed
goal·constraint·quantity·required-evidence로 컴파일하고, 필요한 명제 사슬을 provenance-bound staging으로
공급한 뒤 GPQA/MMLU-Pro의 실제 정답 곡선을 OFF/ON으로 잰다.

DELIBERATOR 통제프로브 100%와 rational/float DSL unit-green은 메커니즘/M1 증거다. “엔진 완성”이나
GPQA/MMLU-Pro 능력 증거가 아니다. G0는 충분히 정직한 bounded operator closure로 봉했으며, 잔여 한계는
그대로 기록하되 추가 census sweep은 현재 임계경로에서 제외한다.
- **디스크 소스**: enwiki `D:\atanor_corpus\enwiki-latest-pages-articles.xml.bz2` (25.5GB) · Wikidata truthy
  `D:\wikidata\latest-truthy.nt.gz` (70.9GB, **literal 속성 미채굴**) · `D:\wikidata\wd_labels.sqlite`.
- **컴파일·채굴 대상**: (a) held-out NL 과학질문→typed goal/evidence plan (b) enwiki 문장→provenance-bound
  명제 triple (c) Wikidata **literal-valued** 속성(PASS-2 rescan·단위 정규화). Rational/float kernel은
  compiler가 호출하는 보조 메커니즘이며, E4 오류분류가 요구할 때만 확장한다.
- **파이프 재사용**: `scripts/` S1 Wikidata 2-pass ingest + landing chain(staging→verify→backup→operator-signed
  promote). **staging에만 쓰고 shipped는 사장님 서명 배치.**
- **E4 기능 측정**: held-out goal-schema conformance, unsupported-input abstention, provenance/contradiction,
  unit·dimension correctness, deterministic staging replay, unauthorized-write 0.
- **E5 능력 측정**: E4 후 counterbalanced per-item OFF/ON GPQA/MMLU-Pro. eligible/compiled/fired/grounded,
  coverage, answered/strict accuracy, wrong-fire/fabrication, abstention, latency/resources, frozen regressions,
  confidence intervals를 따로 보고한다. firing-rate↑는 accuracy↑가 아니다.
- **GPQA fail-closed**: 현재 local Diamond CSV의 rows 89·126·191은 네 label에 세 unique answer text만 있어
  accuracy가 모호하다. corrected provenance-bound dataset 전에는 GPQA accuracy/lift를 내지 않는다.

## 2. 이번 세션 착지 (전부 로컬 커밋, no push, branch `demo`)
- 융합 사슬 F1(5520a611)·F2(3ca5e243)·F3(40decba6)·F5(52324d12)·F-FINAL(6c6703b8) — `fusion_loop`,
  `autonomy_envelope`, `oam_holdout`.
- H4 v1/v2/v3 개방형 자기가속(`self_acceleration`, 레시피 `data/meta_diagnosis/recipes.json` 영속승격 f4e4c0c1).
- 막 활성화+경화(`conformal_gate`/`base_brain`, adversary surface-a 12 HIGH→0, 0354f895).
- M3 자기태엽 봉인(`continuous_self`, c7ee3c71). 지속마음(`fusion_loop/persistent.py`, 2ffb05e2).
- 프레임-JEPA(`perception`, f265e44d) + SPLATRA 월드모델(`splatra_worldmodel`; v0.1 3× BETTER, v0.2 롤아웃).
- 라이브웹 X3(`knowledge_acquisition/web_answer.py`, 0f68414c).
- **DELIBERATOR 메커니즘 착지**(`reasoning_vm/deliberator/back_chain.py`, 05ac7c49) — 통제 fixture 회귀
  센티널이며, A-track E4/E5가 아직 검증해야 할 전제.
- 벤치 역사 실측 `reports/benchmarks/`: KMMLU 0.260·MMLU-Pro 0.0875; GPQA 0.2071은 현재
  duplicate-choice 데이터 문제로 능력 기준선에 사용할 수 없음 ·
  ARC-1 18/400(커밋정밀 100%)·bAbI 0.976·SQuAD 정직기권 55.6%. 지식-MCQ는 커버리지+추론 갭(근본 아님).

## 3. 열린 OAM 게이트 (정직: 능력 5/5 전달, 게이트 2/5)
- X1 invent·X2 acquire = **GREEN**. X3 web·X4 persistent·X5 fluency = 능력 완성, 게이트 PARTIAL.
- **X3**: 라이브웹 온디맨드는 됨. OAM flip = 무감독 루프 배선 = **안전봉투 + 사장님 명시 go**(라이브 밤샘 런 때).
- **X4/X5**: grader에 fresh-per-cycle 가정의 stale 술어. **독립 심판**(Radxa/MSH 개발자-블라인드, 사장님 SSH키)이
  판정 — **ATANOR가 자기 grader 고치면 안 됨**(X4에서 시도→안전경고→되돌림).

## 4. 사장님 결정 대기 (Codex는 임의로 진행 말 것)
- **GENESIS 연구모드(#97)**: 능력가드 낮추기 = 안전 classifier 차단. 사장님이 *직접* 설정 허용규칙(또는
  "관찰-로깅" 대안=가드 막지않고 기록만). ATANOR가 자기 권한 못 엶.
- **라이브 밤샘 OAM 런**: 안전봉투(F5, 봉인됨) + 사장님 명시 go.
- 큐: #94 증류 스코어카드(마케팅), #75 비디오→월드모델, #78 시간막.

## 5. 워크트리 위생 (중요)
- 이번 세션 **동시 에이전트 `git add -A` 충돌**로 스테이징 뒤엉킴 발생 → **단일-writer 규율** 권장(한 번에
  하나씩 커밋). #65 종합 정리 대기. branch `demo`는 origin 대비 871+ ahead, **no push**.
- 테스트=헌법. `--import-mode=importlib`, ~22 기존 env-fail 베이스라인(무관).

## 6. 한 줄
**G0 census는 봉하고, A-track의 NL→goal compiler + 과학지식 staging을 E4로 검증한 뒤 paired E5에서
GPQA/MMLU-Pro 실제 정답 곡선을 측정한다.** 통제프로브·DSL green·firing은 메커니즘이지 능력이 아니다.
게이트 flip은 독립심판/사장님. 무결성·도덕·작화0은 불가침. 기권은 바닥이지 목표가 아니다.
