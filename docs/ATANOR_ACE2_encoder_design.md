# ACE2 — 인코더 백본 결정체 설계 (2026-07-16, 사장님 지시 "완벽하게 설계")

## 0. 한 줄
**word-level 어휘를 BPE 16k로 갈고, MLM을 ELECTRA-RTD로 갈고, 5×256을 12×384(GeGLU+RoPE+pre-norm)로
갈아, 우리 enwiki 코퍼스(~0.9B 토큰)를 2-3에폭 도는 24h 단일-GPU 재사전학습** — 그 위에 기존 헤드 사다리
(SQuAD2→Hotpot→support→동결 하드네거 캘리브레이션)를 그대로 다시 태운다. 이름 ACE2.

## 1. 왜 지금 "백본"인가 — 측정 사슬 (믿음 아님)
이 세션의 모든 벽이 한 지점으로 수렴했다:
- answerability 헤드-온리 플래토 **0.704** (하드네거 더 줘도 0.697 — 헤드는 백본이 주는 걸 다 뽑았다)
- span gold F1 **0.53**, SQuAD2 F1 **50.6** (M2 게이트 55 미달)
- relevance 헤드 **포화**(전부 ~1.0, 임계 불가) · S2≈S1 (0.352≈0.350) · 모놀로그<병렬
- 블라인드 MLM 이어붙이기 **회귀**(0.672→0.643) — 백본을 만지되 목적 없이 만지면 죽는다
→ 남은 유일한 레버 = 백본 그 자체. 단, **표적 있는 재설계**로 (0-8 블라인드 전례 회피).

## 2. 현 ACE의 4대 구조 결함 (진단)
1. **word-level 어휘 60k + 4096 해시버킷**: (a) 임베딩이 7.7M(≈모델 28%)을 룩업에 소모, (b) 희귀
   엔티티(QA의 돈이 되는 토큰)가 해시 충돌로 뭉개짐, (c) 스팬 경계가 단어 granularity에 갇힘
   → span F1 천장·포화의 구조 원인. 강한 소형 인코더 전부 subword 사용.
2. **MLM 15%**: 토큰의 15%에서만 학습 신호. RTD는 전 위치에서 신호 — 문헌상 **3-7× 수렴 효율**.
3. **5층×256 얕음**: 같은 파라미터로 깊고 좁은 쪽이 소형에서 우월(MobileBERT/Turc/LTG-BERT 계열 소견).
4. **사전학습량 ~0.2B 토큰×1에폭**: BabyLM 우승(LTG-BERT)은 0.1B 단어로도 되지만 **다에폭 반복** 전제.
   우리는 1에폭에서 멈췄다. 반복(≤4에폭≈신선 데이터)을 안 쓴 것.

## 3. 문헌 증거 (검증 완료, 2026-07-16 검색)
| 논문/결과 | 발견 | 우리 채택 |
|---|---|---|
| **ELECTRA** (Clark et al. 2020) | RTD가 MLM 대비 3-7× 수렴, 1/4 FLOPs로 RoBERTa 동급; **ELECTRA-Small(14M) 단일 GPU 수일 → SQuAD2 F1 74.8** | 목적함수=RTD (λ=50, 소형 G 병행훈련) |
| **Cramming** (Geiping & Goldstein 2022) | 소비자 GPU(2080ti) **1일**로 BERT-base 근접; one-cycle LR·시퀀스 패킹·seq128 | 24h 예산·one-cycle·패킹; 우리 5080은 그 GPU보다 수 배 빠름 |
| **BabyLM/LTG-BERT** (2023-24) | **0.1B 단어로 조 단위 학습 모델 능가**; pre-norm+GeGLU+위치정보 분리; 다에폭 반복이 유효 | 아키텍처 3종 채택; 코퍼스 반복 2-3에폭 (우리 데이터는 BabyLM의 8×) |
| SpanBERT (Joshi et al.) | 스팬 마스킹이 extractive QA에 +2-3 F1 | G 마스킹을 스팬 단위로 |
| Should-You-Mask-15% (Wettig et al.) | 15%는 신성불가침 아님; 중-고 마스킹률 유리 | 마스킹률 25% |
| DAPT/TAPT (Gururangan et al.) | 태스크 도메인 텍스트로 마무리 사전학습 시 소예산 이득 | 마지막 5% 스텝에 SQuAD/Hotpot 문단 혼입 |
| 데이터 제약 스케일링 (Muennighoff et al. 2023) | ≤4에폭 반복 ≈ 신선 데이터 | 2-3에폭 정당화 |

