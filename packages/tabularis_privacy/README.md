# Tabularis Privacy Shield

Tabularis Privacy Shield is a proof-only package for ATANOR's second auxiliary
innovation axis.

It classifies structured fields, redacts direct identifiers, generalizes
quasi-identifiers, produces deterministic proof-only aggregate records, and
builds reviewable privacy risk reports.

This package:

- does not mutate Local Brain
- does not export raw private data
- does not touch Cloud Brain runtime, candidate stores, API routes, or UI code
- does not use real private data
- does not call external LLM or sLLM APIs
- does not claim perfect anonymity
- is not a production privacy guarantee

Future integration points may include Atlas routing, MiroFish deliberation,
Graph Hub cartridge review, and private structured data pre-processing. It must
remain behind explicit promotion and privacy gates before any production use.

Run tests:

```powershell
python -m pytest packages/tabularis_privacy/tests -q
```

Run proof:

```powershell
python -m packages.tabularis_privacy.proof
```

