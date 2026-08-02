# Pattern #5 capability execution manifest

상태: **harness 봉인 준비 완료 / target 18건 미실행**

## EOL 결속 정정

기존 v1 candidate binding은 당시 checkout bytes를 그대로 봉인했다. OFF digest
`3e18…`은 bc5 Git blob을 CRLF로 바꾼 값이고, ON digest `948b…`은 수정 직후
working tree의 mixed-EOL 값이다. v1을 고쳐 쓰지 않고 그대로 보존한 채,
`pattern_05_web_authority_execution_binding_v2.json`이 실행 identity만
명시적으로 supersede한다.

- OFF: commit `bc5cccde…`, object `9a132f61…`, blob SHA-256 `cca015ab…`
- ON: commit `e94d1c1e…`, object `9c4d16b6…`, blob SHA-256 `c9385021…`

Controller는 attempt marker를 만들기 **전에** 두 commit/object/blob과
`referent_resonance.py` dependency blob을 모두 확인한다. 하나라도 다르면
worker를 시작하지 않는다.

## 격리 실행

실행 승인 시에만 controller가 write-once attempt marker를 먼저 만든 뒤,
각 commit에서 필요한 tracked paths를 fresh temporary root로 `git archive`
한다. OFF와 ON worker는 각각 대응 root를 cwd/sys.path로 사용한다.
current checkout source fallback은 없다.

Worker 환경은 PATH·SystemRoot·temp 등 명시적 OS allowlist와 deterministic
Python 변수만 상속한다. `PYTHONPATH`, proxy, `ATANOR_*`, provider override,
API key·auth token은 상속하지 않는다. `.env.local`은 archive에 없고,
urllib/socket network entry point는 fail-closed다. 실제 repo-local import의
root-relative path와 SHA-256도 결과에 남긴다.

## 한 번만 실행되는 프로토콜

고정 18건을 item-id hash로 A/B 9건씩 나누고 다음 네 fresh subprocess로
실행한다.

1. A/OFF forward
2. B/ON forward
3. A/ON reverse
4. B/OFF reverse

각 항목은 OFF·ON 각 1회다. Controller는 raw counts, false assertion,
wrong-source adoption, disposition accuracy, 정상 accept, hedge 보존과
사전등록 gate를 계산한다. `attempt`, `report`, `failure` 중 하나라도 이미
존재하면 재실행을 거부한다.

현재는 target run을 하지 않았다. 수행한 것은 synthetic counting/self-test와
static digest validation뿐이다. Capability 결론은 아직 없다.
