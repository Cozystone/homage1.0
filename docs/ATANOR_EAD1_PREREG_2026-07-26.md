# EAD-1 사전등록 — live 배선·권한 경계

상태: **판정 전**

시간예산은 체크포인트 4시간, 하드캡 10시간이다. 사용자의 지시에 따라 체크포인트
보고는 하지 않고 EAD-1 결론만 보고한다.

EAD-1은 모델을 실행하지 않는다. `RealTimeThinker`가 별개의 answerability/support
reader를 기본 임계값 `0.90/0.90`으로 구성하는지, 답을 만든 정확한 evidence row만
검증하는지, 검증되지 않은 live/static evidence와 결속 불명 상태가 fail-closed인지,
public `/learn`이 `verified` 권한을 만들 수 없는지만 검증한다.

모든 사전등록 노드가 skip·xfail·error 없이 통과하고, 실행 전후 source/candidate/dataset
bytes가 같을 때만 GREEN이다. 하나라도 실패하면 EAD-1 RED이며 EAD-2로 진행하지 않는다.

GREEN의 주장 상한은 **model-free live wiring mechanism**이다. 모델 신호, 신규 회상
capability, 일반추론, 공개 벤치마크, E5 또는 독립 심판을 주장하지 않는다.
