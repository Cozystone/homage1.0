# Live Selfhood Life Cycle v0

`packages/live_selfhood_cycle` is a proof-only lifecycle engine for ATANOR.

It can run deterministic local cycles that observe status, detect needs, rank
impulses, prepare proposals, run local deliberation summaries, enqueue
user-approval-required actions, and generate concise briefs.

It does not:

- write Local Brain
- mutate production stores
- mutate candidate stores
- promote candidates
- connect real P2P
- upload data
- execute generated code
- perform hot-swap
- enable always-on microphone capture
- store raw voice transcripts automatically

The default proof autonomy level is `LEVEL_3_SANDBOX_PLANNER`.
`LEVEL_4_GATED_OPERATOR` can prepare operator confirmation requests, but real
apply remains impossible.
