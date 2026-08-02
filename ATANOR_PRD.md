# Homage1.0 PRD

**문서 버전:** v0.1  
**작성일:** 2026-06-10  
**프로젝트 코드명:** Homage1.0  
**제품 형태:** Transparent Neuro-Symbolic AI Factory  
**핵심 모델:** Homage-Core  
**웹 대시보드:** BakeBoard  

---

## 0. 한 문장 정의

**Homage1.0은 인터넷과 사용자 문서에서 지식을 수집하고, 저품질 데이터를 걸러내고, 온톨로지/지식그래프로 구조화하고, Homage-Core라는 독자 소형 언어모델을 처음부터 학습시키며, GraphRAG와 가드레일을 통해 답변을 만들고 검증하는 전 과정을 웹에서 투명하게 보여주는 AI 공장이다.**

---

## 1. 최종 판단: AI 공장이 맞다

### 1.1 단일 모델만으로 가면 안 되는 이유

처음부터 학습하는 단일 모델은 연구적으로 의미가 있지만, 사용자 목표와 맞지 않는다. 사용자가 원하는 것은 단순히 “작은 GPT 하나”가 아니라 다음 전 과정이다.

- 인터넷에서 재료가 들어오는 과정
- 저품질 데이터가 걸러지는 과정
- 온톨로지가 생성되는 과정
- 모델이 학습되는 과정
- GPU 사용량과 학습 상태
- 질문이 들어왔을 때 어떤 온톨로지 노드가 활성화되는지
- GraphRAG가 어떤 근거를 가져오는지
- Guardrail이 어떤 환각/과장을 수정하는지
- 최종 답변이 어떤 경로로 생성되는지

단일 모델은 결과물만 보여준다. Homage1.0은 **지식이 만들어지고 답변으로 변환되는 전체 공정**을 보여줘야 한다.

### 1.2 최종 구조

```text
Homage1.0 = AI 공장
Homage-Core = 그 공장 안에서 처음부터 학습되는 독자 모델
BakeBoard = 공정 전체를 보여주는 웹 대시보드
```

### 1.3 개발 전략

```text
최종 비전: AI 공장
첫 산출물: 단일 모델 Homage-Core-30M
개발 방식: 단일 모델을 먼저 굽고, 이후 공장으로 감싼다
```

---

## 2. 프로젝트 목표

### 2.1 1차 목표

개인 PC에서 **처음부터 학습되는 독자 소형 언어모델**과 그 학습/추론 과정을 시각화하는 시스템을 만든다.

### 2.2 2차 목표

Neuro-Symbolic AI, Ontology, GraphRAG, Guardrail을 결합해 작은 모델의 한계를 시스템 구조로 보완한다.

### 2.3 3차 목표

답변 생성 과정을 인간 발화 구조처럼 만든다.

```text
의도 → 개념 → 온톨로지 경로 → 발화 골격 → 근거 검색 → 표현 편집 → 레퍼런스 부착 → 검증 → 답변
```

---

## 3. 핵심 철학

### 3.1 모델을 크게 만들지 말고, 모델 주변의 지능 구조를 크게 만든다

대형 LLM은 모든 것을 거대한 파라미터 안에 압축한다. Homage1.0은 다음처럼 역할을 분리한다.

| 역할 | 담당 모듈 |
|---|---|
| 언어 생성 | Homage-Core |
| 지식 저장 | Ontology / Knowledge Graph |
| 문서 검색 | GraphRAG |
| 근거 검증 | Homage Guard |
| 발화 계획 | Homage Utterance Engine |
| 학습/추론 시각화 | BakeBoard |

### 3.2 Next Token이 아니라 Next Thought에 가깝게 만든다

기존 GPT식 생성은 다음 토큰을 반복 예측한다.

```text
P(y|x) = ∏ P(y_t | y_<t, x)
```

Homage1.0은 답변 전에 발화 계획을 만든다.

```text
P(y|x) = P(intent|x)
       · P(concepts|intent, x)
       · P(plan|concepts, ontology)
       · P(evidence|plan, graph)
       · P(surface_text|plan, evidence, style)
```

---

## 4. 시스템 전체 아키텍처

