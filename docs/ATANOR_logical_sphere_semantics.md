# ATANOR Logical Sphere Semantics

Logical Sphere counts are split into four different count domains. They must not be presented as one graph size.

## Verified Production Graph

Verified production counts come from `verified_store_v0` only.

- `verified_concepts`
- `verified_relations`
- `verified_evidence`
- `verified_case_frames`

These counts change only after an explicit promotion into production knowledge. Candidate-only learning must not increase these values.

## Candidate Overlay Graph

Candidate overlay counts come from unpromoted candidate learning output.

- `candidate_concepts`
- `candidate_relations`
- `candidate_evidence`
- `candidate_case_frames`
- `candidate_surface_items`
- `candidate_cgsr_items`
- `candidate_rhfc_items`

These values can grow during candidate-only learning. They are reviewable learning output, not production knowledge.

## Working Memory Temporary Graph

Working Memory counts describe temporary attached answer/session context.

- `working_memory_nodes`
- `working_memory_relations`
- `working_memory_fragments`

Working Memory is temporary. It is not persistent verified knowledge and does not write to Local Brain by default.

If the backend does not own the session state, these counts should be reported as unknown rather than inferred from production or candidate totals.

## Rendered Viewport Sample

Rendered and materialized counts describe the current viewport or render sample.

- `rendered_nodes`
- `rendered_edges`
- `materialized_nodes`
- `materialized_edges`
- `active_chunks`
- `visible_scale_chunks`
- `virtualization_enabled`

These are not total graph counts. They are bounded by chunk, LOD, viewport, and frame budgets.

## Chunk And LOD Virtualization

The Logical Sphere may represent a large verified graph through chunk and LOD virtualization. This means the UI can show a bounded frame while the backend preserves larger verified and candidate counts separately.

Pair candidates may be implicit. Sending pair edges as rendered edges must remain explicit and bounded; normal graph/status responses should keep `pair_edges_sent=0`.

## Why Verified Counts Do Not Increase During Candidate-Only Learning

Candidate-only learning writes to candidate stores. It does not promote those candidates. Until a separate promotion gate accepts candidates into `verified_store_v0`, production verified counts remain unchanged.

## Why Candidate Counts Are Not Production Knowledge

Candidate counts are useful because they show current learning progress. They are also deliberately labeled as unpromoted so they cannot be mistaken for verified facts.

## Why Rendered Counts Are Not Total Graph Size

Rendered and materialized counts are viewport samples. They answer "what is visible now?" not "how much knowledge exists?"

## Future UI Labels

Recommended labels for a later UI-only slice:

- Verified Logical Nodes
- Verified Stored Relations
- Candidate Concepts
- Candidate Relations
- Working Memory Temporary Nodes
- Rendered Viewport Sample
- Virtualized Full Graph
