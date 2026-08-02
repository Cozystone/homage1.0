# Kimi K3 검색-RAG 방식 분석 + ATANOR 차용 판정 (2026-07-18)

사장님 지시: "Kimi K3에 대해 자세히 찾고 얘가 쓰는 검색RAG 방식을 우리가 차용할 수 있을지
소스코드 되는데까지 최대한 자세하게 분석해서 방안 제시해."

## 0. 소스 접근 한계 — 먼저 정직하게

K3는 **2026-07-16 API 공개, 오픈웨이트·테크리포트·vLLM KDA 구현은 7/27 공개 예정**이다.
오늘(7/18) 기준 K3 자체의 소스는 존재하지 않는다. 따라서 이 분석은
(a) K3 공개 자료(아키텍처·벤치·제약), (b) **같은 팀의 공개된 직계 계보** — K2 Thinking
(HF 모델카드+배포 스택), Kimi-Researcher(에이전틱 검색 테크블로그) — 의 소스/문서까지 판다.
K3의 검색 방식은 이 계보의 연속임이 벤치 구성(BrowseComp 91.2, DeepSearchQA F1 95.0)과
"preserved thinking history" 요구사항으로 교차 확인된다. 7/27 웨이트가 풀리면 재검증한다.

## 1. K3 팩트 시트 (공개 자료 종합)

| 항목 | 값 |
|---|---|
| 총/활성 파라미터 | 2.8T MoE, **16/896 expert** (~50B급 활성) |
| 어텐션 | **KDA(Kimi Delta Attention)** — 일부 층을 하이브리드 선형 어텐션으로 교체, 1M 컨텍스트에서 디코딩 최대 6.3× |
| 신기제 | AttnRes(깊이 방향 선택적 표현 인출), Stable LatentMoE(잠재공간 라우팅+Quantile Balancing), Gated MLA(KV캐시 절약) |
| 컨텍스트 | **1M 토큰** |
| 양자화 | **MXFP4 가중치 + MXFP8 활성, QAT**(SFT 단계부터; 사후양자화 아님) — 1.4TB(vs FP16 5.6TB) |
| 에이전틱 | reasoning_effort max 전용(출시 시점), "preserved thinking history" 필수 — 히스토리 누락 시 생성 불안정 |
| 알려진 약점 | "excessive proactiveness" — 모호하면 묻지 않고 행동 |

## 2. 핵심 발견 — K 계보의 "검색RAG"는 벡터DB RAG가 아니다

임베딩 인덱스→top-k→컨텍스트 스터핑이라는 고전 RAG 파이프라인이 **없다**. 대신:

1. **에이전틱 검색 루프** (K2 Thinking): "think → search → browser → think → code"를
   엔드투엔드 학습으로 인터리브. **200-300 연속 툴콜**을 드리프트 없이 유지.
   툴 포맷은 OpenAI 호환 function calling, 결과는 `role:"tool"` 메시지로 재주입.
2. **컨텍스트 관리 = 증류-축출** (실측 공개):
   - K2 Thinking: 축적 입력이 256k 한계 초과 시 **"이전 툴 출력을 전부 숨긴다"** —
     원문은 버리고 thinking 스트림에 남은 요약이 기억을 대신한다.
   - Kimi-Researcher: "중요 정보는 유지, 불필요 문서는 폐기"하는 관리기로 롤아웃을
     50+ 반복까지 연장. **ablation: 관리기 학습 시 반복 +30%.**
3. **병렬 궤적 + 성찰적 집계**: Heavy mode = 8 궤적 동시 롤아웃 후 집계.
   Kimi-Researcher는 병렬 검색 툴로 태스크당 평균 23 추론 스텝·200+ URL·70+ 쿼리.
4. **자기검증이 학습된 행동**: 상충 정보 시 가설 재정식화, 답 전 교차검증 검색 —
   RL(REINFORCE)로 창발. 보상 = 정오 + 포맷 + **γ-감쇠(짧은 궤적 우대)**.
5. **훈련 데이터는 전자동 합성**: "생성·검증을 전자동으로 하는 QA쌍 파이프라인,
   수작업 개입 최소" — 사람 라벨 없이 검색-추론 커리큘럼을 만든다.
6. **1M 컨텍스트의 의미**: K3에서 KDA가 1M을 싸게 만들면서, "검색"의 상당 부분이
   **다 넣고 어텐션이 찾게 하는 것**으로 이동한다(AttnRes가 층간 선택 인출 담당).
   즉 K 계보의 RAG는 갈수록 "인덱스 기술"이 아니라 "컨텍스트+어텐션 기술"이다.

## 3. 차용 판정 — 무엇이 넘어오고 무엇이 못 넘어오나

**전제(BINDING)**: ATANOR는 No-LLM. K3의 힘의 원천 두 가지 — ①어텐션의 의미 매칭
②RL로 학습된 툴 정책 — 는 **모델 그 자체라 차용 불가**. 그리고 우리는 오늘 어휘
오픈북의 구조적 천장을 실측했다(오라클 0.165<우연, `four_walls` E6b): K3가 검색을
잘하는 이유는 인덱스가 아니라 **의미 표현**이다. 이 분석은 그 결론을 강화한다.

