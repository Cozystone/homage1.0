from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


InputType = Literal[
    "text",
    "voice_transcript",
    "system_status",
    "candidate_run_result",
    "user_goal",
    "morning_wake",
]
RuntimeStateName = Literal[
    "idle",
    "observing",
    "detecting_deficit",
    "deliberating",
    "checking_privacy",
    "checking_promotion",
    "routing",
    "planning_response",
    "awaiting_user_approval",
    "blocked",
    "completed",
]
ProposalType = Literal[
    "answer_user",
    "ask_user_approval",
    "run_promotion_review",
    "open_congress_thread",
    "create_morning_brief",
    "defer",
    "block",
]


def _require_text(name: str, value: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _unit_interval(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class SelfhoodRuntimeInput:
    """Unified proof-only input bus for text, voice transcripts, and status events."""

    input_id: str
    input_type: InputType
    text: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    requires_review: bool = True

    def __post_init__(self) -> None:
        _require_text("input_id", self.input_id)
        if self.input_type in {"text", "voice_transcript", "user_goal"} and not self.text:
            raise ValueError("text is required for textual input types")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfhoodRuntimeState:
    """Observable runtime state for the integrated self-model loop."""

    state: RuntimeStateName = "idle"
    active_goal: str | None = None
    detected_signals: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    safety_flags: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfhoodRuntimeProposal:
    """A reviewable proposal. It is never an executed action."""

    proposal_id: str
    title: str
    summary: str
    proposal_type: ProposalType
    text_response: str | None = None
    voice_response_enabled: bool = False
    requires_user_approval: bool = True
    mutates_production: bool = False
    mutates_local_brain: bool = False
    uses_real_p2p: bool = False
    executes_code: bool = False
    confidence: float = 0.5
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("proposal_id", self.proposal_id)
        _require_text("title", self.title)
        _require_text("summary", self.summary)
        object.__setattr__(self, "confidence", _unit_interval("confidence", self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfhoodRuntimeResult:
    """Final proof-only cycle result with explicit mutation accounting."""

    result_id: str
    input_id: str
    final_state: RuntimeStateName
    proposals: list[SelfhoodRuntimeProposal]
    events: list[dict[str, Any]]
    safety: dict[str, Any]
    text_output: str | None = None
    voice_output_event: dict[str, Any] | None = None
    actual_mutations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("result_id", self.result_id)
        _require_text("input_id", self.input_id)
        blocked_mutations = {
            key: value
            for key, value in self.actual_mutations.items()
            if bool(value)
        }
        if blocked_mutations:
            raise ValueError(f"Selfhood Runtime proof result cannot mutate: {blocked_mutations}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["proposals"] = [proposal.to_dict() for proposal in self.proposals]
        return payload
