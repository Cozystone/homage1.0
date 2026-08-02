# ATANOR 브라우저 셸 계약 (Chrome형 AI 브라우저 — 구현 지시서)

2026-07-07 작성. ATANOR 브라우저 = **크롬 같은 실제 웹 브라우저**인데, 모든 브라우징
행위가 개인 브레인 그래프에 정리되는 AI 브라우저. 이 문서는 네이티브 셸을 기계적으로
구현하기 위한 계약이다. 엔진-측 로직은 이미 완성돼 있다(아래 §3).

## 0. 제품 경계 (혼동 금지)

- **ATANOR 프로그램(앱/exe)** = AI 그 자체(추론 엔진·자의식·대시보드·OS). 웹을 학습.
- **ATANOR 브라우저** = 웹을 렌더링하는 별개 응용프로그램(Chrome/Arc 범주). 이 문서 대상.
- **atanor-shell** = Wayland OS 컴포지터(또 다른 셸). 별개.

## 1. 아키텍처 결정 (변경 금지)

- **네이티브 웹뷰 필수.** iframe 브라우저는 가짜다 — 대부분의 실사이트가
  `X-Frame-Options: DENY` / `CSP frame-ancestors`로 임베드를 막는다. 반드시
  OS 네이티브 웹뷰를 쓴다:
  - **1순위: Tauri v2 + WebviewWindow** (이미 스택에 Tauri 있음; Rust 셸, 시스템
    WebView2(Win)/WKWebView(mac)/WebKitGTK(Linux) 사용, 경량).
  - 대안: Electron `BrowserView`(무겁지만 Chromium 완전제어), CEF(최고 제어·최고 복잡).
- **탭 = BrowserSession의 Tab 객체와 1:1.** 셸은 상태를 소유하지 않는다. 셸은
  이벤트만 방출하고, 세션 상태(활성탭·히스토리)는 엔진의 BrowserSession이 정본.
- **2레인 규칙(엔진이 강제).** 모든 네비게이션→개인 저널(항상·로컬). 페이지 내용→
  공유 인제스트(옵트인, DOM 전달 시에만). 히스토리는 기본 비공개.

## 2. 셸이 방출할 이벤트 (→ 엔진 API)

셸의 웹뷰 콜백에서 아래를 호출한다. 모두 이미 존재하는 라우트다:

| 셸 콜백 | 엔진 호출 | 비고 |
|---|---|---|
| 탭 생성 | (셸 로컬 tab_id 발급) | 세션 상태는 §3 오케스트레이터가 |
| `onNavigate(url,title)` | `POST /api/browser/activity {kind:visit,url,title}` | **항상** — 개인 저널 |
| `onSearch(query)` (주소창 검색) | `POST /api/browser/activity {kind:search,query,url}` | PII 게이트 내장 |
| "이 페이지 기여" 버튼 | `POST /api/browser/ingest {url, html:<DOM>}` | **옵트인** — 공유 레인 |
| 탭 닫기 | (세션 close) | |
| 체류 종료 | `POST /api/browser/activity {kind:dwell,url,dwell_s}` | 관심사 가중 |

DOM 텍스트는 웹뷰의 `document.documentElement.outerHTML`을 JS 인젝션으로 얻는다
(Tauri: `webview.eval` / Electron: `webContents.executeJavaScript`).

## 3. 엔진-측 로직 (이미 완성 — 셸은 이것만 물면 됨)

- `packages/atanor_browser/browser_session.py` — **BrowserSession**: open_tab/
  navigate/search/back/close_tab/activate, 탭별 히스토리, 활성탭. navigate()가
  2레인 라우팅을 강제(개인=항상, 공유=opt-in+DOM). 5 테스트.
- `packages/atanor_browser/activity_journal.py` — 개인 저널(방문·검색·체류→
  에피소드 타임라인+관심사, 로컬, PII 게이트). 6 테스트.
- `packages/atanor_browser/browser_ingest.py` — 공유 인제스트(호스트=voice 합의+
  판정 게이트, 검증스토어 비기입). 12 테스트.
- `packages/atanor_browser/page_distiller.py` — DOM→앵커 게이트 후보 트리플. 5 테스트.
- 라우트: `apps/api/app/routers/browser.py` (activity, ingest, promotable,
  promote-preview, forget, activity/recall|interests|status).

## 4. 크롬형 UI 구성 (셸이 그릴 것)

- 상단: 주소창(검색 겸용) + 탭바 + 뒤로/앞으로/새로고침 + "🧠 브레인에 기여" 토글.
- 사이드(선택): 오늘 방문한 관심사(`GET /api/browser/activity/interests`) + "무엇을
  언제 봤지" 검색(`.../recall?q=`) — 브라우저가 개인 브레인을 되비추는 창.
- 개인정보 컨트롤: "이 도메인 잊기" 버튼 → `POST /api/browser/forget {subject}`.

## 5. 완료 판정 (Definition of Done)

1. 실사이트(네이버/유튜브/위키) 렌더링 (네이티브 웹뷰로 — iframe 아님)
2. 방문 시 `GET /api/browser/activity/status`의 events 증가
3. 관심사 사이드가 체류 가중 도메인 표시
4. "브레인에 기여" 토글 ON 페이지만 `/promote-preview`에 후보 등장, OFF는 개인만
5. "이 도메인 잊기" → recall에서 사라짐(잊힐 권리)
6. 검색어에 개인정보 넣으면 저널에 안 남음(PII 게이트)

## 6. 함정 선답

- **iframe으로 시작하지 마라** — 실사이트 대부분 막힌다. 처음부터 네이티브 웹뷰.
- **셸에 세션 상태 두지 마라** — 활성탭·히스토리는 BrowserSession이 정본(디바이스
  연속성·연속 자의식과 한 곳에서 이어지려면).
- **모든 페이지를 공유 그래프에 넣지 마라** — 기본 비공개. 기여는 명시적 옵트인.
- **DOM 전체를 저널에 저장하지 마라** — 저널은 행위(방문·검색)만. 내용은 인제스트
  레인이 게이트를 거쳐 처리하고, 검증스토어엔 승격 게이트만 쓴다.
