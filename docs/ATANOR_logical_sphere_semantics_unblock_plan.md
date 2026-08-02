# ATANOR Logical Sphere Semantics Unblock Plan

Status: planning-only. No implementation in this slice.

## Current Blockage

Logical Sphere semantics work is blocked by a mixed UI/API/read-model worktree:

- `apps/api/app/routers/cloud_brain.py` contains candidate daemon/status,
  bounded learning, web evidence, and Cloud status route changes.
- `packages/cloud_brain/read_model.py` contains verified store and logical graph
  read-model changes.
- `packages/cloud_brain/tests/test_read_model.py` contains matching test changes.
- `apps/web/app/page.tsx` has a very large mixed UI diff for Cloud Lab,
  candidate overlay, Atlas/Graph Hub, and Logical Sphere labels.
- `apps/web/app/globals.css` contains mixed UI styling changes.
- Several untracked API and web proxy route tests exist under `apps/api/tests/`
  and `apps/web/app/api/cloud-brain/candidate/`.

These files must not be staged together as one broad change.

## Target Semantics

Logical Sphere should explicitly separate:

- verified counts: stable `verified_store_v0` concepts and relations
- candidate counts: unpromoted candidate learning output
- working memory temporary counts: temporary local exchange or overlay state
- rendered viewport sample: current materialized/rendered nodes and edges
- chunk virtualization: active chunks, LOD, implicit pair count, and pair edges
  sent

The UI must not imply that rendered viewport counts are total graph counts.

## API Summary Endpoint Proposal

Add a read-only endpoint only after source isolation:

```text
GET /api/cloud-brain/logical-sphere/summary
```

Proposed fields:

- `verified_counts`
- `candidate_counts`
- `working_memory_temporary_counts`
- `rendered_viewport_sample`
- `chunk_virtualization`
- `explanation_flags`

Required flags:

- `verified_counts_change_only_after_promotion=true`
- `candidate_counts_are_unpromoted_learning=true`
- `rendered_counts_are_view_budget_not_total_graph=true`
- `candidate_pair_edges_sent=0`
- `full_store_scan=false`

## UI Label Changes

Use explicit labels:

- Verified Logical Nodes
- Verified Stored Relations
- Candidate Concepts
- Candidate Relations
- Working Memory Temporary Nodes
- Working Memory Temporary Relations
- Rendered Viewport Sample
- Full Graph Is Chunk-Streamed
- Pair Edges Sent

Korean labels should preserve the same distinction between verified,
candidate/unpromoted, temporary, and rendered/sample counts.

## Minimum Safe Implementation Slice

1. Add read-only summary builder in a small backend module or read-model helper.
2. Add focused tests proving verified counts remain stable during candidate-only
   runs.
3. Add UI label-only changes in a separate commit after backend semantics are
   verified.
4. Do not start learning, promote candidates, write Local Brain, mutate
   `verified_store_v0`, or rebuild indexes during status requests.

## Test Plan

Backend:

```powershell
python -m pytest packages/cloud_brain/tests/test_read_model.py -q
python -m pytest apps/api/tests/test_brain_graph_api.py apps/api/tests/test_cloud_brain_api.py -q
```

UI only if `apps/web` changes are included:

```powershell
npm --workspace apps/web run build
```

Expected invariants:

- production store unchanged
- candidate counts separate from verified counts
- rendered counts are viewport/sample budget only
- `pair_edges_sent=0`
- no full Cloud store scan in normal status/graph request

## Commit Strategy

Split into separate commits:

1. backend read-model/API summary
2. tests
3. UI wording/styling

Do not stage generated proof outputs, `data/audits/**`, candidate stores,
payloads, dumps, backup patches, or unrelated Graph Hub/Atlas work.
