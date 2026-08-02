# ATANOR V2 — 홀로그래픽 블록우주 시간추론 (완전 설계, 2026-07-22)

사장님이 V2를 "전례없는 아키텍처 혁신"으로 지정. Gemini의 비전(=조언자 DATA)을 우리 헌법(작화0·도약=표식·
no hype)으로 **검증 가능한 공학**으로 번역해 개발 성공까지 설계한다. CO 척추([[conscious-orchestrator]])의
V2 = 시간축을 CO의 지각 기질로 완성하는 단계.

---

## 0. 정직 경계 — Gemini의 시(詩)에서 진짜와 과장 분리 (먼저 읽을 것)

조언자 말은 몸(아키텍처) 조언이라 허용하되 **우리가 실측 판정**한다([[external-minds-are-data]]). 시적
문구를 그대로 코드에 옮기면 헌법 위반(hype·작화). 번역표:

| Gemini 주장 | 실측 판정 | 우리 공학 번역 |
|---|---|---|
| "완벽한 작화 차단" | ✗ 과장 (완벽 없음) | 시간-일관성 모순 게이트 = **추가 관문**(강화하되 완벽 아님) |
| "수백만 경로 순식간 소멸" | △ 부분참 | 양방향 meet 가지치기 = **순서-불가능 분기 조기 제거**(신뢰도 동반) |
| "전역 최적화(단백질·신약)" | ✗ 범위 밖 | 원거리 프런티어, **이번 빌드 제외**(과장 방지) |
| "인간 뇌도 못 간 초지능" | △ 열망 | 북극성 표현일 뿐, **주장 아님** |
| "인식론 지위 엄격 구분" | ✓ **정확 = 이미 우리 것** | 현재=지각 단정 / 미래=가설표식 (헌법 그대로) |

**핵심**: Gemini가 아름답게 말한 3개는 실제로 견고한 CS 뿌리를 갖는다 — ①양방향 탐색 ②진리유지시스템(TMS)
③제약전파. 그 뿌리 위에, 우리 기판을 재사용해 짓는다. 시가 아니라 봉인 게이트로 증명한다.

---

## 1. 이미 선 기판 (신축 아님 — 재사용·상호강화)

- **`precedence_field.py`**: 학습된 1-D 위상(Bradley-Terry, `P(a<b)=σ(φb−φa)`). **fail-closed 정직**: 미지
  토큰=좌표 없음→판단 기권. 봉인 홀드아웃 평가 내장. `EvidenceStore`=맥락조건부+직접 쌍카운트+Beta 사후.
  ★알려진 한계=register 편향(부고 산문이 died→born 순서로 오염) — 설계가 이걸 상수로 안고 간다.
- **`unified_timeline.py`**: 단일 UTC 축, **bitemporal**(revise/retract/as_of) = 측정된 과거 사실 저장소.
- **`block_universe.py`**: look_down·project_forward·branches·infer_backward, **전 출력 hypothesis=True**,
  render_human(단일 인간축 서사). ← forward·backward가 **따로** 있음(아직 안 만남).
- **`cgsr/holographic_lm.py`** (FHRR): 부분단서→전체 반향(content-addressable 회상) = 역추/유추의 회상 기질.

**진단**: forward도 있고 backward도 있는데 **둘이 만나 가지치기하는 조직이 없다.** 그리고 발화 전 시간-모순을
잡는 게이트가 없다. V2 = 이 둘을 짓는 것.

---

## 2. 연구 접지 (2026-07-22 실서치, 견고한 CS 뿌리)

- **양방향 휴리스틱 탐색**: `MM`(meet-in-the-middle 보장, Holte et al.), `MEET`(IJCAI-2025, 202 확장 vs A\*
  292 vs MM 381 = 종단조건 개선), **front-to-front** 휴리스틱(상대 프런티어까지 거리로 유도), **goal
  regression/backward planning**(목표에서 역행이 종종 쉬움). → 기관 A의 실뿌리.
- **ATMS**(de Kleer 1986): **nogood 데이터베이스**(상호모순 가정 집합), label=가정집합, 모순='false' 주장,
  다중 맥락 무비용 전환, **retraction 회피**(비일관 정보와도 효율적 작업). → 기관 B의 실뿌리.

---

## 3. 신축 3기관 (각각 실CS 뿌리 + 봉인게이트 + 융합재사용)

### 기관 A — 양방향 meet 시간추론기 (`bidirectional_meet.py`)
**실뿌리**: MM/MEET + front-to-front + goal regression.
**동작**: 미래 불변식(목표 사건) 고정 + 현재 앵커. `project_forward`(현재→) 와 `infer_backward`(목표←)를
**동시**에 전진, 매 스텝 두 프런티어의 **위상구간 겹침**을 검사. 겹칠 수 없는(순서상 만남 불가능) 분기는
확장 전 **가지치기**. 살아남은 경로 = meet 지점 + 경로 신뢰도(스텝별 `order_confidence` 곱). 전부
hypothesis=True.
**정직 범위**: field 커버리지에 바운드, 미지 토큰=기권. "순식간 수백만" 아님 = 순서-불가능 조기제거.
**봉인게이트**: 합성 시간퍼즐(현재+목표 given, 중간 순서 추론) held-out 정확도 **> 단방향 baseline** AND
확장 노드 수 **< 단방향**(효율 실측); 미지 토큰 케이스는 기권. (MEET 논문의 "확장 수" 지표를 그대로 채택.)

