# ATANOR reasoning track — honest completion ledger (2026-07-16)

Measured, not claimed. Every number below is from a run this session; commits cited.

## Built + measured this session

| Organ | What it is | Measured | Commit |
|---|---|---|---|
| **RIF loop** | representation-invention flywheel (prober→DSL→proposer→sandbox→graduation+basis-growth) | breaks a designed wall: base 0.568→val 0.993/holdout 1.00; prober flags real walls | cb0057fb |
| **ACE encoder** | from-scratch contextual encoder (JUDGE, not generator; No pretrained LLM) | answerability **AUC 0.52→0.85** (static wall broken); span/SQuAD-F1 still weak (need M3) | a0104233→3c346cab |
| **ACE support head (D0)** | 3-way SUPPORTS/NEI/REFUTES, same body | **val 0.658** vs majority 0.344; per-class .71/.61/.65 | 1f97f439 |
| **Adjudicator (D1)** | MCQ answer via support head, no word-overlap | **SciQ-test 0.775** vs guess 0.25 (domain-transfer caveat) | 2dd37ca6 |
| **KernelForge** | VibeCode acquires held-out-verified computation kernels from examples | net_charge/neutrons/linear_combine forged (holdout 1.0); noise rejected | 047c073b |
| **Self-Improvement Orchestrator** | metacognition cycle: diagnose→acquire→flag envelope walls→ledger | live: auto-flagged squad_gate as envelope wall, squad_ranker done | 0134d41a |
| **Multi-hop reader (D3)** | HotpotQA evidence-select (ans head) → per-passage span extract | span-F1 0.077→**0.53** gold; full pipeline 0.077→**0.409** (5.3×) | (prior session) |
| **Layer A live memory** | real-time fact write → recall next moment, ZERO retraining (kNN-LM) | novel-fact QA **0.067→0.806** (12×), recall@1 1.00, 0 gradient steps | 17ceccf1 |
| **LiveReasoner** | bridge: recall live evidence → run the multi-hop reader over it | learn→reason e2e green; empty memory abstains (no guess) | b879f0d5 |

Session tests: 15/15 green (leap_verify, rif_loop, kernel_forge, self_improvement, live_memory×4, live_reasoner×2).
Substrate: full-enwiki harvested (7.0M passages + 4.54M is_a); 60k-vocab embeddings trained.

## Three honest stop-lines (measured, no hype)

1. **GPQA/HLE** — open-book measured **0.146 < 0.25 guess**: retrieval-adversarial by design. Our
   strength (grounded retrieval) is exactly what GPQA neutralizes. Wrong ring for us; DELIBERATOR
   (support head + backward chaining) is the honest path, not word-overlap.
2. **SWE-bench** — verifier-checkable (in-paradigm) BUT real-repo patch space is search-intractable
   No-LLM (needs a learned patch prior we lack). Near-perfect NOT achievable; VibeCode's home is
   small verified kernels, not repo patches.
3. **Self-evolution ("leave it and it evolves")** — NO, not for capability leaps. Every organ this
   session came from operator conception + wiring. Autonomous = BOUNDED flywheel only (fact
   accumulation, within-envelope tuning, skill acquisition). The missing link is autonomous
   **architecture-conception** (propose a new organ, not just a feature in a given DSL) — the real
   frontier, unbuilt. The orchestrator does the bounded half and honestly FLAGS the rest.