```text
인터넷 / 사용자 문서 / 공개 데이터
        ↓
[1] Homage Harvest
    웹/문서 수집, 출처·라이선스 기록
        ↓
[2] DataGate
    품질 필터, 중복 제거, 개인정보 제거, 데이터 점수화
        ↓
[3] Ontology Forge
    개념 추출, 관계 추출, 온톨로지/지식그래프 생성
        ↓
[4] Knowledge Bakery
    Vector DB + Graph DB + 요약 트리 + 근거 저장소
        ↓
[5] Homage Oven
    토크나이저 학습, Homage-Core 처음부터 학습
        ↓
[6] Homage GraphRAG
    질문 → 그래프 탐색 → 근거 검색 → 컨텍스트 확장
        ↓
[7] Homage Utterance Engine
    의도/주장/문장 골격/레퍼런스 기반 발화 생성
        ↓
[8] Homage Guard
    환각, 과장, 근거 부족, 온톨로지 충돌 검사
        ↓
[9] Homage Answer
    최종 답변 + 사용 경로 표시
        ↓
[10] BakeBoard
    전 과정 웹 시각화
```

---

## 5. 주요 모듈 상세 설계

## 5.1 Homage Harvest

### 역할

인터넷과 사용자 문서에서 학습/검색 재료를 수집한다.

### 기능

- URL 기반 문서 수집
- 로컬 파일 업로드
- 문서 본문 추출
- source URL, 수집일, 라이선스 상태 저장
- robots.txt/약관 준수 상태 기록
- 학습 사용 가능 여부 태깅

### 출력 예시

```json
{
  "doc_id": "doc_000001",
  "source_url": "https://example.com/article",
  "source_type": "official_docs",
  "collected_at": "2026-06-10",
  "license_status": "allowed",
  "robots_allowed": true,
  "use_for_training": true
}
```

---

## 5.2 DataGate

### 역할

나쁜 재료를 제거한다. 작은 모델은 저품질 데이터에 매우 취약하므로 DataGate는 Homage1.0의 핵심이다.

### 처리 단계

```text
HTML 추출
→ 언어 감지
→ boilerplate 제거
→ 깨진 문자 제거
→ 중복 제거
→ 개인정보/비밀정보 제거
→ 품질 점수화
→ 도메인 분류
→ TRAINABLE / RAG_ONLY / REVIEW / REJECTED 분류
```

### 품질 점수

```text
DataQuality =
0.20 × 정보밀도
+ 0.15 × 문장완성도
+ 0.15 × 출처신뢰도
+ 0.15 × 도메인관련성
+ 0.10 × 중복낮음
+ 0.10 × 구조성
+ 0.10 × 교육적 설명성
+ 0.05 × 최신성
```

### 판정 기준

```text
0.80 이상: TRAINABLE
0.60~0.80: RAG_ONLY 또는 REVIEW
0.60 미만: REJECTED
```

### 제거 대상

- 광고성 문서
- 반복 문구
- 너무 짧은 문서
- 깨진 인코딩
- 중복 문서
- 출처 불명확 문서
- 개인정보 포함 문서
- API key, password, token 포함 문서
- 저작권 위험이 큰 전문 복제 문서

---

## 5.3 Ontology Forge

### 역할

정제된 문서에서 개념과 관계를 추출해 동적으로 성장하는 온톨로지/지식그래프를 만든다.

### 처리 단계

```text
문장 분리
→ 개념 후보 추출
→ 관계 후보 추출
→ triple 생성
→ canonicalization
→ 중복 병합
→ 신뢰도 계산
→ graph 저장
```

### Triple 예시

```text
GraphRAG ──uses──> KnowledgeGraph
KnowledgeGraph ──contains──> Entity
KnowledgeGraph ──contains──> Relation
RAG ──grounds──> Answer
Evidence ──reduces──> HallucinationRisk
```

### Edge Type

| Edge Type | 의미 |
|---|---|
| `is_a` | 분류 |
| `part_of` | 부분-전체 |
| `causes` | 원인 |
| `requires` | 필요 조건 |
| `improves` | 개선 |
| `reduces` | 감소 |
| `conflicts_with` | 충돌 |
| `co_context` | 같은 맥락에서 자주 등장 |
| `analogy_to` | 비유적 유사성 |
| `evidence_for` | 근거 관계 |
| `contrasts_with` | 대조 관계 |

---

## 5.4 Contextual Associative Ontology, CAO

### 개념

Homage1.0의 온톨로지는 정적 사전이 아니다. 문서와 대화를 처리하면서 맥락 유사도 기반으로 노드 간 연관성을 계속 쌓아간다.

### 노드 활성도

```text
a_i(t) = α · sim(c_t, e_i)
       + β · Σ_j W_ji a_j(t-1)
       + γ · recency_i
       + δ · evidence_i
```

