from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .dijkstra import find_lowest_trust_cost_path
from .models import TrustRouteEdge, TrustRouteNode, TrustRoutePolicy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "atlas_router"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _edge(
    edge_id: str,
    source_id: str,
    target_id: str,
    *,
    latency_ms: float = 10.0,
    bandwidth_cost: float = 0.1,
    trust_penalty: float = 0.05,
    license_risk: float = 0.0,
    privacy_risk: float = 0.0,
    stale_data_risk: float = 0.05,
    compute_cost: float = 0.1,
    failure_risk: float = 0.02,
) -> TrustRouteEdge:
    return TrustRouteEdge(
        edge_id=edge_id,
        source_id=source_id,
        target_id=target_id,
        latency_ms=latency_ms,
        bandwidth_cost=bandwidth_cost,
        trust_penalty=trust_penalty,
        license_risk=license_risk,
        privacy_risk=privacy_risk,
        stale_data_risk=stale_data_risk,
        compute_cost=compute_cost,
        failure_risk=failure_risk,
    )


def _nodes() -> list[TrustRouteNode]:
    return [
        TrustRouteNode("local", "local_brain", "Local Brain", 1.0, "private"),
        TrustRouteNode("wm", "working_memory", "Working Memory", 1.0, "restricted"),
        TrustRouteNode("cloud", "cloud_brain", "Cloud Brain", 0.9, "public"),
        TrustRouteNode("peer", "atlas_peer", "Atlas Peer", 0.6, "public"),
        TrustRouteNode("hub", "graph_hub", "Graph Hub", 0.85, "public"),
        TrustRouteNode("cart", "cartridge", "Graph Cartridge", 0.8, "public"),
        TrustRouteNode("source", "public_source", "Public Source", 0.95, "public"),
    ]


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    policy = TrustRoutePolicy(require_public_only=False, max_privacy_risk=0.2, max_license_risk=0.2)

    local_first = find_lowest_trust_cost_path(
        _nodes(),
        [
            _edge("local-wm", "local", "wm", latency_ms=5, trust_penalty=0.01),
            _edge("wm-cloud", "wm", "cloud", latency_ms=20, trust_penalty=0.02),
            _edge("local-peer", "local", "peer", latency_ms=3, trust_penalty=0.4),
            _edge("peer-cloud", "peer", "cloud", latency_ms=3, trust_penalty=0.4),
        ],
        "local",
        "cloud",
        policy,
    )

    privacy_block = find_lowest_trust_cost_path(
        _nodes(),
        [
            _edge("local-peer-private", "local", "peer", privacy_risk=0.9),
            _edge("local-wm-safe", "local", "wm", privacy_risk=0.0),
            _edge("wm-cloud-safe", "wm", "cloud", privacy_risk=0.0),
        ],
        "local",
        "cloud",
        TrustRoutePolicy(require_public_only=False, max_privacy_risk=0.1, max_license_risk=0.2),
    )

    license_block = find_lowest_trust_cost_path(
        _nodes(),
        [
            _edge("local-cart-risk", "local", "cart", license_risk=0.9),
            _edge("local-hub-safe", "local", "hub", license_risk=0.0),
            _edge("hub-cloud-safe", "hub", "cloud", license_risk=0.0),
        ],
        "local",
        "cloud",
        TrustRoutePolicy(require_public_only=False, max_privacy_risk=0.2, max_license_risk=0.1),
    )

    no_route = find_lowest_trust_cost_path(
        _nodes(),
        [
            _edge("local-peer-blocked", "local", "peer", privacy_risk=0.9),
            _edge("peer-cloud-blocked", "peer", "cloud", license_risk=0.9),
        ],
        "local",
        "cloud",
        TrustRoutePolicy(require_public_only=False, max_privacy_risk=0.1, max_license_risk=0.1),
    )

    trust_vs_latency = find_lowest_trust_cost_path(
        _nodes(),
        [
            _edge("fast-untrusted", "local", "peer", latency_ms=1, trust_penalty=0.95),
            _edge("peer-cloud", "peer", "cloud", latency_ms=1, trust_penalty=0.8),
            _edge("slow-trusted", "local", "wm", latency_ms=200, trust_penalty=0.01),
            _edge("wm-cloud-trusted", "wm", "cloud", latency_ms=200, trust_penalty=0.01),
        ],
        "local",
        "cloud",
        policy,
    )

    results = {
        "local_first": local_first.to_dict(),
        "privacy_block": privacy_block.to_dict(),
        "license_block": license_block.to_dict(),
        "no_route": no_route.to_dict(),
        "trust_vs_latency": trust_vs_latency.to_dict(),
        "summary": {
            "local_first_pass": local_first.path == ["local", "wm", "cloud"] and local_first.safe_to_attach_to_working_memory and not local_first.safe_to_write_local_brain,
            "privacy_block_pass": any("privacy_risk" in str(edge.get("reason")) for edge in privacy_block.blocked_edges),
            "license_block_pass": any("license_risk" in str(edge.get("reason")) for edge in license_block.blocked_edges),
            "no_route_pass": no_route.path == [] and not no_route.safe_to_attach_to_working_memory and not no_route.safe_to_write_local_brain,
            "trust_vs_latency_pass": trust_vs_latency.path == ["local", "wm", "cloud"],
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _ts()
    json_path = output_dir / f"atlas_router_proof_{timestamp}.json"
    md_path = output_dir / f"atlas_router_proof_{timestamp}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_proof_markdown(results), encoding="utf-8")
    results["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return results


def _proof_markdown(results: dict[str, Any]) -> str:
    summary = results["summary"]
    lines = ["# Atlas Router Proof", ""]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("Generated proof output is audit data and should not be committed.")
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

