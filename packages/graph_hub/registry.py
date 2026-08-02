from __future__ import annotations

from pathlib import Path
from typing import Any

from .cartridge_format import make_graph_cartridge, write_cartridge
from .models import CATALOG_PATH, GRAPH_HUB_ROOT, cartridge_path, ensure_graph_hub_dirs, read_json, write_json


def _semantic_node(node_id: str, label: str) -> dict[str, Any]:
    return {"id": node_id, "label": label, "source_scope": "cartridge", "trust": 0.72}


def _semantic_edge(edge_id: str, source: str, target: str, relation: str) -> dict[str, Any]:
    return {"id": edge_id, "source": source, "target": target, "relation": relation, "weight": 0.72}


def _weighted_node(node_id: str, label: str, trust: float = 0.78, **metadata: Any) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "source_scope": "cartridge",
        "trust": trust,
        **metadata,
    }


def _weighted_edge(edge_id: str, source: str, target: str, relation: str, weight: float = 0.74) -> dict[str, Any]:
    return {"id": edge_id, "source": source, "target": target, "relation": relation, "weight": weight}


def _surface_defaults(domain: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "constructions": [
            {"id": f"{domain}:direct_grounded_answer", "language": "ko", "pattern_family": "grounded_direct_answer"},
            {"id": f"{domain}:compact_evidence_caveat", "language": "en", "pattern_family": "evidence_then_caveat"},
        ],
        "discourse_moves": [
            {"id": f"{domain}:answer_then_evidence", "function": "direct_answer"},
            {"id": f"{domain}:uncertainty_boundary", "function": "caveat"},
        ],
        "lemma_choices": [],
        "style_profiles": [
            {"id": f"{domain}:clear_operator", "tone": "clear", "density": "medium"},
        ],
    }


