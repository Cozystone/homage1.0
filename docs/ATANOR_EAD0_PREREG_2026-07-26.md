# EAD-0 사전등록 — evidence/answer discrimination 진단

상태: **사전등록·하네스 검증 완료, 실제 신호 측정 미실행**

시간 예산: 체크포인트 3시간 / 하드캡 8시간
승인 범위: EAD-0만. EAD-1+, `realtime.py`, API, LiveMemory, graph/staging 변경 금지.

## 격리 확인

- 구현은 신규 evaluator/worker/사전등록/테스트 파일에만 있다.
- 구조 검증 경로는 RealTimeThinker·DoubtGate·planner를 import하지 않는다.
- worker만 fresh subprocess 안에서 기존 `MultiHopReader`를 import하며, import 전에
  `CUDA_VISIBLE_DEVICES=-1`과 `PYTHONHASHSEED=0`을 강제 검증한다.
- live path에 discrimination 호출은 여전히 없다. 따라서 이 진단은 staging-only이고,
  GREEN이어도 live 배선을 뜻하지 않는다.
- sealed LiveMemory v2 prereg/report raw SHA-256과 candidate checkpoint/code bytes를
  실행 전후 결속한다. 결과 실행은 write-once tombstone 뒤 한 번만 가능하고 retry는 없다.
- evaluator source closure에는 두 EAD 스크립트뿐 아니라 이들이 사용하는
  `packages/eval_evidence/__init__.py`와 `receipt.py`의 strict parser/hash/write/environment
  primitive도 포함한다.

## 고정 표본

- 이미 노출된 replay-A/ON 실패에서 wrong-other-source 20건을 선택했다.
- 각 그룹은 동일 질문의 oracle POS span 하나와 실제 WRONG_SOURCE span 하나로 구성된다.
- unknown 12건은 당시 실제로 선택된 source/answer span을 negative로 사용한다.
- 총 52개: POS 20 / WRONG_SOURCE 20 / UNKNOWN 12.
- POS span은 oracle gold이므로 extraction을 측정하지 않는다. negatives도 post-hoc
  노출 실패 표본이다. 따라서 이 결과는 capability 근거가 아니라 메커니즘 생존성 진단이다.

반복 source 또는 LiveMemory 정규화 answer를 공유하는 그룹은 connected component로
묶은 뒤 signal을 보기 전에 5개 fold로 고정했다. fold별 case 수는 `10/10/11/10/11`이다.
worker 순서는 label과 무관한 worker-visible content digest로 정렬하고 두 번째 replay는
그 정확한 역순이다.

## 신호와 고정 판정

`ace_hotpot.pt`의 학습된 answerability/ranking head에서 `p_ans`를 읽고,
학습된 `ace_support.pt` support head에서 `p_sup_net=P(SUPPORTS)-P(REFUTES)`을 읽는다.
Hotpot checkpoint의 support head는 학습되지 않았으므로 사용하지 않는다. 두 checkpoint
모두 byte-bound된다.

유일한 술어군:

```text
p_ans >= tau_a AND p_sup_net >= tau_s
```

- `tau_a`: 0.00..1.00, 0.05 간격
- `tau_s`: -1.00..1.00, 0.05 간격
- deterministic grouped 5-fold OOF
- train feasible(`POS>=85%`, hard-negative false accept `<=20%`) 우선
- 이후 balanced accuracy, false accept, positive accept, 더 엄격한 두 threshold 순의
  완전결정 total order
- feasible threshold가 없는 fold도 결정론적 fallback은 기록하지만, 전체 결과는 반드시 RED
- 5개의 OOF threshold는 separability 진단일 뿐 하나의 deployable live threshold가 아니다.
- 이 two-reader 조합은 현재 live DoubtGate 구성도 아니다.

## 사전등록 gate

- POS accept `>=17/20`
- aggregate hard-negative accept `<=6/32`
- WRONG_SOURCE accept `<=4/20`
- UNKNOWN accept `<=2/12`
- forward/reverse raw signal exact replay
- worker error `0`
- 다섯 training fold 모두 feasible

하나라도 실패하면 EAD-0 no-go다. 최대 주장 상한은
“노출된 고정 단일홉 표본에서 기존 두 신호가 evidence-answer 결속과 unknown 거절을
동시에 분리할 수 있는가”뿐이다. 일반추론·신규 capability·live wiring·E5 주장은 금지한다.

## 검증 상태

- dry-run 구조 검증: GREEN (`candidate_executed=false`, `live_path_imported=false`)
- candidate digest: `02e30e438c333f5bbf5b05329bf4c6477c28ad2d8c9991893f42327604b87ee1`
- sealed input raw SHA:
  - prereg: `88fd657098c5c19e4da5f05ec7a9221f5376305b7b732f5ae539d6dfd1042a91`
  - report: `c409411e7748c8c5c216aaabd6ff61a932e9d518fa13f487871bcf1d563d3718`
- model-free adversarial/unit tests: `9 passed`
- 실제 checkpoint/model forward pass: **미실행**
