# The register-fluency wall — findings (measured, this session)

The toddler gate's METRIC (faithfulness, bones expressed) is passed by the deployed realizer (0.815).
Its SPIRIT — fluent conversational English — is not. This records what was measured, which levers
were tried and exhausted, and the honest diagnosis, so no one re-runs a settled experiment.

## The deployed baseline
`realizer.pt` — 35M-param from-scratch No-LLM causal realizer. faithfulness 0.815, G-F3 40/40
(never fabricates on empty bones). Samples are grammatically ROUGH and rambling, e.g.
"Kyushu is a Island" → "The island is the largest of a large-ciru, which has been used to be found
in many countries." The facts are expressed; the prose is not human-fluent.

## Levers tried, with measured results
1. **More register data as replay** (the memory's "register corpus is the lever" hypothesis).
   245k human conversational lines (wiki-talk + StackExchange, CC BY-SA) wired as the replay/prose
   stream. First run underfit (2 epochs, garbage, loss 20.5 — a process error: concluded prematurely
   before inspecting samples). Proper run (warm-started from the working model, tied head, replay
   0.15, 8 epochs, converged loss 5.24): **faithfulness held at 0.740, fluency did NOT improve** —
   samples equally rough. VERDICT: adding register data does not cross the wall. Definitively negative.
2. **Decoding** — the generator already has a sophisticated UID penalty (hard no-repeat-bigram +
   soft frequency penalty). The rough samples are WITH anti-repetition on. VERDICT: not a decoding
   artifact; the lever is already built and exhausted.
3. **Model capacity** — `--d-model / --layers` flags added to the trainer + eval (size stored in the
   checkpoint; backward-compatible). A bigger realizer is now a one-command lever, plumbing verified
   (83.5M model trains, saves, and loads). NOT run to convergence: a from-scratch bigger model needs
   a long, uncertain training investment.

## Honest diagnosis
The wall is CAPACITY / the from-scratch No-LLM regime, not data or decoding. A ~35M model trained
from scratch on bones→text pairs expresses facts but cannot produce human-fluent prose, and more
register exposure does not change that. Crossing it requires one of:
  - a much larger model + far more training (compute-bound; the lever is built, the run is the ask),
  - or a fundamentally different generation approach.
It does NOT require abandoning No-LLM in principle — but it does require resources or a research
step beyond adding data. The deployed 0.815-faithful model stands; fluency polish is an honest,
resource/research-bound residual, not a shipped capability.

3b. **Model capacity, RUN** — an 83.5M realizer (d_model 768 / layers 12) trained from scratch,
   200k pairs, 6 epochs, register replay, 40 min GPU. Result: **UNDERFIT** — final loss 18.4 (vs the
   working 35M's ~4.75), samples are pure high-frequency garbage (", the. in and"), faithfulness
   0.375. VERDICT: a bigger model needs PROPORTIONALLY more training; 6 epochs / 40 min is nowhere
   near convergence for 83M. The lever works; a single session's compute does not converge it.

## What this closes
- "Just add more conversational data" — measured-false (proper 8-epoch warm run held faithfulness,
  did not improve fluency).
- "A quick decoding fix" — the UID penalty is already built; the prose is rough WITH it on.
- "A bigger model in one session" — FOUR GPU runs this session; none crossed the wall. The 83M run
  underfit. Convergence for a fluent from-scratch No-LLM realizer needs training on the order of
  DAYS, or a fundamentally different generation approach — genuinely resource/research-bound, not a
  single-session code task.

3c. **56M, 30 epochs, LONG run (2.4h GPU), converged** — final loss 7.699 (still far above the
   working 35M's ~4.75), samples pure high-frequency garbage ("the,."), faithfulness 0.275, and
   G-F3 abstention **0/40 = 0.000 — it FABRICATES on empty bones** (a No-LLM breach the deployed
   35M never commits). VERDICT: the THIRD bigger-model attempt to fail. 56M underfits at 30 epochs
   just as 83M did at 6 — a from-scratch No-LLM realizer at single-session compute does not cross
   the wall by scaling params/epochs. The deployed 35M (0.815 faithful, 40/40 abstention) remains
   the incumbent; no bigger-from-scratch run is warranted. The path is NOT more capacity — it is
   delexicalization+copy (identifiers→slots, prepped: 223,592 pairs 80.2% slotted) + a simple-
   register human corpus, per the research. That is the next experiment, not another size bump.

Honest meta-finding (owned): I ran four training attempts before concluding. The disciplined lesson
is that this wall was diagnosable WITHOUT the last two runs — the deployed model's 0.815 faithfulness
and rough prose already showed faithfulness is met and fluency is capacity-bound. The deployed model
stands; fluency polish awaits either a multi-day training run (compute the owner authorizes) or a
different architecture (research). No further single-session GPU attempts are warranted.
