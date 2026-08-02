# ATANOR Self-Grown Construction Promotion Manifest v0

Status: proof-only gate, not production activation.

Self-grown construction candidates can now be gathered into a promotion manifest, but v0 deliberately stops before product behavior changes. The manifest records which reviewed candidates are eligible, why other candidates were rejected, the route and language scopes, threshold values, the regression prompt set, and a rollback manifest id.

Required invariants:

- `production_construction_activation=false`
- `production_store_mutated=false`
- `local_brain_write=false`
- `external_llm=false`
- `external_sllm=false`
- `signed_manifest_required=true`
- `rollback_required=true`
- raw candidates are not promotable

Eligibility rules:

- Candidate status must be `reviewed` or `promoted_draft`.
- Candidate must have source references.
- Route and language must be inside the manifest scope.
- Route must be product-safe.
- Naturalness, grounding, template-risk, and safety-risk thresholds must pass.
- Even eligible entries keep `activation_allowed=false` in v0.

The sign endpoint is a signature preview only. It can mark a manifest as `signed`, but it still does not create a production activation path. Real activation remains a future operator-controlled gate.

UTF-8 cleanup note: the promotion manifest surface was rechecked after cleanup. The manifest remains non-activating, and production construction activation stays blocked until a future signed activation dry-run is explicitly designed and reviewed.
