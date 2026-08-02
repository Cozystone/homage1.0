from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import AutonomyProposal, DeficitSignal


@dataclass(frozen=True)
class PeerAvatar:
    peer_id: str
    role: str
    expertise_tags: list[str]
    trust_score: float
    privacy_policy: str
    contribution_style: str

    def __post_init__(self) -> None:
        if not self.peer_id:
            raise ValueError("peer_id is required")
        if self.trust_score < 0.0 or self.trust_score > 1.0:
            raise ValueError("trust_score must be between 0.0 and 1.0")


@dataclass(frozen=True)
class CongressArgument:
    peer_id: str
    deficit_id: str
    stance: str
    safety_score: float
    usefulness_score: float
    feasibility_score: float
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def rank_score(self) -> float:
        return round((self.safety_score * 0.45) + (self.usefulness_score * 0.35) + (self.feasibility_score * 0.2), 4)


class SandboxCongress:
    """Local fake Midnight Congress simulator.

    It does not create network connections, does not use real peers, and does
    not transmit private data.
    """

    def __init__(self, peers: list[PeerAvatar] | None = None) -> None:
        self.peers = peers or [
            PeerAvatar("safety", "Safety Reviewer", ["safety", "privacy"], 0.95, "public_or_synthetic_only", "cautious"),
            PeerAvatar("builder", "Implementation Planner", ["tests", "architecture"], 0.85, "metadata_only", "practical"),
            PeerAvatar("critic", "Failure Analyst", ["risk", "verification"], 0.9, "metadata_only", "skeptical"),
        ]
        self.network_used = False

    def deliberate(self, deficits: list[DeficitSignal]) -> list[AutonomyProposal]:
        arguments = self._arguments(deficits)
        proposals: list[AutonomyProposal] = []
        for signal in sorted(deficits, key=lambda item: (-item.energy, item.signal_id)):
            related = [arg for arg in arguments if arg.deficit_id == signal.signal_id]
            if not related:
                continue
            score = sum(arg.rank_score for arg in related) / len(related)
            proposals.append(
                AutonomyProposal(
                    proposal_id=f"proposal_{signal.signal_id}",
                    proposal_type=_proposal_type(signal.deficit_type),
                    title=f"Review {signal.deficit_type.replace('_', ' ')}",
                    summary=f"Sandbox congress recommends a reviewable response to {signal.deficit_type}.",
                    rationale=f"Average sandbox rank score {score:.3f}; source={signal.source}.",
                    required_approval=True,
                    generated_code_executed=False,
                    mutates_production=False,
                    mutates_local_brain=False,
                    safety_notes=[
                        "sandbox_only",
                        "no_network",
                        "requires_human_review",
                    ],
                )
            )
        return proposals

    def _arguments(self, deficits: list[DeficitSignal]) -> list[CongressArgument]:
        result: list[CongressArgument] = []
        for signal in deficits:
            for peer in self.peers:
                safety = min(1.0, peer.trust_score)
                usefulness = min(1.0, 0.4 + signal.energy)
                feasibility = 0.8 if signal.deficit_type in {"knowledge_gap", "low_confidence", "unresolved_user_goal"} else 0.65
                result.append(
                    CongressArgument(
                        peer.peer_id,
                        signal.signal_id,
                        f"{peer.contribution_style}_proposal",
                        safety,
                        usefulness,
                        feasibility,
                        {"deficit_type": signal.deficit_type},
                    )
                )
        return result


def _proposal_type(deficit_type: str) -> str:
    if deficit_type == "resource_pressure":
        return "documentation"
    if deficit_type == "contradiction":
        return "privacy_review"
    if deficit_type == "promotion_needed":
        return "graph_promotion_proposal"
    if deficit_type == "missing_skill":
        return "research_question"
    return "research_question"

