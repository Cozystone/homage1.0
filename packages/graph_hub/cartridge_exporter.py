from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.cloud_brain.semantic_store import (
    DEFAULT_SEMANTIC_CLOUD_ROOT,
    SEMANTIC_STORE_TRUST_STATE,
    SEMANTIC_STORE_VERIFICATION_STATE,
    SemanticCloudStore,
)

from .audit import append_graph_hub_audit_event
from .cartridge_format import make_graph_cartridge, write_cartridge
from .catalog import add_exported_cartridge_to_catalog
from .models import GRAPH_HUB_ROOT


def export_semantic_cloud_to_cartridge(
    cartridge_id: str,
    name: str,
    description: str,
    pricing_model: str = "free",
    source_store_path: str = "data/cloud_brain/store",
    query: str | None = None,
    limit_nodes: int = 100,
    limit_edges: int = 300,
) -> dict[str, Any]:
    root = Path(source_store_path)
    if root.name == "store":
        cloud_root = root.parent
    else:
        cloud_root = root
    if not cloud_root.is_absolute():
        cloud_root = DEFAULT_SEMANTIC_CLOUD_ROOT.parent.parent / cloud_root
    store = SemanticCloudStore(cloud_root)
    graph = store.graph_sample(limit_nodes=limit_nodes, limit_edges=limit_edges)
    nodes = graph["nodes"]
    edges = graph["edges"]
    if query:
        q = query.casefold()
        matched_ids = {node["id"] for node in nodes if q in str(node.get("label", "")).casefold() or q in " ".join(node.get("aliases") or []).casefold()}
        if matched_ids:
            nodes = [node for node in nodes if node["id"] in matched_ids]
            edges = [edge for edge in edges if edge["source"] in matched_ids or edge["target"] in matched_ids]
    cartridge = make_graph_cartridge(
        cartridge_id=cartridge_id,
        name=name,
        subtitle="Exported from the Semantic Cloud candidate store.",
        description=description,
        category="general",
        pricing={"model": pricing_model, "price": None if pricing_model == "free" else 9, "currency": "USD" if pricing_model != "free" else "none", "billing_period": "monthly" if pricing_model == "subscription" else "none"},
        tags=["semantic-cloud", "candidate-store", "exported"],
        author={
            "name": "ATANOR semantic candidate exporter",
            "id": "atanor-semantic-candidate-exporter",
            "verified": False,
        },
        contents={
            "semantic_graph": {"nodes": nodes, "edges": edges},
            "surface_graph": {"constructions": [], "discourse_moves": [], "lemma_choices": [], "style_profiles": []},
            "reasoning_patterns": [{"id": "semantic_candidate_review", "name": "Review semantic candidates before use"}],
        },
        provenance={
            "source_type": SEMANTIC_STORE_TRUST_STATE,
            "source_paths": [str(store.paths["store"])],
            "exported_from_run_id": (store.latest_growth_run() or {}).get("run_id"),
            "proof_store_only": True,
            "old_mirror_snapshot_used": False,
            "verification_state": SEMANTIC_STORE_VERIFICATION_STATE,
            "independent_source_attestation": False,
            "authoritative_for_answer": False,
        },
        permissions={
            "write_local_brain": False,
            "attach_to_working_memory": False,
            "export_allowed": True,
        },
        safety={
            "default_read_only": True,
            "requires_user_approval_for_local_write": True,
            "trusted": False,
            "risk_level": "unknown",
        },
    )
    output = GRAPH_HUB_ROOT / "exported" / f"{cartridge_id}.graphpack.json"
    write_cartridge(output, cartridge)
    add_exported_cartridge_to_catalog(str(output))
    append_graph_hub_audit_event("exported", cartridge_id, {"path": str(output), "nodes": len(nodes), "edges": len(edges)})
    return {**cartridge, "export_path": str(output), "exported_nodes": len(nodes), "exported_edges": len(edges)}


def export_base_brain_to_cartridge(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError("base_brain_export_future_work")


def export_manual_sample_cartridge(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError("manual_sample_export_future_work")
