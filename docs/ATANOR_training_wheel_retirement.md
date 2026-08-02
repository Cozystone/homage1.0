# ATANOR Training-Wheel Retirement Inventory

> **Sequencing note (2026-07-25):** this remains a bounded retirement inventory,
> not the immediate global work queue and not authorization for another census
> sweep. Its recommended order is a local backlog. The active model path is
> NL→goal compiler + scientific-knowledge staging → E4 → paired E5; a listed
> wheel should be touched now only if it blocks that measured path.

Owner directive (2026-07-22): the fear is **neuro growth tipping into an LLM / the model getting
heavy**. The remedy has two arms: (1) enforce the architectural lines as *machinery* — see the
[Neuro Ledger](../packages/neuro_ledger/) budget audit; (2) **retire the hand-rule training wheels**
(regex-as-decision) as soon as a learned organ can carry the decision, per the doctrine
*rules are training wheels*.

This document sweeps for **REGEX-AS-DECISION** points across the answer path and classifies each as
**exempt** (constitutional) or **retire** (with a priority + a replacement design). A regex that only
**extracts a feature** for a learned scorer is *not* a wheel — it is a probe, and stays.

## Scope of "wheel"
- **Wheel (retire):** a regex / hardcoded token-list whose match *is* a routing or answer decision.
- **Feature extractor (keep):** a regex whose match becomes an input to a *learned* scorer that makes
  the decision (e.g. `relational_router`, the new `intent_router`).
- **Exempt (constitutional):** the moral 0th gate, the English-only I/O boundary, and the LAD surface
  layer (particles / endings / construction lists) — these are doctrine-exempt and must NOT be
  "learned away".

---

## Inventory

