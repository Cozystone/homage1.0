# Pattern #22 — Guard token overlap reported as factual support

## Outcome

- Outcome: `fixed` for diagnostic honesty only
- Mechanism: `PARTIAL GREEN`
- Capability: `NOT_MEASURED`
- Production answer authority: unchanged; this surface remains diagnostic-only

The Python checker and its deterministic web fallback now call their signal a
lexical match, attach `support_authority=none`, and state
`basis=unverified_token_overlap`. They do **not** establish entailment or bind
an answer to independently verified evidence.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#22`, `check_guard`, `weak_support`, `token overlap`, and `guard checker`
found no prior RED/WIP remediation. The existing stash does not contain the
target paths. Path history contains the original diagnostic implementation
only.

## Revalidated path and failure

The live local route is:

`apps/api/app/routers/guard.py` →
`apps/api/app/services/alpha_services.py::AlphaService.check_guard()` →
`packages/guard/guard/checker.py::check_guard()`.

The web route proxies to that API and falls back to
`apps/web/app/api/_alphaDemo.ts::demoGuardCheck()` when the API is
unavailable. Neither path is consumed as a trusted answer-acceptance gate;
the UI displays its score and claim count.

Before the fix, the Python checker labeled
`Paris is the capital of Germany.` as `supported` when the supplied evidence
said `Berlin is the capital of Germany.`. The five shared tokens were reused
as if they were independent factual support. The deterministic web fallback
made the same category error with the names `weak_support` and `unsupported`.

## Preregistered adversarial and legitimate controls

The focused Python tests were changed before the checker implementation. The
pre-fix run was sealed as:

`python -m pytest -q packages/guard/tests/test_checker.py`

Result: `3 failed`. The old implementation returned `supported` for both the
contradictory case and the legitimate Berlin control and had no authority or
basis fields.

The web fallback was also executed before modification. For
`GraphRAG uses Evidence.` it returned `support=weak_support` and score `85`.

Fixed controls require:

- the contradictory Paris/Berlin pair to have
  `support=lexical_match`, `support_authority=none`, and
  `basis=unverified_token_overlap`;
- the legitimate Berlin/Berlin pair to retain its lexical diagnostic and
  numeric score, while receiving exactly the same zero-authority boundary;
- the web fallback to use `lexical_match_weak` or `no_match`, preserve scores,
  and expose the same authority/basis fields at result and claim level.

## Minimal fix

- Renamed Python result classes:
  `supported` → `lexical_match`,
  `weak_support` → `lexical_match_weak`, and
  `unsupported` → `no_match`.
- Added `support_authority=none` and
  `basis=unverified_token_overlap` to every claim and the overall report.
- Kept the previous score penalties exactly: `0` for the strongest lexical
  bucket, `15` for the weak bucket, and `35` for no match.
- Applied the same non-authoritative names and fields to the deterministic web
  fallback without changing its score behavior.
- Added a focused live API contract test.

Changed files:

- `packages/guard/guard/checker.py`
- `packages/guard/tests/test_checker.py`
- `apps/api/tests/test_guard_api.py`
- `apps/web/app/api/_alphaDemo.ts`
- `docs/ATANOR_PATTERN_22_GUARD_LEXICAL_DIAGNOSTIC_RESULT_2026-07-28.md`

## Verification

- Guard package plus focused live API:
  `python -m pytest -q packages/guard/tests apps/api/tests/test_guard_api.py`
  — `14 passed`.
- Deterministic web fallback was executed through Node's TypeScript loader for
  both buckets:
  `lexical_match_weak` retained score `85`, `no_match` retained score `65`,
  and both returned authority `none` with the unverified-overlap basis.
- Repository web typecheck was attempted. It still fails on pre-existing
  nullability errors in `apps/web/app/page.tsx` and
  `apps/web/app/SplatraField.tsx`; it reports no error in the changed
  `_alphaDemo.ts` file.
- The broader alpha API smoke test reached `5 passed, 1 failed`, stopping on
  an unrelated web-search provider expectation (`search-api` observed versus
  `wikipedia` expected) before its later guard assertion. The new focused
  guard API test isolates and seals this route.

## Honest boundary

This is `PARTIAL GREEN`, not factual verification. The contradictory and
legitimate high-overlap Python examples intentionally retain the same score
of `100`; the difference is that neither may call that score support
authority. Closing the remaining capability gap requires independent
evidence-answer discrimination/source binding such as the EAD line. That work
was not started here.
