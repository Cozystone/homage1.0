# 멀티프로세스 샤딩 아키텍처 (분할 후 병합) — 프로토타입 설계

작성: 2026-07-11. 목적: 학습(지식+식단) 처리량을 **GIL 없는 N-프로세스 병렬**로 2~4배 가속.
현 상태: 단일 학습기 사이드카(:8509)는 틱당 ~19초 CPU 게이트에 묶여 있고, 파이썬 GIL 때문에
in-process 스레드로는 병렬화가 안 됨. 식단 부스터는 게이트를 건너뛰는 값싼 ~2배였고, **지식 게이트까지
가속하려면 진짜 프로세스 병렬이 필요**하다. 핵심 위험은 `narrative_corpus.jsonl`·후보 스토어의
**단일 라이터 계약** — 이 설계는 그걸 위반하지 않는 "분할 후 병합"으로 안전하게 N배를 낸다.

## 원리: 각 프로세스가 자기 파일만 소유 (write 경합 원천 제거)

```
        ┌─ shard_0 (proc) ─ fetch→gate→ candidate_store.shard0/  +  corpus.shard0.jsonl
route → ├─ shard_1 (proc) ─ fetch→gate→ candidate_store.shard1/  +  corpus.shard1.jsonl
(split) ├─ shard_2 (proc) ─ fetch→gate→ candidate_store.shard2/  +  corpus.shard2.jsonl
        └─ shard_N ...
                                    │
              (read-side union) ────┴──→ 읽기: corpus_tail/stats = glob(corpus.shard*.jsonl) 합집합
              (offline compactor) ─────→ 주기적 병합: 샤드 → main + 전역 dedup (경합 없음, 오프라인)
```

**단일 라이터 유지**: 각 샤드 워커는 자기 번호의 파일에만 append. 두 프로세스가 같은 파일을 쓰지 않음 →
계약 위반 0. 읽기(corpus_tail/stats/answer_bridge)는 여러 파일을 union할 뿐(락 불필요, append-only 안전).

## SPLIT 전략 (작업 분할)

작업 중복(두 워커가 같은 위키 문서 학습)을 피하는 3안, 단순→정교 순:
- **A. 독립 랜덤 (기본, 프로토타입)**: 각 워커가 자기 위키 랜덤 fetch. 중복률 낮음(위키 문서 6M+), dedup가
  꼬리에서 정리. 코디네이션 0 — 가장 안전하고 빠른 착수.
- **B. 해시 분할**: 워커 i는 `hash(title) % N == i`인 문서만 채택. 중복 0이나 fetch 낭비(버린 문서) 발생.
- **C. 작업 큐**: 중앙 큐(SQLite/파일)에서 각 워커가 topic을 pop. 중복 0 + 낭비 0이나 큐가 단일 라이터 병목
  재도입 — 프로토타입엔 과함. **판정: A로 시작, 필요 시 C로 승격.**

## MERGE 전략 (읽기 병합 + 오프라인 압축)

1. **읽기 병합 (즉시, 락 없음)**: `narrative_corpus.corpus_tail/stats`가 `narrative_corpus*.jsonl`
   글롭을 union. 레지스터 균형 샘플링(이미 구현)은 union 위에서 그대로 동작. 샤드 간 소수 중복 허용.
2. **오프라인 압축기 (주기적, 단일 프로세스)**: `scripts/corpus_compactor.py` — 모든 샤드를 main으로
   병합하며 전역 hash dedup + 회전 상한 적용, 샤드는 truncate. 학습 중단 없이 동작(append-only 읽기).
3. **후보 병합 (승격 재개 시)**: 프로모션이 켜질 때만, 압축기가 샤드 후보 스토어들을 k-소스 합의로 병합.
   현재 프로모션은 OFF이므로 이 경로는 미사용(회귀 방지, [[diet-flood-p0-regression]]).

## 안전 (기존 가드와 정합)

