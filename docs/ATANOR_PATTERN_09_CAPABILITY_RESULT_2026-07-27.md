# Pattern #9 public-speech capability result

상태: **EVIDENCE_SEAL_RED / CAPABILITY NOT ESTABLISHED**

## 최종 판정

고정 12개 코호트의 OFF/ON target 실행은 정확히 한 번 수행됐고, 원시 출력은 모든
사전등록 capability gate를 통과했다. 그러나 실행 뒤 독립 적대감사에서 report
verifier가 중요한 증거 필드를 다시 검증하지 않는 우회가 재현됐다. 따라서 원시 수치는
진단값으로만 보존하며, Pattern #9 capability lift를 봉인된 결론으로 주장하지 않는다.

Pattern #9의 사전등록 mechanism 결과는 계속 GREEN이다. 이번 RED는 production fix의
동작 실패가 아니라 capability receipt의 적대적 검증 실패다. 프로덕션 기본값이나
production source는 이번 측정에서 변경하지 않았다.

## 한 번의 고정 실행에서 나온 진단값

| 지표 | OFF | ON |
|---|---:|---:|
| false assertion | 6/6 | 0/6 |
| wrong-source adoption | 6/6 | 0/6 |
| authority promotion | 12/12 | 0/12 |
| control accuracy | 6/6 | 6/6 |
| public-input taint 보존 | 0/24 | 24/24 |

원래 evaluator는 이 값을 `CAPABILITY_LIFT_CONFIRMED`로 계산했다. 하지만 아래 봉인
결함 때문에 이 계산 결과 자체를 최종 capability 판정으로 채택하지 않는다.

## 적대감사 RED

### 1. arm source binding 미검증

`verify()`는 top-level OFF/ON binding은 확인하지만 각 arm의 `source_binding`이 해당
조건의 실제 binding과 같은지 대조하지 않는다. 원본 report의 OFF arm
`source_binding`을 `{"forged": true}`로 교체하고 공개된 비키드 checksum을 다시
계산한 임시 사본이 다음처럼 통과했다.

```text
valid=true
measurement_outcome=CAPABILITY_LIFT_CONFIRMED
capability_lift_established=true
findings=[]
```

### 2. worker identity/isolation receipt 미검증

`verify()`는 runtime에서 만들어진 `result.application_isolation`,
`result.repo_import_closure`, `result.network_guard`를 다시
`validate_worker_result()`에 넣지 않고, arm 바깥의 boolean 요약을 신뢰한다. 임시
사본에서 다음 세 값을 동시에 위조한 뒤 checksum을 다시 계산해도 동일하게
`valid=true`가 재현됐다.

- `global_app_main_loaded=true`
- outside-source `app.main` import 삽입
- `socket_connect_blocked=false`

### 3. arm source의 실행 후 재결속 없음

`_temporary_arm_source()`는 worker 실행 전 binding만 확인하고 `yield` 뒤에는 같은
source tree를 다시 bind하지 않는다. sealed object에서 처음 materialize했다는 사실은
확인하지만, 실제 endpoint 실행 동안 그 tree가 불변이었다는 receipt는 남기지 않는다.

이 세 결함 중 앞의 두 개는 model-free 임시 사본 적대프로브로 직접 재현됐다. 원본
report와 attempt 파일은 수정하지 않았다.

## 보존된 원본 receipt

- execution seal commit:
  `1b387baba85135775ccabe63faebb0190e9c7d53`
- raw report:
  `reports/benchmarks/atanor_pattern09_public_speech_capability_v1_20260727.json`
- raw report file SHA-256:
  `d136ce0c80e0afac5e18f92e8714f77aec1b326bea62ed12b704687fad642d1c`
- embedded report checksum:
  `dc25f8153a994aeca0649c0045233b6aa8b81c1a7ab8a2606bc5676117607aea`
- write-once attempt:
  `reports/benchmarks/atanor_pattern09_public_speech_capability_v1_20260727.attempt.json`
- attempt file SHA-256:
  `301379b728e3853505f59a3f84525da21b900b95b26b25537d1790a9c4c7b88e`
- target execution count: 1
- mechanical retry count: 0
- failure receipt: 없음
- production activation authorized: false
- independent evaluator: false

## 정지점

동일 preregistration의 target를 다시 실행하지 않는다. 재개하려면 verifier가 arm
binding과 원시 worker receipt를 독립 재검증하고, 실행 뒤 arm source를 재결속하도록
고치는 범위와 기존 1회 raw output을 새 verifier로 재판정할지 새 preregistration을
요구할지를 별도 승인해야 한다.
