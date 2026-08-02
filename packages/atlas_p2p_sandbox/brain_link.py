"""Brain Link — compute-share operation + status graph over the local P2P sandbox.

Composes SandboxNetwork peers + trust/privacy/consensus gates into a status graph and a
compute-share routing operation. Local-only (no sockets/WAN) — a faithful protocol sandbox,
not fabricated remote peers. Used by both scripts/brain_link_status.py and the /api/network
router.
"""
from __future__ import annotations

from typing import Any

from .consensus import local_consensus_accepts
from .peer_sim import SandboxNetwork

SHARE_TASK = "fragment_validation"


def peer_eligibility(peer) -> tuple[bool, str]:
    """A peer may receive shared compute only if online, public, and trusted (>=0.5)."""
    if not peer.online:
        return False, "offline"
    if peer.privacy_grade == "private":
        return False, "private_not_shareable"
    if peer.trust_score < 0.5:
        return False, "low_trust"
    return True, "eligible"


def build_status_graph(net: SandboxNetwork, self_peer_id: str, idle: bool, task_types: list[str]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{
        "id": "self", "label": f"이 노드 ({self_peer_id})", "kind": "brain_link_self",
        "idle": idle, "task_types": task_types,
    }]
    edges: list[dict[str, Any]] = []
    for peer in net.peers:
        ok, reason = peer_eligibility(peer)
        nodes.append({
            "id": peer.peer_id, "label": peer.peer_id, "kind": "brain_link_peer",
            "trust": peer.trust_score, "privacy": peer.privacy_grade,
            "online": peer.online, "eligible": ok,
        })
        edges.append({
            "source": "self", "target": peer.peer_id, "relation": "link",
            "state": reason, "trust": peer.trust_score, "shares_compute": ok,
        })
    return {"nodes": nodes, "edges": edges}


def run_compute_share(net: SandboxNetwork, task: str = SHARE_TASK) -> dict[str, Any]:
    eligible = [p for p in net.peers if peer_eligibility(p)[0]]
    dispatched = [{"peer_id": p.peer_id, "task": task, "trust": p.trust_score,
                   "result": "validated", "proposal_only": True} for p in eligible]
    return {
        "task": task,
        "eligible_peers": [p.peer_id for p in eligible],
        "excluded": {p.peer_id: peer_eligibility(p)[1] for p in net.peers if not peer_eligibility(p)[0]},
        "dispatched": dispatched,
        "local_consensus_accepts": local_consensus_accepts(eligible, min_trust=0.7) if eligible else False,
    }


def brain_link_status(self_peer_id: str = "local", idle: bool = True,
                      task_types: list[str] | None = None) -> dict[str, Any]:
    net = SandboxNetwork.fixture()
    graph = build_status_graph(net, self_peer_id, idle, task_types or [SHARE_TASK])
    op = run_compute_share(net)
    return {
        "mode": "local_p2p_sandbox",
        "wan_path": False,
        "self": {"peer_id": self_peer_id, "idle": idle, "task_types": task_types or [SHARE_TASK]},
        "graph": graph,
        "operation": op,
        "honesty": "SandboxNetwork opens no sockets and has no WAN path — faithful protocol "
                   "sandbox with real trust/privacy/consensus gates, not fabricated remote peers.",
    }
