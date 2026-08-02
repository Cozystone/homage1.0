# ATANOR Self-Grown Construction Bank v0

Status: proof-only candidate bank.

Self-Grown Construction Bank v0 extracts reusable conversation construction
candidates from local ATANOR artifacts: ASM-v0 outputs, Inner Voice summaries,
Review Queue items, Web Explorer summaries, SPLATRA briefs, and
operator-provided examples.

It does not turn ASM-v0 into a general language model. ASM-v0 still depends on
hand-authored constructions, heuristic route/act inference, semantic grounding,
and local transition surfaces. This bank is the first step toward reducing that
dependency by collecting candidate constructions from real usage and grounded
sources.

Safety invariants:

- external LLM/sLLM: false
- Local Brain write: false
- production verified_store_v0 mutation: false
- candidate promotion: false
- automatic construction promotion: false
- human review required: true
- production_active: false for every v0 candidate

Candidates are exported to the Agentic Review Queue as
`construction_candidate` items. Approval in this slice is review/draft state
only; it does not activate production behavior.

Future work requires a signed construction promotion manifest and explicit
operator approval before any candidate can affect production answer generation.
