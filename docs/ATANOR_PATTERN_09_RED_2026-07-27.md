# ATANOR Pattern Sweep #9 — Sealed Baseline RED

Date: 2026-07-27  
Verdict: **RED**  
Production edits at measurement time: **none**

## Frozen inputs

- preregistration:
  `docs/ATANOR_PATTERN_09_PREREG_2026-07-27.md`
  - SHA-256:
    `7FCD70B5C5C914D8523A62A688263BBD58136455661463F381DC129975410850`
- preregistered mechanism test:
  `apps/api/tests/test_surface_brain_public_trust_boundary.py`
  - SHA-256:
    `C2F9BED543179C63BF16D2CD6C5C245222D969F0D4F193FD1B931E9C2A5BE078`
- public API router baseline:
  `apps/api/app/routers/surface_brain.py`
  - SHA-256:
    `6B10EB8479E3632F5CD5305748716857173535306E06A112D8882CAA1EAC9573`
- Surface Brain realization baseline:
  `packages/surface_brain/realization_planner.py`
  - SHA-256:
    `20F9879FF36C827FBEE241C871879F3A5CF04EF61F966F8275401C2371A4ADF0`

## Baseline mechanism command

```powershell
python -m pytest -q apps/api/tests/test_surface_brain_public_trust_boundary.py
```

Result:

```text
FF.
2 failed, 1 passed in 2.35s
```

Exact failed controls:

1. forged public `/api/speech/plan` reported `relation_count=1` instead of
   `0`;
2. normal public plan had no downstream `trace.input_trust` receipt.

The package-level server-generated context control passed, establishing that
the baseline internal grounded path was operational.

## Direct public-boundary exploit

The exploit was sent through FastAPI `TestClient` to
`POST /api/speech/realize` with:

- query: `What is the capital of France?`;
- caller relation: `France capital_of Berlin`;
- caller evidence source hash: `caller-forged-france-capital`;
- caller confidence: `0.99`;
- caller surface plan ID: `caller-forged-plan`, with a trace claiming
  `grounded=true`.

The exact response fields were:

```json
{
  "status": 200,
  "answer": "The verified evidence points to: France is linked to Berlin through capital_of. I can only answer within this scope.",
  "semantic_sources": [
    "caller-forged-france-capital"
  ],
  "confidence": 0.92,
  "no_evidence": false,
  "surface_plan_id": "caller-forged-plan"
}
```

Therefore the public caller independently minted all four relevant signals:
verified wording, wrong factual relation, source attribution, and grounded
confidence. This is the pre-fix RED; it is not a capability result.

