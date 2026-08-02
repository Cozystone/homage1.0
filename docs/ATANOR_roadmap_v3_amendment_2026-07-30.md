# 로드맵 v3 개정 A1 — 2026-07-30 실측이 바꾸는 세 곳

`ATANOR_roadmap_v3_ultimate.md`는 **여전히 캐노니컬**이다. 이 문서는 그것을 대체하지 않고,
2026-07-30의 전수 실측(`docs/ATANOR_final_structure_and_attack_order.md`)이 **순서를 바꾸는 지점만**
개정한다. 완성의 정의·공식·5국면·상수는 전부 그대로.

측정 출처: `scripts/package_inventory.py` · `scripts/registry_wiring_fill.py` · `packages/operator_census`

---

## 개정 1 — M1 앞에 **M0 통합**을 넣는다 (첫 삽이 바뀐다)

> ### ⚠ 정정 (같은 날, 착공 직후 실측)
> **이 절의 최초 판본은 "52개 형태/261벌 통합"을 연쇄 지점 1위로 올렸다. 그것은 틀렸다.**
> 형태들을 실제로 열어보니 **중복의 대부분이 유틸리티 보일러플레이트**다 —
> `to_dict` 8형태/53벌(20%) · `utc_now_iso` 11개 조직 · `_clamp01`/`_clip01` 4개 ·
> `_unit_interval` 7개 · `_stable_id` 6개 · `repo_root` 9벌 · JSONL `_append` 17벌.
> `main` 7개는 CLI 진입점이므로 **중복이 아니라 오탐**이다.
>
> 더 중요한 것: **오늘 실제로 찾은 병리(`motion_split`의 1-D k-means 대 텍스트층의 widest-jump)는
> min_spread를 2로 내려도 census에 나타나지 않는다.** 같은 것을 계산하지만 코드 형태가 다르기 때문이다.
> **형태 census는 구문적 중복만 본다. 교리가 말하는 병리는 의미적 중복이고, 이 계측기는 구조상 그것을
> 볼 수 없다.**
>
> 따라서 **M0b는 1위에서 위생(hygiene) 등급으로 강등한다.** M0a(래칫)와 M0c(미배선 조직 채택)는
> 유효하다 — M0c는 도달가능성으로 측정됐고 호출부를 지운다.
>
> spread 2에서 실제로 건질 것 셋: **`autonomy_envelope`의 해시체인 원장이 `genesis_sandbox`에
> 복제**(4형태, verify_chain·read_all·_last_hash·_seq — 그리고 sandbox는 archive 후보) ·
> **`budget_check`가 4개 조직**(federation·self_evolution·swe_eval·fluency) ·
> **패키지 단위 고아 분석은 live 패키지 안의 죽은 코드를 못 본다**(Korean 기계장치가 141개 모듈이
> 수입하는 `graph_scale`에 잔존 — 단 **위반은 아님**: `_kiwi()`가 None을 반환해 분기가 죽어 있고
> 영어 가드가 명시돼 있다. 확인 후 기각).

**왜.** M1은 "하나의 보정된 기권 게이트"다. 그런데 `operator_census`가 AST 형태로 실측한 결과
**52개 계산이 261벌로 복제돼 143개 조직 중 81개에 퍼져 있다**(한 형태는 12곳 재구현). 이 상태에서
M1을 지으면 **262번째 사본**이 된다 — "133번째 기관은 문제를 악화시킨다"는 구속 원칙 그대로.
(★위 정정을 읽을 것: 이 논거는 래칫에는 유효하나, 261벌의 내용은 판별연산이 아니라 보일러플레이트다.)

| # | 수술 | 게이트 |
|---|---|---|
| **M0a** | `operator_census`를 배선하고 테스트에 걸어, 중복 형태 수가 **단조 감소만** 가능하게 한다 | 새 중복 도입 시 테스트 RED |
| **M0b** | `graph_scale`의 재구현 형태 12개 통합 (141개 모듈이 수입 → 최대 도달) | `duplicate_copies` 261 → 감소 실측, 회귀 0 |
| **M0c** | `eye`·`hand`·`image_schema`·`self_check` 채택 (이미 지어진 "단일 문" 조직들) | **호출부가 지워질 때만 인정. import 추가는 인정 안 함** |

★M0는 새 조직을 만들지 않는다. **코드가 줄어드는 것이 게이트다.**

---

## 개정 2 — C1은 **짓는 일이 아니라 배선하는 일**이다

`co_allocator` = "Conscious-Orchestrator metacognitive effort allocator (NS-4 / C1)",
**1,033줄, lifecycle `canonical`, runtime_status `unwired`.** 로드맵이 C1을 미래 수술로 적었지만
**이미 쓰여 있다.** 남은 것은 배선과 게이트 측정뿐.

같은 상태의 로드맵 항목들:

