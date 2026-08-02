# 재부팅 후 재개 체크리스트 (2026-07-16 — Netac NV7000-t 2TB SSD 설치)

재부팅하면 엔진·dev서버·워치독이 모두 종료된다. 순서대로 되살리면 된다.
**모든 코드는 커밋됨(잃는 것 없음). 브랜치: demo (27., ATANOR DEMO worktree).**

## 0. 새 SSD 초기화 (Netac NV7000-t 2TB, M.2 NVMe — 내장)
새 SSD는 처음엔 Windows에 드라이브로 안 뜬다. 한 번만:
1. `Win+X` → **디스크 관리(Disk Management)**.
2. "디스크 초기화" 팝업 → **GPT** 선택.
3. 미할당(Unallocated) 2TB 우클릭 → **새 단순 볼륨** → 전체 크기 → **NTFS** 빠른 포맷 → 드라이브 문자(예: `D:`).
4. 완료되면 `D:` (또는 배정된 문자)로 ~1.8TB가 잡힌다.

## 1. 백엔드 엔진 되살리기 (:8502)
```
cd "C:\0.ASKIM ALL-VIN\27., ATANOR DEMO"
python scripts/engine_watchdog.py    # 워치독이 :8502 uvicorn을 띄우고 죽으면 재spawn
```
확인: `curl -s http://127.0.0.1:8502/health` → `{"status":"ok",...}` (정상시 <100ms).
- **주의(미해결)**: 엔진이 무거운 작업 중 /health 타임아웃 → 프론트가 "엔진 오프라인" 오렌지 배너.
  재발하면 uvicorn 워커 증설(`--workers 2`) 또는 블로킹 op async화 필요. [[ultimate-ui-ops]]

## 2. 프론트(Ultimate UI) 되살리기 (:3101)
```
"C:\0.ASKIM ALL-VIN\27., ATANOR DEMO\apps\web\dev-ultimate.cmd"
```
→ http://localhost:3101 (오늘 UI 클린 패스·엔진 배선 반영됨). 브라우저 새로고침 Ctrl+Shift+R.

## 3. ★ ATANOR Index Ring 1 — 새 2TB SSD에 빌드
storage.py가 **>=200GB 여유 비시스템 볼륨을 자동감지** → 새 D:를 인덱스 루트로 선택.
```
cd "C:\0.ASKIM ALL-VIN\27., ATANOR DEMO"
python scripts/build_ring1_index.py --report   # 새 SSD가 index_root로 잡히는지 먼저 확인
python scripts/build_ring1_index.py             # 잡히면 인덱스를 SSD에 빌드(멱등)
```
- `--report`가 `on_external: true`, `index_root: D:\ATANOR_Index`를 보여주면 성공.
- 현재 코퍼스: EN위키 full 7M(이미 빌드됨, C:). 새 SSD로 옮겨 빌드하면 C: 여유 확보.
- 이후 확장(디스크 넉넉): Wiktionary/StackExchange/Common Crawl 서브셋 → `CORPORA`에 추가.

## 4. (선택) 무거운 데이터를 새 SSD로 이전해 C: 확보
C:가 48GB뿐이라, 새 SSD로 옮기면 좋은 것:
- `data/graph_scale/world_pack_full/` (~7.5GB memmap) → D:로 이동 + 심링크 or 환경변수.
- `data/atanor_index/` (~1.8GB, 커질 예정) → D:.
- 이전 후 경로만 맞추면 됨(ATANOR_INDEX_ROOT 등).

## 5. Radxa Dragon Q6A + 4K 카메라 (엣지 지각 — 별도 트랙)
ATANOR 지각 파이프(카메라→객체/얼굴 인식, [[perceptual-agi-track]] [[visual-cortex-face-v0]])를
엣지 디바이스에서 돌릴 후보. 재부팅과 무관 — 보드 플래싱/카메라 셋업은 별도 세션에서.
Brain Link peer(이 PC와 P2P)로도 붙일 수 있음([[agora-solidarity-growth]]).

## 재개 시 나에게 할 말
"재부팅했어" 한마디면 위 1~3을 확인·실행하고 Ring 1을 새 SSD에 올린다.
