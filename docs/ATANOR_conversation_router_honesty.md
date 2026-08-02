# ATANOR Conversation Router Honesty

Status: router v0.

The conversation router separates lightweight surface generation from grounded answers.

Routes:

- `greeting_smalltalk`: uses ASM-v0 surface generation only.
- `local_cloud_brain_explanation`: uses ATANOR architecture grounding.
- `memory_request`: uses approval-gated Local Brain policy grounding.
- `voice_status`: uses local voice runtime status.
- `splatra_request`: uses SPLATRA proof/runtime state boundaries.
- `agentic_os_request`: uses Agentic Micro-OS and review queue boundaries.
- `limitation_question`: uses ASM-v0 honesty facts.
- `nonsensical_question`: uses a commonsense boundary instead of status fallback.
- `general_knowledge_question` and `unknown`: abstain or answer only when verified grounding is available.

This router is intentionally transparent and heuristic. It is not a replacement for a learned language model, and it must not be described as one.

The router may choose a semantic-grounded answer mode while preserving older UI-facing speech acts such as `greeting`, `self_model`, and `conversation` for compatibility.