- **프로모션 OFF 유지** — 샤드는 코퍼스(표면 언어)+후보만 늘림, 답변팩 무관.
- **P0 파수꾼(:8511)** — 회귀 즉시 `LEARNING_FROZEN`; 모든 샤드 워커가 이 플래그 체크 → 일괄 동결.
- **위키 예의** — N 워커 × ~2 req/s = 2N req/s. N≤4면 ~8 req/s(허용 범위). 연락처 UA 유지.
- **메모리** — 워커별 후보 스토어 = 워커별 RSS. 워치독 rss_limit로 각 캡. N=3~4가 스위트스폿(코어 수).

## 배선 (구현 시)

- `scripts/learner_shard.py <shard_id> <N>` — learner_daemon의 샤드판(자기 파일 경로, freeze 체크).
- `narrative_corpus.py` — CORPUS를 글롭 union으로(쓰기는 프로세스별 `CORPUS.shard{id}.jsonl`).
- `scripts/corpus_compactor.py` — 오프라인 병합+dedup+회전, 워치독 주기 서비스 또는 압축 틱.
- `engine_watchdog.py` — atanor-learner-shard-{0..N} 서비스 N개 등록(:8509,:8512,:8513…), rss_limit 각.
- 헬스: 각 샤드 워커 자기 포트.

## 기대 효과 & 판정

- 독립 랜덤(A) + N=3: GIL-free ⇒ 지식+식단 ~**3배**(현 1480→~4400줄/h 식단 상한, 지식 게이트도 3배).
  15만 줄 ETA(부스터 ~2일) → **~16시간**. 위키 예의·CPU 코어가 실질 상한.
- **판정: 프로토타입은 A(독립 랜덤) + 읽기 union + 오프라인 압축기.** 계약 위반 0, 가드 전부 유지,
  실패 시 샤드 하나만 꺼도 됨(격리).

## 구현 완료 (2026-07-11, 기본 OFF — 라이브 무변경)

프로토타입 **SHIPPED + 테스트**(라이브 미기동, 기본 OFF):
- `packages/autonomy_kernel/narrative_corpus.py` — 쓰기: `ATANOR_CORPUS_SHARD=<id>` → `narrative_corpus.shard<id>.jsonl`(프로세스별 소유). 읽기: `_read_paths()`가 main+shard 글롭 union, `_tail_entries()`가 ISO 타임스탬프로 병합. dedup(`_load_hashes`)·stats도 union. 샤드 없으면 **바이트 동일**(실측: read_paths=[main], 10,626줄, tail/stats 정상).
- `scripts/corpus_compactor.py` — 오프라인 MERGE: 샤드→main 전역 hash dedup + 회전 + 스냅샷-안전 truncate(압축 중 append된 줄 보존), 멱등. `--dry-run` 실데이터 안전 no-op 확인.
- `scripts/learner_shard.py <id> <N>` — 샤드 워커: 코퍼스+후보스토어(`ATANOR_CANDIDATE_STORE_PATH`) 쓰기 격리, health 포트 8520+id(충돌 없음), 공유 freeze 파일 존중.
- `scripts/engine_watchdog.py` — **게이트 등록**: `ATANOR_LEARNER_SHARDS=N`(N≥2)일 때만 단일 :8509 학습기를 N개 샤드(:8520+i, rss 4GB 각, PROMOTE_EVERY=0)로 교체. 미설정=SERVICES 바이트 동일(실측 검증). main/loop은 `__main__` 가드.
- 테스트: `test_narrative_corpus_sharding.py` 5종(쓰기 격리·union 읽기·교차샤드 dedup·압축기 병합+멱등·기본 무변경), autonomy_kernel 74 green.

**착수(사장님 1-스텝)**: 워치독 env `ATANOR_LEARNER_SHARDS=3` 설정 후 재기동 → 3 샤드 GIL-free, ~3배(식단 15만 ETA ~16h). 압축기는 주기 실행(`python scripts/corpus_compactor.py`)으로 샤드→main 병합. **BINDING 유지**: 프로모션 OFF, P0 파수꾼 freeze 전 샤드 일괄 존중, 위키 예의 2N req/s(N≤4). 라이브 기동은 ~16h 프로덕션 쓰기이므로 사장님 명시 go 후.

관련: [[diet-acceleration-150k]] [[diet-flood-p0-regression]] [[store-layer-topology]] [[engine-memory-killloop-fix]] [[parallel-tracks-plan]].
