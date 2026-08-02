# ATANOR CO-C0 F1.1–F4 최종 상태 — 2026-07-26

> **결산 범위:** 이 문서는 CO-C0 F1.1, F2, F3, F4의 미커밋
> prototype stash를 읽기 전용으로 감사한 최종 상태 기록이다. 새 구현,
> prototype 수정, stash apply/pop/drop, staging·graph 변경, production 승격,
> push는 수행하지 않았다.

## 1. 최종 판정

커밋된 F1은 닫힌 필드 스키마와 정합성 검사를 제공하지만, 스스로
`profile_scope=contract_profile_only_not_live_join`이라고 선언한다. 즉 F1은
caller가 제출한 source stamp의 모양과 내부 일관성은 검사하지만, 그 값이
실제 source owner에게서 왔는지는 증명하지 않는다.

F1.1–F4의 적대 검증은 이 경계를 실제로 넘지 못했음을 보여준다.

| 단위 | 좁은 mechanism 결과 | 적대 판정 | 최종 상태 |
|---|---|---|---|
| F1.1 `BoundSourceObservation` | session/envelope/moment, clock, TTL, replay를 한 live context에 결속하는 test-only mechanism 존재 | ordinary in-process caller가 내부 token으로 production registry와 verifier를 직접 만들고 자기 payload를 `fresh=True`로 검증 | **설계 RED / 미봉인** |
| F2 초기 prototype | response workspace의 hash-only 관측 seam과 closed receipt schema 존재 | 다른 session의 `RequestCycle`이 현재 envelope와 함께 승인됨 | **RED** |
| F2 local session fix | 직접적인 `cycle.session_id != envelope.session_id`는 2줄과 3개 테스트로 차단; focused 19/19 | A-session terminal을 B-session context로 canonical re-seal하면 typed/serialized adapter가 모두 승인 | **좁은 수정 GREEN, F2 전체 설계 RED / 미봉인** |
| F3 self snapshot | 두 번 읽기, revision 안정성, stale/future/missing fail-closed, raw-value 축소 | caller clock·TTL 또는 위조 가능한 semantic timestamp로 하루 된 source가 `fresh_bounded_read`가 됨 | **설계 RED / 미봉인** |
| F4 metabolic observer | 네 owner namespace 분리, payload whitelist, advisory-only fence | caller가 지어낸 `instance_id/revision/sampled_at/max_age`가 `fresh`로 봉인되고 secret marker까지 receipt에 직렬화됨 | **설계 RED / 미봉인** |

이 결과는 benchmark capability 감소를 측정한 것이 아니다. F1.1–F4는 신뢰할
수 있는 live mechanism으로 봉인되기 전에 멈췄으므로 attributable capability
측정 자체가 없었다. 일반 테스트 green이나 canonical digest는 capability
신호가 아니며, 여기서는 adversarial trust gate도 통과하지 못했다.

## 2. 증거 범위와 한계

세 stash는 모두 F1 commit
`79f0b9534f24fbfc40b8a4651a2d6963fd86c4b6`를 base로 한다. stash 안에는
source와 test만 있고 JUnit XML, sealed receipt, result JSON, preregistration,
최종 결과문서가 없다. 따라서 저장소만으로 당시 모든 명령과 test count를
재구성할 수는 없다.

이번 결산은 다음 세 증거층을 구분한다.

1. stash object와 blob을 직접 읽어 확인한 코드·테스트;
2. 당시 로컬 Codex session log에 남아 있는 실제 adversarial command/output;
3. 원래 결과가 보존되지 않은 경우 이번 결산 중 stash blob을 apply하지 않고
   메모리에서 재생한 독립 probe.

로컬 session log는 repo artifact도, 서명된 독립 receipt도 아니다. 아래 raw
output은 RED를 구체화하는 감사 근거이지 E4/E5 증거가 아니다.

### 2.1 Stash 식별과 실제 크기

| 논리 단위 | Stash commit | 실제 내용 | F1 base 대비 |
|---|---|---|---:|
| F1.1 | `d90a0f14b17633cafa45295fb89fe6820c3b1c08` | module 1,102줄 + test 433줄 | `+1535` |
| F2 session fix | `8e13d3318b96110b148d2c0e5aee743b06007652` | response workspace tracked patch + F2 module 817줄 + test 562줄 | `+1565/-15` |
| F2–F4 prototype | `9cc3d8d8e4f29c97c211e2e944e9d3809cbf3233` | response workspace tracked patch + F2/F3/F4 modules와 tests | `+4508/-15` |

