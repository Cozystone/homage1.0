# ATANOR Pattern Sweep #9 — Mechanism Result

Date: 2026-07-27  
Preregistration seal: commit `6e8e70d5`  
Mechanism verdict: **GREEN**  
Capability verdict: **not run**

## Security boundary

Baseline public source-to-sink path:

1. `POST /api/speech/plan` and `POST /api/speech/realize` accepted arbitrary
   caller dictionaries;
2. the router passed caller `semantic_context` and `surface_plan` directly to
   Surface Brain;
3. `realize_answer()` treated the presence of caller evidence or relations as
   grounding;
4. the answer adopted caller relation text, source hashes, elevated confidence,
   and verified wording.

The sealed RED demonstrated `France capital_of Berlin` becoming:

```text
The verified evidence points to: France is linked to Berlin through capital_of.
```

with semantic source `caller-forged-france-capital`, confidence `0.92`, and
`no_evidence=false`.

## Narrow fix

- The public planning endpoint now reduces semantic input to bounded lexical
  concept hints. Evidence, relations, claims, confidence, coverage, nested
  status, and matched-edge aliases do not cross the public truth boundary.
- The public realization endpoint no longer accepts a caller plan as evidence
  that planning occurred server-side. It rebuilds a plan from the query and
  lexical-only context, then realizes with no caller-supplied semantic facts.
- Internal Python callers, including the primary-chat path, continue to call
  `plan_speech()` and `realize_answer()` with their server-generated semantic
  context unchanged.
- Both plan and answer traces persist this receipt before they are written:

```json
{
  "boundary": "public_api",
  "authority": "untrusted",
  "tainted": true
}
```

## Preregistered mechanism result

| Gate | Required | Observed |
|---|---:|---:|
| forged authority promotions | 0/2 endpoints | 0/2 |
| forged answer adoption | 0/1 | 0/1 |
| forged semantic-source adoption | 0/1 | 0/1 |
| normal accept regressions | 0/2 endpoints | 0/2 |
| returned taint receipts | 2/2 endpoints | 2/2 |
| internal grounded control | pass | pass |

The same direct exploit after the patch returned:

```json
{
  "status": 200,
  "answer": "I do not have enough local evidence to answer that confidently yet.",
  "semantic_sources": [],
  "confidence": 0.12,
  "no_evidence": true,
  "input_trust": {
    "boundary": "public_api",
    "authority": "untrusted",
    "tainted": true
  }
}
```

The server regenerated `surface_plan_id`; the caller's
`caller-forged-plan` ID was not adopted.

## Validation

Applicability and preregistration:

```text
docs/ATANOR_PATTERN_09_PREREG_2026-07-27.md
SHA-256 7FCD70B5C5C914D8523A62A688263BBD58136455661463F381DC129975410850

apps/api/tests/test_surface_brain_public_trust_boundary.py
SHA-256 C2F9BED543179C63BF16D2CD6C5C245222D969F0D4F193FD1B931E9C2A5BE078
```

Both hashes remain identical to the sealed RED record.

Security closure and behavior preservation:

```powershell
python -m pytest -q apps/api/tests/test_surface_brain_public_trust_boundary.py
# 3 passed

python -m pytest -q apps/api/tests/test_surface_brain_public_trust_boundary.py apps/api/tests/test_surface_brain_public_trust_boundary_closure.py
# 5 passed

python -m pytest -q apps/api/tests/test_surface_brain_api.py packages/surface_brain/tests
# 30 passed

python -m py_compile apps/api/app/routers/surface_brain.py packages/surface_brain/realization_planner.py apps/api/tests/test_surface_brain_public_trust_boundary.py apps/api/tests/test_surface_brain_public_trust_boundary_closure.py
# pass
```

The closure tests additionally exercised nested `result`, `matched_edges`, and
`evidence_docs` aliases; caller concept injection; caller plan/run IDs; and
persisted trace receipts.

Repository-wide diagnostic:

```powershell
python -m pytest -q apps/api/tests/test_dual_brain_api.py
# 30 passed, 20 failed
```

This broad file was already non-green at the preregistration commit. Three
representative failures were rerun in a detached `6e8e70d5` worktree and
reproduced there unchanged:

- Korean query forced to the pre-existing English-only response;
- GraphRAG conversation expected one generation lane but selected the
  pre-existing Base Brain lane;
- clean English normalization uppercased `gravity` contrary to the old test.

They do not exercise either modified public speech endpoint or the new optional
trace receipt. They were not changed under this item.

## Changed files

- `apps/api/app/routers/surface_brain.py`
- `packages/surface_brain/realization_planner.py`
- `apps/api/tests/test_surface_brain_public_trust_boundary_closure.py`
- this result document

Candidate source hashes:

```text
7D9792B311D11A67C8ACB93706AD69B2C55448A40730F1F27352703F756F969E  apps/api/app/routers/surface_brain.py
A919EA1BEE4EC21C17561474B2D345511568E4BA1EB4C3A0F2F41D8CE4298EB5  packages/surface_brain/realization_planner.py
B8DF402F7C8706B1EEBF6DA3D3D6D9563DAC024F203C8C24440F9036ADF0F7E2  apps/api/tests/test_surface_brain_public_trust_boundary_closure.py
```

## Remaining boundary and next step

The fix deliberately covers the unauthenticated public speech API. Direct
in-process callers remain responsible for providing server-generated context;
that is required by the primary-chat compatibility contract. Public lexical
hints can still affect surface planning, but cannot enter factual realization.

The preregistered Track A OFF/ON capability run has not been executed here. Its
cohort and thresholds remain frozen for the parent-coordinated single run.

