# GWIP v4 readiness conclusion: fail-closed before execution

## Conclusion

GWIP v4 is paused before seed creation and before any empirical execution.
The reviewed call-order evaluator correction remains sealed at
`28a61ccbe41940b176ccba3cdf6afa71facea51e`, but its v4 one-shot cannot be
prepared on the current history without changing the already-preregistered
meaning of `candidate_fixed_source_guard_controls`.

This is not a new `CAPABILITY_RED`: no v4 attempt was claimed and no v4
episode ran.

## Exact history mismatch

The frozen candidate is:

`51de7aadf188f9889ff1ea051012693e5aa529e2`

The call-order/preregistration seal is:

`28a61ccbe41940b176ccba3cdf6afa71facea51e`

Between those commits, the complete `packages/` tree differs in exactly six
paths:

```
packages/cloud_brain/continuous_learning.py
packages/cloud_brain/surface_projection.py
packages/cloud_brain/tests/test_surface_projection.py
packages/cloud_brain/tests/test_surface_projection_authority_boundary.py
packages/evolution/frozen_oracle.py
packages/evolution/tests/test_frozen_oracle.py
```

They came from two independent, non-GWIP changes:

- `f4f79f22` — cloud-surface evidence binding;
- `7fdf4609` — frozen-oracle signature authority.

The four directly allowlisted GWIP candidate paths are unchanged from
candidate C. That does not satisfy the existing guard: the candidate binding
deliberately covers every tracked byte below `packages/`, because transitive
ATANOR imports can affect execution.

## Exact fail-closed path

The first reproducible stop is
`scripts/gwip_capability_eval.py:_v3_verification_lineage_base`. It binds the
candidate archive digest and also requires the current working `packages/`
tree to equal candidate C. The existing test:

```
python -m pytest scripts/tests/test_gwip_capability_eval.py::test_v3_lineage_binds_attempt_source_and_v3_paths -q
```

fails at `scripts/gwip_capability_eval.py:619` with:

```
CapabilityEvaluationError: v3 candidate/package bytes differ from C
```

A straight v4 clone would encounter the same invariant at every lifecycle
boundary:

| Boundary | Existing guard location | Effect |
| --- | --- | --- |
| lineage initialization | `scripts/gwip_capability_eval.py:612` | rejects working package drift |
| seed creation | `scripts/gwip_capability_eval.py:1534`, `:1540` | rejects before seed write |
| sealed seed load | `scripts/gwip_capability_eval.py:1710` | rejects C-to-seed package changes |
| schedule seal | `scripts/gwip_capability_eval.py:2635` | rejects C-to-schedule package changes |
| pre-attempt rebinding | `scripts/gwip_capability_eval.py:1127` | rejects before attempt claim |
| lineage finalization | `scripts/gwip_capability_eval.py:752` | refuses a preserved-candidate claim |
| read-only readiness | `scripts/gwip_capability_eval.py:3952`, `:3987` | cannot return readiness GREEN |

The full-tree rationale is implemented by
`scripts/gwip_mechanism_eval.py:1367` (`bind_git_candidate_tree`) and its
sealed archive materialization. Treating only the four direct GWIP files as
authoritative would weaken the transitive-source guard.

## Why no automatic workaround was made

The v4 preregistration permits one new behavioral evaluator delta only:
correcting call-order interpretation. The machine contract, frozen candidate,
dataset, thresholds, and all twelve hard gates must otherwise remain
unchanged.

Relaxing the whole-`packages/` equality check, replacing it with a smaller
allowlist, or redefining archive-only equivalence would alter
`candidate_fixed_source_guard_controls`. Even if an archive-only design could
be made safe, it is a new protocol decision and is outside the approved
bookkeeping/output-path work. No such change was implemented.

An isolated evidence history/worktree with candidate-C package bytes, or a
new preregistration explicitly authorizing and adversarially validating a
replacement guard, requires separate approval.

## Artifact census

The v4 machine and human preregistration files exist in commit `28a61ccb`.
All execution outputs remain absent:

- `data/eval/gwip_capability_seed_manifest_v4.json`
- `data/eval/gwip_capability_semantic_schedule_v4.json`
- `data/eval/gwip_capability_attempt_v4.json`
- `data/eval/gwip_capability_raw_evidence_v4.json.gz`
- `data/eval/gwip_capability_authority_v4.tar.gz`
- `data/eval/gwip_capability_receipt_v4.json`

Production remains OFF. v1 and v3 evidence remain immutable. No staging or
graph data changed, and nothing was pushed.
