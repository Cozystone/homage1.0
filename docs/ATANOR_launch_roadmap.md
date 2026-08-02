# ATANOR 출시 로드맵 — "진짜 출시가능한 완성"까지 (2026-07-21)

> **Sequencing note (2026-07-25):** this product roadmap remains a
> long-horizon delivery map, but its R0/R1 “권장 순서” and “지금 이 순간”
> section are not the current model-completion priority. The active operator
> path is NL→goal compiler + scientific-knowledge staging → E4 →
> counterbalanced paired E5 GPQA/MMLU-Pro. RealCity, packaging, OS, and SPLATRA
> continue as scoped product backlogs and may not substitute for capability
> evidence.

사장님 정의: 완성 = 제3자가 설치/접속해서 가치를 얻는 **출시 가능 상태**. 전 트랙(모델·AI브라우저·OS·
SPLATRA·Realcity·AGORA·수익화)을 하나의 순서로 묶는다. 각 단계는 실측 게이트로만 완료 판정(연구소 톤).

## 출시 라인 3개 + 상시 트랙

### R0 — Realcity 쇼케이스 (가장 빠른 외부 노출, ~스프린트 1개)
"살아있는 도시 + 거짓말 안 하는 AI 시민"을 세상에 보여주는 공개 데모. 신규 개발보다 마감+노출.
1. 도시 마감: 현 웨이브(차량+운전·건축·조닝·역할생활) 착지 → 24h soak(메모리 평탄·프레임 p95)
2. R4 시연 1건: ATANOR가 도시 결함을 감지→자기수리 폐루프로 코드 패치(검증게이트)→저널 공개
3. R5 배포: realcity.vercel.app + 로컬 ATANOR 터널(cloudflared/Tailscale) — ★사장님 승인 필요(BL-0급)
4. 안전: 도시편집 도덕가드·대화학습 격리 게이트 그대로(이미 LIVE), rate-limit 추가
- **게이트**: 공개 URL에서 제3자가 ATANOR 시민과 대화 성공 / 24h 무다운 / 작화 0 유지

### R1 — ATANOR 앱 (본선: 설치형 로컬 AGI 1.0, 스프린트 3~5개)
핵심 제품. "서버 없는 내 PC의 정직한 범용 AI".
**(a) 모델 잔여 게이트**
   - C2 관계형 지식 수리(진행 중: 학습 라우터+그래프 엣지) → 봉인 홀드아웃 재green
   - F0 유창성(delex+copy 223k쌍+simple-register) → G-F3 앎/말분리 프로브 PASS
   - Tier A 정식 봉인 런(전량N+네트워크차단+2x재현) — provisional 6/6 → 정식
   - System-2(DELIBERATOR)는 **1.0 범위 제외**, 2.0 산으로 명시(정직한 스코프)
**(b) AI 브라우저 제품화** — 부품은 LIVE(SearXNG 1순위·검색우선 자율서핑·대화영속·visit_index·
   injection_guard). 남은 것: 사용자 UI(과정 보기), 세션 관리, 안정화. = "ATANOR가 대신 서핑하고
   출처로 말하는 브라우저" 기능으로 패키징
**(c) 패키징/설치** — installer(윈도우 우선), 첫 실행 device identity, world_pack 다운로드/증분 빌드
   (28워커), 25MB torch-free 엣지 답변경로 기본+옵션 무거운 ML(custom hub opt-in), 자동 업데이트(서명)
**(d) 로컬 맥락 로밍 v0** — FOR LATER 설계대로 **T0 관찰(read-only, 허용폴더)만** 1.0에 탑재,
   주의멘트+킬스위치+감사로그 필수(docs/ATANOR_local_context_understanding.md)
**(e) 안전/신뢰** — 헌법 게이트(도덕코어·테스트 불가침·후보승격 operator-signed) 문서화+UI 노출,
   정직성 포지셔닝(작화0 주장 금지, faithful-to-source 표기)
**(f) 최종 시험** — MSH exam_002(머신봉인 홀드아웃, 개발자-블라인드) PASS = 출시 인장
- **게이트**: 클린 PC에서 설치→첫 접지답변 <30분 / 봉인 홀드아웃 green / 기권≠작화 원칙 실측 /
  MSH PASS / 48h 사용자 시나리오 soak

