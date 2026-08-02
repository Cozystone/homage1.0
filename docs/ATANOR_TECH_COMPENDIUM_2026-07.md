# ATANOR 기술 총람 (Tech Compendium) — 2026-07

> 내부 문서. 이 문서 하나로 "지금 ATANOR가 무엇이고, 어디까지 왔고, 왜 그렇게 설계했는지"를
> 새 기여자(사람이든 모델이든)가 재구성할 수 있어야 한다. 모든 수치는 실측이며 커밋으로 재현 가능하다.
> 마지막 대규모 스프린트: 2026-07-07 ~ 07-09 (Fable5 최종 구간).

---

## 0. 한 문단 정의

ATANOR는 **LLM을 쓰지 않는 그래프 네이티브 AI**다. 지식은 int32 컬럼나 트리플 스토어(약 2,600만 트리플)에
출처와 함께 쌓이고, 위상 공간(자체 훈련 64D RotatE-lite)이 소프트 검색을 **제안**하며, 기호 그래프가 모든
제안을 **검증**하고, 재귀 구문 실현기가 검증된 사실만으로 문장을 **합성**한다. 원칙은 하나로 요약된다:
**빠르게 제안하고(GPU/임베딩), 반드시 검증해서만(증거/기호) 승급하라.** 근거가 없으면 지어내지 않는다.

## 1. 지형 (물리 배치)

| 자산 | 위치 | 비고 |
|---|---|---|
| 정본 워크트리 | `C:\0.ASKIM ALL-VIN\27., ATANOR DEMO` (브랜치 `demo`) | 엔진·데이터·랜딩의 정본 |
| 개발 워크트리 | `24.Homage1.0` 등 | 같은 리포의 워크트리 |
| 엔진 | :8502 (FastAPI, `apps/api/app/main.py`) | 워치독이 재기동, cwd=27 |
| 데모 웹 | :3200 (Next.js dev) / Ultimate :3400 / SPLATRA :8010 | |
| 클라우드 브레인 | GCP VM `https://136.114.69.152.sslip.io` (Docker, 1GB) | ATANOR-Demo `demo` 브랜치에서 빌드, `atanor-data` 볼륨에 그래프 영속 |
| 랜딩 | `apps/landing/` → Vercel `atanor-liard.vercel.app` | 정적 + 브라우저 로컬 미니 ATANOR |
| 공개 리포 | github.com/Cozystone/ATANOR-Demo, /ATANOR | VM·랜딩의 소스 오브 트루스 |

운영 수칙: 벌크 적재/스토어 수술 전 **단일-writer**(워치독+엔진 정지). 스토어 절단·리셋·라이브 재시작은
**운영자 승인 필수**. 테스트는 `python -X utf8 -m pytest --import-mode=importlib`(환경성 사전실패 ~22개는 기저선).

## 2. 스토어 계층 — 진실의 물리학

- **TripleStore** (`packages/graph_scale/`): s/p/o/src 4개의 int32 `.col` 파일 + append-only TermDict.
  이 구조가 곧 COO 희소텐서다 — GPU 미러·샤딩·병합이 전부 이 동형성 위에서 성립한다.
  retract는 tombstone(가역·원장 기록). **대량 tombstone은 부적합**(파일 전체 로드) → 대량 수리는 읽기층에서.
- **적재**: turbo_ingest ~96만 rows/s, Arrow 해시커널+TSV 레인 3.0M rows/s(실측, 채택). 다음 병목=TermDict.
- **출처 태깅**: 모든 트리플에 src id. `legacy(0)` = 무출처 구세대 / `dbpedia:bulk`·`wikidata`·`type_alignment:*` =
  검증 출처 / `web:`·`mined:` = 원시 스크레이프. 이 세 층위가 신뢰 필터의 입력이다.
- **합의-증거 기계**: k-소스 합의 게이트(가변 k — 경합 실측 시 문턱 +1) + 격리 원장. 후보↔검증 분리는 전 레인 공통.

## 3. 위상 공간 계층 — 소프트 제안기

- `phase_space.py` / `gpu_phase_space.py`: 자체 훈련 RotatE-lite, 64차원. 전체 그래프(25.9M)가
  RTX 5080 VRAM에 606MB/0.25초로 미러됨.
