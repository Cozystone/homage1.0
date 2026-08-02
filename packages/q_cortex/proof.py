from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .creative_optimizer import sample_creative_paths
from .evidence_optimizer import resolve_evidence_conflicts
from .planning_optimizer import optimize_roadmap
from .salience_optimizer import optimize_salience_workspace
from .storage import DEFAULT_Q_CORTEX_ROOT, ensure_dirs, now_iso, write_json


def _salience_fixture() -> list[dict[str, Any]]:
    trusted = [
        ("seed.core.evidence", "seed_anchor", 0.96, 0.92, 0.92, 0.08),
        ("seed.core.claim", "seed_anchor", 0.92, 0.89, 0.9, 0.09),
        ("seed.core.source", "seed_anchor", 0.78, 0.72, 0.86, 0.08),
        ("seed.core.verification", "seed_anchor", 0.8, 0.74, 0.88, 0.08),
        ("cloud.evidence.bundle", "cloud_attached", 0.82, 0.78, 0.72, 0.18),
        ("cloud.claim.bundle", "cloud_attached", 0.77, 0.73, 0.7, 0.16),
        ("cloud.source.bundle", "cloud_attached", 0.7, 0.64, 0.68, 0.2),
        ("cloud.verification.bundle", "cloud_attached", 0.72, 0.67, 0.69, 0.2),
    ]
    rows = [
        {
            "id": node_id,
            "kind": "node",
            "layer": layer,
            "query_relevance": relevance,
            "activation": activation,
            "trust": trust,
            "novelty": 0.25,
            "user_goal_fit": relevance,
            "risk": risk,
            "fatigue": 0.08,
            "source_id": "seed" if layer == "seed_anchor" else "contributor-001",
            "concept_id": node_id,
            "temporary": layer == "cloud_attached",
        }
        for node_id, layer, relevance, activation, trust, risk in trusted
    ]
    rows.extend(
        {
            "id": f"noise-{index}",
            "kind": "node",
            "layer": "cloud_attached",
            "query_relevance": 0.08,
            "activation": 0.12,
            "trust": 0.18,
            "novelty": 0.6,
            "user_goal_fit": 0.05,
            "risk": 0.88,
            "fatigue": 0.4,
            "source_id": "noisy-source",
            "concept_id": f"noise.{index}",
            "temporary": True,
        }
        for index in range(6)
    )
    return rows


def _evidence_fixture() -> list[dict[str, Any]]:
    return [
        {"id": "ev-support-main", "claim_id": "claim-001", "source_id": "paper-a", "relation": "supports", "trust": 0.92, "recency": 0.8, "specificity": 0.86, "source_reputation": 0.9, "independence": 0.9, "conflicts_with": ["ev-contradict-weak"], "duplicates": [], "seed_aligned": True},
        {"id": "ev-support-independent", "claim_id": "claim-001", "source_id": "paper-b", "relation": "supports", "trust": 0.82, "recency": 0.72, "specificity": 0.74, "source_reputation": 0.86, "independence": 0.95, "conflicts_with": [], "duplicates": [], "seed_aligned": True},
        {"id": "ev-duplicate", "claim_id": "claim-001", "source_id": "paper-a", "relation": "supports", "trust": 0.74, "recency": 0.7, "specificity": 0.62, "source_reputation": 0.84, "independence": 0.2, "conflicts_with": [], "duplicates": ["ev-support-main"], "seed_aligned": True},
        {"id": "ev-contradict-weak", "claim_id": "claim-001", "source_id": "blog-x", "relation": "contradicts", "trust": 0.22, "recency": 0.55, "specificity": 0.25, "source_reputation": 0.18, "independence": 0.4, "conflicts_with": ["ev-support-main"], "duplicates": [], "seed_aligned": False},
        {"id": "ev-unknown", "claim_id": "claim-001", "source_id": "unknown", "relation": "unknown", "trust": 0.18, "recency": 0.3, "specificity": 0.2, "source_reputation": 0.1, "independence": 0.1, "conflicts_with": [], "duplicates": [], "seed_aligned": False},
    ]


