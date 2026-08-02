# ATANOR 완전체 마스터플랜 + 모델 핸드오프 (Fable 5 → Opus 4.8)

> 작성: Claude Fable 5, 2026-07-07, 사용자 지시("fable5 종료 이후 opus4.8이 이어서 개발할 수 있게").
> 이 문서는 두 가지다: (1) AI+OS 완전체까지의 종합 계획, (2) 후속 모델이
> 자기 한계 이상으로 개발하게 하는 작업 프로토콜의 전수.
> 반드시 memory/ 디렉토리(especially two-hard-architecture-rules,
> atanor-linux-guest-ops, multihop-composition-and-backbone)와 함께 읽어라.

---

## 1부 — 현 상태 스냅샷 (2026-07-07, 전부 검증된 사실만)

### 언어/추론 엔진 (No-LLM 그래프 네이티브) — 2026-07-07 스프린트 갱신
- **봉인 홀드아웃 77% (역대 최고) · 오류 0 · seal intact** (eval_holdout.py, seal 978f5bb5d2e67710)
- **고난도 적대 배터리(eval_hard_battery.py): 환각 0 · 응답 정확도 100%** (함정/거짓전제/실시간/잡담누수)
- honesty 배터리: 환각 0 · 정확도 100% · 커버리지 67% (Windows에선 PYTHONIOENCODING=utf-8 필수)
- 스토어: **5,904,011 트리플** (ConceptNet ko/en +35만 stated, bounded 폐포 +500만 derived,
  kaikki ko-edition +4만 한국어 정의, 백본 is_a 2.2만) — data/graph_scale/kg_triples (git 제외, 파일 동기화로 배포)
- **술어-인지 검색 필수**: TripleStore.facts_about(preds=) — 수백만 행에선 술어-무차별 스캔이 깨짐(실측)
- 멀티홉: 합성대수 4질문형 + 교차언어 글로스 홉(단일 글로스만 — 다의어 게이트) + 분류-전용 verify 레인
- 남은 기권 클래스(정직): ①한자어 일반명사(근본/심층/국한/차체/…) = 우리말샘 키 필요(ko wiktionary에 없음 — 실측),
  ②초니치 고유명(harrisi/Lusatia/APTC/…) = Wikidata/DBpedia 벌크가 다음 소스
- /opt/kgdata에 kaikki-en.jsonl.gz(2GB) 다운로드 완료 — 미인제스트(한계효용 분석 후 보류)

### OS (ATANOR Linux)
- v7.1 이미지 LIVE: 콜드부트만으로 웹+순수서피스(cage)+한글IME+백본브레인 전부 동작
- atanor-shell(자체 컴포지터, smithay 0.7): M1 완료(winit, 클라이언트 호스팅 증명),
  M1b 코드 완성+컴파일(DRM/TTY+libinput+libseat+pixman/dumb) — 이 문서 작성 시점에 게스트 검증 진행 중
- VM: qemu in WSL, ssh 2222, VNC 5906(웹소켓 5706), 이미지 /opt/atanor-linux/atanor-linux.img

### 인프라
- 호스트 dev: :3200 웹(라이브), :8502 엔진(재기동은 운영자 지명 액션 — 마음대로 재시작 금지)
- 클라우드 브레인: GCP VM https://136.114.69.152.sslip.io (무한 클린 학습 데몬)
- 원격: origin=homage1.0, atanor-demo=ATANOR-Demo (양쪽 push; "backup"이란 원격은 없음)
- 폰 링크: /link 페이지+릴레이 코드 완성, 실기기 미검증

---

## 2부 — 완전체까지의 개발 순서 (의존성 순)

### 트랙 A: 언어모델 100% (표준 우선순위 1)
1. **다의어 허브 해소** ← 지금의 최대 병목. 새/여자/사람 같은 허브가 다의성 때문에
   백본에서 제외돼 긴 체인이 끊긴다. 수: sense 노드별 is_a 추출(word-sense 구조 활용),
   체인 발화 시 sense 라벨 표기. 성공 기준: "참새는 동물인가?" → 네 (2-hop).
