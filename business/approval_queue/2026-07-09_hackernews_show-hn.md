---
channel: hackernews
status: draft
created_by: atanor-marketing
approved_at:
posted_url:
---

Show HN: ATANOR – an AI that answers from a knowledge graph, not an LLM

Hi HN. I've been building ATANOR, an experimental AI system that answers questions by selecting and quoting facts from a verified knowledge graph, instead of generating text token-by-token with a language model. Every answer comes with a small record of how it was assembled (which concepts were folded, which source was quoted).

There's a live mini version that runs entirely in your browser — no signup, nothing sent to a server:

https://atanor-liard.vercel.app

Ask it something like "What is the capital of Japan?" or "What is the speed of light?" and you'll see the answer quoted from the graph with a reasoning trace and a source tag. It's a small alpha graph, so coverage is limited — that limit is the honest core of the project (more on that in the comments).

Code (public alpha, architecture is meant to be inspected): https://github.com/Cozystone/ATANOR-Demo

I'll be around for the next few hours to answer anything, especially the hard architecture questions.

## 게시 노트

### 제목 옵션 (HN 가이드: 과장 형용사·기업 톤 금지, 사실 진술형)

1. `Show HN: ATANOR – an AI that answers from a knowledge graph, not an LLM`  ← 권장. 차별점이 제목에 있고, "not an LLM"이 클릭을 부른다.
2. `Show HN: ATANOR – answers quoted from a graph, with a reasoning receipt`
3. `Show HN: A local-first AI that quotes its sources instead of generating text`

각주: "no LLM" 앵글은 r/LocalLLaMA에서 특히 신선하지만 HN에서도 궁금증을 유발한다. 단, 제목에서 성능을
암시하지 말 것("better than GPT" 류 절대 금지 — HN이 즉시 반증하려 든다).

### 게시 시간 권고

- 화–목, 미국 동부 오전 8:00–10:00 (KST 21:00–23:00). launch_sequence D-day와 일치.
- 게시 후 첫 4시간은 모든 댓글에 기술적으로 성실 응답 (운영자 또는 승인된 세션).
- 무반응(<10pt) 시: 1주 후 다른 앵글("browser-local AI" 또는 "P2P graph brains")로 1회만 재게시.

---

### 첫 댓글 (기술 해설 — 게시 직후 운영자가 OP로 단다)

I'm the author. Here's how it actually works and, more importantly, where it's weak.

**Why no LLM.** A transformer predicts the next token; plausibility is the objective and truth is, at best, a side effect. I wanted the opposite default: an answer should be *selected from* verified knowledge, not *generated* and hopefully correct. So ATANOR keeps knowledge as an explicit graph and treats answering as retrieval + composition + quotation, not free generation.

**The pipeline, roughly:**

1. Knowledge lives as a graph — concepts, relations, evidence, and provenance — not as weights. There's a local, private "Local Brain" and a public "Cloud Brain" of content-addressed fragments; the two are kept separate on purpose (private memory never silently becomes public).
2. A question is resolved against that graph. Candidate concepts are activated and folded together; the pieces that constructively agree select the facts that answer the question.
3. The answer is **quoted from the matched sources** and tagged with a reasoning record — which fold produced it, which source it came from. That record is the point: you can audit why an answer exists, instead of trusting billions of opaque weights.
4. Improvements happen through a reviewable repair loop (bad answers become inspectable repair candidates), not invisible prompt edits.

**What this buys you:** answers are tied to a source you can inspect; the system is built so it does not invent facts it has no source for; and inference is cheap CPU work, so the mini version runs client-side in your browser with nothing leaving the machine.

**Now the honest part — where it's weak, by construction:**

- **Coverage is the ceiling.** If the graph doesn't cover your question, ATANOR is designed to say so rather than fabricate. The live demo runs a *small* alpha graph, so you'll hit gaps quickly. Quality here is a function of graph size and quality, not model scale — that's the whole bet, and it cuts both ways.
- **Arithmetic and open-ended creative writing are poor.** A quote-from-graph approach is genuinely weak at "compute 17*23" or "write me a poem." I'm not going to pretend otherwise — those aren't retrieval problems.
- **Semantic parsing is deterministic v0, not a perfect parser.** Word-sense ambiguity and messy phrasing still trip it.
- **Cloud Brain is proof-scale, not web-scale.** The P2P/contributor-node side is real code but early; it is not a global knowledge cloud today.

