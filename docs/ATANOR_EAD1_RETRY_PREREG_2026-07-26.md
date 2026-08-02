# EAD-1 재측정 사전등록

상태: **판정 전**

기존 write-once 결과는 수정하거나 재시도하지 않는다. 새 ID와 새 결과 경로를 사용한다.
기존 EAD-1의 production candidate, 24개 pytest case, 임계값, 판정 gate는 그대로
고정한다. 유일한 evaluator 차이는 바깥 `<testsuites>`가 아니라 그 안의
`<testsuite>` 자식 카운터를 합산하는 것이다.

합성 JUnit fixture는 수정 전 `1 failed`, 수정 후 `1 passed`로 집계 결함과 교정을
독립 확인했다.

동일 버그 패턴 감사: **없음**. 이번 세션의 다른 Python evaluator/receipt에서
JUnit 바깥 root의 `attrib`를 직접 카운트로 사용하는 사례는 발견되지 않았다.

한 번만 실행하며 결과와 무관하게 그대로 봉인한다. EAD-2·EAD-3은 자동 착수하지 않는다.
