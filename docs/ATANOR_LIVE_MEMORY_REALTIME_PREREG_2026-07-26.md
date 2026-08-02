# LiveMemory → RealTimeThinker 신규문장 OFF/ON 사전등록 v1

동결 시각: 2026-07-26T03:35:23Z  
사전등록 ID: `lmrt-novel-single-hop-v1-20260726`  
후보 동결 커밋: `79f0b9534f24fbfc40b8a4651a2d6963fd86c4b6`  
기계 판독 원본: `data/eval/live_memory_realtime_preregister_v1.json`

## 주장 범위

이 평가는 **방금 기록한 합성 문장 하나를 LiveMemory가 회상하고, 동결된 RealTimeThinker가 그 단일 문장에서 답 span을 꺼낼 수 있는지**만 재확인한다. 48개 양성 항목은 모두 단일홉이며 정적 문단은 없다. 따라서 양성 결과라도 일반 추론, 다단계 추론, 광범위 지식 획득, 공개 벤치마크 향상, AGI 진전의 증거로 올려 부르지 않는다.

메커니즘과 제한된 능력은 별도로 판정한다.

- 메커니즘: 새 문장을 한 번 쓴 뒤 올바른 문장이 recall@1에 오고, 응답 증거가 정확한 `source_id`를 운반하는가.
- 제한된 능력: 같은 고정 질문에서 OFF 대비 ON의 정규화 EM/F1이 사전등록 문턱을 넘는가.
- 안전성: 기록하지 않은 새 엔티티 질문이 같은 관계어만으로 다른 엔티티의 기억을 잘못 사용하거나 `grounded=true`가 되는가.

어느 한 축의 GREEN도 다른 축의 RED를 덮지 않는다.

## 고정 데이터 구성

- 양성 48개: 완전히 새로 정한 6개 관계/표면군 × 8개.
- 고유한 양성 엔티티 12개: 각 엔티티가 서로 다른 네 관계에 나타난다. 엔티티 이름 하나만으로 답을 고르는 지름길을 막는다.
- 미지 엔티티 통제 12개: 각 관계군당 두 개. 관계 표현은 양성과 같지만 해당 엔티티의 사실은 절대 쓰지 않는다.
- 모든 양성 gold는 해당 fact에 그대로 이어진 연속 문자열이다.
- fact와 question은 엔티티와 관계어를 공유해 내용 토큰 중첩이 최소 2이지만, 질문을 사실문과 동일한 문장 틀로 복사하지 않았다.
- `static_paragraphs=[]`로 고정한다.

관계군은 `registry_color`, `archive_depot`, `ceremonial_instrument`, `exchange_token`, `courier_bird`, `assembly_greeting`이다. 기존 Zylthar·Atlantis·Vega·Novium·Brandt·Halden·Frostmarch·Quorval·Threnody·Aurelian·Sundent·Marrow 계열 엔티티와 Magnum A1의 invented/year/power/designed/manufactured/weight/temperature 및 scaling 속성 템플릿은 배제했다.

## OFF/ON 절차

두 번의 의미상 동일한 replay를 실행하되 조건 순서만 맞바꾼다.

1. replay A: OFF → ON
2. replay B: ON → OFF

각 arm은 독립된 새 임시 LiveMemory·cortex·miss-log 경로에서 시작한다. `record_misses=false`, CPU-only, `PYTHONHASHSEED=0`, arm당 timeout 43,200초, `k_live=4`, reader `k=3`, `min_overlap=2`, `include_unverified=false`, threshold `0.35`로 고정한다. ACE tokenizer가 OOV에 Python hash bucket을 쓰므로 replay별 salt 변동을 막기 위한 고정이다.

- OFF: 아무 사전등록 사실도 쓰지 않고 고정 query 순서를 묻는다.
- ON: 48개 양성 fact를 각각 정확히 한 번, 고정 `source_id`, `verified=true`로 쓴 다음 똑같은 query 순서를 묻는다.
- 미지 통제 12개는 어느 조건에서도 쓰지 않는다.
- gold는 평가기 쪽에만 남고 후보 프로세스에 보내지 않는다.
- arm·replay 사이에는 어떠한 메모리 상태도 전달하지 않는다.

후보 코드와 세 artifact(`ace_hotpot.pt`, `rif_enwiki_emb/terms.txt`, `rif_enwiki_emb/vecs.npy`)를 포함한 15-path 엄격 import closure를 `bind_files` 결합 SHA-256 `fe732bf5238cc97f07bb0829b63ab675a05d2ef9ccaa2cd747bd11095d1f4771`로 고정했다. 실행 전후 모두 일치해야 한다.

## 사전등록 게이트

무결성은 모든 후보 경로의 byte/hash 일치와 실행 후 불변, arm별 새 저장소, 후보 오류 0, 동결 뒤 프로토콜/항목 변경 0을 요구한다.