`stash@{1}`의 “186줄”은 stash 전체 크기가 아니다. 기본 `git stash show`가
보여 준 `packages/cgsr/cgsr/response_workspace.py`의 net tracked delta
`+186/-15`만을 가리킨다. untracked F2 module과 test 1,379줄이 별도로 있다.

또한 `stash@{1}`과 `stash@{2}`의 response workspace blob은 동일한
`9019d105b5ac99de6f5d0e449a07f5b7ac627bd0`이다. 두 stash 사이에서 F2
session fix에 고유한 변경은 정확히 53줄이다.

- 구현 2줄: cross-session equality 거부
- 테스트 51줄: observer, terminal-only builder, strict adapter의 세 경로

Stash 번호는 다른 stash 조작으로 바뀔 수 있으므로 이 문서의 장기 식별자는
stash commit과 blob hash다.

## 3. F1.1 — `BoundSourceObservation`

### 3.1 의도와 담긴 것

Prototype blobs:

- `e5b7066cbb8217b21837a19dd8c89fee2d0fdd3b`
  — `packages/cognitive_core/bound_source_observation.py`
- `df36dfda076d34adcac354c5c553f2fb6c4c7861`
  — `packages/cognitive_core/tests/test_bound_source_observation.py`

의도는 source owner policy, payload digest, session/envelope/moment, read
boundary, freshness를 한 process-local live context에 묶고, serialized
observation 자체에는 freshness를 주장하지 않는 것이었다. Context close,
cross-context replay, stale/future, mutation, fixture/production crossing을
거부하는 13개 테스트도 있다.

공식 production registry는 의도적으로 비어 있고 module docstring도
cross-restart attestation이 아니라고 명시한다. 정상 public factory를
사용하면 production owner issuance가 하나도 없는 상태다.

### 3.2 결정적 adversarial RED

이번 결산에서 stash를 apply하지 않고 blob을 메모리에서 실행해 다음 공격을
독립 재생했다.

1. ordinary in-process caller가 module의 `_CAPABILITY_TOKEN`을 import한다.
2. caller가 `_SourcePolicyRegistry(trust_domain="production")`를 직접 만든다.
3. caller가 자기 clock과 자기 registry로
   `BoundSourceVerificationContext`를 만든다.
4. caller-owned issuer로 attacker payload를 발급한다.
5. public `verify_bound_source_observation()`에 attacker context를 넘긴다.

Raw result:

```text
trust_domain='production'
fresh=True
source_key='attacker.web'
registry_version='attacker.production.v1'
verified_by_public_api=True
```

근거 위치:

- import 가능한 token: prototype line 58
- registry가 token identity만 검사: lines 198–249
- context가 같은 token과 caller registry를 신뢰: lines 668–756
- caller context가 issuance ledger와 verifier를 동시에 소유: lines 771–914
- public verifier가 caller가 준 context를 그대로 사용: lines 938–954

독립 probe의 command/output은 로컬 Codex session log
`rollout-2026-07-26T23-49-34-019f9ee7-1c3e-7a10-9d06-a4133e86a057.jsonl`,
2026-07-26T14:51:17.936Z–14:51:20.221Z에 남아 있다. 별도의 repo receipt는
없다.

기존 테스트는 honest fixture registry 내부의 replay와 policy mismatch는
검사하지만, module-private 이름이 security boundary가 될 수 있는지 시험하지
않는다. Python의 underscore는 접근 통제가 아니므로 이 문제는 단순 누락
검사가 아니라 root-of-trust 실패다.

### 3.3 F1–F4를 고치지 못하는 이유

F1.1 prototype은 `build_co_f1_profile()`과 실제 F2/F3/F4 owner adapter에
연결되지 않았다. 정상 production registry는 비어 있어 공식 issuance
경로가 없고, 비공식 caller는 오히려 자기 production registry를 위조할 수
있다.

따라서 이 stash는 “공통 primitive 하나로 세 RED를 고친다”는 acceptance
condition을 충족하지 못한다. process-local 관습적 privacy를 adversarial
provenance authority로 승격한 설계 자체가 막혔다.

