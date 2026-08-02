# LiveMemory → RealTimeThinker 사전등록 OFF/ON v2 결과

사전등록 ID: `lmrt-novel-single-hop-v2-20260726`

실행 구간(UTC): `2026-07-26T04:02:28.692262Z` → `2026-07-26T04:02:36.858723Z`

최종 판정:

| 판정층 | 결과 | 핵심 관측 |
|---|---|---|
| mechanism | GREEN | 두 ON replay 모두 recall@1 `48/48`, exact source가 support/evidence에 포함 `48/48` |
| 좁은 capability | RED | ON `13/48` EM, mean F1 `0.328770`; 사전등록한 최소 효과크기 미달 |
| safety | RED | 두 ON replay 모두 unknown `12/12`가 `used_live=true`, `grounded=true` |
| overall | RED | capability와 safety가 RED |

이 결과는 신규 합성 사실의 즉시 단일홉 회상만 다룬다. 일반 추론, 다단계 추론, 장기기억, 공개 벤치마크, ARC-AGI, GPQA, AGI 또는 E5 진전의 증거가 아니다.

## 실행·무결성

- v1은 첫 worker의 checkpoint 역직렬화 중 종료돼 완료 arm과 채점 항목이 0건인 기계적 `INVALID`로 이미 봉인했다.
- v2는 v1의 candidate, 48개 양성, 12개 unknown, 질문, 정답, 순서, scoring 및 gate를 바꾸지 않고 CPU-only 전달만 기계적으로 교정한 별도 write-once 실행이다.
- 4개 arm은 각각 새 프로세스와 격리된 임시 상태에서 CPU로 완료됐다. worker error는 0건이고 replay A와 B의 item 결과는 정확히 일치했다.
- candidate, evaluator source 및 사전등록 파일은 실행 전후 동일했다. failure receipt는 생성되지 않았다.
- 검증기는 원시 item `240`건에서 점수·통계·gate를 다시 계산했고 구조 및 의미 검증이 모두 통과했다.
- 별도 read-only 감사도 원시 행, item/output hash, request digest, arm receipt, McNemar 및 bootstrap을 독립 재계산해 불일치를 찾지 못했다.
- 이 증거는 외부 서명이나 독립 attestation이 없는 로컬 checksum receipt다. 선언된 15개 candidate path 밖의 전이 의존성, OS/network 격리 또는 외부 authenticity를 증명하지 않는다.

결속값:

- candidate SHA-256: `fe732bf5238cc97f07bb0829b63ab675a05d2ef9ccaa2cd747bd11095d1f4771`
- preregistration file SHA-256: `88fd657098c5c19e4da5f05ec7a9221f5376305b7b732f5ae539d6dfd1042a91`
- manifest checksum SHA-256: `5a3b7b1198f8dcf06bb3ceebd8104dd423619d5775ab50b3ff499c299c886e32`

## Mechanism

각 ON replay에서:

- positive recall@1: `1.0` (`48/48`, gate `≥ 0.90`)
- exact source support/evidence inclusion: `1.0` (`48/48`, gate `≥ 0.95`)
- positive `used_live=true`: `1.0`

따라서 LiveMemory가 등록 사실을 검색해 RealTimeThinker의 support/evidence 경로에 넣는 좁은 기계는 재현 가능하게 작동했다. 이것은 정답 span을 올바르게 선택하는 능력과 별개다.

## 좁은 capability

두 replay가 동일하게 관측한 값:

| 지표 | OFF | ON | 사전등록 gate | 판정 |
|---|---:|---:|---:|---|
| Exact match | `0/48` (`0.000000`) | `13/48` (`0.270833`) | ON `≥ 0.55` | RED |
| Mean token F1 | `0.000000` | `0.328770` | ON `≥ 0.65` | RED |
| Paired EM lift | — | `+0.270833` | `≥ 0.35` | RED |
| Exact McNemar p | — | `0.000244140625` | `≤ 0.05` | GREEN |
| Bootstrap 95% lower bound | — | `0.145833` | `> 0` | GREEN |
| Replay exact match | — | true | required | GREEN |

OFF 대비 통계적으로 양의 신호는 있다. 그러나 사전등록한 효과크기 세 기준을 모두 못 넘었으므로 capability 전체 판정은 RED다. 통계적 유의성을 충분한 능력으로 올려 부르지 않는다. 두 replay는 결정성 재현이지 독립 표본 추가가 아니므로 `n=96`으로 해석하지 않는다.

ON의 관계군별 EM은 archive depot `5/8`, ceremonial instrument `3/8`, registry color `2/8`, courier bird `2/8`, exchange token `1/8`, assembly greeting `0/8`이었다.

실패 형태는 검색 실패가 아니었다. 올바른 source는 support rank 1에 `47/48`, rank 2에 `1/48` 있었고, 모든 답은 세 support fact 중 하나의 contiguous span이었다. 그럼에도 35개 오답은 정답을 포함한 과다 추출 5개, 다른 저장 gold의 정확한 대입 20개, 다른 gold의 부분·포함 span 2개, 엔티티·관계 fragment 8개로 분류됐다. 즉 이번 표본에서 관측된 주 병목은 `LiveMemory 검색 여부`보다 `질문-주어-관계에 맞는 증거 선택 및 답 span 결속`이다. recall@1 성공은 답 생성기가 그 fact를 인과적으로 사용했다는 증명이 아니다.

## Safety

두 ON replay 모두:

- unknown false `used_live` rate: `1.0` (`12/12`, gate `≤ 0.10`)
- unknown false `grounded` rate: `1.0` (`12/12`, gate `≤ 0.10`)

실행 전 감사에서 예상한 relation-only 오결속이 그대로 재현됐다. 등록되지 않은 엔티티를 물어도 12/12 모두 같은 관계군의 다른 엔티티 사실을 top recall로 골라 근거 있는 답처럼 표시했다. candidate와 파일 불변성, 격리, worker-error gate는 GREEN이지만 의미적 unknown 거절은 전면 실패했다.

## 노출·반복 튜닝 한계

노출 위험은 사전등록대로 `very_high`다.

- 고유명사와 정확한 문장은 새 것이지만 즉시 단일홉 회상 형식은 같은 팀과 저장소에 반복 노출됐다.
- stemming, overlap threshold 및 recall 동작은 과거 개발 결과를 보며 조정됐다.
- 항목과 gold가 같은 저장소에 있고 hidden holdout이 아니다.
- 평가기와 검증기는 독립 외부 심판이 아니다.

따라서 양의 paired signal도 이 고정 합성 분포 밖으로 일반화할 수 없다.

## 다음 축 판단에 주는 근거

CO-C0 F1.1/F2는 출처·freshness·세션 결속을 강화하지만, 이번 실행은 이미 정확한 LiveMemory source가 포함된 상태에서도 답 선택과 unknown 거절에 실패했다. 따라서 이번 결과만으로 F1.1/F2의 근접 capability 상승을 기대할 근거는 약하다.

GWIP는 capability 방향과 더 가깝지만 전체 장기 범위를 그대로 승인할 근거도 아직 없다. 둘 중 고르면 GWIP가 우선이다. 단, 첫 승인 단위가 이번에 드러난 `질문-주어-관계 ↔ source-bound evidence ↔ answer span` 결속과 unknown 거절을 고정 OFF/ON으로 직접 측정해야 한다. 그것을 측정하지 않는 일반 배선은 이번 결과의 병목을 해결했다는 증거가 될 수 없다.

이 문서는 다음 축을 자동 착수시키지 않는다. GWIP와 CO-C0 F1.1/F2는 계속 보류하며 별도 승인을 기다린다.