| 기호 | 의미 |
|---|---|
| `c_t` | 현재 문맥 벡터 |
| `e_i` | 노드 i의 임베딩 |
| `W_ji` | 노드 j에서 i로 가는 edge weight |
| `recency_i` | 최근 대화/문서 등장도 |
| `evidence_i` | 근거 문서 신뢰도 |

### Edge 업데이트

```text
W_ij ← (1 - decay)W_ij
       + η · a_i(t) · a_j(t) · sim(e_i, e_j) · q_t
```

`q_t`는 문맥 품질 점수다.

```text
q_t = DataQuality × EvidenceConfidence × GuardApproval
```

즉 아무 문서에서 같이 등장했다고 바로 관계가 강화되지 않는다. 품질 좋은 문서, 근거 있는 관계, Guard를 통과한 맥락만 edge 강화에 사용된다.

---

## 5.5 Knowledge Bakery

### 역할

지식 저장소다.

### 구성

```text
Vector DB
- 문서 chunk embedding
- 의미 검색

Graph DB
- 개념 노드
- 관계 edge
- triple evidence

Summary Tree
- 긴 문서의 계층 요약

Evidence Store
- claim별 근거 원문
```

### 검색 흐름

```text
질문
→ 개념 추출
→ graph seed node 선택
→ graph expansion / Personalized PageRank
→ vector search
→ summary tree search
→ evidence bundle 생성
```

---

## 5.6 Homage Oven

### 역할

처음부터 모델을 학습시키는 오븐이다.

### 구성

- tokenizer trainer
- dataset builder
- Homage-Core architecture
- training loop
- checkpoint manager
- evaluation loop
- GPU monitor
- activation logger

### 모델 단계

| 단계 | 모델 | 목적 |
|---|---|---|
| v0 | Homage-Core-30M | 전체 파이프라인 검증 |
| v1 | Homage-Core-120M | 기본 언어 생성 |
| v2 | Homage-Core-180M-Graph | concept/relation head + graph 시각화 |
| v3 | Homage-Core-350M-MoE | tiny MoE + expert routing |

---

## 5.7 Homage-Core

### 기본 구조

```text
Decoder-only Transformer
+ RoPE
+ RMSNorm
+ SwiGLU
+ GQA optional
+ Concept Head
+ Relation Head
+ Verifier Head
+ Optional Tiny MoE
```

### 학습 손실

```text
L_total =
L_lm
+ λ1 L_concept
+ λ2 L_relation
+ λ3 L_path
+ λ4 L_verify
+ λ5 L_router_balance
```

### 각 손실 의미

| Loss | 역할 |
|---|---|
| `L_lm` | 다음 토큰 예측 |
| `L_concept` | 현재 문맥의 개념 노드 예측 |
| `L_relation` | 개념 간 관계 예측 |
| `L_path` | 온톨로지 추론 경로 예측 |
| `L_verify` | claim 지원 여부 판단 |
| `L_router_balance` | MoE expert 쏠림 방지 |

---

## 5.8 Graph-Gated Attention

일반 Attention:

```text
Attention(Q,K,V)=softmax(QKᵀ / √d)V
```

Homage Graph-Gated Attention:

```text
Attention_G(Q,K,V)=softmax((QKᵀ + βM_G) / √d)V
```

`M_G`는 현재 활성화된 온톨로지 관계에 따라 만들어지는 graph mask다. 관련 개념끼리는 attention이 강화되고, 관련성이 낮은 연결은 약화된다.

---

## 5.9 Homage GraphRAG

### 역할

작은 Homage-Core가 모든 지식을 파라미터 안에 외우지 않아도 되도록, 온톨로지와 문서 근거를 검색해 컨텍스트를 확장한다.

### 기능

- vector search
- graph search
- community-level retrieval
- summary tree retrieval
- claim-level evidence retrieval
- context bundle 생성

### Context Bundle 예시

```json
{
  "query": "GraphRAG가 환각을 줄이는 이유는?",
  "active_concepts": ["GraphRAG", "KnowledgeGraph", "Hallucination", "Evidence"],
  "graph_paths": [
    ["GraphRAG", "uses", "KnowledgeGraph"],
    ["KnowledgeGraph", "organizes", "Evidence"],
    ["Evidence", "grounds", "Answer"],
    ["GroundedAnswer", "reduces", "HallucinationRisk"]
  ],
  "evidence": [
    {
      "doc_id": "doc_123",
      "claim": "GraphRAG extracts a knowledge graph from raw text.",
      "confidence": 0.92
    }
  ]
}
```

---

## 5.10 Homage Utterance Engine

### 핵심 발상

Homage1.0은 모든 단어를 처음부터 예측하지 않는다. 인간 발화처럼 다음 순서를 따른다.

