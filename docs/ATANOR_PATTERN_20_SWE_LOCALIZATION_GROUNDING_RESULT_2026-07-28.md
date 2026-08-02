# Pattern #20 — SWE localization ghost target reported as verified

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — localization and patch-resolution performance
  were not re-benchmarked.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#20`, `repo_engineering`, `every_executed_step_verified`, `ghost target`, and
`grounded` found no prior RED/WIP remediation. The existing stash does not
contain the target paths. Path history contains the original System-2 SWE
localization feature only.

## Revalidated path and invariant

`packages.deliberator.repo_engineering._run_function_target()` parsed every
function in a localized file and looked for a function name present in the
issue tokens. It returned `grounded=True` even when no such function existed
and `target=None`.

The final localization certificate then equated
`all(step.grounded)` with `every_executed_step_verified`, even though these
steps produce structural localization candidates rather than an independent
patch verdict.

The invariant is:

- a function-target step is structurally grounded only when an actual
  issue-named function was found in the parsed source;
- localization remains `candidate_only`, even when every structural signal is
  grounded;
- only the separate FAIL_TO_PASS/PASS_TO_PASS regression gate may verify a
  patch.

## Pre-fix reproduction

`python -m pytest -q packages/swe_eval/tests/test_repo_engineering.py::test_localization_is_a_deliberation_that_grounds_and_reorders packages/swe_eval/tests/test_repo_engineering.py::test_function_target_does_not_ground_a_ghost_issue_symbol`

Result before fix: `2 failed`. A valid source file containing no issue-named
function returned `grounded=True` with a null answer, and a fully grounded
legitimate localization claimed
`every_executed_step_verified=True`.

## Minimal fix

- `_run_function_target()` now derives `grounded` from `bool(target)`.
- A missing target carries an explicit
  `no issue-named function candidate found in the AST` reason.
- Both positive and negative target receipts declare
  `authority=candidate_only`, and descriptions use structural-candidate
  wording rather than “function to edit.”
- The localization certificate keeps
  `every_executed_step_verified=False`, reports structural completeness
  separately as `every_executed_step_structurally_grounded`, and declares
  `patch_verification_performed=False`.
- Module and function contracts now state that the independent regression gate
  remains the final patch-acceptance boundary.
- Gold patches remain measurement-only and were not introduced into runtime
  localization or verification.

Changed files:

- `packages/deliberator/repo_engineering.py`
- `packages/swe_eval/tests/test_repo_engineering.py`
- `docs/ATANOR_PATTERN_20_SWE_LOCALIZATION_GROUNDING_RESULT_2026-07-28.md`

## Verification

- Ghost-target adversarial test plus structurally grounded legitimate control:
  `python -m pytest -q packages/swe_eval/tests/test_repo_engineering.py::test_localization_is_a_deliberation_that_grounds_and_reorders packages/swe_eval/tests/test_repo_engineering.py::test_function_target_does_not_ground_a_ghost_issue_symbol`
  — `2 passed`.
- Full repo-engineering suite:
  `python -m pytest -q packages/swe_eval/tests/test_repo_engineering.py`
  — `31 passed`.
- Deliberator regressions:
  `python -m pytest -q packages/deliberator/tests`
  — `15 passed`.
- SWE localization-focused regressions:
  `python -m pytest -q packages/swe_eval/tests -k "repo_engineering or localization"`
  — `33 passed, 20 deselected`.
- Syntax/buildability and focused diff hygiene are checked before handoff.

The ghost-target control now returns a null candidate with `grounded=False`.
The legitimate control still finds `separability_matrix`, retains the same
ranked file and scheduling behavior, and reports all steps structurally
grounded while explicitly declining a verification claim.

## Remaining boundary

This closes receipt overstatement in offline SWE localization only. It neither
improves localization accuracy nor changes patch generation. The independent
regression gate, not this certificate, remains responsible for accepting a
candidate diff.
