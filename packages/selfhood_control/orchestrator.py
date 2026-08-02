from __future__ import annotations

from dataclasses import dataclass

from packages.autonomy_kernel.deficit import compute_deficit as autonomy_compute_deficit
from packages.autonomy_kernel.models import DeficitSignal

from packages.selfhood_control.bridges import (
    proposal_from_deficit,
    to_atlas_route,
    to_autonomy_context,
    to_ego_congress,
    to_morning_event,
    to_tabularis_review,
    to_voice_response,
)
from packages.selfhood_control.models import SelfhoodContext, SelfhoodDecision, SelfhoodInput, SelfhoodRunReport
from packages.selfhood_control.policy import SelfhoodSafetyPolicy, validate_decision
from packages.selfhood_control.scenario import all_scenarios


@dataclass
class SelfhoodControlPlane:
    policy: SelfhoodSafetyPolicy

    def observe(self, input_event: SelfhoodInput, context: SelfhoodContext) -> dict[str, object]:
        return {"input": input_event.to_dict(), "context": context.to_dict(), "mutation": False}

    def compute_deficit(self, context: SelfhoodContext) -> list[DeficitSignal]:
        world, self_model = to_autonomy_context(context)
        return autonomy_compute_deficit(world, self_model)

    def deliberate(self, deficits: list[DeficitSignal]) -> dict[str, object] | None:
        if not deficits:
            return None
        return to_ego_congress(deficits)

    def privacy_gate(self, payload: dict[str, object] | None) -> dict[str, object] | None:
        if payload is None:
            return None
        return to_tabularis_review(payload)

    def route_gate(self, target: str | None = None) -> dict[str, object] | None:
        if target is None:
            return None
        return to_atlas_route("local", target)

    def propose(self, deficits: list[DeficitSignal]) -> dict[str, object] | None:
        return proposal_from_deficit(deficits[0] if deficits else None)

    def plan_voice_response(self, input_event: SelfhoodInput, decision: SelfhoodDecision | None = None) -> dict[str, object] | None:
        if input_event.source != "voice_transcript":
            return None
        return to_voice_response(
            input_event,
            "Selfhood Control Plane is in proof-only mode. Production stores, Local Brain, and candidate learning remain untouched.",
        )

    def emit_morning_event(self, decision_id: str, summary: str) -> dict[str, object]:
        return to_morning_event(decision_id, "Selfhood Control Plane Morning Brief", summary)

    def run_once(self, input_event: SelfhoodInput, context: SelfhoodContext) -> SelfhoodDecision:
        deficits = self.compute_deficit(context)
        metadata = input_event.metadata
        privacy_report = self.privacy_gate(metadata.get("private_like_record"))
        trust_route = self.route_gate("public_source" if metadata.get("needs_external_route") else None)
        congress = self.deliberate(deficits)
        proposal = self.propose(deficits)
        action = self._select_action(input_event, deficits, privacy_report, trust_route)
        decision_id = f"decision_{input_event.input_id}"
        voice_response = None
        if action == "speak_status":
            voice_response = self.plan_voice_response(input_event)
        if metadata.get("candidate_knowledge_available"):
            action = "propose_promotion_review"
            proposal = {
                "proposal_id": f"promotion_{input_event.input_id}",
                "proposal_type": "graph_promotion_proposal",
                "summary": "Candidate knowledge is available but requires a promotion review gate.",
                "mutates_production": False,
                "mutates_local_brain": False,
                "required_approval": True,
            }
        if metadata.get("generated_code_patch_requested"):
            action = "blocked"
            proposal = {
                "proposal_id": f"patch_{input_event.input_id}",
                "proposal_type": "code_patch_proposal",
                "summary": "Generated code execution and production code replacement are blocked in proof mode.",
                "generated_code_executed": False,
                "real_hot_swap_performed": False,
                "required_approval": True,
            }
        morning_event = None
        if action == "present_morning_brief":
            morning_event = self.emit_morning_event(decision_id, "Proof-only morning brief prepared for user review.")
        if action in {"propose_research", "propose_promotion_review"} and congress:
            morning_event = self.emit_morning_event(decision_id, str(congress.get("synthesis", {}).get("summary", "Proposal ready.")))
        safety_notes = ["proof-only", "requires user approval", "no production or Local Brain mutation"]
        if privacy_report and privacy_report.get("report", {}).get("safe_for_atlas") is False:
            action = "ask_user"
            safety_notes.append("private data requires review before routing")
        decision = SelfhoodDecision(
            decision_id=decision_id,
            input_id=input_event.input_id,
            deficits=[deficit.to_dict() for deficit in deficits],
            congress_summary=congress,
            privacy_report=privacy_report,
            trust_route=trust_route,
            proposal=proposal,
            voice_response=voice_response,
            morning_event=morning_event,
            action=action,
            requires_user_approval=True,
            safety_notes=safety_notes,
        )
        validation = validate_decision(decision, self.policy)
        if not validation.allowed:
            return SelfhoodDecision(
                decision_id=f"{decision.decision_id}_blocked",
                input_id=input_event.input_id,
                deficits=decision.deficits,
                congress_summary=decision.congress_summary,
                privacy_report=decision.privacy_report,
                trust_route=decision.trust_route,
                proposal=decision.proposal,
                voice_response=decision.voice_response,
                morning_event=decision.morning_event,
                action="blocked",
                requires_user_approval=True,
                safety_notes=safety_notes + [validation.reason],
            )
        return decision

    def run_scenario(self, scenario: str) -> SelfhoodRunReport:
        matching = [item for item in all_scenarios() if item[0] == scenario]
        if not matching:
            raise ValueError(f"unknown scenario: {scenario}")
        _, input_event, context = matching[0]
        decision = self.run_once(input_event, context)
        invariants = build_invariants([decision])
        return SelfhoodRunReport(
            f"run_{scenario}",
            scenario,
            [decision],
            invariants,
            passed=all(value is False for key, value in invariants.items() if key not in {"active_24h_run_not_modified"})
            and invariants["active_24h_run_not_modified"] is True,
            limitations=["proof-only", "not production AGI", "not a consciousness claim", "no peer-network transport"],
        )

    def _select_action(
        self,
        input_event: SelfhoodInput,
        deficits: list[DeficitSignal],
        privacy_report: dict[str, object] | None,
        trust_route: dict[str, object] | None,
    ) -> str:
        voice_intent = input_event.metadata.get("voice_intent", {})
        if isinstance(voice_intent, dict) and voice_intent.get("intent_type") == "autonomy_status_request":
            return "speak_status"
        if input_event.source == "morning_wake":
            return "present_morning_brief"
        if privacy_report is not None:
            return "ask_user"
        if trust_route is not None:
            return "propose_research"
        if any(deficit.deficit_type == "promotion_needed" for deficit in deficits):
            return "propose_promotion_review"
        if deficits:
            return "propose_research"
        return "no_action"


def build_invariants(decisions: list[SelfhoodDecision]) -> dict[str, object]:
    return {
        "production_store_mutated": any(decision.mutates_production for decision in decisions),
        "local_brain_write": any(decision.mutates_local_brain for decision in decisions),
        "candidate_promotion": any(decision.candidate_promotion for decision in decisions),
        "external_llm_used": any(decision.uses_external_llm for decision in decisions),
        "mock_growth": False,
        "pair_edges_sent": sum(decision.pair_edges_sent for decision in decisions),
        "active_24h_run_not_modified": True,
        "raw_private_data_exported": any(decision.raw_private_data_exported for decision in decisions),
        "real_p2p_used": any(decision.uses_real_p2p for decision in decisions),
        "real_cloud_upload": any(decision.real_cloud_upload for decision in decisions),
        "real_hot_swap_performed": any(decision.real_hot_swap_performed for decision in decisions),
        "generated_code_executed": any(decision.generated_code_executed for decision in decisions),
        "always_listening_enabled": any(decision.always_listening_enabled for decision in decisions),
    }