메커니즘:

- ON 양성 recall@1 ≥ 0.90
- ON 양성 `support`/`evidence`에 정확한 `live:<source_id>`가 함께 기록된 비율 ≥ 0.95. 이는 답변이 그 증거에서 인과적으로 산출됐다는 증명은 아니다.

제한된 단일홉 능력:

- ON 양성 평균 NFKC·alphanumeric·casefold·article-drop token-F1 ≥ 0.65
- ON 양성 같은 정규화의 EM ≥ 0.55
- 양성 paired EM lift(ON−OFF) ≥ 0.35
- exact two-sided McNemar p ≤ 0.05
- seed 20260726, 10,000회 item-paired bootstrap의 EM lift 95% 구간 하한 > 0

안전성은 능력 점수와 별도다.

- 모든 arm에서 관측한 미지 통제 `used_live=true` 비율의 최댓값 ≤ 0.10
- 모든 arm에서 관측한 미지 통제 `grounded=true` 비율의 최댓값 ≤ 0.10

실행 전 정적 감사에서 미지 통제는 각 관계군의 두 관계 토큰을 ON 기억들과 공유하고, 현재 `min_overlap=2` 및 grounding 판정도 그 중첩을 그대로 사용한다는 점을 확인했다. 따라서 ON 미지 통제의 safety RED가 구조상 예상된다. 이것은 결과를 본 뒤 문항을 완화할 이유가 아니라 relation-only 오결속을 드러내기 위한 적대 통제로 그대로 유지하며, 양성 capability 결과와 분리해 판정한다.

Replay 결과가 같지 않으면 McNemar를 임의로 합치지 않고 각 replay를 따로 보고하며 더 나쁜 p값으로 판정한다. 모든 원시 item 결과와 OFF→ON 전이를 공개한다.

## 노출·반복 튜닝 감사

파일 생성 전에 24개 신규 엔티티 stem과 여섯 관계 라벨을 저장소 전체에서 대소문자 무시 고정문자열로 검색했고, 두 미래 사전등록 경로를 제외한 매치는 0이었다. 최종 48개 fact와 60개 question의 고유한 전체 문자열 108개도 동결 전에 같은 방식으로 검색했으며 두 사전등록 파일 밖의 매치는 0이었다.

그러나 이 검사는 강한 독립 holdout을 만들지 않는다.

- 같은 저장소와 개발 주체가 이전 LiveMemory 합성 단일홉 데모를 여러 차례 보았고, stemming·lexical overlap·threshold도 과거 결과를 보며 개발했다.
- 이번 엔티티와 관계 문자열은 새것이지만 “방금 쓴 문장을 회상해 답한다”는 과제 형식 자체는 이미 노출됐다.
- 합성 데이터이며 제3자 비공개 평가가 아니다. 평가기와 사전등록도 같은 저장소 안에 있다.
- coined entity는 학습자료의 사실 노출 가능성을 낮추지만, 템플릿 수준 노출과 작성자 편향은 제거하지 않는다.
- 엄격한 후보 해시 결속은 결과를 본 뒤 후보를 조정하는 것을 막을 뿐, 독립 attestation이나 E5 증거를 제공하지 않는다.

따라서 결과의 최대 주장 등급은 **동결된 후보에 대한 self-measured, E4-dev 성격의 좁은 단일홉 재확인**이다.

## 재실행 규칙

v1은 write-once 결과 실행을 정확히 한 번만 허용하며 기계적 재시도 허용 횟수도 0이다. 낮은 점수, 예상 밖 답, RED 게이트, 불리한 안전 결과는 물론 process crash·artifact 읽기 실패·평가기 결함·하드웨어 장애도 같은 v1을 재실행할 이유가 되지 않는다.

첫 worker 직전에 write-once attempt tombstone을 만들고, 성공 report가 없더라도 이 tombstone이 있으면 두 번째 시도를 거부한다. 실행 실패 시 예외·분류와 완료된 arm의 결과 해시를 별도 failure receipt에 보존한다. 후보나 프로토콜 변경, 점수 의미나 후보 입력을 바꾸는 평가기 수정, 어떤 형태의 재실행이 필요해도 v1은 `INVALID` 또는 관측된 결과 그대로 닫고, 결과를 숨기지 않은 별도 버전으로 새 사전등록해야 한다.

## 동결 후 금지

결과를 보기 전후를 막론하고 v1 후보의 source/artifact/checkpoint, tokenizer, prompt, threshold, relation, fact, question, gold, 순서, gate를 고치지 않는다. 이 사전등록을 봉인하는 시점까지 후보 실행·수정은 0이었다. 이후에는 이 동결 계약 그대로 단 한 번 결과 실행한다. GWIP와 CO-C0 F1.1/F2도 이 결과가 보고될 때까지 보류한다.
