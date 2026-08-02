# Isaac Sim 셋업 체크리스트 — Track E M0 (2026-07-19)

사장님 지시: 셋업 리스트 명문화 + D 드라이브 격리 설치(실행은 E9 종료 후). 이 문서 = 운영 절차서.

## 0. 하드웨어/환경 실측 (2026-07-19)

| 항목 | 값 | 판정 |
|---|---|---|
| GPU | RTX 5080 (Blackwell, **SM_120**), 16GB | Isaac Sim 5.1 **공식 recommended 등급** ✓ |
| 드라이버 | **596.36** | 최소 Win 580.88 초과 ✓ |
| base env | Python **3.13** + torch 2.11+cu128 (SM_120 인식) | E9·라이브 엔진 구동 중. **아이작심과 공유 불가**(아래) |
| D 드라이브 | 2000GB, **1996GB 여유** | 설치처로 충분 ✓ |
| 긴 경로 지원 | **미설정(0)** | 짧은 경로 `D:\isaac`로 회피(레지스트리 변경 안 함) |

## 1. 왜 격리 환경이 필수인가 (안전 + 버전 둘 다)

- **Python 버전**: Isaac Sim 5.1은 **Python 3.11 전용**. base는 3.13이라 **공유 불가** — 별도 3.11 env 필수.
- **안전**: base env는 E9 훈련 + 라이브 엔진이 의존. 여기에 isaacsim(자체 torch/numpy 핀)을 설치하면
  의존성이 뒤틀려 **돌아가는 E9·엔진을 깰 수 있음**. → **완전 분리된 env**(D 드라이브)에만 설치.
- **롤백**: env가 D의 독립 디렉토리라, 문제 시 폴더 삭제 = 완전 복원(base 무손상).

## 2. 설치 절차 (설치=지금 가능, GPU 미사용 / 실행=E9 후)

**✅ 설치 완료 (2026-07-19)**: `D:\isaac\env`(Python 3.11.15)에 `isaacsim==5.1.0.0` 전체 설치 성공
(app·core·cortex·extscache-kit/physics 등 서브패키지 포함, 분리 프로세스, GPU 미사용). 유일한
경고 = `packaging 23.0`(Isaac Sim 의도적 핀) vs wheel 빌드툴 24.0 요구 — **런타임 무관 무해**.
**아직 시뮬레이터 실행 안 함**(GPU를 E9가 점유; M0 실행은 E9 종료 후). 아래는 재현용 절차.

```
# 1) 격리 conda env (Python 3.11) — base(3.13) 무손상
conda create -y --prefix D:\isaac\env python=3.11

# 2) Isaac Sim 5.1 (약 10~30GB, 네트워크/디스크만 씀 — E9의 GPU 무영향)
D:\isaac\env\python.exe -m pip install --upgrade pip
D:\isaac\env\python.exe -m pip install "isaacsim[all,extscache]==5.1.0" \
    --extra-index-url https://pypi.nvidia.com

# 3) (RL용) Isaac Lab — 아기 커리큘럼 학습 프레임워크 (M1~에서 사용)
#    Isaac Gym(구버전 Preview 4)은 5080 SM_120 비호환이라 사용 금지. Isaac Lab만.
git clone https://github.com/isaac-sim/IsaacLab.git D:\isaac\IsaacLab   # M1 착수 시
```

**Blackwell 주의**(실사용 보고): Isaac Lab RL은 torch 2.7+ 필요 — Isaac Sim 5.1 번들 torch가 SM_120
지원하는지 M0 검증 게이트에서 확인. 미지원 시 env의 torch를 cu128 빌드로 교체(base와 격리돼 안전).

## 3. GPU 자원 게이트 (실행 순서)

16GB 중 현재 **12GB를 E9+엔진이 점유** → 아이작심(혼자 6~10GB+)과 **동시 구동 불가**.
**실행 순서: E9 종료/킬게이트 → Phase C 판정 → GPU 해제 → 아이작심 M0 실행.** (설치는 GPU 무관, 선행 가능.)

## 4. M0 검증 게이트 (실행 시)

- 콜드부트 → Isaac Sim compatibility checker PASS
- `isaacsim` import + 빈 스테이지 생성 + 1스텝 물리 진행 (headless)
- **Unitree G1 공식 URDF → USD 임포트**(관절 23~43 DOF 보존) — Track E 신체는 sim 속 G1
  (하드웨어 미구매). SPLATRA 리그는 병행/대안. G1 로코모션 = Isaac Lab 정책(운동 기관), 자아는 그래프.
