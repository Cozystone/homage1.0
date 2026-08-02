# ASM-v0: From Hand-Authored Frames to Self-Grown Candidates

ASM-v0 currently produces product conversation through a bounded local path:

- transparent route classification;
- semantic grounding metadata;
- hand-authored construction frames;
- local transition surfaces;
- explicit honesty metadata.

This is not a general neural language model and should not be described as one.
The current implementation remains construction/heuristic-heavy.

Self-Grown Construction Bank v0 adds a candidate layer:

1. Extract short, reusable construction patterns from successful local outputs
   and reviewed sources.
2. Score each candidate for novelty, usefulness, naturalness, grounding,
   template risk, and safety risk.
3. Keep every result as a candidate until human review.
4. Export candidates to the Agentic Review Queue.
5. Retrieve only reviewed candidates in product mode; lab mode can preview raw
   candidates for diagnosis.

This creates a path away from manually written frames without hiding the current
limitations. Production activation remains a future signed-manifest gate.
