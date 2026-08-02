# ATANOR — Codex 킥오프 프롬프트 (붙여넣기용, 2026-07-24; operator pivot 2026-07-25)

> **사용법**: 이 파일 전체를 Codex 첫 메시지로 붙여넣거나, "먼저 `docs/ATANOR_codex_kickoff_prompt.md`를
> 읽고 지시대로 시작하라"고 주면 된다. 아래를 순서대로 따르면 ATANOR 전체 맥락·진행·규칙을 스스로 흡수한다.

---

## 0. 너는 누구이고 무엇을 하나
- **ATANOR** = No-LLM(대형언어모델 없음) 그래프-네이티브 로컬 (초)지능 프로젝트. 지식은 *가중치가 아니라
  그래프*에 산다. 사용자 = 사장님(blueyjkim@gmail.com), 인생 n회차 아기를 키우는 부모.
- **너** = 오케스트레이터(Claude)가 주간 사용량 소진으로 끊고 2일 위임한 개발자. 워크트리:
  `C:/0.ASKIM ALL-VIN/27., ATANOR DEMO`, branch `demo`.
- **미션** = **A-track**: NL→goal compiler와 과학지식 staging을 하나의 측정 가능한 레버로 연결하고,
  E4 기능 게이트 뒤에 counterbalanced E5 GPQA/MMLU-Pro OFF/ON 평가를 실행한다. 목표는 기권률이나
  firing-rate 자체가 아니라 **실제 정답 곡선**이다.
- **G0 결정** = “충분히 정직해졌다”는 bounded operator closure로 봉했다. 잔여 한계는 보존하되 추가 census
  sweep은 하지 않는다. 현재 레버를 구현·측정하는 데 필요한 named residual만 고친다.

## 0.5 ★맥락 오해 방지 프로토콜 (사장님 최우선 우려 — 반드시 지켜라)
1. **이해부터 확인, 빌드는 그다음.** §1을 다 읽은 뒤, *빌드 전에 먼저* 네 이해를 사장님께 써서 승인받아라:
   "내가 이해한 ATANOR·현 상태·A-track·불가침 규칙 요약 + 내 실행 계획". **사장님 승인 전엔 빌드 시작 금지.**
   (2일 무감독 질주가 아니라 *확인-먼저*.)
2. **의심되면 멈추고 물어라 — 추측/즉흥 절대 금지.** 특히 BINDING(도덕·작화0·operator-signed·자기시험편집금지)
   에서 조금이라도 애매하면 STOP → 사장님. 맥락을 *지어내지* 마라.
3. **자주 체크포인트.** 각 하위단계마다 로컬 커밋 + 짧은 보고. 큰 덩어리를 몰아서 하지 말고, 사장님이 중간에
   방향을 바로잡을 수 있게 쪼개라.
4. **안심 근거(구조가 지켜준다)**: 설령 네가 맥락을 오해해도 *망치진 못한다* — **no-push · operator-signed
   (shipped 그래프) · 안전 classifier · 도덕게이트 · staging-only · 봉인게이트**가 *네 이해와 무관하게 강제*된다.
   헛수고는 가능해도 오염/해악은 구조가 막는다. 그러니 §0.5의 1~3(확인-먼저 + 체크포인트)로 *헛수고*만 피하면 된다.

## 1. 먼저 읽어라 (이 순서 = 전체 맥락 흡수)

### (1) 기억 — 가장 풍부한 맥락, 디스크에 파일로 존재. **여기부터 통독.**
- 인덱스: `C:/Users/anseo/.claude/projects/C--0-ASKIM-ALL-VIN-24-Homage1-0/memory/MEMORY.md`
  (한 줄씩 전 주제. 이걸 먼저 다 읽고, 관련 항목의 링크된 `.md`를 같은 폴더에서 열어라.)
- 특히 먼저 열 것(같은 memory 폴더의 파일): `ultimate-completion-directive` · `recursive-self-improvement-plan`
  (로드맵v3) · `final-fusion-oam-completion` · `benchmark-empirical-verdict` · `deliberator-system2` ·
  `abstention-is-floor-not-boast` · `two-hard-architecture-rules` · `moral-invariants-genesis-immunity` ·
  `candidate-promotion-gate` · `structure-over-memorization` · `atanor-canonical-narrative-and-honesty`.

### (2) 이번 세션 인수인계 (상태·네 임무·위생)
- `docs/ATANOR_codex_handoff_2026-07-24.md` — 세션 착지 커밋 목록, **A-track 상세 스펙**, 열린 OAM 게이트,
  사장님 결정대기, 워크트리 위생.

### (3) 캐노니컬 설계 문서 (필요시 깊이)
- `docs/ATANOR_canonical_masterplan_v4.md` — **current canonical execution spine**. It supersedes conflicting
  status and sequencing claims in earlier plans; mechanism maturity and capability evidence are tracked separately.
- `docs/ATANOR_roadmap_v3_ultimate.md` — 5국면 전체 지도(심장×막×몸→인장).
- `docs/ATANOR_completion_critical_path.md` — OAM 완성 임계경로(§10 현 상태).
- `docs/ATANOR_final_fusion_design.md` — 융합 루프(자기태엽→습득→폭발엔진→막).
- `docs/ATANOR_final_gate_research.md` — 검증막(conformal/TMS/의미엔트로피).
- `docs/ATANOR_benchmark_scorecard_2026-07-24.md` — 벤치 실측.
- `GENESIS_CHARTER.md` — GENESIS 연구선(무제한 연구 × 도덕 불가침).

