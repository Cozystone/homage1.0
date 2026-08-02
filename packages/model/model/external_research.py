from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


ResearchUse = Literal[
    "offline_teacher",
    "evaluator",
    "distillation_candidate_review",
    "architecture_reference",
]


@dataclass(frozen=True)
class ExternalModelResearchCandidate:
    """Metadata for external/open models that may inform ATANOR research.

    These candidates are deliberately not runtime answer providers. ATANOR's
    product conversation path remains ASM/CGSR/RHFC/verified-evidence based
    unless a separate, explicit policy change is made and tested.
    """

    model_id: str
    family: str
    license_name: str
    official_repository: str
    official_weights: str
    local_runtime_notes: tuple[str, ...]
    allowed_uses: tuple[ResearchUse, ...]
    default_enabled: bool = False
    answer_path_allowed: bool = False
    external_llm_used_if_enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


GLM_52_RESEARCH_CANDIDATE = ExternalModelResearchCandidate(
    model_id="zai-org/GLM-5.2",
    family="GLM-5.2 MoE",
    license_name="MIT",
    official_repository="https://github.com/zai-org/GLM-5",
    official_weights="https://huggingface.co/zai-org/GLM-5.2",
    local_runtime_notes=(
        "744B-A40B scale; not suitable as a lightweight default dashboard model.",
        "SGLang/vLLM/ktransformers/llama.cpp-GGUF paths are research deployment options.",
        "Any invocation would set external_llm_used=true and must stay outside the default answer path.",
    ),
    allowed_uses=(
        "offline_teacher",
        "evaluator",
        "distillation_candidate_review",
        "architecture_reference",
    ),
)


def known_external_research_candidates() -> tuple[ExternalModelResearchCandidate, ...]:
    return (GLM_52_RESEARCH_CANDIDATE,)


def get_external_research_candidate(model_id: str) -> ExternalModelResearchCandidate:
    normalized = str(model_id or "").strip().lower()
    for candidate in known_external_research_candidates():
        if candidate.model_id.lower() == normalized:
            return candidate
    raise KeyError(f"unknown external research candidate: {model_id}")


def external_candidate_policy_snapshot(model_id: str = "zai-org/GLM-5.2") -> dict:
    candidate = get_external_research_candidate(model_id)
    return {
        "candidate": candidate.to_dict(),
        "atanor_default_answer_path_unchanged": True,
        "runtime_answer_provider": False,
        "requires_explicit_research_gate": True,
        "must_report_external_llm_used_if_invoked": candidate.external_llm_used_if_enabled,
        "production_store_mutation_allowed": False,
        "local_brain_write_allowed": False,
        "candidate_promotion_allowed": False,
    }