### 3.4 회수 가치와 처분

다음은 설계 재료로 회수할 가치가 있다.

- serialized contract와 live freshness verdict의 분리
- session/envelope/moment와 issuance occurrence 결속
- verification 시점 freshness 재계산과 future-date 거부
- bounded issuance, context close, replay fail-closed
- raw value 대신 digest만 내보내는 schema와 redaction tests

그러나 현재 module 전체, 내부 token, caller-constructed registry/context,
green-looking fixture suite는 그대로 되살리면 안 된다. 실제 owner 또는
operator가 지배하는 경계 밖에서 caller가 verifier를 만들 수 없어야 한다.

**처분 판정:** 현재는 최종 문서 리뷰를 위해 forensic stash로 그대로 둔다.
`pop`하거나 참고용 commit으로 올리지 않는다. 문서 승인 후 별도 명시적
승인으로 drop하는 것이 맞다. 향후에는 유용한 계약만 새 trust boundary 위에
다시 구현하고, 위 root-forgery probe를 사전등록 필수 RED test로 둔다.

## 4. F2 — response workspace observation과 session binding

### 4.1 초기 F2 prototype의 RED

`stash@{2}`의 F2 blobs:

- `2f36cbfb38081fb0a915226b3e59ee3f3db7342b`
  — `co_response_observation.py`
- `57190f7fa828528a085ce6023a2461a0d3b24206`
  — `test_co_response_observation.py`
- `9019d105b5ac99de6f5d0e449a07f5b7ac627bd0`
  — modified `response_workspace.py`

초기 `_validate_bindings()`는 canonical `RequestCycle`, moment, F1 receipt의
형태와 identity는 재구성했지만 `request_cycle.session_id`와
`envelope.session_id`를 비교하지 않았다. 따라서 다른 session의 canonical
cycle을 현재 envelope/moment/F1과 함께 제출해도 receipt를 만들 수 있었다.

이 부분은 좁은 binding 누락이었다. Observer의 default-off callback,
hash-only answer snapshot, candidate closure, unchanged arbitration, ordinary
exception containment은 이 결함과 별개로 실제 구현되어 있었다.

### 4.2 `stash@{1}` local fix의 scoped GREEN

`stash@{1}`은 다음 한 검사를 추가했다.

```python
if cycle.session_id != envelope.session_id:
    raise ValueError("request cycle and cognitive envelope session IDs do not match")
```

그리고 다음 세 경로에 cross-session negative test를 추가했다.

- `COF2ResponseObserver` constructor
- `build_co_f2_terminal_only_receipt`
- `adapt_co_f2_response_receipt`

Focused suite는 19/19 통과했고, 직접 잘못 섞은 cycle은 세 경로 모두에서
거부됐다. 이 53줄은 좁은 mechanism fix로는 GREEN이었다.

### 4.3 더 강한 co-reseal adversarial RED

다음 probe는 local equality가 session provenance를 증명하지 못함을 보였다.

1. A session에서 정상 terminal-only receipt를 만든다.
2. 완전히 유효한 B session의 envelope, moment, F1 profile, cycle을 만든다.
3. A receipt의 `moment_id`, `f1_profile_receipt_id`,
   `cycle_binding.{cycle_id,request_id,input_observation_id}`만 B 값으로 바꾼다.
4. canonical `DecisionReceipt`로 다시 봉인하되 A terminal digest와 관측
   payload는 그대로 둔다.
5. B context에서 typed와 serialized strict adapter를 실행한다.

Raw result:

```json
{
  "serialized": {
    "accepted": true,
    "copied_terminal": true,
    "source_session_in_receipt": false
  },
  "typed": {
    "accepted": true,
    "copied_terminal": true,
    "source_session_in_receipt": false
  }
}
```

Command/output은 로컬 Codex session log
`rollout-2026-07-26T11-24-45-019f9c3d-3874-7302-bd40-ed2cdf40b005.jsonl`,
2026-07-26T02:55:59.084Z–02:56:01.385Z에 남아 있다.

직접 equality check는 constructor 입력의 우발적 혼합만 막는다. Receipt의
`cycle_binding`은 session을 담지 않았고, 더 근본적으로 unsigned
`DecisionReceipt`는 caller가 context 필드까지 함께 바꿔 다시 봉인할 수
있다. 단순히 `session_id` 필드를 더 넣어도 attacker가 B 값으로 같이 바꿀
수 있으므로 충분하지 않다.

