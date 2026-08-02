# ATANOR Agentic Review Queue v0

Status: proof-only

Agentic Micro-OS can create useful drafts from public-web exploration, tool traces, and SPLATRA proposals. Those outputs are not allowed to mutate Cloud Brain, Local Brain, skills, production behavior, git state, or runtime configuration directly.

The Agentic Review Queue is the first human-review surface between autonomous exploration and any later approval gate.

## Reviewable Item Types

- `cloud_candidate`: Cloud Brain candidate draft only.
- `skill_draft`: skill registry draft only.
- `source_summary`: attachable public evidence draft only.
- `splatra_patch`: patch proposal only.
- `tool_trajectory`: reusable skill draft candidate only.

## Deterministic Scores

No LLM judge is used.

- novelty: content hash and source uniqueness.
- usefulness: summary length, tags, claims, source references, and procedure detail.
- duplicate: content hash or title token overlap.
- risk: private payload, production-write request, unsafe tool, unknown source, or low confidence signals.
- confidence: source count, excerpt quality, and absence of private or mutating signals.

## Safety Invariants

- `external_llm=false`
- `external_sllm=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `skill_auto_promoted=false`
- `auto_commit=false`
- `auto_push=false`
- `human_approval_required=true`
- `proof_only=true`

Approval changes only the review item status. It does not promote candidates, install skills, write memories, apply patches, or push code.

## Future Path

Future promotion requires a separate signed promotion manifest, operator confirmation, and production gate. The review queue only prepares evidence for that later process.
