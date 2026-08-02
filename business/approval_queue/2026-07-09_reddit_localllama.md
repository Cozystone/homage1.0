---
channel: reddit:r/LocalLLaMA
status: draft
created_by: atanor-marketing
approved_at:
posted_url:
---

**Title:** ATANOR – a local-first AI that answers by quoting a knowledge graph instead of running an LLM (mini version runs entirely in your browser tab)

Been lurking here for a while. This sub is where the "no-LLM" angle is least likely to get an eye-roll, so posting here first.

I've been building **ATANOR**, an experimental AI that answers questions by selecting and quoting facts from an explicit knowledge graph, rather than sampling tokens from a language model. The reason I think this crowd might find it interesting is the local-first / privacy side, not a performance claim.

**The part I can actually demonstrate:** there's a mini version on the landing page that, after the page loads, does *zero* server calls and *zero* GPU work. The answer path is deterministic graph lookup over a knowledge pack shipped to your browser. Ask it something and the "answer" is quoted from the pack with a small reasoning trace and a source tag — all client-side. No signup, nothing leaves the tab.

Live: https://atanor-liard.vercel.app
Code (public alpha): https://github.com/Cozystone/ATANOR-Demo

**How it's structured (relevant to local folks):**

- Knowledge is an explicit graph — concepts, relations, evidence, provenance — not weights.
- There's a deliberate **Local Brain vs Cloud Brain** split: private memory stays on the local runtime; the cloud layer only holds public graph fragments and proof-state. The architecture rule is that cloud/cartridge nodes can give a session temporary evidence but never *silently* write into your private local memory. (`docs/ARCHITECTURE.md` in the repo spells this out.)
- Answering = resolve the question against the graph, fold candidate concepts, select the facts that agree, and **quote from the matched source** with a reasoning record — instead of generating a sentence and hoping it's grounded.

**Why bother, vs a small local LLM?** Different tradeoff, not a "better" claim. A local sLLM gives you fluent, broad text on-device. ATANOR's bet is on *where the facts come from*: the answer is quoted from a source you can inspect, and it's designed not to invent facts it has no source for — if the graph doesn't cover your question, it's built to say so rather than fabricate. You give up fluency and breadth; you get an auditable path from source to answer.

**Honest boundaries (from the repo's Current Limitations section, not marketing):**

- The graph in the live demo is *small* on purpose, so you'll hit coverage gaps fast. Coverage is the quality ceiling here, full stop.
- Arithmetic and open-ended creative writing are genuinely weak — a quote-from-graph approach is the wrong tool for "compute 17*23" or "write me a poem."
- Semantic parsing is deterministic v0, not a perfect parser; messy phrasing and word-sense ambiguity still trip it.
- The Cloud Brain is proof-scale, not web-scale. The P2P/contributor-node side is real code but early.

I'm deliberately **not** posting an "N% accurate" or "hallucination-free" number, because I can't defend a single headline figure across arbitrary questions. What's inspectable instead: the repo commits proof artifacts under `data/*/proofs`, and the demo runs a real (small) pack you can try to break.

Genuinely curious what this sub thinks a local, source-quoting approach is good and bad for. Break the demo and tell me where it fails — the gaps are the honest signal, and wrong answers with a traceable source go into a reviewable repair loop.

## 게시 노트

### 제목 옵션 (r/LocalLLaMA — no-LLM 앵글이 신선, 로컬/프라이버시 강조)
1. `ATANOR – a local-first AI that answers by quoting a knowledge graph instead of running an LLM (mini version runs entirely in your browser tab)`  ← 권장. 로컬+브라우저 실동작이 이 서브의 관심축.
2. `A no-LLM AI whose mini demo does zero server/GPU calls after page load — answers quoted from a graph`
3. `Built a graph-native, local-first answering engine (no LLM in the answer path) — honest alpha, please break the demo`
- 성능 우위 암시 금지. sLLM 대비 "different tradeoff"로만 프레이밍. 이 서브는 벤치 없는 우위 주장을 즉시 반박한다.

### 게시 시간 권고
- launch_sequence상 HN 다음. HN이 프론트에 오르면 그 사회적 증거가 쌓인 뒤 게시 권장.
- 셀프프로모션 비율 규칙: 게시 전 이 서브에서 기술 댓글 참여를 먼저 쌓을 것(플레이북). 새 계정 즉시 링크 게시는 스팸 리스크.
- 같은 날 다른 서브 크로스포스트 금지(r/MachineLearning은 최소 하루 간격).

### 예상 질문 + 답변 (댓글 대응용)

**Q. "이거 그냥 로컬 RAG 아님?"**
같은 계열 맞습니다(retrieval + graph). 강조점 차이: (1) 답을 LLM에 먹여 패러프레이즈시키지 않고 매칭된 출처에서 그대로 인용 + 추론 기록 첨부 → 답이 근거를 벗어날 수 없음; (2) Local Brain / Cloud Brain 프라이버시 경계가 명시적. "RAG가 모델을 먹인다"기보다 "그래프 자체가 답 경로".

**Q. "왜 로컬 sLLM 안 쓰고?"**
트레이드오프 선택입니다. sLLM = 유창·광범위. ATANOR = 좁지만 출처 추적 가능 + 출처 없는 사실 안 지어내도록 설계. 우열이 아니라 축이 다름. 넓이가 필요하면 sLLM이 맞음.

**Q. "숫자는? 정확도/그래프 크기?"**
단일 정확도 수치를 일부러 헤드라인하지 않습니다(임의 질문 전반에 방어 못 하는 수치는 안 냄). 검증 가능한 것: `data/*/proofs`의 커밋된 proof 아티팩트, 그리고 데모의 실제(작은) 팩. 데모를 깨보시고 실패 지점을 알려주세요.

**Q. "브라우저에서 진짜 로컬로 도는 거 맞아? 백엔드 호출 없어?"**
네 — 페이지 로드 후 답변 경로는 브라우저 내 결정론적 그래프 조회입니다(`apps/landing/assets/mini_atanor.js` 상단 주석에 문서화, DevTools Network 탭으로 확인 가능). 팩(mini_brain.json)은 라이브 엔진의 큐레이션 트리플 스토어에서 export된 것.

### 대응 원칙 (플레이북 준수)
- "환각 0%"/"hallucination-free"/"N% accurate" 절대 금지. "quoted from sources", "carries a reasoning record", "designed not to invent facts it has no source for"로만.
- 검증 불가 수치(엣지 수, 정확도 %) 즉석 창작 금지 → "proof artifacts under data/*/proofs, try the demo"로 유도.
- sLLM/LLM 비교는 트레이드오프로 먼저 인정. 성능 우위 단정 금지.
- 비판·실패 제보 = 선물. 인정 + 수리 루프로 답한다.
