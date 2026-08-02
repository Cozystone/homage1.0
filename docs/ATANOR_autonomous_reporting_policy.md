# ATANOR Autonomous Reporting Policy

Status: trigger-based reporting for proof-only explorers.

Morning reports are optional. The explorer should not create noisy reports just
because a loop ran. It emits a full report only when a useful trigger fires.

## Report Triggers

- New high-value cluster found.
- Safety issue found.
- Install or blocker solved.
- Loop budget stopped.
- Enough candidate drafts accumulated.
- User-facing next action needed.

## Compact State Log

If no trigger fires, the loop writes only a compact state log such as:

```text
read=1 rejected=0 drafts=1 stop=completed
```

This keeps autonomous exploration inspectable without turning every small run
into a noisy milestone.

## Safety Requirements

Reports and state logs must preserve these invariants:

- `external_llm=false`
- `external_sllm=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `arbitrary_js_eval=false`
- `auto_commit=false`
- `auto_push=false`
- `human_approval_required=true`

Generated reports, raw web collections, and runtime logs must not be staged or
committed unless they are hand-authored documentation.
