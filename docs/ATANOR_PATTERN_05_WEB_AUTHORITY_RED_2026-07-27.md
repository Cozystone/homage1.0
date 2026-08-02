# Pattern #5 web-authority RED receipt

상태: **RED 재현, production 수정 전**

고정 사전등록 표본을 현재 candidate
`bc5cccde42080a784f490ebbb53414cf7ec45131`에서 실행했다.

```text
python -m pytest apps/api/tests/test_web_authority_boundary.py -q
......FFFFFF......
6 failed, 12 passed
```

- 정상 authoritative URL: 6/6 통과
- 정상 non-authoritative single-source hedge: 6/6 통과
- 위조 caller 거절: 0/6 통과

여섯 위조 유형 모두 `verification.authoritative=true`, `tier=verified`,
unhedged answer로 잘못 승격됐다. 따라서 정상 control을 보존하면서 위조
authority만 닫아야 한다는 사전등록 가설이 정확히 재현됐다.

실행 시 production source SHA-256:
`3e18f1461b046bd642102e328d61ca50782ec3eff219c1876b7716881d4dfda2`

dataset SHA-256:
`d0804422d49c0d5baac3cf110741e29e48ef2c2ecae6164dcd9e3b28bccd1128`
