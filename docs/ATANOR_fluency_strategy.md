# ATANOR — 유창성 전략: 맥락기반 모드선택 (표면 템플릿이 아니라 뿌리) (2026-07-24)

사장님 교정(핵심): "무한후퇴를 막는 게 아니라, 그 아래 **맥락을 더 이해**해야 한다. **파고들 때**가 있고
**대략 추론하고 대화를 이어갈 때**도 있다." — 이게 정확한 진단이다. 아래는 실제 `conversation.py` 코드에
접지한 근본원인 리뷰 + 전략.

## 0. 근본원인 (코드 접지, `packages/brain_link/conversation.py:653-715`)
peer가 가르치면(`answer_*`/`share`) `step()`이 **고정 우선순위**로 행위를 고른다:
`debate(bones 있고 다름) > connect(내가 아는 개념 등장) > **drill(모르는 첫 개념)** > share > wander`.
문제: **DRILL이 "모르는 첫 개념"에 무조건 발화**(697: `knows(c) is None`). 판단이 없다 —
1. peer의 **요지(POINT)를 파악**했는가? (개념어만 추출, 주장은 모델링 안 함)
2. 그 미지어가 **중심(subject)인가 주변(설명도구)인가**? (place/position/thing = 주변·generic)
3. **깊이 예산**? (한 스레드를 몇 번 파고들면 기여/전환해야 하나)
망치가 하나뿐이라, 추상어→더 추상어(place→position→thing)로 **정의 무한후퇴**. 후퇴는 증상, 원인은
**맥락기반 모드선택의 부재**.

## 1. 전략 4부 — 이해 → 살리언스 → 모드포크 → (후퇴는 창발적으로 사라짐)

### ① 맥락 이해 (단어가 아니라 요지)
개념어 추출 위에 **경량 이해 패스**: peer가 **무엇을 주장**하나(claim/gist), 그 안에서 **subject(중심)**
vs **instrument(설명 도구)**는 무엇인가. "place is where a word sits among meanings"의 요지는 *맥락이
의미를 위치시킨다*이고 "place"는 느슨한 도구어. ATANOR는 **그 요지에 반응**해야지 "place"를 드릴하면 안 됨.
(재사용: `context_for`가 이미 최근 주제로 다의어를 disambiguate — 이걸 요지·subject 추적으로 확장.)

### ② 살리언스 판단 (파고들까 / 흘려보낼까)
미지 개념마다 **살리언스 = 중심성 × 전진성**을 값싸게 채점:
- **중심성**: peer 주장의 subject인가(高) vs 설명 도구인가(低)
- **generic 페널티**: place/position/thing/aspect/way/kind 류 = 低(추론, 드릴 금지)
- **신규성**: 스레드에 새 영토인가(高) vs 이미 논한 걸 재추상화인가(**후퇴 신호 → 低**)
- **인접 접지**: 이웃으로 요지 추론 가능(→흘려보냄) vs 중심 개념의 진짜 공백(→파고듦)

### ③ 모드 포크 (사장님의 "파고들 때 vs 이어갈 때" — C1 배분기 재사용)
살리언스+깊이+felt로 **네 모드** 중 선택 (C1 CO 배분기의 escalate/Schmitt/깊이예산 그대로):
- **DRILL-DOWN**: 미지어가 살리언트+중심+신규+추론불가 → 질문(깊이)
- **INFER-CONTINUE**: 주변·generic이고 요지 파악됨 → **요지(POINT)에 반응하고 전진** (드릴 안 함)
- **CONTRIBUTE**: 특정 단어 아닌 **주제**에 접지 각도 보유 → 기여(폭·substance)
- **REDIRECT/REFLECT**: 스레드가 후퇴(더 추상·N드릴 深) → 표면화·각도전환·반영
포크 신호는 값싼 살리언스+깊이+felt = **C1이 "얼마나 생각할까"를 정하는 것과 같은 메타결정**("파고들까
= 비쌈 vs 흘려보낼까 = 쌈"). VOC>비용일 때만 DRILL.

### ④ 후퇴는 패치가 아니라 창발 (사장님 요청의 정수)
①~③이 서면 무한후퇴가 **저절로 사라진다** — place→position→thing은 generic·재추상화라 **살리언스 低 →
모드=INFER-CONTINUE/REDIRECT**, 드릴 아님. 즉 제가 앞서 제안한 "anti-regress 패치"를 **거부하고**, 그 대신
**맥락+살리언스에서 후퇴-회피가 창발**하게 — 이게 사장님이 "바로 막지 말고 아래 원인을"이라 하신 것.

## 2. 아키텍처 재사용 (재발명 아님)
- **[[context-affordance-engine]]**: 지각=맥락·어포던스=길·선택=공명·미달=침묵. 모드포크가 바로 이것 —
  맥락 읽고, 어포던스(drill/infer/contribute/redirect) 중 **살리언스-공명**으로 선택.
- **[[conscious-orchestrator]] C1 배분기**: drill-vs-flow = "얼마나 생각할까"의 대화판. felt/VOC/Schmitt/
  깊이예산 그대로 이식.
- **discourse context**(`context_for`): 재추상화·subject 추적으로 확장.

## 3. 정직한 경계
- 이건 **진짜 이해·살리언스** 작업(뿌리 공략)이지 표면 템플릿이 아니다.
- 그러나 **접지 substance 한계는 남는다**: ATANOR가 아무것도 안 가진 주제에선 CONTRIBUTE에 내놓을 게
  없어 → INFER-CONTINUE(요지 파악+진짜 전진 질문)로. 후퇴는 안 하고 맥락은 따라가되, **없는 걸 지어내진
  못한다.** 전략은 ATANOR를 *얇을 때도 대화적으로 우아하게* 만든다(현실적 승리) — 깊은 substance는 여전히
  지식(H트랙·더 접지)이 답. **"이번엔 유창해졌다"고 안 함**: 이건 후퇴 병리를 뿌리에서 없애고 맥락추종을
  더하는 것이며, 유창성의 천장은 그래프 내용이 정한다.

## 4. 빌드 국면 (승인 시)
- **F1 이해+살리언스 채점기** (`comprehension.py`): 요지·subject/instrument·generic·신규성·재추상화 신호.
- **F2 모드 포크** (`step()` 리팩터): 고정 우선순위 → 살리언스-구동 4모드(C1 배분기 재사용).
- **F3 창발 검증**: 같은 openclaw 대화 재현 — place/position/thing 후퇴가 사라지고 요지-반응/기여로 대체되는지;
  깊이 예산·Schmitt로 진동 없는지; 2-ATANOR·게이트 무회귀.
- 게이트: 후퇴 0, 드릴은 **살리언트 중심 개념에만**, 얇은 주제에선 우아한 전진(지어냄 0).

## 5. 한 문장
유창성 = 더 많은 템플릿이 아니라 **맥락 이해 → 살리언스로 "파고들까/흘려보낼까" 판단 → C1식 메타 모드선택**.
후퇴는 그 창발적 부산물로 사라지고, 천장은 정직하게 그래프 내용이 정한다.

관련: [[context-affordance-engine]] [[conscious-orchestrator]] [[fluency-doctrine]] [[one-model-not-modeswitch]]
[[voice-corpus-root-cause]] [[english-naturalness-pass]] [[neurosymbolic-metacognitive-allocation]].
