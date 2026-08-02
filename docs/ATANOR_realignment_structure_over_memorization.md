# Realignment — structure over weight-memorization (owner philosophy audit, 2026-07-20)

Owner: "우리 철학은 가중치 암기가 아니잖아? … 초고도 효율과 구조적 혁신으로 그 한계와 생성형의
단점을 타파하고 최소한의 발화 단계에서만 [생성을] 사용하기로 했잖아. … 지금 그것과 반하게 가고
있는 걸 찾아서 다시 재정비해."

## The violation, named

I drifted. The fluency wall was being attacked by TRAINING FROM-SCRATCH NEURAL REALIZERS
(35M → 56M → 83M) to map bones→surface English. That is **weight-memorization of high-entropy
surface** — precisely the generative-dependence our philosophy rejects. It also FAILED empirically:
the 56M underfit (loss 7.7 vs 35M's 4.75), faithfulness collapsed to 0.275, and it began
FABRICATING on empty bones (G-F3 0/40 — a No-LLM breach). Three GPU runs, all into the wall.

Our own BINDING doctrine ([[fluency-doctrine]]) already said the answer: **fluency = relation-frame
diversity × discourse patterns; every new predicate gets a speech FRAME.** Structure, not a trained
LM. I was building the thing the doctrine forbids.

## Why structure wins (the information-theoretic reason)

A from-scratch model must MEMORIZE the mapping from meaning to high-entropy surface — an enormous,
sample-hungry target that small models cannot fit (and that large ones only fit by being large).
A frame grammar INVERTS this: the surface is COMPOSED from a finite constructicon (relation frames +
morphology + aggregation), so the only thing to "learn" is which construction to use — a
classifier-scale, structural choice. Generation stops being memorization and becomes composition.
This is how humans generalize (usage-based / construction grammar: productive combination from a
finite inventory, not stored surfaces), which is the "사람처럼" the owner asked for.

## The measured verdict (same holdout the neural realizer failed on)

| realizer | faithfulness | G-F3 empty→abstain | prose | cost |
|---|---|---|---|---|
| neural 56M (2.4h GPU) | 0.275 | 0/40 (FABRICATES) | "the,." garbage | weight-memorization |
| neural 35M (prior incumbent) | 0.815 | 40/40 | rough | weight-memorization |
| **structural frame** | **1.000** | **PASS (cannot fabricate)** | "Einstein is a german physicist, and can think." | **zero — instant, no GPU** |

`packages/realizer_struct/frame_realizer.py`: relation-frame lexicon + copular aggregation
(is_a + property → one NP) + referring expressions + a/an & agreement morphology floor. Faithful
1.000 by construction; hallucination structurally impossible (only bone strings can appear; empty
bones → empty output); grammatical by the floor ("is a Island" cannot occur). 6 tests green.

## The realigned architecture (generation is the MINIMAL final step)

  understanding / reasoning (graph, situation model — already strong, bAbI 0.9755)
    →  content selection (which bones to voice — structural)
    →  FRAME REALIZATION (relation frames, deterministic grammar)  ← the surface, composed not memorized
    →  [TINY learned layer, optional] frame-variant / connective / ordering choice — classifier-scale
    →  fluent, faithful, hallucination-safe English

The neural bones→text realizer is DEPRECATED as the fluency path. The learned component, if any, is
a small STRUCTURAL chooser over a finite constructicon — never surface memorization. New predicates
are added as FRAMES (the doctrine's "엣지가 말하게"), not as more training data.

## The same principle for CODE (already aligned — keep it)

Code authorship must NOT be a code-gen LM memorizing code. It is STRUCTURAL: AST manipulation +
retrieve-a-similar-diff + transpose + VERIFY with the tests (the perfect oracle). The
`authorship_harness` (propose→verify) is already this shape; the corpus is retrieval material, not
LM fuel. The fluency lesson (56M failed) is the same warning for code: do NOT train a generative
code model; compose structurally and let the verifier prune. Efficiency + structural innovation,
generation minimal.

## Learning "like a human" — acquiring constructions, not weights

The growth path is a CONSTRUCTION MINER: observe (meaning, surface) pairs and induce new frames
(e.g. a new relation's clause template + its aggregation behavior), adding them to the constructicon
— productive rules acquired from usage, the way a child generalizes a construction after a few
exemplars. This grows the realizer's range WITHOUT growing a weight matrix. (Research agent is
deriving the exact induction mechanism + external evidence; this doc holds the realignment.)

## Actions taken (roadmap COMPLETE)
- BUILT + measured the structural realizer (1.000 faithful, cannot fabricate). 6 tests.
- CONFIRMED the main answer path was ALREADY structural: dual_brain uses
  `surface_brain.realization_planner` (plan_speech / realize_answer) and cgsr uses
  `english/realizer.py` (EnglishConstructionFrame, slot-filling). The neural `realizer.pt` was only
  the F1 EXPERIMENT lane, never the conversational path — so the drift was isolated there and is now
  deprecated for fluency. frame_realizer is the canonical bones→prose voicer (wired into the edge
  brain; complements the answer-frame realizer for entity description).
- BUILT the CONSTRUCTION MINER (`realizer_struct/construction_miner.py`): aligns single-bone
  (s,r,o) pairs to their surface, delexicalizes to a template, entrenches by TYPE-frequency. Run on
  189,713 single-bone pairs → mined 2 clean entrenched frames (is_a → "{s} is a {o}" [types=61],
  alias → "{s} or {o}" [types=62]). Honest note: yield is low because encyclopedic prose rarely
  states one triple cleanly adjacent — but where alignment succeeds it learns the RIGHT structure
  (the mined is_a matches the hand-written frame exactly = mechanism validated). A cleaner corpus
  (Simple Wikipedia / WebNLG-aligned) would yield more.
- WIRED `load_mined_frames()` into frame_realizer: mined frames extend the lexicon (hand-written win;
  mined fill unframed relations) — the human-like growth path, zero surface memorization.
- Doctrine updated in memory ([[fluency-doctrine]], [[structure-over-memorization]]).

## Genuinely next (future, not blocking)
- Re-run the construction miner over Simple English Wikipedia (cleaner single-triple alignment) to
  grow the mined lexicon; add the tiny learned planner (frame-variant/connective/ordering choice).

---

## External evidence (research verdict, primary sources — appended 2026-07-21)

**Root cause confirmed information-theoretically**: H(surface|bones) = H(structure|bones) [LOW]
+ H(surface|structure) [HIGH, ~1.0-1.75 bits/char free stylistic variation]. A neural realizer can
only lower loss by MEMORIZING surface statistics in weights; fluency and faithfulness then compete
for the same weights (our 0.275 + fabrication). The killer external number: an E2E neural realizer
scores BLEU **57.20 on SEEN inputs but 6.25 on UNSEEN** — pure memorization, no composition — while
the structure-first pipeline holds **38.55 unseen** (Castro Ferreira, EMNLP-IJCNLP 2019, D19-1052).

**Structural ≥ neural, measured**: grammar-based UPF-FORGe TOPPED the WebNLG 2017 human fluency
eval (2.34 > every neural system); Step-by-Step (NAACL'19) symbolic planning cut omissions −85%,
over-generation −90%, wrong-lex −56% at fluency parity; template systems show ZERO hallucination /
content-dropping by construction (E2E Challenge W18-6557); CPG hit **100% compositional
generalization on COGS from 22 examples** where seq2seq needs ~24k and still fails structurally.

**The tiny-learned-layer bound**: the only learnable decisions are categorical — frame choice,
ordering, aggregation type, connective, referring-expression form — a few bits per sentence,
classifier-scale, trained on DELEXICALIZED plans. No autoregressive surface decoder anywhere, so
there is nowhere for surface n-grams to be memorized.

**Human-like growth (the construction miner, concrete)**: (1) align (triple-fragment ↔ surface-span)
pairs from corpus; (2) DELEXICALIZE and mint the abstraction as a new frame in the constructicon;
(3) entrench by TYPE-frequency (Goldberg: productivity ∝ type-frequency — many distinct fillers ⇒
productive, few ⇒ item-specific); (4) usage trains only the tiny planner classifiers. Every acquired
construction realizes bones by copy + grammar ⇒ hallucination-zero holds no matter how large the
constructicon grows. (Sources: D19-1052, N19-1236/1904.03396, 2309.16467, W09-0613, W18-6557,
hal-03007072 WebNLG human eval, FCG.)