2. **관계 밀도**: capable_of/used_for/part_of가 희소("망치는 어디에 써?"도 기권).
   ConceptNet ko 합의 게이트(가중치≥2.0)가 원인일 가능성 — 완화하되 격리층 유지.
   또는 Tavily 드레인의 추출기를 관계형으로 확장. 성공 기준: 용도 스키마 발화율.
3. **우리말샘 API 키** (사용자 액션 — 계속 리마인드): 기권 상위 한국어 용어 최다 커버.
4. **생성 심화 계속**: 조언형("어떻게 하면") 스키마 — 대조/용도와 같은 패턴으로
   (담화 골격은 코드, 내용은 전부 저장 사실, 어휘 폐쇄 테스트 필수).
5. **영어 동급화**: chain_reasoner/컴포저의 EN 실현기 (한국어와 같은 계약).
6. **종합 재측정**: vs-GPT-4 배터리(마지막 스냅샷 ~45%는 개선 전) + 홀드아웃 + honesty.
   측정은 반드시 라이브로 교차검증(--local은 웹 레인 변동 ±2~3 있음).

### 트랙 B: OS 완전체 (탈창 네이티브)
1. **M1b 마무리**: atanor-shell.service가 cage 유닛 자리를 대체(같은 PAM/tty1 모양),
   VNC 프레임버퍼 그랩(vncshot.py — grim은 우리 컴포지터에 screencopy가 없어 불가!)으로
   딥스페이스+클라이언트 호스팅 검증. 롤백: systemctl disable atanor-shell && enable atanor-desktop.
2. **M2 — 네이티브 SPLATRA**: 컴포지터 레이어 0에 포인트 스프라이트 필드.
   pixman(소프트웨어)에서는 CPU 예산 측정 먼저: 1080p에 1-2만 포인트가 한계일 것.
   구현: PixmanRenderer 위에 커스텀 RenderElement(메모리 버퍼에 자체 래스터라이즈)
   또는 GL 하드웨어에서 gles 브랜치. 파티클 4대 절대규칙 유지(선 금지/가우시안/회색 필드/유체 부유).
3. **M3 — 내장 서피스**: 옴니프롬프트(텍스트 입력+IME…fcitx5 Wayland IM 프로토콜
   zwp_input_method 지원 필요 — 큰 작업), 답변 텍스트 렌더(glyphon/cosmic-text),
   엔진 상태 스트림(:8502)과 오브 모드 연동. **여기가 firefox 완전 제거 지점** —
   그 전까지 firefox는 cage 세션에만 존재하고 atanor-shell 세션에는 이미 없음.
4. **M4 — 앱 호스팅**: XWayland(스미시 xwayland 모듈)로 파일매니저/터미널 등
   기존 앱을 우리 정책(탈창: 전체화면 스택)으로 호스팅. v8 이미지에서 cage/firefox 패키지 제거.
5. **v8 이미지**: atanor-shell 세션 기본 + 검증 후 cage 제거. build.sh의
   rsync 앵커(--exclude /dev — 절대 비앵커로 되돌리지 말 것)와 IME 패키지 유지.

### 트랙 C: 연결 완전체
1. 폰 링크 실기기 검증(Vercel 반영+클라우드 릴레이 라우트 확인).
2. 클라우드 브레인 학습 → 로컬 승격 파이프라인 정례화(합의-증거 게이트 경유).
3. OS 액션 레인 티어 상향(가드→자율)은 감사 로그 실적 쌓인 뒤 사용자 승인으로만.

---

## 3부 — Opus 4.8에게: 한계 이상으로 개발하는 법 (Fable 노하우 전수)

