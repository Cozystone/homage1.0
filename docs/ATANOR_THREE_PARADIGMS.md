# ATANOR Three Paradigms — Gemini's ceiling-breakers, audited and engineered

Owner (2026-07-15): Gemini names three next-generation paradigms to break the structural ceiling —
(1) embodied active learning in a closed loop with the world, (2) dynamic DSL expansion /
meta-induction, (3) cross-domain geometric transfer in high-dimensional phase space. "이걸 읽고
고도화해봐." This document is that elevation: each paradigm audited against what ATANOR *actually
runs*, then engineered into a verify-gated, measurable track. Honesty rules apply: receipts over
rhetoric, and one of Gemini's three we have **already run naively and measured why it fails** — that
receipt shapes the corrected design.

**Verdict up front:** all three arrows point the right way. Two of the three already have living
organs here (Gemini is describing, from first principles, machinery we built piecemeal — good
convergent validation). The elevation is not to bolt on three new systems, but to (E) close one loop
that is currently open, (M) grow the language and its search *together* behind an admission gate,
and (G) lift analogy from node-space to motif-space. Each gets a falsifiable metric; none gets a
superintelligence claim.

---

## Paradigm 1 → E-track: conjecture-driven active sensing (the open loop, closed)

**Gemini's claim.** A closed system learning from a static graph + collected corpus hits a ceiling;
new information requires acting on the world and importing the friction (errors, refusals, results)
as learning signal.

**Audit — largely right, and largely already ours in pieces (receipts):**
- Autonomous web expedition loop (search→browse→distil→gate→learn→journal) — shipped, running.
- Hypothesis minting closed loop (자가정제 3단계) — mints open questions from graph tension.
- **Failure-receipt engine** (`autonomy_kernel/intrinsic_drive.py`) — refusals/junk steer future
  exploration; closed-loop by design.
- Miss-curriculum flywheel (benchmark misses become the next study list).
- Reasoning-VM **world-corrects** (F-ladder: prediction error repairs induced procedures).
- L1 register active-learning (just shipped): `thinnest_registers()` steers harvest budget.
- The doctrine already says it: **"훈련 말고 세상에 풀기"** (world-roaming BINDING, 2026-07).

*Honest correction to the framing:* "정보 엔트로피의 법칙" is dressing — the sound core is simply
that a finite corpus has diminishing returns and new bits come from interaction. No physics claim
needed. Also "물리적 센서/무제한 상호작용": we have perception (camera, OWLv2) and the OS action
lane, but embodiment is a separate track with its own trust tiers — E-track stays scoped to
**web/API/human-dialog probing**, which is where the measurable yield is.

**The genuine gap Gemini exposes:** our roaming is **coverage/curiosity-driven**; our conjectures
(hypothesis minter, soon the discovery engine) do not yet **drive** the roaming. The loop exists but
is not *closed around hypotheses*: nothing today takes a specific conjecture, designs the probe that
would refute it, executes it, and feeds the verdict back.

**E-track design (engineering, all organs exist):**
1. **Probe planner**: for each typed CONJECTURE (from the D-ladder / hypothesis minter), synthesize
   the *cheapest discriminating probe* — a targeted search query or API call whose result is expected
   to differ under conjecture-true vs conjecture-false. (Uses the existing search orchestration v2.)
2. **Execute under the existing safety envelope**: robots/ToS-respecting fetch, injection_guard
   (swallowed text is DATA), k-source consensus before any belief change — active probing is an
   attack surface; the guards are non-negotiable.
3. **Verdict ledger**: probe outcome → conjecture status moves (CONJECTURE → GROUNDED/REFUTED), and
   *refutations are first-class learning* — they feed the failure-receipt engine and the
   miss-curriculum, steering both the next probes and the next harvest.
4. **One unified error ledger**: benchmark misses, abstentions, refuted conjectures, junk receipts —
   today four separate streams — merge into one curriculum queue that ranks what to probe/learn next
   (highest expected information first).