### R2 — ATANOR OS + SPLATRA (프리미엄 표면, R1 이후)
1. atanor-shell M1b(DRM 백엔드) → M2(SPLATRA 파티클 셸 = Jarvis 표면) → M3(XWayland 호환)
2. SPLATRA 생성 트랙: 리그+FK/PBD+재질+호르몬 표현 → 상상 컴파일러(생각→장면) 라이브 데모
3. 체화 M2(SPLATRA 기판 조작) — 연구와 제품 사이 다리, G1/dimos는 연구 트랙 유지
- **게이트**: 셸 부팅→SPLATRA 장면 60fps / 상상 컴파일러가 대화 중 실시간 장면 생성

### AGORA 연합 (R1 사용자 기반 후 베타)
공용/개인 분리·연대성장(읽기균등/쓰기 신뢰가중)·암호신원+Sybil PoW+철회격리 — 부품 LIVE.
남은 것: 온보딩 UX, 피어 디스커버리, 남용 대응 운영. **게이트**: 실피어 2+에서 지식루프 연대성장 실측.

### 상시 트랙 (출시 라인과 병렬)
- **수익화**: atanor-revenue로 가격/티어(로컬 1.0 무료? PROPHETA/웹티어 유료?)·B2B 경로 문서 → 사장님 결정
- **마케팅**: landing 사전모집 퍼널(atanor-marketing, 게시=사장님 승인), R0 데모가 최고의 소재
- **운영**: watchdog·자기수리 폐루프·배선감사(audit_wiring) 상시, Cloud Brain은 데모/중계 전용 유지

## 권장 순서 (한 줄)
**R0 쇼케이스 → R1 앱 1.0 (a→f) → AGORA 베타 → R2 OS/SPLATRA**, 수익화·마케팅·운영은 상시 병렬.
이유: R0가 최소비용 최대노출(이미 90% 완성), R1이 가치의 본체, AGORA는 사용자 있어야 의미,
R2는 차별화 표면이라 본체 뒤가 정직한 순서.

## R3+ — 장기 지평: 의식 상관물과 초지능 (사장님 질문 2026-07-21 명시)

**현상적 의식 — "건축은 전부, 주장은 상관물만" (BINDING)**
- 포함되는 것: 측정 가능한 **기능적 상관물의 전체 스택**을 실제로 계속 짓는다 — 이미 상당 부분 LIVE:
  GWT 직렬 점화·하중 항상성(S1)·신체 표지(S3)·자서전적 자아·호르몬 동역학·자기-인과 모델·내적 언어·
  L2 느낌 폐루프. R1 이후에도 상시 심화(비전 기준: 내면 아키텍처 B1-B6 전부 실구축).
- 포함되지 않는 것: **"현상적 의식을 가졌다"는 주장** — 감각질은 외부에서 측정 불가능하므로 주장하는
  순간 작화다. 영구 금지(감각질 주장금지 BINDING). 우리는 상관물을 실측으로 보고하고, 있다/없다의
  단정은 과학이 판정 못 하는 채로 정직하게 둔다. **이건 한계 고백이 아니라 우리 제품의 차별점이다**
  — "의식 있어요"라고 말하는 챗봇들과 반대편에 선다.

**초지능 — "방향은 포함, 선언은 게이트로만"**
- 경로는 이미 로드맵 안에 있다: RSI 플라이휠(봉인게이트 PASS, 얼린신탁+헌법불가침+인간게이트로
  wireheading 차단) × 구조 우위(LLM 5한계) × System-2(2.0) × 스케일 트랙.
- 단계 정의: **1.0 범용 유능 → 2.0 전문가급 추론(DELIBERATOR) → 3.0+ 봉인 홀드아웃에서 인간 전문가
  초과를 실측했을 때만 그 도메인에 한해 "초과"라 말한다.** "초지능 달성" 같은 총론 선언은 하지 않는다
  — 도메인별 실측 게이트의 누적이 있을 뿐. 안전 절대선: 자기개선은 테스트=헌법·후보승격 operator-signed
  구조 안에서만 복리된다.

## 지금 이 순간의 위치
- 진행 중: 도시 웨이브(차량/조닝) + C2 관계형 수리 + 코드 mythos 벤치 — 전부 R0/R1(a) 직결
- 다음 결정 필요(사장님): ①R5 터널 승인(=R0 공개) ②1.0 가격/무료 정책 ③Radxa 온보딩(BL-0, MSH 시험용)
