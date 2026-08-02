# Review: Copilot's "human-like video understanding" pipeline vs ATANOR (2026-07-20)

The owner relayed a Copilot design: to understand video like a human you need
frame → object → action → EVENT → memory → reasoning (+ world model / common sense), not just a
vision model. The owner's stake: if this works, ALL visual information — every context, and
smart-glasses perception — becomes understandable.

## Verdict: the pipeline is correct, and ATANOR already has 5 of the 6 stages as organs.
The proposal's stages map almost one-to-one onto existing ATANOR perception organs. The genuinely
missing piece was a single stitch between them, which this change ships.

| Proposal stage | ATANOR organ | status |
|---|---|---|
| frame → objects | `perception/open_vocab.py` (OWLv2 open-vocab) | ✅ existed |
| objects → scene + relations | `perception/scene_graph.py` (typed spatial relations, graph) | ✅ existed |
| object identity across time | `perception/object_recognition.py` (visual signature cells) | ✅ existed |
| **frames → EVENTS over time** | — | ❌ **the gap** |
| long-term memory | `episodic_memory/bitemporal.py` (bitemporal recall) | ✅ existed |
| reasoning + world model (common sense) | `temporal_reasoning/*` (learned causal order + counterfactual), intent organs | ✅ built this week |

## The one missing stitch — now shipped: `perception/video_events.py`
Nobody was turning a SEQUENCE of per-frame scene graphs into events over time. That is exactly the
"action → event" stage. It is built by DIFFING consecutive scene graphs, reusing the existing
organs, no new heavy model:
- appear / vanish (node set changes), approach / separate (near-edge changes), take / release
  (possession change: fridge-contains-milk → person-contains-milk = "took the milk").
- events are written into bitemporal memory, so "the keys went on the desk at t1" is later
  answered by RECALL ("where are the keys? → on the desk"), not by re-watching. Verified in tests.

## Honesty design (the part that makes this ATANOR, not a hallucinating captioner)
- The NARRATIVE is factual: every event traces to a concrete frame diff (`evidence` field). An
  empty→empty transition invents nothing.
- INTENT is offered as a FLAGGED HYPOTHESIS, never asserted. "person may intend to use the milk"
  carries `is_hypothesis: true`, low confidence, and the events it leans on — the generative-leap
  doctrine: a leap is marked, never stated as truth. This is the difference from the proposal's
  confident "probably going to drink it": we surface the guess AS a guess.

## The owner's bigger claim is right, and here's why the architecture generalizes
The owner said: solve video and you solve all visual info + all context + smart glasses. Correct,
because ATANOR's pipeline is modality-agnostic at the seam: everything becomes a scene graph →
events → the SAME concept graph, memory, and causal engine that already serve text and web. A
smart-glasses stream is just a live frame sequence into `understand_video`; the spatial-memory
organ (`perception/spatial_memory.py`, the Jarvis axis) already rebuilds "where things were". So the
same stitch serves recorded video, a live camera, and glasses — one event/memory/reasoning spine,
many sensors.

## Honest gaps (v0)
- Action vocabulary is coarse (appear/approach/take/…), derived from geometry+possession, not a
  learned action model. Fine-grained actions (open/pour/assemble) need either richer relations or a
  learned action recognizer — the same "learn it, seal it" path we used for temporal order.
- No real video decoded yet in this module: it consumes per-frame scene graphs (the output of the
  existing detector). Wiring a real decode → detect → this stitch is the next step, and it reuses
  `atanor_browser.autonomous_surf.perceive_media`'s image lane per frame.
- Intent hypotheses are template-grounded; making them learned (from the causal field, "take X →
  usually followed by Y") is the natural upgrade and connects directly to this week's temporal work.