- **실측 교훈**: 반발 항 `repel_at`은 상수가 아니라 `dim/2`여야 함(|sin| 거리 범위가 [0,dim]이라
  dim≥32에서 상수 반발이 미발화 — 0.96@8 → 0.28@64로 붕괴했던 원인).
- **아티팩트 규율**: Windows mmap 잠금 때문에 phases.npy 덮어쓰기 불가 → **버전 파일 + current.json 포인터,
  최신 mtime 승리**. 어의 레지스트리도 같은 방식을 상속했다.
- 소비자: `soft_resolve.typed_soft_match`(위상 제안 → 공유 is_a 부모 검증 생존), `phase_flow`(발화 흐름),
  브리지의 composed 레인. **제안은 절대 사실로 직행하지 않는다.**

## 4. 언어 계층 — 무한 표현 × 유한 진실

- **재귀 구문 실현기** (`packages/grounded_composer/recursive_realizer.py`, bb980032→1c15af97→f3d97c54):
  언어의 무한성은 확률이 아니라 **재귀**에서 온다(훔볼트). 폐쇄 구문 목록(관형절·접속·어미 = LAD 표면층,
  코드 허용 유일 지대) × 검증 사실의 재귀 합성. 안전성 한 줄: **output ⊆ closure(구문 ∪ 사실문자열)**.
  실측 결함 수리: 순환내포 가드 / 절별 자기 어미("세워졌입니다" 근절) / 비한글·숫자 머리명사 거부 /
  "나라 이름" 정밀 스트립(블랭킷 스트립이 "공식 명칭"을 파괴했던 사고 포함).
  라이브 합성 예: "대한민국은 수도가 서울특별시인, 인구 51,466,201의 동아시아에 위치한 … 나라이며, 면적은 100,295 km²입니다."
- **컴포저 배선**: `compose_from_facts`가 재귀 문장 1순위(사실 3+개 채택), 평면 체인 폴백,
  킬스위치 `ATANOR_RECURSIVE_REALIZER=0`.
- 표면 규정(어문 규범)은 LAD 표면층에만 — **지식은 그래프로, 절대 코드 테이블로 넣지 않는다** (2대 하드 룰).
- 유창성 독트린: 유창함 = 관계 다양성 × 담화 패턴. 새 술어에는 발화 프레임 동반.

## 5. 어의 질병 수리 — 1번 난제의 4단계 (전 단계 착지)

**진단**: 지식이 표면 문자열로 키잉되어 '물' 한 노드에 물/무렵/접미사가, 'capital'에 수도/자본/기둥머리가 섞임.
모든 서브시스템이 같은 병에 각자 가드를 세웠다. 실측으로 **2겹 구조** 확정: ①진짜 다의어(소수의 실어의)
②파싱 쓰레기(어떤 어의에도 속하지 않는 개별 거짓 엣지 — WordNet 흡인자 배치, in-degree 30,800~31,100 균일, legacy).

수리 순서(위반 금지)와 구현:
1. **신뢰 필터** `sense_trust_filter.py` (149273bc): 검증출처=즉시 신뢰 / 허브+legacy+generic in-degree(≥8,000)=격리.
   **허브 맥락이 load-bearing**: 같은 신호가 허브에선 쓰레기(capital is_a Animal), 비허브에선 실타입(피라냐 is_a Animal).
   **읽기 시점 적용**(`trusted_parents`) — tombstone 대량 부담 회피. capital 490→64.
2. **분할** `sense_partition.py`: 필터 생존 부모를 위상공명(soft)+판별적 조부모(hard)로 클러스터.
   sense 시그니처는 라벨링만(병합 라이선스로 쓰면 잡탕 — 실측). capital 64→42클러스터, 상업/행위자 19개 응집.
3. **어의별 폐포** `per_sense_closure_candidates` (f7788041): 2홉 폐포를 한 어의 클러스터 안으로 스코프.
   blind closure ~30% 오답의 구조적 해소 경로. PROPOSE 전용 — 승급은 증거 게이트.
