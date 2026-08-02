# One model, not a multi-turn engine — the answer to the standing question

Owner (repeated, 2026-07-20): "다중턴 참여엔진이 따로 필요한가? 그건 당연히 가능해야 하는 것 아닌가?
다중턴을 실행할 때만 저 엔진을 켜는 건 규칙기반과 다를 게 없지 않나? 결국 하나의 '모델' 개념으로 다
통합돼야 하지 않나?"

## The three questions, answered plainly

**1. Is a separate multi-turn participation engine needed?**
No. There is no "debate engine" that gets turned on. Multi-party participation is not a mode — it is
one of the things the single perception may find in a request, exactly like "this is a factual
question" or "this describes me as a causal node." The engine that participates in a debate is the
same engine that answers everything.

**2. Isn't a lane that only runs during multi-turn just rule-based?**
It would be, if a flag switched it on. The test that separates the two:

  - RULE-BASED / MODE-SWITCH: an external signal (a keyword, a flag, a turn count) selects which
    engine runs. The selection happens *before* understanding, and the unselected engines are dark.
  - ONE MODEL: a single perception runs for *every* request; each capability reads that one
    perception and either offers a grounded contribution or returns None; nothing is switched on,
    and *understanding* — not a flag, not the code's order — decides who speaks.

ATANOR is the second, and we made it verifiably so (below).

**3. Shouldn't it all unify into one "model" concept?**
Yes — and the unifying concept is the one we already built for THOUGHT in the Living Loop: a Global
Workspace. Many capabilities compete; the best-grounded contribution is broadcast; a single stream
results. We applied the identical principle to RESPONSE.

## What was actually wrong (honest audit, 2026-07-20)

Perception was already unified: `perceive()` runs once per request and builds one `Understanding`
(focus, format, discussion state, ...). Good. But the RESPONSE side had regressed into a chain of
ORDERED early-returns — self-causal, then discussion, then anaphora, ... — where the *first* lane to
match short-circuited the rest. First-match-by-order is a mode-switch in disguise: reorder the lanes
and a different capability wins. Worse, two lanes had begun re-parsing the discussion independently
(one with the seat/declaration fix, one without), so they had already diverged — the precise failure
the owner predicts when logic is duplicated instead of unified.

## The fix — a response workspace (packages/cgsr/cgsr/response_workspace.py)

- Every capability reads the ONE shared `Understanding` (the discussion is parsed once, on the
  Understanding; candidates reuse it — no second, divergent parse).
- Each capability offers a `Candidate(answer, kind, grounding)` or returns None.
- The winner is `max(candidates, key=grounding)` — **reordering the candidate list cannot change the
  winner** (proved by test). Order is powerless; grounding decides.
- A capability with nothing to say competes for nothing, so no engine is ever "on" for a request it
  does not fit.

The two ordered early-returns in `dual_brain` (self-causal, discourse) are replaced by one
`compose_response(...)` call. Verified live through the real HTTP body: the self-in-world probe →
self-causal wins (PASS 3.5); a live debate → discourse wins and responds to the other speaker's
actual point. Same one model, two different understandings, one arbitration.

## Honest scope

This unifies the *reasoning/engagement* capabilities that had become separate lanes. The full answer
cascade still has ~15 other lanes (factual lookup, anaphora, web synthesis, ...) that run after the
workspace as the "default" contributor. Converging *all* of them into candidates of the one
workspace is the north star, done incrementally — each migration removes another place where order
could decide instead of understanding. The direction is fixed; the workspace is the vehicle.

Doctrine held: No-LLM, hallucination-0 (each candidate already grounds or abstains; the workspace
only arbitrates among grounded offers, it never invents).