### 3a. 이미 갖고 있는 것 (수렴 확인 — 재구축 금지)
| K 계보 | ATANOR 대응물 | 상태 |
|---|---|---|
| think→search→refine 루프 | 검색 오케스트레이션 v2 (query-gen→multi-search→corrective) | SHIPPED |
| 답 전 교차검증 | 합의-증거 기계 (k-source, variable-k, 격리층) | SHIPPED |
| 증류-축출 컨텍스트 | 브라우저 증류(DOM→그래프) + 3단 여과 | SHIPPED — K의 +30% ablation이 이 설계의 **외부 실증** |
| 궤적 저널 | activity_journal, 실패 영수증 엔진 | SHIPPED |

### 3b. 차용 가치 있는 것 (No-LLM 호환, 구현 후보)
1. **갭-구동 재질의 (P1, 소형)** — 우리 corrective re-search는 "실패하면 다시"다.
   K식은 **"지금까지 모은 주장 대비 '아직 모르는 것'을 명시 산출 → 그 갭이 다음
   쿼리를 생성"**. 우리 증거 원장(합의 기계의 claim ledger)에 미충족 슬롯 검출기를
   붙이면 규칙 기반으로 가능. 게이트: 다홉 질문 배터리에서 재검색 적중률 상승 실측.
2. **γ-감쇠 계획 채점 (P2, 소형)** — 자율 데몬 원정 루프의 계획 선택에 비용 감쇠
   도입(같은 커버리지면 짧은 계획 우대). 지금은 무가중.
3. **병렬 독립 레인 + 불일치 표면화 (P2)** — multi-search를 "서로 다른 정식화 n개
   독립 실행 → 합의 병합 + **불일치를 답에 명시**"로 승격. Heavy mode의 8-궤적
   집계를 합의 기계 위에 올리는 것. 우리 정직성 독트린과 정합.
4. **전자동 훈련쌍 합성 (P0 — E9의 데이터 엔진)** — Kimi-Researcher의 자동 QA쌍
   파이프라인을 **인코더 훈련용**으로 차용: 7.0M 코퍼스에서 (문장→질문화, 원문단=양성,
   BM25 하드네거=음성) 쌍을 무한 생성. 사람라벨 0 — 우리 독트린과 정확히 일치.
   이것이 §4의 E9 2단(재랭커) 데이터가 된다.
5. **QAT 저정밀 (P3, 장기)** — MXFP4의 교훈 "양자화는 훈련 중부터". ACE류 자체
   인코더의 엣지 배포 시 INT8/INT4 QAT 검토. 지금은 무관.

### 3c. 차용 불가 / 함정
- **1M 컨텍스트 스터핑**: 어텐션 없는 우리에게 "다 넣기"는 무의미 — 우리 등가물은
  그래프 활성장(확산 활성)이며 이미 그 노선이다.
- **RL 툴 정책**: 보상 신호를 채점할 얼린 신탁이 있어야 하는데, 검색 품질의 신탁을
  LLM 없이 만드는 문제가 선행 — 순환. 지금은 규칙 오케스트레이터가 정직한 상한.
- **K3 웨이트 재사용**: 차터 위반(No LLM). 논외.
- **"excessive proactiveness"는 반면교사** — 우리 침묵 독트린(voice-or-silence)이
  옳다는 외부 증거로 읽는다.

## 4. 종합 — K3 분석이 가리키는 곳은 E9다

K 계보에서 **오케스트레이션은 우리가 이미 갖고 있고**(3a), 남은 격차는 단 하나,
**쿼리·패시지·선택지 사이의 의미 매칭**이다. 오늘 실측한 천장(어휘 오라클 0.165)이
그 격차의 크기다. 따라서 이 분석의 결론은 새 검색 파이프라인 증설이 아니라:

> **E9(ACE2 재사전학습)를 실행하되, 첫 배치처를 '생성'이 아니라 '검색 재랭커/
> 옵션-패시지 의미 채점기'로 잡는다.** 데이터는 3b-4의 전자동 합성쌍(사람라벨 0),
> 게이트는 오늘의 오라클 천장(0.165)을 **의미 채점기가 넘는지**로 사전선언한다.

실행 계획·킬게이트·예산은 `docs/ATANOR_four_walls_research.md` E9 항목에 통합.

Sources: [K3 overview (HF blog)](https://huggingface.co/blog/ResterChed/kimi-k3-model-overview-mxfp4-quantization-open-wei) ·
[MarkTechPost K3](https://www.marktechpost.com/2026/07/16/moonshot-ai-releases-kimi-k3-a-2-8-trillion-parameter-open-moe-model-with-kimi-delta-attention-and-1m-context/) ·
[Simon Willison K3](https://simonwillison.net/2026/Jul/16/kimi-k3/) ·
[Tom's Hardware K3](https://www.tomshardware.com/tech-industry/artificial-intelligence/moonshot-releases-2-8-trillion-parameter-kimi-k3) ·
[K2 Thinking model card](https://huggingface.co/moonshotai/Kimi-K2-Thinking) ·
[K2 Thinking blog](https://www.kimi.com/blog/kimi-k2-thinking) ·
[Kimi-Researcher](https://moonshotai.github.io/Kimi-Researcher/) ·
[deeplearning.ai 분석](https://www.deeplearning.ai/the-batch/kimi-k2-thinking-outperforms-proprietary-models-with-new-techniques-for-agentic-tool-use) ·
[MoonshotAI GitHub](https://github.com/moonshotai)