4. **어의 키 읽기층** `sense_registry.py` (f7788041): 버전 아티팩트(registry_v + current.json).
   `senses_of` / `sense_scoped_parents(term, 문맥)` / `register_terms`(컷 밖 병소 타깃 등록).
   라이브 302허브 등록. **물리적 어의ID 컬럼 마이그레이션은 성능 최적화일 뿐**(의미 요건은 레지스트리가 충족) — 운영자 게이트.

잔여: 레지스트리 커버리지 확장(302/~32k 허브, 배치 런), 답변 레인의 `sense_scoped_parents` 소비 배선.

## 6. 학습 계층 — 규모는 연산이 아니라 진실이 병목

- **파생 가속기** `derivation_accelerator.py`: 이행 2홉 폐포 74만/s (GPU 폐포 1.55M 후보/s).
  **정직 정정**: 베이스 노이즈 위 blind closure는 ~30% 오답 → 자동 레인 기본 OFF, 수동 도구 유지.
  신뢰 성장 = 웹학습기 + 벌크 KG(+61만, 출처 태그). 스토어 절단은 운영자 승인 필수(1회 승인·실행: 25,263,997 기준선).
- **예산 신진대사** `metabolism.py` (b199cec8): 실측 RSS 지갑 → 학습기 자가 페이스 + 코르티솔 배선.
  1GB VM OOM의 구조적 재발 방지(earlyoom은 최후 방어).
- **자가정제**: 모순 소독(함수성 술어) + 분류 사이클 소독 + **가설 민팅**(질문만 발행 = 모델붕괴 면역).
- 지식학습기 v2: 질문 수준 whole-web 학습 + 링크 인용. 웹 구조 답변은 반드시 앵커(제목/주제) 또는 기권.

## 7. Brain Link 분산 계층 — 조 단위 확장 (4번 과제, 완결)

**산수**: 26M 엣지=0.6GB VRAM(실측) → 1조=24,000GB → 단일 VRAM 불가 → 피어 1,500대 @16GB.
렌더 토큰 경제를 그래프 엔진에 적용 — 그래프 op은 **정확 재현 가능**하므로 렌더링보다 강한 검증이 가능하다.

- `distributed_tensor_shard.py` (419f6e41): 개념키 라우팅(`_shard_for_key` — 주어 인접성이 한 샤드에),
  `ShardRouter._verify` = **검증자가 원시 슬라이스에서 독립 재계산**(피어 메서드 불신 — 조작된 degree_of를
  메서드 재호출로 검증하면 거짓말끼리 일치하는 결함을 실측으로 잡고 수리).
- `peer_shard_server.py` + `peer_transport.RemoteShard` (f7788041): 피어 1프로세스=슬라이스 npz+HTTP,
  전 요청 HMAC 서명(위조=403). RemoteShard가 TensorShard를 덕타이핑 → **라우터에 원격 분기 0줄**.
- **라이브 실증**: 실엣지 200만→8샤드 균형 분할 0.3s / 크로스-프로세스 라우팅 차수 5개념 전부 단일노드 일치·
  전부 검증 / 거짓 피어 독립 재계산으로 격리. v1=연산 오프로드(코디네이터가 정본 슬라이스 보유).
  잔여: 저장 오프로드(검증을 피어 중복/다수결로 — `_verify`의 reference만 교체), WAN 배포, peer_trust_guard 키 연결.
- 보안 스택: peer_trust_guard(암호신원+Sybil PoW+철회가능 격리), DoS 토큰버킷, 프롬프트 주입 경계, PII 격리.

## 8. 표면·제품 계층

- **미니 ATANOR** (`apps/landing/assets/mini_atanor.js` v3): 브라우저 로컬(팩+WASM 없음, 순수 JS) 엔진식
  파이프라인 — 개체/관계 스포팅, 담화 상태(CTX), 역엣지, 필러 제거. 랜딩이 곧 데모.
- **랜딩 사전예약** (2026-07-09): 다운로드 UI는 `#dl-archived` hidden 래퍼로 보관(래퍼 제거로 복원),
  그 자리에 사전예약 박스 — `POST /api/waitlist`(자체 VM 저장, 외부 폼 서비스 무사용, 순번 반환,
  실패 시 localStorage 보관→다음 방문 자동 재전송). 엔진 라우터 `apps/api/app/routers/waitlist.py`
  (이메일 검증·중복 병합·IP 시간당 6회·일일 2,000 상한, `data/waitlist/waitlist.jsonl`).
