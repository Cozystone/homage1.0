# ATANOR ASM-v0 Dashboard Runtime Alignment

Status: product dashboard runtime alignment.

## Cause

The product dashboard at `http://127.0.0.1:3041/?lang=ko&section=home&workspace=product`
was served from the `ATANOR-live-selfhood-scheduler` worktree, while the API
companion on `8502` was still running from an older main-worktree path. The web
proxy also defaulted to `8500`, which was unavailable in this runtime.

When the dashboard chat path could not reach a valid conversation backend, the
proof-only thought dry-run route returned a user-facing fallback phrase that
described internal boundary checking. That text was removed from product
fallback behavior.

## Runtime Path

Product dashboard text input now posts to:

1. `apps/web/app/AtanorUserStatusCard.tsx`
2. `POST /api/chat/atanor`
3. `apps/web/app/api/chat/atanor/route.ts`
4. `http://127.0.0.1:8502/api/chat/atanor`
5. `apps/api/app/routers/dual_brain.py`
6. ASM-v0 conversation surface in `packages/cgsr/cgsr/conversation_surface.py`

The dashboard sends `mode: "conversation"` and `brain_mode: "conversation"` so
short product dialogue uses ASM-v0 directly instead of graph retrieval.

## Safety Metadata

The expected successful response carries:

- `generation_basis: local_corpus_construction_transition_model`
- `external_llm: false`
- `external_sllm: false`
- `rule_based_answer_used: false`
- `template_free_surface: true`
- `internal_trace_exposed: false`
- `local_brain_write: false`
- `production_store_mutated: false`
- `candidate_promotion: false`

The proof-only thought dry-run route no longer invents a final answer when the
API companion is absent. It returns an unavailable status and a safe connection
message instead.

## Product vs Lab

Product mode hides internal diagnostics and uses the hologram as the primary
conversation surface. Lab and developer surfaces may still expose proof-only
panels, but they must not be treated as product answer generation.

## Speaking Visual

The hologram dashboard now exposes `data-speaking="true"` while the orb is in
the speaking state. This is a visual speaking signal only; microphone capture
and raw voice persistence remain disabled.

## Remaining Limits

- ASM-v0 is a small local construction-conditioned surface model.
- Fish 2 audio generation is not hooked in this slice.
- SPLATRA physics and cartridge rendering are not hooked in this slice.
- A live runtime must run the API companion from a worktree that contains the
  ASM-v0 package and router changes.