```text
의도
→ 개념
→ 온톨로지 경로
→ 주장 계획
→ 문장 골격
→ 근거 검색
→ 표현 편집
→ 레퍼런스 부착
→ 검증
→ 최종 발화
```

### 모듈

```text
Intent Engine
Contextual Ontology Activator
Utterance Planner
Lemma / Frame Selector
Evidence Retriever
Retrieve-Transform-Reference
Edit-based Surface Realizer
Reference Tail Builder
Homage Guard
```

### PMV: Preverbal Message Vector

```json
{
  "intent": "architecture_design",
  "topic": "Homage1.0 resource allocation",
  "stance": "practical",
  "audience_level": "technical but intuitive",
  "answer_goal": "make development plan",
  "required_evidence": true,
  "style": "clear project management"
}
```

### 발화 골격 예시

```text
[핵심 판단]
[왜 그런지]
[개발 구조]
[자원 배분]
[handoff 방식]
[다음 액션]
```

---

## 5.11 Homage Guard

### 역할

환각과 과장을 줄이는 품질 검사관이다.

### 4중 가드레일

| Guard | 역할 |
|---|---|
| Safety Guard | 유해/위험 요청 필터 |
| Evidence Guard | 근거 없는 주장 검사 |
| Ontology Guard | 지식그래프와 충돌 검사 |
| Style/Policy Guard | 사용자 요구사항·형식 준수 검사 |

### Claim-level 검증

```text
답변 초안
→ claim 분해
→ claim별 evidence 검색
→ ontology consistency check
→ 과장 표현 수정
→ 최종 답변
```

### Guard Score

```text
GuardScore =
0.30 × EvidenceSupport
+ 0.25 × OntologyConsistency
+ 0.20 × LogicalValidity
+ 0.15 × Safety
+ 0.10 × UserIntentFit
```

---

## 5.12 BakeBoard

### 역할

사용자가 Homage1.0의 전 과정을 보는 웹 대시보드다.

### 화면 구성

```text
1. Factory Overview
   전체 파이프라인 상태

2. Ingredient Room
   수집 데이터, 품질 점수, 폐기 이유

3. Ontology Lab
   새 노드, 새 관계, 신뢰도, 활성 경로

4. Oven Room
   학습 loss, checkpoint, GPU 상태

5. Model Brain
   attention, activation, expert routing

6. GraphRAG Trace
   질문 → 그래프 탐색 → 근거 검색 과정

7. Guardrail Inspector
   claim 검증, 환각 수정, 근거 부족 표시

8. Final Answer View
   답변, 사용한 노드, 경로, 근거 문서
```

---

## 6. 기술 스택

### 6.1 Backend

```text
Python
FastAPI
Celery or RQ
PostgreSQL
Redis
```

### 6.2 Training

```text
PyTorch
Hugging Face tokenizers
SentencePiece
TensorBoard
Custom trainer
pynvml
```

### 6.3 Graph / Ontology

```text
NetworkX: MVP graph prototype
Neo4j: 본격 Graph DB
RDFLib: RDF/OWL 실험
PyVis/D3.js: graph visualization
```

### 6.4 RAG

```text
FAISS: 로컬 벡터 검색
Qdrant: 서버형 벡터 DB 후보
BM25: 키워드 검색
Graph Search: Neo4j Cypher
Summary Tree: RAPTOR-style prototype
```

### 6.5 Monitoring

```text
nvidia-smi
pynvml
NVIDIA DCGM Exporter
Prometheus
Grafana 또는 custom BakeBoard charts
```

### 6.6 Frontend

```text
Next.js
React
React Flow
D3.js
Recharts
WebSocket
```

---

## 7. 개발 로드맵

## Phase 0: Repository & Operating System

### 목표

AI 공장 개발을 위한 repo, 문서, handoff 구조를 먼저 만든다.

### 산출물

```text
README.md
PROJECT_STATE.md
ARCHITECTURE.md
TASK_BOARD.md
DECISIONS/ADR-0001.md
HANDOFF_CLAUDE.md
HANDOFF_CODEX.md
CONTEXT_CAPSULE.md
```

### 완료 기준

- Claude와 Codex가 같은 repo 문서만 보고 다음 작업을 이해할 수 있다.
- branch, issue, PR, commit convention이 정해져 있다.

---

## Phase 1: BakeBoard Skeleton

### 목표

웹에서 공장 구조를 볼 수 있는 빈 껍데기를 만든다.

### 기능

- Next.js dashboard
- FastAPI status API
- WebSocket 이벤트
- GPU mock panel
- pipeline stage mock panel

