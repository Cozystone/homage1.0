# ATANOR 첫 프로젝트 — Realcity 디지털트윈 (2026-07-21)

사장님 비전: Realcity 3D 가상도시에 ATANOR를 **에이전트로 넣어** 그 세계를 보며 상호작용하고,
플레이어(사장님)는 realcity.vercel.app로 접속해 ATANOR와 대화하며, ATANOR는 **세상을 학습하며
직접 코드를 수정해 도시를 더 실제답게** 만든다.

## 이미 된 것 (오늘)
- **ATANOR = NPC 두뇌 (SHIPPED)**: `apps/api/app/routers/realcity_agent.py` — Realcity `localLLM.js`가
  쓰는 ollama-generate 프로토콜(`{prompt}`→`{response}`)을 그대로 말한다. `VITE_LOCAL_LLM_ENDPOINT`를
  ATANOR로 돌리면 **모든 시민이 ATANOR 엔진으로 사고**한다. 실측:
  - "컵이 가장자리에 있고 쳤어. 어떻게 돼?" → "the cup falls (미지지→낙하)" — **작동원리 추론이 도시 안에서**
  - "터널이 막혔는데 버스가 지나가?" → "no (막힌 길은 통과불가)"
  - "안녕" → 사회적 인사, "어제 뭐 먹었어?" → "네 삶이라 내가 볼 수 없어"(정직, 작화無)
  - **ATANOR 시민은 거짓말을 안 한다** — 살지 않은 삶을 지어내지 않는다(정직성이 캐릭터).
- **코드 저작 엔진 (SHIPPED)**: `packages/code_reason/code_author.py` — 구조적 합성+검증, 0.0→1.0.
  도시 코드를 ATANOR가 수정할 때 **검증 게이트**(자기수리 폐루프와 동형)로 안전 보장.

## 배선 (로컬 우선 → 배포)
1. **로컬**: Realcity를 `npm run dev`로 띄우고 `.env`에 `VITE_LOCAL_LLM_ENDPOINT=http://127.0.0.1:8502/api/realcity/agent`.
   → 로컬 도시의 NPC가 즉시 ATANOR로 사고. 브라우저 프리뷰로 실증 가능.
2. **배포(realcity.vercel.app)**: 브라우저→로컬 ATANOR 직결 불가(엔진이 로컬). 두 경로:
   (a) 로컬 엔진을 터널(Tailscale/cloudflared)로 노출 → Vercel env가 그 URL. (b) Vercel serverless
   `api/`에 ATANOR 프록시(로컬로 릴레이). BL-0급 온보딩 필요 — 사장님 승인 사항.

## 지각·학습 루프 (디지털트윈)
- **지각**: 각 프롬프트의 world-state(장소·필요·주변 시민)가 ATANOR의 **도시 지각**. `world` 필드로
  구조화 전달 → S2 점화 후보 + S1 stakes에 "converse"로 기록(이미 배선). 도시가 ATANOR의 lived
  record에 들어온다 = 진짜 상호작용.
- **학습**: 도시에서 만난 개념·인과를 자기 웹/그래프로 학습(세계멘토·인과추출 재사용). 도시 = 살아있는
  코퍼스. 얀 르쿤 "world model"의 놀이터.

## 코드 수정 루프 (도시를 더 실제답게)
ATANOR가 도시를 개선하는 방식 = **자기수리 폐루프를 Realcity 코드베이스로 확장**:
1. 결함/개선점 식별(예: "택시가 벽을 통과한다" = collision.js 작동원리 위반, ATANOR의 mechanism
   추론이 잡음 — "막히면 통과불가"를 도시가 어긴다).
2. code_author가 패치 합성(또는 GPT 초안+ATANOR 검증).
3. **테스트/시뮬 게이트**(도시가 여전히 뜨고 회귀 없음) 통과 시 적용, 아니면 복원.
4. 저널링. → **ATANOR가 자기 작동원리 이해로 도시를 더 물리적으로 만든다.**

