# Pattern #15 — Frozen Oracle colocated unkeyed seal

## Outcome

- Outcome: `fixed`
- Mechanism: `GREEN`
- Capability: `NOT_MEASURED` — Critic quality was not re-benchmarked.

## 0-stage prior-attempt audit

`git stash list`, `git branch --list`, and `git log --all --grep` searches for
`#15`, `frozen_oracle`, `unkeyed seal`, `co-located`, and `offline oracle`
found no prior RED/WIP remediation. Existing commits introduced the oracle and
later text cleanup only; the sole stash does not contain the target path.

## Revalidated path and invariant

`ensure_oracle` trusted `seal == sha256(canonical(pairs))`. The oracle pairs,
seal, and public `_seal` implementation were colocated, so a writer could edit
the exam, recompute the seal, and regain `verified=True`. That directly
invalidated the claim that the evolving evaluator could not rewrite its exam.

The invariant is: a writer with the oracle file and repository code must not be
able to authorize changed pairs. Legitimate untouched seed data and the
existing Critic scoring/promotion behavior must remain usable offline.

## Pre-fix reproduction

`python -m pytest -q packages/evolution/tests/test_frozen_oracle.py::test_attacker_cannot_recompute_a_colocated_unkeyed_seal`

Result before fix: failed because the edited oracle with a freshly recomputed
SHA-256 seal loaded as `verified=True`.

## Minimal fix

- The SHA-256 seal remains a diagnostic corruption checksum but no longer
  grants authority.
- Oracle authority is now a detached Ed25519 signature over canonical
  `{pairs, version}` bytes, verified against a pinned public key.
- The one-time signing private key was generated outside the repository for
  this sealed seed and discarded; no private signing material is in code,
  data, tests, environment instructions, or git state.
- A missing oracle is created from the compiled signed seed record.
- An exact legacy v1 seed is safely migrated to that same signed v2 record.
  Any changed legacy pairs remain unverified even with a recomputed SHA seal.
- Missing `cryptography`, malformed signatures, wrong keys, and invalid
  signatures all fail closed.

Changed files:

- `packages/evolution/frozen_oracle.py`
- `packages/evolution/tests/test_frozen_oracle.py`
- `docs/ATANOR_PATTERN_15_FROZEN_ORACLE_SIGNATURE_RESULT_2026-07-28.md`

The ignored local `data/evolution/frozen_oracle.json` was restored to its
original v1 bytes; runtime migration is exercised in a temporary test path and
no local data artifact is part of the patch.

## Verification

- Original exploit, legitimate scoring, wirehead rejection, tamper rejection,
  and legacy migration:
  `python -m pytest -q packages/evolution/tests/test_frozen_oracle.py packages/evolution/tests/test_critic_integrity.py packages/evolution/tests/test_critic_arena.py`
  → `17 passed`.
- Syntax/buildability:
  `python -m compileall -q packages/evolution/frozen_oracle.py packages/evolution/tests/test_frozen_oracle.py`
  → passed.
- Patch hygiene: focused `git diff --check` → passed (only the repository's
  existing CRLF normalization warning for `frozen_oracle.py`).

The original issue no longer reproduces: changing the bad set and recomputing
the public SHA seal leaves the detached signature invalid, returns
`verified=False`, and blocks promotion. The untouched signed seed still
supports sensible-Critic scoring; a flat wirehead remains rejected; and the
exact legacy seed migrates to a verified signed record.

## Remaining boundary

This closes oracle-file forgery by a process that can write colocated data and
read repository code. As with every in-process Python guard, arbitrary code
that can modify the verifier module or interpreter itself is outside this
file-level boundary; code-level Critic proposals remain separately constrained
by `critic_integrity` and reviewed promotion.

Changing the human oracle now requires an explicitly reviewed new public-key
pin and detached signature. There is intentionally no automatic re-seal path.