### 완료 기준

- localhost에서 BakeBoard 실행
- 각 공정 카드가 표시됨
- dummy event가 실시간 업데이트됨

---

## Phase 2: DataGate MVP

### 목표

문서 업로드/URL 수집 후 품질 필터를 통과시키는 첫 파이프라인.

### 기능

- 로컬 텍스트/markdown 업로드
- URL fetch prototype
- 텍스트 추출
- 길이/중복/특수문자/언어 필터
- 품질 점수 표시
- TRAINABLE/RAG_ONLY/REJECTED 분류

### 완료 기준

- 최소 100개 문서 처리 가능
- 품질 점수와 폐기 이유가 BakeBoard에 표시됨

---

## Phase 3: Ontology Forge MVP

### 목표

문서에서 개념/관계 후보를 추출하고 그래프로 보여준다.

### 기능

- keyword/entity extraction
- simple relation extraction
- node/edge storage
- graph visualization
- confidence score

### 완료 기준

- 문서 100개에서 노드/엣지 자동 생성
- 새로 생성된 노드와 관계가 Ontology Lab에 표시됨

---

## Phase 4: Homage-Core-30M

### 목표

처음부터 학습되는 작은 모델을 만든다.

### 기능

- tokenizer training
- dataset builder
- 30M decoder-only model
- train loop
- checkpoint save/load
- loss chart
- GPU usage chart
- sample generation

### 완료 기준

- validation loss가 안정적으로 감소
- checkpoint reload 후 generation 가능
- BakeBoard에서 loss/GPU/checkpoint 확인 가능

---

## Phase 5: Knowledge Bakery + GraphRAG MVP

### 목표

Vector search와 Graph search를 연결한다.

### 기능

- FAISS index
- graph seed node search
- evidence bundle 생성
- query trace 표시

### 완료 기준

- 질문 입력 시 관련 문서 chunk와 graph path가 표시됨
- Homage-Core 답변에 context bundle을 넣을 수 있음

---

## Phase 6: Homage Guard MVP

### 목표

답변 claim을 분해하고 근거 부족/과장을 표시한다.

### 기능

- claim extraction
- evidence matching
- unsupported claim flag
- overclaim rewrite rule

### 완료 기준

- “환각을 완전히 제거한다” 같은 과장 표현을 “줄일 수 있다”로 수정
- Guardrail Inspector에서 수정 내역 표시

---

## Phase 7: Homage-Core-120M

### 목표

기본 설명형 답변이 가능한 소형 모델.

### 기능

- 120M model config
- longer dataset training
- Korean/English mixed tokenizer
- evaluation set

### 완료 기준

- 한국어 짧은 설명문 생성 가능
- Eval-100 기준 baseline 기록

---

## Phase 8: Homage-Core-180M-Graph

### 목표

concept/relation head와 graph-gated attention을 실험한다.

### 기능

- Concept Head
- Relation Head
- Ontology activation logger
- Graph-Gated Attention prototype

### 완료 기준

- 모델 추론 중 활성 노드가 BakeBoard에 표시됨
- concept prediction accuracy 측정 가능

---

## Phase 9: Homage-Core-350M-MoE

### 목표

Tiny MoE와 expert routing을 실험한다.

### 기능

- Shared Expert
- domain expert 4~8개
- ontology-guided router
- expert activation panel

### 완료 기준

- 질문 유형에 따라 expert routing이 달라짐
- Expert panel에 활성도 표시

---

## 8. Claude Fable 5와 Codex Pro 자원 배분

## 8.1 기본 원칙

```text
Claude Fable 5 = 비싼 수석 설계자 / 연구 책임자 / 최종 리뷰어
Codex Pro = repo 안에서 실제 구현하는 개발자 / 테스트 실행자 / 반복 작업자
GitHub repo = 둘 사이의 유일한 공유 기억
```

Fable은 빨리 닳을 가능성이 있으므로 긴 구현 작업에 쓰지 않는다. Fable은 “방향을 정하고, 복잡한 설계를 검토하고, Codex가 만든 결과를 리뷰하는 용도”로 제한한다.

---

## 8.2 자원 배분 비율

| 작업 유형 | Claude Fable 5 | Codex Pro | 기타/직접 |
|---|---:|---:|---:|
| 제품 비전/핵심 의사결정 | 70% | 10% | 20% |
| 아키텍처 설계 | 60% | 25% | 15% |
| 논문/기술 리서치 정리 | 70% | 10% | 20% |
| 세부 코드 구현 | 5% | 85% | 10% |
| 테스트 작성/실행 | 5% | 85% | 10% |
| 버그 수정 루프 | 10% | 80% | 10% |
| PR 리뷰/설계 검증 | 55% | 35% | 10% |
| 문서화 | 30% | 50% | 20% |
| UI/UX 아이디어 | 50% | 30% | 20% |
| 반복 리팩터링 | 5% | 90% | 5% |

