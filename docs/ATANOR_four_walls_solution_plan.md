# The Four Walls to AGI — research findings, application plans, first measured results

Owner directive (2026-07-20): the four remaining walls (fluency, messy real-world text, embodiment,
open-world transfer) are unknowns to SOLVE, not fates to accept. Four parallel research lanes swept
papers/repos with primary-source numbers; this document is the synthesis, the ranked plan per wall,
and — because plans are cheap — the first experiments ALREADY RUN with their measured results.

Doctrine constants: No-LLM (from-scratch learned components fine), English-only, hallucination-zero,
everything measured, local Windows + RTX 5080 (Blackwell sm_120).

---

## Wall 1 — Fluency (from-scratch realizer produces rough prose)

**Research verdict: capacity was the WRONG suspect.** TinyStories (Eldan & Li 2023): 1–33M models
produce fluent English when the training distribution is simple — a 21M single-layer model already
writes fluent stories; grammar is "mastered by relatively small models." Our 35M is ABOVE the
fluency threshold; the binding constraints are (a) the complex encyclopedic register of our 200k
enwiki pairs and (b) capacity wasted memorizing entity strings. BabyLM (2023/24): near-human
grammar (BLiMP 86) is reachable from scratch on 100M human words — with 450–2000 epochs, i.e. our
"underfit in 40min" was off by orders of magnitude on epochs, not parameters. Data-to-text (WebNLG/
E2E, pre-LLM era): small seq2seq models were ALREADY fluent+faithful over ~10-relation vocabularies
using **delexicalization + copy** — entities become slot tokens, the model learns only connective
tissue, and entity hallucination becomes structurally impossible. Three independent negative
results on curricula (BabyLM 1+2, CDS study): do NOT build one.

**Ranked plan**
1. **Delex+copy retrofit** of the 35M on the existing 200k pairs (highest information per GPU-hour;
   strengthens G-F3 by construction). Gates: LanguageTool grammar-error rate −30%, faithfulness
   ≥0.815 held, G-F3 40/40 held, entity-hallucination 0 by bookkeeping.
2. **Register swap**: re-mine bones→text from Simple English Wikipedia (human, CC BY-SA, ~250k
   articles) — the same pipeline, simple-register targets.
