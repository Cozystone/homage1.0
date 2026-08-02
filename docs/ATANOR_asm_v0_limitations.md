# ATANOR ASM-v0 Limitations

Status: honesty baseline for product conversation.

ASM-v0 is not a general language model. It is a local, construction-conditioned surface generator backed by hand-authored constructions, heuristic act inference, and a small local transition surface.

The product conversation path must not claim that ASM-v0 performs unrestricted reasoning, real consciousness, AGI-level cognition, or hidden chain-of-thought revelation. It may expose bounded public diagnostics, but raw internal traces remain hidden.

Required truth labels:

- `external_llm_used=false`
- `external_sllm_used=false`
- `direct_prompt_answer_table_used=false`
- `hand_authored_construction_used=true`
- `heuristic_act_inference_used=true`
- `raw_hidden_cot_claim=false`
- `consciousness_claim=false`

Pure ASM-v0 surface generation is appropriate for greetings and lightweight conversation only. Meaningful questions should be routed through semantic grounding before realization.
