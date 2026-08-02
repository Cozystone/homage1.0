# ATANOR Shell — 자체 컴포지터 (2b) 설계

## 왜 (측정된 근거)
1단계(X11+openbox+firefox)에서 부딪힌 벽들이 전부 "남의 컴포지터/브라우저에게
부탁하는" 데서 왔다: firefox가 WM_CLASS를 고정해 규칙 매칭 불가, openbox의
keepBorder가 MOTIF를 무시, kiosk 전체화면이 패널을 덮음, 소프트렌더에서 웹
캔버스 파티클이 무거움. **컴포지터가 우리 것이면 이 문제들은 존재 자체가 없다** —
배경 레이어는 부탁하는 게 아니라 우리가 그린다.

## 무엇 (범위)
Rust + smithay(라이브러리 — 참고/의존, 포팅 아님) 기반 Wayland 컴포지터:

- **레이어 0 (우리가 직접 렌더)**: SPLATRA 파티클 필드 + 오브. wgpu 포인트
  스프라이트로 네이티브 렌더 — 브라우저·DOM 없음. 모드 변위(성운/응축/수동)는
  엔진 상태 스트림(127.0.0.1:8502 SSE/poll)에서 구동.
- **레이어 1**: 일반 Wayland/XWayland 앱 창들 — 윈도우식 이동/리사이즈/
  Alt-Tab, 타이틀바는 컴포지터가 그림(우리 토큰).
- **레이어 2**: 작업표시줄/옴니프롬프트/승인카드 — 컴포지터 내장 UI(우리가 그림).
- **입력**: libinput; Super=옴니프롬프트, 음성은 엔진 경유.

## 마일스톤
- M0 (이 스캐폴드): 크레이트 골격 + winit 백엔드로 창 하나 띄워 클리어컬러 렌더
  — WSLg에서 실행 가능, 빌드 파이프라인 검증.
- M1: smithay smallvil 수준 — Wayland 클라이언트(웨스턴 데모) 하나를 띄우고
  이동. TTY/DRM 백엔드로 ATANOR Linux에서 부팅.
- M2: wgpu 파티클 배경(포인트 10만+, 60fps 하드웨어 렌더) + 엔진 상태 연동.
- M3: 작업표시줄+옴니프롬프트 내장 UI, XWayland, 앱 아이콘.
- M4: cage/openbox/firefox 완전 대체 — atanor-desktop.service가 이걸 실행.

## 참고(참고만)
smithay/smallvil·anvil (MIT), niri, cosmic-comp — 구조 아이디어만, 코드 이식 없음.
