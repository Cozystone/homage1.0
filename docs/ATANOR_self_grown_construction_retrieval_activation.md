# ATANOR Self-Grown Construction Retrieval Activation v0

Status: proof-only retrieval activation.

This slice lets ASM-v0 retrieve self-grown construction candidates, but it does
not promote them to production constructions. The activation path is deliberately
split into retrieval, preview, and use.

## Candidate Status Rules

- `candidate`: preview only. Never used for answer generation.
- `reviewed`: usable in Lab retrieval only.
- `promoted_draft`: usable in Product only on safe allowlisted routes.
- `production_active`: remains false in this slice.

## Product Allowlist

Product retrieval can use `promoted_draft` candidates only for:

- `greeting_smalltalk`
- `local_cloud_brain_explanation`
- `limitation_question`
- `voice_status`
- `splatra_request`
- `agentic_os_request`

Product does not use construction candidates for memory writes, private
requests, production mutation, host execution, or Tier4 execution requests.

## Honesty Metadata

Every retrieval result reports:

- whether a self-grown construction was retrieved
- whether it was actually used
- candidate status
- activation reason
- rejection reasons
- template risk
- grounding score
- safety risk
- `production_active=false`
- `production_construction_activation=false`

Hand-authored fallback remains visible when candidate policy does not allow use.

## Future Gate

Real production construction activation requires a future signed construction
promotion manifest, explicit operator review, and separate regression gates.