I deliberately don't make an "N% accurate" or "hallucination-free" claim, because I can't honestly stand behind a single headline number across arbitrary questions. What I can stand behind: answers are quoted from sources, they carry a reasoning record, and the boundaries above are documented in the repo (see the "Honest Boundaries" section and `docs/ARCHITECTURE.md`).

Large models win on breadth of general knowledge — that's their dimension. ATANOR is exploring a different one: transparent, local, source-quoting reasoning. Curious what this crowd thinks the approach is good and bad for. The architecture and committed proof artifacts are here: https://github.com/Cozystone/ATANOR-Demo

---

### 예상 질문 5개 + 답변 (댓글 대응용, 운영자/세션이 참고)

**Q1. "Isn't this just RAG / a knowledge graph with extra steps?"**
Fair framing — retrieval + a graph is the family it belongs to. Two differences in emphasis: (1) the answer is *quoted* from matched sources and shipped with a reasoning record you can audit, rather than fed to an LLM that then paraphrases (and can drift); (2) there's an explicit private/public memory boundary (Local Brain vs Cloud Brain) so personal context never silently joins a shared store. It's less "RAG feeding a model" and more "the graph *is* the answer path." Happy to be told where that distinction breaks down.

**Q2. "How is this different from just using GPT-4 with citations / grounding?"**
An LLM-with-citations still generates the sentence and then attaches sources; the text can say things the sources don't. ATANOR selects and quotes from the source first, so the sentence can't outrun its evidence. The tradeoff is real: LLM-with-citations is far more fluent and broad; ATANOR is narrower and blunter but structurally can't wander off its sources. Different points on the fluency-vs-faithfulness curve.

**Q3. "What are the actual numbers? Accuracy? Graph size?"**
I'm intentionally not headlining a single accuracy number, because it would be meaningless across arbitrary questions and I won't claim what I can't defend. What's real and inspectable: the repo commits proof artifacts under `data/*/proofs` and a sample Graph Hub catalog under `data/graph_hub/catalog`, and the whole thing is a public alpha with a test suite you can run. The live demo's graph is small on purpose — please do try to break it; the gaps are the honest signal.

**Q4. "The demo answered [X] wrong / said it doesn't know."**
Expected, and useful — thank you. Two failure modes I'd distinguish: (a) "doesn't know" = the graph lacks coverage, which is the designed-honest behavior (coverage is the ceiling); (b) an actually wrong quote = usually the answer is faithful to a source that is itself wrong or mis-parsed. If you paste the exact question I can tell you which one it is, and (b) goes into the repair loop. What shouldn't happen is a *fabricated* fact with no source — if you see that, it's a bug I want.

**Q5. "No LLM at all? How do you handle language / phrasing then?"**
"No LLM" refers to the answer-generation path: the answer is composed and quoted from graph structure, not sampled from a language model. Language handling (parsing the question, surface realization of the answer) is a separate, mostly deterministic layer with a reviewable repair loop, plus morphology rules for Korean. It's not as fluent as an LLM — that's the honest cost. The claim is about *where the facts come from*, not that there's zero NLP anywhere.

### 대응 원칙 (플레이북 준수)

- 기술 비판 = 선물. 정직하게 인정 + 수리 계획으로 답한다. 감정 소모전 금지.
- "환각 0%"/"hallucination-free" 절대 사용 금지. "quoted from sources", "carries a reasoning record",
  "designed not to invent facts it has no source for"로만.
- 검증 불가 수치(엣지 수, 정확도 %) 즉석 창작 금지. "proof artifacts under data/*/proofs, try the demo"로 유도.
- GPT-4 비교는 grounded/citation 범위로 한정하고 트레이드오프를 먼저 인정한다.