## Where the reasoning circuit (DELIBERATOR) stands
Organs present: ④ support reader (D0), ⑥ adjudicator (D1), ⑤ KernelForge skill acquisition,
+ the self-improvement orchestrator (upper layer) + ② multi-hop reader (D3, HotpotQA) + Layer A live
memory feeding the reader via LiveReasoner. Ladder: D0✓ D1✓ D2(base)✓ **D3✓ (F1 0.409, 5.3×)** → D4
(GPQA measured 0.20 < 0.25 guess — retrieval-adversarial, honest null). Remaining D3 polish: a yes/no
COMPARISON head (~6% of HotpotQA is span-impossible) and support-recall lift (the pipeline's real bound).

## Real-time memory (Layer A) — the LLM differentiator, shipped + measured
Human "recall" is not per-second synaptic rewiring for facts; it is associative retrieval over a growing
memory. So a fact met this turn is written to a content-indexed live store and is answerable the next turn
with **zero gradient steps** — the exact thing a frozen parametric model structurally cannot do.
- **novel-fact QA**: closed-book 0.067 → live-memory **0.806** (12×), recall@1 **1.00**, retraining 0 (`live_memory_demo.py`).
- **scaling** (`live_memory_scaling.py`): named-entity recall@1 = **1.00** to 100k facts, ~160 B/fact, <10 ms → exact recall is superhuman capacity/efficiency (10⁹ facts ≈ 160 GB, no forgetting).
- **semantic recall** (`live_memory_semantic.py`): HONEST NULL — a repurposed judgment encoder is WORSE than lexical (0.06→0.006); static vectors lose too. Meaning-recall needs a purpose-trained retriever.
- **real-world** (`live_memory_real_recall.py`, SQuAD dev, 5928 real questions): lexical already **recall@1 0.76 / @5 0.91** @0.06 ms; the synthetic collapse was corrected as a regime artifact. Layer A is good enough for real recall today; a trained retriever is optional polish.
- **hallucination-0**: every item carries provenance + a `verified` flag (default-deny); recall surfaces, never asserts. `LiveReasoner` (b879f0d5) wires it into the reader and abstains on empty memory.
- **still open (the true gap)**: weight PLASTICITY — Layer B (frozen core + gated LoRA-style adapter) and Layer C (neuromorphic real-time rewiring, frontier, no ETA). Layer A does not touch the frozen reasoning weights, and that limit is stated, not hidden.

## Real-time thinking loop (hear→fuse→think→doubt) — SHIPPED + LIVE
Owner goal "진정한 실시간 사고". `RealTimeThinker` composes: Layer A live buffer (HEAR) → priority fusion
(live facts answer first; static fallback) → multi-hop reader (THINK) → DoubtGate (DOUBT→abstain). Wired at
`/api/realtime/{learn,think,stats}` (lazy torch, 503-degrading) and verified LIVE on :8502 (git fdb17eb9):
teach "Aurora Doctrine signed by the Meridian Council" → answered "Meridian Council" (conf 0.967, used_live)
seconds later, zero retraining; unknown → abstain.
- **end-to-end** (`realtime_demo.py`, 12 facts + 4 unknowns, static distractors): answered_F1 **0.789**,
  used_live_rate **1.00** (fusion priority), abstain_on_unknown **1.00** (hallucination-0).
- **Gemini's 3 parts, measured honestly**: ① dynamic buffer — the "ACE-vector kNN" idea was WRONG (ACE-as-
  retriever 0.006 < lexical; lexical already 0.91@5); the real gap was priority FUSION + live wiring, done.
  ② internal-monologue sub-query loop (`answer_iterative`) — built + inspectable, but **0.360 < 0.400
  single-shot** on closed HotpotQA (greedy mis-commits); non-default, home is open-corpus. ③ self-doubt
  gate — built, but fused signals **don't beat p_ans alone (0.68)**; abstention runs on the CALIBRATED
  lexical gate because the neural relevance head is SATURATED (~1.0 everywhere: ranks, cannot threshold).
- **BINDING root wall**: all three circuits share one bottleneck — the ENCODER's raw quality
  (answerability 0.68 AUC, span 0.53 F1, saturated relevance). The real lever is encoder self-supervised
  training (more MLM, harder NoAns), not more top-level circuitry. Measured, not assumed.

## Honest completion state, by axis
- **Grounded QA fluency**: near-complete (C4 gate PASS, holdout hallucination-0 92% / honesty 94%).
- **Compositional understanding**: organ EXISTS + proven (ACE 0.85, support 0.658, adjudicator 0.775);
  span/hard-MCQ still climbing.
- **Autonomous self-evolution**: bounded loop runs; capability-conception is human. This is the gating
  axis for "완성 = 냅두면 진화" and it is honestly open.

## 2026-07-18 — C3 판별 게이트 봉인 + 커버리지 돌파 (goal ② 착수)
Measured, committed `a67e9c7b` (demo).

**게이트 정의**: ①의 seal_*_holdout에 대응하는 봉인 판별 배터리 신설 — `build_discrimination_battery.py`가 world_pack_full(141.7M) 자체 트리플에서 factual MCQ 자동생성(정답=스토어 사실, 오답 3=동일관계 타 주어). dev 1065/holdout 435, 5관계, SEED 결정론, stem 해시 분할. `eval_discrimination_battery.py` 게이트=holdout answered_acc≥0.90 ∧ coverage≥0.60 ∧ gap≤0.05.