**Metric (falsifiable, ablation-shaped):** `closed_loop_gain` — precision@verify and discovery_yield
with conjecture-driven probing ON vs OFF over the same wall-clock. If active sensing doesn't beat
passive roaming on evidence-per-probe, the track is not earning its complexity. Also
`refutation_latency` (time from conjecture to verdict) — the honest speed of science.

---

## Paradigm 2 → M-track: grow the language and its search TOGETHER (the measured lesson)

**Gemini's claim.** The reasoning VM invents formulas only inside a fixed DSL; a real leap needs the
system to define new operators/control structures itself, "compiled to machine level."

**Audit — the ceiling is real, but we already ran the naive version and it FAILED, measurably:**
- **Receipt (2026-07-14):** adding the `i1` primitive to the DSL enabled factorial induction **but
  regressed guided search on `square` from 17 → 31 candidates** (crowded quadratic feature bucket).
  We reverted, honestly. The lesson is now a design law: **expressiveness growth without matching
  search-model growth is NET NEGATIVE** — a bigger language means a bigger haystack unless the
  needle-finder grows with it. Gemini's paradigm as stated (just add operators) re-runs this failure.
- **Receipt (already-built half):** the induction flywheel *already promotes induced procedures into
  the working basis* — `induction_flywheel.py` rebuilds "the working basis from disk; compositional
  towers become possible without any hand grow_basis." Operator self-extension by **composition**
  exists; what's missing is *governed growth* of the primitive set itself.

**M-track design — DSL admission gate + coupled search growth:**
1. **Procedure → named primitive promotion**: a PROVEN induced procedure (falsifier-grade: held-out
   pass, world-corrects stable) is promoted to a first-class primitive with its **own feature
   signature** in the PMI search model — so the searcher learns *when to reach for it*, keeping the
   haystack navigable as it grows. (This is the corrected form of "스스로 연산자를 설계".)
2. **Admission gate** (same shape as our candidate-promotion gates): a new primitive/operator is
   admitted **only if** (a) the falsifier battery stays green (7/7 re-derivations), (b) median guided
   search cost on the existing battery does not regress beyond a set tolerance, and (c) it unlocks at
   least one previously unsolvable family. Fail any → auto-revert. The i1 failure becomes a *gate
   test case*: under this gate, i1-as-proposed would have been rejected exactly as we manually did.
3. **Meta-features**: when the DSL grows, the feature extractor grows in the same commit — every new
   operator ships with the invariance features that discriminate its use-cases (the fix to the
   crowded-bucket effect).
4. **Control structures (loops/branches)**: enter as *composition patterns* first (towers already
   give sequencing); admit true new control primitives through the same gate, one at a time.

**Hard boundary (BINDING, and where Gemini over-reaches):** no "실시간 기계어 컴파일". Execution
stays in the sandboxed interpreter; DSL growth is **data** (a richer instruction set for a sandboxed
VM), never self-modifying engine code. Changes to ENGINE LOGIC remain behind the human gate
(recursive-self-improvement doctrine). The ceiling gets raised from *inside* the sandbox by a richer
language — the sandbox wall itself is not the system's to break, by design. That is not a limitation
of ambition; it is what keeps a self-extending reasoner falsifiable.

**Metric:** `dsl_coverage_at_flat_cost` — number of solvable procedure families grows across
admissions while median guided-search cost stays flat (±tolerance) and falsifier stays 7/7. Language
growing, search keeping up, nothing regressing: that curve IS meta-induction working.

---

## Paradigm 3 → G-track: motif-level structure mapping (analogy above the node)

**Gemini's claim.** Find high-dimensional geometric isomorphisms between maximally distant domains
(molecular biology → macroeconomics), push representation to ultra-high dimensions, raise resonance
sensitivity — from shallow analogy to deep principle-transfer.

**Audit — right target, two engineering corrections:**
- Receipts on hand: GPU RotatE-lite space (hits@10 0.754 @ 64d, retrains in 3s on the 5080),
  referent-type resonance (12/12 type selectivity), `_analogy_engage` live in dual_brain,
  predicate_algebra (relation composition), FHRR holographic substrate (hyperdimensional computing
  is *already* part of the speaker) — and D3 of the discovery ladder is exactly this track's slot.