| 로드맵 항목 | 실제 상태 |
|---|---|
| C1 NS-4 CO 배분기 | `co_allocator` 1,033줄 **unwired** |
| C3 자기태엽 (spark_chamber) | `spark_chamber` 576줄 **unwired** |
| Z4 ITT v2 | `itt` 512줄 **unwired**(계측기이므로 정상) |
| M2 NS-3 TMS 승격경로 | `promotion_gate`/`promotion_manifest`는 **대체됨** → `autonomy_envelope`가 담당(live) |

★따라서 국면 C의 착공 비용은 로드맵이 가정한 것보다 **낮다.** 단 M1 뒤라는 의존성은 유지(배분기가
막의 신호를 먹으므로).

---

## 개정 3 — 국면 S에 **S5 장면 코퍼스**를 추가한다 (로드맵에 없던 구멍)

**왜.** 로드맵의 S는 전부 **기호 인제스트**(Wikidata, 위키 전문, 도메인 코퍼스)다. 지각 전선
(E1–E4 · F1–F5 · 게슈탈트 기관)은 **로드맵에 항목이 없다.** 그리고 2026-07-30 실측이 그 구멍을
정량화했다: **장면당 유의성 검정은 n=10에서 검정력이 없다** — 10은 한 프레임에 실제로 들어있는
개수다. 따라서 보정 게이트(=M1과 같은 기제)는 **수천 장면에 걸친 사전분포**가 필요하고, 그것은
Atari 롤아웃 하나로 만들 수 없다.

| # | 수술 | 게이트 |
|---|---|---|
| **S5a** | 공개 라이선스 장면 코퍼스 확보(이미지) → `depth_learner`(CARLA 학습완료·소비자 0)·`splatra_worldmodel`(소비자 0)에 투입 | 얼린-B 전이: 학습 장면 아닌 곳에서 성능 유지 |
| **S5b** | 장면횡단 사전분포 학습 → n=10에서 검정력 획득 | 손 k-means 대체 가능(오늘 실패한 검정 4가 통과) |
| S5c | 영상(시간축) — 프레임→사건 diff, 이미 있는 5/6 기관 활용 | 미접촉 스트림에서 사건 분절 |

★S5b가 통과하면 **손으로 고른 문턱 399개 중 점수/유사도 계열 ~102개가 도출 가능**해진다.
이것이 사장님이 말한 "데이터를 투입해 기관을 계몽시키면 관련 문제가 의외로 풀린다"의 실물이다.

---

## 데이터 병목의 정확한 형태 (비대칭)

| | 측정 결과 | 결론 |
|---|---|---|
| **산문 부피** | 영어 재건축이 26.9M→7.17M로 **줄였는데 성능 상승**. 유창성 진범 = register 복잡도 + 개체암기 | 부피 겨눈 수집투어 = 이미 측정된 실수 반복 |
| **register 다양성** | 발화코퍼스를 사실DB에서 학습하던 구성 오류 | ✅ 명령문·대화·절차·서사를 겨눈 수집 (시드 라벨 세트가 그 형태, 검수 대기) |
| **관계 그래프** | 그래프 98% 계사 = 관계 **종류** 부족 | ✅ S1 Wikidata는 산문이 아니라 관계 엣지 — 유효 |
| **장면 수** | n=10 검정력 0, 수천 장면이면 획득 | ✅ **최강 레버** (S5) |

---

## 착공 순서 (개정 후)

```
M0a  operator_census 배선 + 중복 단조감소 테스트     <- 첫 삽 (오늘)
M0b  graph_scale 12형태 통합                          (도달 141모듈)
M0c  eye/hand/image_schema/self_check 채택            (호출부 삭제가 게이트)
  |
M1   NS-1 conformal 기권 게이트  <- M0 뒤라야 사본이 안 된다
  |                                S1 Wikidata 인제스트 (병렬, 진행중)
  |                                S5a 장면 코퍼스 (병렬, 새 항목)
M2   NS-3 TMS  (S1 승격 직후)      S5b 장면횡단 사전분포 -> 문턱 102개 도출
  |
C1   co_allocator 배선 (짓는 일 아님)  H1~H5 상시 병렬
C2   CO 키스톤 ON
C3   spark_chamber 배선
  |
Z1~Z4  인장 — 전부 선 뒤에만
```

## 불변 (v3 §4 승계, 재확인)

작화0 · 봉인측정 · 시험특화 금지 · operator-signed 승격 · 테스트=헌법 · 로컬 커밋만 · 영어-only ·
안전=상수 · **날짜 없음, 게이트 green 누적만, 도달 선언 없음** · 폐기(archive)는 사장님 결정.

관련: [[recursive-self-improvement-plan]] [[generality-is-consolidation]] [[conscious-orchestrator]]
[[check-cascade-before-depth]] [[final-gate-research]]