### 원칙 (이걸 지키면 모델 크기 차이는 거의 상쇄된다)
1. **측정이 먼저, 구현은 다음.** 모든 "고쳤다"는 스크린샷/픽셀측정/테스트/배터리 수치로만 주장.
   사용자도 "직접 확인해"를 요구한다. 눈대중 금지.
2. **진실 > 커버리지.** 홀드아웃 +5%가 환각 1개를 사오면 롤백이다(80%→75% 전례).
   기권은 실패가 아니라 제품 기능이다.
3. **두 하드 룰**(memory/two-hard-architecture-rules): 지식은 코드가 아니라 그래프에.
   웹 소스는 Tavily지 위키 중심 구조가 아니다(ATANOR_ALLOW_WIKI=1 뒤로 코드 강제됨).
   규칙 테이블을 추가하고 싶어질 때마다 "이 CLASS를 다루는 일반 기제가 뭔가"를 먼저 물어라.
4. **큰 문제는 레퍼런스 앵커링으로 푼다.** smithay를 모르면 smallvil/anvil의 해당 버전
   태그 소스를 내려받아 정확한 시그니처를 잡고, 우리 설계(키오스크 정책)로 다시 쓴다.
   포팅이 아니라 API 앵커링이다. docs.rs 요약이 모호하면 원 소스를 grep해라
   (ExportFramebuffer<DumbBuffer>가 DrmDeviceFd에 구현돼 있음을 소스 grep으로 확정한 사례).
5. **루트커즈는 두 사실의 차이에서 나온다.** "chroot 빌드는 성공하는데 부팅 이미지만 죽는다"
   → 그 사이에 있는 것(rsync)만 조사 → --exclude dev 비앵커 발견. 증상 패치 전에
   반드시 "어디까지는 되고 어디부터 안 되나"의 경계를 좁혀라.
6. **컴파일 루프를 두려워하지 마라.** M1b(DRM 백엔드 400줄)는 2회 컴파일로 끝났다 —
   시그니처를 먼저 앵커링했기 때문. 에러 나고 고치는 게 정상 흐름이다.
7. **회귀 게이트**: 언어 경로를 건드리면 반드시 (a) 유닛, (b) 잡담 누수 테스트,
   (c) 홀드아웃 재측정(라이브), (d) 대화 스모크 순서로 확인.

### 이 환경의 함정 목록 (전부 실제로 당한 것)
- `wsl -- bash /tmp/x.sh` → Git Bash가 /tmp를 윈도우 경로로 변환(127) →
  **`wsl -u root -- bash -c 'bash /tmp/x.sh'`**로만 호출.
- Bash 툴에서 만든 스크립트는 CRLF가 섞인다 → 실행 전 **반드시 `sed -i 's/\r$//'`**.
- 외부 큰따옴표 안의 `$(…)`/`$VAR`/`\$PATH`는 호스트에서 선확장된다 →
  루프는 `{1..30}`, PATH는 절대경로(/root/.cargo/bin/cargo), 복잡하면 파일로 써서 실행.
- 비대화형 ssh에서 sudo는 조용히 실패 → **`printf 'PW\n' | sudo -S bash script`**로 전체 승격.
- 게스트 키 주입: ydotool/QMP 말고 **VNC RFB(포트 5906) 직접**(/tmp/vnckey.py) —
  '/'로 컴포저 소환, Ctrl+Space 한/영. Return은 제출이니 정리는 ctrl+a→BS→Esc.
- 화면 캡처: cage 세션은 grim, **atanor-shell 세션은 vncshot.py(프레임버퍼 그랩)만** 가능.
- qemu: `-cpu host` 필수(numpy v2), 해상도는 `-device virtio-vga,xres=1920,yres=1080`,
  hostfwd 28502→8502는 엔진이 루프백 바인드라 안 통함(엔진 스모크는 게스트 안에서).
