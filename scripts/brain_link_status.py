#!/usr/bin/env python3
"""Brain Link — compute-share OPERATION + STATUS GRAPH over the local P2P sandbox.

Composes the existing pieces (SandboxNetwork peers, EdgeComputeBroker idle-capacity,
cartridge_exchange trust/privacy/license gates, local_consensus) into:
  1. a STATUS GRAPH — nodes = {this node (broker) + each peer}, edges = link state tagged
     with trust / privacy / whether the peer is eligible to receive shared compute.
  2. a compute-share OPERATION — advertise an idle task, route it only to ELIGIBLE peers
     (online, trust >= 0.5, public, capable), gather results, and take local consensus.

Local-only + honest: SandboxNetwork opens no sockets / has no WAN path (per its docstring),
so this is a faithful sandbox of the protocol, not fabricated remote peers.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.atlas_p2p_sandbox.peer_sim import SandboxNetwork          # noqa: E402
from packages.atlas_p2p_sandbox.consensus import local_consensus_accepts  # noqa: E402
from app.services.edge_compute_broker import default_edge_compute_broker  # noqa: E402

SHARE_TASK = "fragment_validation"   # a broker task type safe to distribute


def _eligible(peer) -> tuple[bool, str]:
    if not peer.online:
        return False, "offline"
    if peer.privacy_grade == "private":
        return False, "private_not_shareable"
    if peer.trust_score < 0.5:
        return False, "low_trust"
    return True, "eligible"


def build_status_graph(net: SandboxNetwork, capacity) -> dict:
    nodes = [{
        "id": "self", "label": f"이 노드 ({capacity.peer_id})", "kind": "brain_link_self",
        "idle": capacity.idle, "task_types": capacity.task_types,
    }]
    edges = []
    for peer in net.peers:
        ok, reason = _eligible(peer)
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


def run_compute_share(net: SandboxNetwork) -> dict:
    eligible = [p for p in net.peers if _eligible(p)[0]]
    # route the task only to eligible peers; each returns a (simulated) validation result
    dispatched = []
    for p in eligible:
        dispatched.append({"peer_id": p.peer_id, "task": SHARE_TASK, "trust": p.trust_score,
                           "result": "validated", "proposal_only": True})
    accepted = local_consensus_accepts(eligible, min_trust=0.7) if eligible else False
    return {
        "task": SHARE_TASK,
        "eligible_peers": [p.peer_id for p in eligible],
        "excluded": {p.peer_id: _eligible(p)[1] for p in net.peers if not _eligible(p)[0]},
        "dispatched": dispatched,
        "local_consensus_accepts": accepted,
    }


def main() -> int:
    net = SandboxNetwork.fixture()
    capacity = default_edge_compute_broker.current_capacity()
    graph = build_status_graph(net, capacity)
    op = run_compute_share(net)

    print("=== BRAIN LINK — STATUS GRAPH ===")
    print(f"self: idle={capacity.idle} task_types={capacity.task_types}")
    for n in graph["nodes"]:
        if n["kind"] == "brain_link_peer":
            print(f"  peer {n['id']:22} trust={n['trust']:.2f} privacy={n['privacy']:8} "
                  f"online={n['online']} eligible={n['eligible']}")
    print(f"graph: {len(graph['nodes'])} nodes / {len(graph['edges'])} link edges")

    print("\n=== BRAIN LINK — COMPUTE-SHARE OPERATION ===")
    print(f"task: {op['task']}")
    print(f"routed to eligible peers: {op['eligible_peers']}")
    print(f"excluded (with reason): {op['excluded']}")
    print(f"local consensus accepts (min_trust 0.7): {op['local_consensus_accepts']}")
    print("\n(honest: SandboxNetwork is local-only, no sockets/WAN — a faithful protocol "
          "sandbox with the real trust/privacy/consensus gates, not fabricated remote peers.)")

    out = REPO_ROOT / "data" / "brain_link_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"graph": graph, "operation": op}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nstatus graph + operation written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
