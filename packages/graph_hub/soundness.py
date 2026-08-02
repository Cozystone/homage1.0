from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any

from .cartridge_profile import GraphSoundnessIssue, PhaseRoutingProbe


PROMPT_MARKERS = ("ignore previous", "system prompt", "developer message", "jailbreak", "api key", "password")


def graph_soundness_checks(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], *, max_fanout: int = 24) -> dict[str, Any]:
    issues: list[GraphSoundnessIssue] = []
    node_ids = {str(node.get("id")) for node in nodes if node.get("id") is not None}
    out_degree: Counter[str] = Counter()
    self_loops = 0
    broken_refs = 0
    suspicious_text = 0

    for node in nodes:
        text = f"{node.get('label', '')} {node.get('description', '')}".lower()
        if any(marker in text for marker in PROMPT_MARKERS):
            suspicious_text += 1

    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source == target and source:
            self_loops += 1
        if source not in node_ids or target not in node_ids:
            broken_refs += 1
        out_degree[source] += 1
        adjacency[source].append(target)

    excessive = [(node_id, count) for node_id, count in out_degree.items() if count > max_fanout]
    if broken_refs:
        issues.append(GraphSoundnessIssue("broken_chunk_references", "blocker", f"{broken_refs} edges reference missing nodes"))
    if self_loops:
        issues.append(GraphSoundnessIssue("self_reinforcing_cycles", "review", f"{self_loops} self-loop edges found"))
    if excessive:
        issues.append(GraphSoundnessIssue("excessive_fanout", "review", f"{len(excessive)} nodes exceed fanout {max_fanout}"))
    if suspicious_text:
        issues.append(GraphSoundnessIssue("prompt_like_payload", "blocker", f"{suspicious_text} nodes contain prompt-like payload markers"))

    edge_density = len(edges) / max(len(nodes), 1)
    if edge_density > max_fanout:
        issues.append(GraphSoundnessIssue("suspicious_edge_density", "review", f"edge/node density {edge_density:.2f} is high"))

    probes = simulate_phase_routing(nodes, edges, max_depth=4, max_nodes_visited=128, max_fanout=max_fanout)
    blocker_count = sum(1 for issue in issues if issue.severity == "blocker")
    review_count = sum(1 for issue in issues if issue.severity == "review")
    soundness_score = max(0.0, 1.0 - blocker_count * 0.45 - review_count * 0.12 - min(edge_density, max_fanout) / (max_fanout * 8))
    topology_health = max(0.0, 1.0 - broken_refs * 0.08 - self_loops * 0.05 - len(excessive) * 0.08)
    malicious_risk = min(1.0, suspicious_text * 0.5 + blocker_count * 0.25)
    return {
        "issues": [issue.__dict__ for issue in issues],
        "soundness_score": round(soundness_score, 4),
        "topology_health_score": round(topology_health, 4),
        "malicious_pattern_risk": round(malicious_risk, 4),
        "simulated_queries": [probe.__dict__ for probe in probes],
        "pair_edges_sent": 0,
        "edge_density": round(edge_density, 4),
    }


def simulate_phase_routing(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_depth: int,
    max_nodes_visited: int,
    max_fanout: int,
) -> list[PhaseRoutingProbe]:
    if not nodes:
        return []
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source and target:
            adjacency[source].append(target)
    seeds = [str(node.get("id")) for node in nodes[: min(3, len(nodes))]]
    probes: list[PhaseRoutingProbe] = []
    for seed in seeds:
        visited = {seed}
        queue: deque[tuple[str, int, float]] = deque([(seed, 0, 1.0)])
        terminated = True
        while queue and len(visited) < max_nodes_visited:
            current, depth, amplitude = queue.popleft()
            if depth >= max_depth or amplitude < 0.08:
                continue
            fanout = adjacency.get(current, [])[:max_fanout]
            for target in fanout:
                if target in visited:
                    continue
                visited.add(target)
                queue.append((target, depth + 1, amplitude * 0.62))
        if queue and len(visited) >= max_nodes_visited:
            terminated = False
        probes.append(
            PhaseRoutingProbe(
                query=seed,
                visited_nodes=len(visited),
                max_depth=max_depth,
                terminated_by_attenuation=terminated,
                pair_edges_sent=0,
            )
        )
    return probes