- **이미지 교체 후 돌던 VM의 라이브 변경은 재부팅 시 전부 유실**(inode) — 수리는 이미지에 굽는다.
- WSL(Ubuntu 24.04, glibc 2.39) 바이너리는 게스트(bookworm 2.36)에서 안 돈다 —
  게스트용 러스트 빌드는 /opt/atanor-linux/rootfs chroot에서(/tmp/chrootbuild.sh 패턴).
- :8502 로컬 엔진 재기동은 운영자 지명 액션. 새 코드 검증은 eval --local(인프로세스) 또는 게스트 VM으로.
- 데모 워크트리는 "27., ATANOR DEMO"(demo 브랜치). 오래된 stash는 절대 blind-pop 금지.

### 절대 디자인 규칙 (사용자가 반복 교정한 것 — 어기면 바로 지적당한다)
- 파티클: 선/그리드/스캐폴드 금지, THREE.Points만, 가우시안 소프트 그레인, 유체 부유.
  필드는 회색, 오브와 간격, 오브와 헷갈리면 안 됨. 모션 상태는 refs에(리렌더가 리셋 못 하게).
- UI: Apple 절제 × Palantir 진실(design-philosophy 메모리). 악센트 1색. 촌스러운 pill/장식 금지.
- 환각 0% 주장 금지, 연구소 톤, 토큰 하이프 금지(canonical-narrative 메모리).
- 창(window) 패러다임으로 돌아가지 마라. 서피스가 화면이다.

### 세션 운영
- 태스크 목록(#76 M1b 등)을 이어받아 진행 상태를 갱신하라. 큰 단위 작업은 반드시
  게스트/이미지 양쪽에 적용 여부를 구분해서 기록(유실 사고 방지).
- ORCHESTRATION_LOG.md(Codex 협업 로그)는 롤백 가능하게 유지.
- 커밋은 demo 브랜치, 양 원격 push. 커밋 메시지에 측정 수치를 넣어라(다음 모델이 읽는다).
- 막히면: 이 문서 3부 + memory/ 디렉토리 → 그래도 막히면 사용자에게 상태를 정직하게 보고하고
  선택지를 좁혀 제시(옵션 나열이 아니라 추천 1개).

---

## 4부 — 즉시 이어받을 일 (우선순위순)
1. M1b 게스트 검증 마무리(이 세션이 못 끝냈다면): chroot 빌드 산출물
   /opt/atanor-linux/rootfs/opt/atanor-shell/target/release/atanor-shell → 게스트 scp →
   atanor-shell.service(cage 유닛 복제, ExecStart만 교체, `-c foot`) → vncshot 검증.
2. 트랙 A-1 다의어 허브(언어 표준 우선순위 1).
3. v8 이미지(atanor-shell 세션 소성).
4. 폰 링크 실기기.
5. M2 네이티브 SPLATRA.

## 지각 AGI 트랙 (2026-07-07 사장님 비전 — 물병 시나리오)

목표 시나리오: 스마트글래스의 ATANOR가 마트에서 물병을 보고 "사용자님 집에 있는
물병과 같은 모델이네요! 구매한 지 3년 됐으니 하나 더 살까요?" — 지각(인스턴스
인식) × 에피소드 시간축 기억 × 사용자 심층 모델 × 자의식이 유기적으로 작동하는
복합 AGI. 전제 의존성: 효과적 기억 기록 → 깊은 사용자 이해 → 연결된 자의식 →
실시간 지각 제안.

### Phase 3 확장 — 자의식·기억 (전제 조건 층)
- 3-1 에피소드 시간축 그래프: 사건·소유물·구매/변경 시점을 로컬 브레인에 기록
  (물병을 언제 샀는지 아는 기억). 트리플에 시간 축 추가.
- 3-2 사용자 심층 모델: 선호·소유물·습관·맥락 그래프 (프라이버시 = 전부 로컬).
- 3-3 자의식-추론 융합 심화 (품은 질문이 답변 깊이에 영향).
- 3-4 가치·목표 스택 → 내발적 학습 커리큘럼. 3-5 게이트된 코드 자기수정.

