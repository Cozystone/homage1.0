# ATANOR Spark Chamber

`packages/spark_chamber` is a proof-only controlled-chaos sandbox. It tests
whether bounded uncertainty, contradiction, reversible mutation, and
self-reference can generate useful candidate insights.

It is not a consciousness claim, not AGI, not production mutation, and not
random corruption of real knowledge. It does not write Local Brain, mutate
candidate stores, mutate approved payloads, execute generated code, perform
production code replacement, or call external LLMs.

All Spark Chamber outputs are candidate-only and require review. Mutations are
applied only to copied proof fixtures and are blocked when the chaos budget is
exceeded.

Run tests:

```powershell
python -m pytest packages/spark_chamber/tests -q
```

Run proof:

```powershell
python -m packages.spark_chamber.proof
```

Proof outputs and triage reports are audit files under `data/audits/spark_chamber/`
and must not be committed.
