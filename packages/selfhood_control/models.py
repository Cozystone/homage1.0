from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SelfhoodInputSource = Literal[
    "voice_transcript",
    "scheduled_idle_check",
    "morning_wake",
    "user_manual_request",
    "proof_fixture",
]
SelfhoodAction = Literal[
    "no_action",
    "ask_user",
    "propose_research",
    "propose_promotion_review",
    "propose_code_patch",
    "present_morning_brief",
    "speak_status",
    "blocked",
]


def _required(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


@dataclass(frozen=True)
class SelfhoodInput:
    input_id: str
    source: SelfhoodInputSource
    text: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("input_id", self.input_id)
        if self.source == "voice_transcript" and not self.text:
            raise ValueError("voice_transcript input requires text")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfhoodContext:
    context_id: str
    world_model_summary: dict[str, Any]
    self_model_summary: dict[str, Any]
    resource_state: dict[str, Any]
    user_goals: list[str]
    active_project: str | None
    privacy_policy: dict[str, Any]
    timestamp: str

    def __post_init__(self) -> None:
        _required("context_id", self.context_id)
        _required("timestamp", self.timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfhoodDecision:
    decision_id: str
    input_id: str
    deficits: list[dict[str, Any]]
    congress_summary: dict[str, Any] | None = None
    privacy_report: dict[str, Any] | None = None
    trust_route: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    voice_response: dict[str, Any] | None = None
    morning_event: dict[str, Any] | None = None
    action: SelfhoodAction = "no_action"
    requires_user_approval: bool = True
    mutates_production: bool = False
    mutates_local_brain: bool = False
    uses_real_p2p: bool = False
    uses_external_llm: bool = False
    safety_notes: list[str] = field(default_factory=list)
    generated_code_executed: bool = False
    real_hot_swap_performed: bool = False
    raw_private_data_exported: bool = False
    real_cloud_upload: bool = False
    always_listening_enabled: bool = False
    candidate_promotion: bool = False
    pair_edges_sent: int = 0

    def __post_init__(self) -> None:
        _required("decision_id", self.decision_id)
        _required("input_id", self.input_id)
        if self.mutates_production:
            raise ValueError("proof decision must not mutate production")
        if self.mutates_local_brain:
            raise ValueError("proof decision must not mutate Local Brain")
        if self.uses_real_p2p:
            raise ValueError("proof decision must not use peer-network transport")
        if self.uses_external_llm:
            raise ValueError("proof decision must not use external LLM")
        if self.generated_code_executed:
            raise ValueError("proof decision must not execute generated code")
        if self.real_hot_swap_performed:
            raise ValueError("proof decision must not perform production code replacement")
        if self.raw_private_data_exported:
            raise ValueError("proof decision must not export raw private data")
        if self.real_cloud_upload:
            raise ValueError("proof decision must not upload to cloud")
        if self.always_listening_enabled:
            raise ValueError("proof decision must not enable always-listening")
        if self.candidate_promotion:
            raise ValueError("proof decision must not promote candidates")
        if self.pair_edges_sent != 0:
            raise ValueError("proof decision must not send pair edges")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfhoodRunReport:
    run_id: str
    scenario: str
    decisions: list[SelfhoodDecision]
    invariants: dict[str, Any]
    passed: bool
    limitations: list[str]

    def __post_init__(self) -> None:
        _required("run_id", self.run_id)
        _required("scenario", self.scenario)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decisions"] = [decision.to_dict() for decision in self.decisions]
        return data