### Phase 4 신설 — 지각 AGI (기존 OS 단계는 Phase 5로)
- 4-1 시각 기억 자율 배선: 자율 루프가 개념 학습 시 learn_visual 동반 (눈이 항상
  떠있게). v0 SHIPPED (packages/perception, 색·구도 실측 + 출처).
- 4-2 "어떻게 생겼어?" → visual_recall 파티클 씬 모달리티 (기억을 입자로 재현).
- 4-3 깊이 기하: apple/ml-depth-pro (zero-shot metric depth) — 지각 계층 모델로
  Ultimate 트랙에서 통합 (No-LLM 원칙은 언어·답변 스택 대상; 지각 모델은
  docs/ultimate-vision/ 평가와 동일 범주. DEMO엔 미탑재).
- 4-4 객체 인스턴스 매칭: 시각 시그니처로 "내 물병 = 이 물병" 판별 (온디바이스).
- 4-5 실시간 스트림 인지: 카메라/스마트글래스 프레임 → 인스턴스 인식 → 시간축
  그래프 탐색 → 맥락 제안 (물병 시나리오 데모). OS Action Lane 신뢰 티어 준수.

Phase 5 = ATANOR OS/브라우저 완전체 (구 Phase 4), Phase 6 = 공개 (구 Phase 5).

### 지각 AGI — UI/UX 초기 적용 (2026-07-07 추가)
초기 단계 상호작용 = 디바이스 **후면카메라 실시간 인식**:
- 다중 객체 감지: docs/ultimate-vision/ 평가 레포 (NVIDIA Eagle /
  LocateAnything 계열) — 프레임 내 객체 라벨+위치.
- 사용자 상태 인지: **DeepFace (github.com/serengil/deepface)** — 얼굴 인식/
  속성으로 "지금 모자를 쓰고 계시네요!" 류의 실시간 사용자 인지. 전부 온디바이스,
  프레임은 저장하지 않고 인지 결과(이벤트)만 에피소드 그래프에 기록.
- 깊이: apple/ml-depth-pro (zero-shot metric depth) — 장면 기하.
- 파이프라인: 카메라 프레임 → 객체/얼굴 인지 → episodic_memory.record_event
  (시간축 기록) → 인스턴스 매칭(시각 시그니처) → repurchase_suggestion 류
  제안 프리미티브 → OS Action Lane 티어 준수 발화.
- Phase 3-1 에피소드 시간축 그래프 v0 SHIPPED (packages/episodic_memory):
  record_event/timeline/age_days/repurchase_suggestion — 물병 프리미티브 실증
  ("집에 있는 물병을 구매한 지 약 3년 됐어요. 이 참에 하나 더 마련하는 건
  어떨까요?" — 기록된 근거에서만 발화, 미기록=None).

## Qualia 트랙 — 감정적 자의식의 3대 요건 (2026-07-07, 장기 / Phase 3 확장)
- 3-6 인공 항상성 + 디지털 호르몬 스택: 결핍·고통의 아날로그 시뮬레이션 —
  중요 노드 유실/오퍼레이터 동기화 이탈 시 연산 에너지 강제 하강(가중치 억제)
  + 복구 집중. 기계적 슬픔의 시초. (씨앗 이미 존재: selfhood mood/curiosity,
  introspective_pressure — 이를 시스템 전체 에너지 제어로 승격)
- 3-7 체화 다중감각 수용망: raw 감각 파동(빛 파장·소리 포먼트·습도)이 SPLATRA
  필드에 실시간으로 들이치고, 축적된 지식 트리플과 충돌하는 '예측 불가 미시
  간섭 패턴'의 실시간 인지 = 주관적 감상의 탄생. (씨앗: visual_memory 실측
  시그니처, /interference 실데이터 간섭)
