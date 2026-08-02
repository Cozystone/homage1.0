# Code Mastery — teaching ATANOR to become a master of code (owner directive, 2026-07-20)

Owner: "ATANOR가 코드의 마스터가 될 수 있게 공부시키자." This is the missing capability the advisor
loop named (Amendment 1: ATANOR can't yet author code, so it can only DECIDE on drafts). Mastering
code moves the authorship share inward — the ratchet that makes ATANOR the drafter, not just the
judge.

## Why code is the RIGHT domain to attack (not a detour)

Code is where every ATANOR strength lines up and every weakness is neutralized:

1. **The situation graph is EXACT, not extracted.** Prose forced heuristic parsing (bAbI 0.127 →
   0.9755 was us building extractors). Code hands over a perfect graph via the AST — comprehension
   is a solved floor (measured 1.000 this session, see below). We start the ladder already standing.
2. **The verifier is PERFECT.** Prose fluency had no oracle (the fluency wall). Code has the test
   suite: a candidate either passes or it doesn't. This is the AlphaGeometry shape (propose →
   verify) that our No-LLM doctrine has always wanted, and code is the one domain where the verifier
   never lies and cannot be flattered. Hallucinated code cannot score — the test rejects it.
3. **We already own the corpus.** 1599 commits of our OWN authorship: license-clean, self-
   supervised, English-only, zero LLM-generated content. Every atomic commit is an (intent → diff)
   pair — exactly the bones→text shape of the language realizer.
4. **We already own the safety gate.** auto_self_modification (staging + no-regression + genesis
   immunity) is precisely the production-side verifier for authored code. Code mastery and safe
   self-modification are the same machinery.

## Measured this session (the honest floor)

- **Comprehension: 1.000** (1800 questions over 300 own-repo functions; `code_reason.comprehension_
  battery`). The battery is non-circular (ground truth = independent ast walk) and earned its keep:
  it caught a real extraction gap (bare `raise` re-raise), now fixed.
- **Authorship: 0.000** (honest stub — ATANOR cannot author yet; `code_reason.authorship_harness`).
  The VERIFIER self-tests at 1.000 on reference bodies and 0.000 on nonsense — the oracle works. So
  0.000 is the true starting line, and the harness that raises it is built.
- **Corpus: 215 atomic (intent → diff) pairs** mined from single-file ≤40-line commits (`scripts/
  mine_code_corpus.py`; 161 py / 49 tsx / 5 ts / 1 rs). The learnable-unit substrate.

## The ladder (each rung a measured gate, contiguous)

- **CM-1 Comprehension** ✓ 1.000 — read structure exactly (params/returns/calls/raises/loops/
  branches/recursion). NEXT: dataflow + type questions ("what type does x hold here", "can this
  return None"), and cross-function (call graph) comprehension.
- **CM-2 Localization** — given a failing test + traceback, name the function/line at fault. Ground
  truth from the traceback; this is comprehension applied to debugging. Corpus: our own fix commits
  (the diff names the culprit).
- **CM-3 Modification** — given a change spec + the target function, produce the edit. The delex/copy
  insight transfers: identifiers are slots, the model learns the STRUCTURAL edit, re-lexicalizes.
  Verifier: the repo's own tests for that function. Start with the 215-pair corpus's smallest hunks.
- **CM-4 Authorship** — given (spec, tests), produce a passing body. Verifier = the tests
  (authorship_harness). Start with the trivial seed suite (add/is_even/last/count_vowels), grow by
  mining docstring+test pairs from the repo. THIS is the number that must move off 0.000.
- **CM-5 Self-authored patches** — CM-4 aimed at ATANOR's OWN failing gates (a bAbI residual, a
  noise cell). Output flows into auto_self_modification (staging + no-regression + constitution).
  Gate: the fraction of accepted self-patches ATANOR drafted itself, rising, honestly reported.

## How the generator gets built (No-LLM, verifier-first)

Not token-by-token LLM emission. The propose→verify loop:
1. **Retrieve** structurally-similar (intent → diff) pairs from the corpus (our ATANOR Index).
2. **Transpose** the retrieved edit onto the current AST (the analogy/structure-transfer organ that
   the brain-like graph already does for facts — here over code graphs).
3. **Propose** a small set of candidate diffs (search, not single-shot).
4. **Verify** each against the tests; keep only passers (the perfect oracle prunes hallucination).
5. **Ratchet** — a passer becomes a new (intent → diff) corpus example; the loop self-supervises.

This is generate-and-verify with a real oracle, so correctness is bounded by the verifier, never
asserted. It also composes with the advisor loop: an advisor can DRAFT a candidate diff, but it
faces the identical verifier + constitution — no advisor code is trusted, only tested.

## Guardrails (inherited, non-negotiable)
- auto_self_modification.IMMUTABLE stands: authored code may never target the moral core or any gate.
- Untrusted candidate code is verified in a SUBPROCESS with a timeout, never exec'd in-process; the
  test/spec is fixed so a candidate cannot rewrite the test to pass itself.
- Every authored patch reaching the live tree passes staging tests + sealed-gate no-regression.

## First experiments (next, <1 day each)
1. CM-1+: add dataflow/type/call-graph question families to the comprehension battery; measure.
2. CM-4 seed grow: mine (docstring, test) pairs from the repo into the authorship suite (target
   ~100 tasks) so the 0.000 has real headroom to move against.
3. CM-3 retrieval baseline: for the 215-pair corpus, measure how often nearest-neighbor edit
   transposition + verify produces a passing modification (the first non-zero authorship signal).