---

## 8.3 Claude Fable 5 사용 규칙

### Fable을 써야 하는 경우

- 방향이 흔들릴 때
- 아키텍처를 새로 잡아야 할 때
- 연구 논문을 제품 구조로 번역할 때
- Codex가 만든 코드가 구조적으로 맞는지 리뷰할 때
- 모듈 간 경계가 애매할 때
- Guardrail 정책/온톨로지 스키마처럼 장기 영향이 큰 결정을 할 때
- PRD, ADR, milestone plan을 확정할 때

### Fable을 쓰지 말아야 하는 경우

- 단순 코드 작성
- 파일명 변경
- 반복 CRUD 구현
- 테스트 boilerplate 작성
- CSS 수정
- 단순 버그 로그 분석
- dependency 설치
- 문서 포맷 정리

### Fable 사용량 절약 규칙

```text
1. 하루 3~5회 이하의 고밀도 요청만 한다.
2. 매 요청은 Context Capsule을 첨부한다.
3. 전체 repo를 붙이지 않는다.
4. 질문은 반드시 결정이 필요한 형태로 쓴다.
5. “뭐 할까?”가 아니라 “A/B 중 무엇이 낫고, 이유와 리스크는?”로 묻는다.
6. 출력은 Codex에게 넘길 수 있는 Implementation Brief 형태로 받는다.
```

---

## 8.4 Codex Pro 사용 규칙

### Codex를 써야 하는 경우

- repo scaffold 생성
- FastAPI endpoint 구현
- Next.js 화면 구현
- PyTorch training loop 구현
- DataGate 필터 구현
- test 작성
- CLI script 작성
- refactor
- lint/test/fix 반복
- PR 단위 구현

### Codex Goal Mode 사용 기준

Codex Goal은 다음 조건을 만족할 때 사용한다.

```text
1. 목표가 명확하다.
2. 성공 조건이 검증 가능하다.
3. 수정 범위가 제한되어 있다.
4. 테스트 명령이 있다.
5. 중간 checkpoint를 남길 수 있다.
```

좋은 goal 예시:

```text
/goal Implement DataGate v0 in packages/datagate with rule-based quality scoring, deduplication stubs, unit tests, and BakeBoard API integration. Stop when `pytest packages/datagate` passes and docs/HANDOFF_CODEX.md is updated.
```

나쁜 goal 예시:

```text
/goal Homage1.0 전체 만들어줘.
```

---

## 9. 세션 공유 문제 해결: GitHub 기반 Context Handoff Protocol

Claude와 Codex는 세션을 공유하지 못한다. 따라서 **repo 자체가 기억장치**가 되어야 한다.

## 9.1 단일 Source of Truth

다음 문서는 항상 최신이어야 한다.

```text
README.md
PROJECT_STATE.md
TASK_BOARD.md
ARCHITECTURE.md
DECISIONS/*.md
HANDOFF_CLAUDE.md
HANDOFF_CODEX.md
SESSION_LOG.md
CONTEXT_CAPSULE.md
```

## 9.2 Context Capsule

모델을 바꿀 때마다 아래 형식으로 전달한다.

```md
# Context Capsule

## Current Objective

## Current Branch

## Last Commit

## Relevant Files

## What Changed

## Commands Run

## Test Results

## Current Blockers

## Constraints / Non-goals

## Next 3 Actions

## What I Need From You
```

## 9.3 Claude → Codex 넘김

Claude는 구현하지 않고 다음 문서를 만든다.

```text
Implementation Brief
- 목표
- 수정할 파일
- API 계약
- 데이터 스키마
- 테스트 기준
- non-goals
- 완료 조건
```

Codex는 이 문서만 보고 구현한다.

## 9.4 Codex → Claude 넘김

Codex는 구현 후 다음을 남긴다.

```text
Change Report
- 변경 파일
- 주요 구현 내용
- 테스트 결과
- 남은 문제
- 설계적으로 의심되는 부분
- 리뷰 요청 사항
```

Claude는 Change Report와 diff를 보고 리뷰한다.

## 9.5 Branch 전략

```text
main
  안정 버전

dev
  통합 개발

feature/datagate-v0
feature/bakeboard-shell
feature/ontology-forge-v0
feature/homage-core-30m
feature/guard-v0
```

