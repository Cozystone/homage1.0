# ATANOR Cloud Candidate Review Flow

Status: proof-only

Open-Web Explorer and Agentic Micro-OS may produce Cloud Brain candidate drafts from public sources. Those drafts remain outside `verified_store_v0` until a separate promotion process is designed and explicitly approved.

## Flow

1. Public source is read through a bounded policy gate.
2. A candidate draft is created through Brain Access Road.
3. The draft enters Agentic Review Queue as `cloud_candidate`.
4. Deterministic scoring marks novelty, usefulness, duplicate risk, confidence, and risk level.
5. A human reviewer may approve as draft, reject, defer, or require more evidence.

## Boundary

Approved cloud candidates do not mutate production. They may only become reviewable candidate queue entries or promotion request drafts.

Rejected and deferred states are preserved as review decisions so the system can learn what not to promote without hidden writes.

## Explicit Non-Goals

- No Local Brain write.
- No production Cloud Brain mutation.
- No candidate promotion.
- No private payload storage.
- No external LLM/sLLM judging.