핵심 판단: **ELECTRA-Small(우리와 동급 14-28M, 단일 GPU)이 SQuAD2 74.8 F1** — 우리 게이트(55)는 문헌
천장보다 한참 아래. 예산도 데이터도 문헌이 "충분"이라 답한다. 이 벳은 무모하지 않다.

## 4. 설계 결정 (결정 / 근거 / 기각 대안)
1. **토크나이저: byte-level BPE 16,384** (+6 specials), 우리 enwiki 300MB 샘플로 직접 훈련.
   근거: 결함1 제거 + 임베딩 6.3M으로 절약분을 깊이에 재투자. HF `tokenizers`는 **훈련 도구**(가중치
   아님, PyTorch와 동급) — 차터 클린. 기각: word-level 유지(천장 재생산), 32k(소형엔 임베딩 과다).
2. **목적함수: ELECTRA-RTD** — 소형 생성기 G(2.5M, d192×4L)가 25% 스팬-마스킹 MLM, 판별기 D(본체)가
   전 토큰 real/replaced 판별, loss = L_G + 50·L_D. G는 사전학습 후 **폐기**(훈련 비계).
   근거: 3-7× 효율 + **판별 표현이 answerability 판정과 동형** — 우리가 필요한 바로 그 능력을
   전 토큰에서 배운다. 차터: G는 우리가 밑바닥부터 병행훈련 — No-LLM 준수. 기각: 순수 MLM(효율),
   distillation(교사=사전학습 모델이라 차터 위반; MobileBERT 경로 불가).
3. **본체: d384 × 12층 × 6헤드, GeGLU FFN 1024, pre-norm, RoPE, dropout 0.1** ≈ **27.7M**
   (지금과 같은 총량, 그러나 깊이 2.4×+subword). 근거: LTG-BERT 3종 채택 + 깊-좁 우월. RoPE=위치
   테이블 제거·길이 외삽. 기각: 더 큰 모델(GPU/지연 예산, 노트북 구동 정체성).
4. **데이터: 전체 enwiki 패시지(~0.9B BPE 토큰) × 2-3에폭, 시퀀스 패킹 seq128**, 마지막 5%는
   SQuAD/Hotpot 문단 TAPT. 근거: Cramming 패킹 + BabyLM 반복 + TAPT.
5. **최적화: AdamW(0.9,0.98) wd0.01, one-cycle peak 5e-4 (warmup 3%), micro-bs 64×accum 8=512,
   bf16, clip 1.0, masked-positions-only G 프로젝션**(기존 OOM 트릭 재사용).
6. **손 자질 6종 제거**(NFEAT 채널 0). 근거: 제대로 사전학습된 subword 표현엔 불필요(문헌 일관).
   단순화 — 단 A/B로 확인, 회귀 시 복원.
7. **헤드/인터페이스 불변**: ans/start/end/support 헤드 API, encode/collate 시그니처, 평가 하니스,
   ATANOR_SQUAD_CKPT 배포 경로 전부 유지 — 폭발 반경 최소화. 새 토크나이저는 data.py 뒤에 숨는다.
8. **파인튠 사다리 재사용**: SQuAD2 조인트(ans_w=2, LLRD 0.9) → Hotpot span → ranker → support →
   **동결 하드네거 캘리브레이션**(이번에 검증된 +0.03 레시피를 최종 폴리시로) → 임계 캘리브레이션.
9. **버저닝**: ace2_* 체크포인트, 현역(ace_squad*.pt) 불가침. 이길 때만 배포 (v2-MLM 사고의 규율).
10. **이어붙이기 금지**: ACE2는 from-scratch. (회귀 원인이던 fresh-head+전체해동+무리플레이 경로 차단.)

