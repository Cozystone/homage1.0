from __future__ import annotations

from .models import DeliberationInput, DeliberationResult, RoleStatement


PRIVATE_FLAGS = {"private_data_present", "raw_private_data", "contains_secret"}


def _privacy_blocks(report: dict[str, object]) -> bool:
    return any(bool(report.get(flag)) for flag in PRIVATE_FLAGS)


def run_deliberation(deliberation: DeliberationInput) -> DeliberationResult:
    """Run a deterministic local deliberation with review-only outputs."""

    evidence_count = len(deliberation.evidence_refs)
    contradiction_count = len(deliberation.contradictions)
    privacy_blocked = _privacy_blocks(deliberation.privacy_report)
    route_allowed = bool(deliberation.router_report.get("route_allowed", True))
    statements = [
        RoleStatement(
            "skeptic",
            "challenge",
            deliberation.contradictions or ["no explicit contradiction supplied"],
            blocks_promotion=contradiction_count > 0,
        ),
        RoleStatement(
            "builder",
            "construct",
            [f"{evidence_count} evidence refs can support a review packet"],
            blocks_promotion=evidence_count == 0,
        ),
        RoleStatement(
            "domain_expert",
            "scope",
            ["topic is treated as a candidate-review problem, not production truth"],
        ),
        RoleStatement(
            "privacy_guard",
            "guard",
            ["private raw data detected"] if privacy_blocked else ["no private raw data flag present"],
            blocks_promotion=privacy_blocked,
        ),
        RoleStatement(
            "router",
            "route",
            ["router allows local review"] if route_allowed else ["router blocks this route"],
            blocks_promotion=not route_allowed,
        ),
    ]
    blockers = [finding for statement in statements if statement.blocks_promotion for finding in statement.findings]
    if blockers:
        recommendation = "blocked"
        synthesis = "Deliberation found blockers; keep the candidate in review quarantine."
    elif evidence_count < 2:
        recommendation = "needs_more_evidence"
        synthesis = "Deliberation found no blocker, but evidence is too thin for promotion review."
    else:
        recommendation = "approve_for_review"
        synthesis = "Deliberation can prepare a manual promotion review packet."
    statements.extend(
        [
            RoleStatement("synthesis_chair", "synthesize", [synthesis], blocks_promotion=False),
            RoleStatement(
                "promotion_judge",
                "dry_run_only",
                ["manual approval required before any real promotion"],
                blocks_promotion=recommendation != "approve_for_review",
            ),
        ]
    )
    return DeliberationResult(
        topic=deliberation.topic,
        transcript=statements,
        objections=blockers,
        synthesis=synthesis,
        promotion_recommendation=recommendation,
        requires_manual_approval=True,
        morning_brief_candidate=f"{deliberation.topic}: {synthesis}",
    )