def _creative_fixture() -> list[dict[str, Any]]:
    return [
        {"id": "mobile-hippocampus", "nodes": ["mobile", "working_memory"], "edges": ["compresses"], "domains": ["mobile", "memory"], "distance": 0.62, "novelty": 0.74, "usefulness": 0.86, "feasibility": 0.76, "atanor_fit": 0.88, "risk": 0.32, "cost": 0.38, "source_trace": ["cortex_g2"], "is_fact_claim": False},
        {"id": "smart-glasses-cortex", "nodes": ["sensory", "atlas"], "edges": ["streams"], "domains": ["wearable", "sensor"], "distance": 0.9, "novelty": 0.92, "usefulness": 0.64, "feasibility": 0.34, "atanor_fit": 0.7, "risk": 0.78, "cost": 0.86, "source_trace": ["roadmap"], "is_fact_claim": False},
        {"id": "contributor-network", "nodes": ["peer", "public_fragment"], "edges": ["validates"], "domains": ["network", "verification"], "distance": 0.48, "novelty": 0.68, "usefulness": 0.92, "feasibility": 0.72, "atanor_fit": 0.9, "risk": 0.38, "cost": 0.52, "source_trace": ["cloud_brain"], "is_fact_claim": False},
        {"id": "quantum-inspired-optimization", "nodes": ["qubo", "salience"], "edges": ["routes"], "domains": ["optimization", "cortex"], "distance": 0.7, "novelty": 0.88, "usefulness": 0.84, "feasibility": 0.82, "atanor_fit": 0.94, "risk": 0.25, "cost": 0.42, "source_trace": ["q_cortex"], "is_fact_claim": False},
        {"id": "privacy-gate", "nodes": ["vault", "policy"], "edges": ["filters"], "domains": ["privacy", "security"], "distance": 0.36, "novelty": 0.58, "usefulness": 0.9, "feasibility": 0.86, "atanor_fit": 0.93, "risk": 0.22, "cost": 0.25, "source_trace": ["payload_vault"], "is_fact_claim": False},
        {"id": "unsupported-magic-claim", "nodes": ["quantum", "mind"], "edges": ["proves"], "domains": ["speculative"], "distance": 0.98, "novelty": 0.99, "usefulness": 0.1, "feasibility": 0.02, "atanor_fit": 0.05, "risk": 0.96, "cost": 0.9, "source_trace": [], "is_fact_claim": True},
    ]


def _roadmap_fixture() -> list[dict[str, Any]]:
    return [
        {"id": "local-brain-ux-latency", "title": "Local Brain UX latency fix", "description": "Make overlay visible before graph payload.", "user_value": 0.95, "technical_proof_value": 0.82, "strategic_value": 0.76, "difficulty": 0.25, "risk": 0.18, "cost_points": 10, "dependencies": [], "conflicts_with": [], "unblocks": ["cortex-panel"], "time_to_demo": 0.12, "confidence": 0.92},
        {"id": "cortex-activation-panel", "title": "CORTEX-G2 activation panel", "description": "Show active/inhibited/prediction traces.", "user_value": 0.84, "technical_proof_value": 0.88, "strategic_value": 0.78, "difficulty": 0.38, "risk": 0.24, "cost_points": 18, "dependencies": ["local-brain-ux-latency"], "conflicts_with": [], "unblocks": ["q-cortex-salience"], "time_to_demo": 0.22, "confidence": 0.86},
        {"id": "q-cortex-salience", "title": "Q-Cortex salience optimizer", "description": "QUBO routing for workspace selection.", "user_value": 0.78, "technical_proof_value": 0.94, "strategic_value": 0.86, "difficulty": 0.44, "risk": 0.3, "cost_points": 24, "dependencies": ["cortex-activation-panel"], "conflicts_with": [], "unblocks": ["remote-broker-verification"], "time_to_demo": 0.34, "confidence": 0.82},
        {"id": "remote-broker-verification", "title": "Remote Broker verification", "description": "Prove Cloudflare submit/readback.", "user_value": 0.88, "technical_proof_value": 0.9, "strategic_value": 0.94, "difficulty": 0.52, "risk": 0.42, "cost_points": 28, "dependencies": [], "conflicts_with": [], "unblocks": ["multi-peer-proof"], "time_to_demo": 0.4, "confidence": 0.72},
        {"id": "multi-peer-proof", "title": "multi-peer contributor proof", "description": "Move beyond single local peer.", "user_value": 0.8, "technical_proof_value": 0.9, "strategic_value": 0.92, "difficulty": 0.72, "risk": 0.58, "cost_points": 42, "dependencies": ["remote-broker-verification"], "conflicts_with": ["mobile-brain-lite"], "unblocks": [], "time_to_demo": 0.68, "confidence": 0.62},
        {"id": "mobile-brain-lite", "title": "mobile brain lite prototype", "description": "Small local viewer/worker.", "user_value": 0.7, "technical_proof_value": 0.65, "strategic_value": 0.78, "difficulty": 0.64, "risk": 0.5, "cost_points": 38, "dependencies": ["remote-broker-verification"], "conflicts_with": ["multi-peer-proof"], "unblocks": [], "time_to_demo": 0.62, "confidence": 0.66},
        {"id": "smart-glasses-future", "title": "smart glasses future concept", "description": "Future sensory cortex concept.", "user_value": 0.54, "technical_proof_value": 0.38, "strategic_value": 0.68, "difficulty": 0.86, "risk": 0.82, "cost_points": 55, "dependencies": ["mobile-brain-lite"], "conflicts_with": [], "unblocks": [], "time_to_demo": 0.92, "confidence": 0.34},
    ]


