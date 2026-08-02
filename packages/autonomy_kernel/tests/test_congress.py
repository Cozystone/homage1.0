from __future__ import annotations

from packages.autonomy_kernel.congress import SandboxCongress
from packages.autonomy_kernel.models import DeficitSignal


def test_sandbox_congress_uses_no_network_and_requires_approval() -> None:
    congress = SandboxCongress()
    proposals = congress.deliberate([DeficitSignal("d", "knowledge_gap", 0.6, 0.6, "test", [{"q": "x"}])])
    assert congress.network_used is False
    assert proposals
    assert all(proposal.required_approval for proposal in proposals)
    assert all(not proposal.mutates_production and not proposal.mutates_local_brain for proposal in proposals)

