# ATANOR 4D Spatiotemporal Ontology — Verification Layer Design

Transplant a 4D (3D PHFE graph + time axis **T**) deterministic verification layer onto
ATANOR v0.3, inspired by ATLASky-AI's TruthFlow/4D-STKG (see docs/atlasky_adoption_plan.md).
Goal: every knowledge node/edge carries temporal validity, and the engine deterministically
cross-checks **point-validity** and **continuity** over time — suppressing the *temporal-
contradiction / staleness* class of error, while preserving No-LLM, no-embeddings, GPU-0,
~11 MB-engine determinism.

## 0. Honest position (no hype)
- v0.3 = 3D phase-holographic graph: measures **static** concept associations only.
- 4D layer adds: each fact has a validity interval on T; a deterministic temporal verifier rejects
  facts that contradict the existing timeline and answers "as of time t".
- **Scope claim, precisely:** this structurally suppresses **temporal contradictions and stale
  facts** (two simultaneous CEOs; a fact whose validity has expired). It does NOT "perfectly
  suppress all hallucination" — a wrong fact with internally-consistent dates still needs the other
  RMMVe modules (LOV/POV/WSV/resonance). Stating this is mandatory (project honesty rule).
- **Ultralight framing (precise):** "GPU 0, ~11 MB" = the *engine* footprint (deterministic code,
  zero model weights). The *knowledge store* grows with knowledge (currently 66 MB) — that is
  expected and separate. The temporal verifier adds **only interval arithmetic** (O(1)–O(log n)),
  no matrix multiply, no weights → the ultralight property is preserved.

## 1. The 4D node/edge schema (compact temporal block)
case_frames/relations already carry `created_at` / `updated_at` (ingest time). Add ONE optional
temporal block per fact:

```
temporal = {
  "t_observed":    iso8601,    # when a source asserted it (defaults to created_at)
  "t_valid_from":  iso8601|null,  # validity interval start (null = -inf / unknown)
  "t_valid_to":    iso8601|null,  # validity interval end  (null = +inf / still valid)
  "t_as_of":       iso8601|null,  # the date the SOURCE speaks about (e.g. "as of 2019")
  "t_confidence":  0.0-1.0,    # how precisely T is known (1.0=explicit date, low=inferred)
  "t_grain":       "year|month|day|unknown",
  "supersedes":    frame_id|null,     # the fact this replaces in the same slot
  "superseded_by": frame_id|null
}
```
Byte cost: ~5 short values + 2 ids ≈ 40–70 bytes/fact. For the current ~5.5 k case_frames that is
< 0.5 MB added to the *store* (not the engine). Bounded and trivial.

## 2. Deterministic temporal verification (the core — no neural)
Three pure-arithmetic checks:

1. **Point validity** `valid(fact, t)` ⇔ `t_valid_from ≤ t ≤ t_valid_to`. O(1).
2. **Functional-slot non-overlap (continuity).** Some predicate-slots are *functional* — at most one
   value at a time (e.g. `(org)–CEO→(person)`, `(country)–대통령→(person)`). For all facts sharing a
   functional slot, their validity intervals **must not overlap**. Overlap ⇒ **temporal
   contradiction** ⇒ reject/flag (deterministic interval-overlap test). Non-functional slots (e.g.
   `(person)–authored→(book)`) are exempt.
3. **Supersession chain.** When a new functional-slot fact post-dates an existing one, set
   `old.t_valid_to = new.t_valid_from`, link `supersedes/superseded_by`. The timeline becomes an
   ordered chain instead of contradictory coexistence — old facts are retained (long-term memory),
   not destroyed.

"Functional slot" is declared by **graph schema** (a relation-type property `functional: true`),
NOT a hand-written answer table — it is a linguistic/ontological fact about the relation, the same
allowed category as agentive-suffix morphology (see two-hard-architecture-rules).

## 3. T extraction (honest feasibility)
Measured on the live store: **only ~11% of facts carry an explicit year in source text**; the rest
get `t_observed = created_at` with low `t_confidence`. So:
- Explicit-date facts → real semantic validity interval, high confidence.
- Date-less facts → open interval `[-inf,+inf]`, `t_confidence` low, `t_grain=unknown`.
- The verifier only **enforces** non-overlap when both competing facts have confident intervals;
  otherwise it flags-for-review rather than auto-rejecting (no false determinism on unknown dates).

## 4. Integration: a Temporal-Consistency module in the RMMVe cascade
The 4D layer is one verification module in the cascade already built
(`scripts/rmmve_shadow_scorer.py`), mapping to ATLASky's MAV temporal agent:
- **TCV (Temporal Consistency Verification)**: `C_tcv = 1` if the candidate's interval does not
  overlap a confident functional-slot fact; `0` (contradiction) ⇒ flag/reject.
- Ranked **early** (pure interval math = cheap), after LOV, before expensive POV/WSV.
- Output stays in the promotion/measurement namespace (Contract C1) — never answer evidence.

## 5. What 4D unlocks (the product goals, honestly)
- **Permanent long-term memory:** supersession never deletes — `valid_to` closes a fact, history is
  queryable. `V(t)` = the graph as-of time t (time-travel / audit).
- **Hyper-personalization:** a per-user private graph layer with its own temporal facts; `V(t)`
  tracks how a user's state/preferences evolved → personalization that is *auditable*, not a black box.
- **High-value B2B private module:** isolated tenant graph + temporal verifier gives a deterministic
  **audit trail** ("we asserted X from source S, valid 2021–2023") — exactly the regulated-industry
  need ATLASky targeted (aerospace). Determinism + provenance + time = defensible B2B claim.
- **Decentralized fit:** interval math is local and cheap → runs on edge/peer nodes (Brain Link
  P2P) without GPUs, unlike LLM inference.

## 6. Phased build (reversible, shadow-first)
- **P-4D.0 (GREEN):** add the optional `temporal` block to the schema as non-required; backfill
  `t_observed=created_at`; parse explicit dates where present. Measure coverage/confidence. No
  behavior change.
- **P-4D.1 (GREEN):** TCV module in the *shadow* RMMVe cascade (read-only); measure how many
  real candidates it would flag as temporal contradictions. Side-report only.
- **P-4D.2 (RED, operator/Codex gate):** enable supersession writes + `V(t)` query API on the
  candidate store; promotion gate (C2) consults TCV + drift==stable.
- **P-4D.3 (RED):** per-tenant private graph layer + temporal audit export (B2B).
Each step backed up; revert = delete sidecar / drop temporal block.

## 7. Open questions for Codex (vision-sync + No-LLM watch)
1. Where is the relation-type schema, to declare `functional: true` without a rule table? (file:line)
2. Does any existing path destructively overwrite facts (would break "never delete" long-term memory)?
3. Is `supersedes` chaining safe against the multiple merge paths Codex flagged for P1-③?
4. Does TCV anywhere let a temporal score leak into answer selection (Contract C1)?
5. Minimal `V(t)` query that doesn't bloat the 11 MB engine — index design?