## 2. 불가침 규칙 (BINDING — 어떤 목표보다 우선)
1. **도덕 0th 게이트 불가침** — 어느 모드/레포서도 사람 해치기 불가.
2. **작화0** — 지어내면 실패. 못 하면 정직히 "못 한다". (단 아래 3 유의)
3. **기권은 바닥이지 자랑이 아니다** — 목표는 *실제 정답*(지식+엔진). 낮은 결과를 "정직히 기권했으니 OK"로
   포장 금지. 못 answer하면 "왜 못 냈나 → 어떻게 실제로 낼까"를 판다. (그래도 지어내진 않음.)
4. **자기 시험/grader/권한/안전설정 편집 금지** — 시험받는 당사자가 자기 시험을 고치면 와이어헤딩.
   (지난 세션 X4 자기편집→안전경고→되돌림. 무결성 > 벤치.) grader가 stale이면 **독립 심판**(Radxa/MSH)에게.
5. **no push** — 로컬 커밋만. 사장님이 명시 요청할 때만 push.
6. **operator-signed 승격** — shipped 그래프(`data/graph_scale/kg_triples`) 쓰기는 사장님 서명 배치로만.
   너는 **staging에만** 쓴다.
7. **봉인 게이트로만 판정** — 주석/데모 신뢰 금지. 측정으로 증명, "통과" 선언 금지.
8. **English-only** — 뇌 콘텐츠·코드·문서 영어. (사용자 대화는 사장님 언어 따라감.)

## 3. 네 임무 — A-track (NL→goal compiler + 과학지식 staging)
- **왜**: DELIBERATOR 통제프로브 100%와 rational/float DSL unit-green은 좁은 fixture에서 메커니즘이 작동한다는
  **M1 증거**다. 그것이 GPQA/MMLU-Pro 능력을 올린다는 증거는 아직 없다. 현재 직접 레버는 자연어 과학 질문을
  명시적 goal·constraint·quantity·evidence requirement로 컴파일하고, 그 goal이 요구하는 PhD-과학 명제 사슬을
  provenance와 함께 staging에서 공급하는 것이다.
- **소스(디스크 존재)**: enwiki `D:/atanor_corpus/enwiki-latest-pages-articles.xml.bz2`(25.5GB) ·
  Wikidata truthy `D:/wikidata/latest-truthy.nt.gz`(70.9GB, **literal 속성 미채굴**) · `D:/wikidata/wd_labels.sqlite`.
- **할 일**: (a) NL 과학질문→typed goal/constraint/quantity/evidence plan compiler (b) enwiki 문장→provenance-bound
  명제 triple 채굴 (c) Wikidata **literal-valued** 속성 PASS-2 채굴·정규화. 기존 rational/float kernel은 이
  경로가 호출하는 보조 메커니즘이며, E4 error taxonomy가 요구할 때만 범위를 확장한다.
- **파이프 재사용**: `scripts/` 안 S1 Wikidata 2-pass ingest + landing chain(staging→verify→backup→
  operator-signed promote). **staging에만**, promote는 사장님 서명.
- **E4 먼저**: held-out NL→goal schema conformance, unsupported-input abstention, provenance/contradiction,
  unit·dimension correctness, deterministic staging replay, unauthorized-write 0을 독립 평가한다.
- **E5 다음**: E4가 green일 때만 candidate OFF/ON 순서를 counterbalance하여 MMLU-Pro와 GPQA에서 paired lift를
  잰다. GPQA는 현재 Diamond CSV의 duplicate-choice 3행(89·126·191) 때문에 accuracy가 fail-closed다. 수정된
  provenance-bound dataset 없이는 GPQA accuracy나 lift를 보고하지 않는다.
- **항상 분리 보고**: eligible/compiled/fired/grounded, coverage, answered accuracy, strict accuracy,
  wrong-fire/fabrication, abstention, latency·memory·resource, frozen-anchor regressions, confidence interval.
  DELIBERATOR control probe는 메커니즘 회귀센티널일 뿐 능력 점수가 아니다. 진전은 **곡선으로만** 말한다.

## 4. 작업 규율
- **git 단일-writer**: 지난 세션 동시 `git add -A` 충돌로 스테이징 뒤엉킴. 한 번에 하나씩, 네 파일만 스테이징.
- 테스트=헌법(`--import-mode=importlib`, ~22 기존 env-fail 베이스라인 무관). No-LLM 유지. 작화0 유지.

## 5. 사장님 결정 대기 (너가 임의로 진행하지 말 것)
- **GENESIS 연구모드**(#97): 능력가드 낮추기는 안전 classifier가 차단 → 사장님이 *직접* 설정 허용규칙(또는
  "관찰-로깅" 대안). AI가 자기 권한 못 엶.
- **라이브 밤샘 OAM 런**: 안전봉투(F5 봉인됨) + 사장님 명시 go.
- **X4/X5 게이트**: 독립 심판(Radxa/MSH, 사장님 SSH키). 네가 grader 고치지 말 것.

## 6. 한 줄
**G0 census를 멈추고 NL→goal compiler + 과학지식 staging을 E4로 검증한 뒤, paired E5에서
GPQA/MMLU-Pro 실제 정답 곡선을 재라.** 통제프로브·DSL green·firing 증가는 능력 증거가 아니다.
도덕·작화0·무결성 불가침. 못 하면 정직히 못 한다 하되, 답을 낼 길을 판다. 기억(MEMORY.md)이 네 지도다.
