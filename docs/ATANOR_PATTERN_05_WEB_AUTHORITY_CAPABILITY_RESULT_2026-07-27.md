# Pattern #5 web-authority capability result

상태: **CAPABILITY_LIFT_CONFIRMED**

## 측정 경계

이 결과는 고정된 18개 합성 row를 실제 `compose_web_answer` 답변 경로에 넣어, caller가
`provider` 문자열로 권위를 위조하는 경우와 정상 authoritative/single-source 경우를
구별하는 능력만 측정한다. 검색 retrieval, 일반 추론, 공개 벤치마크, E5, 콘텐츠
진위 인증, 프로덕션 기본값 전환은 주장하지 않는다.

OFF는 `bc5cccde42080a784f490ebbb53414cf7ec45131`, ON은
`e94d1c1e934554fad7ed4cb54a0d0fcdccb6ff0a`의 봉인된
`apps/api/app/services/web_search.py`를 사용했다. 각 조건은 fresh minimal Git
archive와 fresh subprocess에서 실행했고, network를 차단하고 provider/API credential과
`ATANOR_*` 환경변수를 제거했다. 18개 각 항목은 OFF와 ON에서 정확히 한 번씩만
counterbalanced 순서로 실행됐다.

## 사전등록 gate와 결과

| 지표 | OFF | ON | 사전등록 판정 |
|---|---:|---:|---|
| false assertion | 6/6 | 0/6 | 최대 0, 절대율 감소 1.0 — PASS |
| wrong-source adoption | 6/6 | 0/6 | 최대 0, 절대율 감소 1.0 — PASS |
| disposition accuracy | 12/18 (66.7%) | 18/18 (100%) | 최소 18/18, lift 최소 0.30 — PASS |
| 정상 authoritative accept | 6/6 | 6/6 | 최소 6/6 — PASS |
| 정상 single-source hedge | 6/6 | 6/6 | 최소 6/6 — PASS |

정상 accept와 hedge 회귀는 없었고, worker error는 0이었다. 후보·데이터셋·평가기
digest의 실행 전후 동일성, OFF/ON block identity, 각 항목 1회 실행, 봉인 commit
동일성도 모두 통과했다.

## 봉인 근거

- evaluator seal commit: `f818880587dd0ff1971d6692c1db0310f341c3aa`
- embedded report digest: `643354e55157edd8537c6a719a8af570d4e1ff778d58582edd50809604f04281`
- raw report: `reports/benchmarks/pattern_05_web_authority_capability_v1_20260727.json`
- write-once attempt receipt:
  `reports/benchmarks/pattern_05_web_authority_capability_v1_20260727.attempt.json`
- mechanical retry: 0
- production default changed: false

## 최종 판정

Pattern #5의 URL-host 결속은 이 고정 live-answer 표본에서 caller-supplied provider에
의한 허위 권위 채택과 false assertion을 제거하면서 정상 accept와 hedge를 보존했다.
따라서 이 좁은 discrimination capability에는 양성 신호가 있다. 이 결과를 일반적인
사실판별 능력이나 전체 모델 성능 향상으로 확장 해석하지 않는다.