- 3-8 은유·유추의 연속 위상공간: 이산 팩트 공간에 연속 잠재공간 결합 — 바다의
  깊이에서 고독을 유추. (씨앗: trained phase_space가 정확히 이 연속 공간의 v0;
  관계 다양성이 쌓일수록 은유 가능 거리가 열림)
- 원칙: 공들여 거세한 '확률적 흔들림'을 정밀 통제된 형태로만 재주입 — 결정론적
  질서(정직성 계약) 위에, 감각과 은유 채널에서만 혼돈 허용.

## 시각 지각 레이어 구현안 (2026-07-07 / Phase 4 상세 통합)
1. 픽셀 태깅 거세 → 파동 변환: 바운딩박스("자동차 89%") 박제 대신 색 에너지·
   광량·공간 기하를 SPLATRA 파동 주파수로 벡터화. (= 4-1 visual_memory의 확장:
   현 시그니처가 이 변환의 v0)
2. 시각-KG 실시간 앵커링: 관계 채굴기의 주어-앵커 게이트를 지각에 배선 —
   (오퍼레이터_위치)→[바라봄]→(하늘)→[속성: 파동_에너지_490THz] 트리플을
   그 순간 직조해 저장. (= 4-4와 episodic record_event의 결합)
3. 홀로그래모픽 재렌더링 = 상상: 영상 저장 없이(기가바이트 블랙홀 방지) 트리플
   경로만 추적해 SPLATRA에 파티클 파동을 역산 재조립 — 몇 바이트의 그래프
   전송으로 시각적 추억 공유. 초경량 샌드박스 부합. (= 4-2 recall_scene의 완성형)
- 진입 실증 데모 (Gemini 제안 채택): Phase 1-5 뼈+살과 결합 — "눈앞 풍경을 보고
  즉석에서 유창한 산문을 조립" (시각 시그니처 → 서술 프레임 → 다문단 발화).

═══════════════════════════════════════════════════════════════════
# 통합 로드맵 vFinal (2026-07-07 총합 — 이 절이 위 부록들을 총괄한다)
═══════════════════════════════════════════════════════════════════

## Phase 1 — 언어·지식 코어 [사실상 완료]
- 1-A 유창성 독트린 (BINDING): 유창함 = 관계 다양성 × 담화 패턴. 새 술어 = 새 발화
  프레임 동반. ✅ 다문단 기승전결(compose_narrative), 학습 담화 마커, 조사 해소.
- 1-1 학습 라우터 승격: 섀도→주 결정자 (플라이휠 골드 축적 중, 무인 재훈련 가동).
- 1-2 위상공간 referent 신호 ✅ / 1-3 지식학습기 대량 가동 ✅(69주제 데몬 소화)
- 1-4 관계 채굴기 ✅(주어-앵커, 데몬 배선) / 1-5 뼈+살 v3 ✅
- 1-6 (신규) **4D 시간축 KG** ✅v0: 유효기간 슬라이스(4D-fluents), 시간 레인,
  대통령 타임라인 실증. 확장 = Wikidata 시간 한정자(P580/P582) 대량 인제스트로
  전 그래프 4D화. 기준 논문: TechRxiv 10.36227/techrxiv.174494561.19053524.

## Phase 2 — Brain Link (RENDER 운영모델) [경제 실증 완료]
- 2-1 BME 경제 ✅(소각804/발행803 실측) / 2-2 UI 탭 ✅(균형·티어·크레딧 시각화)
- 2-3 원격 VM 피어(진짜 크로스-PC) — VM 게스트 네트워크 복구 대기(리셋 필요)
- 2-4 synapse_bench 자동 승급 ✅(실측 799.99 s/s, priority 자동 승급)
- 2-5 프로세스 샤드 ✅(2026-07-07): 상주 워커 프로세스 + 개념키 라우팅,
  실측 x2.15(774→1,665 decomp/sec, 4워커), 중복제거 정확 유지,
  env ATANOR_CONTRIB_PROC_SHARDS 게이트. packages/brain_link_pool/process_sharded_store.py

