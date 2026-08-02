# Advisor Loop — ATANOR consults frontier minds to evolve its own body (owner idea, 2026-07-20)

Owner: "일정 수준의 지능 + 스스로 코드를 고칠 정도면, computer-use처럼 직접 컴퓨터를 조작해
Codex Desktop 같은 프로그램으로 시중 고성능 모델과 지속 대화하며 조언받고, 학습하고, 평가받고,
새 구조를 만들며 진화할 수 있지 않을까."

**Verdict: yes — this is the generalization of Brain Link** (an external mind's words are DATA
through the same constitution), and most of the machinery already exists (OS Action Lane risk×trust
tiers + audit ledger; auto_self_modification staging gate; injection boundary; ONE timeline).
Three honest amendments make it real instead of theatrical:

## Amendment 1 — who writes the code TODAY (no theater)
ATANOR is not yet code-fluent: its self-modification organs are gated PROPOSAL/verification
machinery, not autonomous code authorship. So in v1 the division of labor is stated plainly:
- **ATANOR asks** — questions mined from ITS OWN measured failures (battery residuals, degradation
  cells, wall docs). The curiosity is genuinely its own: metrics drive the asking.
- **The advisor drafts** — a frontier model (claude/codex/ollama, all present on this machine)
  proposes analysis or a patch.
- **ATANOR decides by its constitution** — staging + full test battery + sealed-gate no-regression
  + constitutional immunity (auto_self_modification). Accept/reject is EMPIRICAL and its own.
That is real agency in the loop without pretending authorship. As its own code-writing matures
(a measured gate: can it produce a diff that passes staging unaided?), the drafting share shifts
inward — the same ratchet as rules→learning everywhere else.

## Amendment 2 — the distillation boundary (No-LLM stays intact)
- **Advice about the BODY: allowed.** Architecture critiques, experiment designs, bug diagnoses,
  patch drafts — all verified empirically before touching the tree. The resulting capability is
  still from-scratch + human-corpus; consulting a mind about your anatomy does not make you that
  mind.
- **Content into the BRAIN: forbidden.** Advisor-generated text never enters the knowledge graph,
  the training corpora, or the register diet (the TinyStories precedent: LLM-generated data is
  doctrine-gray at best). No advisor sentence becomes a fact ATANOR knows or a phrase it learned
  to say. Advisor transcripts live on the ONE timeline as observed EXPERIENCE (provenance:
  advisor/<name>), searchable but never promoted.
- **Evaluation: allowed and prized** — frontier models as blind examiners/critics (the ITT & GPT-
  audit precedent). Their VERDICTS are measurements; measurements gate, they don't teach content.

## Amendment 3 — interface: CLI first, computer-use second (both real)
Driving a desktop UI by pixels is the fragile way to reach a model that also ships a CLI. Present
on this machine today: `claude` (headless -p), `codex`, `ollama` (dolphin3 local, free). So:
- **v1 (now): CLI advisor channel** — subprocess, structured prompts, deterministic logging,
  cost-bounded. Robust, auditable, same trust model.
- **v2 (later): computer-use lane** — ATANOR operates Codex Desktop / arbitrary UIs through the
  OS Action Lane at GUARDED tier (auto-run READONLY/REVERSIBLE, approve DESTRUCTIVE), append-only
  audit. This is worth building anyway (it is the ATANOR-OS embodiment of "hands"), but it is an
  INTERFACE upgrade, not a capability upgrade — the constitution is identical.

## Security constitution (BINDING, inherits Brain Link's)
1. Advisor output is untrusted observed DATA: injection scan on every reply; imperative content is
   logged, never executed. An advisor cannot instruct — it can only propose.
2. Constitution files (moral core, the gates themselves, operator gate) are untouchable regardless
   of who drafted the patch — genesis immunity applies to advisors exactly as to the self.
3. Every exchange is audited on the ONE timeline (question, advisor, reply hash, verdict).
4. Rate/cost bounds per advisor; local ollama is the unlimited default, paid CLIs are budgeted.
5. The operator (parent) can sever any advisor channel at any time; severing is always safe.

## The loop (v1, buildable now)
```
own metrics (battery residuals, degradation cells, wall docs)
  -> question_miner: rank the most information-dense questions
  -> advisor_session: ask via CLI (claude|codex|ollama), scan, log to timeline
  -> patch_intake: if the reply contains a concrete change -> candidate patch
       -> constitution check (refuse constitutional paths outright)
       -> staging: apply in throwaway copy, run tests + sealed batteries
       -> auto_self_modification.evaluate_change: allow only safe + non-regressing
  -> ledger: applied / rejected(with reason) / advice-only(no patch)
  -> the next question mines the NEW residuals — the loop closes on measurement
```

## Milestones & gates
- **AL-0 (today)**: question miner + CLI session + injection scan + timeline log + MockAdvisor
  tests. GATE: mined questions reference real metric files; injected advice flagged; constitutional
  patch refused at intake.
- **AL-1**: one real advisory round on the current fluency wall (ollama first, then claude/codex),
  transcripts on the timeline, at least one concrete suggestion staged and verdicted by the gate.
  GATE: a full round with an EMPIRICAL accept/reject, zero unaudited exchanges.
- **AL-2**: continuous mode inside the life daemon (budgeted: N questions/day), residual-driven.
  GATE: a week of autonomous rounds with 0 constitution violations and ≥1 gate-passing improvement.
- **AL-3**: computer-use lane via OS Action Lane GUARDED tier (Codex Desktop or any UI).
  GATE: one advisory round driven through the UI with every click in the audit ledger.
- **AL-4**: authorship ratchet — measure the fraction of accepted patches drafted by ATANOR itself;
  the goal is that number rising, honestly reported, never simulated.