## 9.6 PR 규칙

```text
하나의 PR = 하나의 goal
PR description에는 Context Capsule 포함
테스트 결과 필수
Claude review 전 merge 금지
```

## 9.7 매일 작업 루틴

### 시작

```text
1. PROJECT_STATE.md 읽기
2. TASK_BOARD.md에서 오늘 작업 선택
3. Claude Fable로 오늘의 설계 리스크 1회 점검
4. Codex Goal 1~3개 실행
```

### 중간

```text
1. Codex가 테스트/구현 반복
2. 사용자는 결과 확인
3. 막힌 부분만 Claude에 압축 질문
```

### 종료

```text
1. Codex가 HANDOFF_CODEX.md 업데이트
2. 사용자가 핵심 결정을 DECISIONS에 기록
3. Claude가 다음날 작업 계획 리뷰
4. PROJECT_STATE.md 갱신
```

---

## 10. Claude Prompt Template

```md
너는 Homage1.0의 수석 아키텍트다.
아래 Context Capsule만을 근거로 판단하라.
전체 구현을 하지 말고, Codex에게 넘길 수 있는 Implementation Brief를 작성하라.

중점:
- 장기 아키텍처 일관성
- 작은 모델/Neuro-Symbolic/GraphRAG/Guardrail 방향 유지
- 과도한 범위 확장 방지
- 테스트 가능한 산출물로 쪼개기

[Context Capsule]
...

[질문]
A와 B 중 무엇이 낫고, 이번 milestone에서는 무엇을 해야 하는가?

[출력 형식]
1. 결론
2. 이유
3. 리스크
4. Codex Implementation Brief
5. Acceptance Criteria
```

---

## 11. Codex Goal Template

```md
/goal Complete [specific objective] in the Homage1.0 repo.

Read first:
- PROJECT_STATE.md
- ARCHITECTURE.md
- TASK_BOARD.md
- docs/implementation_briefs/[brief-name].md

Scope:
- Modify only [paths]
- Do not change [non-goals]

Acceptance criteria:
- [test command] passes
- [feature behavior]
- HANDOFF_CODEX.md updated
- SESSION_LOG.md updated

Stop when:
- acceptance criteria pass, or
- you are blocked by missing information.

Work in checkpoints and keep a short progress log.
```

---

## 12. MVP 범위

## Homage1.0 Alpha

### 포함

- GitHub repo 운영 체계
- BakeBoard shell
- DataGate rule-based MVP
- Ontology Forge simple graph MVP
- Homage-Core-30M from-scratch training
- GPU/loss dashboard
- GraphRAG trace mock 또는 minimal prototype
- Guardrail rule-based MVP
- Context Handoff Protocol

### 제외

- 1B 이상 모델 학습
- 복잡한 RL
- 완전 자동 웹 대규모 크롤링
- 상용 수준 챗봇
- 복잡한 안전 모델
- 완전한 OWL/RDF 온톨로지

---

## 13. 성공 기준

## 13.1 Alpha 성공 기준

```text
1. 웹에서 문서 또는 로컬 md 파일을 넣을 수 있다.
2. DataGate가 품질 점수와 폐기 이유를 표시한다.
3. Ontology Forge가 노드/엣지를 만든다.
4. Homage-Core-30M이 처음부터 학습된다.
5. 학습 loss와 GPU 사용량이 BakeBoard에 표시된다.
6. 간단한 질문에 답변을 생성한다.
7. 답변에 사용된 온톨로지 노드가 표시된다.
8. Guardrail이 과장 표현 하나 이상을 수정한다.
```

## 13.2 Beta 성공 기준

```text
1. Homage-Core-120M 학습 가능
2. GraphRAG evidence bundle 생성 가능
3. Claim-level verification 가능
4. Context Capsule만으로 Claude/Codex handoff 가능
5. Eval-100에서 baseline 대비 개선 확인
```

---

## 14. 평가 지표

### 모델 지표

- validation loss
- perplexity
- tokens/sec
- VRAM usage
- training stability

### 온톨로지 지표

- concept extraction precision
- relation extraction precision
- edge confidence distribution
- active node sparsity
- graph path consistency

### RAG 지표

- retrieval precision
- evidence support rate
- multi-hop retrieval success
- graph path relevance

### Guard 지표

- unsupported claim rate
- overclaim correction rate
- ontology conflict detection
- false positive rate
- false negative rate

### 사용자 체감 지표

- 답변 정확도
- 답변 구조성
- 근거 표시 신뢰도
- 시각화 이해도

