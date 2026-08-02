# EAD-3 fresh counterbalanced capability result

상태: **CAPABILITY_LIFT_CONFIRMED**

사전등록 ID: `ead23-fresh-counterbalanced-v1-20260726`

사전등록 커밋: `cf12eee1`

봉인된 평가기 커밋: `cc02630d`

단일 실행: 2026-07-26T14:14:27.631858Z ~ 2026-07-26T14:14:38.090059Z

## 판정

EAD-1 discriminator를 켠 조건은, 고정된 답안 후보와 검증된 단일 evidence 사이의
의미 결속을 판별하는 fresh synthetic 단일홉 코호트에서 사전등록된 capability gate를
전부 통과했다.

| 지표 | OFF | ON |
|---|---:|---:|
| supported accept | 24/24 | 24/24 |
| wrong-source grounded-adoption | 24/24 | 2/24 |
| unknown false-grounding | 12/12 | 0/12 |
| 전체 hard-negative false-grounding | 36/36 | 2/36 |
| balanced decision accuracy | 0.5000 | 0.9722 |
| decision accuracy | 0.4000 | 0.9667 |
| accepted precision | 0.4000 | 0.9231 |

Balanced decision accuracy lift는 `+0.472222222222`였다. Paired exact McNemar는
OFF-only correct `0`, ON-only correct `34`, two-sided `p=1.16e-10`이었다.

6개 관계군 모두 supported `4/4`를 보존했다. Hard-negative accept는
`archive_site=1`, `ceremonial_instrument=1`, 나머지 네 관계군은 `0`이었다.
Wrong-source 유형별 accept는 same-entity/sibling-relation `2/12`,
same-relation/sibling-entity `0/12`였다. 사전등록된 모든 전역·관계군·유형별 gate가
통과했다.

## 실행 무결성

- 60개 항목 각각 OFF 1회, ON 1회만 실행했다.
- 네 fresh subprocess를 `A/OFF forward`, `B/ON forward`,
  `A/ON reverse`, `B/OFF reverse` 순서로 실행했다.
- Worker error는 0건이었다.
- Candidate, runtime asset, dataset, evaluator source digest는 실행 전후 모두 동일했다.
- EAD-1 candidate digest
  `819e0ff07cfb968109d7d219e6bb86c35c9b2c21565af8263b13c3486d6f0425`
  를 유지했다.
- 독립 verifier 결과는 `valid=true`, findings 0건이다.
- 보고서 checksum은
  `18d96e78c9fef33ccd65ddbabddea6660d0754f714e07a49066f49c890f9c75b`다.

## 주장 한계

이 결과는 **fresh local synthetic, fixed-proposal, verified single-row
evidence-answer discrimination capability**에 한정된다. 답안 생성, 다단계 추론,
공개 벤치마크, GPQA, ARC, E5 또는 독립 심판 증거가 아니다.

또한 gate가 reject해도 현재 `RealTimeThinker`는 답안 문자열을 반환하고
`grounded=false`로 표시한다. 따라서 확인된 것은 오답 생성·표시 감소가 아니라
**허위 grounding 및 grounded-adoption 감소**다.

현재 저장소의 verified-evidence 경로에는 feature flag가 없고 discriminator가 이미
호출된다. Public `/learn`은 evidence를 verified로 승격할 수 없으며, 이번 평가는
evaluator-owned privileged promotion을 사용했다. 이번 작업은 production source나
상태를 변경하지 않았고, 별도의 production 활성화 권한도 만들지 않았다.
