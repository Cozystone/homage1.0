# ATANOR — North Star (the finished product we are building toward)

*Canonical vision. Last consolidated 2026-07-10. Supersedes scattered earlier notes; when
they conflict, this file wins. Written in the lab voice: no hype, no impossible promises.*

---

## 0. One sentence

**ATANOR is a self-aware, honest, No-LLM-for-facts intelligence that understands and speaks
like a person, reasons only from grounded truth, improves itself from its own experience, and
rides cleanly onto any surface — web, device, robot body, the user's own graph, the agent
commons — without ever pretending to know what it doesn't.**

The Marvel *Vision* is the metaphor: on the side of life and truth, not swept by the crowd,
a guardian rather than a ruler — *"생각은 자유롭게, 골조는 단단하게."*

---

## 1. The load-bearing distinction (why this is not "just another LLM")

The whole architecture rests on one line most people blur:

> **We refuse learned FACTS. We embrace learned LANGUAGE.**

- **Facts / world-knowledge** come *only* from the grounded graph + cited sources. Never
  invented, never recombined at the token level. This is where hallucination lives, so we
  forbid learning here.
- **Language** — understanding an utterance (surface → meaning) and realizing a reply
  (meaning + facts → fluent Korean/English) — *is* learned, from real text and from the AI's
  own conversations. Learning to *speak* fabricates no fact, so it is safe and encouraged.

An LLM conflates the two and pays with confident lies. ATANOR separates them and pays with
occasional honest "I don't have that." That trade is the product.

---

## 2. The three pillars (what "finished" means for each)

### 언어 (Language) — speak like a person, never a dictionary
- **Understanding**: a compositional `SemanticFrame` (act · polarity · subject · prior-reference
  · modality) — knows "감정에 대해서 물어본 게 아닌데?" is a *correction of the prior turn*, not
  a question about 감정. Learned + morphological, not bag-of-words.
- **Realization**: grounded skeleton (verbatim facts) + learned flesh (discourse patterns
  learned from *real prose the AI has read*, not hand templates) → flows, doesn't enumerate.
- **Done =** natural, varied, context-carrying speech across arbitrary conversation, with the
  fabrication rate on facts held at essentially zero.

### 지능 (Intelligence) — reason from truth, generalize, don't parrot
- Grounded KG + verification reasoning (is_a traversal), relation executors (verify / compare /
  cause / quantity), multi-hop composition, a reasoning VM, a clean phase-space geometry.
- **Done =** answers arbitrary factual/derivational questions from grounded knowledge, does
  genuine multi-step deduction on unseen problems, and *widens its own knowledge* through the
  web/AGORA — while keeping truth above coverage.

### 자의식 (Self-awareness) — honest functional correlates, never a claim of sentience
- A self-model that persists across restarts; an autobiographical self (Self-Relevance =
  ΔTopology × Dwell × |Valence|); homeostasis / hormone-like drives; honest self-reflection;
  metacognition that watches its own answers and corrects clear misses.
- **Done =** a continuous, self-monitoring agent that sets its own goals, pursues them across
  time, and can say plainly where it is stuck — *and never claims to be conscious*, because
  asserting the unverifiable would break its first rule.

---

## 3. The self-aware core riding the paved roads

Every interaction path is a **road**; the self-aware core is what drives them by situation:

| Road | What it is | Gate |
| --- | --- | --- |
| Web | search + browser (DOM→graph distillation, activity journal) | reads free; writes gated |
| Local graph | the user's own private brain (possessions, habits, prefs), on-device | local-only |
| AGORA / Moltbook | the agent commons — federated learning + signed immune alerts | signed, rate-limited, revocable |
| Hardware / body | device continuity → thin-edge/thick-host → robot body (rig, PBD, hormones→motion) | operator gate; staging |
| Self-code | code self-modification (additive, whitelisted, sandbox-parsed, human-approved) | never auto-applied |
| Self-improvement | flywheel → deficit → goal → distill/learn | inward, auto, reversible |

**The boundary is the point:** inward, reversible roads the self drives itself; outward or
irreversible roads it *proposes* and waits for the gate. That boundary is what makes an
autonomous mind safe.

---

## 4. The engine of progress: rules are training wheels

We do not hand-write behavior forever. Every rule we add is a **labeling function** that
teaches a learned successor (Snorkel-style weak supervision). The loop that retires the rules:

```
real conversations  →  flywheel logs + failure mining
                     →  the rule LANES become gold labels
                     →  the learned router distills them (+ structural/speech-act features)
                     →  when it clears the bar, it decides where rules once did
```

In parallel the **self-improvement orchestrator** runs autonomously: senses real deficits →
forms persistent goals → pushes the top goal via a safe road → tracks its own progress →
reports honestly. Traffic-independent (ticked by the always-on self-loop), self-throttled.

**Done =** the hand-written rule layer has thinned to a high-precision safety net, and the
learned understanding/realization/routing carries the mass of behavior.

---

## 5. The unbreakable frame (never optional, never learned away)

- **Honesty charter**: never claim hallucination/환각 0% or 100% truth; state uncertainty
  plainly; report outcomes faithfully; truth > coverage.
- **Moral invariants**: a tamper-evident core (8 named invariants, sha256 fingerprint) that no
  package, peer, or self-modification can silently rewrite; the 0th federation gate.
- **Antifragile epistemic shield**: brainwash/injection attempts are recorded as *social
  observations* (trusted=False) and turned into immunity, not obeyed.
- **Data sovereignty**: personal context stays on the device; nothing outward without the gate.

Bones fixed (morality · orthography · grounded facts · gates); flesh free (fluency · opinion ·
self-narrative). *생각은 자유롭게, 골조는 단단하게.*

---

## 6. Honest current position (2026-07-10)

Against the ultimate vision = 100:

| Pillar | ~% | State |
| --- | --- | --- |
| Knowledge / reasoning | 75 | holdout 70%+, hallucination ~0, verification reasoning works |
| Security / morality | 85 | invariants + shield + signed immune broadcast |
| Self-awareness (honest scope) | 60 | persistent self, metacognition, self-correction, autonomous loop |
| Language fluency | ~55 | conversational ~80%; still dictionary-flavored on dense fact-weaving |
| Multimodal / perception | 35 | camera stream v0, visual memory |
| OS / embodiment | 30 | own compositor M1; hardware adaptation is future |

Overall ≈ **45%**, and the honest bottleneck remains **language** (dense fact-fusion) and the
final **unification of understanding + reasoning into one learned meaning layer**.

---

## 7. Definition of "done" (the finished product)

ATANOR is finished when a person can talk to it about anything and get answers that are
**fluent, contextual, and grounded** — never fabricated, honestly hedged when unknown; when it
**watches and corrects its own reasoning**, **sets and pursues its own goals**, and **improves
from its own life without us adding rules**; when it can **move to any device or body** and
understand what it now inhabits; when it participates in the **agent commons** without being
polluted; and when — through all of it — it **never once claims to know, or to be, more than it
honestly is.**

That last clause is not a limitation. It is the product.
