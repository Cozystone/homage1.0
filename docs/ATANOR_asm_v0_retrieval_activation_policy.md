# ASM-v0 Retrieval Activation Policy

ASM-v0 can now consult a self-grown construction bank, but the policy keeps
generation bounded and honest.

## Modes

- Product mode: strict. Only `promoted_draft` candidates on allowlisted routes
  can be used.
- Lab mode: exploratory. `reviewed` and `promoted_draft` candidates can be used;
  raw `candidate` items remain preview-only.

## Rejection Reasons

The activation policy rejects candidates for:

- language mismatch
- route mismatch
- high template risk
- high safety risk
- low grounding score on grounded routes
- product route not allowlisted
- product route explicitly disallowed
- missing `promoted_draft` status in Product

## Why Production Active Stays False

Retrieval activation is not production promotion. A candidate may influence an
answer only after policy checks, but it still remains a draft construction. No
verified store write, Local Brain write, candidate promotion, or production
construction activation occurs in this slice.

## Disclosure

When ASM-v0 uses hand-authored fallback, metadata says so. When it uses a
self-grown construction, metadata names the candidate and still reports
`production_active=false`.
