# ATANOR Product Conversation Grounding

Status: product dashboard conversation guardrail.

Product conversation should avoid generic safety/status fallback phrases when the user asks a meaningful question. The current path is:

1. Classify the utterance with `route_conversation_request`.
2. Gather bounded local context with `gather_grounded_context`.
3. Realize a public answer with `generate_conversation_surface`.
4. Keep hidden traces private and expose only bounded diagnostics.

Examples:

- Greeting: surface-only ASM-v0 is allowed.
- Local Brain vs Cloud Brain: answer from architecture grounding.
- Memory request: answer from approval-gate policy.
- "Are you rule-based?": answer honestly that ASM-v0 is construction/heuristic based, not a general LM.
- Nonsensical premise: answer the premise boundary instead of unrelated project status.

Safety invariants:

- No external LLM or sLLM call.
- No Local Brain write.
- No production store mutation.
- No candidate promotion.
- No generated code execution.
- No real consciousness or AGI claim.

This grounding layer makes the system more honest, not more magically capable. Unknown questions should remain unknown instead of being padded with generic status text.