| # | Wheel | File:line | Decision it makes | Exempt? / Retire priority | Replacement design |
|---|-------|-----------|-------------------|---------------------------|--------------------|
| 1 | **realcity english-intent ladder** (greeting fullmatch / personal-life / `_SELF_SITUATION`) | `apps/api/app/routers/realcity_agent.py` (was ~114, ~174, ~180) | social vs personal_unknowable vs self_situation vs knowledge | **RETIRED (this pass)** | ✅ learned `intent_router` (multinomial logistic over cheap features); regexes demoted to feature extractors; kill-switch `ATANOR_INTENT_ROUTER`; byte-identical fallback |
| 2 | **base_brain `_classify_intent` token lists** | `packages/base_brain/pack_loader.py:292-302` | `compare` / `summarize` / `define` / `explain` / `clarify` from `["what is","define",…]` membership | **RETIRE — high** | learned sibling of `intent_router` over the same features + a define/explain/compare/summarize head; **note:** the define-vs-relational sub-decision here is *already learned* (`relational_router.py`). Currently Korean-mixed → couple with the English-only cleanup (#4) before wiring, to avoid a KO/EN 5-class mismatch |
| 3 | **zero_user_answer English self-model routing** | `packages/base_brain/zero_user_answer.py:1024,1027,1032` (`\byou\b\|are you`, `conscious\|sentient\|aware`, `alive`) | routes a "are you conscious / alive" question to the self-model lane | **RETIRE — high** | a learned self-vs-world / self-model-topic classifier over cheap features (2nd-person + predicate cues), trained on a generated paraphrase set; the *answers* stay grounded in the self-model graph |
| 4 | **zero_user_answer Korean intent / audience / limitation regexes** | `packages/base_brain/zero_user_answer.py:826,923,1020,1038-1046,1072` | how-to / limitation / audience-level / self-address routing via Korean cues | **RETIRE — high (DELETE, not relearn)** | ATANOR is English-only since 2026-07-18; these Korean-cue decision regexes are dead lanes → remove them at the I/O boundary rather than learn them. Track under the English-only enforcement effort |
| 5 | **realcity_learning `dialogue_act`** | `packages/realcity_learning/harvest.py:59-73` | greeting / closing / question / build-on / answer tag (feeds the register pool) | **RETIRE — medium** (borderline LAD-surface) | a learned discourse-act tagger over cheap surface features; low stakes (it tags *register*, not answers). If kept, label it explicitly as LAD-surface. The moral gate in the same file is exempt (#E1) |
| 6 | **realcity `_answer_from_perception` phrasing selectors** | `apps/api/app/routers/realcity_agent.py:133-160` (who/where/doing/scene sub-branches) | which grounded-perception phrasing to emit once `self_situation` is chosen | **RETIRE — low** | a tiny learned sub-router over the same self_* features; low value because every branch is already grounded in perceived state (it only picks phrasing) |
| 7 | **realcity knowledge-branch misroute / abstain detectors** | `apps/api/app/routers/realcity_agent.py:214-219` (`_RELATIONAL_LOOKUP`, "don't hold a grounded", web-deflection phrases) | drop base_brain's abstention / misroute / web-deflection instead of passing it through | **RETIRE — low/medium** | best fixed *upstream*: have base_brain return explicit structured flags (`answer_kind`, `intent`, `grounded`) — it already partially does (`answer_kind == "honest_abstain_relational"`); finish the structured contract so the adapter reads a boolean, not a phrase regex |

## Exempt (constitutional — must NOT be learned away)

| # | Item | File | Why exempt |
|---|------|------|-----------|
| E1 | Moral 0th gate | `apps/api/app/routers/realcity_agent.py:323` (`_HARMFUL_NORM`); `packages/realcity_learning/harvest.py:32` (`MORAL_BLOCK`) | Genesis-immune moral core (federation 0th gate). A regex here is a *floor*, not a wheel; it fails closed and is never softened by a learned scorer |
| E2 | English-only I/O boundary | I/O guard ("I can only speak English") + Kiwi morphology retirement | Constitutional I/O boundary (English-core architecture, 2026-07-18). Deciding language at the boundary is a floor |
| E3 | `parse_relational_shape` / `RELATION_VOCAB` | `packages/base_brain/relational_lookup.py` | **Feature extractor**, not a decision — its structural parse feeds the *learned* `relational_router`. Keep |
| E4 | `intent_router` / `relational_router` regex probes | `packages/base_brain/intent_router.py`, `relational_router.py` | **Feature extractors** feeding the learned scorers. Keep |
| E5 | LAD surface layer | `packages/lad_morphology/*`, `harvest.anonymize/normalize_template/extract_topics` | LAD surface exemption (particles / endings / construction lists; anonymization transforms). Not answer-composition decisions |

---

## Retirement done this pass — #1

**What:** the realcity adapter's english-intent decision.
**How (the proven relational-router pattern):**
- New organ `packages/base_brain/intent_router.py` — a **multinomial-logistic** scorer over 20 cheap
  regex/structural features, classes `social | personal_unknowable | self_situation | define |
  relational`. **Regexes extract features only**; the trained weights make the decision.
- Corpus: deterministically generated, **789 samples** (629 train / 160 held-out) across all five
  classes, saved under `data/intent_router/` (`paraphrases.jsonl`, `heldout.jsonl`, `weights.json`).
- **Held-out accuracy 1.00** (per-class 1.00) on the generated separable corpus — honest caveat:
  this is a synthetic, separable corpus (same regime as `relational_router`); the number is a
  reproducibility check, not a claim about open-web intent noise.
- Wired into `realcity_agent._answer` via `_route()`, which the branch *bodies* consume unchanged.
- **Kill-switch** `ATANOR_INTENT_ROUTER=0` and **graceful fallback** (absent/broken artifacts →
  `None`, no self-heal at request time) restore the **original hand-regex ladder byte-identically**
  (pinned by `apps/api/tests/test_realcity_intent_router.py`).
- Registered in the Neuro Ledger (`intent_router`, enforced tier, ~145 params / 5 KB — well under the
  25M single-organ cap).

**Regression:** the four gates (`test_realcity_agent`, `test_relational_lookup`,
`test_realcity_learning`, `packages/base_brain/tests`) held at **150 passed → 150 passed** (zero new
failures); +21 new tests (router holdout, byte-identical kill-switch, ledger audit) green.

## Next (recommended order)
1. **#2** base_brain `_classify_intent` — highest remaining leverage; do it *after* #4 so the router is
   clean English-only 5-class + a define/explain/compare/summarize head.
2. **#4** delete the dead Korean decision lanes (English-only enforcement).
3. **#3** the English self-model classifier.
4. **#7** finish base_brain's structured answer contract so the adapter reads flags, not phrase regexes.
5. **#5 / #6** low-stakes register/phrasing sub-routers, last.
