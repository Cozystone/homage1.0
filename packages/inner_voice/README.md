# ATANOR Inner Voice

Inner Voice is an explicit self-narration channel generated from observable
ATANOR runtime state: emotion vector, policy decision, permission tier, action
candidates, blocked actions, uncertainty, and next intent.

V1 routes that state through a local ASM/CGSR-style construction bank before
surface text is emitted. The selected construction records an act, stance,
required slots, discourse moves, and a surface score. This makes the visible
self-narration less like deterministic logging while keeping it bounded to
observable runtime signals.

It is not hidden chain-of-thought, not a claim of real consciousness, and not a
Local Brain memory write. Product mode receives only a short redacted summary.
Lab mode can inspect recent frames for debugging the self-model loop.

Safety invariants:

- no external LLM or sLLM calls
- no raw hidden chain-of-thought exposure
- no consciousness, AGI, or real-emotion claim
- no Local Brain write, production mutation, candidate promotion, commit, or push
- product mode hides full frames and exposes only visible self-narration