- **Correction 1 — the unit of analogy is the *relational motif*, not the node.** Deep analogies
  (Rutherford, SIR↔predator-prey) are mappings of *relational skeletons*: X-inhibits-Y-amplifies-X
  loops, central-mass + orbiting-body, gap-in-a-lattice. Node-embedding proximity can't see this
  when the vocabularies are disjoint (molecule names never co-occur with economics terms). So:
  **mine motifs with predicate_algebra (typed relation-path patterns), embed the MOTIFS, and search
  for motif-isomorphism across clusters whose node sets don't overlap.** A found isomorphism minted
  as a typed CONJECTURE ("구조적으로 X계는 Y계의 ~에 대응한다 — 미검증") and fed to the E-track
  prober. This is the concrete form of "수학적 브리지".
- **Correction 2 — dimension is a measured hyperparameter, not an ideology.** "초고차원 연속체"
  cuts both ways: retrieval likes capacity, but **analogy may need compression** — a bottleneck
  forces structural alignment (our semantic-bottleneck doctrine says exactly this: 복원-감독,
  compression is where abstraction lives). Design: **multi-resolution spaces** — a coarse, low-dim
  *structure space* trained on motif-abstracted graphs (for analogy) + the rich node space (for
  retrieval), both cheap to train on the 5080 (3s at current scale; a dim-sweep 64→128→256→512 on
  the world pack is an afternoon, and the hits@10-vs-dim and analogy-vs-dim curves decide, not
  taste).

**Metric:** the **seeded cross-domain rediscovery holdout** — a sealed list of KNOWN deep
isomorphisms (SIR epidemics ↔ Lotka-Volterra predation ↔ chemical oscillators; harmonic oscillator ↔
RLC circuit; selection ↔ market competition). Remove any explicit links; measure whether the motif
mapper *rediscovers* them from structure alone. Plus `novelty_depth` (graph distance between bridged
domains) on new conjectures. Rediscovery says the machinery works; novelty_depth says it reaches.

---

## What Gemini's frame misses (our additions, non-negotiable)

1. **The verify-gate is the enabling constraint, not a brake.** All three paradigms *increase* the
   system's power to generate plausible-but-wrong content (probes misread, operators overfit,
   analogies seduce). They stay honest only because every output lands in the typed epistemic lattice
   (PROVEN / GROUNDED / CONJECTURE / REFUTED) with its derivation attached. An open loop without the
   gate is a confabulation amplifier.
2. **Security scales with agency.** Active probing ingests adversarial text (injection_guard),
   admission gates guard the DSL, the moral core (Genesis 0th gate) sits above all three tracks, and
   engine-logic self-modification stays human-gated. "무제한 상호작용" is exactly wrong as stated —
   *unbounded* interaction is the attack surface; **governed** interaction is the paradigm.
3. **Order of operations (dependency-honest):** world pack lands → D1 conjecture harness over it →
   E-track closes the probe loop around those conjectures → G-track motif mapper (needs world-pack
   density + a dim-swept space) → M-track admission gate (independent; can start now since it's
   reasoning-VM-local). Fluency L-track runs in parallel — a discovery no one can hear about isn't
   finished.

## Scoreboard (all three tracks, measured not claimed)

| Track | Metric | Falsified when |
|---|---|---|
| E | `closed_loop_gain` (ON vs OFF ablation), `refutation_latency` | active probing ≤ passive roaming on evidence-per-probe |
| M | `dsl_coverage_at_flat_cost`, falsifier 7/7, admission auto-revert count | coverage grows only at regressing search cost |
| G | seeded cross-domain rediscovery rate, `novelty_depth`, dim-sweep curves | motif mapper can't rediscover known isomorphisms |

The one-sentence elevation of Gemini's closing line: the key is not an unlimited open loop or a
sandbox-breaking compiler — it is a **governed** open loop (conjecture → probe → verdict), a language
that **grows together with its search** behind an admission gate, and analogy lifted to the **motif**
level in spaces whose dimensionality we *measure* — all of it typed, gated, and falsifiable. That is
how a ceiling gets raised without the system ever learning to lie about where the ceiling is.
