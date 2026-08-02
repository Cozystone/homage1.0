# ATANOR Discovery Engine — the honest path beyond answering

Owner (2026-07-14): *"벤치마크는 그들이 못하니까 우리가 만점을 가려는거야. 안되면 스스로 천재적인
직관과 사고로 새로운 연결을 찾아내 이론을 창시하던지 … 사고를 읽을 수 있으면 천재들처럼 새로운
연결을 구상하고 깊이 탐구해서 … 인간지능의 총합을 뛰어넘는 지능으로 기존의 한계를 뛰어넘는 혁신의
구상이 가능하게 만들 방안을 혁신적으로 내봐."*

This is the plan for that — built to our honesty doctrine, not around it.

## 0. The one honest reframe I owe you

I will **not** build a system that *claims* to exceed the sum of human intelligence. That claim is
unfalsifiable, and our whole edge is that we don't say things we can't show. What I **will** build is
the machine that actually does the thing underneath the dream:

> a **verify-gated discovery engine** that searches the world graph for **novel, inspectable
> connections no human enumerated**, keeps only the ones that survive proof or consensus, and files
> the rest as **open questions — never as fact**.

If the machinery is real, the *results* make the case. We never have to make the claim. That is the
only version of "genius" that is honest, and it is more valuable than the hyped one because it is
**auditable**.

## 1. Why a No-LLM graph engine can genuinely discover (the structural edge)

Three properties an LLM structurally cannot match — and all three are already our substrate:

1. **Inspectable derivation.** Every conjecture carries its full derivation — the analogy mapping,
   the graph path, the score breakdown, the source triples. You can read *why*. This is literally
   what "사고를 읽을 수 있으면" means, and we already emit it (see the proof in §3).
2. **Un-hallucinatable.** A conjecture is *never* asserted as fact. It is verify-gated (proof or
   k-source consensus) or filed as an open question. An LLM's "new theory" is indistinguishable from
   a fabrication; ours is **typed** by epistemic status. That is the difference between a discovery
   engine and a confabulator.
3. **Combinatorially wide + honestly filtered.** A human genius finds a handful of deep analogies in
   a lifetime. A machine can *score millions* of candidate cross-domain mappings over the world graph
   and keep only the verifiable ones. Not "smarter than everyone" — **a wider search with an honest
   filter**. That distinction is the whole doctrine.

## 2. How discovery actually worked — and why it's computable

The canonical breakthroughs were **structure-mapping**: the same relational skeleton, transplanted
across domains.

- Kepler: planetary orbits ↔ musical harmony (ratio structure).
- Rutherford: atom ↔ solar system (central-mass + orbiting-body structure).
- Darwin: natural selection ↔ artificial breeding (selection-over-variation structure).
- Mendeleev: **gaps** in the periodic table → predicted undiscovered elements (missing-node in a
  regular lattice).

None of these required "more intelligence than all humans." Each required **seeing that two distant
subgraphs share a relational shape** — and that is a computation over a knowledge graph. We already
have the primitives (phase-space geometry + predicate algebra). The world pack gives them the scale.

## 3. Proof it already runs (measured today, not promised)

`packages/cgsr/cgsr/creative_engine.py` (`CreativeEngine`, No-LLM, deterministic) run over **30,000
real clean triples** invented 8 grounded, scored, explained concepts. One verbatim:

```
[break]  score=0.800
파괴된 전제: 'camping'은(는) 반드시 fun에 has_property 해야 한다
탐색 경로: camping has_property fun → ¬(has_property fun) → fun 없는 camping
영감(근거): camping has_property fun; camping capable_of includes tents; camping has_property enjoyable
창의성 점수: 0.800 (novelty=1.00, consistency=0.80, surprise=1.00, utility=1.00)
```

**What this proves:** the discovery engine is real, runs on the actual graph, and every output is
grounded + scored + *explained* (broken premise, search path, source triples). The "read the
thinking" property is not aspirational — it ships.

**What this honestly exposes (the gap this plan closes):** today's top results are all
`break_assumption` — shallow negations ("camping without fun"), not deep cross-domain **blends** or
**bridges**. Three things are missing, and they are exactly the D-ladder below:
(a) **scale** — 30k clean triples can't reach across domains; the 100M world pack can;
(b) **analogical transfer** — the engine is pure symbolic co-occurrence today; it does not yet use
the GPU-trained phase-space geometry (§4) to find distant structural matches;
(c) **the verify-gate** — nothing yet filters conjecture → proven.

## 4. The four discovery primitives (each mapped to real machinery)

