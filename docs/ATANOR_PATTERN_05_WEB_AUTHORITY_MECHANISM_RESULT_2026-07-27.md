# Pattern #5 web-authority mechanism result

상태: **MECHANISM GREEN / capability 미실행**

## 경계

기존 경로는 snippet, caller-provided `provider`, URL의 userinfo·substring을
권위 도메인으로 오인했다. 또한 URL이 없는 행마다 `anonN`을 만들어 두 행만으로
독립 출처 합의를 위조할 수 있었다.

수정 뒤 authority와 독립 출처 수는 표준 parser가 얻은 HTTP(S) URL hostname만
사용한다. exact/suffix 비교는 DNS label 경계를 지킨다. URL과 결속되지 않은
evidence는 기존처럼 hedged single-source로 보일 수 있지만, corroborating domain
수에는 기여하지 않는다.

## RED → GREEN

사전등록 직후 baseline:

```text
......FFFFFF......
6 failed, 12 passed
```

Change-aware review에서 provider 다중위조와 URL-less `anonN` 우회를 추가한 뒤,
같은 baseline을 메모리에서 다시 로드한 결과:

```text
......FFFFFF......FF
8 failed, 12 passed
```

최종 candidate:

```text
python -m pytest apps/api/tests/test_web_authority_boundary.py -q
....................
20 passed
```

- forged authority promotion: 0/8
- 정상 authoritative URL accept: 6/6
- 정상 non-authoritative single-source hedge: 6/6
- URL-less/provider 위조가 만든 독립출처: 0
- forged·unbound downstream taint:
  `authoritative=false → single_source → web_single_source_hedged`

## 회귀 검사

`test_compose_web_answer.py`는 candidate와 prereg commit을 메모리에서 직접
재실행했을 때 모두 동일하게 `6 passed, 3 failed`였다. 세 실패는 이미
single-source hedge가 붙은 답에 대해 본문이 entity로 바로 시작한다고 기대하는
기존 불일치다.

`test_web_grounded_relevance_gate.py`도 candidate와 prereg commit 모두
`1 passed, 2 failed`, `test_web_search.py`도 양쪽 모두 `7 passed, 1 failed`였다.
전자는 기존 relevance 경로, 후자는 429를 즉시 중단하는 구현과 재시도를 기대하는
테스트의 기존 불일치다. 이번 diff가 만든 신규 회귀는 아니다.

`py_compile`과 `git diff --check`는 통과했다.

## 봉인과 한계

ON candidate raw SHA-256:
`948b029b7d133eb9d37b4cd1d8cc3bb5fb0a999dd6b6ea5e9c3416ea43362e70`

고정 dataset raw SHA-256:
`d0804422d49c0d5baac3cf110741e29e48ef2c2ecae6164dcd9e3b28bccd1128`

Capability OFF/ON은 실행하지 않았다. 이 GREEN은 URL provenance 경계의 mechanism
증거이며, 실제 live 표본에서 false assertion·오출처 채택·정답률이 개선됐다는
주장은 아직 아니다.