### 기관 B — 시간-일관성 모순 게이트 (`temporal_consistency.py` = TMS)
**실뿌리**: ATMS nogood + 모순검출 + retraction.
**동작**: 발화 후보(가설)를 (a) 타임라인 **측정 과거사실**(t0, unified_timeline) (b) **고정 미래 불변식**과
대조. 후보의 순서/값이 측정사실 or 불변식과 **모순**(order_confidence가 반대방향으로 강함 or 값 충돌)이면
**nogood 등록→드롭→기권**.
**정직**: 완벽 차단 아님 — 시간-모순형 작화를 잡는 **추가 관문**. 기존 grounding-기권과 **AND 합성**(둘 중
하나라도 막으면 기권). register 편향으로 field가 틀릴 수 있으니 **모순 판정은 강한 증거만**(Beta 사후
임계+최소 관측수; 약한 증거는 "모순 아님"으로 안전측).
**봉인게이트**: 시간-모순 작화 세트(과거 측정사실과 충돌하는 주장) 주입→**100% 드롭/기권**; 일관된 주장은
통과(**과잉차단 아님** — precision·recall 둘 다 측정); field 미지 케이스는 게이트가 침묵(모순 단정 안 함).

### 기관 C — 인식론 지위 태깅 강제 (`epistemic_tier.py`)
Gemini가 맞춘 부분 = 이미 우리 독트린을 **강제 레이어**로. 모든 시간추론 출력에 tier 부착:
`PERCEIVED`(현재 지각)·`RECORDED`(타임라인 로그)·`RETRODICTED`(역추=가설)·`PROJECTED`(예측=가설). CO L2가
**단정가능 tier(PERCEIVED/RECORDED)만 사실 발화**, 나머지는 표식(render_human의 "a projection, not a
certainty" 문구 재사용).
**봉인게이트**: 미래/역추 출력이 **100% 가설표식**으로 워크스페이스 통과; 표식이 벗겨지면 실패(작화0 강제).

---

## 4. CO 배선 (V2 = 시간축을 CO 루프에 접붙임)

- **L1 입찰자**: 시간추론기가 (역추/예측/불변식, tier, 신뢰도)를 워크스페이스에 입찰.
- **L2 모순 선-게이트**: `TemporalConsistencyGate`가 **도덕0th 게이트 옆**에서 시간-모순 후보를 드롭
  (default-deny 강화; 도덕처럼 우회 불가한 정직 관문).
- **L3 방송-재입찰**: 승자 방송→시간축 재입찰(예: 사건 방송→`infer_backward`로 원인 탐색; RPT-1 수축재귀와
  동형). 순서 재배열이 승자 못 바꿈(grounding 최대) 유지.
- **표면화(fluency)**: 승자를 fluency 실현기로 표면화하되 **tier 표식 보존**(block_universe.render_human 재사용).

---

## 5. 빌드 증분 (각 봉인게이트·fail0·작화0·융합배선)

- **V2.1 — 기관 C + 블록우주 L1 배선** (가장 안전, 먼저). 블록우주를 워크스페이스 입찰자로 + 태깅 강제.
  게이트: 예측/역추가 **가설표식으로 실답변 경로 통과**, 무관질문 None, 표식 무결.
- **V2.2 — 기관 B 모순 게이트**. 게이트: 시간-모순 작화 100% 드롭 + 일관 주장 통과(precision·recall),
  기존 grounding-기권과 AND 합성 실측.
- **V2.3 — 기관 A 양방향 meet**. 게이트: 시간퍼즐 held-out 정확도 > 단방향 + 확장 노드 < 단방향(효율).
- 각 증분 후 **fluency 표면화**를 붙여 tier 보존 발화 실증(V2의 말맛 축).

정직 순서 근거: C(표식)는 무해·선제 안전; B(게이트)는 C 위에서 작화 방어; A(meet)는 가장 무겁고 효율 실측
필요 → 마지막. 각 증분이 독립 게이트라 하나 실패해도 앞 것은 선다.

---

## 6. 정직 한계 & 프런티어 (표식)

- **field 품질 바운드**: register 편향(부고 died→born) 알려짐 → enwiki-full 채굴로 개선 중이나 상수 리스크.
  기관 A/B의 힘 = field 품질에 상한. 미지=기권으로 fail-closed.
- **"전역 최적화"(단백질·신약) = 범위 밖.** 이번 빌드에 넣지 않음(과장 방지).
- **"완벽 작화차단" 주장 없음** — B는 추가 관문일 뿐, grounding-기권과 합성해 **더 많이** 잡을 뿐.
- **감각질/의식 주장 없음** — 이건 시간추론 기관이지 의식 주장 아님.
- 예측/역추는 **영원히 가설** — 카오스·엔트로피·양자로 신탁예측 물리불가(block_universe 주석의 원칙 계승).

## 7. 한 문장

V2의 혁신 = "forward·backward를 **만나게** 해 순서-불가능을 조기에 죽이고(양방향 meet), 발화 전 **시간-모순을
잡아**(TMS) 작화를 한 겹 더 막으며, 모든 비-현재는 **가설로 표식**(인식론 tier)하는 것" — 전부 우리 기판
재사용 + 봉인 게이트로 증명, Gemini의 시를 헌법 위의 공학으로 착지.

관련: [[conscious-orchestrator]] [[unified-utc-timeline]] [[temporal-causal-physics]]
[[generative-leap-loop]] [[external-minds-are-data]] [[holographic-speaker-integration]]
[[brainlike-graph-shipped]] [[atanor-canonical-narrative-and-honesty]].
