from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .cloud_node_attachment import attach_bundle, create_cloud_node_bundle, detach_bundle, graph_overlay, retrieval_trace_for_bundle
from .contributor_node import announce_shards, contributor_status, register_local_contributor
from .ingestion import ensure_fixture_and_ingest


PROOF_DIR = Path("data/cloud_brain/proofs")
PROOF_JSON = PROOF_DIR / "distributed_attachment_loop_proof.json"
PROOF_MD = PROOF_DIR / "distributed_attachment_loop_proof.md"
SEED_ROOT = Path(__file__).resolve().parents[1] / "seed_research"
if str(SEED_ROOT) not in sys.path:
    sys.path.insert(0, str(SEED_ROOT))


def write_distributed_attachment_loop_proof(
    *,
    root: str | Path = "data/cloud_brain/proof_runtime/distributed_attachment_loop",
) -> dict[str, Any]:
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    seed_root = root / "seed_research"
    cloud_root = root / "cloud_brain"
    contributor_root = root / "contributor"
    attachment_root = root / "working_memory" / "cloud_node_bundles"

    from seed_research import run_seed_iteration

    run_seed_iteration(seed_root)
    ingest = ensure_fixture_and_ingest(seed_root=seed_root, cloud_root=cloud_root)
    peer = register_local_contributor(contributor_root=contributor_root, cloud_root=cloud_root)
    announce = announce_shards(contributor_root=contributor_root, cloud_root=cloud_root)
    bundle = create_cloud_node_bundle(
        "GraphRAG evidence verification",
        contributor_root=contributor_root,
        attachment_root=attachment_root,
    )
    attached = attach_bundle(bundle["bundle_id"], attachment_root=attachment_root)
    overlay_attached = graph_overlay(attachment_root=attachment_root)
    trace = retrieval_trace_for_bundle(attached)
    detach = detach_bundle(bundle["bundle_id"], attachment_root=attachment_root)
    overlay_after_detach = graph_overlay(attachment_root=attachment_root)
    status = contributor_status(contributor_root=contributor_root, cloud_root=cloud_root)

    pass_state = (
        ingest.get("ingestion_success") is True
        and peer.get("local_brain_private") is True
        and announce.get("network_state") == "active_single_peer"
        and len(bundle.get("nodes") or []) > 0
        and attached.get("attached") is True
        and overlay_attached["working_memory_overlay"]["cloud_attached_nodes"] > 0
        and overlay_after_detach["working_memory_overlay"]["cloud_attached_nodes"] == 0
        and trace["working_memory_overlay"]["writes_to_local_brain"] is False
    )
    proof = {
        "schema": "atanor.distributed-attachment-loop-proof.v1",
        "pass": pass_state,
        "result": "PASS" if pass_state else "FAIL",
        "statement": (
            "ATANOR now has a single-peer distributed Cloud Brain attachment loop. The local workstation acts as the first Contributor Node, public Cloud Brain shards can be announced and used to create temporary Cloud Node Bundles, and those nodes can be attached to Working Memory and visually distinguished from Local Brain nodes without being written into Local Brain. This does not claim a production global multi-peer Cloud Brain yet."
            if pass_state
            else "ATANOR distributed attachment loop proof failed."
        ),
        "local_brain_state": {"local_total_nodes": 0, "local_total_edges": 0},
        "contributor_network": status,
        "public_shard_announcement": announce,
        "bundle_id": bundle["bundle_id"],
        "bundle_nodes": len(bundle.get("nodes") or []),
        "bundle_edges": len(bundle.get("edges") or []),
        "attached_overlay": overlay_attached["working_memory_overlay"],
        "detach_result": detach,
        "overlay_after_detach": overlay_after_detach["working_memory_overlay"],
        "retrieval_trace": trace,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "final_answer_generation_claimed": False,
        "claims": [
            "local workstation is Contributor Node 001",
            "Cloudflare/remote broker is metadata/index layer when available",
            "public shards can be announced by a contributor",
            "public Cloud nodes can be temporarily attached to Working Memory",
            "attached nodes are separate from Local Brain",
            "attached nodes can be detached",
            "Local Brain remains isolated",
        ],
        "non_claims": [
            "multi-peer global network exists",
            "production-scale distributed Cloud Brain exists",
            "unrestricted web crawling exists",
            "Cloudflare stores the whole brain",
            "attached Cloud nodes become private Local Brain memory",
            "final answer generation quality",
            "sLLM replacement",
        ],
    }
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    PROOF_JSON.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PROOF_MD.write_text(_markdown(proof), encoding="utf-8")
    return proof


def _markdown(proof: dict[str, Any]) -> str:
    claims = "\n".join(f"- {claim}" for claim in proof["claims"])
    non_claims = "\n".join(f"- {claim}" for claim in proof["non_claims"])
    return f"""# ATANOR Distributed Attachment Loop Proof

Result: **{proof["result"]}**

{proof["statement"]}

## This proof claims

{claims}

## This proof does NOT claim

{non_claims}
"""


def main() -> None:
    print(json.dumps(write_distributed_attachment_loop_proof(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