## 마일스톤
| # | 항목 | 상태 | 게이트 |
|---|---|---|---|
| R1 | ATANOR=NPC 두뇌 어댑터 | ✅ SHIPPED | 실호출 검증 |
| R2 | 로컬 Realcity에 배선+브라우저 실증 | ✅ SHIPPED | 시민이 ATANOR로 답 |
| R3 | world-state 구조 지각 → 도시맥락 추론 | ✅ SHIPPED | 장소/이웃 인지 답변 |
| R4 | 도시 코드 자기수정(collision/물리) | 다음(협업저작) | 회귀無 개선 |
| R5 | 배포 노출(터널/프록시) | 사장님 승인 | 공개 URL서 ATANOR 대화 |

## R2 실증 (2026-07-21) — 로컬 배선 + 브라우저 프루프
- `projects/realcity`에 클론, `.env.local` → `VITE_LOCAL_LLM_ENDPOINT=http://127.0.0.1:8502/api/realcity/agent`.
- **ATANOR 대사(ambassador) 3명 = 시그니처 틸 `#00e5c0`** (cityEngine.js `ATANOR_AMBASSADORS`, Actors.jsx `ATANOR_LOOK`).
  스토어 실측: 160 에이전트 중 npc_0~2(Joon Lee/Yujin Choi/Joon Moon)만 `brain:'atanor'`·틸, 나머지 로컬·잡색.
  → **사장님이 접속하면 색으로 즉시 구분**. 덤: ATANOR 대사는 영어로 답(영어-only 독트린)이라 언어로도 구분됨.
- 브라우저(도시 페이지)→ATANOR 엔드포인트 실호출: "the glass falls (미지지→낙하)" 6ms. CORS·두뇌·추론 폐루프 실증.

## R3 실증 (2026-07-21) — 도시 world-state 구조 지각
- 도시는 구조화 JSON `world`를 안 보냄 — 지각은 **프롬프트 텍스트에 박혀** 옴(`Name/Job/Current place/
  Current activity/Reflection(strongest pressure)/City state`, 그리고 폰 shape `Current place/activity: X / Y`).
- `realcity_agent._perceive(text)`가 두 shape 모두 파싱 → 상황-자기 질문("what's happening here/where are you/
  who are you")을 **지각된 world-state로 접지 답변**. 실측(라이브 :8502):
  - "what is happening here" → "I'm pulling espresso shots over at River Cafe; what's pulling at me is
    checking in with someone; around me: mid-morning, light foot traffic on Depot-gil."
  - "where are you"(간호사) → "I'm at Hanbit Hospital right now, on shift." (시민 간 교차오염 0)
  - 물리 질문은 여전히 mechanism 접지("the cup falls"), 지식은 base_brain 유지.
- **디지털트윈 폐루프 실증**: 도시의 place/activity가 stakes 저널(lived record)에 유입 —
  `{"source":"realcity","agent":"Joon Lee","place":"River Cafe","activity":"pulling espresso shots","decision":"converse"}`.
  vitals coherence 0.25 결핍이 "repair" 욕구를 실제로 구동(연극 아님).
- **환각-제로 게이트 수리**: base_brain이 관계형 "X of Y" 조회를 `intent=define`로 오라우팅해
  "capital of France → capital is named after Washington"(confidence 0.91의 **오답**)을 뱉음.
  어댑터에 정밀 가드 추가(관계형 lookup ∧ intent=define → 정직 기권). photosynthesis 등 진짜 define은 통과.
  → 시민이 **틀린 사실을 자신있게 말하지 않음**(정직=캐릭터 유지). 진짜 지식갭은 C2/four-walls 트랙 소관.

## 정직 경계
- ATANOR 시민은 LLM만큼 수다스럽지 않다 — **접지된 것만 말하고 나머진 정직히 사양**. 이게 특징이자 철학.
- 도시 코드 자작은 **검증 게이트 필수**(작화불가의 코드판). 코드 저작 능력은 성장 중(스켈레톤 첫 계단).