- 텍스트 세션 /chat + 답변별 인증서 PDF, 추론 투명 UI(thinking trace), AGORA Moltbook, Graph Hub 카트리지.
- 사업계획서: `scripts/build_business_plan_pdf.py` → `ATANOR_사업계획서.pdf` (흑백·검은표지·로고,
  2026.07 실측 반영. 로고 에셋은 `ATANOR-live-selfhood-scheduler/assets/`).

## 9. 실측 숫자판 (2026-07-09 기준)

| 항목 | 값 | 출처/커밋 |
|---|---|---|
| 지식 그래프 | ~25.9M 트리플 | 스토어 실측 (승인 절단 후 25,263,997 + 증분) |
| 봉인 홀드아웃 grounded QA | 92%, 날조 0 | 언어 완성도 배터리 2026-07 |
| 정직성 배터리 | 94% | 〃 |
| 멀티홉 합성 | 75%, 환각 0 | 합성대수 + is_a 백본 |
| 위상 링크 예측 | Hits@10 87.8% | 학습형 라우터/위상공간 |
| GPU 미러 | 25.9M → 606MB / 0.25s | RTX 5080, gpu_graph |
| 적재 | 0.96M rows/s (기본) / 3.0M rows/s (터보) | turbo_ingest |
| 파생 | 74만 후보/s (CPU) / 1.55M/s (GPU) | derivation_accelerator (자동 OFF) |
| 어의 필터 | capital 490→64 부모 | 149273bc |
| 분산 셔딩 | 2M/8샤드/0.3s, 크로스-프로세스 5/5 일치 | 419f6e41+f7788041 |
| 스위트 | graph_scale 131+1, brain_link 전송 7/7 | 2026-07-09 |

**정직 한계** (같은 무게로 기록): 커버리지는 프런티어 LLM보다 좁다. 산술·창의는 밀도 창발의 예외
(scale-emergence honest scope). 어의 레지스트리 커버리지 302/~32k. "~에 대해 알려줘" 라우트에
"위치한다입니다" 스플라이스 결함 잔존. 잔여 오답의 주류 = 잘못된 출처에 충실(날조 아님).

## 10. 불변 원칙 (BINDING — 코드보다 오래 산다)

1. **지식은 그래프로** — 코드 테이블 금지(LAD 표면층만 예외). 출처는 검색 API 우선, Wikipedia 중심 금지.
2. **propose–verify** — 소프트(GPU/위상/임베딩)는 제안만, 승급은 증거/기호로만.
3. **truth > coverage** — 기권은 줄이되(find-harder) 날조로 줄이지 않는다. "환각 0%" 절대치 광고 금지.
4. **가역 수리** — tombstone+원장, 버전 아티팩트+포인터. 비가역(절단·리셋·마이그레이션)은 운영자 게이트.
5. **로컬-first** — 개인 데이터는 기기에. PII는 자체 저장(외부 서비스 무전송) + 잊힐 권리 레인.
6. **엔진 라이브 재시작·프로덕션 쓰기 = 운영자 전용.** 후보는 무한히 쌓여도 프로덕션은 게이트 뒤에.

## 11. 다음 지도 (우선순위 순)

1. 어의 레지스트리 답변 레인 소비 배선 + 커버리지 배치 확장 (§5 잔여)
2. Brain Link 저장 오프로드(다수결 검증) + VM 코디네이터 WAN 실증 (§7 잔여)
3. "~에 대해 알려줘" 라우트 재귀 적용 + 스플라이스 결함 수리 (§9 한계)
4. 구문 목록 → 그래프 학습 구문(case_frames) — 실현기의 종착
5. BPE 조사 발견기 라이브 배선 / holographic_lm 산문 밀도
6. WebGPU 오브 미니 ATANOR(지식팩+WebGPU) — 언어 완성 후

— 작성: Claude Fable 5, 2026-07-09. 갱신 규칙: 실측이 바뀌면 §9를, 원칙이 바뀌면(드물어야 함) §10을,
착지가 생기면 §5/§7의 잔여와 §11을 고친다. 이 문서가 낡으면 새 문서를 만들지 말고 이 문서를 고쳐라.