같은 감사에서는 zero-builder topology, equal-score tie ordering,
failed/completed terminal mismatch, raw metadata channels, whitespace
canonicalization, synchronous callback/SystemExit, terminal-only caller
attestation도 미봉인 문제로 남았다. 이 추가 항목들의 독립 sealed receipt는
없으므로 본 결산의 결정적 판정은 위 co-reseal 재현에 둔다.

### 4.4 분류, 회수 가치, 처분

- 초기 cross-session 비교 누락: **좁은 버그**
- local 2줄 check와 3개 test: **회수 가치 있음**
- session/terminal의 issuer provenance 부재와 re-seal 허용: **설계 결함**
- F2 전체: **adversarial RED / 미봉인**

회수할 수 있는 요소는 optional observer seam의 default-off
output-equivalence, hash-only answer body, exact/closed schema validation,
직접 session equality guard와 세 test, deterministic same-session
round-trip이다. 다만 synchronous observer와 terminal attestation까지 포함한
현재 stash 전체는 회수 대상이 아니다.

**처분 판정:** `stash@{1}`은 대부분 `stash@{2}`의 F2와 중복되고 고유
가치는 53줄뿐이다. 현재는 forensic reference로 유지하되 pop/commit하지
않는다. 문서 승인 후 drop하고, F2가 재개될 때 필요한 2줄과 3개 test만
새 owner-bound 설계에 수동 이식하는 것이 맞다.

## 5. F3 — bounded operational-self snapshot

Prototype blobs:

- `ac87f1fcb7f006e12bf2cd601dfa69c375b2433e`
  — `co_self_snapshot.py`
- `51d041a3da6bafa16eb356b89fe16e5c9eb89d9e`
  — `test_co_self_snapshot.py`

### 5.1 결정적 adversarial RED

`build_co_f3_self_snapshot()`은 caller에게서 `read_at_ns`와 네 namespace의
`source_max_age_ns`를 받는다. `_max_ages()`는 이 값이 nonnegative
integer인지밖에 검사하지 않는다. `_pair_stamp()`는 다음 식으로 freshness를
정한다.

```text
age = caller_read_at_ns - source_sampled_at_ns
fresh = 0 <= age <= caller_max_age_ns
```

Source timestamp도 independently attested 값이 아니다.

- `SelfState.updated_at`
- hash chain row 안의 commitment `ts`
- MEC span `ts`
- MEC baseline `updated`

두 번 같은 값을 읽는 것은 안정성은 보여도 owner issuance나 현재 clock을
증명하지 않는다. Commitment chain도 keyed signature가 아닌 SHA-256
연결이므로 내부 연속성만 보인다.

당시 adversarial run의 핵심 raw results:

```text
old_source_forged_read_clock:
  actual_wall_age_seconds=86400.0
  declared_age_seconds=2.0
  freshness=[fresh,fresh,fresh,fresh]
  status=fresh_bounded_read

old_source_huge_ttl:
  age_seconds_min=86400.0044823
  freshness=[fresh,fresh,fresh,fresh]
  status=fresh_bounded_read

adapter_sample_time_laundering:
  accepted=fresh_bounded_read
  revision_unchanged=true

adapter_ttl_laundering:
  original=degraded_fail_closed
  accepted=fresh_bounded_read
```

같은 run은 다음 collateral failures도 기록했다.

- raw path/revision secret가 adapter receipt에 남음;
- source payload가 그대로인데 unbound goal digest가 바뀐 injection이 승인됨;
- `ContinuousSelf` masquerade subclass가 읽기 중 write side effect를
  일으켰는데도 `fresh_bounded_read`로 승인됨.

Command/output은 로컬 Codex session log
`rollout-2026-07-26T11-24-45-019f9c3d-3874-7302-bd40-ed2cdf40b005.jsonl`,
2026-07-26T02:29:21.461Z에 남아 있다.

기존 `test_file_mtime_cannot_launder_old_semantic_sample_timestamps`는 file
mtime만 freshness 근거에서 제외한다. Caller clock, caller TTL, semantic
timestamp owner authenticity는 검사하지 않는다. Module도 limitation으로
`source_digests_not_raw_value_attestation`을 인정하면서 더 강하게 들리는
`fresh_bounded_read` 상태를 발급했다.