## 5. 훈련 계획 (Phase A→D) + go/no-go
- **A. 토크나이저+데이터 (CPU, ~0.5일)**: BPE 훈련 → **스팬 정렬 속성 게이트**: SQuAD 답 10k 샘플이
  offset 왕복으로 char-정확 복원 ≥99.9% **통과 전 GPU 지출 금지**. 패킹 스트림 작성.
- **B. RTD 사전학습 (GPU ≤24h 하드캡)**: SPLATRA 일시정지(승인 패턴), 엔진 유지.
  **프로브 게이트**: +3h 동결백본 로지스틱 ans-프로브 AUC ≥0.62, +8h ≥0.68 — 미달 시 **킬**(싸게 죽음,
  0-8 교훈). 체크포인트 매 5k스텝.
- **C. 파인튠 사다리 (~0.5일)**: 결정8 순서. 각 단 A/B.
- **D. 통합 (~0.5일)**: env-스왑 → doubt/D3/realtime 재측정 → 이기면 배포+워치독 복원+웜 배터리.

## 6. 봉인 게이트 (A/B, 이길 때만 배포)
| 게이트 | 현역 | 목표 |
|---|---|---|
| answerability AUC | 0.704 | **≥0.75** |
| SQuAD2 overall / HasAns F1 | 50.6 / 44.2 | **≥55 / ≥45** (차터 M2) |
| gold span F1 | 0.53 | **≥0.60** |
| HotpotQA full-pipe F1 | 0.409 | **≥0.50** |
| live novel-fact F1 | 0.789 | **무회귀 ≥0.78** |
(문헌 천장 참고: ELECTRA-Small 74.8 — 우리 목표는 그보다 보수적. 정직.)

## 7. 리스크 레지스터
| 리스크 | 확률 | 완화 / 조기신호 |
|---|---|---|
| 토크나이저 offset 버그가 span 천장 재생산 | 중 | **A-게이트(99.9% 왕복) 통과 전 GPU 금지** |
| RTD G/D 결합 버그 | 중 | 100배치 과적합 사니티(D acc>95%), 손실비 모니터(50·L_D ≈ L_G 초기) |
| 사전학습 정체 | 중저 | 3h/8h 프로브 킬 게이트 — 실패해도 반나절 손실 |
| 파인튠서 회귀 | 저 | 전 단 A/B + ace2_* 버저닝, 현역 불가침 |
| 호스트 메모리 사고(이력) | 중 | SPLATRA 정지, commit-headroom 가드 재사용, 종료 후 워치독 복원 |
| 손자질 제거 회귀 | 저 | 결정6 A/B, 복원 옵션 |

## 8. 정직한 확률 + 일정
- AUC·SQuAD·span 게이트(G-A/B/C): **~65-70%** (문헌이 예산 위에 있다고 답함)
- HotpotQA 게이트(G-D): ~50% · 전 게이트 그린: **~45-55%**
- 일정: A 0.5d → B ≤1d → C 0.5d → D 0.5d = **총 2.5-3.5일**, 3h/8h 킬 게이트로 하방 방어.
- 실패 시에도 얻는 것: BPE 토크나이저+패킹 파이프(재사용), "백본 재사전학습도 벽" 확정(다음 봉투로).

Sources: [ELECTRA framework](https://www.emergentmind.com/topics/electra-pre-training-framework) ·
[ELECTRA-Small](https://www.emergentmind.com/topics/electra-small-model) ·
[ELECTRA paper](https://www-nlp.stanford.edu/pubs/clark2020electra.pdf) ·
[Google ELECTRA blog](https://research.google/blog/more-efficient-nlp-model-pre-training-with-electra/) ·
[Cramming (arXiv 2212.14034)](https://arxiv.org/pdf/2212.14034) ·
[BERT on 8GB consumer GPU](https://sidsite.com/posts/bert-from-scratch/) ·
[MosaicBERT](https://www.databricks.com/blog/mosaicbert) ·
[BabyLM Findings (arXiv 2504.08165)](https://arxiv.org/abs/2504.08165) ·
[BabyLM overview](https://www.emergentmind.com/topics/babylm-challenge)
