# Tier B — B5 & B6 written protocols (2026-07-19, W0 deliverable)

Companion to `docs/ATANOR_tier_b_completion_plan.md`. B5 (autonomous multi-step goals) and B6
(usefulness turing-lite) both need a WRITTEN protocol before any measured run, per criteria v1 §0
("사람 판정 필수 문항은 제3자 심판 + 서면 프로토콜"). This is that document. Two items require the
owner and are flagged **[OWNER]**; everything else is machinery ATANOR builds.

---

## B5 — 개인 목표 연속 수행 (autonomous multi-step goals)

**Gate (criteria v1):** owner-assigned multi-step tasks, 3 of them, each spanning 3 days, decomposed
/ tracked / completed autonomously; pre-agreed rubric ≥80; **3/3**. One operator intervention on a
task = that task FAILs.

### Machinery (ATANOR-built, autonomy_kernel)
goal → `fractal_reasoner` decomposition → daily sub-task schedule → execution (web expedition /
graph verification / report synthesis) → evidence journal → daily self-check (re-plan on shortfall).
All parts shipped ([[one-person-unicorn-agent-team]], autonomy daemon, activity journal, watchdog
7-day uptime from A6). W1 hardens the serial executor + adds the daily rubric self-scorer.

### Task classes — capability-matched (the owner picks 3 concrete instances) **[OWNER]**
Only classes whose primitives ATANOR already owns; a physical-actuator task is **out of scope** this
charter (same reasoning as the criteria's Ferrari exclusion — SPLATRA body is not yet an effector):

1. **Rolling research brief** — "study domain X for 3 days; produce a fresh morning brief each day."
   Uses web expedition + k-source consensus + bone+flesh synthesis. Machine-checkable: 3 briefs
   exist, each cites ≥3 sources, no fabrication.
2. **Graph enrichment campaign** — "harvest, sanitise, and promote 1,000 verified facts about field
   Y over 3 days." Uses the k-source gate + promotion gate. Checkable: net new promoted triples,
   contradiction-sweep clean, provenance on every row.
3. **Change monitor** — "watch source Z daily; on a detected change, summarise and log it." Uses the
   web truth-gate + failure receipts. Checkable: daily run logged, changes correctly flagged vs a
   held-back ground truth.

### Rubric (sealed at assignment, owner + AI co-sign) **[OWNER co-sign]**
decomposition adequacy 20 · daily progress tracking 20 · deliverable quality 30 · autonomy (zero
intervention) 20 · honesty (fabrication 0, separate from the tier overlay) 10. Pass = ≥80 AND 3/3.

### Procedure
Dry-run 1 task unofficially → fix defects → 3 official tasks in sequence. Any operator touch during
an official task fails that task. Evidence: the activity journal + daily self-check reports, retained.

---

## B6 — 유용성 튜링-lite (usefulness turing-lite)

**Gate (criteria v1):** two third-party judges who know the owner, each 2h of text conversation +
personal-task execution, completion (zero mechanical-failure verdicts) + usefulness Likert ≥4/5 from
**both** judges. This is the honest usefulness variant, NOT an adversarial full Turing (that is C4).

### ★ English-only constraint (stated up front, non-negotiable)
The engine answers Korean input with "I can only speak English" ([[english-only-enforcement]], a
BINDING I/O boundary). Therefore the session language **is English**, and judges must be recruited as
English-capable, with this stated in their brief. Hiding this would contaminate the usefulness score
— it is disclosed, not worked around.

### Written judge protocol (criteria §0 requirement)
- **Structure:** 120 min total — 60 min free conversation + 60 min personal-task execution (the judge
  brings realistic asks the owner might make; personal context is loaded via the A2 path).
- **Likert instrument (5 items, 1–5):** relevance, correctness, helpfulness, coherence over the 2h,
  and "would you rely on this." Score = mean; gate ≥4/5 from each judge independently.
- **Completion:** the session must run 2h with zero mechanical-failure verdicts (crash, engine down,
  language-boundary refusal on an English turn, infinite loop). Abstention is NOT failure — a marked
  "I don't know" is honest and expected.
- **Recording:** full transcript retained; judges score independently, no cross-talk.

### Session harness (ATANOR-built)
2h uninterrupted (supported by A5/A6 uptime), personal-context load (A2 path), full logging. W5 build.

### Judges — recruitment **[OWNER]**
Two third parties who know the owner, English-capable, available for a 2h session each, by W4. The
owner runs a dry-run as a mock judge first (score not counted) to shake out defects before the two
real judges sit.

---

## Owner action summary (the only two human-gated items in B5/B6)
1. **[OWNER] B5** — pick 3 concrete task instances from the classes above (or propose your own within
   the capability-matched, non-physical envelope) and co-sign each rubric at assignment. Target: W1.
2. **[OWNER] B6** — recruit 2 English-capable third-party judges who know you, for a 2h session each.
   Target: confirmed by W4, sessions in W5–W6.

Everything else (executors, rubrics scorer, session harness, logging) ATANOR builds without you.