### 5.2 분류, 회수 가치, 처분

이 문제는 timestamp 비교 하나를 고치는 것으로 해결되지 않는다. Trusted
clock/TTL policy와 source owner가 발급한 observation이 필요하다.
따라서 freshness authority는 **설계 RED**다. Subclass exact-type과
redaction은 별도의 좁은 결함이지만, 이를 고쳐도 주 RED는 남는다.

회수할 가치가 있는 부분:

- two-pass revision/payload 안정성 검사
- missing, unavailable, unversioned, stale, future, inconsistent의 fail-closed
  상태
- exact projection, bounded file read, lock discipline
- digest-only/privacy 계약과 negative fixtures

회수하면 안 되는 부분:

- caller가 고르는 clock과 TTL
- owner-unbound semantic timestamp
- 현재의 `fresh_bounded_read` 권위 주장
- 현재 builder/adapter 전체를 green foundation으로 취급하는 것

F3는 `stash@{2}` 안의 일부다. **Stash 전체를 pop/commit하지 않는다.**
문서 리뷰까지 forensic reference로 유지한 뒤 별도 승인으로 drop하고,
유용한 validator와 tests는 향후 owner-bound source interface 위에
수동 재구성하는 것이 맞다.

## 6. F4 — metabolic and AUT-0 observation

Prototype blobs:

- `59add879196f86003e57b11ece2c5bc0c997366c`
  — `co_metabolic_observer.py`
- `32d2216726b6e2c0f982a3678e6f1b8eb4eaa3eb`
  — `test_co_metabolic_observer.py`

### 6.1 결정적 adversarial RED

Public builder는 동일 caller에게서 detached raw snapshot, `source_bindings`,
`read_at_ns`를 모두 받는다. `_payloads()`는 declared availability와 snapshot
presence, 필드 shape만 검사한다. `_f1_source_stamps()`는 caller가 제출한
다음 값을 그대로 F1 stamp에 복사한다.

- `state`
- `instance_id`
- `revision`
- `sampled_at_ns`
- `max_age_ns`

Payload digest만 locally 계산된다. Strict adapter도 같은 caller-provided
bindings와 snapshots에서 receipt를 다시 만들기 때문에 일관되게 거짓말한
caller를 구별하지 못한다.

실제 probe는 AUT-0 binding에 다음 값을 넣었다.

```text
instance_id='bearer-looking-lease-secret'
revision='caller-forged-revision'
sampled_at_ns=1000
max_age_ns=0
```

Raw result:

```json
{
  "accepted": true,
  "freshness": "fresh",
  "instance_id": "bearer-looking-lease-secret",
  "profile_status": "fresh",
  "revision": "caller-forged-revision",
  "secret_marker_serialized": true
}
```

Command/output은 로컬 Codex subagent session log
`rollout-2026-07-26T11-16-38-019f9c35-c9eb-74c2-9e79-8ef396fd5f61.jsonl`,
2026-07-26T02:18:18.023Z–02:18:20.581Z에 남아 있다.

기존 tests는 malformed absence/presence, namespace override, authority
smuggling, forbidden raw fields, post-seal tampering은 막는다. 하지만 처음부터
모양이 정확한 거짓 binding은 막지 않는다. Positive fixture 자체도 네
owner의 version/time stamp를 test caller가 만들고 `fresh`를 기대한다.

### 6.2 분류, 회수 가치, 처분

이것은 F1의 `contract_profile_only_not_live_join` 한계를 가장 직접적으로
재현한 **설계 RED**다. Schema는 자기 caller를 인증할 수 없다.

회수할 가치가 있는 부분:

- 네 owner namespace의 비혼합 분리
- source별 payload whitelist와 exact shape 검사
- 기존 hormone source의 implicit merge 거부
- lease/path/secret redaction 의도와 negative fixtures
- advisory-only authority fence

회수하면 안 되는 부분:

- `_f1_source_stamps()`의 caller metadata trust
- 현재 builder/adapter의 “같은 입력으로 재생되면 verified” 모델
- fixture-created binding으로 freshness를 주장하는 positive tests

