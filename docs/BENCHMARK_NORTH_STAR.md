# BENCHMARK NORTH STAR — 공인 벤치마크 만점 헌장

> 사장님 지시 (2026-07-14, BINDING): 세계팩 기반 자율 웹학습의 초고도화 + 자가진화로,
> **GPQA Diamond · MMLU-PRO · LMSYS Chatbot Arena · SWE-bench Verified(VibeCode 플러그인 기준) ·
> Artificial Analysis Intelligence Index(AAII)** 를 목표로 한다. 목표는 만점.
> 기준: **웹 검색 배제, 로컬 구동** — 모델의 내장 지식과 추론만. 우리의 "가중치" = 세계팩(그래프).

> **정정 (2026-07-25, BINDING):** 아래 2026-07-14 수치는 역사 기록이다. GPQA Diamond
> n=198 “봉인 베이스라인 완료” 주장은 철회한다. 현재 local CSV의 rows 89·126·191은 네
> label에 세 unique answer text만 있어 strict loader가 accuracy를 fail-closed한다.
> Corrected provenance-bound dataset 전에는 GPQA baseline·accuracy·lift를 주장하지 않는다.
> 현재 벤치 경로는 **NL→goal compiler + 과학지식 staging → E4 → counterbalanced paired E5**다.
> Rational/float DSL green과 DELIBERATOR control/firing은 메커니즘/M1이지 능력 증거가 아니다.

## 정직한 현 위치 (2026-07-14 실측 — 연구소 톤, 과장 금지)

| 벤치 | 현 상태 | 격차의 이름 |
|---|---|---|
| KMMLU (오픈북, 지식 8과목 200문항) | coverage 0.225 · answered_acc 0.20 · strict 0.045 | 세계지식 부재(사전 카트리지뿐) — **세계팩이 직접 해결** |
| MMLU-PRO | 베이스라인 봉인 예정(이 커밋) | 지식 + 다단추론(10지선다, reasoning-heavy) |
| GPQA Diamond | **현재 accuracy fail-closed**; 과거 n=198 수치는 duplicate-choice 데이터 때문에 현 능력 기준선으로 사용 불가 | corrected provenance-bound dataset + NL→goal×과학지식 paired E5 필요 |
| LMSYS Arena | 미측정 | 인간 선호 대화 = register/유창성 트랙 |
| SWE-bench Verified | 미측정 | 코드 합성 = **ATANOR-VibeCode 플러그인** 트랙 |
| AAII | 종합지수 | 위 전부의 함수 |

참고 좌표(정직): 프런티어 LLM들도 GPQA Diamond ~70–85%, SWE-bench Verified ~70%대다.
"만점"은 그 너머의 목표다 — 우리가 이를 목표로 삼는 근거는 접근법의 차이다:
암기된 가중치가 아니라 **명시적 세계그래프 + 결정론적 추론 + 자가진화 루프**는 원리적으로
틀린 답의 원인을 하나씩 제거할 수 있다(오답이 재현·감사·수리 가능). 그 특성 없이는 만점이
복권이지만, 그 특성이 있으면 만점은 공학 목표가 된다. 도달 시점은 약속하지 않는다 —
매 단계 실측 수치로만 말한다.

## 벤치 → 담당 기관 (전부 로컬, 웹검색 0)

```
GPQA·MMLU-PRO ─┬─ 지식층: 세계팩(Wikidata 전체, 다운로드 중) + 벤치미스-구동 커리큘럼 로밍
               └─ 추론층: 확산활성(무한홉) + 합성대수 + 추론 VM(산술·연역 — next cornerstone)
LMSYS Arena ───── 목소리층: register 수확(합의≥2) + 대화쌍 턴테이킹 + 표면생성기 진화 아레나
SWE-bench ─────── 손층: ATANOR-VibeCode(No-LLM 합성 플러그인) — 별도 레포, 이 헌장의 트랙 4
AAII ──────────── 종합: 위 3층의 함수 — 별도 작업 없음, 지수는 따라온다
```

## 자가진화 플라이휠 (초고도화의 뼈대)

```
공인벤치 실행(오픈북, 봉인 문항) ──→ 미스 채굴(근거없음·오답의 "주제"만 추출)
        ↑                                     │
   재실행=성적표                        benchmark_curriculum.json (주제 토큰만)
        │                                     ↓
그래프 성장(합의 게이트) ←── 로머/원정이 그 주제를 세상에서 학습(호흡+호기심)
```
- 진화 아레나(evolve_traversal + 화자 아레나)가 순회·발화 정책을 세대 선택 — 얼린 채점기.
- 이 루프에는 끝이 없다: 미스가 0이 될 때까지 스스로 돈다. 그게 "만점을 목표로 한다"의 공학적 의미.

## 시험-학습 금지 가드 (BINDING — 오염되면 점수는 거짓말이 된다)

1. 커리큘럼에는 벤치 문항의 **주제 토큰만** 들어간다. 질문 원문·보기·정답은 절대 저장/학습 금지.
2. 벤치 문항은 봉인 캐시로 고정 — 학습 파이프(로머·원정·식단)와 물리적으로 분리된 디렉터리.
3. 로머가 벤치 문항 텍스트를 웹에서 만나도(유출 페이지) 학습 금지 — intake에서 벤치 캐시와
   대조해 드랍한다(구현: 커리큘럼 스크립트가 문항 해시 목록을 유지).
4. 성적 향상은 오직 "그 주제를 세상에서 배워서"만 와야 한다. 답 암기는 0점과 같다.

## 현재 측정 사다리 (2026-07-25 operator decision)

- **E4-A**: held-out NL→goal schema conformance, unsupported-input abstention,
  quantity/unit/dimension correctness.
- **E4-B**: provenance/contradiction-bound scientific staging, deterministic replay,
  unauthorized shipped write 0.
- **E5-MMLU-Pro**: counterbalanced per-item OFF/ON. Eligible/compiled/fired/grounded,
  coverage, answered/strict accuracy, wrong-fire/fabrication, abstention,
  latency/resources, regressions, confidence intervals를 따로 보고.
- **E5-GPQA**: corrected provenance-bound dataset이 준비된 뒤 같은 paired protocol.
  그 전 accuracy는 fail-closed.
- **후속**: LMSYS-형 대화 평가(자체 blind A/B 먼저) + SWE-bench Verified(VibeCode 하네스).
- 각 단계 receipt는 source·dataset·selection·evaluator를 묶는다. Firing-rate 상승이나 unit-test
  green을 accuracy 상승으로 쓰지 않는다.
