# ATANOR Construction Regression Gate v0

Status: proof-only regression check.

The construction regression gate evaluates a promotion manifest against a fixed prompt set before any future production route can be considered. It compares current conversation behavior with self-grown construction retrieval and flags regressions that would make the system less honest or less safe.

The v0 gate blocks or reports:

- empty answers
- mojibake or broken text
- irrelevant generic fallback text
- production activation metadata
- external LLM or sLLM usage metadata

The regression result returns:

- pass/fail
- worst cases
- eligible candidate ids
- recommendation (`review_ready` or `hold_for_review`)
- rows with baseline answer, candidate answer, chosen answer, and honesty metadata

This gate does not promote candidates. It only provides evidence for a human-reviewed manifest.

UTF-8 cleanup note: visible UI and docs around the construction promotion surface were rechecked for mojibake. Regression metadata remains proof-only and must not enable production activation.
