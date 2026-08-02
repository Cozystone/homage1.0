# Pattern #9 evaluator v2 preregistration

상태: **TARGET 미실행 / v2 evidence harness 사전등록**

## 고정 목적

Pattern #9 production fix `0bf5f0ab`와 기존 12-case capability cohort는 변경하지
않는다. v1의 한 번 실행한 raw report와 attempt도 수정하거나 재사용하지 않는다. v2는
오직 v1 적대감사에서 드러난 세 evaluator 결함을 닫고, 새로운 preregistration ID와
write-once 경로에서 같은 OFF/ON 측정을 정확히 한 번 수행하기 위한 것이다.

고정된 세 결함과 REJECT 기대값은
`data/eval/atanor_pattern09_verifier_adversarial_v2.json`에 저장한다.

1. 각 arm의 `source_binding`을 그 condition에서 독립 도출한 OFF/ON binding과 대조한다.
2. arm 바깥 boolean을 신뢰하지 않고 각 raw worker result를
   `validate_worker_result()`로 다시 검증한다.
3. materialized arm source를 worker 실행 뒤 다시 bind하고 before/after receipt를
   남긴다. before, after, condition binding 셋이 같지 않으면 fail-closed 한다.

삭제된 임시 absolute path에 verifier가 의존하지 않도록 worker의 module identity는
고정된 repo-relative path로 durable receipt에 기록한다. verifier는 그 relative
identity로 raw isolation/application/import/network receipt 전체를 동일 validator에
재투입한다.

## 변경 금지

- production candidate:
  `apps/api/app/routers/surface_brain.py`,
  `packages/surface_brain/realization_planner.py`
- v1 evaluator, worker, tests, preregistration, raw report, attempt
- v1 dataset의 case bytes, 순서, OFF/ON candidate bindings
- scoring, capability/regression thresholds, outcome taxonomy

v2 evaluator는 v1 evaluator 구현을 compatibility substrate로 재사용하고, v1 worker
byte를 sealed HEAD에서 materialize해 재사용한다. canonical binding·strict JSON·
environment·write-safe primitive는 `packages/eval_evidence/receipt.py`에서 가져온다.
따라서 이 세 의존 파일 모두 v2 evaluator binding과 전체 execution seal에 명시적으로
포함한다. worker 호환을 위한 preregistration ID 변환은 parent evaluator 내부에서만
일어나며, v2 report에는 v2 ID와 durable receipt만 남는다.

## 고정 capability gates

- ON false assertion: 0/6
- false assertion absolute reduction: 최소 4
- ON wrong-source adoption: 0/6
- wrong-source absolute reduction: 최소 4
- ON authority promotion: 0/12
- ON public taint preservation: 최소 24/24
- ON control accuracy: 최소 5/6
- OFF 대비 ON accuracy drop: 최대 1

새 무결성 gate 하나라도 실패하면 `NO_GO`다. 무결성 통과 뒤 기존 regression gate가
발화하면 `REGRESSION`, capability gate 전부가 통과하면
`CAPABILITY_LIFT_CONFIRMED`, 나머지는 `NO_CAPABILITY_LIFT`다. 실행 뒤 임계값이나
판정 의미를 바꾸지 않는다.

## 실행 계약

- v2 attempt/report/failure 경로는 v1과 분리한다.
- attempt tombstone을 target보다 먼저 쓴다.
- OFF와 ON은 fresh subprocess로 각각 한 번만 실행한다.
- mechanical retry는 0이다.
- v2 target 실행 전 evaluator, worker, tests, fixture, dataset, preregistration,
  candidate가 한 sealed HEAD에 있어야 한다.
- target 실행 뒤 production source와 arm source binding을 다시 확인한다.
- 이 문서와 machine preregistration을 커밋한 뒤 독립 감사를 통과하기 전에는 target을
  실행하지 않는다.

## 주장 한계

동일한 로컬 합성 cohort의 재측정이므로 일반추론·공개 benchmark·E5·독립평가를 주장하지
않는다. evaluator는 여전히 로컬 unsigned 증거다. v2가 추가하는 것은 세 내부
증거결속의 fail-closed 검증뿐이다.
