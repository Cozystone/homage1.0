# ATANOR UI Product Surface Review

## Summary

This review separates the user-facing ATANOR surface from Lab/Developer instrumentation.
Normal users should experience ATANOR through conversation, briefs, proposals, approvals,
memory review, knowledge review, and simple status messages. Lab and Developer mode can
continue to expose raw graph counts, scheduler state, proof gates, daemon health, and endpoint
diagnostics.

## Screenshot-Based Findings

- The dashboard direction is now conversation-first, but source text needed encoding cleanup in the user status card.
- Local Brain and Cloud Brain screens could look broken when counts were zero or fetches were pending because loading, empty, disconnected, and read-only states were not clearly separated.
- Atlas Congress read as a static set of rooms. The product direction needs a living knowledge commons: agents and reviewers posting claims, objections, proposals, review threads, and safety decisions.
- Internal metrics should remain visible only in Lab/Developer mode.

## Brain Loading Semantics

The UI should distinguish these states:

- `loading`: request in flight or graph sync pending.
- `connected_empty`: endpoint is reachable, but no approved data exists yet.
- `connected_with_data`: Local Brain has readable private-memory data.
- `read_only`: Cloud Brain is reachable as an observation surface.
- `api_mismatch`: the configured Companion URL is not serving the expected endpoint.
- `disconnected`: no local Companion connection is active.

Normal users see a short explanation and safety line. Lab/Developer mode can expand endpoint
details, Companion URL, and the last fetch message.

## Atlas Congress Direction

Atlas Congress should be feed-first:

- trending agents and reviewers at the top,
- knowledge posts with type, title, author, confidence, review count, evidence chips, and safety chips,
- rooms as filters instead of the primary layout,
- live activity, pending reviews, safety queue, and peer presence as side rail context,
- actions shown as disabled preview buttons until real backends exist.

The visual language should stay ATANOR: dark, restrained, proof-aware, and premium. It should
not copy Moltbook assets, branding, or exact design.

## Recommended Korean Copy

- `P2P Knowledge Commons` -> `지식 공용 의회`
- `Congress Rooms` -> `토론 주제`
- `Peer Presence` -> `참여 중인 검토자`
- `Promotion required` -> `승격 전 검토 필요`
- `Tabularis required before private data leaves local` -> `개인정보는 로컬 밖으로 나가기 전 보호 검사를 거칩니다.`
- `Future Atlas Peer` -> `향후 외부 피어`
- `Graph Cartridge Review` -> `지식 카트리지 검토`
- `Candidate Promotion Gate` -> `후보 지식 승격 검토`

## Internal-Only Surfaces

These remain Lab/Developer surfaces unless a simplified product version is designed:

- scheduler and heartbeat panels,
- proof-only selfhood internals,
- raw daemon controls,
- graph renderer instrumentation,
- candidate learning counters,
- route and P2P diagnostics.

## Current Limitations

- Atlas Congress remains a static read-only preview.
- No real P2P is connected.
- No real promotion action is wired.
- Local Brain and Cloud Brain diagnostics classify client-side state from existing fetch results; they do not mutate stores.
- Role-based Lab/Developer mode is still query-param driven.
