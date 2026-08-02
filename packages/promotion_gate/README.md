# Candidate Promotion Gate

Candidate Promotion Gate is a dry-run-only reviewer for candidate Cloud Brain
stores. It estimates what would happen if candidates were reviewed for
promotion, but it never mutates `verified_store_v0`, never writes Local Brain,
and never enables actual promotion.

The gate checks provenance, license/use permission, verification status, dedupe
keys, relation endpoints, case-frame structure, conflicts, and manual approval
requirements.
