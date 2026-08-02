"""The public browser route cannot become an erasure or subject-oracle bypass."""

from __future__ import annotations

from apps.api.app.routers.browser import browser_forget


def test_public_forget_route_refuses_before_scanning() -> None:
    result = browser_forget({"subject": "private subject"})

    assert result == {
        "ok": False,
        "accepted": False,
        "scanned": False,
        "applied": False,
        "reason": "authenticated_signed_graph_erasure_workflow_not_wired",
        "required_authority": "operator_signed_graph_mutation_batch",
    }


def test_public_forget_route_requires_a_subject_without_echoing_it() -> None:
    result = browser_forget({"subject": "  "})

    assert result == {"ok": False, "reason": "subject required"}