def sample_cartridges() -> list[dict[str, Any]]:
    return [
        make_graph_cartridge(
            cartridge_id="atanor_base_free",
            name="ATANOR Base Free",
            subtitle="Basic ontology anchors for everyday reasoning.",
            description="A small free graph pack with foundational concepts, surface constructions, and reasoning patterns.",
            category="general",
            pricing={"model": "free", "price": None, "currency": "none", "billing_period": "none"},
            tags=["base", "free", "starter"],
            contents={
                "semantic_graph": {
                    "nodes": [_semantic_node("base:evidence", "Evidence"), _semantic_node("base:claim", "Claim")],
                    "edges": [_semantic_edge("base:evidence-supports-claim", "base:evidence", "base:claim", "supports")],
                },
                "surface_graph": {
                    "constructions": [{"id": "direct_concise", "language": "ko", "pattern_family": "concise_answer"}],
                    "discourse_moves": [{"id": "answer_then_reason", "function": "direct_answer"}],
                    "lemma_choices": [],
                    "style_profiles": [{"id": "clear_default", "tone": "clear"}],
                },
                "reasoning_patterns": [{"id": "evidence_before_claim", "name": "Evidence before claim"}],
            },
            provenance={"source_type": "manual_sample", "source_paths": []},
        ),
        make_graph_cartridge(
            cartridge_id="startup_strategy_demo",
            name="Startup Strategy Demo",
            subtitle="Market, customer, moat, pricing, and investor objection frames.",
            description="A compact startup reasoning cartridge for strategy conversations and pitch critique.",
            category="startup",
            pricing={"model": "one_time", "price": 19, "currency": "USD", "billing_period": "none"},
            tags=["startup", "strategy", "pitch"],
            contents={
                "semantic_graph": {
                    "nodes": [_semantic_node("startup:market", "Market"), _semantic_node("startup:moat", "Moat"), _semantic_node("startup:pricing", "Pricing")],
                    "edges": [
                        _semantic_edge("startup:market-informs-pricing", "startup:market", "startup:pricing", "informs"),
                        _semantic_edge("startup:moat-protects-market", "startup:moat", "startup:market", "protects"),
                    ],
                },
                "surface_graph": {
                    "constructions": [{"id": "investor_framing", "language": "en", "pattern_family": "investor_summary"}],
                    "discourse_moves": [{"id": "objection_then_answer", "function": "objection"}],
                    "lemma_choices": [],
                    "style_profiles": [{"id": "boardroom_concise", "tone": "strategic"}],
                },
                "reasoning_patterns": [{"id": "problem_solution_moat", "name": "Problem-solution-moat"}],
            },
            provenance={"source_type": "manual_sample", "source_paths": []},
        ),
        make_graph_cartridge(
            cartridge_id="korean_writing_demo",
            name="Korean Writing Demo",
            subtitle="Natural Korean explanation and transition patterns.",
            description="A subscription demo cartridge for smoother Korean writing surface planning.",
            category="writing",
            pricing={"model": "subscription", "price": 5, "currency": "USD", "billing_period": "monthly", "trial_days": 7},
            tags=["korean", "writing", "surface"],
            contents={
                "semantic_graph": {
                    "nodes": [_semantic_node("writing:clarity", "명료성"), _semantic_node("writing:transition", "전환 표현")],
                    "edges": [_semantic_edge("writing:transition-improves-clarity", "writing:transition", "writing:clarity", "improves")],
                },
                "surface_graph": {
                    "constructions": [{"id": "ko_soft_contrast", "language": "ko", "pattern_family": "soft_contrast"}],
                    "discourse_moves": [{"id": "ko_summary_close", "function": "summary"}],
                    "lemma_choices": [{"concept": "summary", "choices": ["정리하면", "핵심만 말하면"]}],
                    "style_profiles": [{"id": "ko_clean_professional", "tone": "clean"}],
                },
                "repair_rules": [{"id": "avoid_repeated_marker", "review_required": True}],
            },
            provenance={"source_type": "manual_sample", "source_paths": []},
        ),
        make_graph_cartridge(
            cartridge_id="software_architect_demo",
            name="Software Architect Demo",
            subtitle="API, backend, frontend, deployment, testing, and tradeoff frames.",
            description="A practical software architecture cartridge for technical planning and review.",
            category="software",
            pricing={"model": "free", "price": None, "currency": "none", "billing_period": "none"},
            tags=["software", "architecture", "testing"],
            contents={
                "semantic_graph": {
                    "nodes": [_semantic_node("sw:api", "API"), _semantic_node("sw:test", "Testing"), _semantic_node("sw:deployment", "Deployment")],
                    "edges": [
                        _semantic_edge("sw:api-requires-test", "sw:api", "sw:test", "requires"),
                        _semantic_edge("sw:test-supports-deployment", "sw:test", "sw:deployment", "supports"),
                    ],
                },
                "surface_graph": {
                    "constructions": [{"id": "tradeoff_frame", "language": "en", "pattern_family": "architecture_tradeoff"}],
                    "discourse_moves": [{"id": "risk_then_mitigation", "function": "warning"}],
                    "lemma_choices": [],
                    "style_profiles": [{"id": "senior_engineer", "tone": "precise"}],
                },
                "reasoning_patterns": [{"id": "risk_tradeoff_mitigation", "name": "Risk-tradeoff-mitigation"}],
            },
            provenance={"source_type": "manual_sample", "source_paths": []},
        ),
        make_graph_cartridge(
            cartridge_id="graphrag_evidence_verification_demo",
            name="GraphRAG Evidence Verification",
            subtitle="Claim, evidence, citation, and verification flow for grounded answers.",
            description="A realistic sample graph fragment that models how retrieved evidence constrains answer candidates without exposing internal routes by default.",
            category="verification",
            pricing={"model": "free", "price": None, "currency": "none", "billing_period": "none"},
            tags=["graphrag", "evidence", "verification", "claim", "source"],
            contents={
                "semantic_graph": {
                    "nodes": [
                        _weighted_node("rag:query", "User Query", 0.8, role="input"),
                        _weighted_node("rag:seed_anchor", "Seed Anchor", 0.84, role="anchor"),
                        _weighted_node("rag:concept_node", "Concept Node", 0.78, role="semantic"),
                        _weighted_node("rag:evidence_chunk", "Evidence Chunk", 0.82, role="evidence"),
                        _weighted_node("rag:source_document", "Source Document", 0.8, role="source"),
                        _weighted_node("rag:claim", "Claim", 0.76, role="claim"),
                        _weighted_node("rag:answer_candidate", "Answer Candidate", 0.74, role="candidate"),
                        _weighted_node("rag:verifier", "Evidence Verifier", 0.86, role="checker"),
                        _weighted_node("rag:citation", "Citation", 0.8, role="support"),
                        _weighted_node("rag:unsupported_claim", "Unsupported Claim", 0.28, role="rejected"),
                    ],
                    "edges": [
                        _weighted_edge("rag:query-matches-anchor", "rag:query", "rag:seed_anchor", "matches", 0.8),
                        _weighted_edge("rag:anchor-activates-concept", "rag:seed_anchor", "rag:concept_node", "activates", 0.76),
                        _weighted_edge("rag:concept-retrieves-evidence", "rag:concept_node", "rag:evidence_chunk", "retrieves", 0.82),
                        _weighted_edge("rag:evidence-from-source", "rag:evidence_chunk", "rag:source_document", "from_source", 0.84),
                        _weighted_edge("rag:evidence-supports-claim", "rag:evidence_chunk", "rag:claim", "supports", 0.82),
                        _weighted_edge("rag:claim-forms-answer", "rag:claim", "rag:answer_candidate", "constrains", 0.74),
                        _weighted_edge("rag:verifier-checks-answer", "rag:verifier", "rag:answer_candidate", "checks", 0.86),
                        _weighted_edge("rag:citation-backs-answer", "rag:citation", "rag:answer_candidate", "backs", 0.78),
                        _weighted_edge("rag:source-provides-citation", "rag:source_document", "rag:citation", "provides", 0.78),
                        _weighted_edge("rag:verifier-rejects-unsupported", "rag:verifier", "rag:unsupported_claim", "inhibits", 0.88),
                        _weighted_edge("rag:unsupported-conflicts-answer", "rag:unsupported_claim", "rag:answer_candidate", "conflicts_with", 0.36),
                    ],
                },
                "surface_graph": _surface_defaults("rag"),
                "reasoning_patterns": [
                    {"id": "evidence_before_answer", "name": "Evidence before answer"},
                    {"id": "unsupported_claim_inhibition", "name": "Unsupported claim inhibition"},
                ],
            },
            provenance={"source_type": "curated_sample", "source_paths": [], "proof_store_only": True},
        ),
        make_graph_cartridge(
            cartridge_id="local_cloud_boundary_demo",
            name="Local Cloud Boundary",
            subtitle="Read-only Cloud context, Payload Vault boundary, and Working Memory overlay rules.",
            description="A sample safety graph showing how public cloud fragments can be attached temporarily while private Local Brain and Payload Vault data remain isolated.",
            category="safety",
            pricing={"model": "free", "price": None, "currency": "none", "billing_period": "none"},
            tags=["privacy", "working_memory", "local_brain", "cloud_attached", "payload_vault"],
            contents={
                "semantic_graph": {
                    "nodes": [
                        _weighted_node("boundary:local_brain", "Local Brain", 0.86, role="private_boundary"),
                        _weighted_node("boundary:payload_vault", "Payload Vault", 0.9, role="private_store"),
                        _weighted_node("boundary:ghost_shell", "Ghost Shell", 0.84, role="execution_boundary"),
                        _weighted_node("boundary:working_memory", "Working Memory Overlay", 0.82, role="temporary_overlay"),
                        _weighted_node("boundary:cloud_fragment", "Public Cloud Fragment", 0.74, role="public_context"),
                        _weighted_node("boundary:semantic_cloud", "Semantic Cloud Graph", 0.76, role="public_graph"),
                        _weighted_node("boundary:approval_gate", "Explicit Promotion Gate", 0.86, role="approval"),
                        _weighted_node("boundary:local_write", "Local Write", 0.64, role="protected_action"),
                        _weighted_node("boundary:trial_chunk", "Trial Cartridge Chunk", 0.72, role="temporary_chunk"),
                        _weighted_node("boundary:detach", "Detach Cleanup", 0.82, role="cleanup"),
                    ],
                    "edges": [
                        _weighted_edge("boundary:vault-owned-by-local", "boundary:payload_vault", "boundary:local_brain", "protected_by", 0.88),
                        _weighted_edge("boundary:ghost-shell-guards-vault", "boundary:ghost_shell", "boundary:payload_vault", "guards", 0.84),
                        _weighted_edge("boundary:cloud-attaches-wm", "boundary:cloud_fragment", "boundary:working_memory", "attaches_temporarily", 0.76),
                        _weighted_edge("boundary:semantic-cloud-provides-fragment", "boundary:semantic_cloud", "boundary:cloud_fragment", "provides", 0.76),
                        _weighted_edge("boundary:trial-attaches-wm", "boundary:trial_chunk", "boundary:working_memory", "attaches_temporarily", 0.74),
                        _weighted_edge("boundary:wm-not-local-write", "boundary:working_memory", "boundary:local_write", "does_not_perform", 0.82),
                        _weighted_edge("boundary:approval-enables-write", "boundary:approval_gate", "boundary:local_write", "requires_explicit_approval", 0.88),
                        _weighted_edge("boundary:detach-clears-wm", "boundary:detach", "boundary:working_memory", "clears", 0.84),
                        _weighted_edge("boundary:trial-detaches", "boundary:trial_chunk", "boundary:detach", "expires_to", 0.74),
                    ],
                },
                "surface_graph": _surface_defaults("boundary"),
                "reasoning_patterns": [
                    {"id": "temporary_context_no_private_write", "name": "Temporary context without private write"},
                    {"id": "explicit_promotion_gate", "name": "Explicit promotion gate"},
                ],
            },
            provenance={"source_type": "curated_sample", "source_paths": [], "proof_store_only": True},
        ),
        make_graph_cartridge(
            cartridge_id="cortex_surface_answer_demo",
            name="CORTEX Surface Answer Path",
            subtitle="Activation, salience, surface planning, repair, and hidden trace flow.",
            description="A sample graph fragment for natural answer planning: activation selects a bounded workspace, surface planning chooses phrasing, and repair moves internal details into trace.",
            category="answering",
            pricing={"model": "free", "price": None, "currency": "none", "billing_period": "none"},
            tags=["surface_brain", "cortex_g2", "answer_quality", "repair", "trace_hygiene"],
            contents={
                "semantic_graph": {
                    "nodes": [
                        _weighted_node("answer:intent", "User Intent", 0.82, role="intent"),
                        _weighted_node("answer:activation", "Graph Activation", 0.78, role="activation"),
                        _weighted_node("answer:salience", "Salience Gate", 0.82, role="selection"),
                        _weighted_node("answer:workspace", "Bounded Workspace", 0.84, role="workspace"),
                        _weighted_node("answer:semantic_support", "Semantic Support", 0.82, role="grounding"),
                        _weighted_node("answer:surface_plan", "Surface Plan", 0.78, role="realization"),
                        _weighted_node("answer:q_cortex", "Candidate Optimizer", 0.72, role="optimizer"),
                        _weighted_node("answer:repair_loop", "Surface Repair Loop", 0.86, role="repair"),
                        _weighted_node("answer:clean_answer", "Clean Answer", 0.84, role="output"),
                        _weighted_node("answer:trace_panel", "Collapsed Trace Panel", 0.78, role="trace"),
                    ],
                    "edges": [
                        _weighted_edge("answer:intent-activates", "answer:intent", "answer:activation", "triggers", 0.78),
                        _weighted_edge("answer:activation-feeds-salience", "answer:activation", "answer:salience", "feeds", 0.76),
                        _weighted_edge("answer:salience-selects-workspace", "answer:salience", "answer:workspace", "selects", 0.84),
                        _weighted_edge("answer:workspace-uses-semantic", "answer:workspace", "answer:semantic_support", "requires", 0.82),
                        _weighted_edge("answer:semantic-guides-surface", "answer:semantic_support", "answer:surface_plan", "guides", 0.78),
                        _weighted_edge("answer:optimizer-ranks-plan", "answer:q_cortex", "answer:surface_plan", "ranks_candidates", 0.72),
                        _weighted_edge("answer:surface-to-repair", "answer:surface_plan", "answer:repair_loop", "passes_through", 0.82),
                        _weighted_edge("answer:repair-produces-clean", "answer:repair_loop", "answer:clean_answer", "produces", 0.86),
                        _weighted_edge("answer:repair-moves-trace", "answer:repair_loop", "answer:trace_panel", "moves_internal_detail", 0.84),
                        _weighted_edge("answer:trace-not-default", "answer:trace_panel", "answer:clean_answer", "hidden_by_default", 0.76),
                    ],
                },
                "surface_graph": {
                    "constructions": [
                        {"id": "answer:ko_natural_direct", "language": "ko", "pattern_family": "native_direct_answer"},
                        {"id": "answer:en_concise_technical", "language": "en", "pattern_family": "concise_technical_answer"},
                        {"id": "answer:soft_uncertainty", "language": "ko", "pattern_family": "soft_uncertainty_boundary"},
                    ],
                    "discourse_moves": [
                        {"id": "answer:answer_first", "function": "direct_answer"},
                        {"id": "answer:evidence_brief", "function": "evidence_summary"},
                        {"id": "answer:trace_hidden", "function": "hide_internal_trace"},
                    ],
                    "lemma_choices": [],
                    "style_profiles": [{"id": "answer:service_default", "tone": "natural", "verbosity": "compact"}],
                },
                "reasoning_patterns": [
                    {"id": "bounded_workspace_answer", "name": "Bounded workspace answer"},
                    {"id": "repair_before_user_output", "name": "Repair before user output"},
                ],
            },
            provenance={"source_type": "curated_sample", "source_paths": [], "proof_store_only": True},
        ),
    ]