- torch SM_120 커널 동작(간단 텐서 연산 GPU)

### 4.1 M0 1차 콜드부트 실측 (2026-07-19) — RED, 자원 경합 진단

사장님 GPU 배정 후 `scripts/isaac_m0_smoke.py` 헤드리스 콜드부트 시도. 진행/결과:
- **EULA**: 첫 실행이 대화식 NVIDIA Omniverse EULA를 요구 → detached라 EOF로 중단. 사장님 동의
  후 `OMNI_KIT_ACCEPT_EULA=YES`로 비대화식 수락 → **통과**.
- **GPU 인식**: RTX 5080 감지(Vulkan, 드라이버 596.36, 15977MB) ✓.
- **★크래시(831ms)**: `rtx.scenedb.plugin.dll` → `carb.scenerenderer-rtx` → `omni.hydra.rtx`
  RTX 씬 렌더러 초기화에서 Fatal crash. **유력 원인=호스트 RAM 압박**: 크래시 시점 시스템
  **Free Memory 5951MB**(32GB 중 ~26GB를 라이브 엔진 등이 점유). RTX 씬 DB는 부팅 시 호스트 RAM을
  크게 요구 → 6GB로 부족.
- **판정**: §3 자원 게이트가 예고한 그대로 — **아이작심 RTX 렌더러는 라이브 엔진과 동시 구동 불가**.
  E9는 GPU를 풀었으나 **라이브 엔진이 VRAM 7GB + RAM 대부분을 여전히 점유**.
### 4.2 M0 2차 콜드부트 — RAM 가설 반증, 진짜 원인=Blackwell RTX 렌더러 (2026-07-19)

사장님 승인으로 **라이브 엔진 정지**(워치독+엔진 종료, Free RAM 5.95→**8.62GB**, Free VRAM
**8.8GB** 확보) 후 M0 재부팅. **결과: 동일 크래시 재현**(636ms, `rtx.scenedb`→`carb.scenerenderer-rtx`
→`omni.hydra.rtx`). **→ RAM 압박 가설 반증(정정).** 진짜 원인은 **Blackwell SM_120에서 Isaac 5.1
Hydra RTX 렌더러 비호환**(자원 무관, 렌더러 플러그인 자체 결함). 엔진은 즉시 복구(중단 ~5분).

- **확정 다음 수(자원 무관, 서비스 중단 불필요)**:
  ① **물리-only 부팅** — M0 게이트 ②(빈 스테이지+1스텝 물리)는 PhysX만 쓰고 RTX 렌더러 불필요.
     `omni.hydra.rtx`/`rtx.scenedb`를 로드하지 않는 최소 kit experience로 SimulationApp을 띄우면
     크래시 회피 가능(별도 careful 태스크; SimulationApp 기본이 RTX를 로드하므로 experience 지정 필요).
  ② **드라이버/Isaac 버전** — Blackwell RTX 렌더러 지원 드라이버·Isaac 패치 확인(NVIDIA 포럼 다수 보고).
  ③ SPLATRA 리그를 sim 신체 원형으로 우선(렌더러 우회 경로).
  크래시 덤프: `d:/isaac/env/.../5.1/*.py.txt` (py-spy). 로그: `reports/isaac_m0_smoke2*.log`.

### 4.3 M0 CONCLUSIVE VERDICT — 공식 compatibility 체커도 크래시 (2026-07-19)

물리-only 판단 전에 **NVIDIA 공식 compatibility_check experience**를 직접 실행
(`kit.exe isaacsim.exp.compatibility_check.kit --no-window`). **결과: 부팅 0ms에 동일 RTX 크래시**
(crashreporter 발동, GUI가 사용자 입력 대기하며 hang → 강제 정리). **판정 확정: Isaac Sim 5.1의
RTX 렌더러(Vulkan/Hydra)는 이 Blackwell RTX 5080 + 드라이버 596.36 조합에서 근본 비호환.** 공식
체커조차 렌더러 초기화에 실패하므로, 물리-only 커스텀 experience도 렌더 확장을 배제해야만 부팅
가능하며 그 경로의 신체는 카메라/시각이 없어 Track E 목적에 제한적.

