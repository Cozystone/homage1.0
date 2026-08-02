from __future__ import annotations

import json
from typing import Any

from packages.cloud_brain.semantic_handoff import write_semantic_cloud_growth_handoff
from packages.cloud_brain.semantic_store import get_semantic_cloud_growth_status

from .attachment import attach_cartridge, detach_cartridge, list_active_attachments
from .audit import list_graph_hub_audit_events
from .catalog import list_catalog_items, refresh_catalog
from .cartridge_exporter import export_semantic_cloud_to_cartridge
from .entitlement import expire_subscription, grant_free_entitlement, grant_local_one_time_entitlement, grant_local_subscription_entitlement
from .installer import install_cartridge, list_installed_cartridges
from .models import GRAPH_HUB_ROOT, utc_now_iso, write_json
from .sandbox import sandbox_preview


PROOF_JSON_PATH = GRAPH_HUB_ROOT / "proofs" / "graph_hub_proof.json"
PROOF_MD_PATH = GRAPH_HUB_ROOT / "proofs" / "graph_hub_proof.md"


def graph_hub_status() -> dict[str, Any]:
    catalog = list_catalog_items()
    installed = list_installed_cartridges()
    attachments = list_active_attachments()
    semantic = get_semantic_cloud_growth_status()
    return {
        "product_name": "Graph Hub",
        "technical_object": "Graph Cartridge",
        "catalog_items": len(catalog),
        "installed_cartridges": len(installed),
        "active_attachments": len([row for row in attachments if row.get("status") == "attached"]),
        "semantic_cloud": semantic,
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "old_mirror_snapshot_used_as_live_cloud": False,
        "billing_mode": "local_entitlement_simulation",
    }


def run_graph_hub_proof() -> dict[str, Any]:
    handoff = write_semantic_cloud_growth_handoff()
    catalog_result = refresh_catalog()
    catalog = catalog_result["items"]
    exported = export_semantic_cloud_to_cartridge(
        "semantic_cloud_kubernetes_demo",
        "Semantic Cloud Kubernetes Demo",
        "A small real proof-store export from the Semantic Cloud Growth Loop.",
        "free",
        limit_nodes=100,
        limit_edges=300,
    )
    free_entitlement = grant_free_entitlement("atanor_base_free")
    free_install = install_cartridge("atanor_base_free")
    purchase = grant_local_one_time_entitlement("startup_strategy_demo")
    startup_install = install_cartridge("startup_strategy_demo")
    startup_attach = attach_cartridge("startup_strategy_demo")
    subscription = grant_local_subscription_entitlement("korean_writing_demo")
    writing_install = install_cartridge("korean_writing_demo")
    writing_attach = attach_cartridge("korean_writing_demo")
    expired = expire_subscription("korean_writing_demo")
    attachments_after_expiry = list_active_attachments()
    sandbox = sandbox_preview("software_architect_demo")
    detach = detach_cartridge("startup_strategy_demo")
    audit = list_graph_hub_audit_events(200)
    pricing_models = {item["pricing_model"] for item in catalog}
    checks = {
        "semantic_handoff_exists": handoff["proof_store_only"] is True and handoff["old_mirror_snapshot_used_as_live_cloud"] is False,
        "catalog_has_three_pricing_models": {"free", "one_time", "subscription"}.issubset(pricing_models),
        "graph_hub_name_used": all("Brain Store" not in json.dumps(item, ensure_ascii=False) for item in catalog),
        "semantic_export_is_quarantined_candidate": (
            exported["provenance"]["source_type"] == "semantic_candidate_store"
            and exported["provenance"]["independent_source_attestation"] is False
            and exported["permissions"]["attach_to_working_memory"] is False
            and exported["provenance"]["old_mirror_snapshot_used"] is False
        ),
        "free_install_no_local_write": free_entitlement["status"] == "free" and free_install["local_brain_write"] is False,
        "one_time_purchase_attach_read_only": purchase["status"] == "owned" and startup_install["local_brain_write"] is False and startup_attach["local_brain_write"] is False,
        "subscription_expiry_disables_attachment": subscription["status"] == "active_subscription" and writing_attach["status"] == "attached" and expired["status"] == "expired_subscription" and any(row["cartridge_id"] == "korean_writing_demo" and row["status"] == "expired" for row in attachments_after_expiry),
        "sandbox_safe_or_warns": sandbox["safe_to_attach"] or bool(sandbox["warnings"]),
        "audit_events_written": len(audit) >= 6,
    }
    proof = {
        "proof_id": "graph_hub_proof",
        "generated_at": utc_now_iso(),
        "passed": all(checks.values()),
        "checks": checks,
        "status": graph_hub_status(),
        "semantic_handoff": {
            "path": handoff["proof_store_path"],
            "concepts": handoff["concepts"],
            "relations": handoff["relations"],
            "evidence": handoff["evidence"],
            "old_mirror_snapshot_used_as_live_cloud": False,
        },
        "export": {
            "path": exported["export_path"],
            "nodes": exported["exported_nodes"],
            "edges": exported["exported_edges"],
            "source_type": exported["provenance"]["source_type"],
            "old_mirror_snapshot_used": exported["provenance"]["old_mirror_snapshot_used"],
            "write_local_brain": exported["permissions"]["write_local_brain"],
        },
        "pricing": {
            "free": free_entitlement["status"],
            "one_time": purchase["status"],
            "subscription": expired["status"],
        },
        "attachment": {
            "startup_attach": startup_attach,
            "writing_after_expiry": [row for row in attachments_after_expiry if row["cartridge_id"] == "korean_writing_demo"],
            "detach": detach,
        },
        "does_not_claim": [
            "real payment processing",
            "real marketplace backend",
            "DRM enforcement",
            "legal commercial licensing readiness",
            "global cartridge marketplace",
            "automatic trust of third-party packs",
            "production billing",
            "old mirror snapshot as live cloud",
        ],
    }
    write_json(PROOF_JSON_PATH, proof)
    PROOF_MD_PATH.write_text(
        "\n".join(
            [
                "# Graph Hub Proof",
                "",
                f"- Generated: {proof['generated_at']}",
                f"- Result: {'PASS' if proof['passed'] else 'FAIL'}",
                f"- Product name: {proof['status']['product_name']}",
                f"- Exported cartridge: `{proof['export']['path']}`",
                f"- Exported nodes/edges: {proof['export']['nodes']} / {proof['export']['edges']}",
                "",
                "## Checks",
                *[f"- {'PASS' if value else 'FAIL'}: {key}" for key, value in checks.items()],
                "",
                "## Honest Boundaries",
                *[f"- Does not claim: {item}" for item in proof["does_not_claim"]],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return proof


def main() -> None:
    print(json.dumps(run_graph_hub_proof(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
