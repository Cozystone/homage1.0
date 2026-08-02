# ATANOR learning-datasets curation — licensing due diligence + 4D growth loop (2026-07-20)

사장님 제안: 인간이해(Human Universals, HRAF, Murmurs of Earth, Cognitive Science, The Blank Slate),
논리(Lean Mathlib), 상식(Cyc, ConceptNet, ATOMIC, GLUCOSE), 철학(SEP), 토론(Debate), 역사(GDELT),
재난(EM-DAT), 실패(EM-DAT, Bugzilla/Jira/GitHub Issues, SRE/Cloudflare/GitLab postmortems)을 스스로
읽고 이해·학습. **특히 GDELT + EM-DAT + 사고보고서 = "인간 사회의 행동→결과" 인과 코퍼스.**

## 0. BINDING 원칙 (무변경)
- **No-LLM**: 외부 LLM 증류 0. 데이터는 학습 원료지 교사 출력이 아님.
- **라이선스-클린 게이트**: 저작권 자료는 **합법 경로만**. 저작권 서적 전문 복제는 금지 — 파생 통계·
  공개 발췌·도서관/합법 라이선스만.
- **격리 파이프**: 모든 신규 코퍼스는 quarantine → k-소스 합의/무결성 게이트 → 명시적 승격. 직접
  프로덕션 쓰기 금지([[consensus-evidence-machine]] [[candidate-promotion-gate]]).
- **가설 표식**: 인과 도약은 hypothesis=True + 확률(카오스/엔트로피 — 신탁 아님).

## 1. 데이터셋 판정 (라이선스 · 즉시성)

| 데이터셋 | 라이선스 | 판정 | 노선 |
|---|---|---|---|
| **ConceptNet** | CC-BY-SA 4.0 | ✅ 보유/즉시 | 상식 그래프 — 이미 인식사다리에 사용 |
| **ATOMIC / ATOMIC-2020** | CC-BY 4.0 | ✅ 즉시 | if-event→then-event 인과쌍 → causal field 직행 |
| **GLUCOSE** | CC-BY 4.0 | ✅ 즉시 | 서사 인과 10차원 → causal field |
| **GDELT v2** | 공개(무료) | ✅ **LIVE 검증됨** | `causal_corpus.mine_gdelt_slice` — 행동순서쌍 |
| **SRE/Cloudflare/GitLab postmortems** | 공개 게시 | ✅ **LIVE 검증됨** | `mine_incident_timeline` — 시각태그 인과사슬 |
| **GitHub Issues** | 저장소별(대개 공개) | ✅ API/공개 | 버그→수정 순서; repo 라이선스 준수 |
| **Lean Mathlib** | Apache-2.0 | ✅ 즉시 | 정리 의존 DAG → 논리 순서(수학은 시간아닌 논리 우선) |
| **SEP (Stanford Enc. Philosophy)** | ⚠️ 저작권(무료열람) | ⚑ 재점검 | 전문복제 금지; 개념 링크/인용만 |
| **HRAF** | ⚠️ 구독 | ⚑ 사장님 | 기관 구독 필요 — 운영자 액션 |
| **EM-DAT** | ⚠️ **등록 필요**(무료, 비상용) | ⚑ **사장님** | 계정 등록 후 CSV — 운영자 액션 |
| **Cyc / ResearchCyc** | ⚠️ 라이선스 | ⚑ 사장님 | OpenCyc 은퇴; 라이선스 협의 |
| **서적 3종**(Human Universals·Blank Slate·Murmurs·Cognitive Science) | © 저작권 | ⚑ 사장님 | **전문 학습 금지**; 합법 경로(도서관/구매 개인학습)만. 대안: Brown의 Human Universals **목록**은 널리 인용된 사실 명제 → 2차 공개 요약에서 명제만 |
| **Debate datasets** | 개별 상이 | ⚑ 개별 | IBM Debater(CC-BY-SA 다수)=✅, LLM생성=**기각** |
| **Bugzilla/Jira** | 인스턴스별 | ⚑ 개별 | 공개 인스턴스만 |

## 2. 즉시 착수한 것 (이번 세션, SHIPPED)
`packages/temporal_reasoning/causal_corpus.py` + 26 tests:
- **GDELT 실슬라이스** 채굴 LIVE(6 행동순서쌍: conflict→consult, diplomacy→appeal).
- **postmortem 타임라인** 채굴 LIVE(deploy→latency→rollback→recovered 인과사슬).
- 격리 스토어(`causal_counts.json`) + `retrain_field_with_causal`(명시 승격). PrecedenceField로
  직행하는 게 아니라 재훈련 경로로만 흡수.

## 3. 4D 성장 루프 (설계)
```
행동→결과 코퍼스(GDELT·EM-DAT·postmortem·ATOMIC·GLUCOSE)
   → causal_corpus 채굴(순서쌍) → 격리 스토어 → 무결성/합의 게이트
   → PrecedenceField 재훈련(위상장 성장) → BlockUniverse
      · project_forward: "이 행동 다음 무엇이 왔나"(경계·확률)
      · branches: 대안 결과 나란히 랭킹
      · infer_backward: "이 결과는 무엇에서 비롯됐나"
   → 자가 사유 배터리(사회행동→결과 예측/역추론) → 봉인 홀드아웃 채점 → 반복
```
전부 **가설 표식** 유지. 성장의 증거 = 봉인 홀드아웃 인과-순서 정확도 상승(측정), 주장 아님.

## 4. 사장님 액션 (운영자만 가능)
1. **EM-DAT** 계정 등록(무료, 비상용) → CSV 제공 or 자격증명.
2. **HRAF** 기관 구독 여부.
3. 서적 3종: 합법 학습 경로 결정(도서관 API/구매 개인학습/2차 공개요약 명제만).
4. **Cyc** 라이선스 협의 여부.

## 5. 다음 (승인 불요 · 즉시 가능)
- ATOMIC-2020 + GLUCOSE 취득 → causal_corpus 어댑터 → 격리 → 게이트 → 필드 재훈련.
- GDELT 일배치 수집(N일) + 공개 postmortem 목록(danluu/post-mortems) 대량 채굴.
- Lean Mathlib 의존 DAG → 논리-순서 필드(시간장과 분리 축).
- IBM Debater(CC-BY-SA) → argument_miner 코퍼스 보강(F-arg move 전이 강화).