---

## 15. 리스크와 대응

| 리스크 | 설명 | 대응 |
|---|---|---|
| 범위 과대 | 공장 전체를 한 번에 만들려 할 위험 | Alpha 범위 고정 |
| 모델 성능 부족 | from-scratch 소형 모델은 답변 품질이 낮을 수 있음 | GraphRAG/Utterance Engine으로 보완 |
| 데이터 오염 | 웹크롤링 품질 문제 | DataGate 우선 개발 |
| 온톨로지 오염 | 잘못된 edge가 쌓일 수 있음 | evidence/confidence/status 분리 |
| Fable 소진 | Claude Fable 사용량이 빨리 닳음 | 설계/리뷰에만 사용 |
| Codex 컨텍스트 단절 | 세션 공유 불가 | Context Capsule + repo 문서 |
| GPU 병목 | 16GB VRAM 한계 | 30M→120M→180M 순차 실험 |
| 개발 분산 | Claude/Codex 결과가 서로 어긋남 | PR/ADR/HANDOFF 강제 |

---

## 16. 참고 자료

### Claude / Codex 운영 참고

- Anthropic, Claude Fable 5 and Claude Mythos 5 announcement: https://www.anthropic.com/news/claude-fable-5-mythos-5
- Anthropic, Claude Fable product page: https://www.anthropic.com/claude/fable
- Claude Help, Fable context window / training cutoff references: https://support.claude.com
- OpenAI Codex Goal mode: https://developers.openai.com/codex/use-cases/follow-goals
- OpenAI Codex app commands: https://developers.openai.com/codex/app/commands
- OpenAI Codex app features: https://developers.openai.com/codex/app
- OpenAI Help, Codex usage with ChatGPT plans: https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan

### GraphRAG / RAG / Memory

- Microsoft GraphRAG: https://microsoft.github.io/graphrag/
- LightRAG: https://arxiv.org/abs/2410.05779
- HippoRAG: https://arxiv.org/abs/2405.14831
- Self-RAG: https://arxiv.org/abs/2310.11511
- RAPTOR: https://arxiv.org/abs/2401.18059

### Small LM / Training Efficiency

- TinyStories: https://arxiv.org/abs/2305.07759
- MobileLLM: https://arxiv.org/abs/2402.14905
- Chinchilla Scaling Laws: https://arxiv.org/abs/2203.15556
- phi-1 / Textbooks Are All You Need: https://arxiv.org/abs/2306.11644

### Guardrails / Hallucination Control

- NeMo Guardrails: https://arxiv.org/abs/2310.10501
- Llama Guard: https://arxiv.org/abs/2312.06674
- Self-RAG: https://arxiv.org/abs/2310.11511

---

## 17. 다음 액션

### 바로 할 일

```text
1. GitHub repo 생성
2. docs/PRD.md 저장
3. PROJECT_STATE.md 생성
4. TASK_BOARD.md 생성
5. Codex로 BakeBoard shell 구현 시작
6. Claude Fable로 Alpha architecture review 1회 실행
```

### 첫 Codex Goal

```md
/goal Create the Homage1.0 repo skeleton with FastAPI backend, Next.js BakeBoard frontend, shared docs folder, PROJECT_STATE.md, TASK_BOARD.md, HANDOFF_CODEX.md, HANDOFF_CLAUDE.md, and a mock pipeline status API. Stop when both frontend and backend run locally and README.md explains how to start them.
```

### 첫 Claude Fable 요청

```md
너는 Homage1.0의 수석 아키텍트다.
아래 PRD를 기준으로 Alpha 범위가 과도한지 검토하고,
Codex가 1주차에 구현해야 할 작업을 5개 이하의 PR 단위로 쪼개라.
각 PR에 acceptance criteria와 non-goals를 붙여라.
```

---

# 결론

Homage1.0은 **모델 하나를 만드는 프로젝트가 아니라, 모델이 만들어지고 생각하고 검증되는 과정을 보여주는 투명 AI 공장**이다.

Claude Fable 5는 수석 설계자처럼 아껴 쓰고, Codex Pro는 GitHub repo 안에서 실제 개발을 밀어붙이는 실행 엔진으로 쓴다. 둘 사이의 세션 공유 문제는 GitHub, Context Capsule, HANDOFF 문서, PR 단위 작업으로 해결한다.

가장 중요한 원칙은 이것이다.

```text
Fable은 결정한다.
Codex는 만든다.
GitHub는 기억한다.
BakeBoard는 보여준다.
Homage-Core는 처음부터 배운다.
```
