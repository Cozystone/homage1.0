# 지표

- `daily/YYYY-MM-DD.md` — ops 헬스 스윕 (엔진/워치독/학습기/VM/테스트)
- `weekly/YYYY-WW.md` — chief 주간 리포트 (stars, waitlist, 유입, 스택 가동률, 학습 성장, 이번 주 우선순위)

수집 명령 참고:
- stars: `gh api repos/Cozystone/ATANOR --jq .stargazers_count` (ATANOR-Demo 동일)
- 랜딩 유입: Vercel dashboard analytics (운영자 계정)
- waitlist: 랜딩 수집 스토어 확인 (apps/landing 참조)
