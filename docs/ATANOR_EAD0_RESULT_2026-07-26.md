# EAD-0 결과 — evidence/answer discrimination

상태: **mechanism GREEN / capability 미입증 / live 배선 미실행**

EAD-0만 실행했다. EAD-1 이상, `realtime.py`, API, LiveMemory, graph/staging은
변경하지 않았다.

## 사전등록 판정

| 항목 | 사전등록 gate | 실측 | 판정 |
|---|---:|---:|---|
| POS accept | ≥17/20 (85%) | 18/20 (90%) | GREEN |
| WRONG_SOURCE false accept | ≤4/20 (20%) | 0/20 (0%) | GREEN |
| UNKNOWN false accept | ≤2/12 | 0/12 (0%) | GREEN |
| hard-negative 전체 false accept | ≤6/32 (20%) | 0/32 (0%) | GREEN |
| forward/reverse replay | exact | exact | GREEN |
| worker error | 0 | 0 | GREEN |
| training-fold feasibility | 5/5 | 5/5 | GREEN |

두 사용자 핵심 gate인 `POS accept ≥85%`와 `hard-negative false accept ≤20%`를
동시에 통과했다.

사용한 유일한 판정 술어군은 다음과 같다.

```text
p_ans >= tau_a AND p_sup_net >= tau_s
```

5-fold OOF 임계값은 fold 0/1/3/4에서 `(0.90, 0.90)`, fold 2에서
`(0.95, 0.95)`였다. POS false reject 두 건은 P01과 P05다. hard-negative
32건은 모두 reject됐다.

## 무엇이 확인됐나

기존 `ace_hotpot.pt`의 학습된 answerability 신호와 기존 `ace_support.pt`의
학습된 support-minus-refute 신호를 결합하면, 이 고정·노출 표본에서는
“이 근거가 바로 이 답을 지지하는가”와 unknown 오답을 하나의 conjunction
predicate로 분리할 수 있었다.

이는 **staging mechanism 생존성** 증거다. 현 live 경로에는 이 two-reader
조합이 배선돼 있지 않으며, `RealTimeThinker.think()`는 `DoubtGate`를 호출하지
않는다. 따라서 현재 사용자 경로의 능력 향상이나 안전성 향상을 뜻하지 않는다.

## 정직한 한계

- 표본은 이미 노출된 LiveMemory v2 실패에서 post-hoc 선택됐다.
- POS 답 span은 oracle gold라서 답 추출 능력을 측정하지 않았다.
- hidden holdout·독립 평가자·서명·E5 attestation이 없다.
- evaluator·labels·candidate가 같은 로컬 저장소에 있다.
- OOF의 다섯 임계값은 분리 가능성 진단이며 하나의 배포 가능한 live 임계값이 아니다.
- 일반 추론, 다단계 추론, 공개 벤치마크, GPQA/ARC 성능 상승은 전혀 주장하지 않는다.

그러므로 판정은 **EAD-0 mechanism GREEN**까지다. capability와 live wiring은
각각 RED가 아니라 **미측정/미실행**이다.

## 봉인·재현 증거

- pre-run commit: `e18ce714f047a2be1db5f029f731dfaed63cf2ba`
- prereg raw SHA-256:
  `75e765d762e7fa6b06676b823dde7238dbe5119edd497477c53eeedaf641c895`
- evaluator source closure:
  `7c414b2264ad6c54e330efc45eafc6089dbb3da688a1af3c6ef3bb19dafc86e3`
- two-reader candidate closure:
  `02e30e438c333f5bbf5b05329bf4c6477c28ad2d8c9991893f42327604b87ee1`
- report raw SHA-256:
  `1fce0039a111467531e0f128e3cde21f429f104e40bd90914b51120626e96b34`
- attempt raw SHA-256:
  `54021c6cecafb4d6fff27b719eb33fc906e04aa8fef5c9804adc560a2b668e0a`
- report detached checksum:
  `962be7a88e40c27a6617b817a91b9d1feb7de70957131aa6fd067bd520495e8f`
- worker runtime: Python 3.13.12 / PyTorch 2.11.0+cu128 / NumPy 2.4.6,
  CPU-only, `PYTHONHASHSEED=0`
- one-shot evaluation: 2026-07-26T08:47:26.445859Z–
  2026-07-26T08:47:30.858618Z
- verifier: valid=true, findings=[], authenticity/capability/live-wiring established=false
- model-free regression: 50 passed

## 정지점

EAD-0 결과 봉인 뒤 정지한다. EAD-1 이상이나 live `realtime.py`/API 배선은
자동 착수하지 않으며 별도 승인 대상이다.