F4도 `stash@{2}`의 일부다. **Stash 전체를 pop/commit하지 않는다.**
문서 리뷰까지 forensic reference로 유지한 뒤 별도 승인으로 drop한다.

## 7. 공통 원인과 독립 결함

세 원래 RED는 완전히 독립적이지 않다.

```text
caller가 값과 metadata를 제출
        ↓
canonical schema/digest가 내부 정합성을 검사
        ↓
같은 caller-controlled context로 strict adapter가 재구성
        ↓
“재구성 가능”을 “실제 owner에게서 옴”으로 잘못 승격
```

공통 원인은 **source owner와 verifier 사이에 caller가 위조할 수 없는 결속이
없다**는 것이다.

| Failure | 공통 원인의 표현 | 별도 좁은 결함 |
|---|---|---|
| F1.1 | caller가 issuer registry와 verifier context까지 직접 구성 | 정상 production registry가 비어 있어 실사용 경로 없음 |
| F2 | caller가 terminal/context를 함께 re-seal 가능 | 초기 session equality 누락 |
| F3 | caller가 read clock·TTL을 선택하고 owner-unbound timestamp를 제출 | subclass exact-type, redaction, goal-binding 결함 |
| F4 | caller가 source binding 전체를 제출하고 같은 값으로 adapter를 재생 | well-formed secret identifier도 허용 |

따라서 “F1에 validation primitive 하나 추가”라는 방향은 맞았지만, 현재
F1.1은 그 primitive의 root of trust까지 caller와 같은 Python process 안의
importable object로 만들었다. 이 구현으로는 F2–F4 세 개를 고칠 수 없다.

## 8. Stash 최종 처분표

| Stash | 전체 revive 가치 | 부분 회수 | 지금 조치 | 최종 권고 |
|---|---|---|---|---|
| `d90a0f14` F1.1 | 없음; false production trust primitive | context/replay/freshness/redaction 계약 아이디어 | **KEEP, no pop/commit** | 문서 승인 후 **DROP** |
| `8e13d331` F2 session fix | 없음; 대부분 중복이며 F2 전체 RED | 2줄 equality guard + 3 tests, 일부 observer schema | **KEEP, no pop/commit** | 문서 승인 후 **DROP** |
| `9cc3d8d8` F2–F4 | 없음; known-RED monolith와 production response patch 혼합 | source별 validator, two-pass checks, namespace/redaction tests | **KEEP, no pop/commit** | 문서 승인 후 **DROP** |

“참고용으로 pop해서 commit”은 세 개 모두 부적절하다. Known-RED
prototype과 green-looking tests가 main history에 들어가면 이후 census에서
존재하는 코드를 sealed foundation으로 오인하기 쉽다. 필요한 부분은 향후
승인된 새 설계에서 blob hash와 이 문서를 근거로 수동 이식할 수 있다.

이번 작업에서는 stash를 drop하지 않았다. 원본이 유일한 forensic source인
상태에서 사용자 리뷰 전에 파괴하는 것도 적절하지 않기 때문이다.

## 9. CO-C0 현재 경계와 재개 조건

현재 정직한 경계는 다음과 같다.

- F1 commit은 closed contract profile로 남는다.
- F1은 live source join이나 provenance attestation이 아니다.
- F1.1, F2, F3, F4는 shipped code가 아니며 sealed mechanism도 아니다.
- CO-C0 F5/F6의 전제였던 F2–F4 GREEN은 충족되지 않았다.
- CO-C0 capability lift는 측정되지 않았다.

CO-C0을 다시 열 경우 최소한 다음을 implementation 전에
사전등록해야 한다.

1. caller가 production issuer, registry, clock, TTL, verification context를
   만들 수 없는 명시적 trust boundary;
2. 실제 source owner가 발급한 observation만 받는 adapter interface;
3. F1.1 root-forgery, F2 co-reseal, F3 clock/TTL laundering, F4 well-formed
   false binding의 네 고정 adversarial probes;
4. direct mismatch와 internal consistency를 mechanism 증거로, live behavior
   또는 benchmark 변화를 capability 증거로 분리하는 판정표;
5. 네 adversarial probe 중 하나라도 승인되면 해당 단위를 RED로 끝내는
   no-go 기준.

그 전에는 field 수, test pass 수, receipt digest, observer firing 증가를
CO-C0 진전으로 계산하면 안 된다.