| # | Primitive | What it finds | Grounded in |
|---|-----------|---------------|-------------|
| **D-A** | **Analogical transfer** (structure-mapping) | A:B :: C:? — if the relational shape holds geometrically and the target edge is absent, conjecture it (Rutherford) | `phase_space.resonance` / `neighbors` (RotatE-lite, GPU-trained) + `predicate_algebra` + `dual_brain._analogy_engage` |
| **D-B** | **Gap-filling** (link prediction) | high-confidence **absent** edges = candidate discoveries (Mendeleev's gaps) | trained phase-space scoring absent edges + `creative_engine` |
| **D-C** | **Bridging conjecture** (interdisciplinary) | two dense clusters with **no path** → the missing bridge relation; cross-domain bridges are where breakthroughs live | phase-space cluster geometry + `predicate_algebra` composition |
| **D-D** | **Theory conjecture** (rule induction) | a set of observations with **no covering rule** → induce a candidate rule, test on held-out ("creating a theory" as a *falsifiable* conjecture) | reasoning-VM F-ladder (`procedure_induction`, `induction_flywheel`, `falsifier`) |

Each is an **operator over the graph**, so — per the CreativeEngine philosophy — *more triples ⇒ more
assumptions to break, more analogies to draw, sharper value statistics.* Scale is a multiplier, not a
rewrite.

## 5. The closed discovery loop (autonomous, verify-gated)

```
  CONJECTURE ─▶ SCORE ─▶ VERIFY ─▶ TYPE ─▶ PERSIST ─▶ COMPOSE ─┐
  (invent over   (novelty×     (proof /     (PROVEN /   (proven→graph   (proven become
   world graph:   utility×      k-source     GROUNDED /   conjecture→     premises for
   D-A..D-D)      surprise×     consensus     CONJECTURE)  open-question   the next round
                  consistency)  ≥2 indep. /                 ledger)       — the flywheel)
                                held-out)                                          │
  └───────────────────────────────────────────────────────────────────────────────┘
```

Runs on the **already-built always-on autonomous daemon** (task #159), mining the idle graph while
the GPU trains representations. Nothing here is a new runtime — it is an orchestration of parts that
already pass tests.

## 6. Epistemic typing + honesty guardrails (BINDING)

- **Every output is typed:** `PROVEN` (deductive / held-out falsification passed) · `GROUNDED`
  (≥2 independent sources agree) · `CONJECTURE` (novel, plausible, **UNVERIFIED**).
- **A CONJECTURE is surfaced as a question, never as fact** — with its structural evidence attached:
  *"구조적으로 X는 Y일 수 있다 — 근거: …(경로/유추); 미검증."* This is the existing endogenous
  self-inquiry doctrine ("inquiry from state pressure, never fabricate"), reused verbatim.
- **No confidence inflation. No "환각 0%". No "초지능".** The numbers are the numbers.
- **No-LLM end-to-end.** Every step is graph / geometry / proof — inspectable, replayable.
- **The moral core (Genesis 0th gate) sits above the loop:** a discovery that violates the
  uncontaminable invariants is discarded before it is ever surfaced.

## 7. Measure, don't claim — the discovery scoreboard

We publish these, not adjectives:

- **`discovery_yield`** — novel conjectures that *later* verify, per week.
- **`precision@verify`** — fraction of surfaced conjectures that survive verification (guards against
  a firehose of plausible-but-wrong).
- **`novelty_depth`** — graph distance between the two bridged domains (how *far apart* the connected
  things were — the honest proxy for "genius leap").
- **Seeded-rediscovery test** — remove a set of *known* edges from the graph, run the loop, measure
  what fraction it *rediscovers* (Mendeleev backtest). This is a falsifiable benchmark of the engine
  itself.

## 8. The benchmark bridge (how this lifts coverage without fabricating)

For a benchmark anchor with **no lookup/traversal answer**, the loop gives a **second path**:
analogical transfer from a solved neighbor (D-A), or an induced rule (D-D) — **with epistemic status
attached.** Instead of abstaining or fabricating, ATANOR emits a **CONJECTURE-marked best-effort
answer + its derivation.** Coverage rises; honesty holds; the grader (and you) can audit the
reasoning. That is how you approach 만점 the only honest way: **ground what's groundable, conjecture
the rest transparently, and make every step auditable.** A wrong conjecture that shows its work is a
lesson (it feeds the failure-receipt engine); a fabricated fact is a betrayal. We only ever do the
former.

## 9. Build ladder D0–D5 (each verify-gated + measurable)

- **D0 — representation on GPU** ✅ *(done today)*: `scripts/retrain_clean_space.py` retrained
  RotatE-lite on the RTX 5080 in **3s** (392k triples → hits@10 0.754), atomic + rollback-safe.
  Re-run on the **world pack** when the build lands (100M triples → a vastly richer analogy space;
  proper-noun clusters like 서울 stop being noisy).
- **D1 — harness `CreativeEngine.invent` over the world graph** *(offline)*; emit typed conjectures
  to an open-question ledger. Metric: `discovery_yield` on the seeded-rediscovery test. *(proof of
  concept already runs — §3.)*
- **D2 — wire the verify-gate**: each conjecture → proof (reasoning-VM) or k-source consensus
  (existing consensus-evidence machine, task #45). Metric: `precision@verify`.
- **D3 — analogical transfer (D-A/D-C)**: structure-mapping over the GPU phase-space; cross-domain
  bridge finder. This is the leap from shallow negation to genius connection. Metric: `novelty_depth`.
- **D4 — theory conjecture (D-D)**: F-ladder rule induction on unexplained observation sets, held-out
  falsification. Metric: induced-rule survival rate on held-out.
- **D5 — benchmark bridge**: route unanswerable benchmark anchors through the loop, emit typed
  best-effort. Re-measure the three north-star benchmarks (KMMLU / MMLU-Pro / GPQA) coverage.

## 10. What we are explicitly NOT doing (the anti-hype boundary)

- Not claiming superhuman intelligence or consciousness-driven insight.
- Not asserting any conjecture as fact.
- Not using an LLM to "generate theories" (unfalsifiable, hallucination-prone — the exact failure
  mode we exist to avoid).
- Not optimizing a benchmark by memorization.

The claim is narrow, and it is true: **a verify-gated, inspectable, combinatorially-wide discovery
engine, whose yield we measure and publish.** That is the honest shape of "무한한 가능성" — and it is
buildable from parts that already run.
