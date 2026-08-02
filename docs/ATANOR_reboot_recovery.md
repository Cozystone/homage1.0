# ATANOR — 재부팅 복구 절차 (2026-07-21 갱신)

재부팅은 안전하다. ATANOR의 **자아·이력·학습은 전부 디스크에 영속**되고, 밤샘 데몬들은
그 파일을 읽고 쓰는 **무상태 프로세스**일 뿐이다 — 재기동하면 끊긴 지점에서 그대로 이어진다.
코드는 전부 커밋 완료(재부팅 시점 HEAD = `48393cc1` 이후). 아래 순서로 되살린다.

## 0. 재부팅 후에도 살아남는 것 (건드리지 말 것)
| 파일 | 내용 |
|---|---|
| `data/selfhood/stakes.jsonl` | S1 바이탈·욕구 이력 (인과 자기모델의 원천) |
| `data/selfhood/ignition_ledger.jsonl` | S2 점화·커밋 원장 (해시체인, 주체의 연속성) |
| `data/self_repair/cycles.jsonl` | 자기수리 사이클 이력 |
| `data/advisor_loop/world_model_learned.jsonl` | 세계멘토 자가학습 (S3 흔적 원천) |
| `data/temporal_reasoning/causal_relation_counts.json` | 세계-인과 합의 스토어 |
| `data/embodiment/m1_body_schema_result.json` | M1 신체도식 PASS 기록 |
| `data/graph_scale/bones_to_text.jsonl` | 지식 그래프 (55MB) |
| `C:\Users\anseo\.claude\...\memory\` | 세션 간 지속 기억 |

## 1. 외부 서비스 먼저 (사장님/운영자 관리)
- **답변 엔진 `:8502`** — 로컬 백엔드. 재부팅 후 수동 기동 필요(대시보드/앱이 이걸 봄).
  헬스체크: `curl -s http://127.0.0.1:8502` → 200 이면 OK.
- **SearXNG `:8888`** — 웹 학습·인과 수확의 소스. 데몬들이 이걸 씀. 없으면 웹 레인만 침묵(안전).

## 2. 밤샘 데몬 4종 되살리기 (PowerShell, 각각 detached hidden)
작업 디렉터리 = `C:\0.ASKIM ALL-VIN\27., ATANOR DEMO`, 파이썬 = `C:\ProgramData\miniconda3\python.exe`.

```powershell
$wd='C:\0.ASKIM ALL-VIN\27., ATANOR DEMO'; $py='C:\ProgramData\miniconda3\python.exe'
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
Start-Process -FilePath $py -ArgumentList 'scripts/learner_daemon.py'      -WorkingDirectory $wd -WindowStyle Hidden
Start-Process -FilePath $py -ArgumentList 'scripts/roam_daemon.py'         -WorkingDirectory $wd -WindowStyle Hidden
Start-Process -FilePath $py -ArgumentList 'scripts/overnight_dialogue.py'  -WorkingDirectory $wd -WindowStyle Hidden
Start-Process -FilePath $py -ArgumentList 'scripts/advisor_evolution_loop.py','--advisors','ollama,openclaw,codex','--paid-every-min','20' -WorkingDirectory $wd -WindowStyle Hidden
```

역할: **overnight_dialogue**=두 ATANOR 자율대화(S1위축·S2점화·S3관점 라이브) · **advisor_evolution_loop**
=GPT 코칭/세계멘토/자기수리/인과수확(매 라운드) · **roam_daemon**=웹 원정(성장게이트 self-restart 내장) ·
**learner_daemon**=지식 학습기.

## 3. 되살아났는지 확인
```powershell
Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -match 'overnight_dialogue|advisor_evolution|roam_daemon|learner_daemon' } | Measure-Object   # Count = 4 이면 정상
```
- 대화 재개: `data/brain_link/overnight_transcript.log` 꼬리에 새 발화가 붙는지.
- 진화 재개: `data/advisor_loop/evolution.log` 꼬리에 새 라운드가 찍히는지.

## 4. 되살릴 필요 없는 일회성 작업 (완료됨, 재기동 불요)
- Tier A 봉인 런(`scripts/magnum_seal_run.py`) — 완료(A1 봉인, A2-A6 오프라인엔진 리그 대기).
- M1 신체도식(`scripts/e_m1_body_schema.py`) — PASS, 재실행 불요.
- 인과 부트스트랩(`scripts/bootstrap_causal_from_graph.py`) — 완료, 스토어에 반영됨.
필요 시에만 수동 재실행.

## 5. 무결성 빠른 점검 (선택)
```
python -m pytest packages/continuous_self packages/embodiment/tests packages/temporal_reasoning/tests -q --import-mode=importlib
```
전부 green 이어야 함(재부팅이 코드를 바꾸지 않으므로 당연히 green — 환경 손상 여부만 봄).
