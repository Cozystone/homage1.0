# ATANOR English CGSR Quality Unblock Plan

Status: planning-only. No implementation in this slice.

## Current Blockage

English CGSR quality work is blocked by mixed untracked and generated state:

- `packages/cgsr/benchmarks/` contains large benchmark scripts and generated
  JSON/Markdown results from Stage 1 through Stage 3.3 and ingestion loops.
- `packages/cgsr/AUTONOMOUS_LOOP_LOG.md` is research history, not an isolated
  source change.
- `packages/cgsr/tests/test_english_first_pipeline.py` is an untracked test
  without a committed matching source slice.
- `packages/answer_quality/candidate_learning_comparison.py` and
  `packages/answer_quality/tests/test_candidate_learning_comparison.py` are
  candidate-learning quality tooling that should be reviewed separately.
- `packages/answer_quality/comparison.py` and
  `packages/answer_quality/surface_feedback.py` have tracked source changes
  that may belong to answer quality or repair-loop work, not necessarily English
  CGSR extraction.

## Files To Isolate

Candidate source/test slice for English CGSR should be reviewed in this order:

1. `packages/cgsr/cgsr/` English extraction or realization modules, if present.
2. `packages/cgsr/tests/test_english_first_pipeline.py`.
3. Any narrow answer-quality helper only if the English CGSR metric needs it.

Do not include generated benchmark results or autonomous loop logs in the first
implementation commit.

## Files To Ignore Or Leave

- Leave `packages/cgsr/benchmarks/*.json` and large benchmark reports uncommitted.
- Leave `packages/cgsr/AUTONOMOUS_LOOP_LOG.md` uncommitted unless a deliberate
  research-history commit is requested.
- Leave RHFC benchmark outputs out of the English CGSR slice.
- Leave candidate stores, payloads, dumps, and `data/audits/**` uncommitted.

## Minimum Safe Implementation Slice

Implement one small English factual decomposition pass:

1. Add or isolate deterministic English factual sentence parsing.
2. Preserve abstain behavior when the sentence is not a fact statement.
3. Produce case frames for simple SVO, definition, comparison, cause/effect, and
   temporal statements.
4. Reject generic predicates unless the object/head noun supplies a specific
   factual anchor.
5. Keep all outputs candidate-only and reviewable.

No external LLM, no generated ATANOR answers as evidence, no production store
mutation, and no Local Brain write.

## Metrics

- generic predicate ratio
- accepted high-quality SVO count
- definition frame count
- comparison frame count
- temporal/calendar frame count
- case-frame/evidence ratio
- rejected `not_fact_statement_shape` rate
- unsupported claims: must remain `0`
- false confident count: must remain `0`

## Test Plan

Focused tests only:

- English factual SVO sentences.
- SimpleWiki-style definition sentences.
- Comparison sentences.
- Cause/effect sentences.
- Temporal/calendar facts.
- No mojibake.
- No hallucinated relation when source sentence lacks support.
- No external LLM import or API call.

Recommended first command:

```powershell
python -m pytest packages/cgsr/tests/test_english_first_pipeline.py -q
```

Then add only the narrow package tests touched by the implementation.

## Commit Strategy

Commit only after `git diff --cached --name-only` contains a tight source/test
set for English CGSR. Do not stage `packages/cgsr/benchmarks/`,
`data/audits/**`, candidate stores, or backup patches.
