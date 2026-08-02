---
channel: linkedin
status: draft
created_by: atanor-marketing
approved_at:
posted_url:
---

# LinkedIn 파운더 노트 — 영문 + 한글 (운영자 개인 계정 명의)

톤: 사업/파운더. 문제 → 접근 → 검증 → 사전모집. 1인 개발 서사, 진솔하게.
정직성: "환각 0%"/"hallucination-free"/"N% accurate" 금지. "quotes its sources / reasoning record / designed not to invent facts it has no source for"로만. 검증 불가 수치 미기재.
운영자 개인 계정에서 1인칭으로 게시. 데모 링크가 주장을 대신한다.

---

## 영문 (EN)

I spent the last stretch building something that runs against the grain of how most AI is being shipped right now.

Most language models generate an answer token by token — plausibility is the objective, and truth is, at best, a side effect. You get fluent text with no receipt, your data metered by the token in someone else's data center, and no way to audit *why* the answer says what it says.

I wanted the opposite default. So I built **ATANOR**: an AI that answers by *quoting* facts from an explicit knowledge graph, not by generating text with a language model. Three things it's built around:

→ **Every answer carries a reasoning record.** Which concepts were folded, which source was quoted. You can inspect why an answer exists instead of trusting billions of opaque weights.

→ **Local-first by design.** Private memory stays on your device. There's a deliberate wall between the local runtime and the shared cloud layer — personal context never silently becomes public. The mini version on the site runs entirely in your browser: no GPU, no server call after the page loads.

→ **It's designed not to invent facts it has no source for.** If the graph doesn't cover your question, it's built to say so rather than fabricate.

I'll be straight about the tradeoff, because it matters: large models win on breadth and fluency — that's their dimension. ATANOR is narrower and blunter, weak at arithmetic and creative writing by design, and its quality ceiling is the size of its knowledge graph. Those limits are written into the public repo, not hidden. I'm not claiming a headline accuracy number, because I can't honestly defend one across arbitrary questions. What I can stand behind: answers are quoted from sources, they carry a reasoning record, and the architecture is built to be inspected.

This is a public alpha, built solo. The point of sharing it now isn't to declare it finished — it's to put a different bet in front of people: transparent, local, source-quoting reasoning as an alternative axis to scale.

You can try the mini engine in your browser (no signup), read the architecture, and join early access here:
▶️ https://atanor-liard.vercel.app

If this direction resonates, I'd genuinely value your read on where it's useful and where it isn't.

---

## 한글 (KO)

요즘 대부분의 AI가 만들어지는 방식과 정반대로 가는 걸 한동안 만들었습니다.

거대 언어모델은 답을 토큰 단위로 생성합니다. 목표는 "그럴듯함"이고, 진실은 잘해야 부산물입니다. 유창하지만 근거는 없고, 당신의 데이터는 남의 데이터센터에서 토큰 단위로 과금되며, 답이 "왜" 그렇게 나왔는지 검증할 길이 없습니다.

저는 반대의 기본값을 원했습니다. 그래서 **ATANOR**를 만들었습니다 — 언어모델로 텍스트를 생성하는 대신, 명시적 지식 그래프에서 사실을 "인용"해 답하는 AI입니다. 세 가지 축으로 설계했습니다.

→ **모든 답에 추론 기록이 붙습니다.** 어떤 개념이 접혔고, 어떤 출처에서 인용됐는지. 수십억 개의 불투명한 가중치를 믿는 대신, 답이 존재하는 이유를 검증할 수 있습니다.

→ **로컬 퍼스트 설계.** 개인 메모리는 기기에 남습니다. 로컬 런타임과 공유 클라우드 계층 사이에 의도적인 벽이 있어, 개인 맥락이 소리 없이 공개되지 않습니다. 사이트의 미니 버전은 브라우저 안에서 전부 돌아갑니다 — 페이지 로드 후 GPU도, 서버 호출도 없습니다.

→ **출처 없는 사실을 지어내지 않도록 설계했습니다.** 그래프가 질문을 커버하지 못하면, 지어내는 대신 모른다고 말하도록 만들었습니다.

트레이드오프는 솔직하게 말하겠습니다. 거대 모델은 넓이와 유창함에서 이깁니다 — 그게 그들의 차원입니다. ATANOR는 더 좁고 무디며, 산술과 창작은 설계상 약하고, 품질의 상한은 지식 그래프의 크기입니다. 이 한계들은 숨기지 않고 공개 리포에 그대로 적어뒀습니다. 헤드라인 정확도 수치는 주장하지 않습니다 — 임의의 질문 전반에 정직하게 방어할 수 없기 때문입니다. 제가 책임질 수 있는 것: 답은 출처에서 인용되고, 추론 기록을 달고 나오며, 아키텍처는 뜯어볼 수 있게 만들어졌습니다.

공개 알파이고, 혼자 만들었습니다. 지금 공유하는 이유는 "완성됐다"는 선언이 아니라 — 다른 판돈 하나를 사람들 앞에 놓고 싶어서입니다. 규모(scale)에 대한 대안 축으로서의, 투명하고 로컬하며 출처를 인용하는 추론.

브라우저에서 미니 엔진을 직접 써보고(가입 없이), 아키텍처를 읽고, 사전 등록할 수 있습니다:
▶️ https://atanor-liard.vercel.app

이 방향이 공감된다면, 어디에 유용하고 어디에 그렇지 않은지 당신의 의견을 진심으로 듣고 싶습니다.

---

## 게시 노트

### 게시 시간 / 순서 권고
- launch_sequence상 X 다음, r/MachineLearning 전. HN/Reddit에서 기술 검증이 한 차례 돌면, 그 반응을 (과장 없이) 본문에 한 줄 인용 가능.
- LinkedIn은 텍스트 우선 채널이지만 데모 스크린샷/GIF 1장 첨부 시 도달률 상승. 가능하면 추론 인증서 패널 캡처 1장 첨부(운영자 액션 — 인간 게이트).
- 운영자 개인 계정 1인칭 게시. 회사 페이지 톤 금지 — 파운더의 솔직한 노트.

### 정직성 체크 (게시 전 재확인)
- [ ] "환각 0%"/"hallucination-free"/"N% accurate" 문구 0건
- [ ] 검증 불가 수치(엣지 수, 정확도 %, 개발 기간 구체 숫자) 0건 — 현재 초안 미기재
- [ ] GPT/거대모델 비교는 "breadth·fluency" 차원 인정으로 프레이밍(우열 단정 금지)
- [ ] 라이브 링크 200 OK 재확인(2026-07-09 확인)

### 해시태그 (선택, 3개 이하)
EN: #AI #KnowledgeGraph #LocalFirst
KO: #AI #지식그래프 #로컬퍼스트

### 근거 (본문 주장 → 검증 위치)
- "브라우저 안에서 전부, 로드 후 서버·GPU 호출 없음" → `apps/landing/assets/mini_atanor.js` 상단 주석 + 결정론적 그래프 조회 구현.
- "Local Brain / Cloud 벽, 개인 맥락 안 새어나감" → `docs/ARCHITECTURE.md` 원칙 1·2 + Local Brain 절.
- "산술·창작 약함, 그래프 크기가 상한, 클라우드 proof-scale" → `docs/ARCHITECTURE.md` Current Limitations.
- 정확도 수치 미기재 이유 → 임의 질문 전반 방어 불가. 검증은 `data/*/proofs` + 데모로 유도.