3. **LM-pretrain on a license-clean 10–100M-word simple-register mix** (simplewiki + Gutenberg
   children's [public domain] + Tatoeba [CC-BY]), long-epoch, short-context samples; then fine-tune
   on delexed pairs. TinyStories corpus itself is GPT-generated → diagnostic use only, never diet.
4. **Grammar floor**: port SimpleNLG's ~6 morphology rules (a/an, agreement, number, tense) as a
   deterministic repair/reject pass — LAD-floor doctrine, Korean precedent; fixes "is a Island."
5. Faithfulness+grammar reranking over k samples (E2E challenge's quality winner pattern).

**Status**: 56M long-run training in flight (capacity control arm; waiter reports on convergence).
Delex retrofit queued for the GPU the moment it frees.

---

## Wall 2 — Messy real-world text

**Research verdict: measured recipes exist; none require a pretrained LM.** MoNoise (2017) holds
lexical-normalization SOTA-era results (LexNorm F1 86.39) from Aspell + from-scratch skip-gram +
random forest. A Most-Frequent-Replacement dictionary ALONE captures most normalization mass
(61.88 ERR on English MultiLexNorm). Belinkov & Bisk: noise-mix training recovers most degradation
(~4 BLEU clean cost) but synthetic-only noise does NOT transfer — natural error corpora (GitHub
Typo Corpus) must be in the mix. CharacterBERT-style char-CNN word lanes buy ~+5 F1 at heavy noise.
NSU/fragment classification is tractable non-LLM (~87% F, Fernández 2007). External wild-prose
exams: **NarrativeQA (Apache-2.0, generative, string-metric graded)** primary; MultiWOZ 2.1 (MIT,
real typos) secondary; implicature stays an abstain-friendly flagged lane (even pre-LLM SOTA ~47%).

**FIRST EXPERIMENT RUN (measured today)** — degradation curves on 400 external bAbI-valid items,
4 families x 3 rates, deterministic seed (data/comprehension/noise_degradation.json):
- clean 0.9925 → keyboard @2.5% (natural rate) **0.750 (−24.2 pts)** — literature's strong trained
  systems lose ~2.8 at this rate: our frame parsing is ~10x more noise-brittle. @25%: 0.072.
- natural misspellings @25%: acc 0.190 with **flip rate 0.598** — the DANGEROUS failure (confident
  wrong answers, not honest abstention) dominates under natural spelling noise.
- case_punct: lowercasing alone is FREE (0.993) but **removing periods collapses everything to one
  unparsed sentence (0.037)** — sentence segmentation is single-point-of-failure on '.'.
- fragmentization @10%: 0.485 — function-word loss halves comprehension.

**Ranked plan (now evidence-ranked by the curves)**
1. Punctuation-independent sentence segmentation (capitalization/discourse-cue + learned segmenter).
2. MFR dictionary + edit-distance-over-own-vocab normalizer with confidence τ (leave-as-is = never
   worse than nothing; abstention-safe by construction), supervised by MultiLexNorm-EN + GitHub
   Typo pairs + self-supervised denoising pairs (inject the same families into clean wiki).
3. Char-CNN word lane beside the BPE in our encoder (graceful degradation under residual noise).
4. Flip-rate gate: under noise, a flipped confident answer is a defect class of its own — track it
   in every battery run (hallucination-zero's noise-time extension).
5. Adopt NarrativeQA sealed subset as the standing wild-prose exam (Radxa examiner pattern).

---

## Wall 3 — Embodiment (Isaac blocked on Blackwell)

**Research verdict: the blocker is DEAD — two healthy native-Windows GPU paths exist today.**
(1) **MuJoCo 3.10.0** ships win_amd64 wheels (pip install, CPU-native engine, AVX only) — Reacher-
class proprioceptive tasks train with SAC on CPU in ~1–3h (SB3-verified practice). (2) **MJWarp /
Newton** (Disney+DeepMind+NVIDIA): Newton v1.4.0 README explicitly supports Windows x86-64, GPU
"Maxwell or newer," **no CUDA toolkit required** — Warp 1.15 ships win_amd64 wheels and JIT-compiles
for sm_120 (verified working on RTX 50-series in NVIDIA/warp#1405; keep kernel-cache path short,
MAX_PATH). This is Isaac-class massively-parallel RL on our 5080 with zero Isaac dependency, same
MJCF models — the CPU curriculum ports up unchanged. Genesis: runs on Blackwell but support is
being patched live and its own tracker admits an 18x contact-fidelity gap vs MuJoCo — reference,
not substrate. JAX/MJX: Linux/WSL2 only — skip.

**SPLATRA-native loop (differentiated path)**: M0 body schema (FK rig reach, obs≈8–12d, act 2–3d,
reward −dist−0.1||a||², Jacobian-probe correlate) → M1 affordances (PBD blob displacement + forward
-model error correlate; deformables are native PBD — where we BEAT rigid-body sims) → M2 object
permanence (occlusion/burial + violation-of-expectation surprise → curiosity hormone; PLATO
methodology adapted to acting). Honesty gates: penetration depth, energy drift, momentum meters
logged every run (Genesis's 18x gap is the cautionary tale). MuJoCo M0 runs as the calibrated
measurement control twin of SPLATRA M0 — paired curves, everything-measured.

**Status**: MuJoCo 3.10 + Gymnasium + SB3 installed natively today; **SAC Reacher-v5 M0 (200k
steps, CPU-only, gate: eval mean ≥ −10 over 100 eps) is TRAINING in the background now.** Next:
mujoco-warp smoke test on the 5080; then the SPLATRA twin.

---

## Wall 4 — Open-world transfer (external exams we did not write)

**Research verdict + adopted battery**: bAbI (CC BY 3.0, generative single-word, symbolic ceiling
~100% published — both excuses pre-refuted), CLUTRR (CC BY-NC, report the full k-curve), COGS
(MIT, report lexical vs structural separately), TextWorldExpress (Apache-2.0, interactive, Windows
via JVM). ARC-AGI stays a stretch lane with honest expectation 0–5% (icecuber's 20% took a massive
hand-built DSL; best-ever non-LLM single submission 40%). Sealed protocol: pinned SHA256, test
splits untouched until one-shot runs, all numbers reported, abstention=wrong in the headline.

**FIRST EXPERIMENT RUN (measured today)** — bAbI en-valid-10k, 200 q/task:
- Shipped situation model, zero changes: **strict mean 0.127** (where-questions abstained by
  design — the location organ simply did not exist). Honest and humiliating; per-task deltas
  became the work queue.
- Built the missing WORLD-STATE ORGANS (domain-blind verb-frame trackers: location/possession/
  spatial/path/kind-inheritance/motive — the organs any situation model needs; reasoner abstains
  when state cannot ground rather than falling through to noun-overlap yes/no):
  **train 0.9758, VALID 0.9755** (no overfit gap), coverage 0.981, answered-acc 0.994 —
  vs anchors n-gram 0.34 / LSTM 0.49 / **MemNN 0.79** / ASP symbolic ~0.996. 17/20 tasks at 1.000.
- Honest residuals: qa20 "where will X go" abstains (cross-story regularity requires train-split
  learning — deliberately not built yet), qa16 0.95, qa5 0.89. Test split still sealed.
- Caveat kept in every report: bAbI language is synthetic/templated — this certifies the reasoning
  machinery, not open-world English breadth (that is what NarrativeQA/TextWorldExpress add).

**Next**: CLUTRR harness (k-curve), then TextWorldExpress, then the noise families applied to the
external exams (walls 2x4 compose).

---

## The honest arithmetic after day one

- Wall 4: first external exam went 0.127 → 0.9755 (valid) in one day BECAUSE the research located
  the exact missing organs. The wall was thinner than it looked once measured from outside.
- Wall 2: now has a measured brittleness profile (−24 pts at natural typo rates; flip 0.60 worst
  case) and an evidence-ranked repair list. This wall is real and now quantified.
- Wall 3: the "hardware blocker" dissolved under research (Newton/Warp ship native Windows sm_120);
  M0 control arm is training as this document is written.
- Wall 1: capacity hypothesis DOWNGRADED by literature; the delex+copy + simple-register plan
  attacks the actual constraint. The in-flight 56M run becomes the control arm either way.

None of this is AGI. It is four walls converted from "unknowns" into measured, funded, moving
workstreams — which is the only honest way walls fall.