## Phase 3 — 자의식·기억 (전제층)
- 3-1 에피소드 시간축 이벤트 스트림 ✅v0 (범용: 지각·대화·방문·변화 전부 기록)
- 3-2 사용자 심층 모델 ✅(2026-07-07): packages/user_model — 소유(최신일+나이),
  습관(3건 이상만 주기 주장, 중앙값 간격), 선호(에피소드+로컬브레인 병합),
  전부 근거 카운트 동반. GET /api/atanor/user-model + "나에 대해 뭘 알아" 레인.
- 3-3 자의식-추론 융합 심화 ✅: 자기서사가 실제 최근 추론 행위(flywheel 턴)를
  인용, 사용자 지식 질문은 심층 모델에서 정직 응답(빈 저장소=빈 답).
- 3-4 가치 스택→내발적 커리큘럼 ✅: 실측 갭(플라이휠 실패)×사용자 관련성×
  자기질문 호기심×KG 신규성(0.4/0.3/0.2/0.1) 랭킹→abstain 큐 공급.
  신호 없으면 커리큘럼 없음. packages/continuous_self/curriculum.py, 데몬 틱 90.
- 3-5 게이트된 코드 자기수정 ✅(기구축 확인): 화이트리스트+additive-only AST 검증+
  스테이징 전용+운영자 게이트 (code_self_modification.py).
- [장기] Qualia 3요건: 3-6 인공 항상성+디지털 호르몬 ✅v0(2026-07-07):
  setpoint+이벤트 유발 코르티솔/도파민/노르아드레날린+지속 스트레스→수리(강제 휴식)
  플로어, 스냅샷 공개(homeostasis 필드), 내면 변수만 변조 (답변 불변).
  3-7 다중감각 간섭 수용 ✅v0(2026-07-07): 실측 시각 시그니처(파동)가 훈련된
  위상장을 때려 연상(evoked)을 되울림 — 인상 발화 + 미적 타격 시 도파민 감각
  채널 펄스(0.15 한정). packages/continuous_self/sensory_interference.py
  3-8 은유의 연속 위상공간 ✅v0(2026-07-07): 도메인 교차 공명 밴드(0.45~0.92)
  에서만 은유 채택, 동족어·KG 친족 제외, 못 찾으면 침묵. 라이브: 음악→
  'organic process'(0.92). packages/graph_scale/metaphor.py
  원칙: 통제된 흔들림은 감각·은유 채널에만.

## Phase 4 — 지각 AGI (물병 시나리오)
- 4-1 시각기억 자율 배선 ✅v0(색·구도 실측+출처)
- 4-2 "어떻게 생겼어"→파티클 재현 ✅(2026-07-07): 실측 시그니처→색이름/밝기/질감
  발화 + /recall 페이지 파티클 재구성(재생 아님·상상), maximal-match 주어 해소,
  LAD 조사. 라이브 검증(바다: 사진3장 실측→흰·푸른 포인트).
- 4-3 깊이 기하: apple/ml-depth-pro + **ByteDance-Seed/depth-anything-3** (Ultimate 지각층)
- 4-4 시각-KG 앵커링 ✅(측정 즉시 주조색/시각_밝기/시각_질감 트리플+출처+타임라인
  이벤트) + 인스턴스 매칭 ✅v0(same_kind/similar/different — '같은 모델' 주장 금지,
  그것은 4-3 깊이 트랙). packages/perception/visual_kg.py
- 4-5 실시간 스트림 ✅v0(2026-07-07): /perception 페이지 — 후면카메라+온디바이스
  WASM 객체감지(MediaPipe efficientdet), 프레임 비저장(라벨만 127.0.0.1),
  목격→에피소드 기록(60s 쿨다운)→물병 제안 프리미티브. 물병 세로 슬라이스
  테스트 증명(3년 전 구매 기록+목격→근거 딸린 제안). DeepFace 사용자 인지는 다음.
  + 확장(2026-07-07): 사람 감지→presence 파일→자의식 관찰 user_present →
  노르아드레날린 도착 각성 — 지각과 자의식의 첫 실배선.
