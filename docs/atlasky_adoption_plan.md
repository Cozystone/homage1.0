# ATLASky-AI → ATANOR Adoption Plan

Source: Awill et al., "ATLASky-AI: physics-based trustworthy verification of LLM-generated
spatiotemporal knowledge" (TechRxiv 2025 / Expert Systems w/ Applications 2026,
DOI 10.1016/j.eswa.2026.131801). Full PDF read (docs/ATLASky-AI.pdf, 15p).

## 1. Why it matters
ATLASky's thesis = **verify-before-integrate** ("TruthFlow"): every candidate fact must pass a
verification cascade before entering the knowledge graph. This is ATANOR's exact philosophy
(`verify_sentence` gate before `VerifiedStore.accumulate`). They formalize what we left as a
binary gate.

**Decisive difference (in ATANOR's favor):** ATLASky *generates with an LLM, then verifies*.
ATANOR has **no LLM** — generation is graph-native (decomposer + 발화 graph). So we adopt their
**verification architecture**, not their generator. We also replace their embedding module with
**wave/phase resonance** (no embeddings). Net: "ATLASky's verification rigor, fully no-LLM /
no-embedding / physics-native."

## 2. ATLASky architecture (as read)
- Candidate fact `dk = (e, r, a, s)` extracted (by LLM in theirs; by **decomposer** in ours).
- **TruthFlow** = RMMVe (cascade) + AAIC (adaptive loop).
- **RMMVe**: 5 modules `M = {LOV, POV, MAV, WSV, ESV}` run in **ranked cheap→expensive order**.
  Each `Mi` yields `C_i(dk) = wi·(αi·Metric1 + (1-αi)·Metric2) ∈ [0,1]`.
  **Early termination**: if `C_i ≥ θi`, jump straight to aggregation (skip rest).
  Aggregate `Ctotal = mean(activated C_i)`. Decision `δ = 1 iff Ctotal ≥ Θ` → integrate; else
  reject / flag for manual review.
  - **LOV** Local Ontology: precision/recall of extracted e,r vs local ontology.
  - **POV** Public Ontology: accuracy/coverage vs a public ontology.
  - **MAV** Multi-Agent (Temporal, Spatial, 4D-Consistency agents) with **Shapley-value** credit
    → consensus + reliability score.
  - **WSV** Web Search: recall/F1 of corroboration on the live web.
  - **ESV** Embedding Similarity: cosine(new, existing) + anomaly-detection-rate.
- **AAIC**: real-time adaptive control of `wi, θi, αi`.
  - **CGR-CUSUM** drift detector: `Si(t)=max(0, Si(t-1)+(pi(t)-µ0-k))`, k=0.05, fire when `Si≥h` (h=5).
  - Weight update (exp-weights): `wi(t+1)=wi(t)·exp(-γ·Si(t))`, normalized so Σwi = (#modules-1).
  - Threshold update (gradient ascent on `U(θ)=TPR-λ·FPR`): `θi += η·∂U/∂θi`, η=0.1.
- **4D STKG**: vertices are **time-aware** `(e, a, (X,Y,Z,T))`; `V(t)` = active at time t.
- Results: verification 70–93%; KG creation error 15% → 2.5%.

## 3. ATLASky → ATANOR mapping
| ATLASky | ATANOR today | Action |
|---|---|---|
| LLM extractor → candidate `(e,r,a,s)` | `decompose_sentence` → concepts/relations/case_frames | keep ours (no LLM) ✅ |
| TruthFlow verify-before-integrate | `verify_sentence` (binary, **no score**) | upgrade to scored cascade |
| RMMVe ranked cascade + early-term + `Ctotal` | **missing** (single binary gate) | **ADOPT** — = our P1 "grounding score" |
| LOV (local ontology P/R) | does candidate's entities/predicate exist in our verified store? | = **`predicate_anchor`** (already built in P0!) |
| POV (public ontology) | Wiktionary / Wikidata type check | new cheap module |
| MAV (temporal/spatial/4D + Shapley) | **wave-interference referent-type resonance** | physics-consistency module = ours, on-brand |
| WSV (web corroboration) | SearXNG / web_search | wrap as a **scored** module (recall/F1) |
| ESV (embedding cosine + anomaly) | **no embeddings** (6-float nodes) | replace with **phase-chord resonance similarity** |
| `Ctotal ≥ Θ` → integrate | promotion threshold | = P1 grounding-score → promotion gate |
| AAIC + CGR-CUSUM (drift, auto-tune) | **missing** | **ADOPT** — fixes live-store daemon drift |
| 4D STKG temporal validity | case_frames atemporal | add `valid_from/valid_to/version` |

## 4. Phased adoption (maps onto current P0/P1 work)
**Phase A — RMMVe cascade = the P1 grounding score (read-only design first).**
Replace the binary gate with a ranked, early-terminating cascade emitting `Ctotal ∈ [0,1]`:
`LOV(predicate_anchor, cheap) → POV(public ontology) → resonance-consistency(wave) →
WSV(SearXNG corroboration) → phase-similarity`. Persist `grounding_score = Ctotal` +
`activated_modules` on each candidate. Promotion uses `Ctotal ≥ Θ`. **No new metric philosophy —
ATLASky validates the exact P1 design Codex and I converged on.**

**Phase B — AAIC/CUSUM drift monitor (fixes today's measurement confound).**
Today's P1 delta was polluted because the background learner mutates the live store. Add a
**CUSUM monitor** on P0 metrics (`predicate_anchor`, `leak`, `coverage`) + per-module performance:
`Si(t)=max(0,Si(t-1)+(pi-µ0-k))`, fire at `Si≥h`. On fire → freeze measurement / flag for review,
and auto-tune module weights (exp-weights) + thresholds (gradient ascent). Gives clean before/after
AND adaptive verification.

**Phase C — temporal validity on case_frames.**
Add `valid_from/valid_to/version` (4D STKG idea) → honest time-varying attribution
(e.g. "current CEO"), connecting to Codex's entity-specific-fact concern.

## 5. Non-negotiables to preserve
- **No LLM**: the extractor stays `decompose_sentence`, never an LLM. ATLASky's LLM box is replaced
  by our graph-native generation. (mutual-monitoring guardrail)
- **No embeddings**: ESV → **phase/wave resonance** similarity, keeping nodes at 6 floats.
- **No rule tables / answer tables**: modules score *grounding*, never inject answer strings.
- All changes start as **read-only design + scratch experiments**, backed up, reversible.

## 6. Open questions for Codex review
1. Module ranking for ATANOR (cheap→expensive): is `LOV→POV→resonance→WSV→phase-sim` the right
   order, and which are safe to early-terminate on?
2. Is `Ctotal = mean(activated)` right for us, or weighted-by-Shapley from the start?
3. CUSUM target `µ0`: fixed baseline vs rolling — given our store legitimately grows, how do we
   distinguish healthy growth from drift we must freeze on?
4. Does adding `Ctotal` scoring risk re-introducing a "score that becomes an answer gate" anti-pattern?
5. Temporal validity: minimal schema vs full 4D — what's the smallest honest version?

## 7. Codex consult verdict (2026-06-30)
**Adopt — but as P1's scoring layer, not a separate track.** Hook point on the ingestion path
(continuous_learning.py:350): AFTER `verify_sentence` hard gate, with early-termination just
BEFORE `store.accumulate` (accumulate:361), because predicate_anchor / case-frame quality only
exist after case_frame creation (decomposer:499).

- **Q1 module order:** `hard gate → LOV/local quality → resonance/phase local checks → POV
  cached/public ontology → WSV web`. The current `verify_sentence` source/license/dedupe/mock/shape
  checks stay as **hard reject** (verification_gate:129), NOT folded into the score.
- **Q2 aggregation:** demo starts with `mean(activated)` (or static weighted mean). Shapley /
  exp-weights only AFTER E1 validation logs exist. For P1 just persist `module_scores,
  activated_modules, ctotal, decision_basis`.
- **Q3 CUSUM µ0 = quality-rate rolling baseline, NOT store size.** Healthy growth = leak=0,
  negative-fixture anchor=0, stable rejection mix, normal case_frames_added. Drift = live hash
  changes mid-measurement / negative anchors appear / predicate_anchor with no evidence basis.
  Today's daemon pollution = "measurement isolation drift" (this is the thing CUSUM must catch).
- **Q4 answer-gate firewall:** `Ctotal` = integration/promotion eligibility ONLY, never answer
  evidence. Answer path still requires fact/evidence span. Score metadata may attach to
  `VerificationDecision.to_verification` (verified_fact_retrieval:62) but `answer_text/person/
  target_answer`-type fields are forbidden there.
- **Q5 minimal temporal schema:** `case_frame.temporal = {observed_at, valid_from, valid_to,
  as_of, temporal_confidence, source_time_text}` as OPTIONAL metadata first (leave
  case_frame_required_fields:78 unchanged).

**3 BLOCKER guards (mutual-monitoring):**
1. POV must not become a hand-written role/answer glossary → that's a rule table.
2. WSV must not pull a single web sentence as the answer → composer bypass.
3. phase/resonance must not promote evidence-less candidates as "plausible" → hallucination score.
Avoid these three and ATLASky folds cleanly into P1.

## 8. Implementation status (2026-06-30, all GREEN / read-only / backed up)
- **Drift monitor** `scripts/measurement_drift_monitor.py` — AAIC/CGR-CUSUM slice. Validated:
  stable / measurement_isolation_drift (mid-measurement mutation) / quality_regression. CUSUM
  baseline now externalizable via `--baseline` (Codex review #1).
- **RMMVe shadow scorer** `scripts/rmmve_shadow_scorer.py` — TruthFlow cascade slice. Live result:
  promote 15 / flag 8 / abstain 37; every promote carries an agent-bearing frame (0 violations);
  negatives never promote; firewall clean (no answer fields, decision enum asserted). `local_role_
  consistency` is a REQUIRED module for attribution (Codex review #2); `score_scope` field marks it
  as a partial slice (review #5).
- **Codex review:** PASS, 0 BLOCKER. B1–B5 pass. Polish #1–#5 applied + a found abstain/flag
  ordering bug fixed.

## 9. P1 runtime-absorption design (DESIGN ONLY — wiring is a RED step, operator/Codex gate)
Goal: move the shadow scorer + drift monitor onto the real ingestion path
(`continuous_learning.py:350`, after `verify_sentence` hard gate, before `store.accumulate:361`),
**without** ever letting the score reach the answer path. Two runtime contracts Codex required:

**Contract C1 — score is integration-eligibility only (never answer evidence).**
- Persist the cascade result in a **separate namespace** on the candidate: `grounding = {ctotal,
  module_scores, activated_modules, decision, decision_basis, score_scope}` — NOT in
  `concepts/relations/case_frames/evidence` fact fields.
- Runtime assert at the boundary (reuse `_iter_keys` recursive scan): the `grounding` block must
  contain **none** of `FORBIDDEN_ANSWER_KEYS`, and `decision ∈ ALLOWED_DECISIONS`.
- The answer path (`dual_brain.py:1911` relations→facts, `:4163` payload) must read fact/evidence
  only and **must not import the grounding block** — enforce with a one-line guard: a non-abstain
  answer requires ≥1 `answer_evidence` from fact/case_frame, never from `grounding`.

**Contract C2 — promotion gate uses Ctotal; measurement gate uses drift monitor.**
- Promotion of a candidate to verified staging requires `ctotal ≥ Θ` AND `local_role_consistency==1`
  for attribution (required module), AND drift monitor `classification == stable` on the target
  store (so we never promote during a `measurement_isolation_drift`).
- AAIC auto-tune (weights/θ via CUSUM) stays OFF until E1 validation logs exist (Codex Q2); P1 only
  records `module_scores` for later tuning.

**Rollout (each step reversible, shadow-first):**
1. Shadow-attach: run the cascade on real candidates in `run_once`, write `grounding` to a
   **side report only** (no store field yet). Compare shadow decisions vs current gate. (GREEN)
2. Add `grounding` block to the **candidate** store rows behind a flag, promotion still manual.
   Drift monitor gates the measurement. (RED — operator/Codex approval)
3. Wire promotion gate to `ctotal ≥ Θ` + drift==stable. (RED)
Phase B AAIC auto-tune and POV/WSV/phase real modules come after, each separately gated.