def write_q_cortex_optimizer_proof(root: str | Path = DEFAULT_Q_CORTEX_ROOT) -> dict[str, Any]:
    base = ensure_dirs(root)
    salience = optimize_salience_workspace(_salience_fixture(), max_nodes=8, max_edges=4, seed=101)
    evidence = resolve_evidence_conflicts("claim-001", _evidence_fixture(), max_evidence=3, seed=102)
    creative = sample_creative_paths("ATANOR future architecture", _creative_fixture(), mode="far_walk", max_paths=4, seed=103)
    planning = optimize_roadmap(_roadmap_fixture(), max_steps=4, budget_points=80, seed=104)
    pass_state = (
        salience["selected_count"] <= 12
        and all("noise" not in str(item.get("id")) for item in salience["selected_items"])
        and evidence["trace"].get("verification_route") in {"evidence_backed", "contradiction_pending"}
        and all(not item.get("stored_as_truth") for item in creative["selected_items"])
        and int(planning["trace"].get("budget_used", 9999)) <= 80
        and all(not result["honesty"]["real_quantum_hardware_used"] for result in (salience, evidence, creative, planning))
    )
    proof = {
        "result": "PASS" if pass_state else "FAIL",
        "proved_at": now_iso(),
        "scenarios": {
            "salience": salience,
            "evidence": evidence,
            "creative": creative,
            "planning": planning,
        },
        "claims": [
            "ATANOR can use quantum-inspired optimization to select better candidate graph circuits.",
            "Q-Cortex can optimize salience, evidence consistency, creative path sampling, and planning.",
            "Q-Cortex is classical and local by default.",
            "Q-Cortex does not write to Local Brain.",
            "Q-Cortex can fall back to non-quantum heuristic solvers.",
        ],
        "does_not_claim": [
            "real quantum hardware usage",
            "quantum speedup",
            "consciousness",
            "human-level reasoning",
            "LLM replacement",
            "final answer superiority",
            "global Cloud Brain",
            "autonomous self-learning",
        ],
    }
    json_path = base / "proofs" / "q_cortex_optimizer_proof.json"
    md_path = base / "proofs" / "q_cortex_optimizer_proof.md"
    write_json(json_path, proof)
    md_path.write_text(_markdown(proof), encoding="utf-8")
    return {"proof": proof, "json_path": str(json_path), "markdown_path": str(md_path)}


def _markdown(proof: dict[str, Any]) -> str:
    scenario = proof["scenarios"]
    return "\n".join(
        [
            "# Q-Cortex Optimizer Proof",
            "",
            f"- Result: {proof['result']}",
            f"- Salience selected: {scenario['salience']['selected_count']}",
            f"- Evidence route: {scenario['evidence']['trace'].get('verification_route')}",
            f"- Creative selected: {scenario['creative']['selected_count']}",
            f"- Roadmap next step: {(scenario['planning']['trace'].get('next_single_recommended_step') or {}).get('id')}",
            "",
            "## This proof claims",
            *[f"- {claim}" for claim in proof["claims"]],
            "",
            "## This proof does NOT claim",
            *[f"- {claim}" for claim in proof["does_not_claim"]],
            "",
        ]
    )


def main() -> None:
    print(json.dumps(write_q_cortex_optimizer_proof(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
