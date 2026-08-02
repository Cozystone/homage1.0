# LiveMemory → RealTimeThinker 신규 문장 OFF/ON 사전등록 v2

동결 시각: `2026-07-26T03:58:11Z`  
사전등록 ID: `lmrt-novel-single-hop-v2-20260726`  
기계 판독 원본: `data/eval/live_memory_realtime_preregister_v2.json`

## 주장 범위

이 평가는 새 합성 문장 하나를 LiveMemory에 한 번 기록했을 때 RealTimeThinker가 그 문장의 단일홉 답 span을 즉시 회상하는지를 재확인한다. 일반 추론, 다단계 추론, 광범위한 지식 습득, 장기 학습, 공개 벤치마크 향상 또는 AGI 진전을 주장하지 않는다. 결과는 독립 서명이 없는 로컬 개발 측정이며 E5 증거가 아니다.

mechanism과 좁은 capability는 분리해 판정한다.

- mechanism: ON에서 등록 사실이 recall@1에 나타나고, 답변 증거가 정확한 `source_id`를 동반하는가.
- 좁은 capability: 같은 고정 질문에 대한 OFF 대비 ON의 EM/F1 상승이 사전등록 gate를 통과하는가.
- safety: 등록하지 않은 관계 유사 질문에 잘못 `used_live=true` 또는 `grounded=true`를 부여하지 않는가.

## v1 INVALID와 동일 항목 재사용

v1의 write-once 실행은 첫 OFF worker가 checkpoint를 역직렬화하는 동안 기계적으로 종료되어 `INVALID`로 닫혔다. 완료된 arm은 `0 / 4`였고, candidate가 사전등록 question에 답한 기록, item score, aggregate metric은 모두 0건이다.

Windows subprocess에서 CPU-only 의도를 전달하려고 사용한 `CUDA_VISIBLE_DEVICES=""`가 PyTorch의 가시성·availability 판정을 일관되게 강제하지 못했고, checkpoint 역직렬화 경로가 CUDA device 0을 요구하며 종료됐다. 완료 arm 0건과 실제 예외는 아래 v1 failure receipt에 봉인되어 있다.

- `reports/benchmarks/live_memory_realtime_lmrt-novel-single-hop-v1-20260726.attempt.json`
- `reports/benchmarks/live_memory_realtime_lmrt-novel-single-hop-v1-20260726.failure.json`

따라서 v2는 v1의 48개 양성 항목과 12개 unknown control을 그대로 재사용한다. 재사용의 정당성은 v1에서 candidate/question 실행 및 채점이 한 건도 발생하지 않아 답·오답·점수·gate 결과를 엿볼 결과 자체가 없었다는 데 한정된다. v1 failure 원인 외의 item-level 결과를 본 적이 없으며, v2 작성 중 실제 candidate 또는 question 실행도 하지 않았다.

## v1에서 유지한 동결 내용

다음은 v1과 의미 및 바이트 내용이 동일하다.

- 48개 양성 항목의 `family`, `fact`, `question`, `gold`, `source_id`
- 12개 unknown control의 `family`, `question`
- candidate path 15개, candidate digest `fe732bf5238cc97f07bb0829b63ab675a05d2ef9ccaa2cd747bd11095d1f4771`, checkpoint path
- OFF/ON replay 순서, candidate config, scoring 규칙, mechanism/capability/safety gate
- rerun 정책, claim boundary, exposure audit, `static_paragraphs=[]`

v2에서 바뀐 값은 아래 세 종류뿐이다.

1. `preregistration_id`를 `lmrt-novel-single-hop-v2-20260726`로 변경
2. `frozen_at`을 새 UTC 시각으로 변경
3. 새 preregistration ID를 포함하는 content-derived `item_id` 60개를 재계산

`source_id` 안의 `v1` 문자열도 사실과 출처 결속을 보존하기 위해 변경하지 않았다.

## CPU-only 장치 정책

사전등록의 `device_policy`는 계속 `cpu_only`다. v2 evaluator는 Windows subprocess에서 CUDA 가시성을 끄기 위해 `CUDA_VISIBLE_DEVICES=-1`을 사용한다. 이는 동일한 CPU-only 정책을 Windows에서 실행 가능하게 전달하는 기계적 교정 설명이며, candidate, question, gold, protocol, gate 또는 scoring의 변경이 아니다.

## 실행 전 안전통제 감사

12개 unknown control은 각 관계군의 두 관계 토큰을 ON 기억들과 공유한다. 현재 고정값인 `min_overlap=2`와 grounding 판정은 이 관계 중첩을 사용하므로, ON unknown에서 `used_live=true` 및 `grounded=true`가 발생해 safety gate가 RED가 될 가능성이 구조적으로 높다. 이것은 결과를 본 뒤 문항이나 threshold를 완화할 이유가 아니다. relation-only 오결속을 드러내는 적대 통제를 그대로 유지하고, 양성 항목의 mechanism 및 좁은 capability 결과와 분리해 판정한다.

## 노출·반복 튜닝 감사

이 평가의 노출 위험은 여전히 `very_high`다.

- 같은 개발팀과 저장소가 이전 LiveMemory 단일홉 합성 데모를 여러 번 보았다.
- lexical stemming, overlap threshold, recall 동작은 과거 결과를 보며 이미 조정되었다.
- 이번 고유명사와 정확한 문장은 새 것이지만, “한 문장 기록 후 같은 관계를 묻는 즉시 회상” 형식은 노출되어 있다.
- 항목은 같은 공개 저장소에 있으며 hidden holdout이 아니다.
- evaluator는 독립 심판이 아니고 checksum 결속은 외부 attestation이 아니다.

v1이 0-scored INVALID였다는 사실은 v2의 항목 결과 노출을 만들지 않았지만, 위의 과거 형식 노출과 반복 튜닝 위험을 줄이지도 않는다.

## 결과 실행 전 상태

v2는 result-blind 상태에서 동결되었다. 이 문서와 JSON을 작성하는 동안 허용한 검증은 JSON 스키마, 48+12 census, content-derived ID, candidate digest 결속을 확인하는 `validate` dry-run뿐이다. 실제 `run`, candidate checkpoint 로드, question 질의, OFF/ON 점수 산출은 수행하지 않았다.

v2 결과 실행은 별도 write-once 실행이다. 결과를 본 뒤 candidate, protocol, item, gate 또는 scoring을 조정해 같은 v2를 다시 실행하는 것은 금지된다.
