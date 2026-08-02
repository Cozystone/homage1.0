from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .event_stream import EgoEvent, InMemoryEgoEventStream, utc_now
from .models import CongressArgument, CongressSynthesis, EgoCartridge, MidnightCongressTopic


DETERMINISTIC_ROLES = ["skeptic", "builder", "privacy_guard", "router", "domain_expert", "synthesis_chair"]


@dataclass(frozen=True)
class MorningBriefEvent:
    event_id: str
    topic_id: str
    summary: str
    requires_user_action: bool
    proposed_cartridge_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic_id": self.topic_id,
            "summary": self.summary,
            "requires_user_action": self.requires_user_action,
            "proposed_cartridge_id": self.proposed_cartridge_id,
        }


@dataclass(frozen=True)
class CongressRun:
    topic: MidnightCongressTopic
    arguments: list[CongressArgument]
    synthesis: CongressSynthesis
    morning_brief: MorningBriefEvent
    real_p2p_used: bool = False
    external_llm_used: bool = False
    raw_private_data_exported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic.to_dict(),
            "arguments": [argument.to_dict() for argument in self.arguments],
            "synthesis": self.synthesis.to_dict(),
            "morning_brief": self.morning_brief.to_dict(),
            "real_p2p_used": self.real_p2p_used,
            "external_llm_used": self.external_llm_used,
            "raw_private_data_exported": self.raw_private_data_exported,
        }


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class MidnightCongressSimulator:
    """Deterministic local-only Congress simulator.

    It does not contact peers, call an LLM, export private data, or mutate stores.
    """

    def __init__(self, stream: InMemoryEgoEventStream | None = None) -> None:
        self.stream = stream or InMemoryEgoEventStream()

    def deliberate(
        self,
        topic: MidnightCongressTopic,
        cartridge: EgoCartridge | None = None,
    ) -> CongressRun:
        self.stream.append_event(
            EgoEvent(
                _stable_id("event", topic.topic_id, "start"),
                "ego.midnight_congress_started",
                utc_now(),
                f"Midnight Congress started for {topic.title}",
                {"topic_id": topic.topic_id},
            )
        )
        blocked = topic.privacy_grade == "private_local_only" or (
            cartridge is not None and cartridge.privacy_grade == "private_local_only"
        )
        arguments = self._arguments(topic, blocked)
        if blocked:
            synthesis = CongressSynthesis(
                _stable_id("synth", topic.topic_id, "blocked"),
                topic.topic_id,
                "Private-local-only material is blocked from relay and requires privacy review.",
                ["Keep raw private data local.", "Create a synthetic/public summary only after user approval."],
                None,
                requires_user_approval=True,
                mutates_production=False,
                mutates_local_brain=False,
            )
        else:
            proposed_id = cartridge.cartridge_id if cartridge else None
            recommendations = ["Prepare proposal-only ego cartridge metadata.", "Ask the user before any durable merge."]
            if "contradiction" in topic.deficit_type:
                recommendations.append("Keep skeptic objection attached until evidence resolves the contradiction.")
            if "low_confidence" in topic.deficit_type:
                recommendations.append("Create a research proposal instead of asserting a conclusion.")
            synthesis = CongressSynthesis(
                _stable_id("synth", topic.topic_id, "synthesized"),
                topic.topic_id,
                f"Deterministic Congress synthesized a proposal for {topic.title}.",
                recommendations,
                proposed_id,
                requires_user_approval=True,
                mutates_production=False,
                mutates_local_brain=False,
            )
        morning = MorningBriefEvent(
            _stable_id("brief", topic.topic_id, synthesis.synthesis_id),
            topic.topic_id,
            synthesis.summary,
            requires_user_action=True,
            proposed_cartridge_id=synthesis.proposed_cartridge_id,
        )
        self.stream.append_event(
            EgoEvent(
                _stable_id("event", topic.topic_id, "synth"),
                "ego.midnight_congress_synthesized",
                utc_now(),
                synthesis.summary,
                synthesis.to_dict(),
                requires_user_action=True,
            )
        )
        self.stream.append_event(
            EgoEvent(
                morning.event_id,
                "ego.morning_gift",
                utc_now(),
                morning.summary,
                morning.to_dict(),
                requires_user_action=morning.requires_user_action,
            )
        )
        if synthesis.requires_user_approval:
            self.stream.append_event(
                EgoEvent(
                    _stable_id("event", topic.topic_id, "approval"),
                    "ego.user_approval_required",
                    utc_now(),
                    "User approval required before merge or promotion.",
                    {"topic_id": topic.topic_id, "synthesis_id": synthesis.synthesis_id},
                    requires_user_action=True,
                )
            )
        return CongressRun(topic, arguments, synthesis, morning)

    def _arguments(self, topic: MidnightCongressTopic, blocked: bool) -> list[CongressArgument]:
        claims = {
            "skeptic": "Do not treat proof-only deliberation as real peer consensus.",
            "builder": "A proposal-only cartridge can preserve context for morning review.",
            "privacy_guard": "Private-local-only data must not leave the local proof boundary.",
            "router": "Atlas Router is referenced conceptually; no real P2P route is opened.",
            "domain_expert": "The topic should stay evidence-bound and confidence-limited.",
            "synthesis_chair": "Synthesis requires user approval before any durable action.",
        }
        arguments: list[CongressArgument] = []
        for idx, role in enumerate(DETERMINISTIC_ROLES, start=1):
            objections = []
            if role == "privacy_guard" and blocked:
                objections.append("private_local_only_export_blocked")
            if role == "skeptic" and "contradiction" in topic.deficit_type:
                objections.append("contradiction_requires_more_evidence")
            if role == "domain_expert" and "low_confidence" in topic.deficit_type:
                objections.append("low_confidence_research_only")
            arguments.append(
                CongressArgument(
                    f"{topic.topic_id}_arg_{idx}",
                    topic.topic_id,
                    role,
                    claims[role],
                    [f"deficit:{item}" for item in topic.source_deficit_ids],
                    max(0.35, 0.9 - idx * 0.07),
                    objections,
                )
            )
        return arguments
