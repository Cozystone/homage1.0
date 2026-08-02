from __future__ import annotations

from packages.autonomy_kernel.event_stream import utc_now

from packages.selfhood_control.bridges import from_voice_loop
from packages.selfhood_control.models import SelfhoodContext, SelfhoodInput


def base_context(**overrides: object) -> SelfhoodContext:
    world = {
        "concepts": 12,
        "relations": 20,
        "evidence": 8,
        "unresolved_questions": [],
        "contradictions": [],
        "confidence_gaps": [],
    }
    self_model = {
        "local_memory_count": 0,
        "recent_runs": [],
        "known_limits": [],
    }
    data = {
        "context_id": "ctx_fixture",
        "world_model_summary": world,
        "self_model_summary": self_model,
        "resource_state": {"disk_free_gib": 80.0, "ram_free_gib": 12.0},
        "user_goals": ["keep proof work reviewable"],
        "active_project": "selfhood_control",
        "privacy_policy": {"raw_private_export_allowed": False},
        "timestamp": utc_now(),
    }
    data.update(overrides)
    return SelfhoodContext(**data)  # type: ignore[arg-type]


def voice_status_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    return "voice_status", from_voice_loop("ATANOR, current state"), base_context(user_goals=["ATANOR, current state"])


def knowledge_gap_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    context = base_context(
        world_model_summary={
            "concepts": 12,
            "relations": 20,
            "evidence": 8,
            "unresolved_questions": ["What is the safest promotion gate after the 24h run?"],
            "contradictions": [],
            "confidence_gaps": [],
        }
    )
    return "knowledge_gap_congress", SelfhoodInput("input_gap", "proof_fixture", "review open question", "en-US"), context


def private_data_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    input_event = SelfhoodInput(
        "input_private",
        "proof_fixture",
        "review private record",
        "en-US",
        {"private_like_record": {"name": "Ada Lovelace", "email": "ada@example.test", "age": 34, "generic_topic": "math"}},
    )
    return "private_data_blocked", input_event, base_context()


def atlas_route_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    input_event = SelfhoodInput("input_route", "proof_fixture", "route public cartridge", "en-US", {"needs_external_route": True})
    return "atlas_route", input_event, base_context(user_goals=["route public source"])


def promotion_review_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    input_event = SelfhoodInput("input_promotion", "proof_fixture", "candidate review", "en-US", {"candidate_knowledge_available": True})
    return "promotion_review", input_event, base_context()


def generated_code_blocked_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    input_event = SelfhoodInput("input_code", "proof_fixture", "apply generated patch", "en-US", {"generated_code_patch_requested": True})
    return "generated_code_blocked", input_event, base_context()


def morning_brief_scenario() -> tuple[str, SelfhoodInput, SelfhoodContext]:
    return "morning_brief", SelfhoodInput("input_morning", "morning_wake", "morning brief", "en-US"), base_context()


def all_scenarios() -> list[tuple[str, SelfhoodInput, SelfhoodContext]]:
    return [
        voice_status_scenario(),
        knowledge_gap_scenario(),
        private_data_scenario(),
        atlas_route_scenario(),
        promotion_review_scenario(),
        generated_code_blocked_scenario(),
        morning_brief_scenario(),
    ]
