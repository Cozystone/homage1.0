# ATANOR GLM-5.2 Research Bridge

Status: research-only candidate, not a default answer path.

## Verified External References

- Official repository: https://github.com/zai-org/GLM-5
- Official weights: https://huggingface.co/zai-org/GLM-5.2
- Local/offload reference: https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/kt-kernel/GLM-5.2-Tutorial.md
- GGUF reference: https://unsloth.ai/docs/models/glm-5.2

As of this audit, the official model card describes GLM-5.2 as MIT licensed.
The GitHub model table lists GLM-5.2 as a 744B-A40B model family. That scale
means it is not a reasonable lightweight default model for the product
dashboard, even on a strong local GPU.

## ATANOR Boundary

GLM-5.2 is an external LLM-class model. Using it in the live answer path would
change ATANOR's current invariant:

- `external_llm_used=false`
- `external_sllm_used=false`
- `rule_based_answer_used=false`

Therefore GLM-5.2 must not be wired into `/api/chat/atanor` as the default
conversation engine.

## Allowed Uses

GLM-5.2 may be used only behind an explicit research gate for:

- offline teacher comparison against ASM/CGSR outputs
- evaluator-only scoring of self-grown constructions
- distillation candidate review, where outputs enter a review queue rather than
  production behavior
- architecture reference for long-context routing, speculative decoding, or
  CPU/GPU offload planning

Any actual invocation must report `external_llm_used=true` in the resulting
research artifact. It must not write to Local Brain, mutate `verified_store_v0`,
promote candidates, or overwrite ATANOR's self-grown construction bank.

## Implementation Hook

`packages/model/model/external_research.py` registers GLM-5.2 as a disabled
research candidate:

- `default_enabled=false`
- `answer_path_allowed=false`
- `external_llm_used_if_enabled=true`

This gives ATANOR a place to remember official GLM-5.2 metadata without turning
the model into a hidden runtime dependency.

## Recommended Next Step

If we use GLM-5.2 later, the next slice should be a dry-run evaluator:

1. feed the same verified-evidence question to ASM/CGSR and GLM-5.2;
2. compare factual coverage, Korean naturalness, and refusal behavior;
3. store only metrics and reviewed construction deltas;
4. keep generated text out of production unless it passes a signed human review
   gate.
