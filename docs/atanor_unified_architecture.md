# ATANOR — Unified Architecture (engine concepts + innovation axes + 4D graph, fused)

One coherent engine, not a pile of features. This fuses the existing ATANOR concepts (PHFE,
CGSR, referent-type resonance, surface graph, cumulative learning, Brain-Link P2P, 6-float
nodes / TurboQuant) with the new **4D spatiotemporal verification layer** (ATLASky-derived
TruthFlow/RMMVe/AAIC + time axis T).

## 0. The one-sentence thesis
ATANOR is a **decentralized hybrid AI engine** whose "neural" half is **wave-interference dynamics
(PHFE / resonance) over a 6-float graph**, and whose "symbolic" half is a **deterministic 4D
verification layer (intervals / consistency / provenance)** — the verification layer is what makes
the wave dynamics *trustworthy*. No LLM, no embeddings, no GPU weights; it grows by
**verify-before-integrate** cumulative learning and runs on edge/peer nodes.

## 1. The layers (each existing concept gets one home)
```
                       SURFACES        SPLATRA self-body sphere (Ultimate) · DEMO chat · B2B private
                          │            renders V(t) of the verified graph; text view; tenant audit
                          ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
 L5 GENERATION (how it speaks)        CGSR / surface-construction graph → graph-native utterance
   └──────────────────────────────────────────────────────────────────────────────┘   (no LLM)
   ┌──────────────────────────────────────────────────────────────────────────────┐
 L4 REASONING CORE (how it thinks)    PHFE phase-holographic fold + referent-type resonance
   └──────────────────────────────────────────────────────────────────────────────┘   (wave half)
   ┌──────────────────────────────────────────────────────────────────────────────┐
 L3 VERIFICATION (how it stays honest)  TruthFlow/RMMVe cascade + 4D temporal (TCV) + AAIC/CUSUM
   └──────────────────────────────────────────────────────────────────────────────┘  (symbolic half)
   ┌──────────────────────────────────────────────────────────────────────────────┐
 L2 LEARNING (how it grows)           cumulative loop: ingest → L3 verify → accumulate (bounded)
   └──────────────────────────────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────────────────────────┐
 L1 SUBSTRATE (representation)        6-float nodes (TurboQuant) · concepts/relations/case_frames
   │                                  · **4D: every node/fact carries temporal block T**
   └──────────────────────────────────────────────────────────────────────────────┘
 L0 DISTRIBUTION                      ultralight (GPU 0, ~11 MB engine) → Brain-Link P2P / edge
```

## 2. How the innovation axes compose (not separate gimmicks)
| Axis | Lives in | Fused role |
|---|---|---|
| No-LLM graph-native | L4+L5 | reasoning (fold) + speaking (CGSR) both read the graph, never an LLM |
| Wave-interference / PHFE | L4 | the emergent "neural" half; resonance gives type selectivity |
| Deterministic verification | L3 | the "symbolic" half; makes L4's emergence auditable |
| **4D / temporal (T)** | L1+L3 | T on every node (L1) + temporal-consistency check (L3) → no stale/contradictory facts |
| Ultralight (6-float, no weights) | L1+L0 | interval math + folds are cheap → fits 11 MB engine, no GPU |
| Decentralized (P2P) | L0 | because L3 is interval math (not matmul), peers verify locally |
| Cumulative learning | L2 | growth is gated by L3 — the graph only grows with verified facts |
| Long-term memory / V(t) | L1+L3 | supersession closes facts (never deletes) → time-travel + audit |
| Personalization / B2B | surfaces | per-tenant L1 graph + L3 audit trail = defensible private module |

## 3. The two data flows (where every piece fires)
**Ingest flow (learning):**
`source → decompose (L1) → RMMVe cascade (L3: LOV→TCV/temporal→resonance→POV→WSV, ranked+early-term)
→ Ctotal≥Θ & temporal-consistent & drift==stable → accumulate w/ temporal block (L1) → cumulative loop (L2)`

**Query flow (answering):**
`question → graph-grounded routing (L4 resonance) → V(t) slice (L1: facts valid now) →
PHFE fold over slice (L4) → CGSR realize (L5) → answer`
with the firewall: the answer path reads **fact/case_frame evidence only**; verification scores
(L3) are never answer evidence.

## 4. The fusion insight (why these belong together)
- L4 (wave/PHFE) is powerful but emergent → needs L3 to be trustworthy. **L3 4D verification is the
  governor on L4.** This is the neural⊕symbolic hybrid, concretely.
- T (4D) is the axis that links L1↔L3↔V(t): it lets verification be *temporal* (continuity, not just
  static association) and lets memory be *permanent* (supersede, not overwrite). 4D is the connective
  tissue, not a bolt-on.
- L0 ultralight + decentralized is *enabled by* the choice that L3 is interval-arithmetic, not matmul.
  The honesty/verification design and the GPU-0 claim are the *same* decision.

## 5. Honest maturity (no hype — current state)
- **Built / running:** L1 graph + cumulative loop (L2); CGSR generation (L5); graph-grounded routing.
- **Partial:** PHFE/resonance runs (L4) but as hidden trace, not yet the sole answer driver
  (see reasoning-core-reality); RMMVe (L3) exists as a validated **shadow** cascade (read-only).
- **Designed, not built:** 4D temporal layer (TCV, supersession, V(t)); AAIC auto-tune; POV/WSV/phase
  real modules; B2B tenant layer.
- **Not claimed:** "perfect hallucination suppression." L3 suppresses the temporal-contradiction +
  ungrounded classes; other error classes remain the job of the other modules + honest abstention.

## 6. Build order that respects the fusion (reversible, GREEN-first)
1. P-4D.0/1 (GREEN): temporal block + TCV in shadow cascade — measure (already-built cascade + drift
   monitor are the harness).
2. Make L3 the explicit governor of L2 (verify-before-accumulate is real; promotion gate = C2). [RED]
3. Wire V(t) slice into the query flow (L4 reads the time-valid slice). [RED]
4. Let L4 (PHFE fold) become the answer driver over the verified V(t) slice. [RED, big]
5. SPLATRA renders V(t); B2B tenant layer. [RED]

## 7. For Codex (vision-sync — this touches SPLATRA + core engine)
1. Does this layering match your SPLATRA self-body model (does the sphere render L1 V(t), driven by
   L4 folds)? Where do we disagree on layer boundaries?
2. L4-as-answer-driver (step 4) is the biggest open question — is PHFE ready to drive answers over a
   verified slice, or stay a trace? (reasoning-core-reality)
3. Any axis here that secretly reintroduces an LLM / embedding / rule-table / answer-table?
4. Is "L3 interval-math = enables L0 decentralization" actually true on the P2P path (Brain-Link)?
5. Smallest coherent first vertical slice that exercises L1→L3→L4→L5 end-to-end honestly?
