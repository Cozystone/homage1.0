# Pattern #13 — Surface Projection self-scored readiness

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — this establishes an authority boundary, not a generation-quality lift.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#13`, `surface_projection`, `candidate fields`, `self-score`, and `readiness`
found no prior RED/WIP remediation. The sole stash does not contain the target
package; the path has only its original candidate-surface feature commit.

## Revalidated path and invariant

`project_decompositions_to_surface` marked a candidate `safe_for_cgsr`,
`safe_for_rhfc`, and `confidence=0.8` solely because that same candidate carried
a predicate, case roles, and an evidence hash. A caller-shaped
`DecompositionResult` could therefore use its own fields to mint readiness.

The invariant is: candidate fields may propose a projection, but only an
evidence reference independently bound by the upstream sentence verification
step may authorize generation-facing readiness. A decomposition that passed
that existing verification step must continue into the candidate-only
Surface/CGSR/RHFC path.

## Pre-fix reproduction

`python -m pytest -q packages/cloud_brain/tests/test_surface_projection_authority_boundary.py`

Result before fix: `2 failed`. The forged candidate was accepted as safe with
confidence 0.8, and the projector had no independent evidence-binding input.

## Minimal fix

- The projector now defaults to no authority and accepts an explicit set of
  upstream-verified evidence references.
- Candidate shape and evidence presence remain necessary, but are no longer
  sufficient; the evidence hash must also appear in the independent set.
- Unbound proposals receive zero confidence, remain out of the returned safe
  candidate list, and increment `unsupported_claims`.
- `CloudSurfaceLearningLoop` populates the set only after the existing
  `verify_sentence(...).status == "verified"` branch, using the verified
  server-side `SourceSentence.source_hash`.

Changed files:

- `packages/cloud_brain/surface_projection.py`
- `packages/cloud_brain/continuous_learning.py`
- `packages/cloud_brain/tests/test_surface_projection.py`
- `packages/cloud_brain/tests/test_surface_projection_authority_boundary.py`
- `docs/ATANOR_PATTERN_13_SURFACE_READINESS_RESULT_2026-07-28.md`

## Verification

- Security closure, direct legitimate control, and real learning-loop control:
  `python -m pytest -q packages/cloud_brain/tests/test_surface_projection_authority_boundary.py`
  → `3 passed`.
- Existing projector and downstream adapter:
  `python -m pytest -q packages/cloud_brain/tests/test_surface_projection.py packages/cgsr/tests/test_cloud_surface_adapter.py`
  → `3 passed`.
- Syntax/buildability:
  `python -m compileall -q packages/cloud_brain/surface_projection.py packages/cloud_brain/continuous_learning.py packages/cloud_brain/tests/test_surface_projection_authority_boundary.py`
  → passed.
- Patch hygiene: focused `git diff --check` → passed (only the repository's
  existing CRLF normalization warning for `continuous_learning.py`).

The original issue no longer reproduces: candidate-shaped fields with no
upstream binding yield zero accepted candidates and one unsupported claim. The
legitimate direct control retains confidence 0.8 when its evidence ref is
independently supplied, and the real candidate-only learning loop produces a
ready Surface candidate only after its existing sentence verifier accepts the
source.

The pre-existing
`test_verified_payload_grows_candidate_surface_and_rhfc_without_production_mutation`
currently fails at `semantic.concepts_added == 0` before the changed projection
boundary; the modified call occurs only after semantic accumulation. A new
English real-loop control passes and directly covers the modified wiring. No
adjacent semantic-ingestion behavior was changed to mask that unrelated
failure.

## Remaining boundary

The upstream deterministic verifier establishes licensed, traceable,
structurally usable candidate evidence; it does not prove factual truth. The
projection remains candidate-only and production promotion remains separately
review-gated.
