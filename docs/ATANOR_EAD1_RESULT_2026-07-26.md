# EAD-1 결과 — live 배선·권한 경계

상태: **RED / evidence no-go**

EAD-1 production 수정은 답을 생성한 evidence row를 문자열 title이 아니라
`answer_index`로 결속하도록 만들었다. 중복 title, 누락·범위 밖·불일치 index는
fail-closed이며 public verification 권한 경계도 유지된다.

사전등록된 model-free 실행 자체는 `24 passed`, exit code 0, skip/error/failure 0이었다.
candidate/source/dataset bytes도 실행 전후 동일했다.

그러나 write-once evaluator가 JUnit의 바깥 `testsuites` 노드에서 `tests` 속성을 읽어
실제 24건을 0건으로 기록했다. 그 결과 사전등록 gate
`all_contract_checks_required`가 false가 되었고 공식 report의 `green`은 false다.
동일 preregistration의 retry는 금지되어 있으므로 이 결과를 사후 GREEN으로
고쳐 쓰지 않는다.

따라서 결론은 다음과 같이 분리한다.

- 구현·원시 pytest 결과: 24/24 통과
- 봉인 evidence 판정: RED/no-go
- model signal: 미측정
- capability: 미입증
- EAD-2·EAD-3: 미착수

재개하려면 JUnit 집계기만 고친 새 preregistration과 새 write-once 경로를 먼저
승인받아야 한다. 기존 report와 attempt receipt는 그대로 보존한다.
