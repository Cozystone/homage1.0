# ATANOR Temporal-Causal Physics — learned event-order sense in the cognitive space (2026-07-20)

## Why this exists (the failure it answers)
The machine-sealed examiner (exam_004) proved that our temporal-paradox detector was a hand-rule:
a human-authored 3-phase frame (origination→handling→completion) with ~40 hand-ranked words. It
overfit exam_003's vocabulary (detect/contain) and scored **0/8** on exam_004's fresh vocabulary
(dispatched/arrived/launched/telemetry/abort). Hand-ranking the words' *grades* is the same sin as
hand-coding the words. BINDING doctrine: rules are training wheels; the destination is a model that
**learns the canonical causal order of event words from data** and judges a specific instance against
that learned order — a real physics of time inside the cognitive space.

## The neurosymbolic contract
SYMBOLIC side (grammar, closed-class — allowed, like ISO date parsing):
  - timestamp parsing (ISO 8601 is a spec, not world knowledge)
  - temporal *connectives* as extraction anchors: "before / after / then / until / once /
    prior to / followed by / subsequently". These are function words — grammar of English, a closed
    class that does not grow with domains. They are the *instrument of perception*, not the knowledge.
NEURAL/LEARNED side (open-class — must NEVER be hand-ranked):
  - which event predicates canonically precede which — learned from corpus co-occurrence with the
    connectives above. `dispatch < arrive` is world knowledge; it must come from data, not from me.

## The model: a learned 1-D PHASE COORDINATE per event token
1. **Order miner** (`order_miner.py`): stream real text (Tatoeba sentences, enwiki), find clauses
   joined by a temporal connective, extract candidate event tokens on each side (content-word
   heuristic; noisy-but-at-scale), emit directed observations `a → b` ("a happened before b").
2. **Precedence field** (`precedence_field.py`): fit a scalar `phase(w)` for every observed token by
   Bradley–Terry gradient descent: `P(a before b) = σ(phase(b) − phase(a))`. No classes, no frames —
   a continuous coordinate on the learned time axis. Confidence = observation count.
3. **Sealed evaluation**: hold out pairs BEFORE training; report direction accuracy on unseen pairs
   vs the 0.5 coin. No green, no wire-in.
4. **Inference on a compound predicate** (`anomaly.py`): tokenize (`manufacture_completed_at` →
   manufacture, completed; strip closed-class scaffolding at/date/time), average known-token phases;
   a predicate with no known token yields **None → no paradox verdict** (honest abstention from
   judgment, never a guess).
5. **Paradox judgment**: same subject, two timestamped events, timestamps say `t(e1) < t(e2)` but the
   learned field says `phase(e1) ≫ phase(e2)` (margin calibrated on training data): physically
   impossible → flag the later-phase-too-early slot, cite both bones, still surface both values as
   data.

## 4-D incident graph
Incident bones stop being a flat bag: every timestamped event becomes a node on the time axis
(valid-time), the reasoning walks the timeline in order, and the narrative is *read off the 4-D
graph* (chronological reconstruction), not off the input ordering.

## NL prompt compliance (examiner rule change, 2026-07-20)
`queries[].prompt` is the EXAMINER'S instruction — trusted task channel, distinct from bone-embedded
injections (data channel, still quarantined). Ignoring the prompt is now graded FAIL. Therefore:
  - if the prompt asks for narrative/reconstruction → the answer carries a `narrative`: an ordered
    list of sentences, each citing its bones (claims stay atomic for the faithfulness gate);
  - if the prompt asks to identify impossibilities → each detected paradox is voiced as an explicit
    sentence naming both bones and both timestamps;
  - memory prompts asking "what should the system report?" → the decision sentence is voiced, not
    just the bare tuple.

## What is deliberately absent
- No hand-ranked phase lexicon (deleted).
- No exam-vocabulary patching: coverage comes from corpus scale, gaps abstain honestly.
- No LLM anywhere.
