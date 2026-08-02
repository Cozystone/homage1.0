# 승인 큐 — 게시 대기 초안

모든 대외 게시물은 여기 파일로 산다. **승인 없는 게시는 없다.**

## 파일 형식
파일명: `YYYY-MM-DD_channel_slug.md`

```markdown
---
channel: hackernews | reddit:r/LocalLLaMA | x | linkedin | github:readme
status: draft | approved | posted | rejected
created_by: atanor-marketing
approved_at:
posted_url:
---

(게시 본문 — 그대로 복붙 가능한 최종 형태)

## 게시 노트
(제목 옵션, 게시 시간 권고, 첫 댓글 초안, 예상 질문과 답변)
```

## 라이프사이클
1. marketing이 draft 생성 → BUSINESS_LOG에 `[승인 대기]` 기록
2. 운영자가 읽고 status를 approved로 (수정 지시는 파일에 코멘트)
3. 운영자가 직접 게시하거나, 세션에서 명시 지시로 게시 → posted + URL 기록
4. 게시 후 반응 지표는 metrics/로