**M0 상태 = BLOCKED-BY-EXTERNAL (자율 조사 종결, 운영자 액션 대기).** 필요한 운영자 액션(택1):
- (권고) **GPU 드라이버 업그레이드** — 596.36보다 최신(Blackwell RTX 렌더러 수정 포함 버전). NVIDIA
  포럼에 RTX 50-series + Isaac 5.1 RTX 크래시 다수 보고, 신 드라이버로 해소 사례.
- 또는 **Isaac Sim 차기 패치**(Blackwell RTX 지원 강화판) 대기.
- **대안 경로(즉시 가능)**: Track E 신체 원형을 **SPLATRA**(우리 자체 렌더러/물리, Isaac RTX 무의존)로
  진행 — 감각 피질·반응 엔진·자기모델 루프는 SPLATRA 위에서 M1까지 개발 가능하고, Isaac은 드라이버
  해소 후 로코모션 정책(운동 기관) 용도로 합류. 이는 embodied_development_track의 "SPLATRA 병행/대안"
  가드레일과 정합.

자율 조사 요약: env 검증 ✓ · EULA 수락(운영자 동의) ✓ · GPU 인식 ✓ · **부팅 3회(스모크 2 + 공식
체커 1) 전부 RTX 렌더러 크래시** → 자원(RAM) 무관 확정 → 외부 블로커 확정. 더 이상의 자율 시도는
같은 벽. 결과는 결과다(red도 결과).

### 4.4 torch cu128 리드 검증 — GPU는 살아남, 렌더러는 드라이버 대기 (2026-07-19)

사장님 제보(RTX 5080 사용자가 PyTorch 2.7 + CUDA 12.8로 Isaac Lab 동작): 격리 env의 torch를
**2.7.0+cpu → 2.7.0+cu128로 교체**(`pip install torch==2.7.0 --index-url .../whl/cu128`). 실측:
- **torch cu128 = 성공** — `torch.cuda.is_available()=True`, RTX 5080 인식, **capability (12,0)=SM_120**.
  → **Isaac Lab RL(M1+)의 torch-GPU 요건 해결.** 이 교체는 base env(3.13)와 격리돼 안전.
- **Isaac Sim 렌더러 = 여전히 크래시**(4번째 부팅, access violation, ~780ms 동일 창). cu128은 Kit의
  Vulkan/RTX 렌더러 플러그인을 건드리지 않으므로 그대로.
- **판정 갱신**: Isaac 완전 해결 = **cu128 torch(✓ 완료) + GPU 드라이버 업그레이드(>596.36, 시스템
  레벨 = 운영자 작업)**. 렌더러 크래시는 Blackwell Vulkan/RTX 드라이버 이슈. **SPLATRA가 주력 경로로
  유지**(M0s/M1s green); Isaac은 드라이버 업그레이드 후 로코모션 기관으로 합류(이제 torch는 준비됨).

## 5. Radxa Dragon Q6A 보드 — 아이작심 불가, 별개 용도 (정직)

사장님이 대안으로 제시한 Radxa Dragon Q6A(Qualcomm QCS6490, ARM aarch64, Ubuntu 24.04, Tailscale
100.108.120.104)는 **아이작심을 구동할 수 없음**: 아이작심은 NVIDIA RTX(RT코어+CUDA)를 요구하는데
이 보드는 Adreno GPU(RT코어·CUDA 없음)에 ARM. 물리 시뮬 렌더링 자체가 불가.

**단, 그 NPU는 다른 트랙에서 값어치가 큼**(엣지 추론):
- Qualcomm AI Engine + **QNN**(SNPE 계열)은 **양자화 추론** 가속기 — 학습(Track E 시뮬)이 아니라
  **배포**용. 우리 ACE/판별기/지각 인코더를 INT8로 양자화해 이 보드에서 로컬 추론 = "서버 없는
  로컬 AGI를 실제 엣지 하드웨어에서" 비전의 물증.
- `/dev` NPU 노드 미감지는 흔함(QNN은 유저스페이스 라이브러리 경로). QNN SDK + 런타임 확인 필요.
- **위치: 별도 "엣지 배포 트랙"**(Track E 시뮬 호스트 아님). Tailscale로 이미 접근 가능 →
  E9 인코더가 나오면 양자화·이식 실험 대상 1순위. 이건 향후 별도 태스크로.

## 6. 롤백/안전

- 설치 env = `D:\isaac\env` (독립). 문제 시 `Remove-Item -Recurse D:\isaac` = 완전 복원.
- base env·E9·라이브 엔진 **무손상**(다른 Python, 다른 위치, GPU 미사용).
- 실행은 운영자 승인 + E9 종료 후.