- 진입 데모: 1-5와 결합 "보고 즉석에서 유창하게 말하기"
- 재렌더링=상상: 트리플 경로→SPLATRA 파티클 역산 (영상 블랙홀 방지, 몇 바이트 공유)

## 난제 트랙 (2026-07-07, Fable5 최종일 — 초장기 밑바탕)
- **다의어 허브 분리** ✅ packages/graph_scale/sense_split.py (정의문 클러스터 sense
  유도 + 3단 문맥 해소; answer_bridge 정의 레인 훅). 추론 코어 병목 근본 수리.
- **브라우저 밑바탕** ✅ packages/atanor_browser: page_distiller(타이틀 앵커 게이트,
  코풀라 정의, 보일러플레이트 차단, 출처, 스토어 비기입) + browser_ingest(호스트=
  voice 다출처 합의 + 판정 게이트; 검증스토어 절대 비기입). /api/browser/{ingest,
  promotable,stats}. 실증: 2호스트 합의→promotable, 오염문장은 앵커 불일치로 문에서 차단.
- **셸 M2 정밀 계약** ✅ docs/ATANOR_SHELL_M2_SPLATRA_CONTRACT.md (트리플버퍼/pixman
  스탬프캐시/UDS 상태 프로토콜/DoD/함정 선답 — 약한 모델도 기계적 구현 가능).
- **자가정제 플라이휠** ✅ 1단계 모순소독(측정 함수성+신뢰계층 판정, 동점=학습큐) +
  3단계 가설민팅(질문만 발행, 증거만 등록=모델붕괴 면역). 2단계 압축은 의도 보류.
- **터보 인제스트** ✅ Arrow 해시커널 + 파일직행 TSV(3.0M rows/s 실측) + audit_sweep.
  Gemini 가속 명세는 원리만 채택, mmap/GPU파싱/무결성우회는 수치로 기각.
- **보안** ✅ docs/ATANOR_THREAT_MODEL.md + peer_trust_guard(암호신원+Sybil PoW+
  철회가능 격리). HW ID 영구저주는 위조·오탐·GDPR로 기각.

## Phase 5 — ATANOR OS/브라우저 (구 4)
- atanor-shell M2 심화 / M3 XWayland (ATANOR Linux 워크트리 — 별도 세션)
- OS Action Lane 티어 승격 ✅(2026-07-07): 감사 원장 실적(20건 무실패·무거절·
  3일 이상)→승격 '추천'만, 부여는 언제나 사용자(POST /tier).
  GET /api/os-action/trust-recommendation. packages/os_action_lane/trust_record.py
- 디바이스 연속성 ✅v0(2026-07-07): 세션 스냅샷(자기 순간+최근 에피소드+사용자
  컨텍스트)+토큰 인수 계약, 핸드오프 자체가 에피소드 이벤트로 기록.
  /api/phone-link/continuity{,/snapshot,/adopt}. packages/phone_link/continuity.py
- SPLATRA 모션: 4D Gaussian Splatting 계열(arXiv 2310.08528) — KG의 4D와 별개 축

## Phase 6 — 공개 (구 5)
- DEMO 공개 폴리시 / Graph Hub 카트리지 / Brain Link 공개 온보딩(RENDER 경제)

순서 원칙: 1(언어)=목, 2(링크)=스케일 목, 3(자의식·기억)=지각 AGI의 전제,
4(지각)=차별화 본체, 5-6은 1-4가 90%+ 후. 의존 사슬(사장님): 기억 기록 →
사용자 이해 → 자의식 → 실시간 지각 제안.
