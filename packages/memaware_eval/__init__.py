# -*- coding: utf-8 -*-
"""memaware_eval — measure ATANOR on MemAware (proactive memory retrieval).

MemAware (github.com/kevin-hs-sohn/memaware, MIT; data derived from LongMemEval, MIT) asks a
different question from every other memory benchmark: not "can you FIND the answer when asked"
(RAG / reactive retrieval) but "do you SURFACE the relevant past context when nobody asked for
it" (proactive recall). 900 implicit-context questions over a 3-month, 1307-session history,
split into 3 tiers: easy (keyword overlap exists), medium (same domain, different words), hard
(cross-domain, zero keyword overlap).

Why this is the benchmark most ALIGNED with ATANOR: our Layer-A live memory + associative recall
is exactly a proactive-surface organ (learn a fact this turn, surface it next turn, no retrain).

HONEST SCOPE. The official harness answers each question with an LLM (kimi-k2) and grades the
RESPONSE with a GPT-5.1 judge. ATANOR is No-LLM and we do not call an external judge, so this
package runs a PYTHON ADAPTATION that measures the layer upstream of the response: does ATANOR's
memory organ PROACTIVELY SURFACE the correct past session in its top-k recall? The grader is
deterministic — a hit requires the retrieved item's PROVENANCE (its source session id) to match
the labeled gold session; a miss scores 0. There is no path to score without surfacing the real
gold episode, so a fabricated / hallucinated "recall" cannot earn points (fabricated-recall = 0
by construction). See README.md for the full metric definition and its limits vs the official
response-level number.
"""