def ensure_sample_cartridges() -> list[dict[str, Any]]:
    ensure_graph_hub_dirs()
    cartridges: list[dict[str, Any]] = []
    for cartridge in sample_cartridges():
        path = cartridge_path(cartridge["cartridge_id"])
        if not path.exists():
            write_cartridge(path, cartridge)
        cartridges.append(read_json(path, cartridge))
    return cartridges


def build_catalog_item(cartridge: dict[str, Any]) -> dict[str, Any]:
    pricing = cartridge.get("pricing") or {}
    model = str(pricing.get("model") or "free")
    price = pricing.get("price")
    currency = str(pricing.get("currency") or "none")
    period = str(pricing.get("billing_period") or "none")
    if model == "free":
        price_label = "Free"
    elif model == "one_time":
        price_label = f"{currency} {price} once"
    else:
        price_label = f"{currency} {price}/{period}"
    graph = (cartridge.get("contents") or {}).get("semantic_graph") or {}
    return {
        "cartridge_id": cartridge["cartridge_id"],
        "name": cartridge["name"],
        "subtitle": cartridge["subtitle"],
        "category": cartridge["category"],
        "pricing_model": model,
        "price_label": price_label,
        "rating": 4.6 if model != "subscription" else 4.8,
        "downloads": 0,
        "verified_author": bool((cartridge.get("author") or {}).get("verified")),
        "installed": False,
        "owned": model == "free",
        "subscription_active": False,
        "tags": (cartridge.get("metadata") or {}).get("tags") or [],
        "risk_level": (cartridge.get("safety") or {}).get("risk_level", "unknown"),
        "remote_url": None,
        "preview": {
            "semantic_nodes": len(graph.get("nodes") or []),
            "semantic_edges": len(graph.get("edges") or []),
            "default_read_only": bool((cartridge.get("safety") or {}).get("default_read_only", True)),
        },
    }


def refresh_local_catalog() -> dict[str, Any]:
    cartridges = ensure_sample_cartridges()
    items = [build_catalog_item(cartridge) for cartridge in cartridges]
    exported_dir = GRAPH_HUB_ROOT / "exported"
    for path in sorted(exported_dir.glob("*.graphpack.json")):
        payload = read_json(path, None)
        if isinstance(payload, dict) and not any(item["cartridge_id"] == payload.get("cartridge_id") for item in items):
            items.append(build_catalog_item(payload))
    write_json(CATALOG_PATH, {"product_name": "Graph Hub", "items": items})
    return {"product_name": "Graph Hub", "items": items, "catalog_path": str(CATALOG_PATH)}


def find_cartridge_file(cartridge_id: str) -> Path | None:
    for folder in ["cartridges", "exported", "installed"]:
        path = cartridge_path(cartridge_id, folder)
        if path.exists():
            return path
    return None
