# Cloudflare 도메인 연결 런북 (GCP 무료 티어 트래픽 보호)

목적: Cloud Brain(GCP VM `136.114.69.152`) 앞에 Cloudflare 프록시를 두어
(1) 실제 도메인으로 접속, (2) 캐싱/프록시로 GCP 이그레스(트래픽 비용) 절감, (3) 기본 DDoS 보호.

역할 분담 — **A/B는 사용자만 할 수 있는 단계**(도메인 결제·계정·인증서 발급), C는 준비 완료
상태라 도메인 이름만 정해지면 몇 분 안에 끝납니다.

---

## A. 사용자: 도메인 + Cloudflare 계정 (1회, ~10분)

1. 도메인 구매 — Cloudflare Registrar(원가 판매, 관리 일원화 추천) 또는 아무 등록기관.
   - Cloudflare Registrar는 가입 후 대시보드 → Domain Registration → Register Domain.
2. Cloudflare 무료 플랜 계정 생성 → **Add a Site** 로 도메인 추가.
   - 타 등록기관에서 샀다면 안내되는 네임서버 2개를 등록기관 쪽에 설정 (전파 수 분~수 시간).

## B. 사용자: 대시보드 설정 (~5분)

1. **DNS**: A 레코드 추가
   - Name: `brain` (즉 `brain.<도메인>` — 원하는 서브도메인으로)
   - IPv4: `136.114.69.152`
   - Proxy status: **Proxied (주황 구름)** ← 이게 캐싱/보호의 핵심
2. **SSL/TLS → Overview**: 모드 **Full (strict)**
3. **SSL/TLS → Origin Server → Create Certificate** (기본값, 15년)
   - 표시되는 **Origin Certificate**(PEM)와 **Private Key** 두 텍스트를 복사해 둠.
   - ⚠️ Private Key는 이 화면을 닫으면 다시 못 봄. 채팅에 붙여넣지 말 것 — 아래 C-1처럼
     VM에 직접 저장 (SSH 접속은 사용자 계정으로도, 내가 gcloud로도 가능).
4. (권장) **Caching → Cache Rules**: `*/api/*` 는 **Bypass cache** 규칙 하나 추가
   - API 응답이 캐시되면 안 되고, 정적 자산만 Cloudflare가 대신 서빙하게 됨.

## C. 배포 반영 (내가 실행 — 도메인 이름 + 인증서가 VM에 놓이면 즉시)

1. 인증서 파일 저장 (VM에서):
   ```sh
   sudo mkdir -p /etc/caddy
   sudo nano /etc/caddy/cf-origin.pem   # Origin Certificate 붙여넣기
   sudo nano /etc/caddy/cf-origin.key   # Private Key 붙여넣기
   sudo chmod 600 /etc/caddy/cf-origin.key
   ```
2. `deploy/docker-compose.yml` 의 caddy 서비스에 마운트 추가(이미 준비된 패턴):
   ```yaml
   volumes:
     - ./Caddyfile:/etc/caddy/Caddyfile:ro
     - /etc/caddy/cf-origin.pem:/etc/caddy/cf-origin.pem:ro
     - /etc/caddy/cf-origin.key:/etc/caddy/cf-origin.key:ro
   ```
3. `deploy/Caddyfile` 하단의 주석 블록을 해제하고 `brain.example.com` 을 실제 도메인으로 교체.
4. 재시작 + 검증:
   ```sh
   sudo docker compose -f deploy/docker-compose.yml restart caddy
   curl -s https://brain.<도메인>/health        # {"status":"ok","git_sha":...}
   ```
5. 앱 연결 전환: 웹앱의 `CLOUD_BRAIN_BASE` 를 `https://brain.<도메인>` 으로 교체 (sslip.io 는
   전환 기간 동안 병행 유지 — Caddyfile 에 두 블록이 공존하므로 무중단).

## 확인 포인트

- `https://brain.<도메인>` 응답 헤더에 `cf-cache-status` 가 보이면 Cloudflare 경유 확인.
- GCP 콘솔 네트워크 이그레스 그래프가 정적 자산 비중만큼 내려가는지 1주 뒤 확인.
- sslip.io 주소는 언제든 폴백으로 유지 가능 (비용 0).