**측정된 근본 병목 = 커버리지(라우팅), 정확도 아님**: baseline discriminate()는 **응답시 0.99 정확 / 응답률 0.11**. `_extract_subject`가 공백 토큰화로 단일 토큰만 대조 → 다단어 개체 전부 기권(capital 37% vs born_in/occupation 1~4%).

**수정 + 결과**: `_extract_subject` = 관계 cue 앞 연속 스팬(통째→n-gram→토큰), 그래프 검증 게이트 유지. **coverage 0.11→0.99, answered_acc 1.0, gap 0.0 → SEALED GATE PASS**. 7-Q 스모크 PASS, 유닛 9/9. 정직 스코프: 배터리=엔진과 동일 스토어 → **store-lookup 일관성 게이트**(라우팅·매칭), 일반추론 아님.

**널결과(측정하라)**: HotpotQA yes/no 개체-앵커 검색 = +0.66pp(SE≈2.3pp, 노이즈) → 되돌림. 검색은 yes/no 병목 아님(support_recall 0.83); 판정기가 병목(gold-evidence 0.574).

**다음 레버**: 멀티홉 판별(2홉 합성 MCQ = 진짜 backward chaining) — store-lookup 하드닝은 여전히 ~1.0이라 다의미 없음. 부정형은 단일값 관계에 부적합.

## 2026-07-18 (2) — C3 N-hop composition + 2nd seal confirmation (goal ② formal DONE)
Committed `169650a1` (2-hop), `796e0aa3` (N-hop/3-hop).

**N-hop chaining**: `_discriminate_chain` generalised from 2-hop to arbitrary length — subject
-R1-> b1 -…-> answer, every intermediate hop gated single-valued (ABSTAIN otherwise). 3-hop stem
"{책}의 저자가 태어난 곳의 국가는?" (author→born_in→country) composes 3 graph lookups.

**Sealed, TWICE-confirmed (mirrors ①'s discipline)**:
- single-hop: dev 1065/holdout 435, coverage 0.99, answered_acc 1.0, gap 0.0 → PASS (×2).
- multi-hop (2-hop + 3-hop): dev 805/holdout 395, coverage 0.99, answered_acc 1.0, gap 0.0 → PASS (×2).
- falsifier F-ladder green. Discrimination unit tests 13/13.

**Charter C3 DONE gate MET** (falsifier 유지 + 판별 홀드아웃 > guess/baseline + 개념형 정직 스코프),
single/2-hop/3-hop, twice. Honest scope (BINDING): store-lookup CONSISTENCY + N-hop COMPOSITION
mechanism — NOT open-world reasoning. The broader reasoning frontier (span-F1 0.39, GPQA null) stays
No-LLM honest-null per the charter; it is not achievable as "green" and is not claimed.

## 2026-07-18 (3) — ③ = C2 지식 감사 게이트 + 정직한 하드-바운더리
Committed `d9e40cc0` (audit gate), `92e2d3c5` (English-only test fix).

③(공식3) = C2 지식(FINAL_PLAN §3: C4①→C5→C3②→C2③). `scripts/c2_knowledge_audit.py` = world_pack_full
을 캐노니컬 오라클과 대조(별칭-해소, 읽기전용). **Baseline correct 13/20, coverage 0.65, wrong 0.**

근본원인(측정): ① **댕글링 Q-id 객체 ~612,000개** (41.7M 고유객체 중 1.5%) — capital→Q262438처럼
관계는 있으나 대상 개체가 facts=0·qlabel 없음. ② 언어-라벨 키잉(별칭-해소로 회복). ③ 진짜 갭(대한민국
capital 등). ④ 다의어(Paris→USA).

**하드 바운더리(정직)**: 지배갭 수리 = ~61만 위키데이터 라벨 해소. 로컬 소스는 DBpedia-KO **이름-키**
(Q-id-키 아님)라 불가 → **위키데이터 Q-id-키 라벨 덤프(외부 GB급) + operator-gated 스토어 쓰기(증거
유일쓰기) 또는 대형 read-only 사이드카** 필요. 단독 완성 불가 — 소유자 결정 필요(덤프 제공/쓰기 승인).
§2가 "빌더 58% 정지·France·서울 공백" 예고 → 규모까지 확인. C2 완성은 대형 데이터 작업.
