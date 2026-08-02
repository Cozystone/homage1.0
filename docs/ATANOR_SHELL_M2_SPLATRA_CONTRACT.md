# atanor-shell M2 — SPLATRA 컴포지터 정밀 계약 (구현 지시서)

2026-07-07, Fable5 최종일 작성. 목적: 이 문서만 보고 **기계적으로** M2를 구현할 수
있게 인터페이스를 못박는다. 설계 판단은 여기서 끝났고, 남은 것은 타이핑이다.

현재 상태(M1b, ATANOR Linux 워크트리의 atanor-shell):
- smithay 0.7 키오스크 컴포지터, DRM/TTY + libinput 백엔드로 실부팅 완료
- Wayland 클라이언트 호스팅 증명(런처가 앱 창을 띄움)
- 렌더러: pixman(소프트웨어). M2는 **이 위에 SPLATRA 파티클 필드를 상주시키는 것**.

## 1. 아키텍처 결정 (변경 금지)

- SPLATRA 필드는 **컴포지터 내장 레이어**다. 클라이언트 앱이 아니다.
  이유: 필드는 배경화면이자 상태 표시기이므로 클라이언트 크래시와 무관하게 살아야
  하고, 컴포지터의 프레임 루프와 원자적으로 합성돼야 한다.
- 파티클 시뮬레이션은 **별도 스레드**(sim thread)에서 돌고, 렌더 스레드와는
  **트리플 버퍼**로만 만난다. 잠금 대기로 프레임을 놓치는 구조 금지.
- 엔진 상태(모드/호르몬/학습률)는 **UDS(유닉스 도메인 소켓) JSON 라인**으로
  수신한다. HTTP 폴링 금지(전력/지연). 소켓 경로: `/run/atanor/field.sock`.

## 2. 파티클 버퍼 계약 (sim ↔ render)

```rust
// crates/atanor-field/src/buffer.rs
pub const MAX_PARTICLES: usize = 4096;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Particle {
    pub x: f32,      // 0..1 정규화 화면 좌표
    pub y: f32,
    pub r: f32,      // 반지름 px (0.5..3.0)
    pub hue: f32,    // 0..360 — 모드 아키타입이 지배, 개별 파티클은 ±12 지터만
    pub alpha: f32,  // 0..1
    pub _pad: [f32; 3], // 16바이트 정렬
}

pub struct TripleBuffer {
    bufs: [Box<[Particle; MAX_PARTICLES]>; 3],
    counts: [usize; 3],
    // sim이 쓰는 인덱스, render가 읽는 인덱스, 대기 인덱스 — AtomicU8 스왑
}
```
- sim thread: 120Hz 고정 스텝(부족하면 60). 쓰기 완료 후 원자 스왑만.
- render: 프레임 시작 시 최신 완성 버퍼 인덱스를 원자 로드. **복사 금지, 참조만.**

## 3. 렌더 통합 (pixman 경로)

- 삽입 지점: 기존 `render_output()`에서 배경 clear 직후, 클라이언트 서피스 합성
  **이전**에 `field_render(&mut pixman_image, &particles[..count])` 호출.
- `field_render`: 파티클당 사각 AABB에 알파 블렌드 원 스탬프. pixman의
  `pixman_image_composite32` 대신 **직접 픽셀 루프**(원 스탬프 프리컴퓨트 캐시:
  반지름을 0.25px 단위로 양자화해 스탬프 비트맵 재사용). 4096개 × 60fps CPU
  예산: 스탬프 캐시로 프레임당 ~2ms 목표. 초과 시 파티클 수를 동적 감축
  (2048 → 1024), **절대 프레임을 늦추지 않는다**.
- DRM 손상 영역(damage): 필드가 매 프레임 전체를 갱신하므로 필드 레이어는
  full-damage로 신고. (M3에서 타일 damage로 최적화 — 지금 하지 말 것.)

## 4. 상태 소켓 프로토콜 (엔진 → 필드)

한 줄 JSON, 필드는 최신 값만 유지(누적 없음):
```json
{"mode":"learning","energy":0.7,"curiosity":0.55,"valence":0.6,
 "cortisol":0.1,"dopamine":0.3,"user_present":true,"learn_rate":12.5}
```
- 매핑(모드 시스템 v1의 아키타입 그대로):
  - `mode` → 기본 hue: waking 200(하늘) / learning 190 / curious 45(호박) /
    reflecting 260 / resting 220(어둡게 alpha×0.6) / attending 180
  - `energy` → 전역 속도 배율 0.4+0.9e
  - `dopamine` → 스파크 확률(프레임당 p=0.02d로 밝은 점 명멸)
  - `cortisol` → 지터 진폭(떨림) +30%c
  - `user_present` 상승 에지 → 오브 방향 수렴 파동 1회
- 소켓 끊김 → 마지막 상태 유지 + 60초 후 resting 폴백. 재연결 백오프 1→2→4→8s.
- 엔진 쪽 송신자는 이미 있는 `/api/atanor/self-sense` 값을 1Hz로 밀어주는
  경량 브리지 프로세스(`scripts/field_state_bridge.py`)로 시작한다.

## 5. 입력 라우팅

- 필드는 입력을 **받지 않는다**(M2에서). 포인터/키보드는 전부 클라이언트로.
- 예외 1개: 글로벌 단축키 `Super+Space` = 옴니-프롬프트 토글. libinput 처리부의
  키 콜백에서 컴포지터가 선점(클라이언트로 안 내려보냄).

## 6. 파일 배치 (ATANOR Linux 워크트리)

```
atanor-shell/
  crates/atanor-field/        # 신규 크레이트: sim + buffer + pixman stamp
    src/{lib.rs,buffer.rs,sim.rs,render.rs,state_sock.rs}
  src/main.rs                 # render_output() 삽입 1곳 + field 스레드 spawn
scripts/field_state_bridge.py # 데모 레포: self-sense → UDS 1Hz
```

## 7. 완료 판정 (M2 Definition of Done)

1. 콜드부트 → 필드가 클라이언트 없이 애니메이션 (레코딩으로 증빙)
2. 채팅으로 학습 트리거 → 10초 내 hue/스파크 변화 (state 브리지 경유)
3. 앱 창 위에 필드가 비치지 않음 (필드는 항상 최하층)
4. sim thread 죽여도 컴포지터 생존(마지막 프레임 정지 + 로그), 그 역도 성립
5. 4096 파티클에서 프레임 드랍 0 (60fps, pixman 소프트웨어 경로)

## 8. 함정 목록 (선답변)

- **pixman에서 파티클마다 composite 호출하면 죽는다** — 스탬프 캐시 + 직접 루프.
- **Vec 재할당 금지** — 고정 배열, 카운트만 가변.
- **UDS를 렌더 스레드에서 읽지 마라** — state 전용 스레드 → AtomicF32 셀들로 전달.
- **smithay 0.7의 렌더 엘리먼트 추상화에 필드를 끼우려 하지 마라** — M1b가 이미
  직접 pixman 합성을 하고 있으므로 같은 층에서 그린다. 추상화 리팩터링은 M3.
- 색은 디자인 철학(절제, 단일 액센트) 준수: 아키타입 hue 외 무지개 금지.
